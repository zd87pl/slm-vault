# RunPod Serverless Deployment Guide

## Quick Deploy (Using Script)

```bash
# Set your Docker Hub username
export DOCKER_USERNAME=yourusername
export RUNPOD_API_KEY=your-api-key

# Build and push
./scripts/deploy_runpod.sh
```

## Manual Deployment via RunPod API

### Step 1: Build and Push Docker Image

```bash
# Build for linux/amd64 (RunPod uses x86_64)
docker build --platform linux/amd64 \
  -t yourusername/dora-wdva:latest \
  -f docker/Dockerfile .

# Push to Docker Hub (or your registry)
docker push yourusername/dora-wdva:latest
```

### Step 2: Create Endpoint via API

```bash
curl -X POST "https://api.runpod.io/graphql?api_key=${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { saveEndpoint(input: { name: \"dora-wdva-inference\", templateId: \"your-template-id\", dockerImage: \"yourusername/dora-wdva:latest\", gpuIds: \"AMPERE_16\", workersMin: 0, workersMax: 3, idleTimeout: 5 }) { id name } }"
  }'
```

### Step 3: Create Template First (Recommended)

```bash
# Create template
curl -X POST "https://api.runpod.io/graphql?api_key=${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { saveTemplate(input: { name: \"DoRA WDVA Template\", dockerImage: \"yourusername/dora-wdva:latest\", isServerless: true, env: [{key: \"TOKENIZERS_PARALLELISM\", value: \"false\"}] }) { id name } }"
  }'
```

## Using the Deployed Endpoint

### Inference Request

```bash
curl -X POST "https://api.runpod.ai/v2/${ENDPOINT_ID}/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -d '{
    "input": {
      "task": "inference",
      "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "encrypted_adapter_path": "s3://your-bucket/adapter.enc",
      "encryption_key": "your-hex-key",
      "prompt": "Explain quantum computing:",
      "max_tokens": 256,
      "temperature": 0.7
    }
  }'
```

### Training Request

```bash
curl -X POST "https://api.runpod.ai/v2/${ENDPOINT_ID}/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -d '{
    "input": {
      "task": "training",
      "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "dataset_name": "yahma/alpaca-cleaned",
      "max_samples": 1000,
      "epochs": 3,
      "use_4bit": true
    }
  }'
```

### Encryption Request

```bash
curl -X POST "https://api.runpod.ai/v2/${ENDPOINT_ID}/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -d '{
    "input": {
      "task": "encrypt",
      "adapter_path": "./outputs/dora-adapter",
      "encryption_key": "your-hex-key",
      "enable_compression": true
    }
  }'
```

## Configuration Options

### GPU Types
- `AMPERE_16`: RTX 3090/A4000 (16GB VRAM)
- `AMPERE_24`: RTX 3090 Ti/A5000 (24GB VRAM)
- `AMPERE_48`: RTX A6000 (48GB VRAM)
- `ADA_24`: RTX 4090 (24GB VRAM)

### Scaling Settings
```json
{
  "workersMin": 0,          // Scale to zero when idle
  "workersMax": 3,          // Max concurrent workers
  "idleTimeout": 5,         // Minutes before scale to zero
  "executionTimeout": 600   // Max execution time (seconds)
}
```

## Python SDK Example

```python
import runpod

# Initialize client
runpod.api_key = "your-api-key"

# Run inference
endpoint = runpod.Endpoint("ENDPOINT_ID")

result = endpoint.run({
    "task": "inference",
    "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "encrypted_adapter_path": "s3://your-bucket/adapter.enc",
    "encryption_key": "your-hex-key",
    "prompt": "Hello world",
    "max_tokens": 100
})

print(result)
```

## Cost Estimation

| Operation | GPU | Duration | Cost (approx) |
|-----------|-----|----------|---------------|
| Training (1K samples) | RTX 4090 | 2-3 min | $0.08-0.12 |
| Encryption | CPU | 10-20 sec | $0.01 |
| Inference (cached) | RTX 4090 | 1-2 sec | $0.01-0.02 |
| Inference (cold) | RTX 4090 | 5-10 sec | $0.03-0.06 |

## Environment Variables

Set these in your RunPod template:

```bash
TOKENIZERS_PARALLELISM=false
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
TRANSFORMERS_CACHE=/workspace/.cache/huggingface
HF_HOME=/workspace/.cache/huggingface
HF_TOKEN=your-huggingface-token  # Optional, for gated models
```

## Troubleshooting

### Image Won't Pull
- Ensure image is public or RunPod has registry credentials
- Verify image tag exists: `docker pull yourusername/dora-wdva:latest`

### Out of Memory
- Reduce `max_samples` for training
- Use `use_4bit: true` for QDoRA
- Increase GPU type (e.g., AMPERE_24 instead of AMPERE_16)

### Handler Not Found
- Verify Dockerfile CMD: `CMD ["python3", "-u", "src/rp_handler.py"]`
- Check handler implements: `runpod.serverless.start({"handler": handler})`

### Import Errors
- Ensure all dependencies in `docker/requirements.txt`
- Verify COPY paths in Dockerfile match build context

## Next Steps

1. **Build and test locally** (optional):
   ```bash
   docker run -it --gpus all yourusername/dora-wdva:latest
   ```

2. **Push to registry**:
   ```bash
   docker push yourusername/dora-wdva:latest
   ```

3. **Deploy to RunPod**:
   - Via Web UI: https://www.runpod.io/console/serverless
   - Via API: Use curl commands above
   - Via SDK: Use Python SDK example

4. **Test endpoint**:
   ```bash
   curl -X POST "https://api.runpod.ai/v2/${ENDPOINT_ID}/run" \
     -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
     -H "Content-Type: application/json" \
     -d '{"input": {"task": "inference", "prompt": "test"}}'
   ```

## Support

- RunPod Docs: https://docs.runpod.io/serverless/overview
- RunPod Discord: https://discord.gg/runpod
- WDVA Issues: https://github.com/zd87pl/slm-vault/issues
