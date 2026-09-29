"""Shared test fixtures.

Every test runs with HOME (and USERPROFILE) pointed at a fresh temporary
directory, so no test reads or rewrites the developer's real ~/.vault or
~/.enclave (for example the policy migration upgrading an old
~/.enclave/policies.toml). The Hugging Face cache is pinned to its real
location first, so already-downloaded models are still found.
"""

import os
from pathlib import Path

import pytest

_REAL_HF_HOME = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HF_HOME", _REAL_HF_HOME)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
