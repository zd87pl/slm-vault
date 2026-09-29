"""Device selection for EmbeddingEngine, including ENCLAVE_EMBEDDING_DEVICE.

GitHub-hosted Apple Silicon runners report MPS as available, but allocations
on it fail, so the macOS CI job pins embeddings to the CPU through this
override. None of these tests load a model.
"""

import pytest

torch = pytest.importorskip("torch")

from advanced_vault.training.embeddings import EmbeddingEngine  # noqa: E402


def _engine(**kwargs) -> EmbeddingEngine:
    return EmbeddingEngine(use_persistent_cache=False, **kwargs)


@pytest.fixture(autouse=True)
def mps_reported(monkeypatch):
    """Have torch report MPS as available, as it does on those runners."""
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)


def test_env_override_wins_over_autodetected_mps(monkeypatch):
    monkeypatch.setenv("ENCLAVE_EMBEDDING_DEVICE", "cpu")

    assert _engine()._get_device() == "cpu"


def test_override_is_trimmed(monkeypatch):
    monkeypatch.setenv("ENCLAVE_EMBEDDING_DEVICE", " cpu\n")

    assert _engine()._get_device() == "cpu"


def test_override_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("ENCLAVE_EMBEDDING_DEVICE", "CPU")

    assert _engine()._get_device() == "cpu"


def test_explicit_device_wins_over_env_override(monkeypatch):
    monkeypatch.setenv("ENCLAVE_EMBEDDING_DEVICE", "cpu")

    assert _engine(device="mps")._get_device() == "mps"


def test_autodetect_unchanged_without_override(monkeypatch):
    monkeypatch.delenv("ENCLAVE_EMBEDDING_DEVICE", raising=False)

    assert _engine()._get_device() == "mps"


def test_blank_override_falls_back_to_autodetect(monkeypatch):
    monkeypatch.setenv("ENCLAVE_EMBEDDING_DEVICE", "   ")

    assert _engine()._get_device() == "mps"
