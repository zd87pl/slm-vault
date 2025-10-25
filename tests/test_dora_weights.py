"""
Test suite for DoRA weight application and formula correctness.
"""

import unittest
import torch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDoRAFormula(unittest.TestCase):
    """Test DoRA weight application formula: W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||c)"""

    def test_dora_formula_correctness(self):
        """Test DoRA formula produces correct output."""
        # Create test weights
        W0 = torch.randn(768, 1024)  # Base weights
        lora_A = torch.randn(16, 1024)  # Low-rank A
        lora_B = torch.randn(768, 16)  # Low-rank B
        magnitude = torch.ones(768)  # Magnitude vector

        # Apply DoRA formula
        BA = torch.mm(lora_B, lora_A)
        new_direction = W0 + BA

        # Row-wise normalization (normalize each output feature)
        row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
        normalized_direction = new_direction / row_norm

        # Apply magnitude scaling (scale each row by corresponding magnitude)
        W_prime = magnitude.unsqueeze(1) * normalized_direction

        # Verify shape preserved
        self.assertEqual(W_prime.shape, W0.shape)

        # Verify normalization (row norms should equal magnitude)
        result_norms = torch.linalg.norm(W_prime, dim=1)
        expected_norms = magnitude
        self.assertTrue(torch.allclose(result_norms, expected_norms, rtol=1e-5))

    def test_dora_vs_lora_difference(self):
        """Test that DoRA and LoRA produce different outputs."""
        W0 = torch.randn(768, 1024)
        lora_A = torch.randn(16, 1024)
        lora_B = torch.randn(768, 16)
        magnitude = torch.ones(768)

        # LoRA: W' = W₀ + BA
        BA = torch.mm(lora_B, lora_A)
        W_lora = W0 + BA

        # DoRA: W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||r)
        new_direction = W0 + BA
        row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
        normalized_direction = new_direction / row_norm
        W_dora = magnitude.unsqueeze(1) * normalized_direction

        # They should be different
        self.assertFalse(torch.allclose(W_lora, W_dora))

        # DoRA should have controlled norms
        dora_norms = torch.linalg.norm(W_dora, dim=1)
        self.assertTrue(torch.allclose(dora_norms, magnitude, rtol=1e-5))

    def test_magnitude_scaling_effect(self):
        """Test that magnitude vector controls output magnitude."""
        W0 = torch.randn(768, 1024)
        lora_A = torch.randn(16, 1024)
        lora_B = torch.randn(768, 16)

        # Test with different magnitudes
        magnitudes = [
            torch.ones(768) * 0.5,
            torch.ones(768) * 1.0,
            torch.ones(768) * 2.0,
        ]

        results = []
        for magnitude in magnitudes:
            BA = torch.mm(lora_B, lora_A)
            new_direction = W0 + BA
            row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
            normalized_direction = new_direction / row_norm
            W_prime = magnitude.unsqueeze(1) * normalized_direction
            results.append(W_prime)

        # Verify magnitude control
        for i, magnitude in enumerate(magnitudes):
            norms = torch.linalg.norm(results[i], dim=1)
            self.assertTrue(torch.allclose(norms, magnitude, rtol=1e-5))

    def test_zero_rank_adaptation(self):
        """Test DoRA with zero adaptation (BA = 0)."""
        W0 = torch.randn(768, 1024)
        lora_A = torch.zeros(16, 1024)
        lora_B = torch.zeros(768, 16)
        magnitude = torch.ones(768)

        # Apply DoRA formula
        BA = torch.mm(lora_B, lora_A)  # Should be zero
        new_direction = W0 + BA  # Should equal W0

        row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
        normalized_direction = new_direction / row_norm
        W_prime = magnitude.unsqueeze(1) * normalized_direction

        # With zero adaptation and magnitude=1, should be normalized W0
        W0_normalized = W0 / torch.linalg.norm(W0, dim=1, keepdim=True)
        self.assertTrue(torch.allclose(W_prime, W0_normalized, rtol=1e-5))

    def test_shape_validation(self):
        """Test that shape mismatches are detectable."""
        W0 = torch.randn(768, 1024)

        # Mismatched shapes
        lora_A_wrong = torch.randn(32, 1024)  # Wrong rank
        lora_B_wrong = torch.randn(768, 16)   # Rank doesn't match A

        # This should fail matrix multiplication
        with self.assertRaises(RuntimeError):
            BA = torch.mm(lora_B_wrong, lora_A_wrong)


class TestDoRAWeightExtraction(unittest.TestCase):
    """Test extraction of DoRA weights from models."""

    def test_extract_from_mock_model(self):
        """Test extracting DoRA weights from a mock model."""
        from src.dora_crypto import EncryptedDoRAManager, generate_secure_password

        # Create mock DoRA module
        class MockDoRAModule:
            def __init__(self):
                # PEFT >= 0.9.0 structure
                class LoraDefault:
                    weight = type('obj', (object,), {
                        'data': torch.randn(16, 768)
                    })

                class LoraA:
                    default = LoraDefault()

                class LoraB:
                    default = LoraDefault()

                class Magnitude:
                    weight = type('obj', (object,), {
                        'data': torch.ones(768)
                    })

                self.lora_A = LoraA()
                self.lora_B = LoraB()
                self.weight_m_wdecomp = Magnitude()

        # Create mock model
        class MockModel:
            def named_modules(self):
                return [
                    ('model.layers.0.self_attn.q_proj', MockDoRAModule()),
                    ('model.layers.0.self_attn.v_proj', MockDoRAModule()),
                ]

        model = MockModel()
        manager = EncryptedDoRAManager(generate_secure_password())

        # Extract weights
        weights = manager._extract_dora_weights(model)

        # Verify extraction
        expected_keys = [
            'model.layers.0.self_attn.q_proj.lora_A',
            'model.layers.0.self_attn.q_proj.lora_B',
            'model.layers.0.self_attn.q_proj.magnitude',
            'model.layers.0.self_attn.v_proj.lora_A',
            'model.layers.0.self_attn.v_proj.lora_B',
            'model.layers.0.self_attn.v_proj.magnitude',
        ]

        self.assertEqual(set(weights.keys()), set(expected_keys))

    def test_extract_handles_missing_magnitude(self):
        """Test extraction when magnitude vector is missing (LoRA, not DoRA)."""
        from src.dora_crypto import EncryptedDoRAManager, generate_secure_password

        # Create mock LoRA module (no magnitude)
        class MockLoRAModule:
            def __init__(self):
                class LoraDefault:
                    weight = type('obj', (object,), {
                        'data': torch.randn(16, 768)
                    })

                class LoraA:
                    default = LoraDefault()

                class LoraB:
                    default = LoraDefault()

                self.lora_A = LoraA()
                self.lora_B = LoraB()
                # No weight_m_wdecomp or lora_magnitude_vector

        class MockModel:
            def named_modules(self):
                return [('layer.0', MockLoRAModule())]

        model = MockModel()
        manager = EncryptedDoRAManager(generate_secure_password())

        # Extract weights
        weights = manager._extract_dora_weights(model)

        # Should have A and B but no magnitude
        self.assertIn('layer.0.lora_A', weights)
        self.assertIn('layer.0.lora_B', weights)
        self.assertNotIn('layer.0.magnitude', weights)


if __name__ == '__main__':
    unittest.main()
