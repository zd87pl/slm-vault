"""
Axolotl-based Serverless Fine-tuning for Personal SLMs
Leverages Axolotl's optimized training capabilities with RunPod serverless
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import torch
import runpod
from huggingface_hub import HfApi, create_repo, upload_folder
import wandb
import hashlib
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class AxolotlConfig:
    """Configuration for Axolotl fine-tuning"""
    # Model configuration
    base_model: str = "meta-llama/Llama-3.2-1B"
    model_type: str = "LlamaForCausalLM"
    tokenizer_type: str = "AutoTokenizer"
    load_in_8bit: bool = False
    load_in_4bit: bool = True  # QLoRA by default

    # LoRA/QLoRA configuration
    adapter: str = "qlora"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: List[str] = None
    lora_target_linear: bool = True

    # Training configuration
    sequence_len: int = 2048
    sample_packing: bool = True
    pad_to_sequence_len: bool = True

    micro_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    num_epochs: int = 3
    optimizer: str = "paged_adamw_8bit"
    lr_scheduler: str = "cosine"
    learning_rate: float = 2e-4

    # Advanced training options
    gradient_checkpointing: bool = True
    flash_attention: bool = True
    warmup_steps: int = 100
    eval_steps: int = 50
    save_steps: int = 100
    logging_steps: int = 10

    # DPO configuration (optional)
    rl: Optional[str] = None  # "dpo" or "ipo"
    dpo_beta: float = 0.1

    # Multimodal extensions
    use_multimodal: bool = True
    genetic_embedding_dim: int = 768
    fitness_metrics_dim: int = 4

    # Output configuration
    output_dir: str = "./outputs"
    hub_model_id: Optional[str] = None
    push_to_hub: bool = False

    # Weights & Biases
    wandb_project: str = "personal-slm"
    wandb_entity: Optional[str] = None
    wandb_watch: str = "gradients"
    wandb_run_id: Optional[str] = None

    # Special tokens for health data
    special_tokens: List[str] = None

    def __post_init__(self):
        if self.lora_target_modules is None:
            self.lora_target_modules = ["q_proj", "v_proj", "k_proj", "o_proj"]

        if self.special_tokens is None:
            self.special_tokens = [
                "<genetic_context>", "</genetic_context>",
                "<fitness_metrics>", "</fitness_metrics>",
                "<health_goal>", "</health_goal>"
            ]


class AxolotlDatasetFormatter:
    """Format multimodal health data for Axolotl training"""

    def __init__(self, user_id: str):
        self.user_id = user_id

    def format_for_axolotl(
        self,
        genetic_data: Dict,
        fitness_history: List[Dict],
        user_context: Dict
    ) -> List[Dict]:
        """Convert multimodal data to Axolotl-compatible format"""
        formatted_data = []

        for day_metrics in fitness_history:
            # Create conversation-style training sample
            sample = self._create_conversation_sample(
                genetic_data, day_metrics, user_context
            )
            formatted_data.append(sample)

            # Create instruction-style training sample
            instruction_sample = self._create_instruction_sample(
                genetic_data, day_metrics, user_context
            )
            formatted_data.append(instruction_sample)

        return formatted_data

    def _create_conversation_sample(
        self,
        genetic_data: Dict,
        day_metrics: Dict,
        user_context: Dict
    ) -> Dict:
        """Create ShareGPT-style conversation format"""
        genetic_summary = self._summarize_genetics(genetic_data)
        fitness_summary = self._summarize_fitness(day_metrics)

        conversations = [
            {
                "from": "system",
                "value": f"""You are a personalized health AI assistant with access to:
<genetic_context>
{genetic_summary}
</genetic_context>

User Profile:
- Age: {user_context['age']}, Sex: {user_context['sex']}
- Goals: {', '.join(user_context['goals'])}
- Preferences: {user_context.get('diet', 'balanced')} diet"""
            },
            {
                "from": "human",
                "value": f"""<fitness_metrics>
{fitness_summary}
</fitness_metrics>

