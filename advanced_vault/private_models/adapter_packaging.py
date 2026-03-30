"""Package local WDVA adapters into encrypted artifacts for local-only use."""

from __future__ import annotations

import json
import os
from base64 import b64encode
from pathlib import Path
from typing import Any, Dict, Optional

import zstandard as zstd
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def write_adapter_key(path: str | Path, key: bytes) -> Path:
    """Write a 32-byte adapter master key with secure permissions."""
    if len(key) != 32:
        raise ValueError("Adapter key must be exactly 32 bytes")

    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(key)
    os.chmod(output_path, 0o600)
    return output_path


def package_adapter_file(
    adapter_file: str | Path,
    output_path: str | Path,
    master_key: bytes,
    metadata: Optional[Dict[str, Any]] = None,
    compression_level: int = 3,
) -> Path:
    """
    Encrypt a local safetensors adapter file into a WDVA package.

    The output format matches the local MLX adapter loaders in this repo.
    """
    if len(master_key) != 32:
        raise ValueError("Master key must be exactly 32 bytes")

    input_path = Path(adapter_file).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    raw_adapter = input_path.read_bytes()
    compressed = zstd.ZstdCompressor(level=compression_level).compress(raw_adapter)

    salt = os.urandom(16)
    nonce = os.urandom(12)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"dora-encryption-key-v2",
    )
    encryption_key = hkdf.derive(master_key)

    package_metadata = {
        "adapter_type": "DoRA",
        "compressed": True,
        "compression_level": compression_level,
        "filename": input_path.name,
        "original_size_bytes": len(raw_adapter),
        "version": "local-wdva-1",
    }
    if metadata:
        package_metadata.update(metadata)

    cipher = ChaCha20Poly1305(encryption_key)
    aad = json.dumps(package_metadata, sort_keys=True).encode("utf-8")
    ciphertext_with_tag = cipher.encrypt(nonce, compressed, aad)
    ciphertext = ciphertext_with_tag[:-16]
    tag = ciphertext_with_tag[-16:]

    package = {
        "salt": b64encode(salt).decode("utf-8"),
        "nonce": b64encode(nonce).decode("utf-8"),
        "ciphertext": b64encode(ciphertext).decode("utf-8"),
        "tag": b64encode(tag).decode("utf-8"),
        "metadata": package_metadata,
        "algorithm": "ChaCha20-Poly1305",
        "kdf": "HKDF-SHA256",
    }

    dest = Path(output_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(package, indent=2))
    return dest
