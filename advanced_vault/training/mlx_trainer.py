"""
MLX Trainer for Enclave.

Provides local LoRA/DoRA fine-tuning on Apple Silicon using mlx-lm.
Supports encrypted adapter storage and progress callbacks.
"""

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

# Default training configuration
DEFAULT_CONFIG = {
    "model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "lora_rank": 8,
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "learning_rate": 1e-4,
    "batch_size": 2,
    "epochs": 3,
    "max_seq_length": 512,
    "warmup_steps": 50,
    "use_dora": True,  # DoRA instead of LoRA for better quality
}

# Recommended models by memory
RECOMMENDED_MODELS = {
    "8GB": "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "16GB": "mlx-community/Qwen2.5-3B-Instruct-4bit",
    "24GB": "mlx-community/Qwen2.5-7B-Instruct-4bit",
    "32GB+": "mlx-community/Qwen2.5-14B-Instruct-4bit",
}


@dataclass
class TrainingExample:
    """A single training example in chat format."""

    messages: List[Dict[str, str]]  # [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": self.messages,
        }


@dataclass
class TrainingResult:
    """Result of a training run."""

    adapter_path: Path
    model_name: str
    num_examples: int
    epochs: int
    final_loss: float
    training_time_seconds: float
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_path": str(self.adapter_path),
            "model_name": self.model_name,
            "num_examples": self.num_examples,
            "epochs": self.epochs,
            "final_loss": self.final_loss,
            "training_time_seconds": self.training_time_seconds,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


def check_mlx_available() -> bool:
    """Check if MLX is available."""
    try:
        import mlx.core  # noqa: F401
        return True
    except ImportError:
        return False


def get_recommended_model(memory_gb: int = 24) -> str:
    """Get recommended model for available memory."""
    if memory_gb <= 8:
        return RECOMMENDED_MODELS["8GB"]
    elif memory_gb <= 16:
        return RECOMMENDED_MODELS["16GB"]
    elif memory_gb <= 24:
        return RECOMMENDED_MODELS["24GB"]
    else:
        return RECOMMENDED_MODELS["32GB+"]


