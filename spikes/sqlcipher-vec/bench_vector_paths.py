#!/usr/bin/env python3
"""Vector query path under concurrent writes (ADR 0001 §4.4, review finding B1).

Part A, invalidation. In WAL mode, a commit by *another* connection makes every
reader connection drop its page cache before its next read. With SQLCipher that
means re-decrypting every page the next query touches. This measures sqlite-vec
KNN and FTS5 queries warm, and right after a one-row commit to an unrelated table.
It also measures the case where the writer is the reader's own connection.

Part B, in-engine matrix. This is the design ADR 0001 adopts: the engine, which is
the only writer, keeps the live embeddings in a numpy float32 matrix. The matrix
is loaded from a plain BLOB table in SQLCipher at unlock and updated by the writer.
Measured: load time, memory, query p50 (all rows and a 30% collection mask; default
BLAS threads and 1 thread), update cost (one 20-chunk document in one transaction,
plus the in-memory append), delete cost, and a hybrid query (FTS5 top-50 in
SQLCipher, numpy top-50, RRF in Python) with a writer commit before *every* query,
which is the engine's real pattern.

Every database lives in a temp dir that is deleted at the end.

Usage:
    PYTHONPATH=<deps> python bench_vector_paths.py [--sizes 100000] [--dims 384,1024] [--out vector_paths.json]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spike_sqlcipher_vec as sp  # noqa: E402  (connect, synth_chunks, FTS helpers)

try:  # optional: pin BLAS threads for the 1-thread measurement
    from threadpoolctl import threadpool_limits
except ImportError:  # pragma: no cover
    threadpool_limits = None


def ms_since(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def p50(xs: List[float]) -> float:
    return round(statistics.median(xs), 3)


def unit_rows(rng: np.random.Generator, n: int, dim: int) -> np.ndarray:
    x = rng.standard_normal((n, dim)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return x


# ----------------------------------------------------------------------------
# Part A: page-cache invalidation
# ----------------------------------------------------------------------------


def part_a(workdir: Path, n: int, dim: int, fts_chunks: int, reps: int) -> Dict[str, Any]:
    key = secrets.token_bytes(32)
    path = workdir / "inval.db"
    w = sp.connect(path, key)
    w.execute("CREATE TABLE other(id INTEGER PRIMARY KEY, x TEXT)")
    w.execute(f"CREATE VIRTUAL TABLE v USING vec0(embedding float[{dim}])")
    w.execute("CREATE TABLE chunks(id INTEGER PRIMARY KEY, doc_id INTEGER, text TEXT NOT NULL)")
    w.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2')")
    rng = np.random.default_rng(1)
    x = unit_rows(rng, n, dim)
    w.execute("BEGIN")
    w.executemany("INSERT INTO v(rowid, embedding) VALUES (?, ?)", ((i + 1, x[i].tobytes()) for i in range(n)))
    w.execute("COMMIT")
    chunks, queries = sp.synth_chunks(fts_chunks, 300)
    w.execute("BEGIN")
    w.executemany("INSERT INTO chunks(id, doc_id, text) VALUES (?, ?, ?)", ((i + 1, i // 20, c) for i, c in enumerate(chunks)))
    w.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
    w.execute("COMMIT")
    w.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size_kib = path.stat().st_size // 1024
    r = sp.connect(path, key, cache_kib=int(size_kib * 1.5) + 4096)
    q = x[7].tobytes()
    knn_sql = "SELECT rowid, distance FROM v WHERE embedding MATCH ? AND k = 10"

    def t_knn(con: Any) -> float:
        t0 = time.perf_counter()
        con.execute(knn_sql, (q,)).fetchall()
        return ms_since(t0)

    def t_fts(con: Any, term: str) -> float:
        t0 = time.perf_counter()
        con.execute(sp.FTS_SQL, (term,)).fetchall()
        return ms_since(t0)

    out: Dict[str, Any] = {"n": n, "dim": dim, "fts_chunks": fts_chunks, "file_mib": round(path.stat().st_size / 2**20, 1)}
    t_knn(r)  # load everything into the reader's cache
    for term in (queries["common term"], queries["rare term"]):
        t_fts(r, term)
    out["vec0_knn_warm_p50_ms"] = p50([t_knn(r) for _ in range(reps)])
    out["fts_common_warm_p50_ms"] = p50([t_fts(r, queries["common term"]) for _ in range(reps)])
    out["fts_rare_warm_p50_ms"] = p50([t_fts(r, queries["rare term"]) for _ in range(reps)])
    after_knn, after_common, after_rare = [], [], []
    for i in range(max(5, reps // 3)):
        w.execute("INSERT INTO other(x) VALUES (?)", (f"audit row {i}",))
        after_knn.append(t_knn(r))
        w.execute("INSERT INTO other(x) VALUES (?)", (f"audit row {i}b",))
        after_common.append(t_fts(r, queries["common term"]))
        w.execute("INSERT INTO other(x) VALUES (?)", (f"audit row {i}c",))
        after_rare.append(t_fts(r, queries["rare term"]))
    out["vec0_knn_after_other_connection_commit_p50_ms"] = p50(after_knn)
    out["fts_common_after_other_connection_commit_p50_ms"] = p50(after_common)
    out["fts_rare_after_other_connection_commit_p50_ms"] = p50(after_rare)
    # the same connection commits and then queries: its own cache stays valid
    t_knn(r)
    own = []
    for i in range(max(5, reps // 3)):
        r.execute("INSERT INTO other(x) VALUES (?)", (f"own row {i}",))
        own.append(t_knn(r))
    out["vec0_knn_after_own_connection_commit_p50_ms"] = p50(own)
    r.close()
    w.close()
    sp.remove_db(path)
    return out


# ----------------------------------------------------------------------------
# Part B: numpy matrix in the engine, SQLCipher for persistence
# ----------------------------------------------------------------------------


class VectorMatrix:
    """What the engine keeps in RAM: ids + a float32 matrix with spare capacity."""

    def __init__(self, dim: int, capacity: int):
        self.dim = dim
        self.ids = np.zeros(capacity, dtype=np.int64)
        self.mat = np.zeros((capacity, dim), dtype=np.float32)
        self.alive = np.zeros(capacity, dtype=bool)
        self.n = 0
        self.pos: Dict[int, int] = {}

    def append(self, ids: np.ndarray, rows: np.ndarray) -> None:
        need = self.n + len(ids)
        if need > len(self.ids):
            cap = max(need, int(len(self.ids) * 1.5) + 1024)
            self.ids = np.resize(self.ids, cap)
            self.alive = np.concatenate([self.alive, np.zeros(cap - len(self.alive), dtype=bool)])
            mat = np.zeros((cap, self.dim), dtype=np.float32)
            mat[: self.n] = self.mat[: self.n]
            self.mat = mat
        self.ids[self.n:need] = ids
        self.mat[self.n:need] = rows
        self.alive[self.n:need] = True
        for j, cid in enumerate(ids.tolist()):
            self.pos[cid] = self.n + j
        self.n = need

    def delete(self, cid: int) -> None:
        j = self.pos.pop(cid)
        self.alive[j] = False
        self.mat[j] = 0.0  # tombstone; zero the row so the plaintext vector does not linger

    def topk(self, q: np.ndarray, k: int, mask: np.ndarray | None = None) -> np.ndarray:
        scores = self.mat[: self.n] @ q
        valid = self.alive[: self.n] if mask is None else (self.alive[: self.n] & mask[: self.n])
        scores[~valid] = -np.inf
        idx = np.argpartition(-scores, k)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return self.ids[idx]


def load_matrix(con: Any, dim: int, n_hint: int) -> VectorMatrix:
    vm = VectorMatrix(dim, n_hint + 1024)
    cur = con.execute("SELECT chunk_id, vec FROM chunk_vectors ORDER BY chunk_id")
    i = 0
    ids = vm.ids
    mat = vm.mat
    while True:
        rows = cur.fetchmany(4096)
        if not rows:
            break
        for cid, blob in rows:
            ids[i] = cid
            mat[i] = np.frombuffer(blob, dtype=np.float32)
            i += 1
    vm.alive[:i] = True
    vm.n = i
    vm.pos = {int(c): j for j, c in enumerate(ids[:i].tolist())}
    return vm


BLOCK = 4096  # vectors per snapshot block


def write_blocks(con: Any, x: np.ndarray) -> None:
    """Optional snapshot format: one row per BLOCK vectors (ids + matrix bytes)."""
    con.execute("CREATE TABLE IF NOT EXISTS vector_blocks(block_id INTEGER PRIMARY KEY, ids BLOB NOT NULL, vecs BLOB NOT NULL)")
    con.execute("BEGIN")
    for b, start in enumerate(range(0, len(x), BLOCK)):
        ids = np.arange(start + 1, min(start + BLOCK, len(x)) + 1, dtype=np.int64)
        con.execute("INSERT INTO vector_blocks VALUES (?, ?, ?)", (b, ids.tobytes(), x[start:start + BLOCK].tobytes()))
    con.execute("COMMIT")


def load_blocks(con: Any, dim: int) -> VectorMatrix:
    ids, mats = [], []
    for _b, id_blob, vec_blob in con.execute("SELECT block_id, ids, vecs FROM vector_blocks ORDER BY block_id"):
        ids.append(np.frombuffer(id_blob, dtype=np.int64))
        mats.append(np.frombuffer(vec_blob, dtype=np.float32).reshape(-1, dim))
    vm = VectorMatrix(dim, 0)
    vm.ids = np.concatenate(ids)
    vm.mat = np.concatenate(mats)
    vm.n = len(vm.ids)
    vm.alive = np.ones(vm.n, dtype=bool)
    return vm


def part_b(workdir: Path, n: int, dim: int, reps: int) -> Dict[str, Any]:
    key = secrets.token_bytes(32)
    path = workdir / f"matrix_{n}_{dim}.db"
    rng = np.random.default_rng(2000 + dim)
    x = unit_rows(rng, n, dim)
    con = sp.connect(path, key, with_vec=False)
    con.execute("CREATE TABLE chunk_vectors(chunk_id INTEGER PRIMARY KEY, vec BLOB NOT NULL)")
    t0 = time.perf_counter()
    con.execute("BEGIN")
    con.executemany("INSERT INTO chunk_vectors(chunk_id, vec) VALUES (?, ?)", ((i + 1, x[i].tobytes()) for i in range(n)))
    con.execute("COMMIT")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    persist_s = ms_since(t0) / 1000
    con.close()
    out: Dict[str, Any] = {"n": n, "dim": dim, "persist_bulk_s": round(persist_s, 2), "file_mib": round(path.stat().st_size / 2**20, 1)}

    # unlock: fresh connection (cold SQLCipher cache), read everything into RAM
    con = sp.connect(path, key, with_vec=False)
    t0 = time.perf_counter()
    vm = load_matrix(con, dim, n)
    out["load_at_unlock_ms"] = round(ms_since(t0), 1)
    out["matrix_mib"] = round(vm.mat[: vm.n].nbytes / 2**20, 1)
    # block snapshot variant: write once, reopen (cold cache), load
    write_blocks(con, x)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    con = sp.connect(path, key, with_vec=False)
    t0 = time.perf_counter()
    vb = load_blocks(con, dim)
    out["load_at_unlock_blocks_ms"] = round(ms_since(t0), 1)
    assert vb.n == n
    del vb
    con.execute("DROP TABLE vector_blocks")

    qs = unit_rows(np.random.default_rng(42), reps + 3, dim)
    exact = np.argsort(-(x @ qs[0]))[:10] + 1
    out["exact_top10_match"] = sorted(vm.topk(qs[0], 10).tolist()) == sorted(exact.tolist())

    def bench(mask: np.ndarray | None) -> float:
        for i in range(3):
            vm.topk(qs[i], 10, mask)
        lat = []
        for i in range(reps):
            t = time.perf_counter()
            vm.topk(qs[3 + i], 50, mask)
            lat.append(ms_since(t))
        return p50(lat)

    mask = np.random.default_rng(9).random(len(vm.ids)) < 0.3
    out["query_top50_p50_ms"] = bench(None)
    out["query_top50_masked30pct_p50_ms"] = bench(mask)
    if threadpool_limits is not None:
        with threadpool_limits(limits=1):
            out["query_top50_p50_ms_1_thread"] = bench(None)

    # updates: one 20-chunk document per transaction, persisted, then appended in RAM
    persist, mem = [], []
    next_id = n + 1
    for _ in range(20):
        rows = unit_rows(rng, 20, dim)
        ids = np.arange(next_id, next_id + 20)
        next_id += 20
        t = time.perf_counter()
        con.execute("BEGIN")
        con.executemany("INSERT INTO chunk_vectors(chunk_id, vec) VALUES (?, ?)", ((int(i), r.tobytes()) for i, r in zip(ids, rows, strict=True)))
        con.execute("COMMIT")
        persist.append(ms_since(t))
        t = time.perf_counter()
        vm.append(ids, rows)
        mem.append(ms_since(t))
    out["update_doc20_persist_p50_ms"] = p50(persist)
    out["update_doc20_in_memory_p50_ms"] = p50(mem)
    dels = []
    for cid in range(1, 21):
        t = time.perf_counter()
        con.execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (cid,))
        vm.delete(cid)
        dels.append(ms_since(t))
    out["delete_one_vector_p50_ms"] = p50(dels)
    con.close()
    sp.remove_db(path)
    return out


def part_hybrid(workdir: Path, fts_chunks: int, dim: int, reps: int) -> Dict[str, Any]:
    """FTS5 in SQLCipher + numpy matrix + RRF, with an audit-style commit on another
    connection before every query (the engine writes on almost every request)."""
    key = secrets.token_bytes(32)
    path = workdir / "hybrid.db"
    chunks, queries = sp.synth_chunks(fts_chunks, 300)
    x = unit_rows(np.random.default_rng(5), fts_chunks, dim)
    w = sp.connect(path, key, with_vec=False)
    w.execute("CREATE TABLE audit(id INTEGER PRIMARY KEY, x TEXT)")
    w.execute("CREATE TABLE chunks(id INTEGER PRIMARY KEY, doc_id INTEGER, text TEXT NOT NULL)")
    w.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2')")
    w.execute("CREATE TABLE chunk_vectors(chunk_id INTEGER PRIMARY KEY, vec BLOB NOT NULL)")
    w.execute("BEGIN")
    w.executemany("INSERT INTO chunks(id, doc_id, text) VALUES (?, ?, ?)", ((i + 1, i // 20, c) for i, c in enumerate(chunks)))
    w.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
    w.executemany("INSERT INTO chunk_vectors(chunk_id, vec) VALUES (?, ?)", ((i + 1, x[i].tobytes()) for i in range(fts_chunks)))
    w.execute("COMMIT")
    w.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    r = sp.connect(path, key, with_vec=False)
    vm = load_matrix(r, dim, fts_chunks)
    fts_sql = "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 50"

    def hybrid(term: str, qv: np.ndarray) -> List[int]:
        fts_ids = [row[0] for row in r.execute(fts_sql, (term,)).fetchall()]
        vec_ids = vm.topk(qv, 50).tolist()
        score: Dict[int, float] = {}
        for rank, cid in enumerate(fts_ids, 1):
            score[cid] = score.get(cid, 0.0) + 1.0 / (60 + rank)
        for rank, cid in enumerate(vec_ids, 1):
            score[cid] = score.get(cid, 0.0) + 1.0 / (60 + rank)
        return sorted(score, key=score.get, reverse=True)[:10]

    out: Dict[str, Any] = {"chunks": fts_chunks, "dim": dim}
    for label, term in (("two terms (AND)", queries["two terms (AND)"]), ("common term", queries["common term"])):
        for _ in range(3):
            hybrid(term, x[1])
        warm, after = [], []
        for i in range(reps):
            t = time.perf_counter()
            hybrid(term, x[i])
            warm.append(ms_since(t))
        for i in range(reps):
            w.execute("INSERT INTO audit(x) VALUES (?)", (f"event {i}",))
            t = time.perf_counter()
            hybrid(term, x[i])
            after.append(ms_since(t))
        out[label] = {"warm_p50_ms": p50(warm), "after_commit_every_query_p50_ms": p50(after), "p95_after_ms": round(sp.pct(after, 95), 3)}
    r.close()
    w.close()
    sp.remove_db(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=lambda s: [int(v) for v in s.split(",")], default=[100_000])
    ap.add_argument("--dims", type=lambda s: [int(v) for v in s.split(",")], default=[384, 1024])
    ap.add_argument("--inval-n", type=int, default=100_000)
    ap.add_argument("--fts-chunks", type=int, default=10_000)
    ap.add_argument("--reps", type=int, default=30)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    workdir = Path(tempfile.mkdtemp(prefix="vector-paths-"))
    res: Dict[str, Any] = {"environment": sp.environment(), "numpy": np.__version__}
    try:
        print("[A] invalidation", flush=True)
        res["invalidation"] = part_a(workdir, args.inval_n, 384, args.fts_chunks, args.reps)
        print(json.dumps(res["invalidation"], indent=2), flush=True)
        res["matrix"] = []
        for n in args.sizes:
            for dim in args.dims:
                print(f"[B] matrix n={n} dim={dim}", flush=True)
                row = part_b(workdir, n, dim, args.reps)
                res["matrix"].append(row)
                print(json.dumps(row, indent=2), flush=True)
        print("[C] hybrid with a commit before every query", flush=True)
        res["hybrid"] = part_hybrid(workdir, args.fts_chunks, 384, args.reps)
        print(json.dumps(res["hybrid"], indent=2), flush=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    res["environment"]["loadavg_at_end"] = os.getloadavg() if hasattr(os, "getloadavg") else None
    if args.out:
        args.out.write_text(json.dumps(res, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
