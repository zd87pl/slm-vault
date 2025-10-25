"""
Test suite for DoRA encryption/decryption functionality.
"""

import unittest
import torch
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dora_crypto import EncryptedDoRAManager, generate_secure_password
from src.utils.memory_security import secure_zero_dict


class TestEncryption(unittest.TestCase):
    """Test encryption and decryption of DoRA weights."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()
        self.crypto_manager = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True
        )
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up temp files
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_key_generation(self):
        """Test secure password generation."""
        key1 = generate_secure_password()
        key2 = generate_secure_password()

        # Keys should be 32 bytes
        self.assertEqual(len(key1), 32)
        self.assertEqual(len(key2), 32)

        # Keys should be random (different)
        self.assertNotEqual(key1, key2)

    def test_encryption_decryption_roundtrip(self):
        """Test that encryption and decryption produce identical weights."""
        # Create mock DoRA weights
        mock_weights = {
            "layer.0.lora_A": torch.randn(16, 768),
            "layer.0.lora_B": torch.randn(768, 16),
            "layer.0.magnitude": torch.ones(768),
            "layer.1.lora_A": torch.randn(16, 768),
            "layer.1.lora_B": torch.randn(768, 16),
            "layer.1.magnitude": torch.ones(768) * 0.5,
        }

        # Save original values
        original_values = {
            k: v.clone() for k, v in mock_weights.items()
        }

        # Create mock model with weights
        class MockModule:
            def __init__(self, weights):
                self.weights = weights

            def named_modules(self):
                modules = []
                for key in self.weights.keys():
                    module_name = key.rsplit('.', 1)[0]
                    if module_name not in [m[0] for m in modules]:
                        # Create mock module
                        class SubModule:
                            pass
                        sub = SubModule()

                        # Add weights to module
                        for k, v in self.weights.items():
                            if k.startswith(module_name):
                                weight_type = k.split('.')[-1]
                                if weight_type == 'lora_A':
                                    class LoraA:
                                        weight = type('obj', (object,), {'data': v})
                                    sub.lora_A = LoraA()
                                elif weight_type == 'lora_B':
                                    class LoraB:
                                        weight = type('obj', (object,), {'data': v})
                                    sub.lora_B = LoraB()
                                elif weight_type == 'magnitude':
                                    class Magnitude:
                                        weight = type('obj', (object,), {'data': v})
                                    sub.weight_m_wdecomp = Magnitude()

                        modules.append((module_name, sub))

                return modules

        mock_model = MockModule(mock_weights)

        # Encrypt
        encrypted_path = os.path.join(self.temp_dir, "encrypted_test.json")
        metadata = self.crypto_manager.extract_and_encrypt_dora_weights(
            mock_model,
            encrypted_path
        )

        # Verify encrypted file exists
        self.assertTrue(os.path.exists(encrypted_path))
        self.assertIn('metadata', metadata)
        self.assertEqual(metadata['metadata']['num_tensors'], len(mock_weights))

        # Decrypt
        decrypted_weights = self.crypto_manager.decrypt_and_load_dora_weights(
            encrypted_path
        )

        # Verify all keys present
        self.assertEqual(set(decrypted_weights.keys()), set(original_values.keys()))

        # Verify values match
        for key in original_values.keys():
            self.assertTrue(
                torch.allclose(original_values[key], decrypted_weights[key]),
                f"Mismatch in {key}"
            )

    def test_compression(self):
        """Test that compression reduces file size."""
        # Create large mock weights
        mock_weights = {
            f"layer.{i}.lora_A": torch.randn(32, 1024)
            for i in range(10)
        }

        class MockModel:
            def named_modules(self):
                return []  # Simplified for this test

        # Encrypt with compression
        manager_compressed = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True,
            compression_level=3
        )

        path_compressed = os.path.join(self.temp_dir, "compressed.json")
        manager_compressed._encrypt_weights_dict(mock_weights, path_compressed)

        # Encrypt without compression
        manager_uncompressed = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=False
        )

        path_uncompressed = os.path.join(self.temp_dir, "uncompressed.json")
        manager_uncompressed._encrypt_weights_dict(mock_weights, path_uncompressed)

        # Compressed should be smaller
        size_compressed = os.path.getsize(path_compressed)
        size_uncompressed = os.path.getsize(path_uncompressed)

        self.assertLess(size_compressed, size_uncompressed,
                       "Compressed file should be smaller")

    def test_authentication_failure(self):
        """Test that tampered data fails authentication."""
        # Create and encrypt mock weights
        mock_weights = {
            "layer.0.lora_A": torch.randn(16, 768),
        }

        class MockModel:
            def named_modules(self):
                return []

        encrypted_path = os.path.join(self.temp_dir, "tampered.json")
        manager = EncryptedDoRAManager(self.encryption_key, enable_compression=False)
        manager._encrypt_weights_dict(mock_weights, encrypted_path)

        # Tamper with encrypted data
        import json
        with open(encrypted_path, 'r') as f:
            data = json.load(f)

        # Modify ciphertext
        data['ciphertext'] = data['ciphertext'][:-10] + "TAMPERED=="

        with open(encrypted_path, 'w') as f:
            json.dump(data, f)

        # Decryption should fail
        with self.assertRaises(ValueError):
            manager.decrypt_and_load_dora_weights(encrypted_path)

    def test_wrong_key(self):
        """Test that wrong key fails to decrypt."""
        mock_weights = {
            "layer.0.lora_A": torch.randn(16, 768),
        }

        class MockModel:
            def named_modules(self):
                return []

        # Encrypt with one key
        manager1 = EncryptedDoRAManager(generate_secure_password(), enable_compression=False)
        encrypted_path = os.path.join(self.temp_dir, "wrong_key.json")
        manager1._encrypt_weights_dict(mock_weights, encrypted_path)

        # Try to decrypt with different key
        manager2 = EncryptedDoRAManager(generate_secure_password(), enable_compression=False)

        # Should fail authentication
        with self.assertRaises(ValueError):
            manager2.decrypt_and_load_dora_weights(encrypted_path)


class TestMemorySecurity(unittest.TestCase):
    """Test secure memory operations."""

    def test_secure_zero_tensor(self):
        """Test secure tensor zeroing."""
        from src.utils.memory_security import secure_zero_tensor

        # CPU tensor
        tensor_cpu = torch.randn(100, 100)
        self.assertFalse(torch.all(tensor_cpu == 0))

        secure_zero_tensor(tensor_cpu)
        self.assertTrue(torch.all(tensor_cpu == 0))

        # CUDA tensor (if available)
        if torch.cuda.is_available():
            tensor_cuda = torch.randn(100, 100, device='cuda')
            self.assertFalse(torch.all(tensor_cuda == 0))

            secure_zero_tensor(tensor_cuda)
            self.assertTrue(torch.all(tensor_cuda == 0))

    def test_secure_zero_dict(self):
        """Test secure dictionary zeroing."""
        tensor_dict = {
            'a': torch.randn(10, 10),
            'b': torch.randn(20, 20),
        }

        secure_zero_dict(tensor_dict)

        # Dictionary should be empty
        self.assertEqual(len(tensor_dict), 0)


if __name__ == '__main__':
    unittest.main()
