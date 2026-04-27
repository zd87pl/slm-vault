"""
Tests for the mlx-lm-lora backend integration.

These tests verify that the backend wrapper correctly:
1. Instantiates without error when mlx-lm-lora is available
2. Prepares datasets in the correct format for each train_mode
3. Builds AdvancedTrainingConfig correctly
4. Lists adapters with advanced metadata
"""

import json
import tempfile
from pathlib import Path

import pytest


try:
    from advanced_vault.training.mlx_lora_backend import (
        AdvancedTrainingConfig,
        MLXLoRABackend,
        _check_mlx_lm_lora,
    )
    BACKEND_AVAILABLE = _check_mlx_lm_lora()
except ImportError:
    BACKEND_AVAILABLE = False


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="mlx-lm-lora not installed")
class TestMLXLoRABackend:
    def test_backend_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = MLXLoRABackend(output_dir=tmp)
            assert backend.output_dir == Path(tmp)
            assert backend.output_dir.exists()

    def test_advanced_training_config_to_args(self):
        config = AdvancedTrainingConfig(
            model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
            train_mode="dpo",
            train_type="dora",
            lora_rank=16,
            lora_alpha=32,
            beta=0.2,
            qat_enable=True,
            qat_bits=4,
        )
        args = config.to_mlx_lm_lora_args()
        assert args["model"] == "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
        assert args["train_mode"] == "dpo"
        assert args["train_type"] == "dora"
        assert args["lora_parameters"]["rank"] == 16
        assert args["lora_parameters"]["alpha"] == 32
        assert args["beta"] == 0.2
        assert args["qat_enable"] is True
        assert args["qat_bits"] == 4

    def test_dataset_write_sft(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = MLXLoRABackend(output_dir=tmp)
            examples = [
                {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]},
                {"messages": [{"role": "user", "content": "Bye"}, {"role": "assistant", "content": "Goodbye"}]},
            ]
            data_dir = backend._write_dataset(examples, Path(tmp), mode="sft")
            train_file = data_dir / "train.jsonl"
            valid_file = data_dir / "valid.jsonl"
            assert train_file.exists()
            assert valid_file.exists()

            with open(train_file) as f:
                lines = [json.loads(line) for line in f]
            assert len(lines) == 1  # 2 examples - 1 validation
            assert "messages" in lines[0]

    def test_dataset_write_dpo(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = MLXLoRABackend(output_dir=tmp)
            examples = [
                {"prompt": "Q1", "chosen": "Good", "rejected": "Bad"},
                {"prompt": "Q2", "chosen": "Better", "rejected": "Worse"},
                {"prompt": "Q3", "chosen": "Best", "rejected": "Worst"},
            ]
            data_dir = backend._write_dataset(examples, Path(tmp), mode="dpo")
            train_file = data_dir / "train.jsonl"
            with open(train_file) as f:
                lines = [json.loads(line) for line in f]
            assert len(lines) == 2  # 3 examples - 1 validation
            assert "prompt" in lines[0]
            assert "chosen" in lines[0]
            assert "rejected" in lines[0]

    def test_list_adapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = MLXLoRABackend(output_dir=tmp)
            # Create a fake adapter
            adapter_dir = Path(tmp) / "test_adapter"
            adapter_dir.mkdir()
            config = {
                "base_model": "test-model",
                "train_mode": "dpo",
                "train_type": "dora",
                "created_at": "2024-01-01T00:00:00",
                "num_examples": 10,
                "use_dora": True,
                "qat": {"enabled": True, "bits": 4},
            }
            with open(adapter_dir / "adapter_config.json", "w") as f:
                json.dump(config, f)

            adapters = backend.list_adapters()
            assert len(adapters) == 1
            assert adapters[0]["name"] == "test_adapter"
            assert adapters[0]["train_mode"] == "dpo"
            assert adapters[0]["qat_enabled"] is True

    def test_delete_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = MLXLoRABackend(output_dir=tmp)
            adapter_dir = Path(tmp) / "to_delete"
            adapter_dir.mkdir()
            assert adapter_dir.exists()
            assert backend.delete_adapter("to_delete") is True
            assert not adapter_dir.exists()
            assert backend.delete_adapter("nonexistent") is False


class TestAdvancedTrainingConfigFallback:
    def test_config_exists_without_backend(self):
        """Ensure the module can be imported even if mlx-lm-lora is missing."""
        from advanced_vault.training.mlx_trainer import _ADVANCED_BACKEND_AVAILABLE
        # This should not raise
        assert isinstance(_ADVANCED_BACKEND_AVAILABLE, bool)
