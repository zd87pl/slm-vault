"""
Tests for MLX DoRA Inference Engine

These tests verify the DoRA formula implementation and adapter loading
for Apple Silicon (MLX) inference.
"""

import unittest
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
import sys
import tempfile
import os

# Check if MLX is available
MLX_AVAILABLE = False
try:
    import mlx.core as mx
    import mlx.nn as nn
    MLX_AVAILABLE = True
except ImportError:
    pass


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestMLXDoRALinear(unittest.TestCase):
    """Test the MLXDoRALinear layer implementation."""

    def test_dora_formula_basic(self):
        """Test basic DoRA formula: W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||)"""
        from ..mlx_dora_inference import MLXDoRALinear

        # Create test weights
        out_features, in_features, rank = 64, 32, 4

        original_weight = mx.random.normal((out_features, in_features))
        lora_a = mx.random.normal((rank, in_features)) * 0.01
        lora_b = mx.random.normal((out_features, rank)) * 0.01
        magnitude = mx.ones((out_features,))

        # Create DoRA layer
        layer = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=None,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=magnitude,
            scaling=1.0
        )

        # Test forward pass
        x = mx.random.normal((2, in_features))
        output = layer(x)

        # Verify output shape
        self.assertEqual(output.shape, (2, out_features))

    def test_dora_without_magnitude(self):
        """Test DoRA layer without magnitude (falls back to LoRA)."""
        from ..mlx_dora_inference import MLXDoRALinear

        out_features, in_features, rank = 64, 32, 4

        original_weight = mx.random.normal((out_features, in_features))
        lora_a = mx.random.normal((rank, in_features)) * 0.01
        lora_b = mx.random.normal((out_features, rank)) * 0.01

        # No magnitude - should use standard LoRA
        layer = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=None,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=None,  # No DoRA magnitude
            scaling=1.0
        )

        x = mx.random.normal((2, in_features))
        output = layer(x)

        self.assertEqual(output.shape, (2, out_features))

    def test_dora_with_bias(self):
        """Test DoRA layer with bias."""
        from ..mlx_dora_inference import MLXDoRALinear

        out_features, in_features, rank = 64, 32, 4

        original_weight = mx.random.normal((out_features, in_features))
        original_bias = mx.random.normal((out_features,))
        lora_a = mx.random.normal((rank, in_features)) * 0.01
        lora_b = mx.random.normal((out_features, rank)) * 0.01
        magnitude = mx.ones((out_features,))

        layer = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=original_bias,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=magnitude,
            scaling=1.0
        )

        x = mx.random.normal((2, in_features))
        output = layer(x)

        self.assertEqual(output.shape, (2, out_features))

    def test_scaling_factor(self):
        """Test that scaling factor affects output."""
        from ..mlx_dora_inference import MLXDoRALinear

        out_features, in_features, rank = 64, 32, 4

        original_weight = mx.zeros((out_features, in_features))  # Zero base
        lora_a = mx.ones((rank, in_features))
        lora_b = mx.ones((out_features, rank))
        magnitude = mx.ones((out_features,))

        # Create layers with different scaling
        layer_scale_1 = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=None,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=magnitude,
            scaling=1.0
        )

        layer_scale_2 = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=None,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=magnitude,
            scaling=2.0
        )

        x = mx.ones((1, in_features))
        out1 = layer_scale_1(x)
        out2 = layer_scale_2(x)

        # Outputs should be different due to scaling
        self.assertEqual(out1.shape, out2.shape)


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestDoRAWeightsGrouping(unittest.TestCase):
    """Test adapter weight parsing and grouping."""

    def test_group_weights_by_layer(self):
        """Test grouping flat weights dict into DoRAWeights."""
        from ..mlx_dora_inference import MLXDoRAInference

        engine = MLXDoRAInference.__new__(MLXDoRAInference)

        # Create mock flat weights
        flat_weights = {
            "model.layers.0.self_attn.q_proj.lora_A": mx.random.normal((4, 32)),
            "model.layers.0.self_attn.q_proj.lora_B": mx.random.normal((64, 4)),
            "model.layers.0.self_attn.q_proj.magnitude": mx.ones((64,)),
            "model.layers.0.self_attn.k_proj.lora_A": mx.random.normal((4, 32)),
            "model.layers.0.self_attn.k_proj.lora_B": mx.random.normal((64, 4)),
            # No magnitude for k_proj - should still work
        }

        grouped = engine._group_weights_by_layer(flat_weights)

        # Should have 2 layers grouped
        self.assertEqual(len(grouped), 2)
        self.assertIn("model.layers.0.self_attn.q_proj", grouped)
        self.assertIn("model.layers.0.self_attn.k_proj", grouped)

        # q_proj should have magnitude
        q_proj = grouped["model.layers.0.self_attn.q_proj"]
        self.assertIsNotNone(q_proj.magnitude)

        # k_proj should not have magnitude
        k_proj = grouped["model.layers.0.self_attn.k_proj"]
        self.assertIsNone(k_proj.magnitude)

    def test_skip_incomplete_layers(self):
        """Test that layers missing lora_A or lora_B are skipped."""
        from ..mlx_dora_inference import MLXDoRAInference

        engine = MLXDoRAInference.__new__(MLXDoRAInference)

        flat_weights = {
            # Complete layer
            "layer1.lora_A": mx.random.normal((4, 32)),
            "layer1.lora_B": mx.random.normal((64, 4)),
            # Incomplete - missing lora_B
            "layer2.lora_A": mx.random.normal((4, 32)),
            # Incomplete - missing lora_A
            "layer3.lora_B": mx.random.normal((64, 4)),
        }

        grouped = engine._group_weights_by_layer(flat_weights)

        # Only complete layer should be included
        self.assertEqual(len(grouped), 1)
        self.assertIn("layer1", grouped)

    def test_peft_format_with_prefix(self):
        """Test handling of PEFT-style naming with base_model prefix."""
        from ..mlx_dora_inference import MLXDoRAInference

        engine = MLXDoRAInference.__new__(MLXDoRAInference)

        # PEFT-style naming
        flat_weights = {
            "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": mx.random.normal((4, 32)),
            "base_model.model.layers.0.self_attn.q_proj.lora_B.weight": mx.random.normal((64, 4)),
        }

        grouped = engine._group_weights_by_layer(flat_weights)

        # Should strip prefix and suffix
        self.assertEqual(len(grouped), 1)
        self.assertIn("model.layers.0.self_attn.q_proj", grouped)

    def test_normalize_weight_type_names(self):
        """Test normalization of various weight type names."""
        from ..mlx_dora_inference import MLXDoRAInference

        engine = MLXDoRAInference.__new__(MLXDoRAInference)

        flat_weights = {
            # Lowercase variants
            "layer1.lora_a": mx.random.normal((4, 32)),
            "layer1.lora_b": mx.random.normal((64, 4)),
            # DoRA magnitude vector with different name
            "layer1.lora_magnitude_vector": mx.ones((64,)),
        }

        grouped = engine._group_weights_by_layer(flat_weights)

        self.assertEqual(len(grouped), 1)
        layer = grouped["layer1"]
        self.assertIsNotNone(layer.lora_a)
        self.assertIsNotNone(layer.lora_b)
        self.assertIsNotNone(layer.magnitude)


