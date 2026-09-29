#!/usr/bin/env python3
"""Is `PRAGMA rekey` all-or-nothing if the process dies mid-way? (ADR 0001 §5.6, finding B3)

Builds an encrypted WAL-mode database, times a full rekey, then repeats the rekey
in a child process and SIGKILLs it at 15%, 40% and 70% of that time. After each
kill it reports which key opens the file and whether `PRAGMA quick_check` passes.
The two-phase DEK rotation in the ADR relies on the answer being "exactly one of
old or new, never a mix".

Usage:
    PYTHONPATH=<deps> python check_rekey_crash.py [--rows 60000] [--out rekey_crash.json]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import sqlcipher3


def pragma(key: bytes, name: str = "key") -> str:
    return f"PRAGMA {name} = \"x'{key.hex()}'\""


def child(path: str, k1: str, k2: str) -> None:
    con = sqlcipher3.connect(path, isolation_level=None)
    con.execute(pragma(bytes.fromhex(k1)))
    con.execute("SELECT count(*) FROM t").fetchone()
    print("start", flush=True)
    con.execute(pragma(bytes.fromhex(k2), "rekey"))
    print("done", flush=True)


def build(path: Path, key: bytes, rows: int) -> None:
    con = sqlcipher3.connect(str(path), isolation_level=None)
    con.execute(pragma(key))
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("CREATE TABLE t(x BLOB)")
    con.execute("BEGIN")
    con.executemany("INSERT INTO t VALUES (?)", ((os.urandom(3000),) for _ in range(rows)))
    con.execute("COMMIT")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()


def which_key(path: Path, k1: bytes, k2: bytes, rows: int) -> dict:
    out = {}
    for name, key in (("old", k1), ("new", k2)):
        con = sqlcipher3.connect(str(path))
        con.execute("PRAGMA cipher_log_level = NONE")
        con.execute(pragma(key))
        try:
            n = con.execute("SELECT count(*) FROM t").fetchone()[0]
            out[name] = {"opens": True, "rows_ok": n == rows, "quick_check": con.execute("PRAGMA quick_check").fetchone()[0]}
        except sqlcipher3.DatabaseError as e:
            out[name] = {"opens": False, "error": str(e)}
        con.close()
    return out


def run_child(path: Path, k1: bytes, k2: bytes) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, __file__, "--child", str(path), k1.hex(), k2.hex()],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(*sys.argv[2:5])
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=60_000, help="3,000-byte rows (60k is about 235 MiB)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    k1, k2 = secrets.token_bytes(32), secrets.token_bytes(32)
    res = {"rows": args.rows, "trials": []}
    with tempfile.TemporaryDirectory(prefix="rekey-crash-") as d:
        path = Path(d) / "r.db"
        build(path, k1, args.rows)
        res["file_mib"] = round(path.stat().st_size / 2**20, 1)
        p = run_child(path, k1, k2)
        assert p.stdout.readline().strip() == "start"
        t0 = time.perf_counter()
        assert p.stdout.readline().strip() == "done"
        full = time.perf_counter() - t0
        p.wait()
        res["full_rekey_s"] = round(full, 2)
        res["after_completed_rekey"] = which_key(path, k1, k2, args.rows)
        for frac in (0.15, 0.40, 0.70):
            for f in Path(d).iterdir():
                f.unlink()
            build(path, k1, args.rows)
            p = run_child(path, k1, k2)
            assert p.stdout.readline().strip() == "start"
            time.sleep(full * frac)
            p.send_signal(signal.SIGKILL)
            p.wait()
            wal = Path(str(path) + "-wal")
            res["trials"].append({
                "killed_at_fraction": frac,
                "wal_mib_at_kill": round(wal.stat().st_size / 2**20, 1) if wal.exists() else 0,
                "result": which_key(path, k1, k2, args.rows),
            })
    print(json.dumps(res, indent=2))
    if args.out:
        args.out.write_text(json.dumps(res, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
