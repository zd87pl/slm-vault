# RunPod Axolotl v0.12.2 Integration Guide

## Overview

This guide documents the integration with RunPod's production Axolotl v0.12.2 deployment for serverless fine-tuning of personal health SLMs.

## Key Features

### RunPod Axolotl v0.12.2 Capabilities

- **Serverless Training**: Scale-to-zero with automatic GPU provisioning
- **Efficient Fine-tuning**: QLoRA, LoRA, and DPO support
- **Optimizations**: Flash Attention, gradient checkpointing, sample packing
- **Multi-format**: ShareGPT, Alpaca, and custom conversation formats
- **Cost-effective**: Pay only for actual training time

## Quick Start

### Prerequisites

```bash
# Required environment variables
export RUNPOD_API_KEY="your-runpod-api-key"
export HF_TOKEN="your-huggingface-token"
export WANDB_API_KEY="your-wandb-key"  # Optional but recommended
```

### Deploy Personal Health SLM

```bash
# Using mock data for testing
python scripts/deploy_health_slm.py \
  --user-id user_001 \
  --use-mock-data \
  --base-model "NousResearch/Llama-3.2-1B" \
  --wait

# Using real user data
python scripts/deploy_health_slm.py \
  --user-id user_001 \
  --base-model "NousResearch/Llama-3.2-1B" \
  --deploy
```

### Check Training Status

```bash
# Single check
python scripts/check_training_status.py --job-id <job_id>

# Watch continuously
python scripts/check_training_status.py --job-id <job_id> --watch --interval 30
```

## API Usage

### Python SDK

```python
from src.runpod_axolotl_v12 import PersonalSLMOrchestrator

# Initialize orchestrator
orchestrator = PersonalSLMOrchestrator(user_id="user_001")

# Train model with health data
result = orchestrator.train_personal_slm(
    genetic_data=genetic_data,
    fitness_history=fitness_history,
    user_context=user_context,
    base_model="NousResearch/Llama-3.2-1B"
)

# Check status
status = orchestrator.get_training_status(result["job_id"])

# Deploy for inference (after training completes)
deployment = orchestrator.deploy_trained_model(result["job_id"])
```

### Direct RunPod API

```python
from src.runpod_axolotl_v12 import RunPodAxolotlClient

client = RunPodAxolotlClient(api_key)

# Create configuration
config = client.create_health_slm_config(
    user_id="user_001",
    dataset_path="user_001/health-data-20240115",
    base_model="NousResearch/Llama-3.2-1B",
    use_qlora=True
)

# Submit training
job_id = client.train_model(config)

# Wait for completion
result = client.wait_for_completion(job_id, timeout=7200)
```

## Configuration Options

### Essential Parameters

```json
{
  "input": {
    "user_id": "user_001",
    "model_id": "health-slm-user_001",
    "run_id": "run-20240115-120000",
    "credentials": {
      "wandb_api_key": "",
      "hf_token": ""
    },
    "args": {
      "base_model": "NousResearch/Llama-3.2-1B",
      "load_in_4bit": true,  // QLoRA
      "adapter": "qlora",
      "lora_r": 16,
      "lora_alpha": 32,
      "lora_dropout": 0.05,
      "flash_attention": true,
      "gradient_checkpointing": true,
      "num_epochs": 3,
      "learning_rate": 0.0002
    }
  }
}
```

### Health-Specific Special Tokens

```json
{
  "special_tokens": {
    "pad_token": "<|end_of_text|>",
    "additional_special_tokens": [
      "<genetic_context>", "</genetic_context>",
      "<fitness_metrics>", "</fitness_metrics>",
      "<health_goal>", "</health_goal>",
      "<recovery_status>", "</recovery_status>"
    ]
  }
}
```

## Dataset Formats

### Alpaca Format (Recommended)

```json
{
  "instruction": "Based on my genetic profile and current metrics, provide a personalized morning health assessment.",
  "input": "<genetic_context>Endurance: 0.75, Recovery: 0.68</genetic_context>\n<fitness_metrics>HRV: 45ms, Sleep: 7.5h</fitness_metrics>",
  "output": "Excellent recovery! Your body is ready for challenging activities today."
}
```

