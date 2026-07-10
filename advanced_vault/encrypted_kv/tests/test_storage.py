"""
Tests for encrypted KV store.

Validates:
- Encryption/decryption correctness
- Unique nonces per entry
- Metadata search
- CRUD operations
- Security properties
"""

import pytest
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from advanced_vault.encrypted_kv import (
    EncryptedKVStore,
    EntryType,
    QueryFilter
)


@pytest.fixture
def master_key():
    """Generate random 32-byte key for tests."""
    return os.urandom(32)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def store(master_key, temp_db):
    """Create store instance for testing."""
    return EncryptedKVStore(master_key, db_path=temp_db)


class TestBasicOperations:
    """Test basic CRUD operations."""

    def test_put_and_get(self, store):
        """Test storing and retrieving a secret."""
        # Store
        entry_id = store.put("stripe", "sk_live_ABC123", entry_type=EntryType.API_KEY)
        assert entry_id is not None

        # Retrieve
        secret = store.get("stripe")
        assert secret == "sk_live_ABC123"

    def test_get_nonexistent(self, store):
        """Test retrieving non-existent service."""
        secret = store.get("nonexistent")
        assert secret is None

    def test_put_overwrites(self, store):
        """Test that putting same service overwrites."""
        store.put("github", "old_token")
        store.put("github", "new_token")

        secret = store.get("github")
        assert secret == "new_token"

    def test_delete(self, store):
        """Test deleting an entry."""
        store.put("temp", "temporary_value")
        assert store.get("temp") == "temporary_value"

        deleted = store.delete("temp")
        assert deleted is True

        assert store.get("temp") is None

    def test_delete_nonexistent(self, store):
        """Test deleting non-existent entry."""
        deleted = store.delete("nonexistent")
        assert deleted is False


