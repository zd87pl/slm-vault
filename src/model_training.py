"""
Personalized SLM Finetuning Framework
Implements multimodal model architecture and continuous learning
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.utils.data import DataLoader
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
    TrainingArguments,
    Trainer
)
from peft import LoraConfig, get_peft_model, TaskType
import numpy as np
from dataclasses import dataclass
import wandb


@dataclass
class TrainingConfig:
    """Configuration for model training"""
    base_model: str = "meta-llama/Llama-3.2-1B"
    learning_rate: float = 5e-5
    batch_size: int = 4
    gradient_accumulation_steps: int = 8
    num_epochs: int = 3
    warmup_ratio: float = 0.1
    max_seq_length: int = 2048
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    save_steps: int = 100
    eval_steps: int = 50
    logging_steps: int = 10
    use_mixed_precision: bool = True
    gradient_checkpointing: bool = True


class MultiModalSLM(nn.Module):
    """Multimodal Small Language Model with genetic and fitness data integration"""

    def __init__(self, config: TrainingConfig):
        super().__init__()
        self.config = config

        # Load base language model
        self.language_model = AutoModelForCausalLM.from_pretrained(
            config.base_model,
            torch_dtype=torch.float16 if config.use_mixed_precision else torch.float32,
            device_map="auto"
        )

        # Add LoRA adapters for efficient finetuning
        lora_config = LoraConfig(
            r=config.lora_rank,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
            task_type=TaskType.CAUSAL_LM
        )
        self.language_model = get_peft_model(self.language_model, lora_config)

        # Genetic data encoder
        self.genetic_encoder = nn.Sequential(
            nn.Linear(768, 512),  # From EVO2 embeddings
            nn.LayerNorm(512),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(512, 256)
        )

        # Fitness metrics encoder
        self.fitness_encoder = nn.Sequential(
            nn.Linear(4, 128),  # 4 main fitness metrics
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 256)
        )

        # Cross-attention for multimodal fusion
        self.cross_attention = nn.MultiheadAttention(
            embed_dim=256,
            num_heads=8,
            dropout=0.1,
            batch_first=True
        )

        # Projection to language model dimension
        hidden_size = self.language_model.config.hidden_size
        self.multimodal_projection = nn.Linear(256, hidden_size)

        # Gating mechanism for adaptive fusion
        self.fusion_gate = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.Sigmoid()
        )

    def encode_multimodal_context(self, genetic_embedding, fitness_metrics):
        """Encode non-text modalities"""
        # Encode genetic data
        genetic_features = self.genetic_encoder(genetic_embedding)

        # Encode fitness metrics
        fitness_features = self.fitness_encoder(fitness_metrics)

        # Combine via cross-attention
        combined, _ = self.cross_attention(
            genetic_features.unsqueeze(1),
            fitness_features.unsqueeze(1),
            fitness_features.unsqueeze(1)
        )

        # Project to LM dimension
        multimodal_context = self.multimodal_projection(combined.squeeze(1))

        return multimodal_context

    def forward(self, input_ids, attention_mask, genetic_embedding, fitness_metrics, labels=None):
        """Forward pass with multimodal inputs"""
        # Get language model embeddings
        lm_outputs = self.language_model.model.embed_tokens(input_ids)

        # Encode multimodal context
        multimodal_context = self.encode_multimodal_context(
            genetic_embedding, fitness_metrics
        )

        # Get first token position for injection
        batch_size = input_ids.shape[0]
        multimodal_context = multimodal_context.unsqueeze(1)

        # Adaptive gating
        gate = self.fusion_gate(
            torch.cat([lm_outputs[:, 0:1, :], multimodal_context], dim=-1)
        )

        # Inject multimodal context at beginning
        fused_embeddings = torch.cat([
            multimodal_context * gate,
            lm_outputs[:, 1:, :]
        ], dim=1)

        # Forward through language model
        outputs = self.language_model(
            inputs_embeds=fused_embeddings,
            attention_mask=attention_mask,
            labels=labels
        )

        return outputs


class PersonalizedSLMTrainer:
    """Trainer for personal SLM with continuous learning capabilities"""

    def __init__(self, user_id: str, config: TrainingConfig):
        self.user_id = user_id
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Initialize model
        self.model = MultiModalSLM(config).to(self.device)

        # Optimizer and scheduler
        self.optimizer = AdamW(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=0.01
        )

        # Training history for replay buffer
        self.replay_buffer = []
        self.training_history = []

        # Model versioning
        self.model_version = 0
        self.checkpoint_dir = Path(f"/secure-storage/{user_id}/checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def train_epoch(self, dataloader: DataLoader, epoch: int):
        """Train for one epoch"""
        self.model.train()
        total_loss = 0
        num_batches = 0

        for batch_idx, batch in enumerate(dataloader):
            # Move to device
            batch = {k: v.to(self.device) for k, v in batch.items()}

            # Forward pass
            outputs = self.model(
                input_ids=batch['input_ids'],
                attention_mask=batch['attention_mask'],
                genetic_embedding=batch['genetic_embedding'],
                fitness_metrics=batch['fitness_metrics'],
                labels=batch['labels']
            )

            loss = outputs.loss

            # Gradient accumulation
            loss = loss / self.config.gradient_accumulation_steps
            loss.backward()

            if (batch_idx + 1) % self.config.gradient_accumulation_steps == 0:
                # Gradient clipping
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)

                # Optimizer step
                self.optimizer.step()
                self.optimizer.zero_grad()

            total_loss += loss.item()
            num_batches += 1

            # Logging
            if batch_idx % self.config.logging_steps == 0:
                print(f"Epoch {epoch}, Batch {batch_idx}, Loss: {loss.item():.4f}")

        return total_loss / num_batches

    def evaluate(self, dataloader: DataLoader):
        """Evaluate model performance"""
        self.model.eval()
        total_loss = 0
        num_batches = 0

        with torch.no_grad():
            for batch in dataloader:
                batch = {k: v.to(self.device) for k, v in batch.items()}

                outputs = self.model(
                    input_ids=batch['input_ids'],
                    attention_mask=batch['attention_mask'],
                    genetic_embedding=batch['genetic_embedding'],
                    fitness_metrics=batch['fitness_metrics'],
                    labels=batch['labels']
                )

                total_loss += outputs.loss.item()
                num_batches += 1

        return total_loss / num_batches

    def incremental_training(self, new_dataloader: DataLoader, replay_ratio: float = 0.2):
        """Incremental training with replay buffer"""
        print(f"Starting incremental training for user {self.user_id}")

        # Add new data to replay buffer
        for batch in new_dataloader:
            self.replay_buffer.append(batch)

        # Keep buffer size manageable
        max_buffer_size = 1000
        if len(self.replay_buffer) > max_buffer_size:
            self.replay_buffer = self.replay_buffer[-max_buffer_size:]

        # Create mixed dataset with replay samples
        num_replay = int(len(new_dataloader) * replay_ratio)
        replay_samples = np.random.choice(
            self.replay_buffer,
            min(num_replay, len(self.replay_buffer)),
            replace=False
        )

        # Training loop
        for epoch in range(self.config.num_epochs):
            train_loss = self.train_epoch(new_dataloader, epoch)

            # Train on replay samples
            if replay_samples:
                replay_loader = DataLoader(
                    replay_samples,
                    batch_size=self.config.batch_size
                )
                replay_loss = self.train_epoch(replay_loader, epoch)

            # Evaluation
            eval_loss = self.evaluate(new_dataloader)

            # Log metrics
            self.training_history.append({
                'epoch': epoch,
                'train_loss': train_loss,
                'eval_loss': eval_loss,
                'timestamp': datetime.now().isoformat(),
                'model_version': self.model_version
            })

            print(f"Epoch {epoch}: Train Loss: {train_loss:.4f}, Eval Loss: {eval_loss:.4f}")

            # Save checkpoint
            if epoch % self.config.save_steps == 0:
                self.save_checkpoint(epoch)

        # Increment version
        self.model_version += 1

    def save_checkpoint(self, epoch: int):
        """Save model checkpoint with encryption"""
        checkpoint_path = self.checkpoint_dir / f"v{self.model_version}_epoch{epoch}.pt"

        checkpoint = {
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'config': self.config.__dict__,
            'epoch': epoch,
            'version': self.model_version,
            'user_id': self.user_id,
            'timestamp': datetime.now().isoformat()
        }

        # Encrypt before saving
        # In production: implement actual encryption
        torch.save(checkpoint, checkpoint_path)
        print(f"Saved checkpoint to {checkpoint_path}")

    def load_checkpoint(self, checkpoint_path: Path):
        """Load model from checkpoint"""
        checkpoint = torch.load(checkpoint_path, map_location=self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.model_version = checkpoint['version']

        print(f"Loaded checkpoint from {checkpoint_path}")

    def export_model(self, format: str = "onnx"):
        """Export model for deployment"""
        export_path = self.checkpoint_dir / f"model_v{self.model_version}.{format}"

        if format == "onnx":
            # Export to ONNX
            dummy_input = {
                'input_ids': torch.randint(0, 1000, (1, 512)).to(self.device),
                'attention_mask': torch.ones(1, 512).to(self.device),
                'genetic_embedding': torch.randn(1, 768).to(self.device),
                'fitness_metrics': torch.randn(1, 4).to(self.device)
            }

            torch.onnx.export(
                self.model,
                (dummy_input['input_ids'], dummy_input['attention_mask'],
                 dummy_input['genetic_embedding'], dummy_input['fitness_metrics']),
                export_path,
                input_names=['input_ids', 'attention_mask', 'genetic_embedding', 'fitness_metrics'],
                output_names=['logits'],
                dynamic_axes={
                    'input_ids': {0: 'batch_size', 1: 'sequence'},
                    'attention_mask': {0: 'batch_size', 1: 'sequence'},
                    'genetic_embedding': {0: 'batch_size'},
                    'fitness_metrics': {0: 'batch_size'}
                }
            )
        elif format == "torchscript":
            # Export as TorchScript
            scripted_model = torch.jit.script(self.model)
            scripted_model.save(export_path)

        print(f"Exported model to {export_path}")
        return export_path


class TrainingScheduler:
    """Manages training schedules and triggers"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.last_training = None
        self.training_queue = []

    def should_retrain(self, trigger_type: str, metadata: Dict = None) -> bool:
        """Determine if retraining should be triggered"""
        triggers = {
            'nightly': self._check_nightly_schedule,
            'new_data': self._check_data_threshold,
            'performance_drift': self._check_model_drift,
            'user_request': lambda _: True
        }

        trigger_func = triggers.get(trigger_type)
        if trigger_func:
            return trigger_func(metadata)
        return False

    def _check_nightly_schedule(self, metadata: Dict) -> bool:
        """Check if nightly training should run"""
        if self.last_training is None:
            return True

        hours_since_last = (datetime.now() - self.last_training).total_seconds() / 3600
        return hours_since_last >= 24

    def _check_data_threshold(self, metadata: Dict) -> bool:
        """Check if enough new data accumulated"""
        new_samples = metadata.get('new_samples', 0)
        return new_samples >= 100  # Threshold

    def _check_model_drift(self, metadata: Dict) -> bool:
        """Check for performance degradation"""
        current_loss = metadata.get('current_loss', 0)
        baseline_loss = metadata.get('baseline_loss', 0)

        if baseline_loss == 0:
            return False

        drift = abs(current_loss - baseline_loss) / baseline_loss
        return drift > 0.1  # 10% degradation threshold

    def schedule_training(self, priority: str = "normal"):
        """Add training job to queue"""
        job = {
            'user_id': self.user_id,
            'priority': priority,
            'scheduled_at': datetime.now(),
            'status': 'pending'
        }
        self.training_queue.append(job)
        return job


if __name__ == "__main__":
    # Test the training pipeline
    from data_pipeline import DataPipelineManager

    user_id = "test_user_001"
    config = TrainingConfig()

    # Initialize data pipeline
    data_manager = DataPipelineManager(user_id)
    train_dataloader = data_manager.create_dataloader(batch_size=2)

    # Initialize trainer
    trainer = PersonalizedSLMTrainer(user_id, config)

    # Run training
    print("Starting model training...")
    trainer.incremental_training(train_dataloader)

    # Export model
    print("Exporting model...")
    trainer.export_model("torchscript")

    print("Training completed successfully!")