"""
Tests for DocumentDPOPipeline.

These tests verify preference pair generation and end-to-end
pipeline orchestration without requiring MLX (mocked where needed).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


try:
    from advanced_vault.training.document_dpo_pipeline import (
        DocumentDPOPipeline,
        PreferencePair,
    )
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False


class TestPreferencePair:
    def test_to_dict(self):
        pair = PreferencePair(
            prompt="What is AI?",
            chosen="AI is artificial intelligence.",
            rejected="AI is a type of fruit.",
            system="Be helpful.",
            metadata={"source": "test"},
        )
        d = pair.to_dict()
        assert d["prompt"] == "What is AI?"
        assert d["chosen"] == "AI is artificial intelligence."
        assert d["rejected"] == "AI is a type of fruit."
        assert d["system"] == "Be helpful."

    def test_to_messages_dict(self):
        pair = PreferencePair(
            prompt="What is 2+2?",
            chosen="4",
            rejected="5",
        )
        d = pair.to_messages_dict()
        assert d["messages"][0]["role"] == "system"
        assert d["messages"][1]["role"] == "user"
        assert d["messages"][2]["role"] == "assistant"
        assert d["messages"][2]["content"] == "4"


@pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="document_dpo_pipeline not available")
class TestDocumentDPOPipeline:
    def test_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = DocumentDPOPipeline(output_dir=tmp)
            assert pipeline.output_dir == Path(tmp)

    def test_generate_preference_pairs_from_qa_without_mlx(self):
        """Should raise if MLX not available for synthetic generation."""
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = DocumentDPOPipeline(output_dir=tmp)
            qa_pairs = [
                {"question": "Q1", "answer": "A1"},
                {"question": "Q2", "answer": "A2"},
            ]
            # Without MLX installed, this should raise RuntimeError on model load
            with pytest.raises(RuntimeError):
                pipeline.generate_preference_pairs_from_qa(qa_pairs)

    def test_train_from_preference_pairs_without_backend(self):
        """Should raise if advanced backend not available."""
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = DocumentDPOPipeline(output_dir=tmp)
            pairs = [
                PreferencePair(prompt="Q", chosen="Good", rejected="Bad"),
            ]
            with pytest.raises(ImportError):
                pipeline.train_from_preference_pairs(
                    pairs, adapter_name="test_adapter"
                )

    @patch("advanced_vault.training.document_dpo_pipeline._check_mlx", return_value=True)
    @patch("advanced_vault.training.document_dpo_pipeline._check_advanced_backend", return_value=True)
    def test_end_to_end_mocked(self, mock_backend, mock_mlx):
        """Mocked end-to-end test with fake model generation."""
        with tempfile.TemporaryDirectory() as tmp:
            # We need to mock the actual MLX load/generate inside the pipeline
            with patch.object(DocumentDPOPipeline, "_load_model"), \
                 patch("advanced_vault.training.document_dpo_pipeline.generate") as mock_gen:
                mock_gen.side_effect = [
                    "Rejected answer 1",  # rejected for Q1
                    "Rejected answer 2",  # rejected for Q2
                ]

                # Also mock MLXTrainer.train_dpo
                with patch("advanced_vault.training.mlx_trainer.MLXTrainer.train_dpo") as mock_train:
                    mock_result = MagicMock()
                    mock_result.model_name = "test-model"
                    mock_result.train_mode = "dpo"
                    mock_result.iters = 100
                    mock_result.final_loss = 0.5
                    mock_result.created_at.isoformat.return_value = "2024-01-01T00:00:00"
                    mock_result.adapter_path = Path(tmp) / "test_adapter"
                    mock_train.return_value = mock_result

                    pipeline = DocumentDPOPipeline(output_dir=tmp)
                    qa_pairs = [
                        {"question": "What is AI?", "answer": "Artificial Intelligence."},
                        {"question": "What is ML?", "answer": "Machine Learning."},
                    ]

                    result = pipeline.train_from_qa_pairs(
                        qa_pairs=qa_pairs,
                        adapter_name="test_adapter",
                        train_mode="dpo",
                        num_rejected_per_question=1,
                    )

                    assert result.model_name == "test-model"
                    assert result.train_mode == "dpo"
                    assert result.final_loss == 0.5
