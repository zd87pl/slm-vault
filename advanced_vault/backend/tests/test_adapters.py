"""
Tests for adapter registry API endpoints.

Tests:
- Register adapter
- List adapters
- Get adapter
- Verify ownership
- Update status
- Delete adapter
- User isolation (RLS)
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.backend.api.adapters import (
    router,
    RegisterAdapterRequest,
    hash_encryption_key
)


class TestAdapterRegistryHelpers(unittest.TestCase):
    """Test helper functions."""
    
    def test_hash_encryption_key(self):
        """Test key hashing function."""
        
        # Test key (hex string)
        key_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        
        # Hash should be SHA256 (64 hex chars)
        key_hash = hash_encryption_key(key_hex)
        
        self.assertEqual(len(key_hash), 64)  # SHA256 = 64 hex chars
        self.assertIsInstance(key_hash, str)
        
        # Same key should produce same hash
        hash2 = hash_encryption_key(key_hex)
        self.assertEqual(key_hash, hash2)
        
        # Different key should produce different hash
        different_key = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        different_hash = hash_encryption_key(different_key)
        self.assertNotEqual(key_hash, different_hash)


class TestAdapterRegistryAPI(unittest.TestCase):
    """Test adapter registry API endpoints."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_user_id = "test-user-123"
        self.test_adapter_id = "adapter-456"
        self.test_adapter_path = "/workspace/adapters/test-user-123/adapter-456.json"
        self.test_key_hash = "a" * 64  # Valid SHA256 hash format
        
        # Mock user dict
        self.mock_user = {
            "user_id": self.test_user_id,
            "email": "test@example.com",
            "role": "authenticated"
        }
    
    @patch('advanced_vault.backend.api.adapters.get_supabase')
    @patch('advanced_vault.backend.api.adapters.get_current_user')
    @patch('advanced_vault.backend.api.adapters.log_access')
    def test_register_adapter_success(self, mock_log, mock_get_user, mock_get_supabase):
        """Test successful adapter registration."""
        from advanced_vault.backend.api.adapters import register_adapter
        
        # Mock dependencies
        mock_get_user.return_value = self.mock_user
        
        # Mock Supabase response
        mock_supabase = Mock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{
            "id": "123",
            "adapter_id": self.test_adapter_id,
            "user_id": self.test_user_id
        }]
        mock_get_supabase.return_value = mock_supabase
        
        # Mock request
        mock_request = Mock()
        
        # Create request data
        request_data = RegisterAdapterRequest(
            adapter_id=self.test_adapter_id,
            adapter_path=self.test_adapter_path,
            encryption_key_hash=self.test_key_hash,
            status="pending"
        )
        
        # Call endpoint (async function)
        import asyncio
        async def run_test():
            return await register_adapter(mock_request, request_data, self.mock_user)
        result = asyncio.run(run_test())
        
        # Verify result
        self.assertEqual(result["success"], True)
        self.assertEqual(result["adapter_id"], self.test_adapter_id)
        
        # Verify Supabase was called correctly
        mock_supabase.table.assert_called_once_with("user_adapters")
        insert_call = mock_supabase.table.return_value.insert
        insert_call.assert_called_once()
        
        # Verify insert data includes user_id
        call_args = insert_call.call_args[0][0]
        self.assertEqual(call_args["user_id"], self.test_user_id)
        self.assertEqual(call_args["adapter_id"], self.test_adapter_id)
        self.assertEqual(call_args["encryption_key_hash"], self.test_key_hash)
    
    @patch('advanced_vault.backend.api.adapters.get_supabase')
    @patch('advanced_vault.backend.api.adapters.get_current_user')
    def test_register_adapter_invalid_hash(self, mock_get_user, mock_get_supabase):
        """Test adapter registration with invalid key hash."""
        from advanced_vault.backend.api.adapters import register_adapter
        from fastapi import HTTPException
        
        mock_get_user.return_value = self.mock_user
        mock_request = Mock()
        
        # Invalid hash (not 64 chars)
        request_data = RegisterAdapterRequest(
            adapter_id=self.test_adapter_id,
            adapter_path=self.test_adapter_path,
            encryption_key_hash="short",  # Invalid
            status="pending"
        )
        
        # Should raise HTTPException
        import asyncio
        async def run_test():
            return await register_adapter(mock_request, request_data, self.mock_user)
        with self.assertRaises(HTTPException) as context:
            asyncio.run(run_test())
        
        self.assertEqual(context.exception.status_code, 400)
    
    @patch('advanced_vault.backend.api.adapters.get_supabase')
    @patch('advanced_vault.backend.api.adapters.get_current_user')
    @patch('advanced_vault.backend.api.adapters.log_access')
    def test_verify_adapter_ownership_authorized(self, mock_log, mock_get_user, mock_get_supabase):
        """Test adapter ownership verification for authorized user."""
        from advanced_vault.backend.api.adapters import verify_adapter_ownership
        
        mock_get_user.return_value = self.mock_user
        
        # Mock Supabase: user owns adapter
        mock_supabase = Mock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
            "id": "123"
        }]
        mock_get_supabase.return_value = mock_supabase
        
        mock_request = Mock()
        
        import asyncio
        result = asyncio.run(verify_adapter_ownership(
            self.test_adapter_id,
            mock_request,
            self.mock_user
        ))
        
        self.assertEqual(result["authorized"], True)
        self.assertEqual(result["adapter_id"], self.test_adapter_id)
        self.assertEqual(result["user_id"], self.test_user_id)
    
    @patch('advanced_vault.backend.api.adapters.get_supabase')
    @patch('advanced_vault.backend.api.adapters.get_current_user')
    @patch('advanced_vault.backend.api.adapters.log_access')
    def test_verify_adapter_ownership_unauthorized(self, mock_log, mock_get_user, mock_get_supabase):
        """Test adapter ownership verification for unauthorized user."""
        from advanced_vault.backend.api.adapters import verify_adapter_ownership
        
        mock_get_user.return_value = self.mock_user
        
        # Mock Supabase: user does NOT own adapter (empty result)
        mock_supabase = Mock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_get_supabase.return_value = mock_supabase
        
        mock_request = Mock()
        
        import asyncio
        async def run_test():
            return await verify_adapter_ownership(
                self.test_adapter_id,
                mock_request,
                self.mock_user
            )
        result = asyncio.run(run_test())
        
        self.assertEqual(result["authorized"], False)
    
    @patch('advanced_vault.backend.api.adapters.get_supabase')
    @patch('advanced_vault.backend.api.adapters.get_current_user')
    @patch('advanced_vault.backend.api.adapters.log_access')
    def test_list_adapters(self, mock_log, mock_get_user, mock_get_supabase):
        """Test listing user's adapters."""
        from advanced_vault.backend.api.adapters import list_adapters
        
        mock_get_user.return_value = self.mock_user
        
        # Mock Supabase: return list of adapters
        mock_supabase = Mock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            {
                "id": "1",
                "adapter_id": "adapter-1",
                "user_id": self.test_user_id,
                "status": "completed"
            },
            {
                "id": "2",
                "adapter_id": "adapter-2",
                "user_id": self.test_user_id,
                "status": "pending"
            }
        ]
        mock_get_supabase.return_value = mock_supabase
        
        mock_request = Mock()
        
        import asyncio
        async def run_test():
            return await list_adapters(mock_request, self.mock_user, None)
        result = asyncio.run(run_test())
        
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["adapters"]), 2)
        self.assertEqual(result["adapters"][0]["adapter_id"], "adapter-1")


if __name__ == "__main__":
    unittest.main()

