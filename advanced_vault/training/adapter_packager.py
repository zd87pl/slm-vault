"""
Adapter Packager for Distribution

Packages trained adapters into encrypted, distributable formats.
Supports:
- Encrypted JSON packages (with metadata, compression)
- Raw safetensors export (for unencrypted sharing)
- QAT metadata preservation
- Version tagging and checksums

Usage:
    from advanced_vault.training.adapter_packager import AdapterPackager

    packager = AdapterPackager()
    packager.package_adapter(
        adapter_dir="~/.enclave/adapters/my_adapter",
        output_path="~/my_adapter.enclave",
        password="super-secret",
        metadata={"description": "DPO adapter for legal docs", "version": "1.0"},
    )
"""

import hashlib
import json
import logging
import os
import tempfile
import time
import zipfile
from base64 import b64encode, b64decode
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    logger.warning("cryptography not available, encryption disabled")


try:
    import zstandard as zstd
    _ZSTD_AVAILABLE = True
except ImportError:
    _ZSTD_AVAILABLE = False


@dataclass
class AdapterMetadata:
    """Metadata for a packaged adapter."""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    train_mode: str = "sft"  # sft, dpo, orpo, grpo
    qat_enabled: bool = False
    qat_bits: int = 16
    base_model: str = ""
    lora_rank: int = 8
    lora_alpha: int = 16
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    author: str = ""
    tags: List[str] = field(default_factory=list)
    checksum: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdapterMetadata":
        # Filter unknown fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class AdapterPackager:
    """
    Package and encrypt adapters for distribution.

    Two output formats:
    1. Encrypted JSON package (.enclave) — best for sharing
    2. ZIP archive with metadata (.zip) — best for storage/backup
    """

    def __init__(self, compression_level: int = 3):
        self.compression_level = compression_level

    def package_adapter(
        self,
        adapter_dir: str,
        output_path: str,
        password: Optional[str] = None,
        encryption_key: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
        format: str = "enclave",  # "enclave" or "zip"
    ) -> str:
        """
        Package an adapter directory into an encrypted distributable file.

        Args:
            adapter_dir: Path to adapter directory (contains adapter_*.safetensors, etc.)
            output_path: Output file path
            password: Password for encryption (derived to 32-byte key)
            encryption_key: Raw 32-byte encryption key (overrides password)
            metadata: Additional metadata dict
            format: Output format ("enclave" or "zip")

        Returns:
            Path to the packaged file
        """
        adapter_path = Path(adapter_dir).expanduser()
        if not adapter_path.exists():
            raise FileNotFoundError(f"Adapter directory not found: {adapter_path}")

        # Gather adapter files
        adapter_files = list(adapter_path.glob("adapter*.safetensors"))
        if not adapter_files:
            adapter_files = list(adapter_path.glob("*.safetensors"))
        if not adapter_files:
            raise ValueError(f"No safetensors files found in {adapter_path}")

        # Build metadata
        meta = AdapterMetadata(**(metadata or {}))
        meta.name = meta.name or adapter_path.name

        # Compute checksum over all adapter files
        hasher = hashlib.sha256()
        for f in sorted(adapter_files):
            hasher.update(f.read_bytes())
        meta.checksum = hasher.hexdigest()

        # Read all files into memory
        file_data = {}
        for f in adapter_files:
            file_data[f.name] = f.read_bytes()

        # Also include any JSON config files
        for f in adapter_path.glob("*.json"):
            file_data[f.name] = f.read_bytes()

        # Build package payload
        payload = {
            "metadata": meta.to_dict(),
            "files": {name: b64encode(data).decode("ascii") for name, data in file_data.items()},
        }
        payload_bytes = json.dumps(payload, indent=2).encode("utf-8")

        # Compress
        if _ZSTD_AVAILABLE:
            compressor = zstd.ZstdCompressor(level=self.compression_level)
            compressed = compressor.compress(payload_bytes)
            compressed_flag = True
        else:
            compressed = payload_bytes
            compressed_flag = False

        out_path = Path(output_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "zip":
            return self._write_zip(
                out_path=out_path,
                payload_bytes=compressed,
                metadata=meta,
                compressed=compressed_flag,
            )

        # Default: encrypted JSON package
        return self._write_encrypted_package(
            out_path=out_path,
            payload_bytes=compressed,
            metadata=meta,
            password=password,
            encryption_key=encryption_key,
            compressed=compressed_flag,
        )

    def _write_encrypted_package(
        self,
        out_path: Path,
        payload_bytes: bytes,
        metadata: AdapterMetadata,
        password: Optional[str],
        encryption_key: Optional[bytes],
        compressed: bool,
    ) -> str:
        """Write an encrypted JSON package (.enclave)."""
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError(
                "cryptography library required for encryption. "
                "Install with: pip install cryptography"
            )

        # Derive key
        if encryption_key is None:
            if password is None:
                raise ValueError("Either password or encryption_key must be provided")
            # Derive 32-byte key from password using SHA-256
            key = hashlib.sha256(password.encode("utf-8")).digest()
        else:
            key = encryption_key
            if len(key) != 32:
                raise ValueError(f"encryption_key must be 32 bytes, got {len(key)}")

        # Generate salt and nonce
        salt = os.urandom(16)
        nonce = os.urandom(12)

        # Derive encryption key with HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"enclave-adapter-package-v1",
        )
        derived_key = hkdf.derive(key)

        # Build AAD from metadata
        aad_data = {
            "name": metadata.name,
            "version": metadata.version,
            "created_at": metadata.created_at,
            "compressed": compressed,
        }
        aad = json.dumps(aad_data, sort_keys=True).encode("utf-8")

        # Encrypt
        cipher = ChaCha20Poly1305(derived_key)
        ciphertext_with_tag = cipher.encrypt(nonce, payload_bytes, aad)

        # ChaCha20Poly1305 output: ciphertext + 16-byte tag
        ciphertext = ciphertext_with_tag[:-16]
        tag = ciphertext_with_tag[-16:]

        package = {
            "format": "enclave-adapter-v1",
            "salt": b64encode(salt).decode("ascii"),
            "nonce": b64encode(nonce).decode("ascii"),
            "ciphertext": b64encode(ciphertext).decode("ascii"),
            "tag": b64encode(tag).decode("ascii"),
            "metadata": aad_data,
        }

        out_path.write_text(json.dumps(package, indent=2))
        logger.info(f"Packaged encrypted adapter to {out_path}")
        return str(out_path)

    def _write_zip(
        self,
        out_path: Path,
        payload_bytes: bytes,
        metadata: AdapterMetadata,
        compressed: bool,
    ) -> str:
        """Write a ZIP archive (.zip) with payload and metadata."""
        if not str(out_path).endswith(".zip"):
            out_path = out_path.with_suffix(".zip")

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("payload.bin", payload_bytes)
            zf.writestr("metadata.json", json.dumps(metadata.to_dict(), indent=2))
            zf.writestr("format.txt", "enclave-zip-v1")

        logger.info(f"Packaged adapter ZIP to {out_path}")
        return str(out_path)

    def unpack_adapter(
        self,
        package_path: str,
        output_dir: str,
        password: Optional[str] = None,
        encryption_key: Optional[bytes] = None,
    ) -> AdapterMetadata:
        """
        Unpack an adapter package to a directory.

        Args:
            package_path: Path to .enclave or .zip package
            output_dir: Directory to unpack into
            password: Decryption password
            encryption_key: Raw 32-byte decryption key

        Returns:
            AdapterMetadata from the package
        """
        pkg_path = Path(package_path).expanduser()
        if not pkg_path.exists():
            raise FileNotFoundError(f"Package not found: {pkg_path}")

        out_dir = Path(output_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        if pkg_path.suffix == ".zip":
            return self._unpack_zip(pkg_path, out_dir)

        return self._unpack_encrypted(pkg_path, out_dir, password, encryption_key)

    def _unpack_encrypted(
        self,
        pkg_path: Path,
        out_dir: Path,
        password: Optional[str],
        encryption_key: Optional[bytes],
    ) -> AdapterMetadata:
        """Unpack an encrypted JSON package."""
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library required for decryption")

        package = json.loads(pkg_path.read_text())
        salt = b64decode(package["salt"])
        nonce = b64decode(package["nonce"])
        ciphertext = b64decode(package["ciphertext"])
        tag = b64decode(package["tag"])
        aad_data = package["metadata"]
        aad = json.dumps(aad_data, sort_keys=True).encode("utf-8")

        # Derive key
        if encryption_key is None:
            if password is None:
                raise ValueError("Either password or encryption_key must be provided")
            key = hashlib.sha256(password.encode("utf-8")).digest()
        else:
            key = encryption_key
            if len(key) != 32:
                raise ValueError(f"encryption_key must be 32 bytes, got {len(key)}")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"enclave-adapter-package-v1",
        )
        derived_key = hkdf.derive(key)

        # Decrypt
        cipher = ChaCha20Poly1305(derived_key)
        ciphertext_with_tag = ciphertext + tag
        payload_bytes = cipher.decrypt(nonce, ciphertext_with_tag, aad)

        # Decompress if needed
        if aad_data.get("compressed", False) and _ZSTD_AVAILABLE:
            decompressor = zstd.ZstdDecompressor()
            payload_bytes = decompressor.decompress(payload_bytes)

        payload = json.loads(payload_bytes.decode("utf-8"))
        metadata = AdapterMetadata.from_dict(payload["metadata"])

        # Write files
        for name, b64_data in payload["files"].items():
            data = b64decode(b64_data)
            (out_dir / name).write_bytes(data)

        logger.info(f"Unpacked adapter '{metadata.name}' to {out_dir}")
        return metadata

    def _unpack_zip(self, pkg_path: Path, out_dir: Path) -> AdapterMetadata:
        """Unpack a ZIP archive."""
        with zipfile.ZipFile(pkg_path, "r") as zf:
            zf.extractall(out_dir)

        meta_path = out_dir / "metadata.json"
        if meta_path.exists():
            metadata = AdapterMetadata.from_dict(json.loads(meta_path.read_text()))
        else:
            metadata = AdapterMetadata(name=pkg_path.stem)

        logger.info(f"Unpacked ZIP adapter to {out_dir}")
        return metadata

    def verify_package(
        self,
        package_path: str,
        password: Optional[str] = None,
        encryption_key: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Verify an adapter package without fully unpacking.

        Returns dict with:
        - valid: bool
        - metadata: AdapterMetadata
        - checksum_match: bool (if adapter files can be verified)
        """
        try:
            with tempfile.TemporaryDirectory() as tmp:
                meta = self.unpack_adapter(
                    package_path, tmp, password=password, encryption_key=encryption_key
                )
                # Re-compute checksum
                adapter_files = list(Path(tmp).glob("adapter*.safetensors"))
                if not adapter_files:
                    adapter_files = list(Path(tmp).glob("*.safetensors"))

                hasher = hashlib.sha256()
                for f in sorted(adapter_files):
                    hasher.update(f.read_bytes())
                computed = hasher.hexdigest()

                return {
                    "valid": True,
                    "metadata": meta,
                    "checksum_match": computed == meta.checksum,
                    "computed_checksum": computed,
                }
        except Exception as e:
            return {"valid": False, "error": str(e)}
