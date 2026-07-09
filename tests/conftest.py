"""Collection guards for legacy cloud-training tests.

These tests exercise the legacy `src/` cloud-training stack (RunPod / DoRA),
which needs torch, safetensors, zstandard, and pycryptodome. None of those are
part of the local-first install, so skip collection when they are missing
instead of breaking `pytest` for everyone else.
"""

import importlib.util


def _missing(*modules: str) -> list:
    return [m for m in modules if importlib.util.find_spec(m) is None]


collect_ignore = []

# Every file below imports the `src` package, whose __init__ pulls in the
# whole legacy stack — so any one missing module breaks them all.
if _missing("torch", "safetensors", "zstandard", "Crypto"):
    collect_ignore += [
        "test_adapter_cache.py",
        "test_dora_weights.py",
        "test_encryption.py",
        "test_ephemeral_inference.py",
        "test_error_handling.py",
        "test_integration.py",
        "test_performance.py",
        "test_rp_handler_user_isolation.py",
        "test_wdva_crypto.py",
    ]
