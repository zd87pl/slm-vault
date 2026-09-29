# Spike: SQLCipher + FTS5 + sqlite-vec in one connection (plus Argon2id and keyring)

This spike backs [ADR 0001](../../docs/design/0001-vault-engine.md). It answers the risk the roadmap
lists as "sqlite-vec inside SQLCipher untested across platforms" and checks the key-management
building blocks. Measured on 2026-09-29.

**Revision (review round 1, finding B1).** The warm-cache vector numbers in §6 do not survive the engine's real
write pattern. In WAL mode, one commit by another connection empties every reader connection's page cache, and the
next encrypted KNN query costs 534–549 ms instead of 41 ms. The ADR therefore queries vectors from an **in-engine numpy
matrix**, with SQLCipher only for persistence. §9 has the measurements. sqlite-vec is not on the Phase 1 query path.

## Verdict

- **It works.** One `sqlcipher3` connection (SQLCipher 4.12.0 community, SQLite 3.51.1) runs FTS5 and the
  `sqlite-vec` 0.1.9 loadable extension together, including a single SQL statement that fuses FTS5 BM25 and
  vec0 KNN results with reciprocal rank fusion. The extension loads whether or not the key has been set yet.
  No static linking or vendored build is needed.
- **Wheels exist for every target.** `sqlcipher3` 0.6.2 ships wheels for macOS arm64/x86_64/universal2,
  Windows x64/arm64/x86 and manylinux/musllinux, for CPython 3.10–3.14. `sqlite-vec` 0.1.9 has no
  Windows-arm64 or musl wheel; for those, compile its single C file.
- **The file is opaque without the key.** That covers the header, the stdlib `sqlite3` module, a wrong key and the WAL
  before checkpoint. `PRAGMA rekey` works in WAL mode (570 ms for a 64 MiB file). `VACUUM INTO` and
  `sqlcipher_export` both produce encrypted copies.
- **Deletes need two settings.** `secure_delete` is on by default for keyed SQLCipher databases, and sqlite-vec zeroes
  deleted vectors. But **FTS5 keeps a deleted document's tokens in its index, even after VACUUM**,
  unless the table's `secure-delete` option is on. The engine must turn it on.
- **Encryption costs little for FTS5 and storage; vectors need a different query path.** File-size overhead is about 2%.
  FTS5 queries are unaffected, even right after another connection commits: 10–11 ms becomes 21–23 ms for a common term,
  and a rare term stays under 2 ms (§9). An encrypted sqlite-vec scan is fast only with a warm cache as large as the
  vector table: 100k × 384 float32 takes 40 ms warm and 523 ms with the default 2 MB cache. But any commit on another
  connection empties that cache: 534–549 ms (§9).
- **In-engine matrix instead (§9).** A numpy float32 matrix, loaded from a BLOB table at unlock, answers top-50 in
  1.9 ms (100k × 384) and 9.6–19.8 ms (100k × 1024). Updates cost under 1 ms per 20-chunk document. Loading it at
  unlock takes 1.2–1.6 s and 2.9–3.9 s respectively, dominated by decryption. Hybrid FTS5 + matrix + RRF takes 1.2–11 ms
  even with a commit before every query.
- **sqlite-vec brute force on this x86 box is slower than the roadmap's figure** ("5–15 ms per 100k", from a secondary
  source): 40 ms for 100k × 384 and 120 ms for 100k × 1024 (float32, encrypted, warm cache). The PyPI Linux wheel has no AVX
  code; a local AVX build gave 25 ms and 67 ms. The macOS arm64 wheel uses NEON. With the numpy matrix this question is moot.
- **Argon2id:** a memory-first calibration picked **m = 1 GiB, t = 2, p = 4 (0.82 s)** here. Timings at p = 4 swing by up to
  2× with background load, so calibrate at vault creation and store the parameters.
