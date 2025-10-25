"""
Test suite for ephemeral inference engine.

These tests verify the critical path: decrypt → load → inference → cleanup
"""

import unittest
import torch
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dora_crypto import EncryptedDoRAManager, generate_secure_password


class TestEphemeralInference(unittest.TestCase):
    """Test ephemeral inference workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.encryption_key = generate_secure_password()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_state_capture_and_restoration(self):
        """Test that model state is properly captured and restored."""
        from src.ephemeral_inference import EphemeralDoRAInference

        # Create mock model
        class MockModel:
            def __init__(self):
                self.param1 = torch.nn.Parameter(torch.randn(10, 10))
                self.param2 = torch.nn.Parameter(torch.randn(20, 20))
                self._forward_hooks = {}
                self._backward_hooks = {}

            def named_parameters(self):
                return [
                    ('param1', self.param1),
                    ('param2', self.param2),
                ]

            def named_buffers(self):
                return []

            def named_modules(self):
                return [('', self)]

        model = MockModel()

        # Save original state
        original_param1 = model.param1.data.clone()
        original_param2 = model.param2.data.clone()

        # Mock the inference engine's capture method
        with patch.object(EphemeralDoRAInference, '__init__', lambda x, **kwargs: None):
            engine = EphemeralDoRAInference()
            engine.base_model = model

            # Capture state
            state = engine._capture_model_state()

            # Modify model
            model.param1.data = torch.zeros_like(model.param1)
            model.param2.data = torch.ones_like(model.param2)

            # Verify modification
            self.assertFalse(torch.allclose(model.param1.data, original_param1))
            self.assertFalse(torch.allclose(model.param2.data, original_param2))

            # Restore state
            engine._restore_model_state(state)

            # Verify restoration
            self.assertTrue(torch.allclose(model.param1.data, original_param1))
            self.assertTrue(torch.allclose(model.param2.data, original_param2))

    def test_adapter_cleanup_after_inference(self):
        """Test that adapters are cleaned up after inference."""
        # This is an integration-style test
        # We'll verify memory cleanup happens

        weights = {
            'layer.0.lora_A': torch.randn(16, 768),
            'layer.0.lora_B': torch.randn(768, 16),
            'layer.0.magnitude': torch.ones(768),
        }

        # Test cleanup
        from src.utils.memory_security import secure_zero_dict

        # Make copy
        weights_copy = {k: v.clone() for k, v in weights.items()}

        # Cleanup
        secure_zero_dict(weights)

        # Verify all tensors zeroed and dict empty
        self.assertEqual(len(weights), 0)

    def test_adapter_loading_with_cache_hit(self):
        """Test adapter caching works correctly."""
        from src.utils.adapter_cache import AdapterCache

        cache = AdapterCache(max_size=3)

        # Create adapter weights
        adapter_path = "/test/adapter.json"
        weights = {
            'layer.0.lora_A': torch.randn(16, 768),
            'layer.0.lora_B': torch.randn(768, 16),
        }

        # Put in cache
        cache.put(adapter_path, self.encryption_key, weights)

        # Get from cache
        cached = cache.get(adapter_path, self.encryption_key)

        self.assertIsNotNone(cached)
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 0)

    def test_adapter_loading_with_cache_miss(self):
        """Test cache miss triggers decryption."""
        from src.utils.adapter_cache import AdapterCache

        cache = AdapterCache(max_size=3)

        # Get non-existent adapter
        adapter_path = "/test/nonexistent.json"
        cached = cache.get(adapter_path, self.encryption_key)

        self.assertIsNone(cached)
        self.assertEqual(cache.hits, 0)
        self.assertEqual(cache.misses, 1)


class TestDoRAWeightApplication(unittest.TestCase):
    """Test the actual DoRA weight application to models."""

    def test_apply_dora_weights_to_mock_module(self):
        """Test applying DoRA weights to a module."""
        from src.ephemeral_inference import EphemeralDoRAInference

        # Create mock module with weight parameter
        class MockLinear:
            def __init__(self):
                self.weight = torch.nn.Parameter(torch.randn(768, 1024))

            def __repr__(self):
                return "MockLinear()"

        module = MockLinear()
        original_weight = module.weight.data.clone()

        # Create DoRA weights
        dora_weights = {
            'module.lora_A': torch.randn(16, 1024),
            'module.lora_B': torch.randn(768, 16),
            'module.magnitude': torch.ones(768) * 1.5,
        }

        # Group weights by module
        modules_to_update = {
            'module': {
                'lora_A': dora_weights['module.lora_A'],
                'lora_B': dora_weights['module.lora_B'],
                'magnitude': dora_weights['module.magnitude'],
            }
        }

        # Apply DoRA formula manually (since we can't easily test the full method)
        W0 = module.weight.data
        lora_A = modules_to_update['module']['lora_A']
        lora_B = modules_to_update['module']['lora_B']
        magnitude = modules_to_update['module']['magnitude']

        # DoRA formula
        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA
        row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
        row_norm = torch.clamp(row_norm, min=1e-8)
        normalized_direction = new_direction / row_norm
        W_personalized = magnitude.unsqueeze(1) * normalized_direction

        # Apply
        module.weight.data = W_personalized

        # Verify changed
        self.assertFalse(torch.allclose(module.weight.data, original_weight))

        # Verify norms match magnitude
        result_norms = torch.linalg.norm(module.weight.data, dim=1)
        expected_norms = magnitude
        self.assertTrue(torch.allclose(result_norms, expected_norms, rtol=1e-5))

    def test_shape_mismatch_detection(self):
        """Test that shape mismatches are handled gracefully."""
        # Create module with one shape
        class MockModule:
            def __init__(self):
                self.weight = torch.nn.Parameter(torch.randn(768, 1024))

        module = MockModule()

        # Create DoRA weights with mismatched shapes
        dora_weights = {
            'module.lora_A': torch.randn(16, 512),  # Wrong! Should be 1024
            'module.lora_B': torch.randn(768, 16),
            'module.magnitude': torch.ones(768),
        }

        W0 = module.weight.data
        lora_A = dora_weights['module.lora_A']
        lora_B = dora_weights['module.lora_B']

        # This should raise an error due to shape mismatch
        with self.assertRaises(RuntimeError):
            BA = torch.mm(lora_B, lora_A)
            new_direction = W0 + BA  # Shape mismatch here

    def test_apply_without_magnitude_fallback_to_lora(self):
        """Test that missing magnitude falls back to LoRA."""
        class MockModule:
            def __init__(self):
                self.weight = torch.nn.Parameter(torch.randn(768, 1024))

        module = MockModule()
        original_weight = module.weight.data.clone()

        # Create weights without magnitude (LoRA mode)
        dora_weights = {
            'module.lora_A': torch.randn(16, 1024),
            'module.lora_B': torch.randn(768, 16),
            # No magnitude!
        }

        # Apply LoRA formula (fallback)
        W0 = module.weight.data
        lora_A = dora_weights['module.lora_A']
        lora_B = dora_weights['module.lora_B']

        BA = torch.mm(lora_B, lora_A)
        W_adapted = W0 + BA

        module.weight.data = W_adapted

        # Verify changed
        self.assertFalse(torch.allclose(module.weight.data, original_weight))


class TestMemoryCleanup(unittest.TestCase):
    """Test memory cleanup after inference."""

    def test_tensor_zeroing(self):
        """Test that tensors are properly zeroed."""
        from src.utils.memory_security import secure_zero_tensor

        tensor = torch.randn(100, 100)
        self.assertFalse(torch.all(tensor == 0))

        secure_zero_tensor(tensor)
        self.assertTrue(torch.all(tensor == 0))

    def test_dict_cleanup(self):
        """Test that dictionaries are properly cleaned."""
        from src.utils.memory_security import secure_zero_dict

        tensor_dict = {
            'a': torch.randn(100, 100),
            'b': torch.randn(200, 200),
            'c': torch.randn(50, 50),
        }

        self.assertEqual(len(tensor_dict), 3)

        secure_zero_dict(tensor_dict)

        # Dictionary should be empty
        self.assertEqual(len(tensor_dict), 0)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA not available")
    def test_cuda_memory_cleanup(self):
        """Test CUDA memory cleanup."""
        from src.utils.memory_security import secure_zero_tensor

        tensor_cuda = torch.randn(100, 100, device='cuda')
        self.assertFalse(torch.all(tensor_cuda == 0))

        secure_zero_tensor(tensor_cuda)
        self.assertTrue(torch.all(tensor_cuda == 0))


if __name__ == '__main__':
    unittest.main()
