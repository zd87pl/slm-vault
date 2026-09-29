#!/usr/bin/env python3
"""SQLCipher + FTS5 + sqlite-vec feasibility spike for ADR 0001.

Answers, with measurements on the machine it runs on:

* caps   -- does one SQLCipher connection give us FTS5 *and* sqlite-vec?
* crypto -- is the file unreadable without the key (header, stdlib sqlite3,
            wrong key, WAL file)?  Does PRAGMA rekey work?  Is a VACUUM INTO /
            sqlcipher_export copy encrypted?  What survives a DELETE inside the
            encrypted file (page-level decryption with the raw key)?
* fts    -- FTS5 build + query latency on ~10k synthetic chunks, a one-query
            hybrid (FTS5 + vec0 + reciprocal rank fusion), rekey time, and the
            file-size overhead of encryption.
* knn    -- sqlite-vec brute-force KNN latency for N x dim x {float32,int8,bit},
            encrypted vs plaintext, with SQLCipher's default page cache and with
            a cache large enough to hold the table.

Every database is created in a scratch directory that is deleted at the end
(use --keep to keep it).  Results are printed as Markdown and, with --out,
written as JSON.

Run (see README.md for installing the pinned dependencies into a scratch dir):
    PYTHONPATH=<deps> python spike_sqlcipher_vec.py all --out results.json
    PYTHONPATH=<deps> python spike_sqlcipher_vec.py knn --knn-sizes 10000 --knn-dims 384
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import sqlite3 as stdlib_sqlite3
import statistics
import struct
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np
import sqlcipher3
import sqlite_vec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SQLITE_HEADER = b"SQLite format 3\x00"
MARK_TEXT = "ZEBRAQUARTZ7741 marker sentence for residue checks"
MARK_TOKEN_TAIL = b"quartz7741"  # FTS5 prefix-compresses terms; search a suffix
MARK_VEC = [1234.5678] * 8
MARK_VEC_BYTES = struct.pack("<8f", *MARK_VEC)
VEC_EXT_PATH: Optional[str] = None  # --vec-ext: load a custom sqlite-vec build instead of the wheel's


def load_vec(con: Any) -> None:
    """Load sqlite-vec into a connection (extension loading is switched off again after)."""
    con.enable_load_extension(True)
    if VEC_EXT_PATH:
        con.load_extension(VEC_EXT_PATH)
    else:
        sqlite_vec.load(con)
    con.enable_load_extension(False)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def key_pragma(key: bytes, pragma: str = "key") -> str:
    """Raw 256-bit key: SQLCipher uses it directly, skipping its own PBKDF2."""
    return f"PRAGMA {pragma} = \"x'{key.hex()}'\""


def connect(
    path: Path,
    key: Optional[bytes] = None,
    *,
    cache_kib: Optional[int] = None,
    wal: bool = True,
    with_vec: bool = True,
) -> "sqlcipher3.Connection":
    con = sqlcipher3.connect(str(path), isolation_level=None)
    if key is not None:
        con.execute(key_pragma(key))  # must be the first statement
    con.execute("SELECT count(*) FROM sqlite_schema").fetchone()  # fails fast on a wrong key
    if wal:
        con.execute("PRAGMA journal_mode = WAL")
    if cache_kib:
        con.execute(f"PRAGMA cache_size = -{int(cache_kib)}")
    if with_vec:
        load_vec(con)
    return con


def remove_db(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()


def timed(fn: Callable[..., Any], *args: Any) -> Tuple[float, Any]:
    t0 = time.perf_counter()
    out = fn(*args)
    return (time.perf_counter() - t0) * 1000.0, out


def fetch_all(con: Any, sql: str, params: Any = ()) -> List[Any]:
    return con.execute(sql, params).fetchall()


def pct(values: List[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return float("nan")
    idx = min(len(s) - 1, max(0, int(round(q / 100.0 * (len(s) - 1)))))
    return s[idx]


def summary(values: List[float]) -> Dict[str, float]:
    return {
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(pct(values, 95), 3),
        "mean_ms": round(statistics.fmean(values), 3),
        "n": len(values),
    }


def environment() -> Dict[str, Any]:
    cpu = platform.processor() or ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    con = sqlcipher3.connect(":memory:")
    con.execute(key_pragma(b"\x00" * 32))
    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": cpu,
        "cpu_count": os.cpu_count(),
        "loadavg_at_start": os.getloadavg() if hasattr(os, "getloadavg") else None,
        "sqlcipher3_module": sqlcipher3.__file__,
        "sqlite_version": con.execute("select sqlite_version()").fetchone()[0],
        "cipher_version": con.execute("PRAGMA cipher_version").fetchone()[0],
        "cipher_provider": " ".join(
            str(con.execute(p).fetchone()[0]) for p in ("PRAGMA cipher_provider", "PRAGMA cipher_provider_version")
        ),
    }
    load_vec(con)
    env["sqlite_vec_version"] = con.execute("select vec_version()").fetchone()[0]
    env["sqlite_vec_source"] = VEC_EXT_PATH or sqlite_vec.loadable_path()
    con.close()
    return env


# --------------------------------------------------------------------------
# caps
# --------------------------------------------------------------------------


def run_caps(_args: argparse.Namespace, _workdir: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    con = sqlcipher3.connect(":memory:")
    con.execute(key_pragma(secrets.token_bytes(32)))
    opts = [r[0] for r in con.execute("PRAGMA compile_options")]
    out["compile_options_of_interest"] = [
        o for o in opts
        if any(k in o for k in ("FTS", "LOAD_EXT", "OMIT", "HAS_CODEC", "TEMP_STORE", "THREADSAFE", "SECURE_DELETE", "DBPAGE"))
    ]
    out["cipher_default_settings"] = [r[0] for r in con.execute("PRAGMA cipher_default_settings")]
    out["cipher_memory_security"] = con.execute("PRAGMA cipher_memory_security").fetchone()[0]
    out["has_enable_load_extension"] = hasattr(con, "enable_load_extension")

    load_vec(con)
    out["vec_version"] = con.execute("select vec_version()").fetchone()[0]

    con.execute("CREATE VIRTUAL TABLE f USING fts5(body)")
    con.execute("CREATE VIRTUAL TABLE v USING vec0(embedding float[4])")
    con.execute("INSERT INTO f(rowid, body) VALUES (1, 'the lease notice period is two months')")
    con.execute("INSERT INTO v(rowid, embedding) VALUES (1, ?)", (struct.pack("<4f", 1, 0, 0, 0),))
    row = con.execute(
        "SELECT f.rowid, v.distance FROM f JOIN (SELECT rowid, distance FROM v WHERE embedding MATCH ? AND k = 1) v"
        " ON v.rowid = f.rowid WHERE f MATCH 'notice'",
        (struct.pack("<4f", 1, 0, 0, 0),),
    ).fetchone()
    out["fts5_and_vec0_in_one_query"] = row is not None
    # extension state after the key is set, and loading *before* the key is set
    con2 = sqlcipher3.connect(":memory:")
    load_vec(con2)
    con2.execute(key_pragma(secrets.token_bytes(32)))
    con2.execute("CREATE VIRTUAL TABLE v USING vec0(embedding float[4])")
    out["vec_loaded_before_key_ok"] = True
    return out


# --------------------------------------------------------------------------
# crypto
# --------------------------------------------------------------------------


def iter_decrypted_pages(path: Path, key: bytes, page_size: int = 4096, reserve: int = 80) -> Iterator[Tuple[int, bytes]]:
    """Decrypt SQLCipher 4 pages ourselves (AES-256-CBC, IV at the start of the
    reserved area, raw key used directly).  HMACs are not verified."""
    data = path.read_bytes()
    usable = page_size - reserve
    for i in range(len(data) // page_size):
        page = data[i * page_size:(i + 1) * page_size]
        start = 16 if i == 0 else 0  # page 1 starts with the 16-byte salt
        iv = page[usable:usable + 16]
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        yield i + 1, dec.update(page[start:usable]) + dec.finalize()


def scan_markers(blob: bytes) -> Dict[str, bool]:
    return {
        "text": MARK_TEXT.encode() in blob,
        "fts_token": MARK_TOKEN_TAIL in blob,
        "vector": MARK_VEC_BYTES[:16] in blob,
    }


def _crypto_schema(con: "sqlcipher3.Connection") -> None:
    con.execute("CREATE TABLE docs(id INTEGER PRIMARY KEY, body TEXT)")
    con.execute("CREATE VIRTUAL TABLE fts USING fts5(body)")
    con.execute("CREATE VIRTUAL TABLE vec USING vec0(embedding float[8])")


def _crypto_fill(con: "sqlcipher3.Connection", rng: np.random.Generator, n: int = 200) -> None:
    con.execute("BEGIN")
    for i in range(1, n + 1):
        body = f"filler document {i} " + " ".join(f"w{int(x)}" for x in rng.integers(0, 5000, 60))
        con.execute("INSERT INTO docs(id, body) VALUES (?, ?)", (i, body))
        con.execute("INSERT INTO fts(rowid, body) VALUES (?, ?)", (i, body))
        con.execute("INSERT INTO vec(rowid, embedding) VALUES (?, ?)", (i, rng.standard_normal(8).astype(np.float32).tobytes()))
    con.execute("COMMIT")


def _insert_marker(con: "sqlcipher3.Connection", rowid: int) -> None:
    con.execute("BEGIN")
    con.execute("INSERT INTO docs(id, body) VALUES (?, ?)", (rowid, MARK_TEXT))
    con.execute("INSERT INTO fts(rowid, body) VALUES (?, ?)", (rowid, MARK_TEXT))
    con.execute("INSERT INTO vec(rowid, embedding) VALUES (?, ?)", (rowid, MARK_VEC_BYTES))
    con.execute("COMMIT")


def _delete_marker(con: "sqlcipher3.Connection", rowid: int) -> None:
    con.execute("BEGIN")
    con.execute("DELETE FROM docs WHERE id = ?", (rowid,))
    con.execute("DELETE FROM fts WHERE rowid = ?", (rowid,))
    con.execute("DELETE FROM vec WHERE rowid = ?", (rowid,))
    con.execute("COMMIT")


def _residue_scenario(workdir: Path, label: str, secure_delete: Optional[bool], fts_secure: bool) -> Dict[str, Any]:
    key = secrets.token_bytes(32)
    path = workdir / f"residue_{label}.db"
    rng = np.random.default_rng(7)
    con = connect(path, key)
    if secure_delete is not None:  # None: keep SQLCipher's default (ON for keyed databases)
        con.execute(f"PRAGMA secure_delete = {'ON' if secure_delete else 'OFF'}")
    effective_secure_delete = con.execute("PRAGMA secure_delete").fetchone()[0]
    _crypto_schema(con)
    if fts_secure:
        con.execute("INSERT INTO fts(fts, rank) VALUES ('secure-delete', 1)")
    _crypto_fill(con, rng)
    _insert_marker(con, 10_000)
    con.executemany("INSERT INTO docs(id, body) VALUES (?, ?)", [(i, f"late filler {i}") for i in range(300, 320)])
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = {k: False for k in ("text", "fts_token", "vector")}
    for _no, page in iter_decrypted_pages(path, key):
        for k, v in scan_markers(page).items():
            before[k] = before[k] or v
    _delete_marker(con, 10_000)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    # note: a fresh connection below starts with SQLCipher's default secure_delete again
    after = {k: False for k in ("text", "fts_token", "vector")}
    for _no, page in iter_decrypted_pages(path, key):
        for k, v in scan_markers(page).items():
            after[k] = after[k] or v
    # a VACUUM rebuilds the file from live rows only
    con = connect(path, key)
    con.execute("VACUUM")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    after_vacuum = {k: False for k in ("text", "fts_token", "vector")}
    for _no, page in iter_decrypted_pages(path, key):
        for k, v in scan_markers(page).items():
            after_vacuum[k] = after_vacuum[k] or v
    remove_db(path)
    return {
        "secure_delete_effective": effective_secure_delete,
        "fts5_secure_delete_option": fts_secure,
        "marker_found_before_delete": before,
        "marker_found_after_delete": after,
        "marker_found_after_vacuum": after_vacuum,
    }


def run_crypto(_args: argparse.Namespace, workdir: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    key, key2, key3 = (secrets.token_bytes(32) for _ in range(3))
    rng = np.random.default_rng(3)

    # 1. plaintext control vs encrypted, including the WAL before checkpoint
    for label, k in (("plaintext_control", None), ("encrypted", key)):
        path = workdir / f"crypto_{label}.db"
        con = connect(path, k)
        con.execute("PRAGMA wal_autocheckpoint = 0")
        _crypto_schema(con)
        _crypto_fill(con, rng, n=50)
        _insert_marker(con, 10_000)
        wal = Path(str(path) + "-wal").read_bytes()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        main = path.read_bytes()
        out[label] = {
            "file_header_is_sqlite_magic": main[:16] == SQLITE_HEADER,
            "first_16_bytes_hex": main[:16].hex(),
            "markers_in_wal_before_checkpoint": scan_markers(wal),
            "markers_in_main_file": scan_markers(main),
        }
    enc_path = workdir / "crypto_encrypted.db"

    # 2. stdlib sqlite3 / no key / wrong key
    def _stdlib() -> str:
        c = stdlib_sqlite3.connect(str(enc_path))
        try:
            c.execute("SELECT count(*) FROM sqlite_master").fetchone()
            return "OPENED (unexpected)"
        except stdlib_sqlite3.DatabaseError as e:
            return f"{type(e).__name__}: {e}"
        finally:
            c.close()

    def _sqlcipher(k: Optional[bytes]) -> str:
        c = sqlcipher3.connect(str(enc_path))
        try:
            if k is not None:
                c.execute(key_pragma(k))
            c.execute("SELECT count(*) FROM sqlite_schema").fetchone()
            return "OPENED"
        except sqlcipher3.DatabaseError as e:
            return f"{type(e).__name__}: {e}"
        finally:
            c.close()

    out["open_with_stdlib_sqlite3"] = _stdlib()
    out["open_sqlcipher_no_key"] = _sqlcipher(None)
    out["open_sqlcipher_wrong_key"] = _sqlcipher(secrets.token_bytes(32))
    out["open_sqlcipher_right_key"] = _sqlcipher(key)

    # 3. rekey (in WAL mode, as the engine will run)
    con = connect(enc_path, key)
    try:
        con.execute(key_pragma(key2, "rekey"))
        out["rekey_in_wal_mode"] = "ok"
    except sqlcipher3.DatabaseError as e:
        out["rekey_in_wal_mode"] = f"{type(e).__name__}: {e}"
    con.close()
    out["after_rekey_old_key"] = _sqlcipher(key)
    out["after_rekey_new_key"] = _sqlcipher(key2)
    current = key2 if out["after_rekey_new_key"] == "OPENED" else key

    # 4. copies: VACUUM INTO and sqlcipher_export (backups)
    vac = workdir / "vacuum_into.db"
    con = connect(enc_path, current)
    try:
        con.execute(f"VACUUM INTO '{vac}'")
        vb = vac.read_bytes()
        out["vacuum_into"] = {
            "header_is_sqlite_magic": vb[:16] == SQLITE_HEADER,
            "markers_in_copy": scan_markers(vb),
            "opens_with_same_key": None,
        }
        c = sqlcipher3.connect(str(vac))
        try:
            c.execute(key_pragma(current))
            c.execute("SELECT count(*) FROM docs").fetchone()
            out["vacuum_into"]["opens_with_same_key"] = True
        except sqlcipher3.DatabaseError:
            out["vacuum_into"]["opens_with_same_key"] = False
        c.close()
    except sqlcipher3.DatabaseError as e:
        out["vacuum_into"] = f"{type(e).__name__}: {e}"
    exp = workdir / "export.db"
    try:
        con.execute(f"ATTACH DATABASE '{exp}' AS backup KEY \"x'{key3.hex()}'\"")
        con.execute("SELECT sqlcipher_export('backup')")
        con.execute("DETACH DATABASE backup")
        eb = exp.read_bytes()
        c = connect(exp, key3, wal=False)
        counts = {
            t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("docs", "fts", "vec")
        }
        knn = c.execute(
            "SELECT rowid FROM vec WHERE embedding MATCH ? AND k = 1", (MARK_VEC_BYTES,)
        ).fetchone()
        fts_hit = c.execute("SELECT rowid FROM fts WHERE fts MATCH 'zebraquartz7741'").fetchone()
        c.close()
        out["sqlcipher_export_new_key"] = {
            "header_is_sqlite_magic": eb[:16] == SQLITE_HEADER,
            "markers_in_copy": scan_markers(eb),
            "row_counts": counts,
            "vec_knn_finds_marker": bool(knn and knn[0] == 10_000),
            "fts_finds_marker": bool(fts_hit and fts_hit[0] == 10_000),
        }
    except sqlcipher3.DatabaseError as e:
        out["sqlcipher_export_new_key"] = f"{type(e).__name__}: {e}"
    con.close()

    # 5. page-level decryption with the raw key: sanity + delete residue
    header = next(iter_decrypted_pages(enc_path, current))[1]
    out["own_page_decryption"] = {
        "page_size_field": struct.unpack(">H", header[0:2])[0],
        "reserved_bytes_field": header[4],
        "live_markers_visible_in_decrypted_pages": {
            k: any(scan_markers(p)[k] for _n, p in iter_decrypted_pages(enc_path, current))
            for k in ("text", "fts_token", "vector")
        },
    }
    out["delete_residue_sqlcipher_defaults"] = _residue_scenario(workdir, "default", None, fts_secure=False)
    out["delete_residue_secure_delete_off"] = _residue_scenario(workdir, "off", False, fts_secure=False)
    out["delete_residue_fts5_secure_delete"] = _residue_scenario(workdir, "secure", True, fts_secure=True)
    for p in (enc_path, workdir / "crypto_plaintext_control.db", vac, exp):
        remove_db(p)
    return out


# --------------------------------------------------------------------------
# fts (+ hybrid)
# --------------------------------------------------------------------------


def _syllable_vocab(size: int, rng: np.random.Generator) -> List[str]:
    sy = ["ka", "lo", "mi", "ne", "ru", "sa", "te", "vi", "zo", "pa", "de", "fi", "go", "hu", "ja", "ke", "li", "mo", "nu", "po"]
    words, seen = [], set()
    while len(words) < size:
        w = "".join(sy[int(i)] for i in rng.integers(0, len(sy), int(rng.integers(2, 5))))
        if w not in seen:
            seen.add(w)
            words.append(w)
    return words


def synth_chunks(n: int, words: int, seed: int = 11) -> Tuple[List[str], Dict[str, str]]:
    rng = np.random.default_rng(seed)
    vocab = _syllable_vocab(30_000, rng)
    ranks = np.arange(1, len(vocab) + 1)
    p = 1.0 / ranks ** 1.07
    p /= p.sum()
    ids = rng.choice(len(vocab), size=(n, words), p=p)
    chunks = [" ".join(vocab[j] for j in row) for row in ids]
    # injected facts: entities, dates and one phrase, as a life-document vault would hold
    for i in rng.choice(n, 100, replace=False):
        chunks[int(i)] += f" policy number ZX-{10000 + int(i)} renews 2027-03-{1 + int(i) % 28:02d}"
    for i in rng.choice(n, 20, replace=False):
        chunks[int(i)] += " the boiler warranty expires on 12 March 2031"
    target_entity = next(c for c in chunks if "ZX-" in c).split("ZX-")[1].split()[0]
    queries = {
        "common term": vocab[3],
        "mid-frequency term": vocab[400],
        "rare term": vocab[20_000],
        "two terms (AND)": f"{vocab[150]} {vocab[900]}",
        "phrase": '"boiler warranty expires"',
        "prefix": vocab[1200][:4] + "*",
        "entity (policy no.)": f'"ZX-{target_entity}"',
        "OR of 5 terms": " OR ".join(vocab[k] for k in (50, 300, 700, 2000, 9000)),
    }
    return chunks, queries


FTS_SQL = (
    "SELECT rowid, snippet(chunks_fts, 0, '[', ']', '...', 12) FROM chunks_fts "
    "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 10"
)
HYBRID_SQL = """
WITH fts AS (
    SELECT rowid AS id, row_number() OVER (ORDER BY rank) AS r
    FROM chunks_fts WHERE chunks_fts MATCH :q ORDER BY rank LIMIT 50
), knn AS (
    SELECT rowid AS id, row_number() OVER (ORDER BY distance) AS r
    FROM chunks_vec WHERE embedding MATCH :v AND k = 50
)
SELECT coalesce(fts.id, knn.id) AS id,
       coalesce(1.0 / (60 + fts.r), 0) + coalesce(1.0 / (60 + knn.r), 0) AS score