- **`keyring` has no usable backend in this container.** It falls back to `keyring.backends.fail.Keyring`, because
  `DBUS_SESSION_BUS_ADDRESS` is unset, and `set_password` raises `NoKeyringError`. That is the Linux fallback path
  the ADR designs for.
- **Fallback binding confirmed.** `apsw-sqlite3mc` 3.53.4.0 (SQLite3 Multiple Ciphers) also runs FTS5 and sqlite-vec,
  and it reads and writes SQLCipher-4-format files in both directions against `sqlcipher3`. The binding choice is
  therefore not a one-way door. Its wheels also bundle SQLite's own IVF-PQ extension, `vec1`, which was observed
  here but not evaluated.

## Method

Machine: Linux x86_64 container, Intel Xeon @ 2.10 GHz (AVX2/AVX-512 available), 4 vCPUs shared with other
jobs, 15.7 GiB RAM, CPython 3.11.15. Timings are wall-clock medians (p50) and p95. FTS5 queries: 3 warm-ups, then 30
timed runs. KNN: the first query on a fresh connection is reported separately as "first", then 30 timed runs (10 for the
2 MB-cache rows). Load average was recorded before and after each run (in `results/*.json`). All databases went into a temporary directory that was deleted afterwards.
Vectors are random unit vectors and the text is a synthetic Zipf-distributed vocabulary: latency depends on
sizes and dimensions, not on semantics.

Keys are raw 256-bit keys (`PRAGMA key = "x'…'"`), which is how the engine will use SQLCipher. The data key
is random, so SQLCipher's own PBKDF2 (256,000 iterations by default) is skipped at open.

Dependencies were installed only into scratch `--target` directories and put on `PYTHONPATH`, never into
the project venv or `pyproject.toml`. The three `sqlcipher3` distributions share one import name, so each got its
own directory. For a reader, a throwaway venv is simpler:

```bash
python3.11 -m venv /tmp/spike-venv
/tmp/spike-venv/bin/pip install -r spikes/sqlcipher-vec/requirements-spike.txt
cd spikes/sqlcipher-vec
/tmp/spike-venv/bin/python spike_sqlcipher_vec.py all --out /tmp/results.json   # caps, crypto, fts, knn (~3 min here)
/tmp/spike-venv/bin/python spike_sqlcipher_vec.py knn --knn-sizes 10000 --knn-dims 384   # quick subset
/tmp/spike-venv/bin/python bench_vector_paths.py --out /tmp/vector_paths.json    # §9, ~1 min
/tmp/spike-venv/bin/python check_rekey_crash.py --out /tmp/rekey_crash.json      # §10, ~15 s
/tmp/spike-venv/bin/python bench_argon2.py --out /tmp/argon2.json                # ~1 min
/tmp/spike-venv/bin/python check_keyring.py
/tmp/spike-venv/bin/python check_apsw_sqlite3mc.py
# inspect other platforms' wheels without installing them
/tmp/spike-venv/bin/pip download --no-deps --only-binary=:all: --python-version 3.11 \
    --platform macosx_11_0_arm64 -d /tmp/wheels sqlcipher3==0.6.2 sqlite-vec==0.1.9
/tmp/spike-venv/bin/python inspect_wheels.py /tmp/wheels/*.whl
```

To benchmark a custom sqlite-vec build, pass `--vec-ext /path/to/vec0.so`. The file must be named `vec0.*`
so that SQLite finds the `sqlite3_vec_init` entry point. This spike's AVX build was made with:
`gcc -O3 -mavx -mavx2 -mfma -fPIC -shared -DSQLITE_VEC_ENABLE_AVX sqlite-vec.c -o avx/vec0.so -lm`, from the
v0.1.9 release amalgamation.

The scripts are not tests: none is named `test_*.py`, and `spikes/` is outside the pytest `testpaths`.
Raw outputs from this run are in [`results/`](results/), with scratch paths replaced by `<deps>`/`<scratch>`.

## Results

### 1. Bindings and wheels

