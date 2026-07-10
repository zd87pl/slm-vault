"""Collection guards for backend tests.

The self-hosted sync backend is optional (see the `backend` extra in
pyproject.toml). Skip its tests when the server dependencies are absent so a
plain `pytest` run stays green on a local-only install.
"""

import importlib.util


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


collect_ignore = []
collect_ignore_glob = []

if not _available("fastapi"):
    collect_ignore_glob = ["test_*.py", "langchain/test_*.py"]
elif not _available("supabase"):
    collect_ignore_glob = ["langchain/test_*.py"]