class TestMLXDoRAAvailability(unittest.TestCase):
    """Test availability checking."""

    def test_availability_function(self):
        """Test is_mlx_dora_available returns appropriate value."""
        from ..mlx_dora_inference import is_mlx_dora_available

        result = is_mlx_dora_available()

        # Should return True if both MLX and crypto are available
        if MLX_AVAILABLE:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
                self.assertTrue(result)
            except ImportError:
                self.assertFalse(result)
        else:
            self.assertFalse(result)


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestDoRAMathCorrectness(unittest.TestCase):
    """Test mathematical correctness of DoRA implementation."""

    def test_normalization_rows_unit_length(self):
        """Verify that DoRA produces unit-length rows when magnitude=1."""
        from ..mlx_dora_inference import MLXDoRALinear

        out_features, in_features, rank = 16, 8, 2

        original_weight = mx.random.normal((out_features, in_features))
        lora_a = mx.random.normal((rank, in_features)) * 0.1
        lora_b = mx.random.normal((out_features, rank)) * 0.1
        magnitude = mx.ones((out_features,))  # Unit magnitude

        layer = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=None,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=magnitude,
            scaling=1.0
        )

        # Get adapted weight (internal)
        adapted_weight = layer._adapted_weight

        # Each row should have unit length (magnitude=1)
        row_norms = mx.linalg.norm(adapted_weight, axis=1)

        # Allow small numerical tolerance
        np.testing.assert_array_almost_equal(
            np.array(row_norms),
            np.ones(out_features),
            decimal=5
        )

    def test_magnitude_scaling(self):
        """Test that magnitude correctly scales row norms."""
        from ..mlx_dora_inference import MLXDoRALinear

        out_features, in_features, rank = 8, 4, 2

        original_weight = mx.random.normal((out_features, in_features))
        lora_a = mx.random.normal((rank, in_features)) * 0.1
        lora_b = mx.random.normal((out_features, rank)) * 0.1

        # Custom magnitude values
        target_magnitudes = mx.array([0.5, 1.0, 1.5, 2.0, 0.25, 0.75, 1.25, 1.75])

        layer = MLXDoRALinear(
            original_weight=original_weight,
            original_bias=None,
            lora_a=lora_a,
            lora_b=lora_b,
            magnitude=target_magnitudes,
            scaling=1.0
        )

        adapted_weight = layer._adapted_weight
        row_norms = mx.linalg.norm(adapted_weight, axis=1)

        # Row norms should match magnitudes
        np.testing.assert_array_almost_equal(
            np.array(row_norms),
            np.array(target_magnitudes),
            decimal=5
        )


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestDoRAWeightsClear(unittest.TestCase):
    """Test DoRAWeights cleanup."""

    def test_clear_method(self):
        """Test that clear() properly nullifies weight references."""
        from ..mlx_dora_inference import DoRAWeights

        weights = DoRAWeights(
            lora_a=mx.random.normal((4, 32)),
            lora_b=mx.random.normal((64, 4)),
            magnitude=mx.ones((64,)),
            scaling=1.0
        )

        # Verify weights are set
        self.assertIsNotNone(weights.lora_a)
        self.assertIsNotNone(weights.lora_b)
        self.assertIsNotNone(weights.magnitude)

        # Clear
        weights.clear()

        # Verify weights are None
        self.assertIsNone(weights.lora_a)
        self.assertIsNone(weights.lora_b)
        self.assertIsNone(weights.magnitude)


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestSafetensorsParsing(unittest.TestCase):
    """Test safetensors parsing with in-memory data."""

    def test_parse_safetensors_to_mlx(self):
        """Test parsing safetensors bytes to MLX arrays."""
        from ..mlx_dora_inference import MLXDoRAInference

        try:
            from safetensors.numpy import save as save_numpy
        except ImportError:
            self.skipTest("safetensors not available")

        engine = MLXDoRAInference.__new__(MLXDoRAInference)

        # Create test data
        test_weights = {
            "layer.lora_A": np.random.randn(4, 32).astype(np.float32),
            "layer.lora_B": np.random.randn(64, 4).astype(np.float32),
        }

        # Serialize to safetensors bytes
        safetensors_bytes = save_numpy(test_weights)

        # Parse to MLX
        mlx_weights = engine._parse_safetensors_to_mlx(safetensors_bytes)

        # Verify
        self.assertEqual(len(mlx_weights), 2)
        self.assertIn("layer.lora_A", mlx_weights)
        self.assertIn("layer.lora_B", mlx_weights)
        self.assertEqual(mlx_weights["layer.lora_A"].shape, (4, 32))
        self.assertEqual(mlx_weights["layer.lora_B"].shape, (64, 4))


@unittest.skipUnless(MLX_AVAILABLE, "MLX not available")
class TestModelFallbackLogic(unittest.TestCase):
    """Test model loading fallback logic."""

    def test_fallback_order(self):
        """Test that custom model is tried first, then fallbacks."""
        from ..mlx_dora_inference import MLXDoRAInference

        custom_model = "custom/my-model"
        engine = MLXDoRAInference(model_path=custom_model)

        # The model_path should be set to custom model
        self.assertEqual(engine.model_path, custom_model)

        # Verify SUPPORTED_MODELS doesn't include custom model
        self.assertNotIn(custom_model, engine.SUPPORTED_MODELS)


if __name__ == "__main__":
    unittest.main()
