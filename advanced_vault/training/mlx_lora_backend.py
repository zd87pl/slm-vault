"""
MLX-LM-LoRA Backend Wrapper for Enclave.

Thin abstraction over mlx-lm-lora that exposes all advanced training algorithms
(SFT, DPO, ORPO, GRPO, etc.) with Enclave-native progress callbacks and config.
"""

import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Training modes supported by mlx-lm-lora
TRAIN_MODES = [
    "sft",
    "dpo",
    "cpo",
    "orpo",
    "grpo",
    "online_dpo",
    "xpo",
    "rlhf-reinforce",
    "ppo",
]


@dataclass
class AdvancedTrainingConfig:
    """Unified config for all mlx-lm-lora training modes."""

    model: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    train_mode: str = "sft"  # sft, dpo, orpo, grpo, ...
    train_type: str = "lora"  # lora, dora, full
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    learning_rate: float = 1e-5
    batch_size: int = 4
    iters: int = 600
    max_seq_length: int = 2048
    grad_checkpoint: bool = True
    mask_prompt: bool = False
    seed: int = 0

    # DPO / ORPO / preference
    beta: float = 0.1
    reward_scaling: float = 1.0
    dpo_cpo_loss_type: str = "sigmoid"
    delta: float = 50.0
    reference_model_path: Optional[str] = None

    # GRPO
    group_size: int = 4
    epsilon: float = 1e-4
    epsilon_high: Optional[float] = None
    max_completion_length: int = 512
    temperature: float = 0.8
    reward_functions: Optional[str] = None
    reward_functions_file: Optional[str] = None
    reward_weights: Optional[List[float]] = None
    grpo_loss_type: str = "grpo"
    importance_sampling_level: Optional[str] = None

    # QAT
    qat_enable: bool = False
    qat_bits: int = 8
    qat_group_size: int = 64
    qat_mode: str = "affine"
    qat_start_step: int = 1
    qat_interval: int = 1

    # Online DPO / XPO
    judge: Optional[str] = None
    alpha: float = 1e-5

    # Export
    lm_studio_name: Optional[str] = None

    def to_mlx_lm_lora_args(self) -> Dict[str, Any]:
        """Export as argparse Namespace-compatible dict."""
        args = {
            "model": self.model,
            "train": True,
            "train_mode": self.train_mode,
            "train_type": self.train_type,
            "batch_size": self.batch_size,
            "iters": self.iters,
            "learning_rate": self.learning_rate,
            "max_seq_length": self.max_seq_length,
            "grad_checkpoint": self.grad_checkpoint,
            "mask_prompt": self.mask_prompt,
            "seed": self.seed,
            "lora_parameters": {
                "rank": self.lora_rank,
                "alpha": self.lora_alpha,
                "dropout": self.lora_dropout,
                "scale": self.lora_alpha / max(self.lora_rank, 1),
            },
            # Preference
            "beta": self.beta,
            "reward_scaling": self.reward_scaling,
            "dpo_cpo_loss_type": self.dpo_cpo_loss_type,
            "delta": self.delta,
            "reference_model_path": self.reference_model_path,
            # GRPO
            "group_size": self.group_size,
            "epsilon": self.epsilon,
            "epsilon_high": self.epsilon_high,
            "max_completion_length": self.max_completion_length,
            "temperature": self.temperature,
            "reward_functions": self.reward_functions,
            "reward_functions_file": self.reward_functions_file,
            "reward_weights": self.reward_weights,
            "grpo_loss_type": self.grpo_loss_type,
            "importance_sampling_level": self.importance_sampling_level,
            # QAT
            "qat_enable": self.qat_enable,
            "qat_bits": self.qat_bits,
            "qat_group_size": self.qat_group_size,
            "qat_mode": self.qat_mode,
            "qat_start_step": self.qat_start_step,
            "qat_interval": self.qat_interval,
            # Online
            "judge": self.judge,
            "alpha": self.alpha,
            # Export
            "lm_studio_name": self.lm_studio_name,
            # Defaults
            "load_in_4bits": False,
            "load_in_6bits": False,
            "load_in_8bits": False,
            "load_in_mxfp4": False,
            "optimizer": "adam",
            "optimizer_config": {"adam": {}, "adamw": {}, "muon": {}},
            "data": "data/",
            "num_layers": -1,
            "epochs": None,
            "gradient_accumulation_steps": 1,
            "val_batches": 25,
            "steps_per_report": 10,
            "steps_per_eval": 200,
            "resume_adapter_file": None,
            "adapter_path": "adapters",
            "save_every": 100,
            "test": False,
            "test_batches": 500,
            "config": None,
            "efficient_long_context": False,
            "lr_schedule": None,
            "fuse": True,
        }
        return args


