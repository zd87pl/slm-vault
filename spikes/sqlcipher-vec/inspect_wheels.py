#!/usr/bin/env python3
"""Inspect native binaries inside platform wheels without running them.

For every .so/.dylib/.pyd/.dll inside the given wheels this prints:

* Mach-O (macOS): architectures, linked dylibs (LC_LOAD_DYLIB and friends),
  whether an LC_CODE_SIGNATURE is present and, if so, whether it is ad-hoc /
  linker-signed and which Team ID it carries.  This answers "will the
  hardened runtime load it after the app is re-signed?" and "does it link the
  system libcrypto / libsqlite3?".
* PE (Windows): the DLL names the binary references (a string scan, good
  enough to spot an external libcrypto/sqlite3 dependency).
* ELF (Linux): the shared-library names the binary references (string scan).

Usage:
    python inspect_wheels.py WHEEL [WHEEL ...]

Download wheels for another platform with, e.g.:
    pip download --no-deps --only-binary=:all: --python-version 3.11 \
        --platform macosx_11_0_arm64 -d wheels/ sqlcipher3==0.6.2 sqlite-vec==0.1.9
"""

from __future__ import annotations

import re
import struct
import sys
import zipfile

LC_CODE_SIGNATURE = 0x1D
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_RPATH = 0x8000001C

CPU_NAMES = {0x01000007: "x86_64", 0x0100000C: "arm64", 7: "i386", 12: "arm"}
BINARY_SUFFIXES = (".so", ".dylib", ".pyd", ".dll")


def _code_signature(blob: bytes) -> dict:
    """Decode the parts of an embedded code signature we care about."""
    info = {"adhoc": None, "linker_signed": None, "team_id": None, "cms_signed": False}
    magic, _length, count = struct.unpack_from(">III", blob, 0)
    if magic != 0xFADE0CC0:  # CSMAGIC_EMBEDDED_SIGNATURE
        info["error"] = f"unexpected superblob magic {magic:#x}"
        return info
    for i in range(count):
        _slot, offset = struct.unpack_from(">II", blob, 12 + 8 * i)
        bmagic, blen = struct.unpack_from(">II", blob, offset)
        if bmagic == 0xFADE0C02:  # CodeDirectory
            version, flags = struct.unpack_from(">II", blob, offset + 8)
            ident_off = struct.unpack_from(">I", blob, offset + 20)[0]
            ident = blob[offset + ident_off:].split(b"\0", 1)[0].decode(errors="replace")
            info["identifier"] = ident
            info["adhoc"] = bool(flags & 0x2)
            info["linker_signed"] = bool(flags & 0x20000)
            if version >= 0x20200:
                team_off = struct.unpack_from(">I", blob, offset + 48)[0]
                if team_off:
                    info["team_id"] = blob[offset + team_off:].split(b"\0", 1)[0].decode()
        elif bmagic == 0xFADE0B01:  # CMS signature wrapper
            info["cms_signed"] = blen > 8
    return info


def _macho_slice(data: bytes, base: int) -> dict:
    magic = struct.unpack_from("<I", data, base)[0]
    if magic != 0xFEEDFACF:
        return {"error": f"not a 64-bit Mach-O slice (magic {magic:#x})"}
    cputype, _sub, _ftype, ncmds, _size, _flags = struct.unpack_from("<iiIIII", data, base + 4)
    out = {"arch": CPU_NAMES.get(cputype, hex(cputype)), "dylibs": [], "rpaths": [], "signature": None}
    off = base + 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB):
            name_off = struct.unpack_from("<I", data, off + 8)[0]
            out["dylibs"].append(data[off + name_off: off + cmdsize].split(b"\0", 1)[0].decode())
        elif cmd == LC_RPATH:
            name_off = struct.unpack_from("<I", data, off + 8)[0]
            out["rpaths"].append(data[off + name_off: off + cmdsize].split(b"\0", 1)[0].decode())
        elif cmd == LC_CODE_SIGNATURE:
            dataoff, datasize = struct.unpack_from("<II", data, off + 8)
            out["signature"] = _code_signature(data[base + dataoff: base + dataoff + datasize])
        off += cmdsize
    return out


def inspect_macho(data: bytes) -> list[dict]:
    if data[:4] == b"\xca\xfe\xba\xbe":  # universal (fat) binary, big-endian header
        nfat = struct.unpack_from(">I", data, 4)[0]
        slices = []
        for i in range(nfat):
            _cpu, _sub, offset, _size, _align = struct.unpack_from(">iiIII", data, 8 + 20 * i)
            slices.append(_macho_slice(data, offset))
        return slices
    return [_macho_slice(data, 0)]


def referenced_names(data: bytes, pattern: bytes) -> list[str]:
    return sorted({m.decode(errors="replace") for m in re.findall(pattern, data)}, key=str.lower)


def inspect_binary(name: str, data: bytes) -> None:
    print(f"  {name} ({len(data):,} bytes)")
    if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        for sl in inspect_macho(data):
            if "error" in sl:
                print(f"    {sl['error']}")
                continue
            print(f"    arch={sl['arch']}")
            print(f"    linked dylibs: {', '.join(sl['dylibs']) or '(none)'}")
            if sl["rpaths"]:
                print(f"    rpaths: {', '.join(sl['rpaths'])}")
            sig = sl["signature"]
            if sig is None:
                print("    code signature: NONE")
            else:
                print(
                    "    code signature: "
                    f"adhoc={sig.get('adhoc')} linker_signed={sig.get('linker_signed')} "
                    f"team_id={sig.get('team_id')!r} cms_signed={sig.get('cms_signed')} "
                    f"identifier={sig.get('identifier')!r}"
                )
    elif data[:2] == b"MZ":
        dlls = referenced_names(data, rb"[A-Za-z0-9_.\-]+\.(?:dll|DLL)")
        print(f"    referenced DLLs: {', '.join(dlls)}")
    elif data[:4] == b"\x7fELF":
        libs = referenced_names(data, rb"lib[A-Za-z0-9_.+\-]+\.so(?:\.[0-9]+)*")
        print(f"    referenced shared libs: {', '.join(libs)}")
    else:
        print("    unknown binary format")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for wheel in argv:
        print(f"== {wheel}")
        with zipfile.ZipFile(wheel) as zf:
            for info in zf.infolist():
                if info.filename.endswith(BINARY_SUFFIXES):
                    # apsw ships ~40 optional extension binaries; show only the core ones
                    if "sqlite_extra_binaries/" in info.filename and "vec1" not in info.filename:
                        continue
                    inspect_binary(info.filename, zf.read(info))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
