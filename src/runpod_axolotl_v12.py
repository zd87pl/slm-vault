"""
RunPod Axolotl v0.12.2 Integration for Personal SLM Fine-tuning
Aligned with RunPod's production Axolotl deployment
"""

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import runpod
import boto3
import requests
from huggingface_hub import HfApi, create_repo
import logging

logger = logging.getLogger(__name__)


@dataclass
class RunPodAxolotlRequest:
    """Request structure for RunPod Axolotl v0.12.2"""
    user_id: str
    model_id: str
    run_id: str
    credentials: Dict[str, str]
    args: Dict[str, Any]

    def to_runpod_format(self) -> Dict:
        """Convert to RunPod API format"""
        return {
            "input": {
                "user_id": self.user_id,
                "model_id": self.model_id,
                "run_id": self.run_id,
                "credentials": self.credentials,
                "args": self.args
            }
        }


class PersonalHealthDataFormatter:
    """Format personal health data for Axolotl training"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.hf_api = HfApi()

    def create_health_dataset(
        self,
        genetic_data: Dict,
        fitness_history: List[Dict],
        user_context: Dict
    ) -> List[Dict]:
        """Create Alpaca-format dataset for health recommendations"""
        dataset = []

        # Generate training samples for each day
        for day_metrics in fitness_history:
            # Morning check-in
            dataset.append(self._create_morning_sample(
                genetic_data, day_metrics, user_context
            ))

            # Recovery assessment
            dataset.append(self._create_recovery_sample(
                genetic_data, day_metrics, user_context
            ))

            # Training recommendation
            dataset.append(self._create_training_sample(
                genetic_data, day_metrics, user_context
            ))

            # Nutrition guidance
            dataset.append(self._create_nutrition_sample(
                genetic_data, day_metrics, user_context
            ))

        return dataset

    def _create_morning_sample(self, genetic_data: Dict, metrics: Dict, context: Dict) -> Dict:
        """Create morning health check sample"""
        genetic_summary = self._format_genetic_context(genetic_data)

        instruction = "Based on my genetic profile and current metrics, provide a personalized morning health assessment."

        input_text = f"""<genetic_context>
Endurance capacity: {genetic_data.get('polygenic_scores', {}).get('endurance', 0.5):.2f}
Recovery efficiency: {genetic_data.get('polygenic_scores', {}).get('recovery', 0.5):.2f}
Key variants: {', '.join([v['gene'] for v in genetic_data.get('actionable_variants', [])[:3]])}
</genetic_context>

<fitness_metrics>
Sleep duration: {metrics.get('sleep_hours', 0):.1f} hours
Sleep quality: {metrics.get('sleep_quality', 0):.2f}
HRV: {metrics.get('hrv', 0):.0f} ms
Resting HR: {metrics.get('resting_hr', 0):.0f} bpm
Recovery score: {metrics.get('recovery_score', 0):.2f}
</fitness_metrics>

<health_goal>{context.get('primary_goal', 'optimize health')}</health_goal>"""

        output = self._generate_morning_recommendation(genetic_data, metrics, context)

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output
        }

    def _create_recovery_sample(self, genetic_data: Dict, metrics: Dict, context: Dict) -> Dict:
        """Create recovery assessment sample"""
        instruction = "Analyze my recovery status and provide recommendations."

        input_text = f"""<genetic_context>
Recovery gene score: {genetic_data.get('polygenic_scores', {}).get('recovery', 0.5):.2f}
Inflammation markers: {genetic_data.get('inflammation_risk', 'normal')}
</genetic_context>

<fitness_metrics>
Yesterday's training load: {metrics.get('yesterday_load', 0):.1f}
HRV trend (7-day): {metrics.get('hrv_trend', 'stable')}
Muscle soreness: {metrics.get('soreness_level', 0)}/10
Energy level: {metrics.get('energy_level', 5)}/10
Recovery score: {metrics.get('recovery_score', 0.5):.2f}
</fitness_metrics>"""

        output = self._generate_recovery_recommendation(genetic_data, metrics)

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output
        }

    def _create_training_sample(self, genetic_data: Dict, metrics: Dict, context: Dict) -> Dict:
        """Create training recommendation sample"""
        instruction = "Provide a personalized training recommendation for today."

        input_text = f"""<genetic_context>
