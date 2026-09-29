#!/usr/bin/env python3
"""Argon2id timing grid + unlock-time calibration for ADR 0001.

Measures argon2-cffi's Argon2id (RFC 9106, version 0x13) raw-hash time for a
grid of memory / time / parallelism settings, then runs the calibration the
engine will use at vault creation (see ADR 0001, "Key hierarchy"):

    1. parallelism = min(4, logical CPUs); start at m = 256 MiB, t = 2
    2. memory first: double m (256 -> 512 -> 1024 MiB; cap 1 GiB with >= 16 GB
       RAM, 512 MiB with >= 8 GB, else 256 MiB) while the derive stays <= 1.0 s
    3. then time: raise t until the derive takes >= 0.5 s
    4. a machine too slow for 256 MiB / t=2 within 1.0 s halves m (floor 64 MiB,
       and then t >= 3: RFC 9106's second recommended option)

The chosen (m, t, p) are stored next to the wrapped key, so later unlocks
reuse them; they are never re-derived per unlock.

Usage:
    PYTHONPATH=<deps> python bench_argon2.py [--reps 3] [--quick] [--out argon2.json]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import statistics
import sys
import time
from typing import Any, Dict, List, Tuple

from argon2.low_level import Type, hash_secret_raw

MiB = 1024  # argon2 memory_cost is in KiB


def derive_ms(m_mib: int, t: int, p: int, reps: int) -> Tuple[float, List[float]]:
    pw = b"correct horse battery staple"
    salt = secrets.token_bytes(16)
    runs = []
    for _ in range(reps):
        t0 = time.perf_counter()
        hash_secret_raw(pw, salt, time_cost=t, memory_cost=m_mib * MiB, parallelism=p, hash_len=32, type=Type.ID)
        runs.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(runs), runs


def total_ram_gib() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (ValueError, OSError, AttributeError):
        return 8.0


def calibrate(reps: int, low_ms: float = 500.0, high_ms: float = 1000.0) -> Dict[str, Any]:
    """Memory first (it is what makes GPU/ASIC guessing expensive), then time.

    m grows 256 -> 512 -> 1024 MiB (capped by RAM) while t=2 stays <= high_ms;
    if the largest affordable m is still < low_ms, t grows until >= low_ms.
    Machines too slow for 256 MiB at t=2 within high_ms fall back to 64-128 MiB
    with t >= 3 (RFC 9106's second recommended option is m=64 MiB, t=3, p=4).
    """
    ram = total_ram_gib()
    cap = 1024 if ram >= 15 else (512 if ram >= 7 else 256)  # 16 GB machines report ~15.x GiB
    p = min(4, os.cpu_count() or 1)
    trace: List[Dict[str, Any]] = []

    def run(m: int, t: int) -> float:
        ms, _ = derive_ms(m, t, p, reps)
        trace.append({"m_mib": m, "t": t, "p": p, "median_ms": round(ms, 1)})
        return ms

    m, t = 256, 2
    ms = run(m, t)
    while ms > high_ms and m > 64:  # slow machine: shrink memory
        m //= 2
        ms = run(m, t)
    while ms < low_ms and m * 2 <= cap:  # grow memory first
        nxt = run(m * 2, t)
        if nxt > high_ms:
            break
        m, ms = m * 2, nxt
    if m < 256 and t < 3:  # floor: RFC 9106's second recommended option (64 MiB, t=3)
        t = 3
        ms = run(m, t)
    while ms < low_ms and t < 10:  # then time
        t += 1
        ms = run(m, t)
    return {"chosen": {"m_mib": m, "t": t, "p": p, "median_ms": round(ms, 1)}, "trace": trace,
            "ram_gib": round(ram, 1), "memory_cap_mib": cap}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--quick", action="store_true", help="smaller grid (m in 64,256; t in 2,3; p in 1,4)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--calibrate-only", action="store_true")
    args = ap.parse_args()
    if args.calibrate_only:
        print(json.dumps(calibrate(args.reps), indent=2))
        return 0

    mems = [64, 256] if args.quick else [64, 256, 512]
    times = [2, 3] if args.quick else [2, 3, 4]
    pars = [1, 4] if args.quick else [1, 2, 4]
    from importlib.metadata import version

    res: Dict[str, Any] = {
        "env": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "argon2_cffi": version("argon2-cffi"),
            "loadavg_at_start": os.getloadavg() if hasattr(os, "getloadavg") else None,
        },
        "owasp_minimum_19mib_t2_p1_ms": round(derive_ms(19, 2, 1, args.reps)[0], 1),
        "grid": [],
    }
    for m in mems:
        for t in times:
            for p in pars:
                ms, runs = derive_ms(m, t, p, args.reps)
                row = {"m_mib": m, "t": t, "p": p, "median_ms": round(ms, 1), "runs_ms": [round(r, 1) for r in runs]}
                res["grid"].append(row)
                print(f"m={m:>4} MiB t={t} p={p}: {ms:8.1f} ms", flush=True)
    res["calibration"] = calibrate(args.reps)
    res["env"]["loadavg_at_end"] = os.getloadavg() if hasattr(os, "getloadavg") else None

    print("\n| m (MiB) | t | p=1 ms | p=2 ms | p=4 ms |")
    print("|---|---|---|---|---|")
    for m in mems:
        for t in times:
            cells = []
            for p in (1, 2, 4):
                hit = [r for r in res["grid"] if r["m_mib"] == m and r["t"] == t and r["p"] == p]
                cells.append(f"{hit[0]['median_ms']}" if hit else "-")
            print(f"| {m} | {t} | " + " | ".join(cells) + " |")
    print(f"\nOWASP floor (19 MiB, t=2, p=1): {res['owasp_minimum_19mib_t2_p1_ms']} ms")
    print(f"calibration: {res['calibration']['chosen']} (RAM {res['calibration']['ram_gib']} GiB)")
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(res, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
