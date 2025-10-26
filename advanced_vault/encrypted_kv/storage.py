"""
Encrypted key-value storage implementation.

This module provides ProtonMail-style E2EE storage where:
- Client encrypts data before storage
- Server (or local DB) never sees plaintext
- Metadata remains searchable
- Each entry uses unique nonce (semantic security)
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, List
from uuid import uuid4
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import constant_time
import os

from .models import EncryptedEntry, QueryFilter, VaultStats, EntryType


logger = logging.getLogger(__name__)


class EncryptedKVStore:
    """
    Local encrypted key-value store with metadata search.

    Security properties:
    - ChaCha20-Poly1305 authenticated encryption
    - Unique nonce per entry (96-bit random)
    - Client-side encryption only (never sends plaintext)
    - Constant-time operations where possible
    """

    def __init__(self, master_key: bytes, db_path: str = "~/.vault/kv_store.db"):
        """
        Initialize encrypted KV store.

        Args:
            master_key: 32-byte encryption key
            db_path: Path to SQLite database
        """
        if len(master_key) != 32:
            raise ValueError("Master key must be exactly 32 bytes")

        self.master_key = master_key
        self.cipher = ChaCha20Poly1305(master_key)
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

        logger.info(f"Initialized EncryptedKVStore at {self.db_path}")

    def _init_db(self):
        """Create database schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS encrypted_entries (
                    id TEXT PRIMARY KEY,
                    entry_type TEXT NOT NULL,
                    service TEXT NOT NULL,
                    tags TEXT,
                    description TEXT,
                    encrypted_data TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    accessed_at TEXT,
                    version INTEGER DEFAULT 1
                )
            """)

            # Create indexes for fast metadata search
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_service
                ON encrypted_entries(service)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entry_type
                ON encrypted_entries(entry_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON encrypted_entries(created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_accessed_at
                ON encrypted_entries(accessed_at)
            """)

            conn.commit()

    def put(
        self,
        service: str,
        secret_value: str,
        entry_type: EntryType = EntryType.SECRET,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
        entry_id: Optional[str] = None
    ) -> str:
        """
        Store encrypted entry.

        Encryption happens CLIENT-SIDE. Server never sees plaintext.

        Args:
            service: Service name (e.g., "stripe", "github")
            secret_value: Plaintext secret to encrypt
            entry_type: Type of entry
            tags: Optional tags for organization
            description: Optional description
            entry_id: Optional ID (generates UUID if None)

        Returns:
            Entry ID
        """
        # Generate unique entry ID
        if entry_id is None:
            entry_id = str(uuid4())

        # Generate unique nonce (96-bit random for ChaCha20Poly1305)
        nonce = os.urandom(12)  # 12 bytes for ChaCha20Poly1305

        # Encrypt the secret value
        # Associated data: service name (prevents ciphertext substitution)
        associated_data = service.encode('utf-8')
        ciphertext = self.cipher.encrypt(
            nonce,
            secret_value.encode('utf-8'),
            associated_data
        )

        # Create entry
        entry = EncryptedEntry(
            id=entry_id,
            entry_type=entry_type,
            service=service,
            tags=tags or [],
            description=description,
            encrypted_data=ciphertext,
            nonce=nonce,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Store in database
        with sqlite3.connect(self.db_path) as conn:
            data = entry.to_dict()
            conn.execute("""
                INSERT OR REPLACE INTO encrypted_entries
                (id, entry_type, service, tags, description, encrypted_data,
                 nonce, created_at, updated_at, accessed_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["id"], data["entry_type"], data["service"], data["tags"],
                data["description"], data["encrypted_data"], data["nonce"],
                data["created_at"], data["updated_at"], data["accessed_at"],
                data["version"]
            ))
            conn.commit()

        logger.info(f"Stored encrypted entry: {service} (ID: {entry_id})")
        return entry_id

    def get(self, service: str, update_access_time: bool = True) -> Optional[str]:
        """
        Retrieve and decrypt secret by service name.

        Decryption happens CLIENT-SIDE. Returns plaintext only to caller.

        Args:
            service: Service name to retrieve
            update_access_time: Whether to update accessed_at timestamp

        Returns:
            Decrypted secret value, or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM encrypted_entries
                WHERE service = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (service,))

            row = cursor.fetchone()
            if row is None:
                return None

            # Parse entry
            entry = EncryptedEntry.from_dict(dict(row))

            # Update access time
            if update_access_time:
                conn.execute("""
                    UPDATE encrypted_entries
                    SET accessed_at = ?
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), entry.id))
                conn.commit()

        # Decrypt (CLIENT-SIDE)
        try:
            associated_data = service.encode('utf-8')
            plaintext = self.cipher.decrypt(
                entry.nonce,
                entry.encrypted_data,
                associated_data
            )
            return plaintext.decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed for {service}: {e}")
            return None

    def get_by_id(self, entry_id: str, update_access_time: bool = True) -> Optional[str]:
        """
        Retrieve and decrypt secret by entry ID.

        Args:
            entry_id: Entry UUID
            update_access_time: Whether to update accessed_at timestamp

        Returns:
            Decrypted secret value, or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM encrypted_entries WHERE id = ?
            """, (entry_id,))

            row = cursor.fetchone()
            if row is None:
                return None

            # Parse entry
            entry = EncryptedEntry.from_dict(dict(row))

            # Update access time
            if update_access_time:
                conn.execute("""
                    UPDATE encrypted_entries
                    SET accessed_at = ?
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), entry.id))
                conn.commit()

        # Decrypt (CLIENT-SIDE)
        try:
            associated_data = entry.service.encode('utf-8')
            plaintext = self.cipher.decrypt(
                entry.nonce,
                entry.encrypted_data,
                associated_data
            )
            return plaintext.decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed for ID {entry_id}: {e}")
            return None

    def search(self, filter: QueryFilter) -> List[EncryptedEntry]:
        """
        Search entries by metadata (NOT encrypted data).

        Server can search metadata but never sees plaintext secrets.

        Args:
            filter: Query filter

        Returns:
            List of encrypted entries (metadata only, no decryption)
        """
        # Build SQL query
        conditions = []
        params = []

        if filter.service:
            conditions.append("service = ?")
            params.append(filter.service)

        if filter.entry_type:
            conditions.append("entry_type = ?")
            params.append(filter.entry_type.value)

        if filter.tags:
            if filter.require_all_tags:
                # Match ALL tags
                for tag in filter.tags:
                    conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")
            else:
                # Match ANY tag
                tag_conditions = " OR ".join(["tags LIKE ?" for _ in filter.tags])
                conditions.append(f"({tag_conditions})")
                params.extend([f"%{tag}%" for tag in filter.tags])

        if filter.created_after:
            conditions.append("created_at >= ?")
            params.append(filter.created_after.isoformat())

        if filter.created_before:
            conditions.append("created_at <= ?")
            params.append(filter.created_before.isoformat())

        if filter.accessed_after:
            conditions.append("accessed_at >= ?")
            params.append(filter.accessed_after.isoformat())

        # Build WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Build ORDER BY
        order_direction = "DESC" if filter.sort_desc else "ASC"
        order_by = f"{filter.sort_by} {order_direction}"

        # Execute query
        query = f"""
            SELECT * FROM encrypted_entries
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """
        params.extend([filter.limit or -1, filter.offset])

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        # Parse entries (return encrypted, no decryption)
        return [EncryptedEntry.from_dict(dict(row)) for row in rows]

    def delete(self, service: str) -> bool:
        """
        Delete entry by service name.

        Args:
            service: Service name to delete

        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM encrypted_entries WHERE service = ?
            """, (service,))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Deleted entry: {service}")
        return deleted

    def delete_by_id(self, entry_id: str) -> bool:
        """
        Delete entry by ID.

        Args:
            entry_id: Entry UUID

        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM encrypted_entries WHERE id = ?
            """, (entry_id,))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Deleted entry ID: {entry_id}")
        return deleted

    def list_services(self) -> List[str]:
        """Get list of all service names."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT DISTINCT service FROM encrypted_entries ORDER BY service
            """)
            return [row[0] for row in cursor.fetchall()]

    def get_stats(self) -> VaultStats:
        """Get vault statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Total entries
            total = conn.execute("SELECT COUNT(*) FROM encrypted_entries").fetchone()[0]

            # Entries by type
            type_counts = {}
            for row in conn.execute("SELECT entry_type, COUNT(*) FROM encrypted_entries GROUP BY entry_type"):
                type_counts[row[0]] = row[1]

            # Unique services
            services = [row[0] for row in conn.execute("SELECT DISTINCT service FROM encrypted_entries ORDER BY service")]

            # Unique tags
            tag_set = set()
            for row in conn.execute("SELECT tags FROM encrypted_entries WHERE tags IS NOT NULL AND tags != ''"):
                if row[0]:
                    tag_set.update(row[0].split(','))
            tags = sorted(tag_set)

            # Size
            total_size = conn.execute("SELECT SUM(LENGTH(encrypted_data)) FROM encrypted_entries").fetchone()[0] or 0

            # Timestamps
            oldest = conn.execute("SELECT MIN(created_at) FROM encrypted_entries").fetchone()[0]
            newest = conn.execute("SELECT MAX(created_at) FROM encrypted_entries").fetchone()[0]
            last_accessed = conn.execute("SELECT MAX(accessed_at) FROM encrypted_entries").fetchone()[0]

        return VaultStats(
            total_entries=total,
            entries_by_type=type_counts,
            services=services,
            tags=tags,
            total_size_bytes=total_size // 2,  # Hex encoding doubles size
            oldest_entry=datetime.fromisoformat(oldest) if oldest else None,
            newest_entry=datetime.fromisoformat(newest) if newest else None,
            last_accessed=datetime.fromisoformat(last_accessed) if last_accessed else None
        )

    def close(self):
        """Close database connection and zero master key."""
        # Securely zero the master key
        if self.master_key:
            # Convert to bytearray for mutability, then zero
            if isinstance(self.master_key, bytes):
                # bytes are immutable, so we can't zero them in place
                # Best we can do is delete the reference
                del self.master_key
                self.master_key = None
            elif isinstance(self.master_key, bytearray):
                # bytearray is mutable
                for i in range(len(self.master_key)):
                    self.master_key[i] = 0

        logger.info("Closed EncryptedKVStore")
