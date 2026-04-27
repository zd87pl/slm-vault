"""
Encrypted Adapter Backup & Sharing

Enables consumers to:
- Export encrypted WDVA adapters to files
- Back up to cloud storage (iCloud, Google Drive, Dropbox)
- Share adapters via QR codes or secure links
- Import adapters from other devices
- Verify adapter integrity before loading

All operations work on encrypted blobs only - raw weights never leave the device.
"""

import os
import json
import base64
import hashlib
import tempfile
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import shutil

try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


class BackupFormat(Enum):
    """Supported backup formats."""
    WDVA = "wdva"           # Raw encrypted WDVA blob
    ENCLAVE = "enclave"     # Enclave package (WDVA + metadata + manifest)
    QR = "qr"               # QR code representation (small adapters only)
    CLOUD = "cloud"         # Cloud storage reference


@dataclass
class BackupManifest:
    """Metadata about a backed-up adapter."""
    
    adapter_id: str
    adapter_name: str
    category_id: str
    preset_id: str
    created_at: str
    backed_up_at: str
    document_count: int
    training_method: str
    base_model: str
    file_size: int
    checksum: str
    encryption_version: str = "WDVA_v1.0"
    backup_format: str = "enclave"
    tags: List[str] = None
    description: str = ""
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "category_id": self.category_id,
            "preset_id": self.preset_id,
            "created_at": self.created_at,
            "backed_up_at": self.backed_up_at,
            "document_count": self.document_count,
            "training_method": self.training_method,
            "base_model": self.base_model,
            "file_size": self.file_size,
            "checksum": self.checksum,
            "encryption_version": self.encryption_version,
            "backup_format": self.backup_format,
            "tags": self.tags,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupManifest":
        return cls(**data)


