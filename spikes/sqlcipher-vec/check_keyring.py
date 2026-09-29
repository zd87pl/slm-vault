#!/usr/bin/env python3
"""Report which `keyring` backend is usable here and whether a round trip works.

The engine wants an OS-held key-encryption key for "unlock without typing the
passphrase" (ADR 0001, "Key hierarchy").  On macOS that is the Keychain, on
Windows the Credential Manager (DPAPI-protected), on Linux the Secret Service
(GNOME Keyring / KWallet) over D-Bus.  Headless Linux, containers and many
minimal desktops have no Secret Service; this script shows what the engine
will see there, so the fallback path can be designed against real behaviour.

It never writes anything unless a real (non-fail, non-plaintext) backend is
selected, and it deletes its test entry afterwards.

Usage:
    PYTHONPATH=<deps> python check_keyring.py
"""

from __future__ import annotations

import json
import os
import secrets
import sys


def main() -> int:
    import keyring
    from keyring import backend as kb
    from keyring.errors import KeyringError, NoKeyringError

    out = {
        "keyring_version": getattr(keyring, "__version__", None) or _dist_version("keyring"),
        "env": {k: os.environ.get(k) for k in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY", "PYTHON_KEYRING_BACKEND")},
        "backends": [],
    }
    for b in sorted(kb.get_all_keyring(), key=lambda x: -_priority(x)):
        out["backends"].append({"backend": f"{type(b).__module__}.{type(b).__name__}", "priority": _priority(b)})
    # Why the Secret Service backend is not viable here (if it is not)
    try:
        from keyring.backends import SecretService

        try:
            SecretService.Keyring.priority  # noqa: B018 - property raises when not viable
            out["secretservice_viable"] = True
        except Exception as e:  # noqa: BLE001
            out["secretservice_viable"] = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001
        out["secretservice_viable"] = f"import failed: {type(e).__name__}: {e}"

    selected = keyring.get_keyring()
    out["selected"] = f"{type(selected).__module__}.{type(selected).__name__}"
    name = out["selected"].lower()
    if "fail" in name or "plaintext" in name or "null" in name:
        try:
            keyring.set_password("enclave-spike", "probe", "x")
            out["round_trip"] = "set_password unexpectedly succeeded"
        except NoKeyringError as e:
            out["round_trip"] = f"NoKeyringError: {e}"
        except KeyringError as e:
            out["round_trip"] = f"{type(e).__name__}: {e}"
    else:
        token = secrets.token_hex(16)
        try:
            keyring.set_password("enclave-spike", "probe", token)
            ok = keyring.get_password("enclave-spike", "probe") == token
            keyring.delete_password("enclave-spike", "probe")
            out["round_trip"] = "ok" if ok else "read-back mismatch"
        except Exception as e:  # noqa: BLE001
            out["round_trip"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out, indent=2))
    return 0


def _priority(b) -> float:
    try:
        return float(b.priority)
    except Exception:  # noqa: BLE001
        return float("-inf")


def _dist_version(name: str):
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    sys.exit(main())