| Package (version) | SQLite / cipher | FTS5 | Loads sqlite-vec | Wheels (CPython 3.11) |
|---|---|---|---|---|
| `sqlcipher3` 0.6.2 (coleifer) | 3.51.1 / SQLCipher 4.12.0 community, OpenSSL 3.6.0 static | yes | yes | macOS arm64, x86_64, universal2; Windows x64, arm64, x86; manylinux_2_28 x86_64/aarch64/i686; musllinux |
| `sqlcipher3-binary` 0.6.0 | 3.51.1 / 4.12.0, OpenSSL 3.5.4 | yes | yes | manylinux x86_64 only |
| `sqlcipher3-wheels` 0.5.7 (fork) | 3.51.1 / 4.12.0 | yes | yes | same as `sqlcipher3` plus ppc64le/s390x |
| `apsw-sqlite3mc` 3.53.4.0 | 3.53.4 / SQLite3MultipleCiphers (SQLCipher-compatible mode) | yes | yes | macOS arm64/x86_64, Windows x64/arm64/x86, manylinux, musllinux |
| `sqlite-vec` 0.1.9 | loadable `vec0` | n/a | n/a | macOS arm64 + x86_64, Windows x64, manylinux x86_64 + aarch64. **No win_arm64, no musl.** |
| `argon2-cffi-bindings` 26.1.0 | n/a | n/a | n/a | abi3 wheels for macOS arm64, Windows x64/arm64/x86, manylinux, musllinux. **No macOS x86_64 wheel** (Intel Macs build from source) |

Compile options for `sqlcipher3` 0.6.2: `ENABLE_FTS5`, `ENABLE_LOAD_EXTENSION`, `HAS_CODEC`, `TEMP_STORE=2`
(temporary tables and sort spills stay in memory, never in plaintext temp files) and `THREADSAFE=1`.
SQLCipher defaults: 4096-byte pages, HMAC-SHA512, PBKDF2-HMAC-SHA512 with 256,000 iterations (unused with raw keys),
`cipher_memory_security = 0` and `cipher_log_level = WARN` to stderr. The engine should route or silence that
log: a wrong key prints `hmac check failed for pgno=1`.

`inspect_wheels.py` on the downloaded macOS arm64 and Windows wheels:

- **macOS:** every Mach-O (`sqlcipher3/_sqlite3.cpython-311-darwin.so`, `sqlite_vec/vec0.dylib`, apsw's) links only
  `/usr/lib/libSystem.B.dylib`. OpenSSL is static, so the Apple "unsafe libcrypto" abort cannot happen. Each binary is
  **linker-signed ad hoc with no Team ID**. The app must therefore re-sign every one of them with its Developer ID under the
  hardened runtime, or library validation refuses to load them. That includes `vec0.dylib`, loaded via `load_extension`.
- **Windows:** `_sqlite3.cp311-win_amd64.pyd` imports only OS DLLs (`CRYPT32`, `ADVAPI32`, `WS2_32`, UCRT) and `python311.dll`,
  with no external libcrypto or sqlite3 DLL. `vec0.dll` imports only `KERNEL32`.

### 2. One connection, all features

`caps` (see `results/caps.json`): FTS5 table and vec0 table in the same encrypted connection, joined in one query.
Also verified: loading the extension **before** `PRAGMA key` works; loading happens per connection and
does not touch the pager. The hybrid statement the engine can use verbatim, as benchmarked below:

```sql
WITH fts AS (SELECT rowid AS id, row_number() OVER (ORDER BY rank) AS r
             FROM chunks_fts WHERE chunks_fts MATCH :q ORDER BY rank LIMIT 50),
     knn AS (SELECT rowid AS id, row_number() OVER (ORDER BY distance) AS r
             FROM chunks_vec WHERE embedding MATCH :v AND k = 50)
SELECT coalesce(fts.id, knn.id) AS id,
       coalesce(1.0/(60+fts.r), 0) + coalesce(1.0/(60+knn.r), 0) AS score
FROM fts FULL OUTER JOIN knn ON fts.id = knn.id ORDER BY score DESC LIMIT 10;
```

### 3. Encryption checks (`crypto`)

Test database: a normal table, an FTS5 table and a vec0 table, with a marker sentence, a marker FTS token and a
marker vector (8 × 1234.5678f), in WAL mode.

| Check | Plaintext control | Encrypted |
|---|---|---|
| First 16 bytes | `SQLite format 3\0` | random salt (`23fed29f…`) |
| Marker text / FTS token / vector bytes in `-wal` before checkpoint | found / found / found | none |
| Same, in main file after checkpoint | found / found / found | none |
| Open with stdlib `sqlite3` | n/a | `DatabaseError: file is not a database` |
| `sqlcipher3` with no key / wrong key | n/a | `file is not a database` / same |
| `PRAGMA rekey` in WAL mode | n/a | ok; old key then fails, new key opens |
| `VACUUM INTO copy.db` | n/a | copy is **encrypted with the same key** (no plaintext header, no markers) |
| `ATTACH … KEY x'new'` + `sqlcipher_export()` | n/a | encrypted with the new key; FTS5 and vec0 tables copied and queryable (51/51/51 rows, KNN and MATCH find the marker) |

Our own page decryption (AES-256-CBC, IV at the start of the 80-byte reserve, raw key used directly)
reproduces SQLCipher's page format: page-size field 4096, reserve field 80. It is used for the residue checks.

### 4. What survives a DELETE inside the encrypted file

Each result is visible to someone holding the data key and reading free pages. Scenarios run on an encrypted database
with 200 filler rows: insert the markers, delete them, checkpoint, then decrypt every page and search.

| Scenario | Row text | FTS5 token | Vector bytes |
|---|---|---|---|
| SQLCipher defaults (`secure_delete` = 1 on keyed DBs) | gone | **still present, also after VACUUM** | gone |
| `PRAGMA secure_delete = OFF` | **present** (gone after VACUUM) | **present, also after VACUUM** | gone |
| `secure_delete = ON` + FTS5 `INSERT INTO fts(fts, rank) VALUES('secure-delete', 1)` | gone | gone | gone |

sqlite-vec zeroes a deleted vector's slot in its chunk blob. FTS5 by default appends a delete marker and
leaves the old segment until a merge, and VACUUM does not merge FTS5 segments. The `secure-delete` option
(SQLite ≥ 3.42) removes the entries eagerly.

### 5. FTS5 and hybrid latency (`fts`)

10,000 chunks × 300 words (20.2 MiB of text) in an external-content FTS5 table
(`tokenize='unicode61 remove_diacritics 2'`) plus a 384-d float32 vec0 table. Query:
`… MATCH ? ORDER BY rank LIMIT 10` with `snippet()`. Times are p50 / p95 in ms.

| Query | Plain, 2 MB cache | Encrypted, 2 MB cache | Plain, large cache | Encrypted, large cache | Hits |
|---|---|---|---|---|---|
| common term | 10.7 / 13.2 | 10.9 / 14.2 | 10.4 / 11.0 | 10.5 / 11.4 | 10 |
| mid-frequency term | 0.72 / 0.78 | 0.77 / 0.93 | 0.73 / 0.94 | 0.96 / 1.27 | 10 |
| rare term | 0.17 / 0.26 | 0.16 / 0.23 | 0.15 / 0.18 | 0.26 / 0.31 | 9 |
| two terms (AND) | 0.31 / 0.40 | 0.29 / 0.35 | 0.29 / 0.40 | 0.49 / 0.53 | 10 |
| phrase `"boiler warranty expires"` | 0.23 / 0.28 | 0.22 / 0.30 | 0.21 / 0.24 | 0.36 / 0.40 | 10 |
| prefix `lika*` | 9.0 / 9.8 | 9.7 / 15.1 | 8.7 / 9.1 | 9.1 / 15.5 | 10 |
| entity `"ZX-10203"` | 0.05 / 0.07 | 0.05 / 0.07 | 0.05 / 0.07 | 0.05 / 0.08 | 1 |
| OR of 5 terms | 6.6 / 10.3 | 5.5 / 7.4 | 5.4 / 5.8 | 5.9 / 7.9 | 10 |
| **hybrid RRF** (FTS5 top-50 + KNN top-50) | 5.3 / 7.7 | **51.3 / 55.2** | 5.5 / 6.9 | **4.8 / 5.7** | 10 |

Build (insert 10k rows + FTS5 `rebuild` + 10k vectors): 1.05 s plaintext, 1.33 s encrypted. File size:
65.9 MB plaintext vs 67.3 MB encrypted (**+2.0%**, the 80-byte per-page reserve). `PRAGMA rekey` of the 64 MiB
file: 570 ms. First query after open: 20 ms encrypted vs 12 ms plaintext. An earlier run under heavier background load
had encrypted "common term" at 24.7 ms p50; single-digit-ms differences between columns are noise.

Every query sits well inside the roadmap's "under 100 ms search-as-you-type" budget. The one row that moves
is the hybrid query: its KNN half re-decrypts 15 MiB of vector pages per query when the cache is 2 MB. The ADR
no longer runs the KNN half in SQLite: §9C measures hybrid with the in-engine matrix.

### 6. sqlite-vec brute-force KNN (`knn`, k = 10)

PyPI wheel. "2 MB cache" is SQLCipher's default (`cache_size = -2000`). "Large cache" is 1.5 × the file size. "first"
is the first query on a fresh connection, i.e. decrypting the whole vector table. Top-10 results matched a numpy
exact search for every 10k float32 case.

| n | dim | type | encrypted | file MiB | insert s | 2 MB cache p50 / p95 ms | large cache first / p50 / p95 ms |
|---|---|---|---|---|---|---|---|
| 10k | 384 | float32 | no | 15.3 | 0.38 | 6.0 / 8.8 | 5.2 / 5.2 / 5.5 |
| 10k | 384 | float32 | yes | 15.6 | 0.38 | 57.3 / 64.8 | 70.2 / 4.2 / 5.3 |
| 10k | 384 | int8 | yes | 4.1 | 0.44 | 5.5 / 5.9 | 24.1 / 3.5 / 5.4 |
| 10k | 384 | bit | yes | 0.7 | 0.37 | 0.61 / 0.65 | 3.4 / 0.59 / 0.63 |
| 10k | 1024 | float32 | no | 40.3 | 0.86 | 18.2 / 19.2 | 16.0 / 15.1 / 18.0 |
| 10k | 1024 | float32 | yes | 41.1 | 0.79 | 153.6 / 163.4 | 158.5 / 11.9 / 13.4 |
| 10k | 1024 | int8 | yes | 10.5 | 0.55 | 39.7 / 46.0 | 40.5 / 8.4 / 9.1 |
| 10k | 1024 | bit | yes | 1.5 | 0.32 | 0.89 / 1.02 | 6.6 / 0.87 / 0.96 |
| 100k | 384 | float32 | no | 149.4 | 3.9 | 54.8 / 57.8 | 55.1 / 55.0 / 69.3 |
| 100k | 384 | float32 | yes | 152.3 | 4.7 | 523 / 572 | 568 / **39.7** / 43.1 |
| 100k | 384 | int8 | no | 39.0 | 3.1 | 44.4 / 60.2 | 40.8 / 40.6 / 55.4 |
| 100k | 384 | int8 | yes | 39.8 | 3.0 | 147 / 206 | 150 / 33.6 / 37.5 |
| 100k | 384 | bit | yes | 6.9 | 1.5 | 2.8 / 3.2 | 19.9 / 2.8 / 3.2 |
| 100k | 1024 | float32 | no | 394.6 | 7.2 | 149 / 208 | 166 / 153 / 168 |
| 100k | 1024 | float32 | yes | 402.4 | 9.3 | 1304 / 1442 | **2194** / **120** / 137 |
| 100k | 1024 | int8 | no | 100.3 | 5.2 | 100 / 116 | 100 / 98 / 118 |
| 100k | 1024 | int8 | yes | 102.3 | 5.2 | 386 / 415 | 467 / 89 / 110 |
| 100k | 1024 | bit | no | 14.5 | 3.4 | 6.1 / 8.2 | 7.1 / 6.4 / 7.1 |
| 100k | 1024 | bit | yes | 14.8 | 2.9 | 48.7 / 61.9 | 48.1 / 5.1 / 6.6 |

(The full 24-row matrix, including the plaintext int8/bit rows for 10k, is in `results/knn.json`.)

The same float32 rows with **sqlite-vec built locally with AVX** (`results/knn_avx.json`):

| n | dim | encrypted | 2 MB cache p50 | large cache first / p50 / p95 ms | vs PyPI wheel (large-cache p50) |
|---|---|---|---|---|---|
| 10k | 384 | no / yes | 3.4 / 54.2 | 3.2 / 3.1 / 3.4 and 63.8 / 2.0 / 3.0 | 5.2 → 3.1, 4.2 → 2.0 |
| 10k | 1024 | no / yes | 9.2 / 126 | 9.0 / 8.2 / 8.8 and 136 / 5.3 / 6.2 | 15.1 → 8.2, 11.9 → 5.3 |
| 100k | 384 | no / yes | 41.2 / 501 | 45.3 / 39.4 / 49.5 and 1379 / **25.5** / 31.9 | 55.0 → 39.4, 39.7 → 25.5 |
| 100k | 1024 | no / yes | 98 / 1293 | 94 / 104 / 127 and 1750 / **67.4** / 84.8 | 153 → 104, 120 → 67.4 |

Observations:

- **Encrypted with a warm, large cache is faster than plaintext.** Plaintext reads of the vector chunk blobs
  go through `read()` on every query. SQLite reads overflow pages directly for unencrypted files, so they never sit in
  its page cache. The encrypted path keeps decrypted pages in the cache.
- **Memory is the real cost.** A warm encrypted vector table means `n × dim × bytes` of plaintext vectors in the
  engine's RAM while unlocked: 100k × 384 float32 is about 150 MiB, while int8 is a quarter of that and bit 1/32. The first query after unlock
  pays the full decrypt, 0.57 s for 100k × 384 and 2.2 s for 100k × 1024. The engine should warm the cache in the
  background at unlock.
- int8 does not speed up the scan much in this build. bit vectors do, by 10–20×, but they need a float rescore of the
  candidates for quality. That is the standard binary-prefilter pattern, and only worth it well above 100k chunks.
- Insert throughput (about 10–30k vectors/s) is not a bottleneck next to embedding time.
- **These are single-connection numbers.** §9 shows that they collapse once another connection writes.

### 7. Argon2id (`bench_argon2.py`, argon2-cffi 25.1.0)

Median of 3 derives per cell. The ranges span three separate grid runs, because the other jobs sharing
the 4 vCPUs mostly affect p = 4. Latest run: `results/argon2.json`.

| m (MiB) | t | p = 1 ms | p = 2 ms | p = 4 ms |
|---|---|---|---|---|
| 64 | 2 | 107–131 | 70–95 | 38–84 |
| 64 | 3 | 155–180 | 99–107 | 59–62 |
| 64 | 4 | 197–231 | 115–137 | 71–83 |
| 256 | 2 | 567–637 | 325–374 | 180–211 |
| 256 | 3 | 778–862 | 456–485 | 265–274 |
| 256 | 4 | 1081–1094 | 622–647 | 340–453 |
| 512 | 2 | 1289–1349 | 698–794 | 391–599 |
| 512 | 3 | 1745–1861 | 1015–1084 | 577–1196 |
| 512 | 4 | 2268–3559 | 1374–1695 | 760–1655 |

OWASP's floor (19 MiB, t = 2, p = 1) takes 28–30 ms, about 25× cheaper than what a desktop can afford.

Calibration (`--calibrate-only`, `results/argon2_calibration.json`), memory first, then time, targeting 0.5–1.0 s:
256 MiB → 175 ms, 512 MiB → 425 ms, 1024 MiB → **821 ms, chosen: m = 1 GiB, t = 2, p = 4**. Under load, the
same algorithm chose 512 MiB/t=2 (861 ms) in one run and 256 MiB/t=3 (776 ms) in another. That is why the parameters are
measured once at vault creation, stored in the key header and reused. They are never re-derived at unlock.

### 8. keyring (`check_keyring.py`, keyring 25.7.0)

```text
selected:  keyring.backends.fail.Keyring   (only other backend: chainer, priority -1)
SecretService: RuntimeError: Unable to initialize SecretService: Environment variable DBUS_SESSION_BUS_ADDRESS is unset
set_password: NoKeyringError: No recommended backend was available. …
```

On Python 3.11, keyring also needs `importlib_metadata` and `backports.tarfile`. Pip resolves them, but a frozen
build must include them. The engine treats `fail.Keyring`, the chainer with no backends, and the `keyrings.alt`
plaintext/"encrypted file" backends as **"no OS keystore"**: convenience unlock is off and only passphrase and
recovery-key unlock work (ADR 0001 §5.4).

### 9. Vector search under concurrent writes, and the in-engine matrix (`bench_vector_paths.py`)

Added after review finding B1, adapting the reviewer's `cache_invalidation.py`. Encrypted database, WAL, a reader connection
with a cache 1.5 × the file, and a second connection that commits one row to an unrelated table, as the engine's audit,
`last_seen` and job writes do on almost every request. Two full runs; `results/vector_paths.json` is the second.

**A. Page-cache invalidation** (100k × 384 vec0 plus 10k-chunk FTS5, 202 MiB; p50 in ms):

| Query | Warm | After another connection commits one row | After the same connection commits |
|---|---|---|---|
| sqlite-vec KNN, k = 10 | 41.4 | **534–549** | 41.2–44.7 |
| FTS5, common term | 10.3–11.4 | 21.2–23.1 | n/a |
| FTS5, rare term | 0.15–0.28 | 1.5–1.7 | n/a |

The reviewer's run of the same script gave 723 ms and 608 ms, and my rerun of it gave 626 and 571 ms (20k × 384:
10 → 108–125 ms). A reader's cache survives only its *own* connection's commits, and the engine needs concurrent readers.
FTS5 reads few pages per query, so invalidation costs it about 10 ms at most.