@dataclass
class AdvancedTrainingResult:
    """Result of an advanced training run."""

    adapter_path: Path
    model_name: str
    train_mode: str
    num_examples: int
    iters: int
    final_loss: float
    training_time_seconds: float
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_path": str(self.adapter_path),
            "model_name": self.model_name,
            "train_mode": self.train_mode,
            "num_examples": self.num_examples,
            "iters": self.iters,
            "final_loss": self.final_loss,
            "training_time_seconds": self.training_time_seconds,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


def _check_mlx_lm_lora() -> bool:
    """Check if mlx-lm-lora is installed."""
    try:
        import mlx_lm_lora  # noqa: F401
        return True
    except ImportError:
        return False


class MLXLoRABackend:
    """
    Backend wrapper around mlx-lm-lora.

    Provides Enclave-native APIs while delegating all training to mlx-lm-lora.
    """

    def __init__(self, output_dir: str = "~/.enclave/adapters"):
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not _check_mlx_lm_lora():
            raise ImportError(
                "mlx-lm-lora is required for advanced training. "
                "Install with: pip install mlx-lm-lora"
            )

    def _write_dataset(
        self,
        examples: List[Dict[str, Any]],
        output_dir: Path,
        mode: str = "sft",
    ) -> Path:
        """
        Write examples to mlx-lm-lora compatible dataset files.

        Supports:
        - sft: {"messages": [...]}
        - dpo/orpo/cpo: {"prompt": "...", "chosen": "...", "rejected": "..."}
        - grpo: {"prompt": "...", "answer": "..."}
        """
        data_dir = output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        train_path = data_dir / "train.jsonl"
        valid_path = data_dir / "valid.jsonl"

        val_size = max(1, len(examples) // 10)
        train_examples = examples[val_size:]
        valid_examples = examples[:val_size]

        with open(train_path, "w") as f:
            for ex in train_examples:
                f.write(json.dumps(ex) + "\n")

        with open(valid_path, "w") as f:
            for ex in valid_examples:
                f.write(json.dumps(ex) + "\n")

        logger.info(
            f"Prepared {mode} dataset: {len(train_examples)} train, "
            f"{len(valid_examples)} valid"
        )
        return data_dir

    def _build_progress_callback(
        self,
        user_callback: Optional[Callable[[float, str], None]],
        total_iters: int,
    ) -> Callable:
        """
        Build a progress callback compatible with mlx-lm-lora's TrainingCallback.

        mlx-lm-lora uses a callback signature: callback(step, loss, info_dict)
        We translate that to Enclave's (progress_0_1, message).
        """
        if user_callback is None:
            return None

        def callback(step: int, loss: float, info: Dict[str, Any] = None):
            progress = min(1.0, step / max(total_iters, 1))
            msg = f"Step {step}/{total_iters}, loss: {loss:.4f}"
            user_callback(progress, msg)

        return callback

    def train(
        self,
        examples: List[Dict[str, Any]],
        adapter_name: str,
        config: AdvancedTrainingConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> AdvancedTrainingResult:
        """
        Train an adapter using any mlx-lm-lora algorithm.

        Args:
            examples: Training examples (format depends on train_mode)
            adapter_name: Name for the output adapter
            config: AdvancedTrainingConfig specifying algorithm and hyperparams
            progress_callback: Optional Enclave-style progress callback

        Returns:
            AdvancedTrainingResult
        """
        import time

        start_time = time.time()
        adapter_output = self.output_dir / adapter_name
        adapter_output.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(0.0, f"Preparing {config.train_mode} dataset...")

        # Write dataset
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_path = Path(tmp_dir)
            data_dir = self._write_dataset(examples, temp_path, mode=config.train_mode)

            # Build args for mlx-lm-lora
            args_dict = config.to_mlx_lm_lora_args()
            args_dict["data"] = str(data_dir)
            args_dict["adapter_path"] = str(adapter_output)

            if progress_callback:
                progress_callback(0.1, "Loading model...")

            # Import mlx-lm-lora training orchestrator
            from mlx_lm_lora.train import (
                build_parser,
                calculate_iters,
                load_judge_model,
                load_reference_model,
                load_reward_functions_from_file,
            )
            from mlx_lm_lora.trainer.datasets import load_dataset
            from mlx_lm_lora.utils import from_pretrained
            from mlx_lm_lora.visuals import print_banner, print_info
            from mlx_lm import load as mlx_load
            import mlx.core as mx
            import numpy as np

            # Convert dict to argparse Namespace
            parser = build_parser()
            # We need to create a namespace object manually since we already have the dict
            import argparse

            args = argparse.Namespace(**args_dict)

            # Set random seed
            np.random.seed(args.seed)
            mx.random.seed(args.seed)

            if progress_callback:
                progress_callback(0.15, f"Loading {args.model}...")

            # Load model and tokenizer
            model, tokenizer = mlx_load(args.model)

            if progress_callback:
                progress_callback(0.2, "Configuring LoRA/DoRA layers...")

            # Apply LoRA/DoRA using mlx-lm-lora's utility
            from mlx_lm.tuner.utils import linear_to_lora_layers

            num_layers = (
                len(model.model.layers)
                if hasattr(model, "model")
                else len(model.layers)
            )
            lora_layers = (
                num_layers if args.num_layers == -1 else args.num_layers
            )

            model = linear_to_lora_layers(
                model,
                lora_layers=lora_layers,
                lora_parameters=args.lora_parameters,
                use_dora=(args.train_type == "dora"),
            )

            if progress_callback:
                progress_callback(0.25, "Loading dataset...")

            # Load dataset using mlx-lm-lora's loader
            train_set, valid_set, test_set = load_dataset(
                args,
                tokenizer,
                is_train=(args.train and not args.test),
            )

            if progress_callback:
                progress_callback(0.3, "Starting training...")

            # Determine total iterations
            total_iters = args.iters
            if args.epochs is not None and args.iters is None:
                total_iters = calculate_iters(
                    train_set, args.batch_size, args.epochs
                )

            # Wrap progress callback
            wrapped_callback = self._build_progress_callback(
                progress_callback, total_iters
            )

            # Dispatch to correct trainer
            final_loss = 0.0

            if args.train_mode == "sft":
                from mlx_lm_lora.trainer.sft_trainer import (
                    SFTTrainingArgs,
                    evaluate_sft,
                    train_sft,
                )

                training_args = SFTTrainingArgs(
                    batch_size=args.batch_size,
                    iters=total_iters,
                    gradient_accumulation_steps=args.gradient_accumulation_steps,
                    val_batches=args.val_batches,
                    steps_per_report=args.steps_per_report,
                    steps_per_eval=args.steps_per_eval,
                    steps_per_save=args.save_every,
                    adapter_file=str(adapter_output / "adapters.safetensors"),
                    max_seq_length=args.max_seq_length,
                    grad_checkpoint=args.grad_checkpoint,
                    qat_enable=args.qat_enable,
                    qat_bits=args.qat_bits,
                    qat_group_size=args.qat_group_size,
                    qat_mode=args.qat_mode,
                    qat_start_step=args.qat_start_step,
                    qat_interval=args.qat_interval,
                )

                final_loss = train_sft(
                    model=model,
                    tokenizer=tokenizer,
                    args=training_args,
                    train_dataset=train_set,
                    val_dataset=valid_set,
                    training_callback=wrapped_callback,
                )

            elif args.train_mode in ("dpo", "cpo"):
                from mlx_lm_lora.trainer.dpo_trainer import (
                    DPOTrainingArgs,
                    evaluate_dpo,
                    train_dpo,
                )

                ref_model = load_reference_model(args)

                training_args = DPOTrainingArgs(
                    batch_size=args.batch_size,
                    iters=total_iters,
                    gradient_accumulation_steps=args.gradient_accumulation_steps,
                    val_batches=args.val_batches,
                    steps_per_report=args.steps_per_report,
                    steps_per_eval=args.steps_per_eval,
                    steps_per_save=args.save_every,
                    adapter_file=str(adapter_output / "adapters.safetensors"),
                    max_seq_length=args.max_seq_length,
                    grad_checkpoint=args.grad_checkpoint,
                    beta=args.beta,
                    loss_type=args.dpo_cpo_loss_type,
                    delta=args.delta,
                    reference_model_path=args.reference_model_path,
                    qat_enable=args.qat_enable,
                    qat_bits=args.qat_bits,
                    qat_group_size=args.qat_group_size,
                    qat_mode=args.qat_mode,
                    qat_start_step=args.qat_start_step,
                    qat_interval=args.qat_interval,
                )

                final_loss = train_dpo(
                    model=model,
                    ref_model=ref_model,
                    tokenizer=tokenizer,
                    args=training_args,
                    train_dataset=train_set,
                    val_dataset=valid_set,
                    training_callback=wrapped_callback,
                )

            elif args.train_mode == "orpo":
                from mlx_lm_lora.trainer.orpo_trainer import (
                    ORPOTrainingArgs,
                    evaluate_orpo,
                    train_orpo,
                )

                training_args = ORPOTrainingArgs(
                    batch_size=args.batch_size,
                    iters=total_iters,
                    gradient_accumulation_steps=args.gradient_accumulation_steps,
                    val_batches=args.val_batches,
                    steps_per_report=args.steps_per_report,
                    steps_per_eval=args.steps_per_eval,
                    steps_per_save=args.save_every,
                    adapter_file=str(adapter_output / "adapters.safetensors"),
                    max_seq_length=args.max_seq_length,
                    grad_checkpoint=args.grad_checkpoint,
                    beta=args.beta,
                    reward_scaling=args.reward_scaling,
                    qat_enable=args.qat_enable,
                    qat_bits=args.qat_bits,
                    qat_group_size=args.qat_group_size,
                    qat_mode=args.qat_mode,
                    qat_start_step=args.qat_start_step,
                    qat_interval=args.qat_interval,
                )

                final_loss = train_orpo(
                    model=model,
                    tokenizer=tokenizer,
                    args=training_args,
                    train_dataset=train_set,
                    val_dataset=valid_set,
                    training_callback=wrapped_callback,
                )

            elif args.train_mode == "grpo":
                from mlx_lm_lora.trainer.grpo_trainer import (
                    GRPOTrainingArgs,
                    evaluate_grpo,
                    train_grpo,
                )

                # Load custom reward functions if specified
                if args.reward_functions_file:
                    load_reward_functions_from_file(args.reward_functions_file)

                ref_model = load_reference_model(args)

                training_args = GRPOTrainingArgs(
                    batch_size=args.batch_size,
                    iters=total_iters,
                    gradient_accumulation_steps=args.gradient_accumulation_steps,
                    val_batches=args.val_batches,
                    steps_per_report=args.steps_per_report,
                    steps_per_eval=args.steps_per_eval,
                    steps_per_save=args.save_every,
                    adapter_file=str(adapter_output / "adapters.safetensors"),
                    max_seq_length=args.max_seq_length,
                    grad_checkpoint=args.grad_checkpoint,
                    group_size=args.group_size,
                    beta=args.beta,
                    epsilon=args.epsilon,
                    epsilon_high=args.epsilon_high,
                    max_completion_length=args.max_completion_length,
                    temperature=args.temperature,
                    reference_model_path=args.reference_model_path,
                    reward_weights=args.reward_weights,
                    grpo_loss_type=args.grpo_loss_type,
                    importance_sampling_level=args.importance_sampling_level,
                )

                final_loss = train_grpo(
                    model=model,
                    ref_model=ref_model,
                    tokenizer=tokenizer,
                    args=training_args,
                    train_dataset=train_set,
                    val_dataset=valid_set,
                    training_callback=wrapped_callback,
                )

            else:
                raise ValueError(f"Unsupported train_mode: {args.train_mode}")

            if progress_callback:
                progress_callback(0.95, "Saving adapter and config...")

            # Save merged model if requested
            if args.lm_studio_name:
                from mlx_lm_lora.utils import save_to_lmstudio_merged

                save_to_lmstudio_merged(
                    model_path=args.model,
                    adapter_path=str(adapter_output),
                    output_path=str(adapter_output / "merged_lmstudio"),
                    lm_studio_name=args.lm_studio_name,
                )

            # Write Enclave-compatible adapter config
            config_path = adapter_output / "adapter_config.json"
            with open(config_path, "w") as f:
                json.dump(
                    {
                        "base_model": args.model,
                        "train_mode": args.train_mode,
                        "train_type": args.train_type,
                        "lora_rank": args.lora_parameters["rank"],
                        "lora_alpha": args.lora_parameters["alpha"],
                        "use_dora": args.train_type == "dora",
                        "num_examples": len(examples),
                        "iters": total_iters,
                        "final_loss": final_loss,
                        "created_at": datetime.utcnow().isoformat(),
                        "qat": {
                            "enabled": args.qat_enable,
                            "bits": args.qat_bits,
                        },
                    },
                    f,
                    indent=2,
                )

            training_time = time.time() - start_time

            if progress_callback:
                progress_callback(1.0, "Training complete!")

            return AdvancedTrainingResult(
                adapter_path=adapter_output,
                model_name=args.model,
                train_mode=args.train_mode,
                num_examples=len(examples),
                iters=total_iters,
                final_loss=final_loss,
                training_time_seconds=training_time,
                metadata={
                    "lora_rank": args.lora_parameters["rank"],
                    "use_dora": args.train_type == "dora",
                    "qat_enabled": args.qat_enable,
                },
            )

    def list_adapters(self) -> List[Dict[str, Any]]:
        """List trained adapters."""
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
                adapters.append(
                    {
                        "name": adapter_dir.name,
                        "path": str(adapter_dir),
                        "base_model": config.get("base_model"),
                        "train_mode": config.get("train_mode", "sft"),
                        "train_type": config.get("train_type", "lora"),
                        "created_at": config.get("created_at"),
                        "num_examples": config.get("num_examples"),
                        "use_dora": config.get("use_dora", False),
                        "qat_enabled": config.get("qat", {}).get("enabled", False),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to load adapter config {config_path}: {e}")
        return sorted(
            adapters, key=lambda a: a.get("created_at", ""), reverse=True
        )

    def delete_adapter(self, adapter_name: str) -> bool:
        """Delete an adapter."""
        adapter_path = self.output_dir / adapter_name
        if not adapter_path.exists():
            return False
        shutil.rmtree(adapter_path)
        logger.info(f"Deleted adapter: {adapter_name}")
        return True