### ShareGPT Format (Multi-turn)

```json
{
  "conversations": [
    {
      "from": "system",
      "value": "You are a personalized health AI with access to genetic and fitness data."
    },
    {
      "from": "human",
      "value": "How is my recovery today?"
    },
    {
      "from": "gpt",
      "value": "Based on your HRV of 45ms and 7.5 hours of quality sleep, your recovery is excellent."
    }
  ]
}
```

## Performance & Cost

### Resource Usage

| Configuration | GPU Memory | Training Time | Cost Estimate |
|---------------|------------|---------------|---------------|
| QLoRA (4-bit) | ~4GB | 30-45 min | $2-3 |
| LoRA (16-bit) | ~12GB | 45-60 min | $4-6 |
| Full Fine-tune | ~24GB | 2-3 hours | $15-20 |

### Optimization Tips

1. **Use QLoRA** for most cases (75% memory savings)
2. **Enable Flash Attention** for 2x faster training
3. **Use gradient checkpointing** for 40% memory reduction
4. **Enable sample packing** for 15% efficiency gain
5. **Set appropriate batch sizes** based on GPU memory

## Monitoring

### Weights & Biases Integration

```python
config = {
  "wandb_project": "personal-health-slm",
  "wandb_entity": "your-team",
  "wandb_name": "run-user_001",
  "wandb_watch": "gradients"
}
```

View training progress at: https://wandb.ai/your-team/personal-health-slm

### Training Metrics

- Loss curves
- Learning rate schedules
- GPU utilization
- Memory usage
- Gradient norms

## Deployment Options

### After Training Completes

1. **HuggingFace Hub**: Models automatically pushed if configured
2. **RunPod Inference**: Deploy as serverless endpoint
3. **Local Export**: Download and run locally
4. **Edge Deployment**: Convert to ONNX/CoreML

## Troubleshooting

### Common Issues

1. **Flash Attention Error**
   - Solution: Delete worker and restart

2. **Out of Memory**
   - Solution: Reduce batch size or switch to QLoRA

3. **Training Timeout**
   - Solution: Increase max_runtime in configuration

4. **Dataset Not Found**
   - Solution: Ensure HF token has access to private repos

### Debug Commands

```bash
# Check RunPod endpoint status
curl -H "Authorization: Bearer $RUNPOD_API_KEY" \
  https://api.runpod.ai/v2/endpoints

# View training logs
python scripts/get_training_logs.py --job-id <job_id>

# Download trained model
python scripts/download_model.py --job-id <job_id> --output-dir ./models
```

## Advanced Usage

### Custom Training Pipeline

```python
from src.runpod_axolotl_v12 import PersonalHealthDataFormatter

# Custom data formatting
formatter = PersonalHealthDataFormatter(user_id)

# Add specialized health metrics
dataset = formatter.create_health_dataset(
    genetic_data={
        "polygenic_scores": {...},
        "pharmacogenomics": {...},
        "methylation_age": ...
    },
    fitness_history=[...],
    user_context={...}
)

# Upload to HuggingFace
dataset_repo = formatter.upload_dataset_to_hf(dataset, "custom-health-v1")
```

### Multi-Stage Training

```python
# Stage 1: Base health knowledge
stage1_config = {
    "num_epochs": 2,
    "learning_rate": 0.0003,
    "datasets": [{"path": "medical-qa", "type": "alpaca"}]
}

# Stage 2: Personalization
stage2_config = {
    "num_epochs": 3,
    "learning_rate": 0.0001,
    "datasets": [{"path": user_dataset, "type": "alpaca"}],
    "lora_model_dir": stage1_output  # Continue from stage 1
}
```

## Security & Privacy

- All data encrypted in transit (TLS 1.3)
- User-specific model isolation
- Private HuggingFace repos by default
- Secure credential management
- Audit logging for compliance

## Support

- RunPod Documentation: https://docs.runpod.io
- Axolotl Documentation: https://github.com/OpenAccess-AI-Collective/axolotl
- Issues: Create an issue in this repository
- RunPod Support: support@runpod.io