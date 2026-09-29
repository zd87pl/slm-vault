"""
Regression tests: already-downloaded models load without contacting Hugging Face.

Loading a model by repo id used to query the Hugging Face Hub on every load
(about 30 HTTP requests for the embedder), even with every file on disk, and
stalled or failed offline. These tests pin the offline-first behaviour of
advanced_vault.model_cache and the loaders routed through it: the embedder
(index and search), the local LLM (torch, MLX, MLX DoRA) and SmolDocling OCR
(PDF import).
"""

import importlib
import json
import os
import socket
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from advanced_vault import model_cache
from advanced_vault.model_cache import (
    ModelNotDownloadedError,
    find_cached_snapshot,
    is_complete_snapshot,
    load_offline_first,
)

REPO_ID = "example-org/example-model"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


class NetworkForbidden(Exception):
    """Raised by the socket guard. Not an OSError, so HTTP clients do not retry it."""


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def no_network(monkeypatch):
    """Fail and record every outgoing socket connection."""
    attempts = []

    def guard(sock, address):
        attempts.append(address)
        raise NetworkForbidden(f"network access attempted: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    return attempts


@pytest.fixture
def online(monkeypatch):
    """Network access allowed: the situation in which the bug made requests."""
    hub_constants = pytest.importorskip("huggingface_hub.constants")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.setattr(hub_constants, "HF_HUB_OFFLINE", False)


@pytest.fixture
def offline(monkeypatch):
    """The user has set HF_HUB_OFFLINE=1."""
    hub_constants = pytest.importorskip("huggingface_hub.constants")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(hub_constants, "HF_HUB_OFFLINE", True)


@pytest.fixture
def hub(monkeypatch):
    """Mock the huggingface_hub functions the loaders could reach."""
    huggingface_hub = pytest.importorskip("huggingface_hub")
    mocks = MagicMock()
    mocks.try_to_load_from_cache.return_value = None
    mocks.snapshot_download.side_effect = AssertionError("snapshot_download must not be called")
    mocks.hf_hub_download.side_effect = AssertionError("hf_hub_download must not be called")
    for name in ("try_to_load_from_cache", "snapshot_download", "hf_hub_download"):
        monkeypatch.setattr(huggingface_hub, name, getattr(mocks, name))
    return mocks


def write_model(directory: Path, weights=("model.safetensors",), index=None) -> Path:
    """Write a minimal model folder: config, tokenizer and the given weight files."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text("{}")
    (directory / "tokenizer.json").write_text("{}")
    for name in weights:
        (directory / name).write_bytes(b"weights")
    if index is not None:
        weight_map = {f"layer{i}.weight": shard for i, shard in enumerate(index)}
        (directory / "model.safetensors.index.json").write_text(json.dumps({"weight_map": weight_map}))
    return directory


def write_hf_cache(cache_dir: Path, repo_id: str, **model_kwargs) -> Path:
    """Lay a model out the way huggingface_hub caches it; return the snapshot dir."""
    repo_dir = Path(cache_dir) / f"models--{repo_id.replace('/', '--')}"
    (repo_dir / "refs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "refs" / "main").write_text(COMMIT)
    return write_model(repo_dir / "snapshots" / COMMIT, **model_kwargs)


def link_hf_cache(source_snapshot: Path, cache_dir: Path, repo_id: str, keep=lambda name: True) -> Path:
    """Lay out a real cached model in another cache, as symlinks to its files."""
    source_repo = source_snapshot.parent.parent
    commit = source_snapshot.name
    repo_dir = Path(cache_dir) / f"models--{repo_id.replace('/', '--')}"
    (repo_dir / "refs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "refs" / "main").write_text(commit)
    for item in source_snapshot.rglob("*"):
        relative = item.relative_to(source_snapshot)
        if item.is_dir() or not keep(relative.parts[0]):
            continue
        target = repo_dir / "snapshots" / commit / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(item.resolve())
    for marker in (source_repo / ".no_exist").rglob("*"):  # files known not to exist
        if marker.is_file():
            target = repo_dir / ".no_exist" / marker.relative_to(source_repo / ".no_exist")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
    return repo_dir / "snapshots" / commit


@pytest.fixture
def hub_cache(monkeypatch, tmp_path):
    """Point huggingface_hub's default cache (HF_HUB_CACHE) at an empty directory."""
    hub_constants = pytest.importorskip("huggingface_hub.constants")
    cache = tmp_path / "hf-hub-cache"
    cache.mkdir()
    monkeypatch.setattr(hub_constants, "HF_HUB_CACHE", str(cache))
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)
    return cache


