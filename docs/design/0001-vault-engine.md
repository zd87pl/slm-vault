# ADR 0001: One vault engine that owns the key, the index and consent

| | |
|---|---|
| Status | Proposed (Phase 1 foundation) |
| Date | 2026-09-29 |
| Base commit | `2ec68a7` (all `path:line` references are at this commit) |
| Decides | Engine process model, IPC, data root and storage format, key hierarchy, consent/audit model, MCP shim, sidecar packaging, migration from today's layout, Phase 1 PR plan |
| Evidence | [ROADMAP.md](../launch-plan/ROADMAP.md) · [research notes](../launch-plan/research/) · [SQLCipher/sqlite-vec spike](../../spikes/sqlcipher-vec/README.md) |

Names: the product rename is pending ([ROADMAP.md](../launch-plan/ROADMAP.md), "Rename before launch"). This
document uses `<App>` for the display name, `<app>` for the lowercase slug (directories, socket, CLI) and
`<bundle-id>` for the reverse-DNS identifier. Code must define them once (`APP_ID`, `APP_NAME`), so that the rename
is a one-line change.

---

## 1. Context, goals and non-goals

### The root cause

The roadmap traces four defects to one missing owner. The section "One engine process should own the key, the
index and consent" lists them:

- **The index split.** MCP read `$VAULT_PATH/rag.db` while the GUI and CLI wrote
  `private_models/<profile>/vault/rag.db`. Phase 0 (#23) repointed MCP at the profile index, but it still
  reopens the index in a second process with its own key read (`advanced_vault/mcp_server/agent.py:1-28`).
- **Shell-built consent.** The consent dialog is a subprocess the MCP server spawns
  (`advanced_vault/mcp_server/consent.py:195-254`; argv-only since #18), so consent is decided by whichever process an
  agent happened to launch.
- **A frozen app cannot serve MCP.** The app points Claude Desktop at a system Python with a `PYTHONPATH` hack
  (`advanced_vault/gui/mcp_setup.py:129-192`).
- **The key sits next to the data.** Five code paths write a random `master.key` beside the database they protect
  (`cli/main.py:26-56`, `mcp_server/server.py:96-125`, `private_models/manager.py:402-412`, `gui/vault_app.py:6898-6908`,
  and the MCP agent through the manager, `mcp_server/agent.py:195-196`). No user secret, KDF or keychain is involved
  ([codebase_audit_core.md](../launch-plan/research/codebase_audit_core.md) Q5).

The audit also found names, absolute paths, unsalted content hashes, embeddings (in `rag.db`, `rag.hnsw`/`rag.brute.json`
and the global `~/.enclave/embedding_cache.db`), chat history, activity logs and consent state in plaintext
(Q5 "Plaintext leakage"). The README now says so (#22). Phase 1 has to make it untrue.

### Goals

1. **One engine process.** Only one process ever holds the unwrapped data key. It is the only reader and writer of
   the encrypted store, the only place ingestion, retrieval and generation run, the only consent authority and the only audit writer.
2. **Thin clients.** The Tauri UI, the `<app>` CLI and the MCP stdio shim are clients. They get identical answers and
   citations by construction.
3. **Nothing sensitive in plaintext on disk.** The exceptions are listed in §4.6 and none of them is document-derived. This
   is the Phase 1 exit criterion "Nothing on disk in plaintext except documented metadata".
4. **A user secret.** A random data key is wrapped by an Argon2id passphrase key, an OS-keystore key and a printable
   recovery key. The passphrase can change without re-encrypting data.
5. **A locked vault is closed.** An agent calling a locked or stopped vault gets "open <App> to unlock your vault", never data.
6. **Consent is decided in the vault's own UI.** It is scoped, expiring, quota-limited and audited, and it never runs as a shell command.
7. **Safe migration** of today's data: one-shot, resumable, verifiable, and non-destructive until the user confirms.

### Non-goals (Phase 1)

- The Tauri UI itself (Phase 2). Phase 1 defines the IPC it will use and keeps the Flet GUI alive as a client (§11).
- Retrieval quality work: Docling, OCR, reranker, verified citations, Qwen3.5, llama.cpp, ONNX embeddings. These are Phase 1
  items too, but they plug into interfaces defined here and get their own design notes.
- Sync, household sharing, multi-device (Phase 5). Nothing here may block them; §4 keeps keys per vault and
  blobs separate from the index for that reason.
- Protecting an unlocked vault from malware running as the same user. That is not achievable (§10), and this
  document says so rather than pretending otherwise.
- Secrets management. The `encrypted_kv` store is quarantined ([ROADMAP.md](../launch-plan/ROADMAP.md) disposition
  table). §9 covers only how its data is carried over or exported.

---

## 2. Process architecture

```
 ┌──────────────── <App>.app (signed, notarized) ────────────────┐
 │  Tauri shell (Rust)                   WebView (TypeScript UI) │
 │   • spawns + supervises engine  ◄──── Tauri commands/channels │
 │   • holds owner token (memory)                                │
 │   • OS events: sleep/lock/power                               │
 │        │ owner connection (UDS / named pipe)                  │
 │        ▼                                                      │
 │  <app>-engine (Python, PyInstaller onedir, same Team ID)      │
 │   key custody · store · ingest · retrieval · generation       │
 │   consent/policy · audit · migrations                         │
 └────────▲──────────────────────────▲───────────────────────────┘
          │ owner (after passphrase)  │ agent role (token file)
     `<app>` CLI                 `<app>-mcp` stdio shim  ◄── stdio ── Claude Desktop / Cursor / LM Studio …
```

**The engine** is a headless asyncio process with these parts:

- **IPC server (§3).** Runs on the event loop.
- **One writer connection and a small reader pool** to the SQLCipher database. Queries run in a thread pool; SQLite
  releases the GIL.
- **One generation worker** thread that owns the LLM runtime. MLX and llama.cpp both prefer a single owner thread.
- **An ingestion scheduler** that runs staged jobs at low priority. Interactive queries preempt it.
- **Key custody.** Holds the unwrapped DEK in memory only while unlocked (§5.6).

**Who starts it.**

| Situation | Starter | Engine lifetime |
|---|---|---|
| Consumer app | The Tauri shell spawns the sidecar at app launch (§8.2) | Until the app quits. Closing the window leaves the tray and the engine running |
| CLI with the app running | Nobody; the CLI connects to the running engine | n/a |
| CLI or dev without the app | `<app> engine start [--foreground]` | Until `<app> engine stop` or Ctrl-C. No UI, so consent prompts cannot be answered and agent calls outside existing grants are denied |
| MCP client launches the shim | The shim never starts an engine (§7.4) | n/a |

**Single instance.** The engine takes an exclusive, non-blocking lock on `<data_root>/engine.lock` for its lifetime:
`fcntl.flock` on macOS/Linux, `msvcrt.locking`/`LockFileEx` on Windows. A second engine prints the running
engine's socket path and exits with code 3. Before binding, the engine removes a stale socket, which can only
exist when no lock holder does. The Tauri UI also uses `tauri-plugin-single-instance`.

**Locked state.** The engine runs normally with no DEK. It answers `hello`, `vault.status` and `vault.unlock`. Every
data method returns the error `VAULT_LOCKED`, and agent methods return the "open <App> to unlock" error (§7.4). Watchers
record nothing on disk while locked. A reconciliation scan at unlock catches up instead, so file paths never sit in
an unencrypted queue.

**Crash and restart.**

- **Recovery.** SQLite WAL recovery is automatic on the next open. Ingestion jobs are rows in the encrypted `jobs` table
  with a stage and attempt count. They resume after unlock, and three failures park a job as `failed` with the error text.
- **Restart policy.** The Tauri supervisor restarts the engine with backoff (1, 2, 4 … 30 s). After 5 crashes in 2 minutes
  it gives up and shows the last 50 log lines, which never contain document content (§4.6).
- **After a restart** the vault comes back locked. If keystore unlock is enabled (§5.3), the UI immediately calls
  `vault.unlock{method:"keystore"}`, which triggers Touch ID where it is configured.
- **Orphan protection.** The engine exits when its stdin reaches EOF, which happens when the Tauri parent dies. It is
  never left holding the key without a UI. A headless engine started with `<app> engine start` is the explicit exception.

**Background indexing** runs only while unlocked and in stages ([document_rag_sota.md](../launch-plan/research/document_rag_sota.md) §10):

1. **Text layer and FTS5** (seconds). The document is searchable immediately.
2. **Embeddings** (minutes).
3. **OCR of hard pages, contextual headers, extraction** (hours). This stage runs only on AC power when idle; the shell reports
   power state through `settings.set_runtime`.

On lock, the scheduler finishes or aborts the current transaction and pauses.

---

## 3. IPC

### 3.1 Transport

| OS | Transport | Location | Access control |
|---|---|---|---|
| macOS | Unix domain socket | `<runtime_dir>/engine.sock`, where `<runtime_dir>` = `platformdirs.user_runtime_dir("<app>")` (`~/Library/Caches/TemporaryItems/<app>`). If the path exceeds 100 bytes (the `sun_path` limit is 104), fall back to `$TMPDIR/<app>` | Directory created `0700`. The engine refuses to start if the directory is a symlink or not owned by the current uid. Socket `0600`. Peer uid checked with `getpeereid()`; the peer pid (`LOCAL_PEERPID`) is logged |
| Linux | Unix domain socket | `$XDG_RUNTIME_DIR/<app>/engine.sock`. Fallback `/tmp/<app>-<uid>/`, with the same ownership and mode checks | Same; `SO_PEERCRED` uid check |
| Windows (Phase 4) | Named pipe | `\\.\pipe\<app>-engine-<user SID>` | Explicit DACL granting only the current user SID, `FILE_FLAG_FIRST_PIPE_INSTANCE` against squatting, `PIPE_REJECT_REMOTE_CLIENTS`. The client checks the server image path with `GetNamedPipeServerProcessId` |

HTTP on loopback is rejected (§12): any local user can reach a port, and browsers add DNS-rebinding exposure. The MCP
security guidance prefers stdio or restricted IPC for local servers
([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §4).

**The webview never touches the socket.** The TypeScript UI calls Tauri commands. The Rust core relays them to the engine and
streams results back through Tauri channels. Document-derived content rendered in the webview (PDF.js, Markdown answers)
is untrusted. A strict CSP plus the Rust-side command allow-list keeps an XSS in rendered content away from the owner
connection.

### 3.2 Authentication and roles

Every connection starts with `hello` and then `auth`. There are two roles.

| Role | Can | Credential |
|---|---|---|
| `owner` | Everything: unlock/lock, ingest/delete, settings, consent decisions, audit, raw document access for the UI viewer | (a) The **owner token**: 32 random bytes the Tauri shell generates per launch and writes to the engine's stdin at spawn. It never touches disk. (b) Or a successful `auth.passphrase` / `auth.recovery` on the connection: the engine verifies it by unwrapping the header slot. The CLI uses this path, via a prompt or `--passphrase-fd` |
| `agent` | Only the `agent.*` methods (§3.4), always through policy and consent | The **agent token**: 32 random bytes written at engine start to `<runtime_dir>/engine.token` (`0600`, directory `0700`), rotated on every engine start |

Tokens are compared in constant time (`hmac.compare_digest`). Failed `auth` closes the connection. After 5 failures a
minute, the engine logs an audit event and slows further attempts.

**Honest limits.** Anything running as the same user can read `engine.token` and so reach the agent role. Nothing
on a desktop distinguishes Claude Desktop from malware posing as it (§6.3). The split still buys three things:

- Only the UI, or someone who knows the passphrase, can *approve* consent, change grants, read raw documents or export data.
- An impersonating process gets exactly what an agent gets: nothing without a grant, and grants for sensitive
  collections always need a fresh click in the UI.
- Peer-uid checks stop other local users even if file modes are wrong.

### 3.3 Protocol

**Framing and dispatch.**

- **Framing.** JSON-RPC 2.0, one message per line (NDJSON), UTF-8, maximum 1 MiB per line (`asyncio.StreamReader(limit=…)`).
  It is simple in both Python and Rust (`tokio_util::codec::LinesCodec`) and easy to debug with `socat`.
- **Streaming.** A streaming request, e.g. `ask`, gets `stream.event` notifications
  `{"jsonrpc":"2.0","method":"stream.event","params":{"id":<request id>,"seq":n,"event":{…}}}` and then the normal response
  carrying the final result. This follows LSP's progress model.
- **Cancellation.** The client sends the notification `rpc.cancel {"id": …}`. The engine stops at the next checkpoint (between
  retrieval stages, between generated tokens, between ingest files) and answers the request with error `CANCELLED`.
- **Server-pushed events.** `events.subscribe {"topics": [...]}` is a long-lived streaming request. Topics:
  `vault.state`, `consent.requested`, `index.progress`, `jobs`, `unlock.requested`.
- **Errors** use JSON-RPC error objects with stable string codes in `data.code`: `VAULT_LOCKED`, `NOT_INITIALIZED`,
  `AUTH_REQUIRED`, `FORBIDDEN`, `CONSENT_PENDING`, `CONSENT_DENIED`, `RATE_LIMITED`, `QUOTA_EXCEEDED`, `NOT_FOUND`, `CANCELLED`,
  `BAD_REQUEST`, `INTERNAL`.

**Versioning.** `hello {"protocol":"<app>-ipc","versions":[1],"client":{"kind":"ui|cli|mcp-shim","name","version"}}`
returns `{"version":1,"engine":"x.y.z","capabilities":[…],"vault_state":…}`.

- Additive changes (new methods, new optional fields, new event types) do not bump the version. Clients ignore unknown fields
  and events.
- A breaking change bumps the major version. The engine serves N and N-1 for at least one release.
- The UI and engine ship together, so skew mainly affects the CLI and the MCP shim. The shim runs from inside the app bundle
  (§7.3), which keeps skew rare.

### 3.4 API surface (v1)

Parameters and results are abbreviated. Every method except `hello`, `auth*` and `vault.status` requires
authentication. `owner` is implied unless marked `agent`.

| Method | Params | Result / stream events |
|---|---|---|
| `hello` | `versions, client` | `version, engine, capabilities, vault_state` |
| `auth` | `token` | `role` |
| `auth.passphrase` / `auth.recovery` | `secret` | `role: owner` |
| `vault.status` (any, incl. unauthenticated) | none | `state: uninitialized/locked/unlocked`, `vault_id`, `unlock_methods`, `idle_lock_s` |
| `vault.create` | `passphrase, keystore: bool` | `vault_id, recovery_key` (shown once), `kdf` |
| `vault.unlock` | `method: passphrase/keystore/recovery, secret?` | `state` |
| `vault.lock` | none | `state` |
| `vault.change_passphrase` | `old, new` | ok (rewraps; no data re-encryption) |
| `vault.keystore.enable` / `.disable` | none | ok |
| `vault.recovery.regenerate` | `passphrase` | `recovery_key` |
| `vault.rotate_data_key` | `passphrase` | job id (background `PRAGMA rekey` plus blob re-encryption) |
| `collections.list/create/update/delete` | `name, sensitivity: normal/sensitive/private` | collection objects; delete = crypto-erase of every document |
| `docs.list` | `collection?, cursor, limit` | titles, types, dates, status |
| `docs.get` | `id` | metadata, pages, extraction status |
| `docs.read_original` (stream) | `id, range?` | `chunk` events with base64 bytes, for the UI viewer; never written to disk |
| `docs.delete` | `id` | ok (crypto-erase, §4.5) |
| `ingest.add` (stream) | `paths[], collection` | job id; `progress{file, stage, n, total}` |
| `ingest.cancel` / `ingest.jobs` | `job?` | ok / job list |
| `watch.add/list/remove` | `path, collection` | watch folders |
| `search` | `query, collections?, k, mode: hybrid/keyword/vector` | hits: `{citation, doc, page, snippet, score}` |
| `ask` (stream) | `question, collections?, conversation?` | `stage` → `sources` (citation handles before any token) → `token`… → `verdict` (citation check, abstain/conflict) → final `{answer, citations[], abstained, conflict}` |
| `citation.open` | `handle` | `{doc, page, char_span, bbox, excerpt}` |
| `conversations.list/get/delete` | `id?` | encrypted chat history |
| `agent.ask` (agent) | `question, collections?` | as `ask`, after policy and consent (§6); streamed only as the final result |
| `agent.search` (agent) | `query, collections?, k≤20` | titles, snippets (redaction hook), handles |
| `agent.open_citation` (agent) | `handle` | redacted excerpt ≤ 500 chars; always needs consent |
| `agent.list_collections` (agent) | none | only collections the client holds a grant for |
| `agent.status` (agent) | none | `{state, app_version}`; no counts or names while locked |
| `consent.pending` / `consent.decide` | `request_id, decision, scope?` | pending requests / ok |
| `grants.list` / `grants.revoke` | `client?, id?` | grants |
| `audit.query` / `audit.export` / `audit.verify` | `since, client, method, limit` / `format` / none | events, file bytes, chain status |
| `settings.get` / `settings.set` / `settings.set_runtime` | keys | values; runtime = power/sleep hints from the shell |
| `events.subscribe` (stream) | `topics` | events |
| `engine.shutdown` | none | ok, then the connection closes |

---

## 4. Data root and storage

### 4.1 Platform directories

The engine resolves directories with `platformdirs` (`appauthor=False`, `roaming=False`):

| | macOS | Windows | Linux |
|---|---|---|---|
| Data root | `~/Library/Application Support/<App>` | `%LOCALAPPDATA%\<App>` (not roaming `%APPDATA%`: a multi-GB database must not ride roaming-profile sync) | `$XDG_DATA_HOME/<app>` (`~/.local/share/<app>`) |
| Runtime dir (socket, token) | see §3.1 | named pipe; token under `%LOCALAPPDATA%\<App>\run` with a user-only ACL | `$XDG_RUNTIME_DIR/<app>` |
| Logs | `~/Library/Logs/<App>` | `%LOCALAPPDATA%\<App>\Logs` | `$XDG_STATE_HOME/<app>/log` |

`<APP>_DATA_DIR` overrides the data root for tests and portable installs. Today's `~/.vault` and `~/.enclave` are
legacy and read only by the importer (§9).

### 4.2 Layout

```
<data_root>/                         0700
  engine.lock                        single-instance lock (empty)
  vaults/
    <vault_id>/                      0700, one per vault (v1 ships one)
      vault.json                     key header: plaintext by necessity, holds no content (§5.2)
      vault.db, vault.db-wal, -shm   SQLCipher 4 database, raw 256-bit DEK
      blobs/<2 hex>/<blob_id>        original files, per-file-key AEAD (§4.4)
      blobs/.tmp/                    in-flight writes (same filesystem, for atomic rename)
  models/                            downloaded model weights (public data, not secret)
```

Today's per-profile indexes become **collections** inside one vault. One vault per user keeps "one data root, one
key, one index" ([ROADMAP.md](../launch-plan/ROADMAP.md) Phase 1). The `vaults/<id>` level exists so
household vaults (Phase 5) do not need another layout change.

### 4.3 The database: one SQLCipher file per vault

The binding is `sqlcipher3` (pinned; SQLCipher 4.12 community, SQLite 3.51, static OpenSSL, wheels for every target).
`sqlite-vec` is loaded per connection. The spike showed FTS5 and vec0 working together in one encrypted connection, and
`apsw-sqlite3mc` reading and writing the same file format as a fallback ([spike](../../spikes/sqlcipher-vec/README.md) §1–2).

Connection setup, in this order:

```text
PRAGMA key = "x'<64 hex>'";          -- raw DEK; SQLCipher's PBKDF2 is skipped
SELECT count(*) FROM sqlite_schema;  -- fail fast on a wrong key
PRAGMA journal_mode = WAL;
PRAGMA secure_delete = ON;           -- default on keyed DBs, set explicitly anyway
PRAGMA foreign_keys = ON;
PRAGMA cipher_log_level = NONE;      -- SQLCipher logs to stderr by default
enable_load_extension(True); sqlite_vec.load(con); enable_load_extension(False)
PRAGMA cache_size = -<KiB>;          -- vector reader: sized to the vec0 table (below)
```

Schema v1 (abridged; migrations are numbered SQL files applied at unlock, and `VACUUM INTO` snapshots the database first):

```sql
meta(key PRIMARY KEY, value)            -- schema_version, vault_id, embedder id + dim, pipeline_version
collections(id, uuid, name, sensitivity CHECK IN ('normal','sensitive','private'), settings_json, created_at)
documents(id, uuid, collection_id, title, source_path, mime, size_bytes, content_mac BLOB,
          blob_id, file_key BLOB, page_count, status, pipeline_version, created_at, updated_at)
pages(doc_id, page_no, width, height, text_source CHECK IN ('text','ocr','vlm'), PRIMARY KEY(doc_id, page_no))
chunks(id, doc_id, ord, page_start, page_end, header, text, char_start, char_end)
chunks_fts  = fts5(header, text, content='chunks', content_rowid='id',
                   tokenize='unicode61 remove_diacritics 2')          + secure-delete = 1
chunks_vec  = vec0(embedding float[<dim>])                            -- rowid = chunks.id
anchors(id, chunk_id, doc_id, page_no, kind, char_start, char_end, bbox_json)   -- citation targets
entities(id, doc_id, type, value_json, anchor_id, valid_from, valid_to, superseded_by, confirmed_at)
conversations(id, title, created_at) ; messages(id, conversation_id, role, content, citations_json, created_at)
citation_handles(handle PRIMARY KEY, client_key, anchor_id, created_at, expires_at)
clients(client_key PRIMARY KEY, claimed_name, install_id, kind, first_seen, last_seen)
grants(id, client_key, collection_id, tools, expires_at, daily_quota, hourly_rate, verbatim_cap, created_via, created_at, revoked_at)
consent_requests(id, client_key, method, args_json, collections_json, status, created_at, decided_at, decision, grant_id)
audit_events(seq PRIMARY KEY, ts, actor, client_key, method, collections_json, decision, grant_id,
             request_json, result_json, prev_mac BLOB, mac BLOB)
jobs(id, kind, doc_id, stage, status, attempts, error, updated_at) ; watch_folders(id, path, collection_id, last_scan_at)
settings(key PRIMARY KEY, value_json) ; migration_items(…)                          -- §9
```

**Settings the spike forced:**

- **FTS5 `secure-delete` is mandatory.** Without it, a deleted document's tokens stay in the FTS5 index even after
  `VACUUM` (spike §4). With it, and with `secure_delete = ON`, the row text, tokens and vector bytes are all gone from
  the decrypted pages after delete. sqlite-vec zeroes deleted vectors on its own.
- **Page cache sized to the vector table.** With SQLCipher's default 2 MB cache, each KNN query re-decrypts the vector
  pages: 100k × 384 float32 took 523 ms instead of 40 ms. The vector reader connection gets `cache_size` ≈ 1.2 × the
  vec0 table, capped at 25% of RAM, and is warmed in the background at unlock (the first query costs 0.57 s at 100k × 384).
  Page caches are per connection, so only the vector reader gets the large cache.
- **Embedding width.** At most 512 dimensions via Matryoshka truncation of Qwen3-Embedding
  ([ROADMAP.md](../launch-plan/ROADMAP.md) layer table), float32 up to about 100k chunks. Beyond that, a bit-vector
  prefilter with float rescore. Measured on the x86 box: 100k × 384 float32 took 40 ms with the PyPI wheel and 25 ms
  with an AVX build. The roadmap's "5–15 ms per 100k" does not hold on that hardware; Apple Silicon (NEON build) is
  unmeasured.
- A changed embedder or dimension means a new `chunks_vec_<model>` table, filled in the background and swapped in, with
  `meta` recording which table is live.

**Temporary data.** `TEMP_STORE=2` is compiled in, so SQLite temp tables and sorts stay in memory. Parsers get
in-memory streams; Docling accepts `DocumentStream`. When a library insists on a filesystem path, the file is created
inside `<vault_id>/blobs/.tmp` with `0600` and unlinked right after open where the OS allows it. Each such case is listed
in the threat model as a known gap.

### 4.4 Original files: per-file AEAD blobs outside the database

**Decision.** Originals are stored as encrypted blob files, each with its own random 256-bit key. That key lives in
`documents.file_key` inside the SQLCipher database.

| | Blobs inside SQLCipher | **Per-file blobs (chosen)** |
|---|---|---|
| Size of `vault.db` | Grows with every scan (tens of GB for a large household) | Index and metadata only (tens to hundreds of MB) |
| `PRAGMA rekey`, `VACUUM`, backup, migration | Proportional to all originals (rekey 570 ms per 64 MiB in the spike) | Proportional to the index |
| Crypto-erase of one document | Relies on `secure_delete` plus free-page reuse | Delete the key row (overwritten by `secure_delete`) and unlink the blob. Ciphertext left on SSD is useless without the key |
| Atomicity | One transaction | Two-phase write (below). Orphans are garbage-collected |
| Leakage | None beyond total size | Count, sizes rounded up to 64 KiB, mtimes. Blob names are random |
| Future sync (Phase 5) | Must sync the whole DB | Blobs sync individually; indexes are rebuilt per device, as [mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §7 recommends |

**Format** `<app>-blob/1`:

- A header of magic `AVB1`, version, 16-byte `blob_id` and segment size (64 KiB).
- Then segments of AES-256-GCM ciphertext plus tag. The nonce is an 88-bit segment counter plus a 1-bit "final segment" flag
  (the STREAM construction). The header is authenticated as associated data (AAD) in every segment.
- Keys are single-use per file version, so nonce reuse is impossible. Truncation, reordering and swapping segments
  between blobs are all detected.
- The final segment is padded to the segment size.
- AES-GCM uses the `cryptography` package, which is already a dependency and hardware-accelerated on both targets.

**Write path.** Encrypt into `blobs/.tmp/<id>`, `fsync`, `rename` into place, then insert the row in a DB transaction. At
unlock, the engine deletes `.tmp` leftovers and blobs no row references. A row whose blob is missing is marked `damaged`
and shown in the UI.

### 4.5 Content hashes and deletion

- `content_mac = HMAC-SHA256(K_hash, file bytes)`, where `K_hash = HKDF-SHA256(DEK, info="<app>/content-mac/1")`. It is used for
  dedupe and change detection. Equal files are recognisable only to someone holding the key; today's unsalted SHA-256
  (`training/rag_index.py:548`) allows "is file X in this vault?" confirmation attacks.
- **Document delete, in one transaction:**
  1. Delete the `chunks`; the FTS5 external-content delete runs through triggers with `secure-delete`.
  2. Delete the `chunks_vec`, `anchors`, `entities` and `citation_handles` rows, then the `documents` row. That removes
     `file_key`, which `secure_delete` overwrites.
  3. Commit, then `PRAGMA wal_checkpoint(TRUNCATE)`, so that old page images do not linger in the WAL.
  4. Unlink the blob.
- **Vault delete.** Remove `vault.json` and the keystore item. That is the crypto-erase: the database and blobs are then
  unreadable, and they are unlinked too.
- **What we will not claim.** SSD wear-levelling and APFS/Time Machine snapshots may keep *encrypted* old pages or blobs.
  They are unreadable without the DEK or the per-file key. "Secure overwrite" of plaintext files is unreliable on
  flash, so the design keeps plaintext off disk in the first place ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §6).

### 4.6 Plaintext that remains on disk (documented metadata)

| File | Content | Why |
|---|---|---|
| `vault.json` | Format version, vault id, KDF algorithm and parameters with salt, wrapped keys, keystore item reference, creation time | Needed before the key exists |
| Blob files | Size (64 KiB granularity), count, timestamps | Filesystem metadata |
| `engine.lock`, `engine.token`, socket | Empty / random token / socket | Process coordination; the token is rotated per start |
| Logs | Event names, timings, error classes, ids | Must never contain titles, paths, queries, answers or document text (enforced by a log filter and a test) |
| `models/` | Public model weights | Not user data |
| MCP client configs | Shim path, `<APP>_CLIENT_ID` | Written into third-party config files |

### 4.7 Backups

- **Explicit export.** `vault.export_backup(path)` writes `VACUUM INTO` of `vault.db` (the spike confirmed the copy stays
  encrypted with the same key), plus copies of the blobs and `vault.json`. It is restorable with the same passphrase or
  recovery kit. `sqlcipher_export` into a database with a new key is available for "backup with a different passphrase"
  (the spike confirmed FTS5 and vec0 tables are copied and queryable).
- **OS backup tools** (Time Machine, File History) copy only ciphertext. The engine checkpoints the WAL on lock and when idle,
  so the main file is usually self-consistent. If a restored copy is inconsistent, the fallback is the last explicit export.
  The UI says this plainly.

---

## 5. Key hierarchy

### 5.1 Keys

```
                      ┌─ KEK_pass     = Argon2id(passphrase, salt, m, t, p)   ─┐
DEK (32 random bytes) ├─ KEK_keystore = 32 random bytes held by the OS keystore ├─ each wraps the DEK (AES-256-GCM)
                      ├─ KEK_recovery = HKDF-SHA256(recovery secret, salt)     ─┤   in its own slot in vault.json
                      └─ KEK_prf      = HKDF(passkey PRF output) (later)       ─┘
DEK ─► SQLCipher raw key
    ─► HKDF-SHA256(DEK, "<app>/content-mac/1")  = K_hash   (content MACs)
    ─► HKDF-SHA256(DEK, "<app>/audit-chain/1")  = K_audit  (audit hash chain)
per-file keys (random, 32 bytes) stored in documents.file_key (inside the encrypted DB)
```

- **DEK.** `secrets.token_bytes(32)`, generated once per vault. It changes only on `vault.rotate_data_key`.
- **Passphrase KEK.** Argon2id (RFC 9106, v1.3) via `argon2-cffi`, with a 16-byte random salt and a 32-byte output. The
  passphrase is NFKC-normalised UTF-8. Minimum length 10; the UI shows a zxcvbn-style strength meter and blocks only the
  weakest passphrases.
- **Calibration, run once at vault creation and on passphrase change,** targets 0.5–1.0 s:
  1. p = min(4, logical CPUs); start at m = 256 MiB, t = 2.
  2. Grow memory first: 256 → 512 → 1024 MiB, capped at 1 GiB with ≥ 16 GB RAM, 512 MiB with ≥ 8 GB, else 256 MiB.
  3. Then grow t.
  4. Floor: RFC 9106's second recommended option, m = 64 MiB, t = 3.

  Measured on the 4-vCPU spike box: m = 1 GiB, t = 2, p = 4 → 0.82 s. At p = 1 the same memory would take about 2.6 s.
  The grid varied up to 2× under background load, which is why parameters are stored, never re-measured at unlock
  ([spike](../../spikes/sqlcipher-vec/README.md) §7). OWASP's 19 MiB/t=2 floor costs 28 ms here and is far too cheap for
  an offline-attackable header ([ROADMAP.md](../launch-plan/ROADMAP.md) "A user secret…"). The parameters must also work on
  the weakest device that will ever open the vault; revisit when sync arrives.
- **Wrapping.** AES-256-GCM with a random 96-bit nonce. The AAD is the canonical JSON of
  `{format, vault_id, slot_type, slot_id, kdf params}`, so an attacker who can edit `vault.json` cannot downgrade
  parameters or move a slot between vaults without the unwrap failing.

### 5.2 `vault.json`

```json
{
  "format": "<app>-vault/1",
  "vault_id": "3b0d…",
  "created_at": "2026-10-…",
  "db": {"cipher": "sqlcipher4", "key": "raw256"},
  "blobs": {"cipher": "aes256gcm-stream/1", "segment": 65536},
  "slots": [
    {"id": "p1", "type": "passphrase",
     "kdf": {"alg": "argon2id", "v": 19, "m_kib": 1048576, "t": 2, "p": 4, "salt": "b64…"},
     "wrap": {"alg": "aes256gcm", "nonce": "b64…", "ct": "b64…"}},
    {"id": "k1", "type": "keystore", "store": "macos-keychain",
     "item": {"service": "<bundle-id>.vault", "account": "3b0d…"}, "wrap": {"…": "…"}},
    {"id": "r1", "type": "recovery", "kdf": {"alg": "hkdf-sha256", "salt": "b64…"}, "wrap": {"…": "…"}}
  ]
}
```

Writes are atomic: temp file, `fsync`, `rename`, `fsync` of the directory. A previous header is never kept, because it
would still accept an old passphrase.

### 5.3 OS keystore (convenience unlock)

| OS | Store | Item | Notes |
|---|---|---|---|
| macOS | Keychain, generic password | service `<bundle-id>.vault`, account `vault_id` | **Phase 1:** via `keyring` (Security.framework). That creates a default login-keychain item whose ACL trusts our signed binary; other apps trigger a keychain prompt. `keyring` cannot set accessibility or access-control flags. **Phase 2:** the Tauri shell creates the item in the data-protection keychain with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` and `SecAccessControl` `.userPresence` (Touch ID or login password), and hands `KEK_keystore` to the engine over the owner connection. The shell holds a KEK briefly, never the DEK |
| Windows | Credential Manager (DPAPI, per user) via `keyring` | target `<app>/vault/<vault_id>` | Windows Hello gating later (`KeyCredentialManager`) |
| Linux | Secret Service (GNOME Keyring/KWallet) via `keyring` | collection default, attributes `{app, vault_id}` | Secret Service has **no per-application ACL**: any process in the session can read the item once the collection is unlocked. The UI labels the option "convenience: apps you run can unlock this vault" |

**Fallback when no keystore is usable.** The spike showed that in a container `keyring` resolves to
`keyring.backends.fail.Keyring` because `DBUS_SESSION_BUS_ADDRESS` is unset, and `set_password` raises `NoKeyringError`.

- The engine treats that, a chainer with no backends and any `keyrings.alt` backend as "no OS keystore". The keystore slot
  is simply not offered.
- Unlock is by passphrase or recovery key only. The engine never falls back to a plaintext or password-file keyring.
- If a keystore item disappears (the user wiped the keychain), unlock via that slot fails with `KEYSTORE_UNAVAILABLE` and
  the UI asks for the passphrase. The slot is removed on the next successful passphrase unlock.

### 5.4 Recovery kit and passkeys

- **Recovery secret.** 160 random bits, shown as 32 Crockford-base32 characters in 8 groups of 4, plus a check group:
  `ABCD-EFGH-…-XY12`. Because the secret is high-entropy, `KEK_recovery = HKDF-SHA256(secret, salt, "<app>/recovery/1")`
  and no Argon2 is needed.
- **Printing.** The UI renders a printable kit (vault id, creation date, the key, instructions), in the 1Password
  Emergency Kit model ([ROADMAP.md](../launch-plan/ROADMAP.md)). It is not saved by default. Setup asks the user to type
  back the last group. Phase 1's CLI prints the key once with the same confirmation.
- `vault.recovery.regenerate` replaces the slot, so the old kit stops working.
- **Passkey PRF (later).** A `passkey-prf` slot stores the credential id and a PRF salt, with `KEK_prf = HKDF(PRF output)`.
  WebAuthn inside a Tauri webview has no usable RP origin, so this needs native `AuthenticationServices` (macOS 15+) or
  Windows Hello. That is an open question (§12), and the slot format already allows it.

### 5.5 Changing and rotating

- **Passphrase change.** Unwrap with the old passphrase, re-derive with a new salt and fresh calibration, rewrap, and
  atomically write `vault.json`. The data is not touched, so it takes about one second.
- **Keystore enable/disable, recovery regenerate.** These add or remove slots only.
- **DEK rotation** is rare, e.g. after a suspected compromise of an unlocked machine.
  1. Background `PRAGMA rekey` (works in WAL mode; 570 ms per 64 MiB in the spike).
  2. Re-encrypt every blob under new per-file keys; the old DEK may have exposed them.
  3. Then rewrap every slot. Progress is resumable through `jobs`.

### 5.6 Memory: what lives where, and when it is dropped

| Secret | Where | Dropped |
|---|---|---|
| Passphrase / recovery secret | IPC message → `bytearray` → KDF | Right after the KDF. The JSON decoding created an immutable `str` copy that Python cannot wipe |
| KEKs | `bytearray` | Right after unwrap/wrap |
| DEK | One `bytearray` in the key-custody object. The hex `PRAGMA key` string is built per connection open and dereferenced | On lock or exit. The `str` copies used for `PRAGMA key` cannot be wiped |
| Per-file keys | `bytearray` for the duration of one blob read/write | After use |
| SQLCipher's internal key and decrypted page cache | C heap | On connection close. `PRAGMA cipher_memory_security = ON` makes SQLCipher wipe and `mlock` its allocations. The spike found the default OFF; turn it on and measure the cost in PR 3 |
| Decrypted data in flight (chunks, answers, LLM KV cache) | Python objects, model runtime | On lock: close connections, cancel jobs, reset the generation state (the LLM KV cache holds document text), drop caches, `gc.collect()` |

Python cannot reliably zeroise `bytes`/`str` ([pyca/cryptography limitations](https://cryptography.io/en/latest/limitations/),
cited in [ROADMAP.md](../launch-plan/ROADMAP.md)). The threat model says so; the README must not claim "key zeroing".

**Hardening at engine start:**

- `RLIMIT_CORE = 0`, so no core dumps.
- On Linux, `prctl(PR_SET_DUMPABLE, 0)`: same-uid, non-root processes cannot `ptrace` or read `/proc/<pid>/mem`.
- On macOS, the hardened runtime without `get-task-allow` blocks debugger attach.
- Swap and hibernation files can hold pages. FileVault, BitLocker or LUKS is the mitigation, and the threat model recommends it.

**Lock triggers.**

- **Idle timeout.** Default 15 minutes without *owner* activity. Agent calls do not reset the timer, or a polling agent
  would keep the vault open forever.
- **System events.** System sleep and screen lock, which the Tauri shell observes: `NSWorkspace` sleep and
  `com.apple.screenIsLocked` on macOS, `WTS_SESSION_LOCK`/`PBT_APMSUSPEND` on Windows, logind `PrepareForSleep`/ScreenSaver on
  Linux. The shell then sends `vault.lock`.
- **Explicit.** Manual lock, app quit, engine exit.
- **Headless engines** only have the idle timeout.

---

## 6. Consent and policy inside the engine

### 6.1 Model

- **Default deny.** Every `agent.*` call except `agent.status` needs a grant.
- **A grant** is `(client_key, collection or *, tools ⊆ {ask, search, open_citation, list_collections}, expires_at,
  hourly_rate, daily_quota, verbatim_cap)`. There are no "all tools forever" grants. Today's "Always Allow" grants every
  tool with no expiry (`consent.py:478-482`); that is exactly what the ConLeash study found users click just to dismiss
  prompts ([ROADMAP.md](../launch-plan/ROADMAP.md) moment three).

**Collection sensitivity:**

| Sensitivity | Agent access |
|---|---|
| `normal` | Grants of up to 30 days |
| `sensitive` (IDs, medical, suggested at creation) | Grants last at most the current app session. `open_citation` always prompts |
| `private` | Invisible to agents: absent from `list_collections`, never retrieved for `agent.*` |

The secrets store, if kept as a plugin, has no agent methods at all.

### 6.2 Prompts, in the app and never through a shell

1. An `agent.*` call without a covering grant creates a `consent_requests` row. The engine emits `consent.requested`
   with the client's claimed name, the method, the **exact arguments**, the collections involved and what would be returned
   (e.g. "an answer and up to 5 citations").
2. The UI shows an inline card: Allow once · Allow <client> on <collection> for 1 h / 1 day / 30 days · Deny · Always deny
   <client>. `consent.decide` records the decision, creates the grant and resumes the waiting call.
3. The call waits up to 55 s. It then returns `CONSENT_PENDING` with "The user has been asked in <App>; retry after they
   respond." The text neither invites spamming nor tells the agent to ask the user to approve blindly.
4. If no owner connection is listening (no UI), the call returns `CONSENT_DENIED`: "Open <App> to approve access".
5. On spec 2026-07-28, the shim may also send an MRTR `input_required` ("Approve in <App>, then continue"). That is a
   courtesy only. The decision comes solely from the vault UI, because the caller's UI may auto-approve or be compromised
   ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §1).

### 6.3 Client identity: weak by nature, designed around

A stdio MCP server cannot authenticate its client. It sees a self-asserted `clientInfo` (in `initialize` on 2025-11-25,
or in per-request `_meta` on 2026-07-28), its parent process (spoofable), and whatever its launch config contains. Today's
heuristics (`consent.py:309-358`) collapse to `"unknown"`.

The design:

- `client_key = hash(claimed name, install_id)`. The installer ("Connect to Claude", `.mcpb`, `<app> mcp install`)
  writes a random `install_id` into the client's MCP config as `<APP>_CLIENT_ID`. That lets the user revoke one
  install and tells two configured clients apart. **It does not stop another local process from reading that config
  and reusing it.**
- The UI and audit log always show the identity as *claimed* ("says it is Claude Desktop").
- Mitigation comes from narrow scopes, short expiries, quotas, `sensitive` collections that always prompt, and the audit log,
  not from identity.

### 6.4 Extraction resistance: hooks now, detectors later

The answer pipeline exposes four hook points. Phase 1 ships the ones marked **now**.

| Hook | Phase 1 | Later |
|---|---|---|
| `pre_retrieval(query, client)` | **now:** token-bucket rate limit per client (default 30/min, 500/day) and per-grant quotas | RAG-CT-style single-record query detection ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §5) |
| `post_retrieval(hits, client)` | **now:** drop hits from collections outside the grant or `private`; cap agent context at 10 chunks | Retrieval-distribution anomaly scoring |
| `post_generation(answer, hits, client)` | **now:** verbatim cap: if more than 40% of the answer's 8-grams appear in the retrieved chunks, truncate and flag. Strip Markdown links and images | Presidio + GLiNER PII redaction ([ROADMAP.md](../launch-plan/ROADMAP.md) "A user secret…") |
| `open_citation(handle, client)` | **now:** handles are random, bound to `client_key`, expire after 24 h. Excerpt ≤ 500 chars. Always prompts for `sensitive`. Daily quota of 20 | Redaction |

### 6.5 Audit log

`audit_events` lives in the encrypted database, so it is not a plaintext JSONL as today (`activity_logger.py:152,196`).

- **Contents.** Every agent call, consent decision, grant change, unlock/lock, export and settings change: actor, claimed
  client, method, collections, decision, grant, request (the agent's question verbatim, which "What the AI saw" needs),
  result summary (answer length, citation handles and documents), and timing.
- **Arguments are kept in full**, inside the encrypted database, because the owner needs to see exactly what was asked. No agent method accepts secrets, so none can reach the log.
- **Retention.** 180 days by default. An "export activity log" JSON follows Apple's Intelligence Report model.
- **Tamper evidence.** `mac = HMAC-SHA256(K_audit, prev_mac ‖ canonical(row))`, and `audit.verify` walks the chain. That
  makes the log tamper-evident against anyone without the DEK. It is not tamper-proof against someone who holds it.
- **Kill switch.** Today's kill switch (`enclave_control`) becomes the setting `agents.enabled`. When false, every agent
  call returns `FORBIDDEN` and is audited.

---

## 7. The MCP shim

### 7.1 Shape

`<app>-mcp` is a stdio MCP server with **no crypto, no storage and no model**. It translates MCP tool calls to `agent.*`
IPC calls. It uses Python MCP SDK 2.x (`MCPServer`, the renamed FastMCP API; [codebase_audit_core.md](../launch-plan/research/codebase_audit_core.md) Q6),
pinned `>=2.2,<3`, and targets spec **2026-07-28**. It keeps **2025-11-25** compatible because clients lag
([ROADMAP.md](../launch-plan/ROADMAP.md) "A user secret, five MCP tools…").

Whether one SDK 2.x server can serve 2025-11-25 clients (the `initialize` handshake) is a PR 9 acceptance test against
both an SDK 1.x client and a 2026-07-28 client. If it cannot, the shim negotiates on the protocol version it receives and
keeps a thin legacy path.

### 7.2 Tools (static, read-only)

| Tool | Input | Structured output |
|---|---|---|
| `<app>_ask` | `question`, `collections?`, `response_format: concise/detailed` | `{answer, citations: [{handle, document, page}], abstained, conflict, generated_by: "local model"}` |
| `<app>_search` | `query`, `collections?`, `limit ≤ 20` | `{results: [{handle, document, page, snippet}]}` |
| `<app>_open_citation` | `handle` | `{document, page, excerpt}` (redacted, ≤ 500 chars) |
| `<app>_list_collections` | none | `{collections: [{name, document_count}]}` (granted only) |
| `<app>_status` | none | `{state, app_version, setup_hint?}` |

- **Annotations.** All tools carry `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`,
  `openWorldHint: false`, and return an `outputSchema` plus a text rendering.
- **Static descriptions.** Descriptions and server `instructions` are fixed at build time, and a test asserts they are
  byte-identical to the checked-in manifest. Document-derived text never reaches them, which blocks the tool-poisoning
  vector ([ROADMAP.md](../launch-plan/ROADMAP.md)).
- **Tool-manifest hashes** are published with releases (Phase 3).

### 7.3 Packaging and discovery

- **One binary.** The shim is the engine's PyInstaller build started in shim mode (`<app>-engine mcp`). It ships inside the app
  bundle as `Contents/MacOS/<app>-mcp`, a thin launcher, so it is signed with the app and updated with it.
- **Registration with clients:**
  - **Claude Desktop:** a signed `.mcpb` whose manifest runs the installed shim. Whether the manifest's `server` can reference a
    binary outside the bundle, or must embed a launcher, is verified in PR 9. The `.mcpb` path is preferred because
    "Connect to Claude" should be one click ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §1, §4).
  - **Cursor, LM Studio and others:** `<app> mcp install --target …` merges an entry `{command: <path to shim>, env:
    {<APP>_CLIENT_ID}}`, keeping today's backup-and-refuse-on-parse-error behaviour (#17).
- **Engine discovery.** The shim finds the engine through the same `platformdirs` resolution as §3.1, then reads
  `engine.token`. `<APP>_RUNTIME_DIR` overrides it for tests.

### 7.4 Error semantics

The shim never returns document data from anywhere but the engine, and never caches any.

| Situation | Tool result |
|---|---|
| No socket or connection refused (app not running) | `isError: true`, "<App> isn't running. Ask the user to open <App> to use their documents." |
| `VAULT_LOCKED` | `isError: true`, "The <App> vault is locked. Ask the user to unlock it in <App>." The engine also emits `unlock.requested`, so the UI can show a notification |
| `CONSENT_PENDING` / `CONSENT_DENIED` | "Waiting for the user to approve this in <App>" / "The user has not allowed this" |
| `RATE_LIMITED` / `QUOTA_EXCEEDED` | Error with the retry-after time |
| Engine protocol version unsupported | "Update <App>" |
| `<app>_status` | Always succeeds: `{state: "not_running" / "locked" / "unlocked"}` |

Launching the app from the shim, e.g. `open -g -b <bundle-id>`, is off by default (§12).

---

## 8. Packaging with Tauri

### 8.1 Engine build

- **PyInstaller `--onedir`**, never `--onefile`. A onefile build unpacks an ad-hoc-signed Python framework at run time,
  and the hardened runtime refuses it after re-signing ([consumer_ux_patterns.md](../launch-plan/research/consumer_ux_patterns.md) Q9/Q10,
  [ROADMAP.md](../launch-plan/ROADMAP.md) Tauri costs).
- **Nuitka standalone** is the alternative evaluated in PR 13, as in the tauri-python-sidecar reference repo.
- **Placement.** The onedir tree goes under `Contents/Frameworks/<app>-engine/`, because code must not live in `Resources`.
  The Tauri `externalBin` entry is a small launcher in `Contents/MacOS/`. Exact placement is verified by the CI job in PR 13.
- **Signing.** Sign inside-out: every Mach-O (the Python dylib, every `.so`, `sqlcipher3/_sqlite3*.so`, `sqlite_vec/vec0.dylib`,
  the MLX and llama.cpp libraries) with the **same Developer ID Team ID**, `--options runtime` and `--timestamp`; then the
  launchers; then the app. The spike found every macOS wheel binary linker-signed ad hoc with **no Team ID**, so
  re-signing is mandatory. That includes `vec0.dylib`, which is loaded through `load_extension` and falls under library
  validation. All of them link only `libSystem`, with OpenSSL static ([spike](../../spikes/sqlcipher-vec/README.md) §1).
- **Entitlements.** Start with none. Add `com.apple.security.cs.allow-unsigned-executable-memory` only if the PR 13 CI run
  proves cffi/ctypes closures need it. Never add `disable-library-validation` or `allow-dyld-environment-variables`.
- **Size budget.** The core install must stay under about 200 MB without models (Phase 1 exit). The `sqlcipher3` macOS wheel is
  6.6 MB and `vec0` 0.16 MB. Torch leaves the core by the ONNX-embeddings PR.

### 8.2 Supervision from Tauri

The shell uses `tauri-plugin-shell`'s sidecar API.

1. **Spawn.** `<app>-engine serve --owner-token-stdin --parent-pid <pid>`, then write the owner token and a newline to
   stdin, keeping stdin open.
2. **Ready handshake.** The engine answers with one JSON line on stdout: `{"ready":true,"socket":…,"protocol":1,"pid":…}`.
   Stdout carries nothing else; logs go to the log file. If no ready line arrives within 20 s, the shell kills the engine
   and restarts it.
3. **Restart policy.** Backoff 1–30 s, give up after 5 crashes in 2 minutes (§2).
4. **Shutdown.** On quit: `engine.shutdown` over IPC, wait 5 s, then SIGTERM / `TerminateProcess`. Closing stdin also
   makes the engine exit.
5. **System events.** The shell forwards sleep, screen-lock and power events (§5.6).

### 8.3 Updates

The engine is inside the signed app bundle, so it updates atomically with the app through the Tauri updater (signed
artifacts plus `latest.json`) or Sparkle 2 ([consumer_ux_patterns.md](../launch-plan/research/consumer_ux_patterns.md) Q10).
Schema migrations run at the first unlock after an update, after a `VACUUM INTO` snapshot, and are forward-only. The
snapshot is deleted after the next successful unlock. IPC versioning (§3.3) covers a shim or CLI running outside the bundle.

---

## 9. Migration from today's layout

### 9.1 What exists today (at `2ec68a7`)

The vault root is `~/.vault`. The CLI accepts `--vault-path` and MCP reads `$VAULT_PATH`, but the GUI hard-codes `~/.vault`
(`gui/vault_app.py:234`).

| Path | Written by | Contents and protection |
|---|---|---|
| `private_models/<profile>/profile.json` | GUI, `model create` | **Plaintext** JSON: name, description, system prompt, keywords, model name, adapter paths and adapter *key paths* |
| `private_models/<profile>/vault/master.key` | `manager.py:402-412` | **Plaintext** 32 random bytes, `chmod 0600` *after* write |
| `private_models/<profile>/vault/rag.db` | `RAGIndex` (`training/rag_index.py:327-366`) | SQLite. `documents`: `name`, absolute `source_path`, unsalted SHA-256 `content_hash`, `metadata {"folder": abs path}` and timestamps in **plaintext**; `content` = ChaCha20-Poly1305(full extracted text, AAD = doc id, random 96-bit nonce). `chunks`: `content` = ChaCha20-Poly1305(chunk text, AAD = chunk id); **plaintext** float32 `embedding` (e5-small, 384-d, `rag_index.py:627`); offsets; `metadata '{}'`. **Original file bytes are not stored** |
| `private_models/<profile>/vault/rag.hnsw` + `rag.meta.json`, or `rag.brute.json` | `vector_index.py:234-262, 362-376` | **Plaintext** vectors and chunk-id maps |
| `private_models/<profile>/{models,trained_adapters,wdva_packages,keys}/` | GUI / `model train-adapter` | Model cache; adapters; adapter key files (**plaintext**) |
| `.active_private_profile` | GUI | Plaintext profile name |
| `master.key` (vault root) | CLI `VaultCLI` (`cli/main.py:26-56`), MCP `_get_vault` (`server.py:96-125`), GUI (`vault_app.py:6898-6908`) | **Plaintext** 32 bytes; key for `vault.db`, and for older builds' root `rag.db` |
| `vault.db` | `EncryptedKVStore` (`encrypted_kv/storage.py:72-120`) | `encrypted_entries`: `service`, `tags`, `description`, `folder`, timestamps in **plaintext**; `encrypted_data` = ChaCha20-Poly1305(value, AAD = service) |
| `rag.db` (+ `.hnsw`/`.meta.json`/`.brute.json`) at the root | Builds before #23 (`LocalAgent`) | Same format as the profile index, keyed by the root `master.key`. Now only counted (`mcp_server/agent.py:288-306`) |
| `chat_history_<profile>.json`, `question_history.json` | GUI (`vault_app.py:244, 426-433`) | **Plaintext** chat history and questions |
| `activity.jsonl` | `ActivityLogger` (`mcp_server/activity_logger.py:152, 196`) | **Plaintext** agent query previews, app ids, redacted argument metadata |
| `control_plane/events.db` | `enclave_control/audit_store.py` via `runtime.py:29` | **Plaintext** SQLite audit events and module status |
| `permissions.json` | `ConsentManager` (`consent.py:279`) | **Plaintext** per-app `auto_approve` / `deny_always`, `0600` |
| `.onboarding_v1_complete`, `.language_pref`, `session.json`, `activity_export.*` | GUI | UI state; legacy Supabase session; user exports |
| `sheriff/`, `wallet/`, `local_adapters/`, `adapters/`, `local_datasets/`, `training_queue/`, `datasets/` | Sheriff, wallet, training | Out of scope. They are removed or quarantined by the Phase 1 cut PRs |
| `~/.enclave/policies.toml` | `enclave_control/config.py` | **Plaintext** policy: kill switch and per-agent allow-lists |
| `~/.enclave/embedding_cache.db` | `training/embeddings.py:72` | **Plaintext** embeddings keyed by a 16-hex SHA-256 prefix of chunk text (`:348`). It survives document deletion |
| `~/.enclave/config.env` | GUI config loader | Optional env overrides |
| Model caches | HF cache (`$HF_HOME`), `~/Library/Application Support/Enclave/models` or `~/.cache/enclave/models` (`gui/local_inference.py:51-58`) | Public weights. Not migrated, because the model set changes; the import report lists their size so the user can delete them |
| Claude Desktop / Cursor config | `gui/mcp_setup.py:184-192` | `{command: <python>, args: [-m, advanced_vault.mcp_server], env: {VAULT_PATH, PYTHONPATH}}` |

### 9.2 The importer

`<app> migrate [--dry-run] [--resume] [--verify] [--remove-legacy]`, also driven from the UI's first-run screen when
`~/.vault` exists. It is **read-only on legacy data** until the final, separately confirmed removal step.

1. **Inventory (dry run).** Enumerate profiles, legacy root index, KV entries, chat files, logs and policy, with counts and
   sizes. Check that the source files still exist and that free disk space is at least 1.5 × (originals + legacy databases). The
   report tells the user what will be imported, what will be dropped and why.
2. **Create the new vault first.** Passphrase, recovery kit, optional keystore. Nothing is imported into an unprotected store.
3. **Documents.** Each profile becomes a collection: name, description, and keywords as tags. The active profile becomes the
   default collection. For each legacy document, open `rag.db` read-only with its sibling `master.key`, decrypt
   `documents.content`, and:
   - **Re-ingest from source.** If `source_path` exists and is a supported file, run the normal pipeline. That brings the
     original blob, pages, FTS5, new embeddings and citation anchors. Status `imported_from_source`.
   - **Text only.** Otherwise store the decrypted text as a text-only document titled with the legacy name, with no pages and
     no original. Status `imported_text_only`, and the UI marks it "original file not found".
   - Legacy embeddings, the HNSW/brute index files and `embedding_cache.db` are never read. The embedder changes, and those
     files are plaintext liabilities.
4. **Chat history** JSON goes into `conversations`/`messages`. `question_history.json` is imported as one conversation, marked legacy.
5. **Secrets KV** (`vault.db` with the root `master.key`). Entries are decrypted and written to a `legacy_secrets` table that
   no agent method can reach. The owner can list and export them to a password manager, via CLI now and a UI page if the owner
   keeps the plugin. See §12.
6. **Consent and policy.**
   - `permissions.json` "always allow" entries are **not** carried over: all tools, no expiry, heuristic identity. The report
     says so and the first agent call prompts afresh. `deny_always` entries become deny rules for that claimed name.
   - From `policies.toml`, only the kill switch carries over, as `agents.enabled`.
7. **Activity.** `activity.jsonl` and `control_plane/events.db` are imported as `audit_events` with `actor = legacy`. The
   hash chain starts with an `import` marker event, so the log says legacy rows were never tamper-evident.
8. **Client configs.** Back up each Claude Desktop/Cursor config and replace the legacy `advanced_vault.mcp_server` entry with
   the shim entry (§7.3).

**Resumable.** Each unit (legacy document, KV entry, chat file, log file) is a row in `migration_items(source_kind,
source_path, source_id, status, new_id, error, attempts)` inside the new, encrypted vault. Each unit is processed in its own
transaction, so `--resume` skips finished rows. A crash leaves at worst one unit to redo.

**Verifiable** (`--verify`, which also runs automatically at the end):

- Every legacy document id maps to exactly one new document with status `imported_from_source`, `imported_text_only` or
  `failed(reason)`. Counts per profile must match.
- For `imported_text_only`, `HMAC(K_hash, stored text) == HMAC(K_hash, decrypted legacy text)`.
- For `imported_from_source`, the new document exists and its FTS5 and vector rows are complete.
- Every KV entry decrypts and round-trips.

The report is shown in the UI and exportable as JSON.

**Removing legacy data** happens only after verification passes *and* the user confirms. The user chooses "Remove now"
or "Keep a copy for 30 days". Keeping renames `~/.vault` to `~/.vault.migrated-<date>`, with a warning that it holds
plaintext; a reminder follows at 30 days. Removal:

- unlinks the plaintext files (`embedding_cache.db`, `activity.jsonl`, chat JSON, `permissions.json`, `events.db`,
  `rag.hnsw`/`.meta.json`/`.brute.json`, `profile.json`, adapter key files);
- unlinks the legacy databases and their `master.key` files;
- removes `~/.enclave`.

It does not claim secure erasure. On APFS, SSDs and Time Machine, old copies may persist, and the UI says so, with a link
on how to delete local snapshots.

**Failure handling:**

- A missing or corrupt `master.key` or `rag.db` marks that profile's items `failed` with the reason and continues.
- Decryption failures (bad tag) are reported per item.
- Running out of disk stops the import cleanly, and it can be resumed.
- If vault creation fails, nothing has been written and legacy data is untouched.
- The legacy Flet GUI must not be used against migrated data. After migration it runs as an engine client only (§11, PR 11).

---

## 10. Threat model summary

| Adversary / situation | Protected? | How / why not |
|---|---|---|
| Offline disk theft, stolen backup, synced copy of the data dir (vault locked or machine off) | **Yes**, subject to passphrase strength | Everything is under SQLCipher or per-file AEAD. Only `vault.json` (KDF parameters, wrapped keys) and blob sizes and timestamps are visible. Guessing costs one Argon2id derive (~1 GiB, ~0.8 s here) per candidate. With FileVault/BitLocker off, a stolen login keychain adds the keystore slot as a target, and it needs the login password |
| Another local, non-admin user | **Yes** | `0700` directories and `0600` files, peer-uid checks on the socket, user-only named-pipe DACL |
| Admin or root on the machine | **No** | Can read engine memory, or install a keylogger |
| Malware as the same user, vault **locked** | **Partly** | Cannot decrypt without the passphrase, but it can keylog the passphrase. On Linux it can read the Secret Service item (no per-app ACL), so the keystore slot there is convenience only (§5.3). On macOS the keychain item's ACL is tied to our signature |
| Malware as the same user, vault **unlocked** | **No** | It can reach the agent role through `engine.token`, where consent still applies and the user must click. On Windows it can read engine memory; `PR_SET_DUMPABLE=0` and the macOS hardened runtime block same-uid debugging but not everything. It can drive the UI through accessibility APIs, which on macOS require a TCC grant. The roadmap asks for this to be stated plainly |
| Malicious or hijacked agent via MCP (prompt-injected Claude, rogue skill) | **Partly** | Five read-only tools, answers rather than files, default deny, scoped and expiring grants, quotas, verbatim cap, `sensitive` collections always prompt, `private` ones are invisible, audit log. **It cannot stop an authorised agent from learning the facts it asks about** ([ROADMAP.md](../launch-plan/ROADMAP.md)) |
| Prompt injection from documents (malicious PDF or email) | **Partly** | The synthesis model has no tools and no network. Document text is delimited as data. Links and images are stripped from answers. Tool descriptions are static. Instruction-like content is flagged at ingest (later). A poisoned document can still produce a misleading answer; citations and the verifier make that visible |
| Other users' processes or a web page reaching the IPC | **Yes** | No TCP listener. The webview has no socket access (§3.1) |
| Supply chain (malicious dependency, runtime fetch) | **Partly** | Pinned lockfile. No runtime `pip`/`npx`. Signed and notarized builds. SBOM and Sigstore in Phase 3 |
| Forensic recovery of deleted documents | **Mostly** | Crypto-erase through per-file keys, FTS5 `secure-delete`, `secure_delete`, WAL checkpoint. Encrypted old pages may survive on SSD and are useless without the DEK |

This table seeds `docs/THREAT_MODEL.md`, which replaces `docs/architecture/CRYPTOGRAPHIC_SPECS.md` (Phase 3 deliverable).

---

## 11. Implementation plan (Phase 1)

New code lives in `advanced_vault/engine/` until the rename, then moves wholesale. It must not import `advanced_vault.gui`.
New dependencies: `sqlcipher3`, `sqlite-vec`, `argon2-cffi`, `keyring`, `platformdirs`, plus `pywin32` in Phase 4. Each is
pinned in the uv lockfile by the PR that first needs it.

| # | PR | Reuses / replaces | Tests (beyond unit) | Exit criteria |
|---|---|---|---|---|
| 1 | **Paths, lock, logging policy**: `engine/paths.py` (platformdirs, runtime-dir checks), single-instance lock, content-free log filter | New | Two-process lock contention; symlinked or foreign-owned runtime dir refused; log filter drops fields named title/path/query/text | `<app> engine paths` prints the resolved dirs; no behaviour change elsewhere |
| 2 | **Key management**: `engine/keys/` (vault.json format, Argon2id slot + calibration, recovery slot, keystore slot via `keyring` + null store, passphrase change) | Replaces the five `master.key` writers (removed in PR 12) | Wrong passphrase; tampered AAD, parameter downgrade and slot swap rejected; calibration with a fake clock; `fail.Keyring` → no keystore slot; recovery unlock; fuzzed header parser | 100% branch coverage of `keys/`; header documented; spike numbers reproduced in CI (Linux + macOS) |
| 3 | **Store v1**: SQLCipher connection factory and pragmas, schema v1 + migration runner, per-file AEAD blob store, crypto-erase delete, content MACs, `cipher_memory_security` measured | Replaces `RAGIndex` storage (`training/rag_index.py:314-366`), `vector_index.py`, the embedding cache | The spike's crypto checks as tests: header, stdlib cannot open, WAL has no markers, residue after delete is clean. Blob tamper, truncation and reorder detected; orphan GC | Create/unlock/lock a vault programmatically; a test scans every file under the data root for marker strings and finds none |
| 4 | **IPC server and client**: asyncio UDS server, NDJSON JSON-RPC, `hello`/`auth`/roles, streaming and cancel, peer creds, token file; `engine/ipc/client.py` for the CLI, shim and Flet | New | Auth failures and throttling; wrong-uid peer (simulated) refused; oversized frame; cancel mid-stream; 20 concurrent clients | `<app> status` talks to a running engine |
| 5 | **Engine lifecycle and vault API**: `serve` (stdin owner token, ready line, parent-death exit), `vault.*` methods, idle lock, `events.subscribe`, graceful shutdown | Replaces `VaultCLI` key handling | Engine killed mid-write reopens cleanly; idle lock not reset by agent calls; lock drops every connection | `<app> engine start / unlock / lock / status` work end to end |
| 6 | **Ingestion service**: staged jobs (text + FTS5, then embeddings), watch folders with reconciliation, progress events, `docs.*`, collections | Reuses `parsing/`, the chunker from `rag_index.py:368-519`, and `EmbeddingEngine` behind an interface (swapped for ONNX by its own PR) | Ingest → search round trip; kill during ingest → resume after unlock; delete → residue scan clean; watcher records nothing while locked | `<app> ingest <paths>` over IPC; searchable after stage A |
| 7 | **Retrieval and `ask()`**: hybrid FTS5 + vec0 RRF (the spike's SQL), streamed `ask` with sources before tokens, citation handles; inference moved out of `gui/` into `engine/llm/` | Replaces `PrivateModelSession.ask` (`manager.py:555-627`) and `LocalAgent.query`; removes the core → gui imports | Same answer object for UI, CLI and agent paths (parity test); cancel during generation | One `ask()`; `grep "advanced_vault.gui" advanced_vault/engine` is empty |
| 8 | **Consent, policy, audit**: grants, `consent_requests` and events, rate limits and quotas, sensitivity levels, extraction hooks, audit chain, kill switch | Replaces `mcp_server/consent.py`, `activity_logger.py` and `enclave_control` for the new path | Default deny; expiry; quota; `sensitive` always prompts; `private` invisible; chain tampering detected; no-UI → denied | Every agent call audited with a verifiable chain |
| 9 | **MCP shim on SDK 2.x**: five tools, annotations and output schemas, error semantics (§7.4), `<app> mcp install`, `.mcpb` manifest (unsigned) | Replaces `mcp_server/server.py` (as trimmed by the Phase 1 cut PRs); the `enclave-mcp` entry point becomes the shim | Contract tests with an in-process engine; clients on 2026-07-28 and 2025-11-25; locked and not-running paths; tool descriptions match the manifest byte for byte | Claude Desktop (manual) gets a cited answer from a document ingested via IPC |
| 10 | **Migration importer** (§9) | Reads legacy formats with the legacy `RAGIndex`/`EncryptedKVStore` code kept read-only in `engine/migrate/legacy/` | Fixture legacy vault generated by today's code (2 profiles, KV entries, chat, logs, missing sources); kill mid-import → `--resume`; verification catches an injected mismatch; removal only after confirmation | `--dry-run`, import, `--verify` and `--remove-legacy` work on the fixture |
| 11 | **Flet GUI as an engine client**: an `EngineClient` adapter exposing the subset of `PrivateModelSession` the GUI calls (`ingest_paths`, `ask`, `list_documents`, `search`, `get_status`), a passphrase unlock dialog, migration prompt; training, adapter, secrets, wallet and Sheriff pages hidden | Keeps the Flet UI usable until Tauri (Phase 2) without porting 31k lines | **Roadmap exit test**: ingest through the GUI's client API → MCP shim query returns a cited answer | The GUI never opens a database or key itself |
| 12 | **Delete the legacy data paths**: the five key writers, `private_models` storage, `RAGIndex` storage, `vector_index.py`, the embedding cache, consent/activity/`enclave_control` runtime | Removal | Grep gates in CI: no `master.key`, no `sqlite3.connect` outside `engine/store` and `engine/migrate/legacy`, no `bash -c` | Legacy code only in the importer |
| 13 | **Frozen-build CI (macOS arm64)**: PyInstaller onedir engine + shim, re-sign every Mach-O (ad hoc in PR CI, Developer ID in release), hardened runtime, smoke test from the frozen build (create vault, ingest, query via shim, `vec0.dylib` loads) | Replaces `enclave.spec`'s single-binary build | Runs on every PR touching `engine/` or packaging | De-risks §8 before Phase 2. Can start right after PR 3 |

**Order and parallelism.** The foundation runs 1 → 2 → 3 → 4 → 5. Then 6, 7 and 8 can proceed in parallel. 9 needs 4 and 8. 10
needs 3 and 6. 11 needs 5, 6 and 7. 12 comes last. 13 starts after 3.

The retrieval-quality track plugs into PR 6 and 7 interfaces and lands independently: ONNX embeddings, reranker, Docling and
OCR, verified citations, Qwen3.5 and llama.cpp, the golden evaluation set.

**Flet GUI during the transition.**

- **PRs 1–10.** The GUI keeps working unchanged on the legacy in-process path. The importer is exposed only through the CLI
  and a hidden flag.
- **PR 11.** The GUI switches to the engine and offers migration.
- From then on there is exactly one data path, and the Tauri UI in Phase 2 replaces Flet on the same IPC.

---

## 12. Open questions and alternatives considered

### Alternatives considered

| Option | Verdict | Reason |
|---|---|---|
| Keep today's per-row ChaCha20-Poly1305 with plaintext metadata and vectors | Rejected | Leaks names, paths, hashes and embeddings; FTS5 cannot index ciphertext; the index files and cache live outside the database |
| DuckDB 1.4 with AES-GCM | Rejected for the primary store (possible later for analytics) | No incremental BM25 comparable to FTS5; VSS HNSW persistence is experimental; a second engine to secure ([document_rag_sota.md](../launch-plan/research/document_rag_sota.md) §4) |
| LanceDB | Rejected | Encryption at rest is Enterprise-only (same source) |
| `apsw-sqlite3mc` instead of `sqlcipher3` | **Fallback** | Also works, and reads and writes SQLCipher-4 files both ways (spike §1). `sqlcipher3` wins on DB-API compatibility with existing `sqlite3` code and SQLCipher tooling (the `sqlcipher` CLI for recovery). The file format stays the same either way |
| Blobs inside SQLCipher | Rejected | §4.4 |
| Separate SQLCipher databases per sensitivity tier (attached with their own keys) | Deferred | Would make `sensitive` collections separately lockable; adds cross-database queries. Revisit with household vaults |
| gRPC | Rejected | Needs a protoc toolchain on both sides and HTTP/2; heavier in Python; JSON-RPC matches MCP semantics and debugs with `socat` |
| HTTP on loopback with a bearer token | Rejected | Reachable by every local user; DNS rebinding from browsers; needs Origin/Host checks. UDS/named pipes enforce the OS access control |
| Key custody in the Rust shell (the engine receives the DEK per call) | Rejected for Phase 1 | Rust would zeroise better, but splitting custody across processes contradicts "one owner". The keystore/Touch ID part does move to Rust in Phase 2 (§5.3). A Rust engine is a long-term option |
| Keystore-only unlock (no passphrase) | Rejected | Roadmap: "the key must never sit next to the data"; also no recovery if the keychain is lost |
| sqlite-vec ANN (0.1.10 alpha) or SQLite `vec1` (IVF-PQ, found in apsw wheels) | Not now | Brute force meets the budget up to about 100k chunks at ≤ 512 dimensions (spike §6). Re-evaluate when vaults exceed that |

### Open questions for the owner

1. **Name, bundle id and CLI name.** PR 1 can land with placeholder constants, but the real values are needed before any
   build writes the new layout for real users (PR 11). Directory names, the keychain service and the socket path all derive
   from them, and changing them later means another migration. The roadmap asks for the name by the end of Phase 1.
2. **Windows data root.** This document picks `%LOCALAPPDATA%` over `%APPDATA%` so that a multi-GB database stays out of
   roaming-profile sync. Confirm.
3. **Secrets KV.** Import into a non-agent `legacy_secrets` table with an export path (§9.2 step 5), or export-only and drop the
   feature?
4. **Engine lifetime.** Should the engine (and so the unlocked vault) keep running in the tray when the window is closed? This
   document says yes, with idle lock. And may the MCP shim launch the app when it is not running? This document says no by default.
5. **Default idle lock.** 15 minutes, and lock on sleep/screen lock, are proposed. Stricter for `sensitive` collections?
6. **Touch ID in v1.** It moves keychain access into the Tauri shell (Phase 2) and needs the keychain-access-groups
   entitlement and a provisioning profile. Is that acceptable for the first public release, or should v1 ship without the
   biometric gate?
7. **Recovery kit mandatory at setup** (type-back confirmation), or skippable with a persistent warning?
8. **Passkey (PRF) unlock.** Needs native `AuthenticationServices` on macOS 15+. Worth scheduling before sync?
9. **x86 vector performance.** Ship our own AVX build of `vec0` for Windows/Linux (1.6–1.8× in the spike), or wait for upstream wheels?
10. **Flet GUI.** Adopt PR 11 (a thin engine-client adapter keeping Chat, Library and Connect), or freeze Flet and ship Phase 1
    as CLI + MCP only until Tauri lands?