class AdapterBackupManager:
    """Manages encrypted adapter backup, restore, and sharing."""
    
    def __init__(self, vault_path: str, cloud_provider: Optional[str] = None):
        self.vault_path = Path(vault_path)
        self.backup_path = self.vault_path / "backups"
        self.backup_path.mkdir(parents=True, exist_ok=True)
        
        self.cloud_provider = cloud_provider  # "icloud", "gdrive", "dropbox", None
        self._cloud_handlers: Dict[str, Callable] = {}
        
        logger.info(f"AdapterBackupManager initialized: {self.backup_path}")
    
    def export_adapter(
        self,
        adapter_path: str,
        adapter_name: str,
        category_id: str,
        preset_id: str,
        document_count: int = 0,
        training_method: str = "dpo",
        base_model: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
        description: str = "",
        tags: Optional[List[str]] = None,
        output_path: Optional[str] = None,
        format: BackupFormat = BackupFormat.ENCLAVE,
    ) -> str:
        """
        Export an encrypted adapter to a portable file.
        
        Args:
            adapter_path: Path to the WDVA encrypted adapter
            adapter_name: Human-readable name
            category_id: Vault category ID
            preset_id: Training preset used
            document_count: Number of training documents
            training_method: Training method used
            base_model: Base model name
            description: Optional description
            tags: Optional tags
            output_path: Where to save (default: backups folder)
            format: Backup format
        
        Returns:
            Path to the exported file
        """
        adapter_path = Path(adapter_path)
        if not adapter_path.exists():
            raise FileNotFoundError(f"Adapter not found: {adapter_path}")
        
        # Read encrypted adapter
        with open(adapter_path, "rb") as f:
            encrypted_data = f.read()
        
        # Build manifest
        manifest = BackupManifest(
            adapter_id=self._generate_adapter_id(adapter_path),
            adapter_name=adapter_name,
            category_id=category_id,
            preset_id=preset_id,
            created_at=datetime.utcnow().isoformat(),
            backed_up_at=datetime.utcnow().isoformat(),
            document_count=document_count,
            training_method=training_method,
            base_model=base_model,
            file_size=len(encrypted_data),
            checksum=hashlib.sha256(encrypted_data).hexdigest(),
            backup_format=format.value,
            tags=tags or [],
            description=description,
        )
        
        # Package based on format
        if format == BackupFormat.WDVA:
            # Just the raw encrypted blob
            output_data = encrypted_data
            output_ext = ".wdva"
        elif format == BackupFormat.ENCLAVE:
            # Package with metadata
            package = {
                "manifest": manifest.to_dict(),
                "data": base64.b64encode(encrypted_data).decode("ascii"),
            }
            output_data = json.dumps(package, indent=2).encode("utf-8")
            output_ext = ".enclave"
        elif format == BackupFormat.QR:
            # Small adapters only - encode as base64 string
            if len(encrypted_data) > 2000:
                raise ValueError("Adapter too large for QR format (>2KB)")
            output_data = base64.b64encode(encrypted_data)
            output_ext = ".qr.txt"
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        # Determine output path
        if output_path:
            output_file = Path(output_path)
        else:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in adapter_name)
            output_file = self.backup_path / f"{safe_name}_{manifest.adapter_id[:8]}{output_ext}"
        
        # Write output
        if format == BackupFormat.QR:
            with open(output_file, "w") as f:
                f.write(output_data.decode("ascii"))
        else:
            with open(output_file, "wb") as f:
                f.write(output_data)
        
        logger.info(f"Exported adapter to {output_file} ({len(output_data)} bytes)")
        return str(output_file)
    
    def import_adapter(
        self,
        import_path: str,
        verify_integrity: bool = True
    ) -> Tuple[str, BackupManifest]:
        """
        Import an adapter from a backup file.
        
        Args:
            import_path: Path to the backup file
            verify_integrity: Whether to verify checksum
        
        Returns:
            Tuple of (adapter_output_path, manifest)
        """
        import_path = Path(import_path)
        if not import_path.exists():
            raise FileNotFoundError(f"Backup not found: {import_path}")
        
        # Detect format
        suffix = import_path.suffix.lower()
        
        if suffix == ".wdva":
            # Raw WDVA blob
            with open(import_path, "rb") as f:
                encrypted_data = f.read()
            manifest = None
        elif suffix == ".enclave":
            # Enclave package
            with open(import_path, "r") as f:
                package = json.load(f)
            manifest = BackupManifest.from_dict(package["manifest"])
            encrypted_data = base64.b64decode(package["data"])
        elif suffix == ".qr.txt":
            # QR code text
            with open(import_path, "r") as f:
                b64_data = f.read().strip()
            encrypted_data = base64.b64decode(b64_data)
            manifest = None
        else:
            raise ValueError(f"Unknown backup format: {suffix}")
        
        # Verify integrity
        if verify_integrity and manifest:
            actual_checksum = hashlib.sha256(encrypted_data).hexdigest()
            if actual_checksum != manifest.checksum:
                raise ValueError(
                    f"Checksum mismatch! Expected {manifest.checksum}, got {actual_checksum}"
                )
        
        # Determine output path
        if manifest:
            adapter_id = manifest.adapter_id
            adapter_name = manifest.adapter_name
        else:
            adapter_id = hashlib.sha256(encrypted_data[:32]).hexdigest()[:16]
            adapter_name = f"imported_{adapter_id}"
        
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in adapter_name)
        output_path = self.vault_path / "adapters" / f"{safe_name}_{adapter_id[:8]}.wdva"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write imported adapter
        with open(output_path, "wb") as f:
            f.write(encrypted_data)
        
        logger.info(f"Imported adapter to {output_path}")
        return str(output_path), manifest
    
    def verify_adapter(
        self,
        adapter_path: str,
        manifest: Optional[BackupManifest] = None
    ) -> Dict[str, Any]:
        """
        Verify an adapter's integrity.
        
        Args:
            adapter_path: Path to the adapter
            manifest: Optional manifest to verify against
        
        Returns:
            Verification report dict
        """
        adapter_path = Path(adapter_path)
        
        report = {
            "path": str(adapter_path),
            "exists": adapter_path.exists(),
            "readable": False,
            "checksum_match": None,
            "manifest_valid": False,
            "encryption_detected": False,
            "warnings": [],
            "errors": [],
        }
        
        if not adapter_path.exists():
            report["errors"].append("File does not exist")
            return report
        
        try:
            with open(adapter_path, "rb") as f:
                data = f.read()
            report["readable"] = True
            report["file_size"] = len(data)
        except Exception as e:
            report["errors"].append(f"Cannot read file: {e}")
            return report
        
        # Detect encryption (WDVA format starts with nonce)
        if len(data) > 16:
            # WDVA blob: nonce(12) || aad_len(4) || aad || ciphertext
            report["encryption_detected"] = True
        
        # Verify checksum if manifest provided
        if manifest:
            actual_checksum = hashlib.sha256(data).hexdigest()
            report["checksum_match"] = actual_checksum == manifest.checksum
            if not report["checksum_match"]:
                report["errors"].append("Checksum mismatch - file may be corrupted")
        
        # Validate manifest if present in enclave format
        if adapter_path.suffix == ".enclave":
            try:
                with open(adapter_path, "r") as f:
                    package = json.load(f)
                manifest_data = package.get("manifest", {})
                if "adapter_id" in manifest_data and "checksum" in manifest_data:
                    report["manifest_valid"] = True
            except Exception as e:
                report["warnings"].append(f"Could not validate manifest: {e}")
        
        report["valid"] = (
            report["exists"]
            and report["readable"]
            and report["encryption_detected"]
            and (report["checksum_match"] is None or report["checksum_match"])
        )
        
        return report
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List all backups in the backup directory."""
        backups = []
        for file_path in self.backup_path.iterdir():
            if file_path.suffix in (".wdva", ".enclave", ".qr.txt"):
                stat = file_path.stat()
                backups.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "format": file_path.suffix.lstrip("."),
                })
        return sorted(backups, key=lambda x: x["modified"], reverse=True)
    
    def delete_backup(self, filename: str) -> bool:
        """Delete a backup file."""
        file_path = self.backup_path / filename
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted backup: {file_path}")
            return True
        return False
    
    def generate_share_metadata(
        self,
        manifest: BackupManifest,
        share_method: str = "file"
    ) -> Dict[str, Any]:
        """
        Generate metadata for sharing an adapter.
        
        Args:
            manifest: Adapter manifest
            share_method: How it will be shared (file, qr, cloud)
        
        Returns:
            Share metadata dict
        """
        return {
            "adapter_name": manifest.adapter_name,
            "category": manifest.category_id,
            "description": manifest.description,
            "tags": manifest.tags,
            "document_count": manifest.document_count,
            "training_method": manifest.training_method,
            "base_model": manifest.base_model,
            "share_method": share_method,
            "encrypted": True,
            "disclaimer": (
                "This adapter contains encrypted learned weights only. "
                "No raw documents or personal data are included."
            ),
        }
    
    def register_cloud_handler(
        self,
        provider: str,
        upload_fn: Callable[[str, bytes], str],
        download_fn: Callable[[str], bytes]
    ):
        """Register a cloud storage provider handler."""
        self._cloud_handlers[provider] = {
            "upload": upload_fn,
            "download": download_fn,
        }
        logger.info(f"Registered cloud provider: {provider}")
    
    def upload_to_cloud(
        self,
        backup_path: str,
        provider: Optional[str] = None
    ) -> str:
        """
        Upload a backup to cloud storage.
        
        Args:
            backup_path: Path to backup file
            provider: Cloud provider (default: configured provider)
        
        Returns:
            Cloud reference/URL
        """
        provider = provider or self.cloud_provider
        if not provider:
            raise ValueError("No cloud provider configured")
        
        if provider not in self._cloud_handlers:
            raise ValueError(f"Cloud provider not registered: {provider}")
        
        backup_path = Path(backup_path)
        with open(backup_path, "rb") as f:
            data = f.read()
        
        reference = self._cloud_handlers[provider]["upload"](
            backup_path.name,
            data
        )
        
        logger.info(f"Uploaded {backup_path.name} to {provider}: {reference}")
        return reference
    
    def download_from_cloud(
        self,
        reference: str,
        provider: Optional[str] = None,
        output_name: Optional[str] = None
    ) -> str:
        """
        Download a backup from cloud storage.
        
        Args:
            reference: Cloud reference/URL
            provider: Cloud provider
            output_name: Local filename (default: from reference)
        
        Returns:
            Local file path
        """
        provider = provider or self.cloud_provider
        if not provider:
            raise ValueError("No cloud provider configured")
        
        if provider not in self._cloud_handlers:
            raise ValueError(f"Cloud provider not registered: {provider}")
        
        data = self._cloud_handlers[provider]["download"](reference)
        
        output_name = output_name or f"cloud_download_{hashlib.sha256(data[:32]).hexdigest()[:8]}.enclave"
        output_path = self.backup_path / output_name
        
        with open(output_path, "wb") as f:
            f.write(data)
        
        logger.info(f"Downloaded from {provider} to {output_path}")
        return str(output_path)
    
    def _generate_adapter_id(self, adapter_path: Path) -> str:
        """Generate a unique adapter ID from file content and timestamp."""
        with open(adapter_path, "rb") as f:
            content = f.read()
        
        hash_input = content + datetime.utcnow().isoformat().encode()
        return hashlib.sha256(hash_input).hexdigest()
