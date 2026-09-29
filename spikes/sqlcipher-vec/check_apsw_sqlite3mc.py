#!/usr/bin/env python3
"""Fallback binding check: apsw + SQLite3MultipleCiphers (`apsw-sqlite3mc`).

Shows that the fallback can (1) load sqlite-vec and use FTS5 in one
connection and (2) read and write the *same file format* as SQLCipher 4, in
both directions, so a vault created with `sqlcipher3` could be opened with
this binding (and vice versa) if we ever had to switch.

Needs both bindings importable at once (they are different module names and
each links its own SQLite statically):
    PYTHONPATH=<deps>/sqlcipher3:<deps>/apsw-sqlite3mc:<deps>/common \
        python check_apsw_sqlite3mc.py
"""

from __future__ import annotations

import json
import secrets
import sys
import tempfile
from pathlib import Path

import apsw
import sqlcipher3
import sqlite_vec


def mc_open(path: str, key: bytes) -> "apsw.Connection":
    con = apsw.Connection(path)
    # SQLite3MultipleCiphers: select the SQLCipher scheme with SQLCipher 4 defaults
    con.execute("PRAGMA cipher = 'sqlcipher'")
    con.execute("PRAGMA legacy = 4")
    con.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    return con


def sc_open(path: str, key: bytes) -> "sqlcipher3.Connection":
    con = sqlcipher3.connect(path, isolation_level=None)
    con.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    return con


def main() -> int:
    out = {"apsw": apsw.apsw_version(), "sqlite": apsw.sqlite_lib_version()}
    mem = apsw.Connection(":memory:")
    out["compile_options"] = [r[0] for r in mem.execute("PRAGMA compile_options") if any(k in r[0] for k in ("FTS5", "LOAD_EXT", "SQLITE3MC", "SECURE_DELETE"))]
    mem.enable_load_extension(True)
    mem.load_extension(sqlite_vec.loadable_path())
    out["vec_version"] = mem.execute("select vec_version()").fetchone()[0]
    mem.execute("CREATE VIRTUAL TABLE f USING fts5(body)")
    mem.execute("CREATE VIRTUAL TABLE v USING vec0(embedding float[4])")
    out["fts5_and_vec0"] = True
    vec1 = Path(apsw.__file__).parent / "sqlite_extra_binaries"
    out["bundled_vec1_extension"] = sorted(p.name for p in vec1.glob("vec1*")) if vec1.is_dir() else []

    key = secrets.token_bytes(32)
    with tempfile.TemporaryDirectory() as d:
        a, b = str(Path(d) / "made_by_sqlcipher3.db"), str(Path(d) / "made_by_sqlite3mc.db")
        con = sc_open(a, key)
        con.execute("CREATE TABLE t(x)")
        con.execute("INSERT INTO t VALUES ('written by sqlcipher3')")
        con.close()
        out["sqlite3mc_reads_sqlcipher3_file"] = mc_open(a, key).execute("SELECT x FROM t").fetchall()

        con = mc_open(b, key)
        con.execute("CREATE TABLE t(x)")
        con.execute("INSERT INTO t VALUES ('written by sqlite3mc')")
        con.close()
        out["sqlcipher3_reads_sqlite3mc_file"] = sc_open(b, key).execute("SELECT x FROM t").fetchall()
        out["sqlite3mc_file_header_hex"] = Path(b).read_bytes()[:16].hex()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
