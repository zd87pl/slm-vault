"""Minimal local encrypted store for extracted secrets."""

from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .storage import JSONFileStore


class SecretsVault:
    """Encrypts and stores extracted secrets (not full files)."""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.key_path = self.base_path / "secrets.key"
        self.store = JSONFileStore(self.base_path / "secrets.json")
        self._key = self._load_or_create_key()
        self._cipher = ChaCha20Poly1305(self._key)

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            return self.key_path.read_bytes()
        key = os.urandom(32)
        self.key_path.write_bytes(key)
        if os.name != "nt":
            os.chmod(self.key_path, 0o600)
        return key

    def _load_items(self) -> Dict[str, dict]:
        return self.store.load(default={})

    def _save_items(self, items: Dict[str, dict]) -> None:
        self.store.save(items)

    def put_secret(self, *, secret_name: str, plaintext: str, source_path: str, line_no: Optional[int] = None) -> str:
        """Store one secret value encrypted."""
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), None)
        secret_id = str(uuid4())
        items = self._load_items()
        items[secret_id] = {
            "secret_id": secret_id,
            "secret_name": secret_name,
            "source_path": source_path,
            "line_no": line_no,
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
            "created_at": datetime.utcnow().isoformat(),
        }
        self._save_items(items)
        return secret_id

    def get_secret(self, secret_id: str) -> Optional[dict]:
        """Return decrypted secret payload."""
        items = self._load_items()
        row = items.get(secret_id)
        if not row:
            return None

        nonce = base64.b64decode(row["nonce"])
        ciphertext = base64.b64decode(row["ciphertext"])
        plaintext = self._cipher.decrypt(nonce, ciphertext, None).decode("utf-8")
        return {
            "secret_id": row["secret_id"],
            "secret_name": row["secret_name"],
            "source_path": row["source_path"],
            "line_no": row.get("line_no"),
            "created_at": row["created_at"],
            "value": plaintext,
        }

    def list_secrets(self) -> List[dict]:
        """List metadata (without plaintext values)."""
        items = self._load_items()
        rows = list(items.values())
        rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return [
            {
                "secret_id": r["secret_id"],
                "secret_name": r["secret_name"],
                "source_path": r["source_path"],
                "line_no": r.get("line_no"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