Based on my current metrics and genetic profile, what should I focus on today?"""
            },
            {
                "from": "gpt",
                "value": self._generate_recommendation(
                    genetic_data, day_metrics, user_context
                )
            }
        ]

        return {"conversations": conversations}

    def _create_instruction_sample(
        self,
        genetic_data: Dict,
        day_metrics: Dict,
        user_context: Dict
    ) -> Dict:
        """Create Alpaca-style instruction format"""
        genetic_summary = self._summarize_genetics(genetic_data)
        fitness_summary = self._summarize_fitness(day_metrics)

        return {
            "instruction": "Provide personalized health recommendations based on genetic and fitness data.",
            "input": f"""<genetic_context>{genetic_summary}</genetic_context>
<fitness_metrics>{fitness_summary}</fitness_metrics>
<health_goal>{user_context.get('primary_goal', 'optimize health')}</health_goal>""",
            "output": self._generate_recommendation(
                genetic_data, day_metrics, user_context
            )
        }

    def _summarize_genetics(self, genetic_data: Dict) -> str:
        """Create concise genetic summary"""
        summary = []

        if 'polygenic_scores' in genetic_data:
            scores = genetic_data['polygenic_scores']
            summary.append(f"Endurance: {scores.get('endurance', 0):.2f}")
            summary.append(f"Strength: {scores.get('strength', 0):.2f}")
            summary.append(f"Recovery: {scores.get('recovery', 0):.2f}")

        if 'actionable_variants' in genetic_data:
            for variant in genetic_data['actionable_variants'][:3]:  # Top 3
                summary.append(f"{variant['gene']}: {variant.get('impact', 'unknown')}")

        return ", ".join(summary)

    def _summarize_fitness(self, day_metrics: Dict) -> str:
        """Create concise fitness summary"""
        return f"""Steps: {day_metrics.get('steps', 0):,}
Heart Rate: {day_metrics.get('heart_rate_avg', 0):.0f} bpm
HRV: {day_metrics.get('hrv', 0):.0f} ms
Sleep: {day_metrics.get('sleep_hours', 0):.1f} hours
Recovery: {day_metrics.get('recovery_score', 0):.2f}
Training Load: {day_metrics.get('training_load', 0):.1f}"""

    def _generate_recommendation(
        self,
        genetic_data: Dict,
        day_metrics: Dict,
        user_context: Dict
    ) -> str:
        """Generate personalized recommendation (placeholder for training target)"""
        recovery = day_metrics.get('recovery_score', 0.5)

        if recovery < 0.4:
            base_rec = "Focus on recovery today with light movement or rest."
        elif recovery > 0.7:
            base_rec = "Excellent recovery! Ready for challenging workout."
        else:
            base_rec = "Moderate intensity training recommended."

        # Add genetic context
        if genetic_data.get('polygenic_scores', {}).get('endurance', 0) > 0.7:
            base_rec += " Your genetic profile favors endurance activities."

        return base_rec

    def save_dataset(self, formatted_data: List[Dict], output_path: Path):
        """Save dataset in JSONL format for Axolotl"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            for sample in formatted_data:
                f.write(json.dumps(sample) + '\n')

        logger.info(f"Saved {len(formatted_data)} samples to {output_path}")


