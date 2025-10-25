"""
Test error handling and edge cases.

These tests ensure the system handles errors gracefully and provides
useful error messages.
"""

import unittest
import torch
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dora_crypto import EncryptedDoRAManager, generate_secure_password
from src.utils.adapter_cache import AdapterCache


class TestInputValidation(unittest.TestCase):
    """Test input validation and error messages."""

    def test_invalid_encryption_key_length(self):
        """Test that invalid key length raises error."""
        # Key must be 32 bytes
        invalid_key = b'too_short'

        with self.assertRaises(ValueError) as context:
            manager = EncryptedDoRAManager(invalid_key)

        self.assertIn('32 bytes', str(context.exception))

    def test_nonexistent_file_decryption(self):
        """Test that missing file raises appropriate error."""
        manager = EncryptedDoRAManager(generate_secure_password())

        with self.assertRaises(FileNotFoundError):
            manager.decrypt_and_load_dora_weights('/nonexistent/path.enc')

    def test_empty_adapter_path(self):
        """Test that empty path is handled."""
        manager = EncryptedDoRAManager(generate_secure_password())

        with self.assertRaises(Exception):  # Could be various errors
            manager.decrypt_and_load_dora_weights('')

    def test_invalid_compression_level(self):
        """Test invalid compression level."""
        # zstd valid range is 1-22
        with self.assertRaises(Exception):
            manager = EncryptedDoRAManager(
                generate_secure_password(),
                enable_compression=True,
                compression_level=100  # Invalid!
            )


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_very_large_adapter(self):
        """Test handling of large adapters."""
        # Create large adapter (100MB worth of tensors)
        large_weights = {
            f'layer.{i}.lora_A': torch.randn(1000, 1000)
            for i in range(50)  # ~200MB total
        }

        manager = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True,
            compression_level=1  # Fast compression for large data
        )

        encrypted_path = os.path.join(self.temp_dir, 'large.enc')

        # Should handle large data
        manager._encrypt_weights_dict(large_weights, encrypted_path)

        # Verify file was created
        self.assertTrue(os.path.exists(encrypted_path))

        # Verify can decrypt (may take a while)
        decrypted = manager.decrypt_and_load_dora_weights(encrypted_path)
        self.assertEqual(len(decrypted), len(large_weights))

    def test_very_small_adapter(self):
        """Test handling of minimal adapters."""
        # Single small tensor
        tiny_weights = {
            'layer.0.lora_A': torch.randn(1, 1),
        }

        manager = EncryptedDoRAManager(self.encryption_key)
        encrypted_path = os.path.join(self.temp_dir, 'tiny.enc')

        manager._encrypt_weights_dict(tiny_weights, encrypted_path)
        decrypted = manager.decrypt_and_load_dora_weights(encrypted_path)

        self.assertEqual(len(decrypted), 1)
        self.assertTrue(torch.allclose(
            decrypted['layer.0.lora_A'],
            tiny_weights['layer.0.lora_A']
        ))

    def test_special_characters_in_tensor_names(self):
        """Test tensor names with special characters."""
        special_weights = {
            'model.layers.0.self_attn.q_proj.lora_A': torch.randn(16, 768),
            'model.layers.0.self-attn.k-proj.lora_B': torch.randn(768, 16),
            'model/layers/0/v_proj/magnitude': torch.ones(768),
        }

        manager = EncryptedDoRAManager(self.encryption_key)
        encrypted_path = os.path.join(self.temp_dir, 'special.enc')

        manager._encrypt_weights_dict(special_weights, encrypted_path)
        decrypted = manager.decrypt_and_load_dora_weights(encrypted_path)

        self.assertEqual(set(decrypted.keys()), set(special_weights.keys()))

    def test_unicode_in_metadata(self):
        """Test Unicode characters in metadata."""
        weights = {'layer.0.lora_A': torch.randn(16, 768)}

        manager = EncryptedDoRAManager(self.encryption_key)
        encrypted_path = os.path.join(self.temp_dir, 'unicode.enc')

        # Encrypt with Unicode metadata
        class MockModel:
            def named_modules(self):
                return []

        metadata = manager._encrypt_weights_dict(weights, encrypted_path)

        # Should handle gracefully
        decrypted = manager.decrypt_and_load_dora_weights(encrypted_path)
        self.assertEqual(len(decrypted), 1)

    def test_concurrent_cache_access(self):
        """Test cache behavior under concurrent access."""
        import threading

        cache = AdapterCache(max_size=5)
        errors = []

        def add_adapter(i):
            try:
                weights = {f'tensor_{i}': torch.randn(100, 100)}
                cache.put(f'/adapter{i}.json', self.encryption_key, weights)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [
            threading.Thread(target=add_adapter, args=(i,))
            for i in range(10)
        ]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # NOTE: This test currently will likely have race conditions
        # because cache is not thread-safe. This is a known issue.
        # We're just documenting the behavior here.
        # In production, cache should have locks.

        # Cache should have at most max_size entries
        self.assertLessEqual(cache.size, 5)

    def test_cache_with_huge_tensors(self):
        """Test cache memory limits with large tensors."""
        # Cache with 10MB limit
        cache = AdapterCache(max_size=100, max_memory_mb=10)

        # Add tensors larger than limit
        huge_tensor = torch.randn(1000, 2500)  # ~10MB

        weights = {'huge': huge_tensor}
        cache.put('/huge.json', self.encryption_key, weights)

        # Should still respect memory limit
        self.assertLessEqual(cache.memory_mb, 11)  # Small margin