@pytest.fixture
def local_inference(monkeypatch, tmp_path):
    """Import local_inference with its model store in tmp_path."""
    # Fix huggingface_hub's cache location from the real environment first:
    # importing local_inference sets HF cache env vars (restored afterwards).
    pytest.importorskip("huggingface_hub.constants")
    monkeypatch.setenv("ENCLAVE_MODEL_CACHE_DIR", str(tmp_path / "enclave-models"))
    for name in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "HF_HUB_ENABLE_HF_TRANSFER"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
        if not os.environ[name]:
            monkeypatch.delenv(name)
    return importlib.import_module("advanced_vault.gui.local_inference")


# ---------------------------------------------------------------------------
# The shared helper
# ---------------------------------------------------------------------------


def test_cached_model_loads_from_local_snapshot_without_network(tmp_path, hub, online, no_network):
    snapshot = write_model(tmp_path / "snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    load = MagicMock(return_value="model")

    assert load_offline_first(REPO_ID, load) == "model"

    load.assert_called_once_with(str(snapshot))
    hub.try_to_load_from_cache.assert_called_once_with(REPO_ID, "config.json", cache_dir=None)
    hub.snapshot_download.assert_not_called()
    hub.hf_hub_download.assert_not_called()
    assert no_network == []


def test_missing_model_takes_the_download_path_exactly_once(hub, online):
    load = MagicMock(return_value="model")

    assert load_offline_first(REPO_ID, load) == "model"

    load.assert_called_once_with(REPO_ID)
    hub.snapshot_download.assert_not_called()  # the loader's own download is the only one


def test_offline_missing_model_raises_clear_error_without_network(hub, offline, no_network):
    load = MagicMock()

    with pytest.raises(ModelNotDownloadedError, match="HF_HUB_OFFLINE"):
        load_offline_first(REPO_ID, load)

    load.assert_not_called()
    hub.snapshot_download.assert_not_called()
    assert no_network == []


@pytest.mark.parametrize("mode", ["online", "offline"])
def test_library_local_lookup_is_used_before_any_download(request, hub, no_network, mode):
    """A model the library finds locally (outside one snapshot) loads with no network."""
    request.getfixturevalue(mode)
    load = MagicMock(side_effect=AssertionError("must not download"))
    load_local = MagicMock(return_value="model")

    assert load_offline_first(REPO_ID, load, load_local=load_local) == "model"

    load_local.assert_called_once_with()
    load.assert_not_called()
    assert no_network == []


def test_library_local_lookup_miss_downloads_once(hub, online):
    load = MagicMock(return_value="model")
    load_local = MagicMock(side_effect=OSError("not cached"))

    assert load_offline_first(REPO_ID, load, load_local=load_local) == "model"

    load_local.assert_called_once_with()
    load.assert_called_once_with(REPO_ID)


def test_offline_library_local_lookup_miss_raises_clear_error(hub, offline, no_network):
    load = MagicMock()
    missing = OSError("couldn't find them in the cached files")

    with pytest.raises(ModelNotDownloadedError, match="offline mode") as excinfo:
        load_offline_first(REPO_ID, load, load_local=MagicMock(side_effect=missing))

    assert excinfo.value.__cause__ is missing
    load.assert_not_called()
    assert no_network == []


def test_offline_local_copy_that_fails_to_load_reports_the_real_error(hub, offline):
    corrupt = ValueError("corrupt weights")

    with pytest.raises(ValueError, match="corrupt weights"):
        load_offline_first(REPO_ID, MagicMock(), load_local=MagicMock(side_effect=corrupt))


def test_missing_dependency_is_not_retried_as_a_download(tmp_path, hub, online):
    snapshot = write_model(tmp_path / "snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    load = MagicMock(side_effect=ImportError("accelerate is required"))

    with pytest.raises(ImportError):
        load_offline_first(REPO_ID, load)

    load.assert_called_once_with(str(snapshot))  # no second load by repo id


def test_missing_model_with_downloads_disabled_raises(hub, online):
    load = MagicMock()

    with pytest.raises(ModelNotDownloadedError, match="not been downloaded"):
        load_offline_first(REPO_ID, load, allow_download=False)

    load.assert_not_called()


def test_partial_snapshot_falls_back_to_download(tmp_path, hub, online):
    snapshot = write_model(
        tmp_path / "snapshot",
        weights=("model-00001-of-00002.safetensors",),
        index=("model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"),
    )
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    load = MagicMock(return_value="model")

    load_offline_first(REPO_ID, load)

    load.assert_called_once_with(REPO_ID)


def test_cached_copy_that_fails_to_load_falls_back_to_download(tmp_path, hub, online):
    snapshot = write_model(tmp_path / "snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    load = MagicMock(side_effect=[OSError("corrupt tokenizer"), "model"])

    assert load_offline_first(REPO_ID, load) == "model"

    assert [c.args for c in load.call_args_list] == [(str(snapshot),), (REPO_ID,)]


def test_cached_copy_that_fails_to_load_is_not_retried_offline(tmp_path, hub, offline):
    snapshot = write_model(tmp_path / "snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    load = MagicMock(side_effect=OSError("corrupt tokenizer"))

    with pytest.raises(OSError, match="corrupt tokenizer"):
        load_offline_first(REPO_ID, load)

    load.assert_called_once_with(str(snapshot))


@pytest.mark.parametrize(
    "files, index, expected",
    [
        ((), None, False),                                       # no weights
        (("model.safetensors",), None, True),
        (("pytorch_model.bin",), None, True),
        (("a.safetensors", "b.safetensors"), ("a.safetensors", "b.safetensors"), True),
        (("a.safetensors",), ("a.safetensors", "b.safetensors"), False),  # missing shard
    ],
)
def test_is_complete_snapshot(tmp_path, files, index, expected):
    assert is_complete_snapshot(write_model(tmp_path / "m", weights=files, index=index)) is expected


def test_is_complete_snapshot_requires_config_and_readable_index(tmp_path):
    no_config = write_model(tmp_path / "no-config")
    (no_config / "config.json").unlink()
    assert not is_complete_snapshot(no_config)

    bad_index = write_model(tmp_path / "bad-index")
    (bad_index / "model.safetensors.index.json").write_text("not json")
    assert not is_complete_snapshot(bad_index)


def test_find_cached_snapshot_reads_the_hf_cache_layout(tmp_path):
    pytest.importorskip("huggingface_hub")
    snapshot = write_hf_cache(tmp_path, REPO_ID)

    assert find_cached_snapshot(REPO_ID, cache_dir=tmp_path) == snapshot
    assert find_cached_snapshot("example-org/not-downloaded", cache_dir=tmp_path) is None
    assert find_cached_snapshot(str(tmp_path / "no" / "such" / "dir"), cache_dir=tmp_path) is None
    # A local model directory is used as-is; an empty id is not the current directory.
    assert find_cached_snapshot(str(snapshot)) == snapshot
    assert find_cached_snapshot("") is None


def test_hf_offline_enabled_follows_the_environment(monkeypatch, online):
    assert not model_cache.hf_offline_enabled()
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    assert model_cache.hf_offline_enabled()
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "true")
    assert model_cache.hf_offline_enabled()


# ---------------------------------------------------------------------------
# Embeddings (index and query path)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_sentence_transformer(monkeypatch):
    """SentenceTransformer stand-in; like the real one, local_files_only fails when nothing is cached."""
    from advanced_vault.training import embeddings

    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 384

    def construct(source, **kwargs):
        if kwargs.get("local_files_only"):
            raise OSError(f"{source} is not in the local cache")
        return model

    cls = MagicMock(side_effect=construct)
    monkeypatch.setattr(embeddings, "SentenceTransformer", cls)
    return cls


def test_embedding_engine_loads_cached_model_from_local_path(tmp_path, fake_sentence_transformer, online, no_network):
    from advanced_vault.training.embeddings import EmbeddingEngine

    snapshot = write_hf_cache(tmp_path, REPO_ID)
    engine = EmbeddingEngine(REPO_ID, cache_dir=tmp_path, device="cpu", use_persistent_cache=False)

    assert engine.dimension == 384
    fake_sentence_transformer.assert_called_once_with(str(snapshot), device="cpu", cache_folder=str(tmp_path))
    assert no_network == []


def test_embedding_engine_downloads_a_missing_model_by_id(tmp_path, fake_sentence_transformer, online):
    from advanced_vault.training.embeddings import EmbeddingEngine

    engine = EmbeddingEngine(REPO_ID, cache_dir=tmp_path, device="cpu", use_persistent_cache=False)
    assert engine.dimension == 384

    # A local-only lookup first, then exactly one download by repo id.
    assert fake_sentence_transformer.call_args_list == [
        call(REPO_ID, device="cpu", cache_folder=str(tmp_path), local_files_only=True),
        call(REPO_ID, device="cpu", cache_folder=str(tmp_path)),
    ]


def test_embedding_engine_offline_missing_model_raises(tmp_path, fake_sentence_transformer, offline, no_network):
    from advanced_vault.training.embeddings import EmbeddingEngine

    engine = EmbeddingEngine(REPO_ID, cache_dir=tmp_path, device="cpu", use_persistent_cache=False)
    with pytest.raises(ModelNotDownloadedError):
        _ = engine.dimension

    # Only the local-only lookup ran; nothing tried to download.
    fake_sentence_transformer.assert_called_once_with(
        REPO_ID, device="cpu", cache_folder=str(tmp_path), local_files_only=True
    )
    assert no_network == []


@pytest.mark.parametrize("mode", ["online", "offline"])
def test_embedding_engine_loads_a_model_split_across_caches(request, hub_cache, fake_sentence_transformer, no_network, mode):
    """
    transformers 4.x keeps the weights under TRANSFORMERS_CACHE (set by the GUI)
    and sentence-transformers keeps its own files in HF_HUB_CACHE, so no single
    snapshot is complete. The library's own local-only load still finds both.
    """
    request.getfixturevalue(mode)
    from advanced_vault.training import embeddings

    snapshot = write_hf_cache(hub_cache, REPO_ID, weights=())
    (snapshot / "config.json").unlink()
    (snapshot / "modules.json").write_text("[]")
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 384
    fake_sentence_transformer.side_effect = (
        lambda source, **kwargs: model if kwargs.get("local_files_only") else pytest.fail("must not download")
    )

    engine = embeddings.EmbeddingEngine(REPO_ID, device="cpu", use_persistent_cache=False)
    assert engine.dimension == 384

    fake_sentence_transformer.assert_called_once_with(REPO_ID, device="cpu", local_files_only=True)
    assert no_network == []


def test_embedding_engine_looks_in_sentence_transformers_home(monkeypatch, tmp_path, hub_cache, fake_sentence_transformer, online, no_network):
    st_home = tmp_path / "st-home"
    snapshot = write_hf_cache(st_home, REPO_ID)
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(st_home))
    from advanced_vault.training.embeddings import EmbeddingEngine

    engine = EmbeddingEngine(REPO_ID, device="cpu", use_persistent_cache=False)
    assert engine.dimension == 384

    fake_sentence_transformer.assert_called_once_with(str(snapshot), device="cpu")
    assert no_network == []


def test_real_e5_embedder_loads_from_cache_without_any_http(online, no_network):
    """The default embedder, cached under HF_HOME, loads with sockets disabled."""
    pytest.importorskip("sentence_transformers")
    from advanced_vault.training.embeddings import DEFAULT_MODEL, EmbeddingEngine

    if find_cached_snapshot(DEFAULT_MODEL) is None:
        pytest.skip(f"{DEFAULT_MODEL} is not in the local Hugging Face cache")

    engine = EmbeddingEngine(device="cpu", use_persistent_cache=False)
    embedding = engine.embed_query("When does the boiler warranty expire?")

    assert embedding.shape == (384,)
    assert no_network == []


@pytest.fixture
def real_e5_snapshot():
    pytest.importorskip("sentence_transformers")
    from advanced_vault.training.embeddings import DEFAULT_MODEL

    snapshot = find_cached_snapshot(DEFAULT_MODEL)
    if snapshot is None:
        pytest.skip(f"{DEFAULT_MODEL} is not in the local Hugging Face cache")
    return snapshot


# sentence-transformers' own files; transformers fetches everything else.
SENTENCE_TRANSFORMERS_FILES = {"modules.json", "sentence_bert_config.json", "README.md", "1_Pooling", "2_Normalize"}


@pytest.mark.parametrize("mode", ["online", "offline"])
def test_real_e5_split_across_transformers_cache_loads_without_any_http(
    request, monkeypatch, tmp_path, real_e5_snapshot, hub_cache, no_network, mode
):
    """
    With transformers 4.x, importing the GUI's local_inference sets
    TRANSFORMERS_CACHE, so e5's weights land there while sentence-transformers'
    own files land in HF_HUB_CACHE. Such a model must load with no HTTP.
    """
    request.getfixturevalue(mode)
    transformers_hub = pytest.importorskip("transformers.utils.hub")
    if not hasattr(transformers_hub, "TRANSFORMERS_CACHE"):
        pytest.skip("transformers 5+ ignores TRANSFORMERS_CACHE, so the split cannot happen")
    from advanced_vault.training.embeddings import DEFAULT_MODEL, EmbeddingEngine

    transformers_cache = tmp_path / "transformers-cache"
    link_hf_cache(real_e5_snapshot, hub_cache, DEFAULT_MODEL, keep=lambda name: name in SENTENCE_TRANSFORMERS_FILES)
    link_hf_cache(real_e5_snapshot, transformers_cache, DEFAULT_MODEL, keep=lambda name: name not in SENTENCE_TRANSFORMERS_FILES)
    monkeypatch.setattr(transformers_hub, "TRANSFORMERS_CACHE", str(transformers_cache))
    assert find_cached_snapshot(DEFAULT_MODEL) is None  # no single complete snapshot

    engine = EmbeddingEngine(device="cpu", use_persistent_cache=False)
    embedding = engine.embed_query("When does the boiler warranty expire?")

    assert embedding.shape == (384,)
    assert [type(module).__name__ for module in engine._model] == ["Transformer", "Pooling", "Normalize"]
    assert no_network == []


def test_real_e5_in_sentence_transformers_home_loads_without_any_http(
    monkeypatch, tmp_path, real_e5_snapshot, hub_cache, online, no_network
):
    from advanced_vault.training.embeddings import DEFAULT_MODEL, EmbeddingEngine

    st_home = tmp_path / "st-home"
    link_hf_cache(real_e5_snapshot, st_home, DEFAULT_MODEL)
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(st_home))

    engine = EmbeddingEngine(device="cpu", use_persistent_cache=False)

    assert engine.embed_query("When does the boiler warranty expire?").shape == (384,)
    assert no_network == []


# ---------------------------------------------------------------------------
# Local LLM (chat path): torch fallback, MLX, MLX DoRA
# ---------------------------------------------------------------------------


def test_torch_fallback_loads_cached_model_from_local_path(monkeypatch, tmp_path, local_inference, online, no_network):
    if not local_inference.TORCH_AVAILABLE:
        pytest.skip("torch/transformers not installed")
    tokenizer_cls, model_cls = MagicMock(), MagicMock()
    monkeypatch.setattr(local_inference, "AutoTokenizer", tokenizer_cls)
    monkeypatch.setattr(local_inference, "AutoModelForCausalLM", model_cls)
    engine = local_inference.LocalInferenceEngine(cache_dir=str(tmp_path / "engine"))
    engine.backend = "torch"
    snapshot = write_hf_cache(engine.shared_model_root / "torch", engine.MODEL_NAME)

    assert engine.load_model() is True

    assert tokenizer_cls.from_pretrained.call_args.args == (str(snapshot),)
    assert model_cls.from_pretrained.call_args.args == (str(snapshot),)
    assert no_network == []


def test_real_transformers_model_loads_from_cache_without_any_http(tmp_path, local_inference, online, no_network):
    """End to end through transformers: a tiny model cached under the default id."""
    if not local_inference.TORCH_AVAILABLE:
        pytest.skip("torch/transformers not installed")
    e5_snapshot = find_cached_snapshot("intfloat/e5-small-v2")
    if e5_snapshot is None:
        pytest.skip("no cached tokenizer to build the test model from")
    from transformers import LlamaConfig, LlamaForCausalLM

    engine = local_inference.LocalInferenceEngine(cache_dir=str(tmp_path / "engine"))
    engine.backend = "torch"
    snapshot = write_hf_cache(engine.shared_model_root / "torch", engine.MODEL_NAME)
    tokenizer = local_inference.AutoTokenizer.from_pretrained(str(e5_snapshot))
    tokenizer.save_pretrained(snapshot)
    config = LlamaConfig(
        vocab_size=tokenizer.vocab_size, hidden_size=16, intermediate_size=32,
        num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2,
    )
    LlamaForCausalLM(config).save_pretrained(snapshot)

    assert engine.load_model() is True

    assert isinstance(engine.model, LlamaForCausalLM)
    assert no_network == []


def test_torch_fallback_offline_missing_model_fails_cleanly(monkeypatch, tmp_path, local_inference, offline, no_network):
    if not local_inference.TORCH_AVAILABLE:
        pytest.skip("torch/transformers not installed")

    def from_pretrained(source, **kwargs):
        if kwargs.get("local_files_only"):
            raise OSError(f"{source} is not in the local cache")
        raise AssertionError("must not download")

    tokenizer_cls, model_cls = MagicMock(), MagicMock()
    tokenizer_cls.from_pretrained.side_effect = from_pretrained
    monkeypatch.setattr(local_inference, "AutoTokenizer", tokenizer_cls)
    monkeypatch.setattr(local_inference, "AutoModelForCausalLM", model_cls)
    engine = local_inference.LocalInferenceEngine(cache_dir=str(tmp_path / "engine"))
    engine.backend = "torch"
    messages = []

    assert engine.load_model(progress_callback=messages.append) is False

    # Only the library's local-only lookup ran.
    assert tokenizer_cls.from_pretrained.call_args.kwargs["local_files_only"] is True
    model_cls.from_pretrained.assert_not_called()
    assert "HF_HUB_OFFLINE" in messages[-1]
    assert no_network == []


def test_mlx_model_already_in_hf_cache_is_not_downloaded_again(tmp_path, local_inference, hub, online):
    snapshot = write_model(tmp_path / "hf-snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    messages = []

    path = local_inference.LocalInferenceEngine.ensure_mlx_model_downloaded(REPO_ID, messages.append)

    assert path == snapshot
    hub.snapshot_download.assert_not_called()
    assert "already on this Mac" in messages[-1]


def test_missing_mlx_model_is_downloaded_once(local_inference, hub, online):
    hub.snapshot_download.side_effect = lambda repo_id, local_dir, **kwargs: write_model(Path(local_dir))
    messages = []

    path = local_inference.LocalInferenceEngine.ensure_mlx_model_downloaded(REPO_ID, messages.append)

    hub.snapshot_download.assert_called_once()
    assert hub.snapshot_download.call_args.kwargs["repo_id"] == REPO_ID
    assert path == local_inference.LocalInferenceEngine.get_mlx_model_dir(REPO_ID)
    assert messages[0].startswith("Downloading") and messages[-1].startswith("Downloaded")


def test_partially_downloaded_mlx_model_is_downloaded_again(local_inference, hub, online):
    engine_cls = local_inference.LocalInferenceEngine
    shards = ("model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors")
    write_model(engine_cls.get_mlx_model_dir(REPO_ID), weights=shards[:1], index=shards)
    hub.snapshot_download.side_effect = lambda repo_id, local_dir, **kwargs: (Path(local_dir) / shards[1]).write_bytes(b"w")

    assert not engine_cls.is_mlx_model_available(REPO_ID)
    engine_cls.ensure_mlx_model_downloaded(REPO_ID)

    hub.snapshot_download.assert_called_once()
    assert engine_cls.is_mlx_model_available(REPO_ID)


def test_offline_missing_mlx_model_raises_without_download(local_inference, hub, offline, no_network):
    with pytest.raises(ModelNotDownloadedError, match="HF_HUB_OFFLINE"):
        local_inference.LocalInferenceEngine.ensure_mlx_model_downloaded(REPO_ID)

    hub.snapshot_download.assert_not_called()
    assert no_network == []


@pytest.mark.parametrize("allow_download", [True, False])
def test_mlx_load_model_uses_the_local_copy(monkeypatch, tmp_path, local_inference, hub, online, no_network, allow_download):
    snapshot = write_model(tmp_path / "hf-snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    mlx_load = MagicMock(return_value=("model", "tokenizer"))
    monkeypatch.setattr(local_inference, "mlx_load", mlx_load, raising=False)
    engine = local_inference.LocalInferenceEngine(cache_dir=str(tmp_path / "engine"))
    engine.backend = "mlx"
    engine.MLX_MODEL_CANDIDATES = [REPO_ID]

    assert engine.load_model(allow_download=allow_download) is True

    mlx_load.assert_called_once_with(str(snapshot))
    hub.snapshot_download.assert_not_called()
    assert no_network == []


def test_unloadable_mlx_copy_in_hf_cache_is_downloaded_again(monkeypatch, tmp_path, local_inference, hub, online, no_network):
    hf_snapshot = write_model(tmp_path / "hf-snapshot")
    hub.try_to_load_from_cache.return_value = str(hf_snapshot / "config.json")
    hub.snapshot_download.side_effect = lambda repo_id, local_dir, **kwargs: write_model(Path(local_dir))
    engine = local_inference.LocalInferenceEngine(cache_dir=str(tmp_path / "engine"))
    app_dir = engine.get_mlx_model_dir(REPO_ID)

    def mlx_load(path):
        if path == str(hf_snapshot):
            raise ValueError("tokenizer files missing")
        return "model", "tokenizer"

    monkeypatch.setattr(local_inference, "mlx_load", MagicMock(side_effect=mlx_load), raising=False)
    engine.backend = "mlx"
    engine.MLX_MODEL_CANDIDATES = [REPO_ID]

    assert engine.load_model() is True

    hub.snapshot_download.assert_called_once()
    assert [c.args for c in local_inference.mlx_load.call_args_list] == [(str(hf_snapshot),), (str(app_dir),)]
    assert no_network == []


def test_unloadable_mlx_copy_is_not_downloaded_when_downloads_are_off(monkeypatch, tmp_path, local_inference, hub, online, no_network):
    hf_snapshot = write_model(tmp_path / "hf-snapshot")
    hub.try_to_load_from_cache.return_value = str(hf_snapshot / "config.json")
    monkeypatch.setattr(local_inference, "mlx_load", MagicMock(side_effect=ValueError("broken")), raising=False)
    engine = local_inference.LocalInferenceEngine(cache_dir=str(tmp_path / "engine"))
    engine.backend = "mlx"
    engine.MLX_MODEL_CANDIDATES = [REPO_ID]

    assert engine.load_model(allow_download=False) is False

    hub.snapshot_download.assert_not_called()
    assert no_network == []


def test_mlx_dora_engine_loads_cached_model_from_local_path(monkeypatch, tmp_path, hub, online, no_network):
    from advanced_vault.gui import mlx_dora_inference

    snapshot = write_model(tmp_path / "hf-snapshot")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")
    mlx_load = MagicMock(return_value=("model", "tokenizer"))
    monkeypatch.setattr(mlx_dora_inference, "MLX_AVAILABLE", True)
    monkeypatch.setattr(mlx_dora_inference, "mlx_load", mlx_load, raising=False)
    engine = mlx_dora_inference.MLXDoRAInference(model_path=REPO_ID, cache_dir=str(tmp_path / "cache"))

    assert engine.load_model() is True

    mlx_load.assert_called_once_with(str(snapshot))
    hub.snapshot_download.assert_not_called()
    assert no_network == []


# ---------------------------------------------------------------------------
# SmolDocling OCR (the GUI's PDF import, whose text goes into the RAG index)
# ---------------------------------------------------------------------------


@pytest.fixture
def smoldocling(monkeypatch):
    """PDFProcessor set up to prefer SmolDocling, with mlx_vlm replaced by mocks."""
    from advanced_vault.gui import pdf_processor

    mlx_vlm = types.ModuleType("mlx_vlm")
    mlx_vlm.load = MagicMock(return_value=("model", "processor"))
    mlx_vlm_utils = types.ModuleType("mlx_vlm.utils")
    mlx_vlm_utils.load_config = MagicMock(return_value={"model_type": "idefics3"})
    mlx_vlm.utils = mlx_vlm_utils
    monkeypatch.setitem(sys.modules, "mlx_vlm", mlx_vlm)
    monkeypatch.setitem(sys.modules, "mlx_vlm.utils", mlx_vlm_utils)

    monkeypatch.setattr(pdf_processor, "SMOLDOCLING_AVAILABLE", True)
    monkeypatch.setattr(pdf_processor, "_is_apple_silicon", lambda: True)
    monkeypatch.setattr(pdf_processor, "probe_liteparse_backend", lambda **kwargs: False)
    monkeypatch.setattr(pdf_processor.PDFProcessor, "_test_ollama_connection", lambda self: False)
    installer = MagicMock(return_value=False)
    monkeypatch.setattr(pdf_processor, "_install_smoldocling_dependencies", installer)
    monkeypatch.delenv("ENCLAVE_USE_SMOLDOCLING", raising=False)
    return types.SimpleNamespace(
        module=pdf_processor, load=mlx_vlm.load, load_config=mlx_vlm_utils.load_config, installer=installer
    )


def test_smoldocling_loads_cached_model_from_local_path(tmp_path, smoldocling, hub, online, no_network):
    snapshot = write_model(tmp_path / "smoldocling")
    hub.try_to_load_from_cache.return_value = str(snapshot / "config.json")

    processor = smoldocling.module.PDFProcessor(auto_setup=True)

    assert processor.smoldocling_available is True
    assert processor.smoldocling_config == {"model_type": "idefics3"}
    smoldocling.load.assert_called_once_with(str(snapshot))
    smoldocling.load_config.assert_called_once_with(str(snapshot))
    smoldocling.installer.assert_not_called()
    hub.snapshot_download.assert_not_called()
    assert no_network == []


def test_smoldocling_missing_model_is_downloaded_by_id(smoldocling, hub, online, no_network):
    processor = smoldocling.module.PDFProcessor(auto_setup=True)

    assert processor.smoldocling_available is True
    model_id = smoldocling.module.SMOLDOCLING_MODEL_ID
    smoldocling.load.assert_called_once_with(model_id)  # mlx_vlm's own download path
    smoldocling.load_config.assert_called_once_with(model_id)
    assert no_network == []  # mlx_vlm is mocked here


def test_smoldocling_offline_missing_model_is_skipped_without_network(smoldocling, hub, offline, no_network):
    processor = smoldocling.module.PDFProcessor(auto_setup=True)

    assert processor.smoldocling_available is False
    smoldocling.load.assert_not_called()
    smoldocling.installer.assert_not_called()  # a missing model is not a missing package
    assert no_network == []
