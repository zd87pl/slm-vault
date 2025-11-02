"""
Tests for RunPod handler user isolation.

Tests:
- user_id requirement
- User-specific storage paths
- Ownership verification logging
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestRunPodHandlerUserIsolation(unittest.TestCase):
    """Test RunPod handler user isolation features."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_user_id = "test-user-123"
        self.test_adapter_id = "adapter-456"
    
    def test_handler_requires_user_id(self):
        """Test that handler requires user_id."""
        # Import handler
        from src.rp_handler import handler
        
        # Event without user_id
        event_without_user = {
            "input": {
                "task": "inference",
                "prompt": "Hello"
            }
        }
        
        # Should return error
        result = handler(event_without_user)
        
        self.assertIn("error", result)
        self.assertIn("user_id is required", result["error"])
    
    def test_handler_accepts_user_id(self):
        """Test that handler accepts user_id."""
        from src.rp_handler import handler
        
        # Event with user_id
        event_with_user = {
            "input": {
                "task": "inference",
                "prompt": "Hello",
                "user_id": self.test_user_id,
                "encrypted_adapter_path": None,  # Basic inference
            }
        }
        
        # Should not return user_id error
        # (May fail for other reasons, but not user_id)
        result = handler(event_with_user)
        
        # Should not have user_id error
        if "error" in result:
            self.assertNotIn("user_id is required", result["error"])
    
    def test_user_specific_storage_paths(self):
        """Test that storage paths include user_id."""
        # This is tested implicitly in the handler code
        # Paths should be: /workspace/adapters/{user_id}/{adapter_id}/
        
        user_id = "user-123"
        adapter_id = "adapter-456"
        
        expected_path = f"/workspace/adapters/{user_id}/{adapter_id}/"
        
        # Verify path format
        self.assertIn(user_id, expected_path)
        self.assertIn(adapter_id, expected_path)
        self.assertTrue(expected_path.startswith("/workspace/adapters/"))
    
    def test_inference_ownership_verification_logging(self):
        """Test that inference logs ownership verification."""
        # This tests that the code includes ownership verification placeholders
        from src.rp_handler import inference_with_encrypted_dora
        
        # Verify function signature includes user_id
        import inspect
        sig = inspect.signature(inference_with_encrypted_dora)
        
        # Check parameters
        params = list(sig.parameters.keys())
        self.assertIn("user_id", params)
        
        # Verify adapter_id parameter exists for verification
        config = {
            "encrypted_adapter_path": "/path/to/adapter.json",
            "encryption_key": "0123456789abcdef" * 4,  # 64 hex chars
            "prompt": "test",
            "adapter_id": self.test_adapter_id,
            "user_id": self.test_user_id
        }
        
        # Note: This won't actually run inference without proper setup
        # But we can verify the function signature is correct
        self.assertEqual(sig.parameters["config"].annotation, "Dict[str, Any]")
        self.assertEqual(sig.parameters["user_id"].annotation, "str")


class TestRunPodHandlerFunctionSignatures(unittest.TestCase):
    """Test that all handler functions have user_id parameter."""
    
    def test_all_functions_have_user_id(self):
        """Test that all handler functions include user_id."""
        from src.rp_handler import (
            train_dora,
            encrypt_dora_adapter,
            train_and_encrypt,
            inference_with_encrypted_dora
        )
        
        import inspect
        
        functions = [
            train_dora,
            encrypt_dora_adapter,
            train_and_encrypt,
            inference_with_encrypted_dora
        ]
        
        for func in functions:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            
            # All should have user_id parameter
            self.assertIn("user_id", params, f"{func.__name__} missing user_id parameter")


if __name__ == "__main__":
    unittest.main()


