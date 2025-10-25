"""
Integration tests for end-to-end workflows.

These tests verify complete workflows work correctly from start to finish.
"""

import unittest
import torch
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dora_crypto import EncryptedDoRAManager, generate_secure_password


class TestEndToEndWorkflow(unittest.TestCase):
    """Test complete encryption → decryption → cleanup workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_complete_encryption_decryption_cycle(self):
        """Test full cycle: create weights → encrypt → decrypt → verify."""
        # Step 1: Create mock adapter weights
        original_weights = {
            'layer.0.lora_A': torch.randn(16, 768),
            'layer.0.lora_B': torch.randn(768, 16),
            'layer.0.magnitude': torch.ones(768),
            'layer.1.lora_A': torch.randn(16, 768),
            'layer.1.lora_B': torch.randn(768, 16),
            'layer.1.magnitude': torch.ones(768) * 0.8,
        }

        # Save copies for verification
        original_copies = {k: v.clone() for k, v in original_weights.items()}

        # Step 2: Create mock model
        class MockModule:
            def __init__(self, weights, name):
                self.name = name

                class LoraDefault:
                    def __init__(self, data):
                        self.weight = type('obj', (object,), {'data': data})

                class LoraA:
                    def __init__(self, data):
                        self.default = LoraDefault(data)

                class LoraB:
                    def __init__(self, data):
                        self.default = LoraDefault(data)

                class Magnitude:
                    def __init__(self, data):
                        self.weight = type('obj', (object,), {'data': data})

                self.lora_A = LoraA(weights[f'{name}.lora_A'])
                self.lora_B = LoraB(weights[f'{name}.lora_B'])
                self.weight_m_wdecomp = Magnitude(weights[f'{name}.magnitude'])

        class MockModel:
            def __init__(self, weights):
                self.weights = weights

            def named_modules(self):
                return [
                    ('layer.0', MockModule(self.weights, 'layer.0')),
                    ('layer.1', MockModule(self.weights, 'layer.1')),
                ]

        model = MockModel(original_weights)

        # Step 3: Encrypt
        crypto_manager = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True
        )

        encrypted_path = os.path.join(self.temp_dir, 'adapter.enc')
        metadata = crypto_manager.extract_and_encrypt_dora_weights(
            model,
            encrypted_path
        )

        # Step 4: Verify encryption metadata
        self.assertIn('metadata', metadata)
        self.assertEqual(metadata['metadata']['num_tensors'], len(original_weights))
        self.assertTrue(os.path.exists(encrypted_path))
        self.assertGreater(os.path.getsize(encrypted_path), 0)

        # Step 5: Decrypt
        decrypted_weights = crypto_manager.decrypt_and_load_dora_weights(
            encrypted_path
        )

        # Step 6: Verify decryption
        self.assertEqual(set(decrypted_weights.keys()), set(original_copies.keys()))

        for key in original_copies.keys():
            self.assertTrue(
                torch.allclose(decrypted_weights[key], original_copies[key]),
                f"Mismatch in {key}"
            )

    def test_multiple_encryption_keys(self):
        """Test that different keys produce different ciphertexts."""
        weights = {
            'layer.0.lora_A': torch.randn(16, 768),
        }

        class MockModel:
            def named_modules(self):
                return []

        # Encrypt with key 1
        key1 = generate_secure_password()
        manager1 = EncryptedDoRAManager(key1, enable_compression=False)
        path1 = os.path.join(self.temp_dir, 'adapter1.enc')
        manager1._encrypt_weights_dict(weights, path1)

        # Encrypt with key 2
        key2 = generate_secure_password()
        manager2 = EncryptedDoRAManager(key2, enable_compression=False)
        path2 = os.path.join(self.temp_dir, 'adapter2.enc')
        manager2._encrypt_weights_dict(weights, path2)

        # Read both encrypted files
        with open(path1, 'r') as f:
            data1 = f.read()
        with open(path2, 'r') as f:
            data2 = f.read()

        # Ciphertexts should be different
        self.assertNotEqual(data1, data2)

    def test_adapter_cache_integration(self):
        """Test adapter cache with encryption/decryption."""
        from src.utils.adapter_cache import AdapterCache

        cache = AdapterCache(max_size=3)

        # Create and encrypt adapters
        crypto_manager = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True
        )

        adapters = []
        for i in range(3):
            weights = {
                f'layer.{i}.lora_A': torch.randn(16, 768),
                f'layer.{i}.lora_B': torch.randn(768, 16),
            }

            encrypted_path = os.path.join(self.temp_dir, f'adapter{i}.enc')
            crypto_manager._encrypt_weights_dict(weights, encrypted_path)

            # Decrypt and cache
            decrypted = crypto_manager.decrypt_and_load_dora_weights(encrypted_path)
            cache.put(encrypted_path, self.encryption_key, decrypted)

            adapters.append((encrypted_path, weights))

        # Verify all cached
        self.assertEqual(cache.size, 3)

        # Access first adapter (should be cache hit)
        cached = cache.get(adapters[0][0], self.encryption_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cache.hits, 1)


class TestErrorScenarios(unittest.TestCase):
    """Test error handling and edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_decrypt_with_wrong_key(self):
        """Test that wrong key fails to decrypt."""
        weights = {'layer.0.lora_A': torch.randn(16, 768)}

        # Encrypt with key1
        key1 = generate_secure_password()
        manager1 = EncryptedDoRAManager(key1, enable_compression=False)
        encrypted_path = os.path.join(self.temp_dir, 'adapter.enc')
        manager1._encrypt_weights_dict(weights, encrypted_path)

        # Try to decrypt with key2
        key2 = generate_secure_password()
        manager2 = EncryptedDoRAManager(key2, enable_compression=False)

        with self.assertRaises(ValueError):
            manager2.decrypt_and_load_dora_weights(encrypted_path)

    def test_decrypt_tampered_data(self):
        """Test that tampered data fails authentication."""
        weights = {'layer.0.lora_A': torch.randn(16, 768)}

        # Encrypt
        manager = EncryptedDoRAManager(self.encryption_key, enable_compression=False)
        encrypted_path = os.path.join(self.temp_dir, 'adapter.enc')
        manager._encrypt_weights_dict(weights, encrypted_path)

        # Tamper with file
        import json
        with open(encrypted_path, 'r') as f:
            data = json.load(f)

        # Modify ciphertext
        data['ciphertext'] = data['ciphertext'][:-20] + "TAMPERED" + "=" * 12

        with open(encrypted_path, 'w') as f:
            json.dump(data, f)

        # Decryption should fail
        with self.assertRaises(ValueError):
            manager.decrypt_and_load_dora_weights(encrypted_path)

    def test_decrypt_corrupt_file(self):
        """Test that corrupt file is handled gracefully."""
        encrypted_path = os.path.join(self.temp_dir, 'corrupt.enc')

        # Write invalid JSON
        with open(encrypted_path, 'w') as f:
            f.write("This is not valid JSON!")

        manager = EncryptedDoRAManager(self.encryption_key)

        with self.assertRaises(Exception):  # Should raise some exception
            manager.decrypt_and_load_dora_weights(encrypted_path)

    def test_encrypt_empty_weights(self):
        """Test encrypting empty weights dictionary."""
        weights = {}

        manager = EncryptedDoRAManager(self.encryption_key)
        encrypted_path = os.path.join(self.temp_dir, 'empty.enc')

        # Should handle gracefully
        manager._encrypt_weights_dict(weights, encrypted_path)

        # Should decrypt to empty dict
        decrypted = manager.decrypt_and_load_dora_weights(encrypted_path)
        self.assertEqual(len(decrypted), 0)

    def test_cache_eviction_cleanup(self):
        """Test that evicted cache entries are properly cleaned."""
        from src.utils.adapter_cache import AdapterCache

        cache = AdapterCache(max_size=2)

        # Add 3 adapters (should evict first)
        for i in range(3):
            weights = {f'tensor_{i}': torch.randn(100, 100)}
            cache.put(f'/adapter{i}.json', self.encryption_key, weights)

        # Should only have 2 (last two)
        self.assertEqual(cache.size, 2)

        # First should be evicted
        self.assertIsNone(cache.get('/adapter0.json', self.encryption_key))

        # Last two should be present
        self.assertIsNotNone(cache.get('/adapter1.json', self.encryption_key))
        self.assertIsNotNone(cache.get('/adapter2.json', self.encryption_key))


if __name__ == '__main__':
    unittest.main()