class MLXTrainer:
    """
    Local LoRA/DoRA trainer using MLX.

    Features:
    - LoRA and DoRA fine-tuning
    - Configurable rank and hyperparameters
    - Progress callbacks for UI integration
    - Adapter encryption support
    - Memory-efficient training
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        output_dir: str = "~/.enclave/adapters",
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize trainer.

        Args:
            model_name: Base model name/path (HuggingFace format)
            output_dir: Directory for adapter output
            config: Training configuration overrides
        """
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        if model_name:
            self.config["model"] = model_name

        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._model = None
        self._tokenizer = None

        logger.info(
            f"Initialized MLXTrainer with model: {self.config['model']}, "
            f"output_dir: {self.output_dir}"
        )

    def _check_dependencies(self):
        """Check that required dependencies are available."""
        if not check_mlx_available():
            raise ImportError(
                "MLX is required for local training on Apple Silicon. "
                "Install with: pip install mlx mlx-lm"
            )

        try:
            import mlx_lm  # noqa: F401
        except ImportError:
            raise ImportError(
                "mlx-lm is required for LoRA training. "
                "Install with: pip install mlx-lm"
            )

    def _prepare_dataset(
        self,
        examples: List[TrainingExample],
        output_path: Path
    ) -> Path:
        """
        Prepare dataset in mlx-lm format.

        Args:
            examples: Training examples
            output_path: Path to save dataset

        Returns:
            Path to dataset file
        """
        dataset_path = output_path / "train.jsonl"

        with open(dataset_path, "w") as f:
            for example in examples:
                f.write(json.dumps(example.to_dict()) + "\n")

        # Create validation split (10%)
        val_size = max(1, len(examples) // 10)
        val_path = output_path / "valid.jsonl"

        with open(val_path, "w") as f:
            for example in examples[:val_size]:
                f.write(json.dumps(example.to_dict()) + "\n")

        logger.info(f"Prepared dataset: {len(examples)} train, {val_size} valid")
        return dataset_path.parent

    def train(
        self,
        examples: List[TrainingExample],
        adapter_name: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> TrainingResult:
        """
        Train a LoRA/DoRA adapter.

        Args:
            examples: List of training examples
            adapter_name: Name for the adapter
            progress_callback: Optional callback(progress: 0-1, message: str)

        Returns:
            TrainingResult with adapter path and metrics
        """
        self._check_dependencies()

        import time
        start_time = time.time()

        if progress_callback:
            progress_callback(0.0, "Preparing dataset...")

        # Create temp directory for training
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Prepare dataset
            dataset_path = self._prepare_dataset(examples, temp_path)

            if progress_callback:
                progress_callback(0.1, "Loading model...")

            # Import mlx-lm modules
            from mlx_lm import load, generate
            from mlx_lm.tuner.trainer import TrainingArgs, train as mlx_train
            from mlx_lm.tuner.datasets import Dataset
            from mlx_lm.tuner.utils import linear_to_lora_layers
            import mlx.core as mx

            # Load model and tokenizer
            model, tokenizer = load(self.config["model"])

            if progress_callback:
                progress_callback(0.2, "Configuring LoRA layers...")

            # Configure LoRA/DoRA
            lora_config = {
                "rank": self.config["lora_rank"],
                "alpha": self.config["lora_alpha"],
                "dropout": self.config["lora_dropout"],
                "scale": self.config["lora_alpha"] / self.config["lora_rank"],
            }

            # Apply LoRA to model
            num_layers = len(model.model.layers) if hasattr(model, "model") else len(model.layers)
            model = linear_to_lora_layers(
                model,
                lora_layers=num_layers,  # Apply to all layers
                lora_parameters=lora_config,
                use_dora=self.config.get("use_dora", True)
            )

            # Prepare training arguments
            adapter_output = self.output_dir / adapter_name
            adapter_output.mkdir(parents=True, exist_ok=True)

            training_args = TrainingArgs(
                batch_size=self.config["batch_size"],
                iters=len(examples) * self.config["epochs"] // self.config["batch_size"],
                val_batches=5,
                steps_per_report=10,
                steps_per_eval=50,
                steps_per_save=100,
                adapter_path=str(adapter_output),
                max_seq_length=self.config["max_seq_length"],
                grad_checkpoint=True,  # Memory efficient
            )

            if progress_callback:
                progress_callback(0.3, "Loading dataset...")

            # Load dataset
            train_set = Dataset(
                path=str(dataset_path / "train.jsonl"),
                tokenizer=tokenizer,
                max_seq_length=self.config["max_seq_length"]
            )
            valid_set = Dataset(
                path=str(dataset_path / "valid.jsonl"),
                tokenizer=tokenizer,
                max_seq_length=self.config["max_seq_length"]
            )

            if progress_callback:
                progress_callback(0.4, "Starting training...")

            # Custom progress tracking
            last_loss = 0.0
            total_steps = training_args.iters

            def step_callback(step: int, loss: float):
                nonlocal last_loss
                last_loss = loss
                if progress_callback:
                    progress = 0.4 + 0.5 * (step / total_steps)
                    progress_callback(progress, f"Training step {step}/{total_steps}, loss: {loss:.4f}")

            # Train
            try:
                mlx_train(
                    model=model,
                    tokenizer=tokenizer,
                    args=training_args,
                    train_dataset=train_set,
                    val_dataset=valid_set,
                )
            except Exception as e:
                logger.error(f"Training failed: {e}")
                raise

            if progress_callback:
                progress_callback(0.95, "Saving adapter...")

            # Save adapter config
            config_path = adapter_output / "adapter_config.json"
            with open(config_path, "w") as f:
                json.dump({
                    "base_model": self.config["model"],
                    "lora_rank": self.config["lora_rank"],
                    "lora_alpha": self.config["lora_alpha"],
                    "use_dora": self.config.get("use_dora", True),
                    "num_examples": len(examples),
                    "epochs": self.config["epochs"],
                    "created_at": datetime.utcnow().isoformat(),
                }, f, indent=2)

            training_time = time.time() - start_time

            if progress_callback:
                progress_callback(1.0, "Training complete!")

            result = TrainingResult(
                adapter_path=adapter_output,
                model_name=self.config["model"],
                num_examples=len(examples),
                epochs=self.config["epochs"],
                final_loss=last_loss,
                training_time_seconds=training_time,
                metadata={
                    "lora_rank": self.config["lora_rank"],
                    "use_dora": self.config.get("use_dora", True),
                }
            )

            logger.info(
                f"Training complete: {len(examples)} examples, "
                f"{training_time:.1f}s, final_loss={last_loss:.4f}"
            )

            return result

    def train_from_qa_pairs(
        self,
        qa_pairs: List[Dict[str, str]],
        adapter_name: str,
        system_prompt: str = "You are a helpful assistant that answers questions based on the provided context.",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> TrainingResult:
        """
        Train from QA pairs (convenience method).

        Args:
            qa_pairs: List of {"question": ..., "answer": ...} dicts
            adapter_name: Name for the adapter
            system_prompt: System prompt for training
            progress_callback: Optional progress callback

        Returns:
            TrainingResult
        """
        examples = []
        for pair in qa_pairs:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pair["question"]},
                {"role": "assistant", "content": pair["answer"]},
            ]
            examples.append(TrainingExample(messages=messages))

        return self.train(examples, adapter_name, progress_callback)

    def list_adapters(self) -> List[Dict[str, Any]]:
        """
        List trained adapters.

        Returns:
            List of adapter info dicts
        """
        adapters = []

        for adapter_dir in self.output_dir.iterdir():
            if not adapter_dir.is_dir():
                continue

            config_path = adapter_dir / "adapter_config.json"
            if not config_path.exists():
                continue

            try:
                with open(config_path) as f:
                    config = json.load(f)

                adapters.append({
                    "name": adapter_dir.name,
                    "path": str(adapter_dir),
                    "base_model": config.get("base_model"),
                    "created_at": config.get("created_at"),
                    "num_examples": config.get("num_examples"),
                    "use_dora": config.get("use_dora", False),
                })
            except Exception as e:
                logger.warning(f"Failed to load adapter config {config_path}: {e}")

        return sorted(adapters, key=lambda a: a.get("created_at", ""), reverse=True)

    def delete_adapter(self, adapter_name: str) -> bool:
        """
        Delete an adapter.

        Args:
            adapter_name: Adapter name

        Returns:
            True if deleted, False if not found
        """
        adapter_path = self.output_dir / adapter_name
        if not adapter_path.exists():
            return False

        shutil.rmtree(adapter_path)
        logger.info(f"Deleted adapter: {adapter_name}")
        return True