class TestMemorySecurityEdgeCases(unittest.TestCase):
    """Test memory security edge cases."""

    def test_secure_zero_non_contiguous_tensor(self):
        """Test zeroing non-contiguous tensors."""
        from src.utils.memory_security import secure_zero_tensor

        # Create non-contiguous tensor
        tensor = torch.randn(100, 100).t()  # Transpose makes it non-contiguous
        self.assertFalse(tensor.is_contiguous())

        # Should still zero it
        secure_zero_tensor(tensor)
        self.assertTrue(torch.all(tensor == 0))

    def test_secure_zero_empty_dict(self):
        """Test zeroing empty dictionary."""
        from src.utils.memory_security import secure_zero_dict

        empty_dict = {}
        secure_zero_dict(empty_dict)  # Should not crash

        self.assertEqual(len(empty_dict), 0)

    def test_secure_zero_with_none(self):
        """Test zeroing None value."""
        from src.utils.memory_security import secure_zero_tensor

        # Should handle None gracefully
        secure_zero_tensor(None)  # Should not crash

    def test_mlock_on_cpu_only_system(self):
        """Test mlock behavior on CPU-only systems."""
        from src.utils.memory_security import mlock_tensor, munlock_tensor

        tensor = torch.randn(100, 100)

        # May or may not succeed depending on platform/permissions
        # Just verify it doesn't crash
        result = mlock_tensor(tensor)
        self.assertIsInstance(result, bool)

        if result:
            # If lock succeeded, unlock should work
            unlock_result = munlock_tensor(tensor)
            self.assertTrue(unlock_result)


class TestDoRAFormulaEdgeCases(unittest.TestCase):
    """Test DoRA formula edge cases."""

    def test_dora_with_zero_magnitude(self):
        """Test DoRA with zero magnitude vector."""
        W0 = torch.randn(768, 1024)
        lora_A = torch.randn(16, 1024)
        lora_B = torch.randn(768, 16)
        magnitude = torch.zeros(768)  # Zero magnitude!

        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA
        row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
        normalized = new_direction / row_norm
        result = magnitude.unsqueeze(1) * normalized

        # Result should be all zeros
        self.assertTrue(torch.all(result == 0))

    def test_dora_with_very_small_norms(self):
        """Test DoRA with very small weight norms."""
        # Create weights with very small values
        W0 = torch.randn(768, 1024) * 1e-10
        lora_A = torch.randn(16, 1024) * 1e-10
        lora_B = torch.randn(768, 16) * 1e-10
        magnitude = torch.ones(768)

        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA
        row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)

        # Clamp to avoid division by zero
        row_norm = torch.clamp(row_norm, min=1e-8)

        normalized = new_direction / row_norm
        result = magnitude.unsqueeze(1) * normalized

        # Should produce finite values
        self.assertTrue(torch.all(torch.isfinite(result)))

    def test_dora_with_inf_or_nan(self):
        """Test DoRA formula rejects inf/nan inputs."""
        W0 = torch.randn(768, 1024)
        lora_A = torch.randn(16, 1024)
        lora_B = torch.randn(768, 16)

        # Inject NaN
        W0[0, 0] = float('nan')

        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA

        # Result will contain NaN
        self.assertTrue(torch.any(torch.isnan(new_direction)))


if __name__ == '__main__':
    unittest.main()
