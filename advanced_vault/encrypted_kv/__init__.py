"""
Encrypted Key-Value Store (Layer 1)

ProtonMail-style E2EE storage for exact data (API keys, passwords, tokens).

Features:
- Client-side encryption (server never sees plaintext)
- XChaCha20-Poly1305 authenticated encryption
- Unique nonce per entry (semantic security)
- Metadata search (service, tags, timestamps)
- Zero hallucination (exact retrieval, no LLM)

Usage:
    from advanced_vault.encrypted_kv import EncryptedKVStore, EntryType

    # Initialize
    master_key = os.urandom(32)  # 256-bit key
    store = EncryptedKVStore(master_key)

    # Store secret
    store.put("stripe", "sk_live_ABC123", entry_type=EntryType.API_KEY, tags=["payment"])

    # Retrieve secret
    key = store.get("stripe")
    assert key == "sk_live_ABC123"  # Exact match, no hallucination

    # Search by metadata
    filter = QueryFilter(tags=["payment"])
    entries = store.search(filter)
"""

from .storage import EncryptedKVStore
from .models import (
    EncryptedEntry,
    EntryType,
    QueryFilter,
    VaultStats
)

__all__ = [
    "EncryptedKVStore",
    "EncryptedEntry",
    "EntryType",
    "QueryFilter",
    "VaultStats"
]