**B. In-engine numpy matrix** (`chunk_vectors(chunk_id INTEGER PRIMARY KEY, vec BLOB)` in SQLCipher; numpy 2.4 with
OpenBLAS; top-50 by dot product plus `argpartition`; results matched an exact search):

| n × dim | Matrix in RAM | Load at unlock (per-row / 4096-vector blocks) | Top-50 p50, BLAS threads / 1 thread | With a 30% collection mask | Persist one 20-chunk document | In-memory append | Delete one vector |
|---|---|---|---|---|---|---|---|
| 100k × 384 | 146 MiB | 1.56–1.65 s / 1.21 s | **1.9 ms** / 6.6–7.5 ms | 2.1–2.3 ms | 0.6–1.0 ms | 0.04–0.05 ms | 0.3–0.5 ms |
| 100k × 1024 | 391 MiB | 2.9–3.9 s / 3.55 s | **9.6–19.8 ms** / 29 ms | 9.4–16.1 ms | 0.9–1.1 ms | 0.02 ms | 0.2–0.4 ms |

The unlock load is dominated by decrypting the whole table, so a block snapshot helps little. It runs in the
background after unlock; until it finishes, search is keyword-only. The 1024-d rows (4 KiB) overflow a 4 KiB page, and
≤ 512-d rows fit, so 512 dimensions should load in about 2 s.