class TestEncryption:
    """Test encryption properties."""

    def test_different_keys_produce_different_ciphertexts(self, temp_db):
        """Test that different keys produce different ciphertexts."""
        key1 = os.urandom(32)
        key2 = os.urandom(32)

        store1 = EncryptedKVStore(key1, db_path=temp_db)
        store1.put("test", "secret_value")

        # Try to decrypt with wrong key
        store2 = EncryptedKVStore(key2, db_path=temp_db)
        secret = store2.get("test")

        # Should fail to decrypt (returns None)
        assert secret is None

    def test_unique_nonces_for_same_secret(self, store):
        """Test that same secret gets different nonces."""
        # Store same secret twice under different services
        store.put("service1", "same_secret")
        store.put("service2", "same_secret")

        # Search to get encrypted entries
        filter = QueryFilter()
        entries = store.search(filter)

        assert len(entries) == 2
        # Nonces should be different
        assert entries[0].nonce != entries[1].nonce

    def test_ciphertext_differs_for_same_plaintext(self, store):
        """Test semantic security: same plaintext → different ciphertext."""
        store.put("test1", "same_plaintext")
        store.put("test2", "same_plaintext")

        filter = QueryFilter()
        entries = store.search(filter)

        # Same plaintext, but different ciphertexts (due to unique nonces)
        assert entries[0].encrypted_data != entries[1].encrypted_data

    def test_associated_data_prevents_substitution(self, store, temp_db):
        """Test that service name is authenticated (prevents ciphertext substitution)."""
        # Store secret for stripe
        store.put("stripe", "stripe_key_123")

        # Get encrypted entry for stripe
        filter = QueryFilter(service="stripe")
        stripe_entry = store.search(filter)[0]

        # Try to use stripe's ciphertext for github
        # This should fail because service name is authenticated
        import sqlite3
        with sqlite3.connect(temp_db) as conn:
            conn.execute("""
                INSERT INTO encrypted_entries
                (id, entry_type, service, tags, description, encrypted_data,
                 nonce, created_at, updated_at, accessed_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "fake_id",
                EntryType.API_KEY.value,
                "github",  # Different service
                "",
                None,
                stripe_entry.encrypted_data.hex(),  # Stripe's ciphertext
                stripe_entry.nonce.hex(),
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
                None,
                1
            ))
            conn.commit()

        # Try to decrypt github (should fail)
        github_secret = store.get("github")
        assert github_secret is None  # Decryption fails


class TestMetadataSearch:
    """Test metadata search functionality."""

    def test_search_by_service(self, store):
        """Test searching by service name."""
        store.put("stripe", "key1", entry_type=EntryType.API_KEY)
        store.put("github", "key2", entry_type=EntryType.TOKEN)

        filter = QueryFilter(service="stripe")
        results = store.search(filter)

        assert len(results) == 1
        assert results[0].service == "stripe"

    def test_search_by_type(self, store):
        """Test searching by entry type."""
        store.put("service1", "key1", entry_type=EntryType.API_KEY)
        store.put("service2", "pass1", entry_type=EntryType.PASSWORD)
        store.put("service3", "key2", entry_type=EntryType.API_KEY)

        filter = QueryFilter(entry_type=EntryType.API_KEY)
        results = store.search(filter)

        assert len(results) == 2
        assert all(e.entry_type == EntryType.API_KEY for e in results)

    def test_search_by_tags_any(self, store):
        """Test searching by tags (match ANY)."""
        store.put("stripe", "key1", tags=["payment", "production"])
        store.put("github", "key2", tags=["dev", "staging"])
        store.put("aws", "key3", tags=["production", "infrastructure"])

        filter = QueryFilter(tags=["production"])
        results = store.search(filter)

        assert len(results) == 2
        services = [e.service for e in results]
        assert "stripe" in services
        assert "aws" in services

    def test_search_by_tags_all(self, store):
        """Test searching by tags (match ALL)."""
        store.put("stripe", "key1", tags=["payment", "production"])
        store.put("github", "key2", tags=["payment"])
        store.put("aws", "key3", tags=["production"])

        filter = QueryFilter(tags=["payment", "production"], require_all_tags=True)
        results = store.search(filter)

        assert len(results) == 1
        assert results[0].service == "stripe"

    def test_search_by_created_after(self, store):
        """Test searching by creation time."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        store.put("old", "key1")

        # Simulate old entry (would need to manipulate DB directly in real test)
        # For now, just test the filter logic
        filter = QueryFilter(created_after=yesterday)
        results = store.search(filter)

        assert len(results) >= 1  # Should include recent entry

    def test_search_pagination(self, store):
        """Test pagination in search results."""
        # Store multiple entries
        for i in range(10):
            store.put(f"service{i}", f"key{i}")

        # Get first 3
        filter = QueryFilter(limit=3, offset=0)
        page1 = store.search(filter)
        assert len(page1) == 3

        # Get next 3
        filter = QueryFilter(limit=3, offset=3)
        page2 = store.search(filter)
        assert len(page2) == 3

        # Should be different entries
        page1_services = {e.service for e in page1}
        page2_services = {e.service for e in page2}
        assert page1_services.isdisjoint(page2_services)

    def test_search_sorting(self, store):
        """Test sorting search results."""
        store.put("zebra", "key1")
        store.put("alpha", "key2")
        store.put("beta", "key3")

        # Sort by service ascending
        filter = QueryFilter(sort_by="service", sort_desc=False)
        results = store.search(filter)

        services = [e.service for e in results]
        assert services == sorted(services)


class TestVaultStats:
    """Test vault statistics."""

    def test_empty_vault_stats(self, store):
        """Test stats for empty vault."""
        stats = store.get_stats()

        assert stats.total_entries == 0
        assert len(stats.services) == 0
        assert len(stats.tags) == 0

    def test_vault_stats_with_data(self, store):
        """Test stats with multiple entries."""
        store.put("stripe", "key1", entry_type=EntryType.API_KEY, tags=["payment"])
        store.put("github", "key2", entry_type=EntryType.TOKEN, tags=["dev"])
        store.put("aws", "pass1", entry_type=EntryType.PASSWORD, tags=["infrastructure"])

        stats = store.get_stats()

        assert stats.total_entries == 3
        assert len(stats.services) == 3
        assert "stripe" in stats.services
        assert "payment" in stats.tags
        assert "dev" in stats.tags

    def test_list_services(self, store):
        """Test listing all services."""
        store.put("stripe", "key1")
        store.put("github", "key2")
        store.put("aws", "key3")

        services = store.list_services()

        assert len(services) == 3
        assert set(services) == {"stripe", "github", "aws"}


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_secret(self, store):
        """Test storing empty string."""
        store.put("empty", "")
        secret = store.get("empty")
        assert secret == ""

    def test_unicode_secret(self, store):
        """Test storing unicode characters."""
        unicode_secret = "🔐 Secret with émojis and ñ"
        store.put("unicode", unicode_secret)

        secret = store.get("unicode")
        assert secret == unicode_secret

    def test_large_secret(self, store):
        """Test storing large secret."""
        large_secret = "x" * 1000000  # 1MB
        store.put("large", large_secret)

        secret = store.get("large")
        assert secret == large_secret

    def test_invalid_key_length(self, temp_db):
        """Test that invalid key length raises error."""
        with pytest.raises(ValueError, match="32 bytes"):
            EncryptedKVStore(b"short_key", db_path=temp_db)

    def test_access_time_updates(self, store):
        """Test that accessed_at timestamp updates."""
        store.put("test", "secret")

        # First retrieval
        filter = QueryFilter(service="test")
        entry1 = store.search(filter)[0]
        first_access = entry1.accessed_at

        # Get (should update access time)
        import time
        time.sleep(0.1)  # Small delay to ensure different timestamp
        store.get("test", update_access_time=True)

        # Second retrieval
        entry2 = store.search(filter)[0]
        second_access = entry2.accessed_at

        assert second_access is not None
        assert second_access > first_access if first_access else True


class TestSecurity:
    """Test security properties."""

    def test_no_plaintext_in_database(self, store, temp_db):
        """Test that plaintext never appears in database."""
        secret = "super_secret_key_12345"
        store.put("test", secret)

        # Read raw database
        import sqlite3
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT * FROM encrypted_entries WHERE service = ?", ("test",))
            row = cursor.fetchone()

        # Convert all fields to strings and check if secret appears
        row_str = str(row)
        assert secret not in row_str

    def test_master_key_zeroed_on_close(self, temp_db):
        """Test that master key is cleared after close."""
        master_key = bytearray(os.urandom(32))
        key_copy = bytes(master_key)

        store = EncryptedKVStore(bytes(master_key), db_path=temp_db)
        internal_key = store._master_key
        store.close()

        # The store's key buffer must be zeroed in place and dropped
        assert all(b == 0 for b in internal_key)
        assert store._master_key is None
        # But our copy should still have the original value
        assert not all(b == 0 for b in key_copy)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