class AxolotlTrainer:
    """Serverless Axolotl trainer for RunPod"""

    def __init__(self, config: AxolotlConfig):
        self.config = config
        self.hf_api = HfApi()

    def create_axolotl_config(self, dataset_path: str) -> Dict:
        """Generate complete Axolotl configuration"""
        config_dict = {
            # Model
            "base_model": self.config.base_model,
            "model_type": self.config.model_type,
            "tokenizer_type": self.config.tokenizer_type,
            "load_in_8bit": self.config.load_in_8bit,
            "load_in_4bit": self.config.load_in_4bit,

            # LoRA/QLoRA
            "adapter": self.config.adapter,
            "lora_r": self.config.lora_r,
            "lora_alpha": self.config.lora_alpha,
            "lora_dropout": self.config.lora_dropout,
            "lora_target_modules": self.config.lora_target_modules,
            "lora_target_linear": self.config.lora_target_linear,

            # Dataset
            "datasets": [{
                "path": dataset_path,
                "type": "sharegpt" if "conversations" in json.loads(open(dataset_path).readline()) else "alpaca"
            }],

            # Training
            "sequence_len": self.config.sequence_len,
            "sample_packing": self.config.sample_packing,
            "pad_to_sequence_len": self.config.pad_to_sequence_len,

            "micro_batch_size": self.config.micro_batch_size,
            "gradient_accumulation_steps": self.config.gradient_accumulation_steps,
            "num_epochs": self.config.num_epochs,
            "optimizer": self.config.optimizer,
            "lr_scheduler": self.config.lr_scheduler,
            "learning_rate": self.config.learning_rate,

            "gradient_checkpointing": self.config.gradient_checkpointing,
            "flash_attention": self.config.flash_attention,

            "warmup_steps": self.config.warmup_steps,
            "eval_steps": self.config.eval_steps,
            "save_steps": self.config.save_steps,
            "logging_steps": self.config.logging_steps,

            # Output
            "output_dir": self.config.output_dir,

            # Weights & Biases
            "wandb_project": self.config.wandb_project,
            "wandb_entity": self.config.wandb_entity,
            "wandb_watch": self.config.wandb_watch,
            "wandb_run_id": self.config.wandb_run_id,

            # Special tokens
            "special_tokens": self.config.special_tokens,

            # DPO (if enabled)
            **({"rl": self.config.rl, "dpo_beta": self.config.dpo_beta} if self.config.rl else {})
        }

        return config_dict

    def save_config(self, config_dict: Dict, output_path: Path):
        """Save Axolotl configuration to YAML"""
        with open(output_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False)

        logger.info(f"Saved Axolotl config to {output_path}")


