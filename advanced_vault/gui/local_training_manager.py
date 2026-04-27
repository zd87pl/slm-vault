"""
Local Training Manager for GUI

Provides Enclave GUI with local advanced training capabilities
(DPO, ORPO, GRPO) via the mlx-lm-lora backend, complementing the
cloud-based TrainingManager.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from advanced_vault.training.mlx_trainer import MLXTrainer
from advanced_vault.training.document_dpo_pipeline import DocumentDPOPipeline

logger = logging.getLogger(__name__)


try:
    from advanced_vault.training.mlx_lora_backend import (
        AdvancedTrainingConfig,
        AdvancedTrainingResult,
        MLXLoRABackend,
    )
    _ADVANCED_AVAILABLE = True
except ImportError:
    _ADVANCED_AVAILABLE = False


class LocalTrainingManager:
    """
    Local training manager for the Enclave GUI.

    Mirrors the cloud TrainingManager API but runs training locally
    using mlx-lm-lora on Apple Silicon.
    """

    TRAIN_MODES = ["sft", "dpo", "orpo", "grpo"]

    def __init__(
        self,
        output_dir: str = "~/.enclave/adapters",
        model_name: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    ):
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self._backend_available = _ADVANCED_AVAILABLE

    def get_capabilities(self) -> Dict[str, Any]:
        """Return available training capabilities."""
        return {
            "advanced_backend_available": self._backend_available,
            "train_modes": self.TRAIN_MODES if self._backend_available else ["sft"],
            "model_name": self.model_name,
            "output_dir": str(self.output_dir),
        }

    def submit_training_job(
        self,
        dataset_path: str,
        adapter_id: Optional[str] = None,
        train_mode: str = "sft",
        encryption_key_hex: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submit a local training job (GUI-compatible API).

        Args:
            dataset_path: Path to dataset (JSONL)
            adapter_id: Optional adapter ID / name
            train_mode: sft, dpo, orpo, or grpo
            encryption_key_hex: Ignored for local training (encryption applied later)
            **kwargs: Additional params (rank, alpha, beta, etc.)

        Returns:
            Job status dict compatible with cloud TrainingManager
        """
        import json
        import time
        import uuid

        if not self._backend_available and train_mode != "sft":
            raise ValueError(
                f"train_mode='{train_mode}' requires mlx-lm-lora. "
                "Install with: pip install enclave-vault[advanced-training]"
            )

        adapter_name = adapter_id or str(uuid.uuid4())

        # Load examples from JSONL
        examples = []
        with open(dataset_path) as f:
            for line in f:
                examples.append(json.loads(line))

        # Build config overrides from kwargs
        overrides = {}
        for key in [
            "lora_rank",
            "lora_alpha",
            "lora_dropout",
            "learning_rate",
            "batch_size",
            "beta",
            "dpo_cpo_loss_type",
            "reward_scaling",
            "group_size",
            "temperature",
            "qat_enable",
            "qat_bits",
        ]:
            if key in kwargs:
                overrides[key] = kwargs[key]

        config = AdvancedTrainingConfig(
            model=self.model_name,
            train_mode=train_mode,
            train_type="dora" if kwargs.get("use_dora", True) else "lora",
            lora_rank=kwargs.get("rank", 8),
            lora_alpha=kwargs.get("alpha", 16),
            learning_rate=kwargs.get("learning_rate", 1e-5),
            batch_size=kwargs.get("batch_size", 4),
            **overrides,
        )

        # Choose trainer method
        trainer = MLXTrainer(
            model_name=self.model_name,
            output_dir=str(self.output_dir),
        )

        start_time = time.time()
        progress_messages: List[str] = []

        def _progress(p: float, msg: str):
            progress_messages.append(f"[{p:.0%}] {msg}")
            logger.info(f"[{train_mode}] {msg}")

        if train_mode == "sft":
            from advanced_vault.training.mlx_trainer import TrainingExample

            training_examples = [
                TrainingExample(messages=ex.get("messages", []))
                for ex in examples
            ]
            result = trainer.train_sft_advanced(
                examples=training_examples,
                adapter_name=adapter_name,
                qat_enable=kwargs.get("qat_enable", False),
                config_overrides=overrides,
                progress_callback=_progress,
            )
        elif train_mode == "dpo":
            result = trainer.train_dpo(
                examples=examples,
                adapter_name=adapter_name,
                beta=kwargs.get("beta", 0.1),
                loss_type=kwargs.get("dpo_cpo_loss_type", "sigmoid"),
                config_overrides=overrides,
                progress_callback=_progress,
            )
        elif train_mode == "orpo":
            result = trainer.train_orpo(
                examples=examples,
                adapter_name=adapter_name,
                beta=kwargs.get("beta", 0.1),
                reward_scaling=kwargs.get("reward_scaling", 1.0),
                config_overrides=overrides,
                progress_callback=_progress,
            )
        elif train_mode == "grpo":
            result = trainer.train_grpo(
                examples=examples,
                adapter_name=adapter_name,
                group_size=kwargs.get("group_size", 4),
                reward_functions=kwargs.get("reward_functions"),
                reward_functions_file=kwargs.get("reward_functions_file"),
                reward_weights=kwargs.get("reward_weights"),
                config_overrides=overrides,
                progress_callback=_progress,
            )
        else:
            raise ValueError(f"Unsupported train_mode: {train_mode}")

        elapsed = time.time() - start_time

        return {
            "success": True,
            "job_id": adapter_name,
            "adapter_id": adapter_name,
            "user_id": "local",
            "status": "completed",
            "submitted_at": result.created_at.isoformat(),
            "completed_at": result.created_at.isoformat(),
            "train_mode": result.train_mode,
            "model_name": result.model_name,
            "iters": result.iters,
            "final_loss": result.final_loss,
            "training_time_seconds": elapsed,
            "adapter_path": str(result.adapter_path),
            "progress_log": progress_messages,
        }

    def train_dpo_from_qa_pairs(
        self,
        qa_pairs: List[Dict[str, str]],
        adapter_name: str,
        num_rejected_per_question: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        End-to-end DPO training from QA pairs with synthetic rejection generation.

        Args:
            qa_pairs: List of {"question": "...", "answer": "..."}
            adapter_name: Name for the output adapter
            num_rejected_per_question: Rejected variants per question
            **kwargs: Passed to train_dpo config_overrides

        Returns:
            Job status dict
        """
        if not self._backend_available:
            raise ImportError(
                "DPO training requires mlx-lm-lora. "
                "Install with: pip install enclave-vault[advanced-training]"
            )

        pipeline = DocumentDPOPipeline(
            output_dir=str(self.output_dir),
            model_name=self.model_name,
        )

        import uuid
        import time

        adapter_name = adapter_name or str(uuid.uuid4())
        progress_messages: List[str] = []

        def _progress(p: float, msg: str):
            progress_messages.append(f"[{p:.0%}] {msg}")

        result = pipeline.train_from_qa_pairs(
            qa_pairs=qa_pairs,
            adapter_name=adapter_name,
            train_mode="dpo",
            num_rejected_per_question=num_rejected_per_question,
            config_overrides=kwargs,
            progress_callback=_progress,
        )

        return {
            "success": True,
            "job_id": adapter_name,
            "adapter_id": adapter_name,
            "status": "completed",
            "train_mode": "dpo",
            "model_name": result.model_name,
            "iters": result.iters,
            "final_loss": result.final_loss,
            "adapter_path": str(result.adapter_path),
            "progress_log": progress_messages,
        }

    def list_adapters(self) -> List[Dict[str, Any]]:
        """List locally trained adapters."""
        if self._backend_available:
            backend = MLXLoRABackend(output_dir=str(self.output_dir))
            return backend.list_adapters()
        # Fallback to legacy listing
        trainer = MLXTrainer(output_dir=str(self.output_dir))
        return trainer.list_adapters()

    def delete_adapter(self, adapter_name: str) -> bool:
        """Delete a locally trained adapter."""
        if self._backend_available:
            backend = MLXLoRABackend(output_dir=str(self.output_dir))
            return backend.delete_adapter(adapter_name)
        trainer = MLXTrainer(output_dir=str(self.output_dir))
        return trainer.delete_adapter(adapter_name)
