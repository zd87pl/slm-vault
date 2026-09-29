"""
Offline-first loading of Hugging Face models.

Loading a model by repo id (``SentenceTransformer("intfloat/e5-small-v2")``,
``AutoModel.from_pretrained(...)``, ``mlx_lm.load(...)``) asks the Hugging Face
Hub about the repo on every load -- dozens of HTTP requests -- even when every
file is already on disk, so the app contacted huggingface.co on each start and
stalled or failed without a network.

The helpers here look for a complete snapshot in the local Hugging Face cache
first and hand the loader that directory, which loads with no network access.
Only a model that is missing (or whose cached copy fails to load) goes through
the loader's normal download path, so first-run downloads and their progress
reporting are unchanged.

The decision is made per call, by passing local paths, rather than by setting
``HF_HUB_OFFLINE`` for the whole process (that would break first-run downloads
elsewhere). A user-set ``HF_HUB_OFFLINE=1`` is honoured: nothing falls back to
the network. The cache location is the one ``huggingface_hub`` uses, so
``HF_HOME`` / ``HF_HUB_CACHE`` are respected.
"""

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
PathLike = str | os.PathLike

# Same truthy spellings huggingface_hub accepts for its boolean env vars.
_TRUE_VALUES = {"1", "ON", "YES", "TRUE"}

# Weight file formats written by transformers, sentence-transformers and MLX.
_WEIGHT_SUFFIXES = {".safetensors", ".bin", ".npz", ".gguf", ".onnx", ".pt", ".pth", ".h5", ".msgpack"}


class ModelNotDownloadedError(FileNotFoundError):
    """A model is not in the local cache and may not be downloaded now."""


def hf_offline_enabled() -> bool:
    """Return True when the user has disabled Hugging Face network access."""
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        if os.environ.get(name, "").strip().upper() in _TRUE_VALUES:
            return True
    try:
        from huggingface_hub import constants
    except ImportError:
        return False
    return bool(getattr(constants, "HF_HUB_OFFLINE", False))


def is_complete_snapshot(path: PathLike) -> bool:
    """
    Return True when ``path`` holds a model config and a complete set of weights.

    Hugging Face downloads write each file to a temporary name and move it into
    place when it is finished, so an interrupted download leaves files missing
    rather than truncated. A sharded model counts as complete only when every
    shard its index lists is present.
    """
    path = Path(path)
    if not (path / "config.json").is_file():
        return False

    indexes = list(path.glob("*.index.json"))
    if indexes:
        return any(_index_is_complete(path, index) for index in indexes)
    return any(item.suffix in _WEIGHT_SUFFIXES and item.is_file() for item in path.iterdir())


def _index_is_complete(path: Path, index: Path) -> bool:
    try:
        shards = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    return bool(shards) and all((path / shard).is_file() for shard in shards)


def find_cached_snapshot(model_id: str, cache_dir: PathLike | None = None) -> Path | None:
    """
    Resolve a model id to a complete local snapshot without any network access.

    Args:
        model_id: Hugging Face repo id, or a path to a local model directory
        cache_dir: Hugging Face cache directory the loader downloads into
            (default: huggingface_hub's, which follows HF_HOME / HF_HUB_CACHE)

    Returns:
        The snapshot directory (a local model directory is returned as-is), or
        None when the model is missing from the cache or incomplete there.
    """
    local_path = Path(model_id).expanduser()
    if local_path.is_dir():
        return local_path

    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None

    try:
        config_path = try_to_load_from_cache(
            model_id,
            "config.json",
            cache_dir=str(cache_dir) if cache_dir is not None else None,
        )
    except Exception as exc:  # e.g. not a valid repo id
        logger.debug("Could not look up %s in the local model cache: %s", model_id, exc)
        return None

    if not isinstance(config_path, str):
        return None
    snapshot = Path(config_path).parent
    if not is_complete_snapshot(snapshot):
        logger.info("Cached copy of %s is incomplete; it will be downloaded again", model_id)
        return None
    return snapshot


def load_offline_first(
    model_id: str,
    load: Callable[[str], T],
    *,
    cache_dir: PathLike | None = None,
    allow_download: bool = True,
) -> T:
    """
    Load a model from the local cache when possible, downloading only if needed.

    ``load`` is called with a local snapshot directory when the model is fully
    cached. Otherwise, or when that cached copy fails to load, it is called with
    ``model_id`` so the loader downloads the model as it always has.

    Args:
        model_id: Hugging Face repo id (or local model directory)
        load: Loader taking a model id or local path, e.g. ``SentenceTransformer``
        cache_dir: Hugging Face cache directory the loader uses, if not the default
        allow_download: False to fail instead of downloading a missing model

    Raises:
        ModelNotDownloadedError: The model is not cached and downloads are
            disabled (``allow_download=False`` or ``HF_HUB_OFFLINE=1``).
    """
    offline = hf_offline_enabled()
    snapshot = find_cached_snapshot(model_id, cache_dir=cache_dir)

    if snapshot is not None:
        try:
            return load(str(snapshot))
        except Exception as exc:
            if offline or not allow_download or Path(model_id).expanduser().is_dir():
                raise
            logger.warning(
                "Cached copy of %s failed to load (%s); downloading it again", model_id, exc
            )
    elif offline:
        raise ModelNotDownloadedError(
            f"Model '{model_id}' is not in the local model cache and HF_HUB_OFFLINE is set, "
            "so it cannot be downloaded. Unset HF_HUB_OFFLINE and run once with network access "
            "to download it."
        )
    elif not allow_download:
        raise ModelNotDownloadedError(
            f"Model '{model_id}' has not been downloaded to this computer yet."
        )

    return load(model_id)
