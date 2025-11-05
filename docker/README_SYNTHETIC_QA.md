# Synthetic Q&A Generator - Docker Build Guide

## Quick Start

### Option 1: Build from Project Root (Recommended)

```bash
# From project root
docker build -f docker/Dockerfile.synthetic_qa -t synthetic-qa-generator:latest .
```

### Option 2: Use Build Script

```bash
# From project root
./docker/build_synthetic_qa.sh synthetic-qa-generator:latest
```

### Option 3: Standalone Build (Minimal)

```bash
# Only copies handler file, faster build
docker build -f docker/Dockerfile.synthetic_qa.standalone -t synthetic-qa-generator:latest .
```

## RunPod Deployment

### Step 1: Build and Push to Registry

```bash
# Build image
docker build -f docker/Dockerfile.synthetic_qa -t synthetic-qa-generator:latest .

# Tag for your registry (example: Docker Hub)
docker tag synthetic-qa-generator:latest yourusername/synthetic-qa-generator:latest

# Push to registry
docker push yourusername/synthetic-qa-generator:latest
```

### Step 2: Create RunPod Serverless Endpoint

1. **Go to RunPod Console** → Serverless → Create Endpoint

2. **Container Configuration**:
   - **Container Image**: `yourusername/synthetic-qa-generator:latest`
   - **Container Disk**: 50GB (for model cache)
   - **Docker Command**: Leave empty (uses CMD from Dockerfile)

3. **GPU Configuration**:
   - **GPU Type**: A100 80GB (minimum) or H100 80GB (recommended)
   - **GPU Count**: 1
   - **Workers**: 0-2 (scale to zero when idle)

4. **Settings**:
   - **Timeout**: 3600 seconds (1 hour)
   - **Max Execution Time**: 3600 seconds
   - **Handler**: `src/synthetic_qa_handler.py` (already in CMD)

5. **Environment Variables**: None required (keys passed per-request)

6. **Click "Create Endpoint"**

### Step 3: Get Endpoint ID

After creation, copy the **Endpoint ID** from RunPod console.

### Step 4: Configure GUI

Set environment variable:

```bash
export RUNPOD_SYNTHETIC_ENDPOINT_ID=your_endpoint_id_here
```

Or add to `.env`:

```env
RUNPOD_SYNTHETIC_ENDPOINT_ID=your_endpoint_id_here
```

## Local Testing

### Test with GPU

```bash
docker run --gpus all \
    -e RUNPOD_API_KEY=your_api_key \
    -p 8000:8000 \
    synthetic-qa-generator:latest
```

### Test Handler Logic (without GPU)

```bash
docker run \
    -e RUNPOD_API_KEY=your_api_key \
    synthetic-qa-generator:latest \
    python3 -c "from src.synthetic_qa_handler import handler; print('Handler loaded')"
```

## Image Size

- **Base Image**: ~8GB (PyTorch CUDA)
- **Dependencies**: ~2GB
- **Total**: ~10GB
- **With Model Cache**: ~50GB+ (first run downloads Qwen3-235B)

## Build Optimizations

### Layer Caching

The Dockerfile is optimized for layer caching:
1. System dependencies
2. Python dependencies (requirements.txt)
3. Application code

Rebuilds only affected layers.

### Multi-Stage Build (Optional)

For smaller final image, use multi-stage build:

```dockerfile
# Build stage
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime as builder
# ... install dependencies ...

# Runtime stage
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# ... copy handler ...
```

## Troubleshooting

### Build Fails: Out of Memory

```bash
# Increase Docker memory limit
# Docker Desktop → Settings → Resources → Memory: 8GB+
```

### Model Download Fails

- Check internet connection
- Verify HuggingFace Hub access
- Check disk space (need 50GB+)

### GPU Not Detected

```bash
# Verify NVIDIA Docker runtime
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### Handler Not Starting

```bash
# Check logs
docker logs <container_id>

# Verify handler file exists
docker run --rm synthetic-qa-generator:latest ls -la /workspace/src/synthetic_qa_handler.py
```

## Verification

### Verify Handler

```bash
docker run --rm synthetic-qa-generator:latest \
    python3 -c "import sys; sys.path.insert(0, '/workspace'); from src.synthetic_qa_handler import handler; print('✓ Handler loaded')"
```

### Verify Dependencies

```bash
docker run --rm synthetic-qa-generator:latest \
    python3 -c "import torch; import transformers; import runpod; import pypdf; print('✓ All dependencies available')"
```

## Production Checklist

- [ ] Image built and tested locally
- [ ] Pushed to container registry
- [ ] RunPod endpoint created
- [ ] Endpoint ID configured in GUI
- [ ] Tested with sample PDF
- [ ] Monitored generation time and cost
- [ ] Verified encryption end-to-end

## Cost Estimation

**A100 80GB**:
- Generation time: ~15-20 minutes per PDF
- Cost: ~$0.50-0.65 per PDF
- Idle: Scales to zero (no cost)

**H100 80GB**:
- Generation time: ~10-15 minutes per PDF
- Cost: ~$0.75-1.00 per PDF
- Idle: Scales to zero (no cost)

## Support

For issues:
1. Check RunPod logs
2. Verify Docker image builds successfully
3. Test handler locally
4. Check GPU availability