**C. Hybrid** (FTS5 top-50 in SQLCipher + matrix top-50 + RRF in Python, 10k chunks, 384-d):

| Query | Warm p50 | Commit before every query: p50 / p95 |
|---|---|---|
| two terms (AND) | 0.6–4.0 ms | 1.2–3.5 / 1.7–3.6 ms |
| common term | 10.6–20.0 ms | 11.3–19.4 / 12.0–43.8 ms |

### 10. Crash during `PRAGMA rekey` (`check_rekey_crash.py`)

Added for review finding B3, because the ADR's two-phase data-key rotation assumes that rekey is all-or-nothing. Setup: a 235 MiB
encrypted WAL database; a full rekey takes 2.2 s. A child process ran the rekey and was SIGKILLed at 15%, 40% and 70% of
that time, when the WAL held 39, 95 and 169 MiB. **Every time the file reopened with the old key, all rows present and
`quick_check` ok; the new key failed.** After a completed rekey, only the new key opens it (`results/rekey_crash.json`).

## Blockers, workarounds and what this spike did not show

- **No blocker** on Linux x86_64. Loading the extension into SQLCipher builds works, so no workaround was needed. If a
  future platform lacks load-extension support, there are two ways out. One is compiling `sqlite-vec.c` into the SQLCipher
  amalgamation with `SQLITE_CORE` and registering `sqlite3_vec_init` via `sqlite3_auto_extension`, which means a custom
  `sqlcipher3` build. The other is switching to `apsw-sqlite3mc`, which reads the same files (§1).
