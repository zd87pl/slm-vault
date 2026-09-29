#!/usr/bin/env python3
"""Does a deleted `chunk_vectors` BLOB row leave bytes behind? (ADR 0001 §4.3)

Adapted from the round-2 design review's blob_residue.py. For 384-, 512- and
1024-dimension float32 rows (1,536 / 2,048 / 4,096 bytes; the last overflows a
4 KiB page), it inserts a marker vector among 300 random rows, deletes it with
`secure_delete = ON`, checkpoints, then decrypts every page with the raw key and
searches for the first and last 64 bytes of the marker.

Usage:
    PYTHONPATH=<deps> python check_blob_residue.py
"""

from __future__ import annotations

import secrets
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spike_sqlcipher_vec as sp  # noqa: E402


def main() -> int:
    for dim in (384, 512, 1024):
        key = secrets.token_bytes(32)
        with tempfile.TemporaryDirectory(prefix="blob-residue-") as d:
            path = Path(d) / "b.db"
            con = sp.connect(path, key, with_vec=False)
            con.execute("PRAGMA secure_delete = ON")
            con.execute("CREATE TABLE chunk_vectors(chunk_id INTEGER PRIMARY KEY, vec BLOB NOT NULL)")
            rng = np.random.default_rng(1)
            con.execute("BEGIN")
            for i in range(1, 301):
                con.execute("INSERT INTO chunk_vectors VALUES (?, ?)", (i, rng.standard_normal(dim).astype(np.float32).tobytes()))
            con.execute("COMMIT")
            marker = np.full(dim, 1234.5678, dtype=np.float32).tobytes()
            con.execute("INSERT INTO chunk_vectors VALUES (?, ?)", (10_000, marker))
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before = any(marker[:64] in p for _, p in sp.iter_decrypted_pages(path, key))
            con.execute("DELETE FROM chunk_vectors WHERE chunk_id = 10000")
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.close()
            head = any(marker[:64] in p for _, p in sp.iter_decrypted_pages(path, key))
            tail = any(marker[-64:] in p for _, p in sp.iter_decrypted_pages(path, key))
        print(f"dim={dim} ({dim * 4} B): marker before delete={before}; after delete: head={head}, tail={tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
