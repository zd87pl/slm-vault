"""
Tests for Multi-Adapter Engine

These tests verify:
- Adapter registration and caching
- Profile creation and activation
- Weighted adapter merging
- LRU cache behavior
- Usage audit logging
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Check if MLX is available
MLX_AVAILABLE = False
try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    pass


class TestAdapterLRUCache(unittest.TestCase):
    """Test the LRU cache for adapter weights."""

    def test_cache_put_and_get(self):
        """Test basic cache put and get."""
        from ..multi_adapter_engine import AdapterLRUCache

        cache = AdapterLRUCache(max_size=3)
        cache.put("adapter1", {"weights": "data1"})
        cache.put("adapter2", {"weights": "data2"})

        self.assertEqual(cache.get("adapter1"), {"weights": "data1"})
        self.assertEqual(cache.get("adapter2"), {"weights": "data2"})
        self.assertIsNone(cache.get("adapter3"))

    def test_cache_eviction(self):
        """Test LRU eviction when cache is full."""
        from ..multi_adapter_engine import AdapterLRUCache

        cache = AdapterLRUCache(max_size=2)
        cache.put("adapter1", {"weights": "data1"})
        cache.put("adapter2", {"weights": "data2"})
        cache.put("adapter3", {"weights": "data3"})  # Should evict adapter1

        self.assertIsNone(cache.get("adapter1"))
        self.assertIsNotNone(cache.get("adapter2"))
        self.assertIsNotNone(cache.get("adapter3"))

    def test_cache_lru_order(self):
        """Test that accessing moves item to end."""
        from ..multi_adapter_engine import AdapterLRUCache

        cache = AdapterLRUCache(max_size=2)
        cache.put("adapter1", {"weights": "data1"})
        cache.put("adapter2", {"weights": "data2"})

        # Access adapter1, making adapter2 oldest
        cache.get("adapter1")

        # Add new adapter, should evict adapter2
        cache.put("adapter3", {"weights": "data3"})

        self.assertIsNotNone(cache.get("adapter1"))
        self.assertIsNone(cache.get("adapter2"))
        self.assertIsNotNone(cache.get("adapter3"))

    def test_cache_remove(self):
        """Test removing specific adapter."""
        from ..multi_adapter_engine import AdapterLRUCache

        cache = AdapterLRUCache(max_size=3)
        cache.put("adapter1", {"weights": "data1"})
        cache.put("adapter2", {"weights": "data2"})

        cache.remove("adapter1")

        self.assertIsNone(cache.get("adapter1"))
        self.assertIsNotNone(cache.get("adapter2"))

    def test_cache_clear(self):
        """Test clearing entire cache."""
        from ..multi_adapter_engine import AdapterLRUCache

        cache = AdapterLRUCache(max_size=3)
        cache.put("adapter1", {"weights": "data1"})
        cache.put("adapter2", {"weights": "data2"})

        cache.clear()

        self.assertEqual(len(cache), 0)
        self.assertIsNone(cache.get("adapter1"))
        self.assertIsNone(cache.get("adapter2"))


class TestAdapterProfile(unittest.TestCase):
    """Test adapter profile functionality."""

    def test_profile_creation(self):
        """Test creating an adapter profile."""
        from ..multi_adapter_engine import AdapterProfile

        profile = AdapterProfile(
            name="work",
            adapters={"company_docs": 0.8, "professional_tone": 0.2},
            description="Work context",
            keywords=["meeting", "project", "deadline"]
        )

        self.assertEqual(profile.name, "work")
        self.assertEqual(profile.adapters["company_docs"], 0.8)
        self.assertEqual(len(profile.keywords), 3)

    def test_profile_defaults(self):
        """Test profile with default values."""
        from ..multi_adapter_engine import AdapterProfile

        profile = AdapterProfile(
            name="simple",
            adapters={"adapter1": 1.0}
        )

        self.assertEqual(profile.description, "")
        self.assertEqual(profile.keywords, [])
        self.assertIsInstance(profile.created_at, datetime)


class TestMultiAdapterEngine(unittest.TestCase):
    """Test the multi-adapter engine."""

    def test_register_adapter(self):
        """Test registering an adapter."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter(
            name="test_adapter",
            encrypted_data=b"encrypted_data",
            encryption_key=b"key123",
            metadata={"version": "1.0"}
        )

        adapters = engine.list_adapters()
        self.assertEqual(len(adapters), 1)
        self.assertEqual(adapters[0]["name"], "test_adapter")
        self.assertEqual(adapters[0]["metadata"]["version"], "1.0")

    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter("adapter1", b"data", b"key")
        engine.register_adapter("adapter2", b"data", b"key")

        engine.unregister_adapter("adapter1")

        adapters = engine.list_adapters()
        self.assertEqual(len(adapters), 1)
        self.assertEqual(adapters[0]["name"], "adapter2")

    def test_save_and_list_profiles(self):
        """Test saving and listing profiles."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter("adapter1", b"data", b"key")
        engine.register_adapter("adapter2", b"data", b"key")

        engine.save_profile(
            name="work",
            adapters={"adapter1": 0.8, "adapter2": 0.2},
            description="Work profile",
            keywords=["work", "project"]
        )

        profiles = engine.list_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "work")
        self.assertEqual(profiles[0]["description"], "Work profile")

    def test_profile_weight_normalization(self):
        """Test that profile weights are normalized."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter("adapter1", b"data", b"key")
        engine.register_adapter("adapter2", b"data", b"key")

        # Unnormalized weights
        engine.save_profile("test", {"adapter1": 4, "adapter2": 1})

        profiles = engine.list_profiles()
        adapters = profiles[0]["adapters"]

        # Should be normalized to sum to 1.0
        self.assertAlmostEqual(adapters["adapter1"], 0.8)
        self.assertAlmostEqual(adapters["adapter2"], 0.2)

    def test_delete_profile(self):
        """Test deleting a profile."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter("adapter1", b"data", b"key")
        engine.save_profile("work", {"adapter1": 1.0})
        engine.save_profile("personal", {"adapter1": 1.0})

        engine.delete_profile("work")

        profiles = engine.list_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "personal")

    def test_profile_validation(self):
        """Test that profiles validate adapter existence."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter("adapter1", b"data", b"key")

        with self.assertRaises(ValueError):
            engine.save_profile("invalid", {"nonexistent": 1.0})

    def test_context_detection(self):
        """Test context auto-detection from query."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        engine.register_adapter("adapter1", b"data", b"key")
        engine.register_adapter("adapter2", b"data", b"key")

        engine.save_profile("work", {"adapter1": 1.0}, keywords=["meeting", "project", "deadline"])
        engine.save_profile("code", {"adapter2": 1.0}, keywords=["function", "bug", "error"])

        # Should detect "work" context
        detected = engine.detect_context("What time is the project meeting?")
        self.assertEqual(detected, "work")

        # Should detect "code" context
        detected = engine.detect_context("I found a bug in the function")
        self.assertEqual(detected, "code")

        # No match
        detected = engine.detect_context("Hello, how are you?")
        self.assertIsNone(detected)

    def test_get_active_config(self):
        """Test getting active configuration."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()
        config = engine.get_active_config()

        self.assertIsNone(config["profile"])
        self.assertEqual(config["adapters"], {})
        self.assertFalse(config["applied"])
        self.assertFalse(config["model_loaded"])