FROM fts FULL OUTER JOIN knn ON fts.id = knn.id
ORDER BY score DESC LIMIT 10
"""


def _load_fts_corpus(con: Any, chunks: List[str], vecs: np.ndarray) -> None:
    con.execute("BEGIN")
    con.executemany(
        "INSERT INTO chunks(id, doc_id, text) VALUES (?, ?, ?)",
        ((i + 1, i // 20, c) for i, c in enumerate(chunks)),
    )
    con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
    con.executemany(
        "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
        ((i + 1, vecs[i].tobytes()) for i in range(len(chunks))),
    )
    con.execute("COMMIT")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def run_fts(args: argparse.Namespace, workdir: Path) -> Dict[str, Any]:
    n, words, reps = args.fts_chunks, args.fts_words, args.reps
    chunks, queries = synth_chunks(n, words)
    rng = np.random.default_rng(5)
    vecs = rng.standard_normal((n, 384)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    out: Dict[str, Any] = {
        "chunks": n,
        "words_per_chunk": words,
        "corpus_mib": round(sum(len(c) for c in chunks) / 2**20, 1),
        "queries": queries,
    }
    key = secrets.token_bytes(32)
    for label, k in (("plaintext", None), ("encrypted", key)):
        path = workdir / f"fts_{label}.db"
        con = connect(path, k)
        con.execute("CREATE TABLE chunks(id INTEGER PRIMARY KEY, doc_id INTEGER, text TEXT NOT NULL)")
        con.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='id',"
            " tokenize='unicode61 remove_diacritics 2')"
        )
        con.execute("CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[384])")
        build_ms, _ = timed(_load_fts_corpus, con, chunks, vecs)
        con.close()
        size = path.stat().st_size
        res: Dict[str, Any] = {"build_ms": round(build_ms, 1), "file_bytes": size}
        qv = vecs[123].tobytes()
        hq = {"q": queries["two terms (AND)"], "v": qv}
        for cache_label, cache_kib in (("default_cache", None), ("large_cache", int(size / 1024 * 1.5) + 4096)):
            con = connect(path, k, cache_kib=cache_kib)  # reopened: cold page cache
            first_ms, _ = timed(fetch_all, con, FTS_SQL, (queries["common term"],))
            per_query: Dict[str, Any] = {"first_query_after_open_ms": round(first_ms, 2)}
            for name, q in queries.items():
                for _ in range(3):
                    con.execute(FTS_SQL, (q,)).fetchall()
                lat, hits = [], 0
                for _ in range(reps):
                    ms, rows = timed(fetch_all, con, FTS_SQL, (q,))
                    lat.append(ms)
                    hits = len(rows)
                per_query[name] = {**summary(lat), "hits": hits}
            hyb = []
            for _ in range(3):
                con.execute(HYBRID_SQL, hq).fetchall()
            for _ in range(reps):
                ms, rows = timed(fetch_all, con, HYBRID_SQL, hq)
                hyb.append(ms)
            per_query["hybrid RRF (FTS5 top-50 + KNN top-50, 384-d)"] = {**summary(hyb), "hits": len(rows)}
            res[cache_label] = per_query
            con.close()
        if k is not None:
            con = connect(path, k)
            new_key = secrets.token_bytes(32)
            rk_ms, _ = timed(con.execute, key_pragma(new_key, "rekey"))
            con.close()
            ok = connect(path, new_key, wal=False).execute("SELECT count(*) FROM chunks").fetchone()[0] == n
            res["rekey"] = {"ms": round(rk_ms, 1), "file_mib": round(path.stat().st_size / 2**20, 1), "verified": ok}
        out[label] = res
        remove_db(path)
    p, e = out["plaintext"]["file_bytes"], out["encrypted"]["file_bytes"]
    out["encryption_size_overhead_pct"] = round((e - p) / p * 100, 2)
    return out


# --------------------------------------------------------------------------
# knn
# --------------------------------------------------------------------------


def _encode(x: np.ndarray, vtype: str) -> bytes:
    if vtype == "float32":
        return x.astype(np.float32).tobytes()
    if vtype == "int8":
        return np.clip(np.round(x * 127.0 / max(1e-9, float(np.abs(x).max()))), -127, 127).astype(np.int8).tobytes()
    if vtype == "bit":
        return np.packbits(x > 0).tobytes()
    raise ValueError(vtype)


def _wrap(vtype: str) -> str:
    return {"float32": "?", "int8": "vec_int8(?)", "bit": "vec_bit(?)"}[vtype]


def _load_vectors(
    con: Any, insert_sql: str, rng: np.random.Generator, n: int, dim: int, vtype: str, kept: Optional[List[np.ndarray]]
) -> None:
    con.execute("BEGIN")
    for start in range(0, n, 5000):
        m = min(5000, n - start)
        x = rng.standard_normal((m, dim)).astype(np.float32)
        x /= np.linalg.norm(x, axis=1, keepdims=True)
        if kept is not None:
            kept.append(x)
        con.executemany(insert_sql, ((start + i + 1, _encode(x[i], vtype)) for i in range(m)))
    con.execute("COMMIT")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def bench_knn_one(workdir: Path, n: int, dim: int, vtype: str, key: Optional[bytes], reps: int) -> Dict[str, Any]:
    label = "enc" if key else "plain"
    path = workdir / f"knn_{n}_{dim}_{vtype}_{label}.db"
    col = {"float32": f"float[{dim}]", "int8": f"int8[{dim}]", "bit": f"bit[{dim}]"}[vtype]
    rng = np.random.default_rng(1000 + dim)
    con = connect(path, key)
    con.execute(f"CREATE VIRTUAL TABLE v USING vec0(embedding {col})")
    insert_sql = f"INSERT INTO v(rowid, embedding) VALUES (?, {_wrap(vtype)})"
    keep = n <= 10_000 and vtype == "float32"
    kept: List[np.ndarray] = []
    insert_ms, _ = timed(_load_vectors, con, insert_sql, rng, n, dim, vtype, kept if keep else None)
    con.close()
    size = path.stat().st_size
    qrng = np.random.default_rng(42)
    qs = qrng.standard_normal((reps + 1, dim)).astype(np.float32)
    qs /= np.linalg.norm(qs, axis=1, keepdims=True)
    sql = f"SELECT rowid, distance FROM v WHERE embedding MATCH {_wrap(vtype)} AND k = 10"
    res: Dict[str, Any] = {
        "n": n, "dim": dim, "type": vtype, "encrypted": key is not None,
        "insert_s": round(insert_ms / 1000, 2), "file_mib": round(size / 2**20, 1),
    }
    for cache_label, cache_kib, nq in (
        ("default_cache", None, max(5, reps // 3)),
        ("large_cache", int(size / 1024 * 1.5) + 4096, reps),
    ):
        con = connect(path, key, cache_kib=cache_kib)
        first_ms, _ = timed(fetch_all, con, sql, (_encode(qs[0], vtype),))
        lat = []
        for i in range(nq):
            ms, _ = timed(fetch_all, con, sql, (_encode(qs[1 + i % reps], vtype),))
            lat.append(ms)
        res[cache_label] = {"first_query_ms": round(first_ms, 2), **summary(lat)}
        con.close()
    if keep:
        mat = np.concatenate(kept)
        exact = np.argsort(-(mat @ qs[1]))[:10] + 1
        con = connect(path, key)
        got = [r[0] for r in con.execute(sql, (_encode(qs[1], vtype),)).fetchall()]
        con.close()
        res["exact_top10_match"] = sorted(got) == sorted(exact.tolist())
    remove_db(path)
    return res


def run_knn(args: argparse.Namespace, workdir: Path) -> Dict[str, Any]:
    key = secrets.token_bytes(32)
    rows = []
    for n in args.knn_sizes:
        for dim in args.knn_dims:
            for vtype in args.knn_types:
                for k in (None, key):
                    r = bench_knn_one(workdir, n, dim, vtype, k, args.reps)
                    rows.append(r)
                    print(
                        f"  knn n={n} dim={dim} {vtype} {'enc' if k else 'plain'}: "
                        f"{r['file_mib']} MiB, default cache p50 {r['default_cache']['p50_ms']} ms, "
                        f"large cache p50 {r['large_cache']['p50_ms']} ms",
                        flush=True,
                    )
    return {"rows": rows}


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def print_markdown(results: Dict[str, Any]) -> None:
    env = results.get("environment", {})
    print("\n## Environment\n")
    for k, v in env.items():
        print(f"- {k}: {v}")
    if "caps" in results:
        print("\n## Capabilities\n")
        for k, v in results["caps"].items():
            print(f"- {k}: {v}")
    if "crypto" in results:
        print("\n## Crypto checks\n")
        print("```json")
        print(json.dumps(results["crypto"], indent=2))
        print("```")
    if "fts" in results:
        f = results["fts"]
        print(f"\n## FTS5 ({f['chunks']} chunks x {f['words_per_chunk']} words, {f['corpus_mib']} MiB text)\n")
        print("| query | plain, default cache p50 / p95 ms | encrypted, default cache p50 / p95 ms | plain, large cache p50 / p95 ms | encrypted, large cache p50 / p95 ms | hits |")
        print("|---|---|---|---|---|---|")
        for name, e in f["encrypted"]["default_cache"].items():
            if name == "first_query_after_open_ms":
                continue
            cols = [f[lab][cm][name] for cm in ("default_cache", "large_cache") for lab in ("plaintext", "encrypted")]
            print(f"| {name} | " + " | ".join(f"{c['p50_ms']} / {c['p95_ms']}" for c in cols) + f" | {e['hits']} |")
        print(
            f"\nbuild ms plain/enc: {f['plaintext']['build_ms']} / {f['encrypted']['build_ms']}; "
            f"file bytes plain/enc: {f['plaintext']['file_bytes']} / {f['encrypted']['file_bytes']} "
            f"(+{f['encryption_size_overhead_pct']}%); rekey: {f['encrypted'].get('rekey')}"
        )
    if "knn" in results:
        print("\n## sqlite-vec brute-force KNN (k=10)\n")
        print("| n | dim | type | enc | file MiB | insert s | default cache p50 / p95 ms | large cache first / p50 / p95 ms |")
        print("|---|---|---|---|---|---|---|---|")
        for r in results["knn"]["rows"]:
            d, lc = r["default_cache"], r["large_cache"]
            print(
                f"| {r['n']} | {r['dim']} | {r['type']} | {'yes' if r['encrypted'] else 'no'} | {r['file_mib']} | "
                f"{r['insert_s']} | {d['p50_ms']} / {d['p95_ms']} | {lc['first_query_ms']} / {lc['p50_ms']} / {lc['p95_ms']} |"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["caps", "crypto", "fts", "knn", "all"])
    ap.add_argument("--workdir", type=Path, default=None, help="scratch dir for databases (default: a new temp dir)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch dir")
    ap.add_argument("--out", type=Path, default=None, help="write results JSON here")
    ap.add_argument("--reps", type=int, default=30, help="timed repetitions per query")
    ap.add_argument("--fts-chunks", type=int, default=10_000)
    ap.add_argument("--fts-words", type=int, default=300)
    ap.add_argument("--knn-sizes", type=lambda s: [int(x) for x in s.split(",")], default=[10_000, 100_000])
    ap.add_argument("--knn-dims", type=lambda s: [int(x) for x in s.split(",")], default=[384, 1024])
    ap.add_argument("--knn-types", type=lambda s: s.split(","), default=["float32", "int8", "bit"])
    ap.add_argument("--vec-ext", default=None, help="path to a custom sqlite-vec loadable extension (e.g. an AVX build)")
    args = ap.parse_args()
    global VEC_EXT_PATH
    VEC_EXT_PATH = args.vec_ext

    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="sqlcipher-vec-spike-"))
    workdir.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Any] = {"environment": environment()}
    steps = ["caps", "crypto", "fts", "knn"] if args.what == "all" else [args.what]
    runners = {"caps": run_caps, "crypto": run_crypto, "fts": run_fts, "knn": run_knn}
    try:
        for step in steps:
            print(f"[{step}] running...", flush=True)
            t0 = time.perf_counter()
            results[step] = runners[step](args, workdir)
            print(f"[{step}] done in {time.perf_counter() - t0:.1f}s", flush=True)
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
    results["environment"]["loadavg_at_end"] = os.getloadavg() if hasattr(os, "getloadavg") else None
    if args.out:
        args.out.write_text(json.dumps(results, indent=2, default=str))
    print_markdown(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