Power/endurance profile: {genetic_data.get('fiber_type', 'balanced')}
VO2max potential: {genetic_data.get('vo2max_potential', 'average')}
Injury risk factors: {genetic_data.get('injury_risk', 'low')}
</genetic_context>

<fitness_metrics>
Current fitness level: {metrics.get('fitness_level', 5)}/10
Weekly training hours: {metrics.get('weekly_hours', 0):.1f}
Recovery status: {metrics.get('recovery_score', 0.5):.2f}
Last workout: {metrics.get('last_workout_type', 'rest')}
</fitness_metrics>

<health_goal>{context.get('training_focus', 'general fitness')}</health_goal>"""

        output = self._generate_training_recommendation(genetic_data, metrics, context)

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output
        }

    def _create_nutrition_sample(self, genetic_data: Dict, metrics: Dict, context: Dict) -> Dict:
        """Create nutrition guidance sample"""
        instruction = "Provide personalized nutrition recommendations based on my genetics and activity."

        input_text = f"""<genetic_context>
Caffeine metabolism: {genetic_data.get('caffeine_metabolism', 'normal')}
Lactose tolerance: {genetic_data.get('lactose_tolerance', 'tolerant')}
Nutrient needs: {genetic_data.get('nutrient_needs', 'standard')}
</genetic_context>

<fitness_metrics>
Today's activity: {metrics.get('activity_type', 'moderate')}
Calories burned: {metrics.get('calories_burned', 0):,}
Hydration status: {metrics.get('hydration', 'adequate')}
</fitness_metrics>

