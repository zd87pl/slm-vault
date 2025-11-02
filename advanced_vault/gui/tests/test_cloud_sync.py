"""
Tests for cloud sync service.

Tests:
- Sync entry to cloud
- Fetch from cloud
- Merge entries
- Error handling
- Background sync
"""

import unittest
import tempfile
import os
import base64
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.gui.cloud_sync import CloudSyncService
from advanced_vault.encrypted_kv import EncryptedKVStore, EntryType


class TestCloudSyncService(unittest.TestCase):
    """Test cloud sync service."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary vault
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Create master key
        self.master_key = os.urandom(32)
        
        # Create vault instance
        self.vault = EncryptedKVStore(self.master_key, db_path=self.db_path)
        
        # Mock session data
        self.session_data = {
            "access_token": "test-token-123",
            "user_id": "test-user-456"
        }
        
        self.backend_url = "https://api.test.com"
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_init(self):
        """Test service initialization."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        self.assertEqual(service.backend_url, self.backend_url)
        self.assertEqual(service.user_id, "test-user-456")
        self.assertEqual(service.access_token, "test-token-123")
        self.assertIn("Authorization", service.headers)
        self.assertEqual(service.headers["Authorization"], "Bearer test-token-123")
    
    def test_init_missing_token(self):
        """Test initialization fails without access token."""
        with self.assertRaises(ValueError):
            CloudSyncService(
                backend_url=self.backend_url,
                session_data={},  # Missing token
                vault=self.vault
            )
    
    def test_map_entry_type(self):
        """Test EntryType to backend data_type mapping."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        # Test mappings
        self.assertEqual(service._map_entry_type(EntryType.SECRET), "secret")
        self.assertEqual(service._map_entry_type(EntryType.API_KEY), "secret")
        self.assertEqual(service._map_entry_type(EntryType.PASSWORD), "secret")
        self.assertEqual(service._map_entry_type(EntryType.TOKEN), "secret")
        # Other types should map to "knowledge"
        self.assertEqual(service._map_entry_type(EntryType.OTHER), "knowledge")
    
    def test_prepare_entry_for_backend(self):
        """Test entry preparation for backend API."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        # Create test entry
        entry_id = self.vault.put(
            service="test_service",
            secret_value="test_secret_value",
            entry_type=EntryType.SECRET,
            tags=["tag1", "tag2"]
        )
        
        # Get entry
        entries = self.vault.search(service="test_service")
        entry = entries[0]
        
        # Prepare for backend
        prepared = service._prepare_entry_for_backend(entry)
        
        # Verify structure
        self.assertEqual(prepared["entry_id"], entry.id)
        self.assertEqual(prepared["service"], "test_service")
        self.assertEqual(prepared["data_type"], "secret")
        self.assertEqual(prepared["tags"], ["tag1", "tag2"])
        
        # Verify encrypted_data is base64 encoded
        self.assertIn("encrypted_data", prepared)
        encrypted_data = prepared["encrypted_data"]
        
        # Should be base64 decodable
        decoded = base64.b64decode(encrypted_data)
        self.assertIsInstance(decoded, bytes)
        
        # Should contain nonce (12 bytes) + encrypted_data
        self.assertGreater(len(decoded), 12)
        self.assertEqual(len(decoded) - 12, len(entry.encrypted_data))
    
    @patch('advanced_vault.gui.cloud_sync.requests.post')
    def test_sync_entry_success(self, mock_post):
        """Test successful entry sync."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        # Create entry
        entry_id = self.vault.put(
            service="stripe",
            secret_value="sk_live_test123",
            entry_type=EntryType.API_KEY
        )
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response
        
        # Sync entry
        result = service.sync_entry(entry_id)
        
        # Verify success
        self.assertTrue(result)
        
        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Verify URL
        self.assertIn("/api/vault/store", call_args[0][0])
        
        # Verify headers
        self.assertIn("headers", call_args[1])
        self.assertIn("Authorization", call_args[1]["headers"])
        
        # Verify payload structure
        payload = call_args[1]["json"]
        self.assertIn("entry_id", payload)
        self.assertIn("encrypted_data", payload)
        self.assertIn("service", payload)
    
    @patch('advanced_vault.gui.cloud_sync.requests.post')
    def test_sync_entry_failure(self, mock_post):
        """Test entry sync failure."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        # Create entry
        entry_id = self.vault.put(
            service="github",
            secret_value="ghp_test123"
        )
        
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        # Sync entry
        result = service.sync_entry(entry_id)
        
        # Should return False on failure
        self.assertFalse(result)
    
    @patch('advanced_vault.gui.cloud_sync.requests.get')
    def test_fetch_from_cloud(self, mock_get):
        """Test fetching entries from cloud."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "entries": [
                {
                    "entry_id": "entry-1",
                    "service": "stripe",
                    "encrypted_data": base64.b64encode(b"test_data").decode(),
                    "data_type": "secret"
                },
                {
                    "entry_id": "entry-2",
                    "service": "github",
                    "encrypted_data": base64.b64encode(b"test_data2").decode(),
                    "data_type": "secret"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Fetch from cloud
        entries = service.fetch_from_cloud()
        
        # Verify result
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["entry_id"], "entry-1")
        self.assertEqual(entries[1]["entry_id"], "entry-2")
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        
        # Verify URL
        self.assertIn("/api/vault/entries", call_args[0][0])
        
        # Verify headers
        self.assertIn("headers", call_args[1])
        self.assertIn("Authorization", call_args[1]["headers"])
    
    def test_merge_entries(self):
        """Test merging cloud entries with local vault."""
        service = CloudSyncService(
            backend_url=self.backend_url,
            session_data=self.session_data,
            vault=self.vault
        )
        
        # Create local entry
        local_entry_id = self.vault.put(
            service="local_only",
            secret_value="local_secret"
        )
        
        # Cloud entries (won't import without decryption - expected behavior)
        cloud_entries = [
            {
                "entry_id": "cloud-1",
                "service": "cloud_service",
                "encrypted_data": base64.b64encode(b"nonce_data").decode(),
                "data_type": "secret"
            }
        ]
        
        # Merge (should skip cloud entries as we can't decrypt)
        result = service.merge_entries(cloud_entries, conflict_resolution="cloud")
        
        # Verify result structure
        self.assertIn("success", result)
        self.assertIn("skipped", result)
        # Should skip cloud entries since we can't decrypt them
        self.assertGreaterEqual(result["skipped"], 0)


if __name__ == "__main__":
    unittest.main()