class RunPodAxolotlHandler:
    """RunPod serverless handler for Axolotl training"""

    def __init__(self):
        self.training_jobs = {}

    def create_handler(self) -> callable:
        """Create RunPod serverless handler function"""

        def handler(event):
            """
            RunPod serverless handler for Axolotl fine-tuning

            Expected event structure:
            {
                "input": {
                    "user_id": "user_001",
                    "dataset_url": "s3://bucket/path/to/dataset.jsonl",
                    "config": {...},  # AxolotlConfig as dict
                    "action": "train" | "inference" | "export"
                }
            }
            """
            try:
                input_data = event.get("input", {})
                action = input_data.get("action", "train")
                user_id = input_data.get("user_id")

                if not user_id:
                    return {"error": "user_id is required"}

                if action == "train":
                    return self._handle_training(input_data)
                elif action == "inference":
                    return self._handle_inference(input_data)
                elif action == "export":
                    return self._handle_export(input_data)
                else:
                    return {"error": f"Unknown action: {action}"}

            except Exception as e:
                logger.error(f"Handler error: {e}")
                return {"error": str(e)}

        return handler

    def _handle_training(self, input_data: Dict) -> Dict:
        """Handle training request"""
        import subprocess
        import tempfile

        user_id = input_data["user_id"]
        dataset_url = input_data.get("dataset_url")
        config_dict = input_data.get("config", {})

        # Create config
        config = AxolotlConfig(**config_dict)
        trainer = AxolotlTrainer(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Download dataset
            dataset_path = tmpdir / "dataset.jsonl"
            self._download_file(dataset_url, dataset_path)

            # Create Axolotl config
            axolotl_config = trainer.create_axolotl_config(str(dataset_path))
            config_path = tmpdir / "config.yml"
            trainer.save_config(axolotl_config, config_path)

            # Run Axolotl training
            output_dir = tmpdir / "output"
            output_dir.mkdir()

            cmd = [
                "accelerate", "launch",
                "-m", "axolotl.cli.train",
                str(config_path)
            ]

            logger.info(f"Running Axolotl: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "OUTPUT_DIR": str(output_dir)}
            )

            if result.returncode != 0:
                logger.error(f"Training failed: {result.stderr}")
                return {
                    "status": "failed",
                    "error": result.stderr[-1000:]  # Last 1000 chars
                }

            # Upload model to HuggingFace Hub or S3
            model_url = self._upload_model(output_dir, user_id, config)

            return {
                "status": "completed",
                "user_id": user_id,
                "model_url": model_url,
                "metrics": self._extract_metrics(output_dir),
                "timestamp": datetime.now().isoformat()
            }

    def _handle_inference(self, input_data: Dict) -> Dict:
        """Handle inference request"""
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        user_id = input_data["user_id"]
        model_path = input_data.get("model_path")
        prompt = input_data.get("prompt")

        # Load model with adapters
        base_model = AutoModelForCausalLM.from_pretrained(
            input_data.get("base_model", "meta-llama/Llama-3.2-1B"),
            torch_dtype=torch.float16,
            device_map="auto"
        )

        model = PeftModel.from_pretrained(base_model, model_path)
        tokenizer = AutoTokenizer.from_pretrained(model_path)

        # Run inference
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.7,
                do_sample=True
            )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        return {
            "status": "completed",
            "user_id": user_id,
            "response": response,
            "tokens_generated": len(outputs[0]) - len(inputs["input_ids"][0])
        }

    def _handle_export(self, input_data: Dict) -> Dict:
        """Handle model export request"""
        user_id = input_data["user_id"]
        model_path = input_data.get("model_path")
        export_format = input_data.get("format", "onnx")

        # Export model
        if export_format == "onnx":
            export_path = self._export_to_onnx(model_path)
        elif export_format == "merged":
            export_path = self._merge_and_export(model_path)
        else:
            return {"error": f"Unsupported format: {export_format}"}

        # Upload exported model
        upload_url = self._upload_file(export_path, f"{user_id}/exports/")

        return {
            "status": "completed",
            "user_id": user_id,
            "export_url": upload_url,
            "format": export_format
        }

    def _download_file(self, url: str, dest: Path):
        """Download file from URL"""
        import requests

        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def _upload_model(self, model_dir: Path, user_id: str, config: AxolotlConfig) -> str:
        """Upload trained model to storage"""
        if config.push_to_hub and config.hub_model_id:
            # Upload to HuggingFace Hub
            repo_id = f"{config.hub_model_id}-{user_id}"
            create_repo(repo_id, exist_ok=True, private=True)

            upload_folder(
                folder_path=str(model_dir),
                repo_id=repo_id,
                commit_message=f"Upload model for user {user_id}"
            )

            return f"https://huggingface.co/{repo_id}"
        else:
            # Upload to S3 or other storage
            return self._upload_to_s3(model_dir, f"models/{user_id}/")

    def _upload_to_s3(self, source_dir: Path, s3_prefix: str) -> str:
        """Upload directory to S3"""
        import boto3

        s3 = boto3.client('s3')
        bucket = os.getenv("S3_BUCKET", "slm-vault-models")

        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                key = f"{s3_prefix}{file_path.relative_to(source_dir)}"
                s3.upload_file(str(file_path), bucket, key)

        return f"s3://{bucket}/{s3_prefix}"

    def _extract_metrics(self, output_dir: Path) -> Dict:
        """Extract training metrics from Axolotl output"""
        metrics = {}

        # Read trainer_state.json if exists
        trainer_state_path = output_dir / "trainer_state.json"
        if trainer_state_path.exists():
            with open(trainer_state_path) as f:
                state = json.load(f)
                metrics["final_loss"] = state.get("log_history", [{}])[-1].get("loss")
                metrics["total_steps"] = state.get("global_step")

        # Read wandb metrics if available
        wandb_dir = output_dir / "wandb"
        if wandb_dir.exists():
            # Parse wandb run data
            pass

        return metrics

    def _export_to_onnx(self, model_path: Path) -> Path:
        """Export model to ONNX format"""
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
        import torch

        # Load model
        base_model = AutoModelForCausalLM.from_pretrained(
            "meta-llama/Llama-3.2-1B",
            torch_dtype=torch.float16
        )
        model = PeftModel.from_pretrained(base_model, model_path)

        # Merge LoRA weights
        merged_model = model.merge_and_unload()

        # Export to ONNX
        export_path = model_path / "model.onnx"
        dummy_input = torch.randint(0, 1000, (1, 128))

        torch.onnx.export(
            merged_model,
            dummy_input,
            export_path,
            input_names=["input_ids"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence"},
                "logits": {0: "batch_size", 1: "sequence"}
            }
        )

        return export_path

    def _merge_and_export(self, model_path: Path) -> Path:
        """Merge LoRA weights and export full model"""
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        # Load and merge
        base_model = AutoModelForCausalLM.from_pretrained(
            "meta-llama/Llama-3.2-1B",
            torch_dtype=torch.float16
        )
        model = PeftModel.from_pretrained(base_model, model_path)
        merged_model = model.merge_and_unload()

        # Save merged model
        export_path = model_path / "merged"
        merged_model.save_pretrained(export_path)

        # Save tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        tokenizer.save_pretrained(export_path)

        return export_path


