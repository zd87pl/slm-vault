"""
Test suite for adapter caching functionality.
"""

import unittest
import torch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.adapter_cache import AdapterCache
from src.dora_crypto import generate_secure_password


class TestAdapterCache(unittest.TestCase):
    """Test LRU adapter caching."""

    def setUp(self):
        """Set up test fixtures."""
        self.cache = AdapterCache(max_size=3)
        self.key1 = generate_secure_password()
        self.key2 = generate_secure_password()

    def test_cache_put_get(self):
        """Test basic cache operations."""
        weights = {
            'layer.0.lora_A': torch.randn(16, 768),
            'layer.0.lora_B': torch.randn(768, 16),
        }

        # Put in cache
        self.cache.put('/path/adapter1.json', self.key1, weights)

        # Get from cache
        cached = self.cache.get('/path/adapter1.json', self.key1)

        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), len(weights))

    def test_cache_miss(self):
        """Test cache miss."""
        result = self.cache.get('/nonexistent.json', self.key1)
        self.assertIsNone(result)

    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        # Fill cache to capacity
        for i in range(3):
            weights = {'tensor': torch.randn(10, 10)}
            self.cache.put(f'/adapter{i}.json', self.key1, weights)

        # All should be cached
        self.assertEqual(self.cache.size, 3)

        # Add one more (should evict LRU)
        weights4 = {'tensor': torch.randn(10, 10)}
        self.cache.put('/adapter3.json', self.key1, weights4)

        # Size should still be 3
        self.assertEqual(self.cache.size, 3)

        # First item should be evicted
        self.assertIsNone(self.cache.get('/adapter0.json', self.key1))

        # Last item should still be there
        self.assertIsNotNone(self.cache.get('/adapter3.json', self.key1))

    def test_hit_rate_tracking(self):
        """Test cache hit rate calculation."""
        weights = {'tensor': torch.randn(10, 10)}
        self.cache.put('/adapter.json', self.key1, weights)

        # 1 hit
        self.cache.get('/adapter.json', self.key1)
        # 1 miss
        self.cache.get('/other.json', self.key1)

        # Hit rate should be 50%
        self.assertAlmostEqual(self.cache.hit_rate, 0.5)

    def test_memory_limit(self):
        """Test memory-based eviction."""
        # Cache with 1MB limit
        cache = AdapterCache(max_size=10, max_memory_mb=1.0)

        # Add tensors until memory limit is reached
        for i in range(10):
            # Each tensor is ~0.4MB
            weights = {'tensor': torch.randn(100, 1000)}
            cache.put(f'/adapter{i}.json', self.key1, weights)

        # Should have evicted some due to memory limit
        self.assertLess(cache.memory_mb, 1.1)  # Allow small margin

    def test_cache_stats(self):
        """Test cache statistics."""
        weights = {'tensor': torch.randn(10, 10)}

        # Add and access
        self.cache.put('/adapter.json', self.key1, weights)
        self.cache.get('/adapter.json', self.key1)
        self.cache.get('/missing.json', self.key1)

        stats = self.cache.get_stats()

        self.assertEqual(stats['size'], 1)
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['total_requests'], 2)

    def test_clear_cache(self):
        """Test cache clearing."""
        # Add items
        for i in range(3):
            weights = {'tensor': torch.randn(10, 10)}
            self.cache.put(f'/adapter{i}.json', self.key1, weights)

        self.assertEqual(self.cache.size, 3)

        # Clear
        self.cache.clear()

        self.assertEqual(self.cache.size, 0)
        self.assertEqual(self.cache.memory_mb, 0.0)


if __name__ == '__main__':
    unittest.main()
