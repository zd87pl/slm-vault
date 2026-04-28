"""
Data models for encrypted key-value store.

This module defines the schema for storing exact data (API keys, passwords)
with client-side encryption and metadata search capabilities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class EntryType(Enum):
    """Type of stored entry."""
    SECRET = "secret"
    API_KEY = "api_key"
    PASSWORD = "password"
    TOKEN = "token"
    CREDENTIAL = "credential"
    KNOWLEDGE = "knowledge"  # Fuzzy/knowledge entries (Layer 2 fallback)
    FOLDER = "folder"  # Folder with optional password protection
    OTHER = "other"


@dataclass
class EncryptedEntry:
    """
    Represents an encrypted entry in the KV store.

    Security properties:
    - encrypted_data: Ciphertext (never stored as plaintext)
    - nonce: Unique per entry (semantic security)
    - Metadata (service, tags) NOT encrypted (enables search)
    """

    # Identity
    id: str  # UUID

    # Type and metadata (searchable, NOT encrypted)
    entry_type: EntryType
    service: str  # e.g., "stripe", "github", "aws"

    # Encrypted content (NEVER decrypted on server)
    encrypted_data: bytes  # ChaCha20-Poly1305 ciphertext
    nonce: bytes  # 12 bytes (96 bits)

    # Optional metadata fields (with defaults must come after required fields)
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None
    folder: Optional[str] = None  # Folder name (if entry belongs to a folder)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: Optional[datetime] = None

    # Versioning (for key rotation)
    version: int = 1

    def to_dict(self) -> dict:
        """Serialize to dictionary (for storage)."""
        return {
            "id": self.id,
            "entry_type": self.entry_type.value,
            "service": self.service,
            "tags": ",".join(self.tags),  # Store as comma-separated
            "description": self.description,
            "folder": self.folder,  # Folder name
            "encrypted_data": self.encrypted_data.hex(),
            "nonce": self.nonce.hex(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "version": self.version
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncryptedEntry":
        """Deserialize from dictionary."""
        # Parse tags - handle both JSON array and comma-separated formats
        tags_raw = data.get("tags", "")
        if not tags_raw:
            tags = []
        elif tags_raw.startswith("["):
            # JSON array format
            import json
            try:
                tags = json.loads(tags_raw)
                # Ensure all items are strings
                tags = [str(t) for t in tags if t]
            except (json.JSONDecodeError, TypeError):
                # Fallback to comma-separated
                tags = tags_raw.split(",")
        else:
            # Comma-separated format
            tags = tags_raw.split(",")
        
        return cls(
            id=data["id"],
            entry_type=EntryType(data["entry_type"]),
            service=data["service"],
            tags=tags,
            description=data.get("description"),
            folder=data.get("folder"),  # Folder name (optional)
            encrypted_data=bytes.fromhex(data["encrypted_data"]),
            nonce=bytes.fromhex(data["nonce"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            accessed_at=datetime.fromisoformat(data["accessed_at"]) if data.get("accessed_at") else None,
            version=data.get("version", 1)
        )


@dataclass
class QueryFilter:
    """
    Filter for searching encrypted entries.

    Search operates on metadata only (encrypted_data is NOT searchable).
    """

    # Exact match filters
    service: Optional[str] = None
    entry_type: Optional[EntryType] = None
    folder: Optional[str] = None  # Filter by folder name

    # Tag filtering
    tags: Optional[List[str]] = None  # Match ANY tag
    require_all_tags: bool = False  # If True, match ALL tags

    # Time range
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    accessed_after: Optional[datetime] = None

    # Pagination
    limit: Optional[int] = None
    offset: int = 0

    # Sorting
    sort_by: str = "created_at"  # "created_at", "updated_at", "accessed_at", "service"
    sort_desc: bool = True  # Most recent first


@dataclass
class VaultStats:
    """Statistics about the vault contents."""

    total_entries: int
    entries_by_type: dict  # EntryType -> count
    services: List[str]  # Unique service names
    tags: List[str]  # Unique tags
    total_size_bytes: int  # Encrypted data size
    oldest_entry: Optional[datetime]
    newest_entry: Optional[datetime]
    last_accessed: Optional[datetime]
