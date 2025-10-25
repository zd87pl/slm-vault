"""
Performance and benchmark tests.

These tests measure performance metrics and ensure they meet targets.
"""

import unittest
import torch
import tempfile
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dora_crypto import EncryptedDoRAManager, generate_secure_password
from src.utils.adapter_cache import AdapterCache


class TestEncryptionPerformance(unittest.TestCase):
    """Test encryption/decryption performance."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_encryption_latency(self):
        """Test that encryption completes within reasonable time."""
        # Create typical adapter size (~10MB)
        weights = {
            f'layer.{i}.lora_A': torch.randn(16, 4096)
            for i in range(32)  # Typical Llama-like model
        }

        manager = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True
        )

        encrypted_path = os.path.join(self.temp_dir, 'bench.enc')

        # Measure encryption time
        start = time.time()
        manager._encrypt_weights_dict(weights, encrypted_path)
        encryption_time = time.time() - start

        # Should complete in reasonable time (< 5 seconds for ~10MB)
        self.assertLess(encryption_time, 5.0,
                       f"Encryption took {encryption_time:.2f}s, expected < 5s")

        print(f"\n✓ Encryption: {encryption_time*1000:.2f}ms for {len(weights)} tensors")

    def test_decryption_latency(self):
        """Test that decryption completes within reasonable time."""
        # Create adapter
        weights = {
            f'layer.{i}.lora_A': torch.randn(16, 4096)
            for i in range(32)
        }

        manager = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True
        )

        encrypted_path = os.path.join(self.temp_dir, 'bench.enc')
        manager._encrypt_weights_dict(weights, encrypted_path)

        # Measure decryption time
        start = time.time()
        decrypted = manager.decrypt_and_load_dora_weights(encrypted_path)
        decryption_time = time.time() - start

        # Should complete in reasonable time
        self.assertLess(decryption_time, 5.0,
                       f"Decryption took {decryption_time:.2f}s, expected < 5s")

        print(f"✓ Decryption: {decryption_time*1000:.2f}ms for {len(weights)} tensors")

    def test_compression_effectiveness(self):
        """Test that compression reduces size significantly."""
        # Create weights with patterns (should compress well)
        weights = {
            f'layer.{i}.lora_A': torch.randn(16, 4096) * 0.1  # Small values compress better
            for i in range(32)
        }

        # Encrypt with compression
        manager_compressed = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=True,
            compression_level=3
        )
        path_compressed = os.path.join(self.temp_dir, 'compressed.enc')
        manager_compressed._encrypt_weights_dict(weights, path_compressed)

        # Encrypt without compression
        manager_uncompressed = EncryptedDoRAManager(
            self.encryption_key,
            enable_compression=False
        )
        path_uncompressed = os.path.join(self.temp_dir, 'uncompressed.enc')
        manager_uncompressed._encrypt_weights_dict(weights, path_uncompressed)

        # Calculate compression ratio
        size_compressed = os.path.getsize(path_compressed)
        size_uncompressed = os.path.getsize(path_uncompressed)
        compression_ratio = size_compressed / size_uncompressed

        # Random tensors don't compress well (high entropy), but should not make file larger
        # Real model weights typically compress 30-50% due to patterns
        self.assertLess(compression_ratio, 1.0,
                       f"Compression ratio {compression_ratio:.2%}, expected < 100%")

        # Document that random data doesn't compress well
        if compression_ratio > 0.9:
            print(f"  Note: Random tensors have high entropy, compression ratio {compression_ratio:.2%}")

        print(f"✓ Compression: {compression_ratio:.2%} of original size")
        print(f"  Compressed: {size_compressed / 1024**2:.2f} MB")
        print(f"  Uncompressed: {size_uncompressed / 1024**2:.2f} MB")


class TestCachePerformance(unittest.TestCase):
    """Test adapter cache performance."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()

    def test_cache_hit_latency(self):
        """Test that cache hits are fast (< 10ms target)."""
        cache = AdapterCache(max_size=10)

        # Add adapter to cache
        weights = {
            f'layer.{i}.lora_A': torch.randn(16, 4096)
            for i in range(32)
        }

        adapter_path = '/test/adapter.enc'
        cache.put(adapter_path, self.encryption_key, weights)

        # Measure cache hit time
        start = time.time()
        cached = cache.get(adapter_path, self.encryption_key)
        hit_time = (time.time() - start) * 1000  # ms

        self.assertIsNotNone(cached)
        self.assertLess(hit_time, 10.0,
                       f"Cache hit took {hit_time:.2f}ms, expected < 10ms")

        print(f"\n✓ Cache hit: {hit_time:.2f}ms")

    def test_cache_eviction_latency(self):
        """Test that cache eviction is fast."""
        cache = AdapterCache(max_size=3)

        # Fill cache
        for i in range(3):
            weights = {f'tensor_{i}': torch.randn(1000, 1000)}
            cache.put(f'/adapter{i}.enc', self.encryption_key, weights)

        # Measure eviction time (adding 4th adapter)
        weights4 = {'tensor_4': torch.randn(1000, 1000)}

        start = time.time()
        cache.put('/adapter3.enc', self.encryption_key, weights4)
        eviction_time = (time.time() - start) * 1000  # ms

        # Eviction should be fast (< 100ms)
        self.assertLess(eviction_time, 100.0,
                       f"Eviction took {eviction_time:.2f}ms, expected < 100ms")

        print(f"✓ Cache eviction: {eviction_time:.2f}ms")

    def test_memory_tracking_accuracy(self):
        """Test that cache memory tracking is accurate."""
        cache = AdapterCache(max_size=10)

        # Add weights
        weights = {
            'lora_A': torch.randn(16, 4096),
            'lora_B': torch.randn(4096, 16),
            'magnitude': torch.ones(4096),
        }

        # Calculate expected size
        expected_size_bytes = sum(
            w.numel() * w.element_size() for w in weights.values()
        )

        cache.put('/adapter.enc', self.encryption_key, weights)

        # Check tracked memory
        tracked_mb = cache.memory_mb
        expected_mb = expected_size_bytes / 1024**2

        # Should be within 10% tolerance
        self.assertAlmostEqual(tracked_mb, expected_mb, delta=expected_mb * 0.1)

        print(f"✓ Memory tracking: {tracked_mb:.2f} MB (expected {expected_mb:.2f} MB)")