class TestUsageLogging(unittest.TestCase):
    """Test usage audit logging."""

    def test_usage_log_entry(self):
        """Test usage log entry creation."""
        from ..multi_adapter_engine import UsageLogEntry

        entry = UsageLogEntry(
            timestamp=datetime.utcnow(),
            profile_name="work",
            adapter_names=["adapter1", "adapter2"],
            adapter_weights={"adapter1": 0.8, "adapter2": 0.2},
            query_hash="abc123",
            session_id="session1"
        )

        self.assertEqual(entry.profile_name, "work")
        self.assertEqual(len(entry.adapter_names), 2)
        self.assertEqual(entry.adapter_weights["adapter1"], 0.8)

    def test_usage_stats(self):
        """Test usage statistics."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine()

        # Manually add some log entries for testing
        from ..multi_adapter_engine import UsageLogEntry

        engine._usage_log.append(UsageLogEntry(
            timestamp=datetime.utcnow(),
            profile_name="work",
            adapter_names=["adapter1"],
            adapter_weights={"adapter1": 1.0},
            query_hash="hash1",
            session_id=engine._session_id
        ))
        engine._usage_log.append(UsageLogEntry(
            timestamp=datetime.utcnow(),
            profile_name="work",
            adapter_names=["adapter1", "adapter2"],
            adapter_weights={"adapter1": 0.5, "adapter2": 0.5},
            query_hash="hash2",
            session_id=engine._session_id
        ))

        stats = engine.get_usage_stats()

        self.assertEqual(stats["total_queries"], 2)
        self.assertEqual(stats["adapter_usage"]["adapter1"], 2)
        self.assertEqual(stats["adapter_usage"]["adapter2"], 1)
        self.assertEqual(stats["profile_usage"]["work"], 2)

    def test_export_usage_log(self):
        """Test exporting usage log."""
        from ..multi_adapter_engine import MultiAdapterEngine, UsageLogEntry

        engine = MultiAdapterEngine()
        engine._usage_log.append(UsageLogEntry(
            timestamp=datetime.utcnow(),
            profile_name="test",
            adapter_names=["adapter1"],
            adapter_weights={"adapter1": 1.0},
            query_hash="hash1",
            session_id=engine._session_id
        ))

        exported = engine.export_usage_log()

        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["profile"], "test")
        self.assertIn("timestamp", exported[0])
        self.assertIn("query_hash", exported[0])


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestWeightedMerging(unittest.TestCase):
    """Test weighted adapter merging (requires MLX)."""

    def test_merge_two_adapters(self):
        """Test merging two adapters with weights."""
        from ..multi_adapter_engine import MultiAdapterEngine
        from ..mlx_dora_inference import DoRAWeights

        engine = MultiAdapterEngine()

        # Create mock adapter weights
        adapter1_weights = {
            "layer1": DoRAWeights(
                lora_a=mx.ones((4, 32)),
                lora_b=mx.ones((64, 4)),
                magnitude=mx.ones((64,)),
                scaling=1.0
            )
        }

        adapter2_weights = {
            "layer1": DoRAWeights(
                lora_a=mx.ones((4, 32)) * 2,
                lora_b=mx.ones((64, 4)) * 2,
                magnitude=mx.ones((64,)) * 2,
                scaling=1.0
            )
        }

        all_weights = {
            "adapter1": adapter1_weights,
            "adapter2": adapter2_weights
        }
        weights_config = {"adapter1": 0.5, "adapter2": 0.5}

        merged = engine._merge_adapter_weights(all_weights, weights_config)

        # Check merged weights
        self.assertIn("layer1", merged)
        layer = merged["layer1"]

        # With 50/50 weights: (1*0.5 + 2*0.5) = 1.5
        expected = 1.5
        self.assertAlmostEqual(float(layer.lora_a[0, 0]), expected, places=5)
        self.assertAlmostEqual(float(layer.magnitude[0]), expected, places=5)

    def test_merge_with_missing_layers(self):
        """Test merging when adapters have different layers."""
        from ..multi_adapter_engine import MultiAdapterEngine
        from ..mlx_dora_inference import DoRAWeights

        engine = MultiAdapterEngine()

        adapter1_weights = {
            "layer1": DoRAWeights(
                lora_a=mx.ones((4, 32)),
                lora_b=mx.ones((64, 4)),
                magnitude=None,
                scaling=1.0
            ),
            "layer2": DoRAWeights(
                lora_a=mx.ones((4, 32)),
                lora_b=mx.ones((64, 4)),
                magnitude=None,
                scaling=1.0
            )
        }

        adapter2_weights = {
            "layer1": DoRAWeights(
                lora_a=mx.ones((4, 32)) * 2,
                lora_b=mx.ones((64, 4)) * 2,
                magnitude=None,
                scaling=1.0
            )
            # No layer2 in adapter2
        }

        all_weights = {"adapter1": adapter1_weights, "adapter2": adapter2_weights}
        weights_config = {"adapter1": 0.5, "adapter2": 0.5}

        merged = engine._merge_adapter_weights(all_weights, weights_config)

        # Both layers should exist
        self.assertIn("layer1", merged)
        self.assertIn("layer2", merged)

        # layer1 should be merged (1*0.5 + 2*0.5 = 1.5)
        self.assertAlmostEqual(float(merged["layer1"].lora_a[0, 0]), 1.5, places=5)

        # layer2 only from adapter1 (1*0.5 = 0.5)
        self.assertAlmostEqual(float(merged["layer2"].lora_a[0, 0]), 0.5, places=5)


class TestSessionManagement(unittest.TestCase):
    """Test session ID and management."""

    def test_session_id_generation(self):
        """Test that session ID is generated."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine1 = MultiAdapterEngine()
        engine2 = MultiAdapterEngine()

        # Each engine should have unique session ID
        self.assertIsNotNone(engine1._session_id)
        self.assertIsNotNone(engine2._session_id)
        self.assertNotEqual(engine1._session_id, engine2._session_id)

    def test_custom_session_id(self):
        """Test custom session ID."""
        from ..multi_adapter_engine import MultiAdapterEngine

        engine = MultiAdapterEngine(session_id="custom_session_123")
        self.assertEqual(engine._session_id, "custom_session_123")


if __name__ == "__main__":
    unittest.main()