- **Not run on macOS or Windows.** Mac numbers (NEON build), the hardened-runtime load of a re-signed `vec0.dylib`,
  and notarization all need a macOS CI job with a signing identity. That is PR 13 in the ADR's plan. Windows arm64 needs a
  self-built `vec0.dll`.
- The x86 sqlite-vec numbers come from the PyPI wheel's scalar/SSE kernels on a 2.1 GHz shared VM. This is moot
  for Phase 1, because the ADR queries vectors from numpy (§9). An AVX `vec0` would need two binaries and runtime CPU dispatch.
- Matrix load time and BLAS-threaded query times vary run to run on this shared 4-vCPU VM (ranges above). Mac numbers
  (Accelerate/OpenBLAS on Apple Silicon) are unmeasured.
- Cold-from-disk latency was not measured, because dropping the OS page cache would disturb other jobs on this machine.
  "first" numbers include decryption but read from the OS page cache.
- SQLite's `vec1` extension, bundled in apsw wheels (IVF-PQ, needs training), was found but not evaluated.

## Implications carried into ADR 0001

1. Store: `sqlcipher3` pinned, a 256-bit raw key (HKDF-derived from the DEK), WAL, `secure_delete = ON` set explicitly,
   and FTS5 tables created with `secure-delete = 1`. Extension loading is never enabled, because sqlite-vec is not needed on the query path.
2. Vectors are persisted as BLOB rows in SQLCipher and queried from an in-engine numpy matrix that is loaded in the background
   at unlock (§9). Default embedding width is 512 at most (Qwen3-Embedding MRL); the matrix stays float32 up to about 100k chunks.
3. Backups via `VACUUM INTO` (same key) or `sqlcipher_export` (new key). Both were verified to produce encrypted copies.
4. Argon2id calibrated memory-first at vault creation, with parameters stored in the key header. On slow machines the floor is RFC 9106's second recommended option (64 MiB, t = 3).
5. OS-keystore unlock is optional, and "no backend" is a normal state, not an error.
6. Every bundled Mach-O is re-signed with the app's Team ID. sqlite-vec is not bundled in Phase 1.