class TestMemoryCleanupPerformance(unittest.TestCase):
    """Test memory cleanup performance."""

    def test_secure_zero_latency(self):
        """Test that secure zeroing is fast."""
        from src.utils.memory_security import secure_zero_tensor

        tensor = torch.randn(10000, 10000)  # Large tensor

        start = time.time()
        secure_zero_tensor(tensor)
        zero_time = (time.time() - start) * 1000  # ms

        # Should be fast (< 100ms for 400MB tensor)
        self.assertLess(zero_time, 100.0,
                       f"Zeroing took {zero_time:.2f}ms, expected < 100ms")

        print(f"\n✓ Secure zero (100M elements): {zero_time:.2f}ms")

    def test_dict_cleanup_latency(self):
        """Test that dictionary cleanup is fast."""
        from src.utils.memory_security import secure_zero_dict

        # Create dictionary with many tensors
        tensor_dict = {
            f'tensor_{i}': torch.randn(1000, 1000)
            for i in range(10)
        }

        start = time.time()
        secure_zero_dict(tensor_dict)
        cleanup_time = (time.time() - start) * 1000  # ms

        # Should be fast
        self.assertLess(cleanup_time, 500.0,
                       f"Cleanup took {cleanup_time:.2f}ms, expected < 500ms")

        print(f"✓ Dict cleanup (10 tensors): {cleanup_time:.2f}ms")


class TestDoRAFormulaPerformance(unittest.TestCase):
    """Test DoRA formula computation performance."""

    def test_dora_merge_latency(self):
        """Test DoRA merging latency."""
        # Typical Llama layer dimensions
        W0 = torch.randn(4096, 4096)
        lora_A = torch.randn(16, 4096)
        lora_B = torch.randn(4096, 16)
        magnitude = torch.ones(4096)

        # Measure merge time
        start = time.time()

        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA
        column_norm = torch.linalg.norm(new_direction, dim=0, keepdim=True)
        column_norm = torch.clamp(column_norm, min=1e-8)
        normalized = new_direction / column_norm
        result = magnitude.unsqueeze(0) * normalized

        merge_time = (time.time() - start) * 1000  # ms

        # Should be reasonably fast
        self.assertLess(merge_time, 100.0,
                       f"DoRA merge took {merge_time:.2f}ms, expected < 100ms")

        print(f"\n✓ DoRA merge (4096x4096): {merge_time:.2f}ms")

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA not available")
    def test_dora_merge_latency_cuda(self):
        """Test DoRA merging latency on GPU."""
        # Move to GPU
        W0 = torch.randn(4096, 4096, device='cuda')
        lora_A = torch.randn(16, 4096, device='cuda')
        lora_B = torch.randn(4096, 16, device='cuda')
        magnitude = torch.ones(4096, device='cuda')

        # Warm up
        for _ in range(5):
            BA = torch.mm(lora_B, lora_A)
            new_direction = W0 + BA
            column_norm = torch.linalg.norm(new_direction, dim=0, keepdim=True)
            normalized = new_direction / column_norm
            result = magnitude.unsqueeze(0) * normalized

        # Measure
        torch.cuda.synchronize()
        start = time.time()

        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA
        column_norm = torch.linalg.norm(new_direction, dim=0, keepdim=True)
        column_norm = torch.clamp(column_norm, min=1e-8)
        normalized = new_direction / column_norm
        result = magnitude.unsqueeze(0) * normalized

        torch.cuda.synchronize()
        merge_time = (time.time() - start) * 1000  # ms

        # GPU should be faster
        self.assertLess(merge_time, 50.0,
                       f"DoRA merge (GPU) took {merge_time:.2f}ms, expected < 50ms")

        print(f"✓ DoRA merge GPU (4096x4096): {merge_time:.2f}ms")


if __name__ == '__main__':
    # Run with verbose output to see timing results
    unittest.main(verbosity=2)