<dietary_preferences>{context.get('diet_type', 'balanced')}</dietary_preferences>"""

        output = self._generate_nutrition_recommendation(genetic_data, metrics, context)

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output
        }

    def _format_genetic_context(self, genetic_data: Dict) -> str:
        """Format genetic data into readable context"""
        context_parts = []

        if 'polygenic_scores' in genetic_data:
            scores = genetic_data['polygenic_scores']
            for trait, score in scores.items():
                context_parts.append(f"{trait}: {score:.2f}")

        if 'actionable_variants' in genetic_data:
            variants = genetic_data['actionable_variants'][:5]
            for v in variants:
                context_parts.append(f"{v['gene']}: {v.get('impact', 'unknown')}")

        return ", ".join(context_parts)

    def _generate_morning_recommendation(self, genetic_data: Dict, metrics: Dict, context: Dict) -> str:
        """Generate morning health recommendation"""
        recovery = metrics.get('recovery_score', 0.5)
        sleep = metrics.get('sleep_hours', 7)

        if recovery > 0.7 and sleep >= 7:
            base = "Excellent recovery! Your body is ready for challenging activities today."
        elif recovery < 0.4 or sleep < 6:
            base = "Recovery is suboptimal. Focus on restoration and light movement today."
        else:
            base = "Moderate recovery status. Balance activity with adequate rest periods."

        # Add genetic context
        if genetic_data.get('polygenic_scores', {}).get('endurance', 0) > 0.7:
            base += " Your genetic profile supports longer duration activities."

        return base

    def _generate_recovery_recommendation(self, genetic_data: Dict, metrics: Dict) -> str:
        """Generate recovery recommendation"""
        recovery_score = metrics.get('recovery_score', 0.5)
        hrv_trend = metrics.get('hrv_trend', 'stable')

        if recovery_score < 0.4:
            return "Prioritize recovery: Light yoga, walking, or complete rest. Focus on hydration and quality nutrition."
        elif recovery_score > 0.7:
            return "Recovery is optimal. You can handle higher intensity training if desired."
        else:
            return "Moderate intensity training is appropriate. Listen to your body and adjust as needed."

    def _generate_training_recommendation(self, genetic_data: Dict, metrics: Dict, context: Dict) -> str:
        """Generate training recommendation"""
        recovery = metrics.get('recovery_score', 0.5)
        fitness_level = metrics.get('fitness_level', 5)

        recommendations = []

        if recovery > 0.6:
            if fitness_level > 7:
                recommendations.append("High-intensity interval training or tempo work")
            else:
                recommendations.append("Moderate aerobic exercise with short intensity bursts")
        else:
            recommendations.append("Recovery-focused: Easy aerobic work or mobility")

        # Add genetic-based suggestions
        if genetic_data.get('fiber_type') == 'fast-twitch':
            recommendations.append("Include power/sprint work when recovered")
        elif genetic_data.get('fiber_type') == 'slow-twitch':
            recommendations.append("Emphasize endurance and aerobic base building")

        return ". ".join(recommendations)

    def _generate_nutrition_recommendation(self, genetic_data: Dict, metrics: Dict, context: Dict) -> str:
        """Generate nutrition recommendation"""
        activity = metrics.get('activity_type', 'moderate')
        calories = metrics.get('calories_burned', 2000)

        base = f"Target approximately {int(calories * 1.1)} calories today. "

        if activity == 'intense':
            base += "Prioritize carbohydrates for recovery and protein for muscle repair."
        else:
            base += "Focus on balanced macronutrients with emphasis on whole foods."

        # Add genetic-specific advice
        if genetic_data.get('caffeine_metabolism') == 'slow':
            base += " Limit caffeine intake, especially after noon."

        return base

    def upload_dataset_to_hf(self, dataset: List[Dict], repo_name: str) -> str:
        """Upload dataset to HuggingFace Hub"""
        repo_id = f"{self.user_id}/{repo_name}"

        # Create private repo
        create_repo(repo_id, exist_ok=True, private=True)

        # Save dataset as JSONL
        dataset_path = Path(f"/tmp/{repo_name}.jsonl")
        with open(dataset_path, 'w') as f:
            for sample in dataset:
                f.write(json.dumps(sample) + '\n')

        # Upload to HF
        self.hf_api.upload_file(
            path_or_fileobj=str(dataset_path),
            path_in_repo="train.jsonl",
            repo_id=repo_id
        )

        logger.info(f"Uploaded dataset to {repo_id}")
        return repo_id


class RunPodAxolotlClient:
    """Client for RunPod Axolotl v0.12.2 deployments"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        runpod.api_key = api_key
        self.endpoint_id = None
        self.endpoint_url = None

    def create_health_slm_config(
        self,
        user_id: str,
        dataset_path: str,
        base_model: str = "NousResearch/Llama-3.2-1B",
        use_qlora: bool = True
    ) -> Dict:
        """Create Axolotl configuration for health SLM"""

        # Generate unique IDs
        model_id = f"health-slm-{user_id}"
        run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        config = {
            "user_id": user_id,
            "model_id": model_id,
            "run_id": run_id,
            "credentials": {
                "wandb_api_key": os.getenv("WANDB_API_KEY", ""),
                "hf_token": os.getenv("HF_TOKEN", "")
            },
            "args": {
                # Model configuration
                "base_model": base_model,
                "model_type": "LlamaForCausalLM",
                "tokenizer_type": "AutoTokenizer",

                # Quantization
                "load_in_8bit": False,
                "load_in_4bit": use_qlora,

                # Dataset
                "datasets": [
                    {
                        "path": dataset_path,  # HF Hub path or local
                        "type": "alpaca"
                    }
                ],
                "dataset_prepared_path": f"prepared_{user_id}",
                "val_set_size": 0.1,

                # LoRA/QLoRA configuration
                "adapter": "qlora" if use_qlora else "lora",
                "lora_r": 16,
                "lora_alpha": 32,
                "lora_dropout": 0.05,
                "lora_target_modules": [
                    "gate_proj", "down_proj", "up_proj",
                    "q_proj", "v_proj", "k_proj", "o_proj"
                ],

                # Training parameters
                "sequence_len": 2048,
                "sample_packing": True,
                "eval_sample_packing": True,
                "pad_to_sequence_len": True,

                "gradient_accumulation_steps": 4,
                "micro_batch_size": 2,
                "num_epochs": 3,

                # Optimizer
                "optimizer": "adamw_8bit" if use_qlora else "adamw_torch",
                "lr_scheduler": "cosine",
                "learning_rate": 0.0002,
                "warmup_steps": 100,
                "weight_decay": 0.01,

                # Training settings
                "train_on_inputs": False,
                "group_by_length": False,
                "gradient_checkpointing": True,
                "early_stopping_patience": 3,

                # Precision and optimization
                "bf16": "auto",
                "tf32": False,
                "flash_attention": True,

                # Logging and checkpoints
                "logging_steps": 10,
                "eval_steps": 50,
                "save_strategy": "steps",
                "save_steps": 100,
                "save_total_limit": 3,

                # Output
                "output_dir": f"./outputs/{model_id}",
                "hub_model_id": f"{user_id}/{model_id}",

                # Monitoring
                "wandb_project": "personal-health-slm",
                "wandb_entity": user_id,
                "wandb_name": run_id,
                "wandb_run_id": run_id,

                # Special tokens for health data
                "special_tokens": {
                    "pad_token": "<|end_of_text|>",
                    "additional_special_tokens": [
                        "<genetic_context>", "</genetic_context>",
                        "<fitness_metrics>", "</fitness_metrics>",
                        "<health_goal>", "</health_goal>",
                        "<recovery_status>", "</recovery_status>"
                    ]
                },

                # Loss monitoring
                "loss_watchdog_threshold": 5,
                "loss_watchdog_patience": 3
            }
        }

        return config

    def deploy_endpoint(self) -> Dict:
        """Deploy RunPod Axolotl v0.12.2 serverless endpoint"""

        endpoint_config = {
            "name": "axolotl-health-slm",
            "image_name": "runpod/axolotl:v0.12.2",  # Official RunPod Axolotl image
            "gpu_type_id": "NVIDIA RTX A4000",  # or "NVIDIA RTX 3090"
            "min_workers": 0,
            "max_workers": 3,
            "idle_timeout": 300,  # 5 minutes
            "max_run_time": 7200,  # 2 hours max per training
            "capacity_per_deployment": 1,
            "env": {
                "HF_TOKEN": os.getenv("HF_TOKEN", ""),
                "WANDB_API_KEY": os.getenv("WANDB_API_KEY", "")
            }
        }

        # Create serverless endpoint
        endpoint = runpod.create_endpoint(**endpoint_config)

        self.endpoint_id = endpoint["id"]
        self.endpoint_url = endpoint.get("endpoint_url")

        logger.info(f"Created RunPod endpoint: {self.endpoint_id}")
        return endpoint

    def train_model(self, config: Dict) -> str:
        """Submit training job to RunPod"""

        if not self.endpoint_id:
            self.deploy_endpoint()

        # Submit job
        request = RunPodAxolotlRequest(**config)

        response = runpod.run(
            endpoint_id=self.endpoint_id,
            input=request.to_runpod_format()
        )

        job_id = response["id"]
        logger.info(f"Submitted training job: {job_id}")

        return job_id

    def get_job_status(self, job_id: str) -> Dict:
        """Check training job status"""

        status = runpod.get_status(job_id)

        return {
            "job_id": job_id,
            "status": status.get("status"),
            "created_at": status.get("created_at"),
            "started_at": status.get("started_at"),
            "completed_at": status.get("completed_at"),
            "output": status.get("output"),
            "error": status.get("error")
        }

    def wait_for_completion(self, job_id: str, timeout: int = 7200) -> Dict:
        """Wait for training to complete"""

        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_job_status(job_id)

            if status["status"] == "COMPLETED":
                logger.info(f"Job {job_id} completed successfully")
                return status
            elif status["status"] == "FAILED":
                logger.error(f"Job {job_id} failed: {status.get('error')}")
                raise Exception(f"Training failed: {status.get('error')}")

            # Wait before checking again
            time.sleep(30)

        raise TimeoutError(f"Job {job_id} timed out after {timeout} seconds")

    def download_model(self, job_id: str, output_dir: Path) -> Path:
        """Download trained model from RunPod"""

        status = self.get_job_status(job_id)

        if status["status"] != "COMPLETED":
            raise ValueError(f"Job {job_id} not completed")

        # Get model URL from output
        model_url = status["output"].get("model_url")

        if not model_url:
            raise ValueError("No model URL in job output")

        # Download model
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = output_dir / f"model_{job_id}"

        response = requests.get(model_url, stream=True)
        response.raise_for_status()

        with open(model_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded model to {model_path}")
        return model_path


class PersonalSLMOrchestrator:
    """Orchestrate the complete personal SLM training pipeline"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.formatter = PersonalHealthDataFormatter(user_id)
        self.client = RunPodAxolotlClient(os.getenv("RUNPOD_API_KEY"))

    def train_personal_slm(
        self,
        genetic_data: Dict,
        fitness_history: List[Dict],
        user_context: Dict,
        base_model: str = "NousResearch/Llama-3.2-1B"
    ) -> Dict:
        """Complete pipeline for training personal SLM"""

        logger.info(f"Starting personal SLM training for user {self.user_id}")

        # Step 1: Create and format dataset
        dataset = self.formatter.create_health_dataset(
            genetic_data, fitness_history, user_context
        )

        # Step 2: Upload dataset to HuggingFace Hub
        dataset_repo = self.formatter.upload_dataset_to_hf(
            dataset,
            f"health-data-{datetime.now().strftime('%Y%m%d')}"
        )

        # Step 3: Create Axolotl configuration
        config = self.client.create_health_slm_config(
            user_id=self.user_id,
            dataset_path=dataset_repo,
            base_model=base_model,
            use_qlora=True
        )

        # Step 4: Submit training job
        job_id = self.client.train_model(config)

        # Step 5: Monitor training
        logger.info(f"Training job {job_id} submitted, monitoring progress...")

        # Optional: Wait for completion
        # result = self.client.wait_for_completion(job_id)

        return {
            "user_id": self.user_id,
            "job_id": job_id,
            "dataset_repo": dataset_repo,
            "model_id": config["model_id"],
            "status": "training",
            "submitted_at": datetime.now().isoformat()
        }

    def get_training_status(self, job_id: str) -> Dict:
        """Check status of training job"""
        return self.client.get_job_status(job_id)

    def deploy_trained_model(self, job_id: str) -> Dict:
        """Deploy trained model for inference"""

        # Download model
        model_path = self.client.download_model(
            job_id,
            Path(f"/models/{self.user_id}")
        )

        # Deploy for inference (using our existing deployment code)
        from deployment import RunPodDeployer, DeploymentConfig

        deployer = RunPodDeployer(os.getenv("RUNPOD_API_KEY"))
        config = DeploymentConfig(gpu_type="NVIDIA GeForce RTX 3060")

        deployment = deployer.deploy_user_slm(
            user_id=self.user_id,
            container_image=f"health-slm-{self.user_id}:latest",
            config=config
        )

        return deployment


if __name__ == "__main__":
    # Example usage with RunPod Axolotl v0.12.2

    user_id = "user_001"

    # Mock health data
    genetic_data = {
        "polygenic_scores": {
            "endurance": 0.75,
            "strength": 0.60,
            "recovery": 0.68,
            "vo2max": 0.72
        },
        "actionable_variants": [
            {"gene": "ACTN3", "rsid": "rs1815739", "impact": "power_performance"},
            {"gene": "MCT1", "rsid": "rs1049434", "impact": "lactate_clearance"},
            {"gene": "ACE", "rsid": "rs1799752", "impact": "endurance_capacity"}
        ],
        "fiber_type": "balanced",
        "caffeine_metabolism": "fast",
        "injury_risk": "low"
    }

    fitness_history = [
        {
            "date": "2024-01-15",
            "sleep_hours": 7.5,
            "sleep_quality": 0.85,
            "hrv": 45,
            "resting_hr": 58,
            "recovery_score": 0.72,
            "yesterday_load": 6.5,
            "hrv_trend": "improving",
            "soreness_level": 3,
            "energy_level": 7,
            "fitness_level": 6,
            "weekly_hours": 8.5,
            "last_workout_type": "endurance",
            "activity_type": "moderate",
            "calories_burned": 2450,
            "hydration": "adequate"
        }
        # Add more days...
    ]

    user_context = {
        "age": 35,
        "sex": "male",
        "height_cm": 180,
        "weight_kg": 75,
        "primary_goal": "improve cardiovascular endurance",
        "training_focus": "marathon preparation",
        "diet_type": "mediterranean",
        "injuries": [],
        "experience_level": "intermediate"
    }

    # Initialize orchestrator
    orchestrator = PersonalSLMOrchestrator(user_id)

    # Start training
    result = orchestrator.train_personal_slm(
        genetic_data=genetic_data,
        fitness_history=fitness_history,
        user_context=user_context,
        base_model="NousResearch/Llama-3.2-1B"
    )

    print(f"Training initiated: {json.dumps(result, indent=2)}")

    # Check status
    if result["job_id"]:
        status = orchestrator.get_training_status(result["job_id"])
        print(f"Status: {json.dumps(status, indent=2)}")