def create_runpod_endpoint():
    """Create RunPod serverless endpoint for Axolotl"""

    handler_instance = RunPodAxolotlHandler()

    # RunPod endpoint configuration
    endpoint_config = {
        "name": "axolotl-slm-trainer",
        "image": "winglian/axolotl-cloud:main-latest",
        "gpu_type": "NVIDIA A40",
        "gpu_count": 1,
        "workers_min": 0,
        "workers_max": 10,
        "idle_timeout": 60,
        "max_runtime": 3600,  # 1 hour max per job
        "env_vars": {
            "HF_TOKEN": os.getenv("HF_TOKEN"),
            "WANDB_API_KEY": os.getenv("WANDB_API_KEY"),
            "S3_BUCKET": os.getenv("S3_BUCKET", "slm-vault-models")
        },
        "handler": handler_instance.create_handler()
    }

    # Deploy to RunPod
    runpod.api_key = os.getenv("RUNPOD_API_KEY")
    endpoint = runpod.create_serverless_endpoint(**endpoint_config)

    logger.info(f"Created RunPod endpoint: {endpoint['id']}")
    return endpoint


if __name__ == "__main__":
    # Example usage
    import asyncio
    from data_pipeline import DataPipelineManager

    user_id = "test_user_001"

    # Step 1: Prepare data with Axolotl formatter
    data_manager = DataPipelineManager(user_id)

    # Mock data for demonstration
    genetic_data = {
        "polygenic_scores": {
            "endurance": 0.75,
            "strength": 0.60,
            "recovery": 0.68
        },
        "actionable_variants": [
            {"gene": "ACTN3", "impact": "power_performance"},
            {"gene": "MCT1", "impact": "lactate_clearance"}
        ]
    }

    fitness_history = [
        {
            "date": "2024-01-01",
            "steps": 8500,
            "heart_rate_avg": 62,
            "hrv": 45,
            "sleep_hours": 7.5,
            "recovery_score": 0.72,
            "training_load": 4.2
        }
    ]

    user_context = {
        "age": 35,
        "sex": "male",
        "goals": ["endurance", "longevity"],
        "diet": "mediterranean",
        "primary_goal": "improve cardiovascular fitness"
    }

    # Format for Axolotl
    formatter = AxolotlDatasetFormatter(user_id)
    formatted_data = formatter.format_for_axolotl(
        genetic_data, fitness_history, user_context
    )

    # Save dataset
    dataset_path = Path(f"./data/{user_id}/axolotl_dataset.jsonl")
    formatter.save_dataset(formatted_data, dataset_path)

    # Step 2: Configure Axolotl training
    config = AxolotlConfig(
        base_model="meta-llama/Llama-3.2-1B",
        load_in_4bit=True,  # QLoRA
        num_epochs=3,
        micro_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        output_dir=f"./outputs/{user_id}",
        wandb_run_id=f"slm-{user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    # Step 3: Create and save Axolotl config
    trainer = AxolotlTrainer(config)
    axolotl_config = trainer.create_axolotl_config(str(dataset_path))
    config_path = Path(f"./configs/{user_id}/axolotl_config.yml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    trainer.save_config(axolotl_config, config_path)

    print(f"Created Axolotl configuration at: {config_path}")
    print(f"Dataset ready at: {dataset_path}")
    print("\nTo train locally with Axolotl:")
    print(f"  accelerate launch -m axolotl.cli.train {config_path}")

    # Step 4: Deploy to RunPod (if API key is set)
    if os.getenv("RUNPOD_API_KEY"):
        endpoint = create_runpod_endpoint()
        print(f"\nDeployed to RunPod: {endpoint['id']}")
        print(f"Endpoint URL: {endpoint['endpoint_url']}")