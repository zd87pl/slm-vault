# RunPod Build Troubleshooting Guide

## Issue: Build Failed with No Logs

This usually happens due to one of these issues:

### 1. ✅ FIXED: Build Context Too Large

**Problem**: RunPod can timeout if build context is huge (includes .git, tests, cache, etc.)

**Solution**: ✅ Added `.dockerignore` file to exclude:
- `.git/` directory
- `__pycache__/` and Python cache
- `tests/` directory
- Documentation files
- Output files and logs

**Verify**:
```bash
# Check build context size (should be < 50MB)
du -sh .
# Should show ~552KB or less
```

---

### 2. ✅ FIXED: Dockerfile Path Issues

**Problem**: RunPod portal looks for `Dockerfile` at repo root, but yours was in `docker/Dockerfile`

**Solution**: ✅ Created `Dockerfile` at repository root

**RunPod Portal Configuration**:
- **Dockerfile Path**: Leave as default `Dockerfile` (not `docker/Dockerfile`)
- **Build Context**: `.` (repository root)

---

### 3. GitHub Integration Issues

**Problem**: RunPod can't access your repository

**Check**:
1. **Repository is Public** OR
2. **GitHub App is authorized** (if private)

**Solution**:
- Go to RunPod Console → Templates → Edit
- Under "Source", ensure GitHub connection is authorized
- For private repos: Settings → Applications → RunPod (ensure access granted)

---

### 4. Base Image Pull Issues

**Problem**: `pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime` might be slow or unavailable

**Quick Fix** - Use smaller base image:

```dockerfile
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Install Python
RUN apt-get update && apt-get install -y python3.10 python3-pip
```

**Or try different PyTorch version**:
```dockerfile
FROM pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime
```

---

### 5. Dependency Installation Failures

**Problem**: Some packages might fail to install silently

**Debug** - Test locally:
```bash
docker build -t test-build -f Dockerfile . --progress=plain
```

**Common fixes**:

1. **Pin all versions** in `requirements.txt`:
   ```
   torch==2.1.0
   transformers==4.36.0
   peft==0.9.0
   ```

2. **Add build dependencies** to Dockerfile:
   ```dockerfile
   RUN apt-get update && apt-get install -y \
       git \
       wget \
       build-essential \
       libssl-dev \
       libffi-dev \
       python3-dev
   ```

---

## RunPod Portal Step-by-Step

### Method 1: Using GitHub Integration (Recommended)

1. **Go to**: https://www.runpod.io/console/serverless

2. **New Template** → **GitHub**:
   - Repository: `zd87pl/slm-vault`
   - Branch: `main`
   - Dockerfile Path: `Dockerfile` (leave as default)
   - Build Arguments: (none needed)

3. **Configure**:
   - Template Name: `dora-wdva-inference`
   - Container Registry: Docker Hub (or your choice)
   - Registry Username: Your Docker Hub username
   - **⚠️ IMPORTANT**: Add registry credentials

4. **Environment Variables** (Optional):
   ```
   TOKENIZERS_PARALLELISM=false
   PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
   ```

5. **Click "Build"** and wait (can take 5-15 minutes)

---

### Method 2: Using Pre-Built Image (Faster)

**Build locally and push**:

```bash
# Build
docker build --platform linux/amd64 -t yourusername/dora-wdva:latest -f Dockerfile .

# Test locally first
docker run --rm yourusername/dora-wdva:latest python3 -c "import runpod; import torch; print('OK')"

# Push
docker push yourusername/dora-wdva:latest
```

**Then in RunPod Portal**:
1. New Template → **Container Image**
2. Docker Image Name: `yourusername/dora-wdva:latest`
3. Container Registry Credentials: Your Docker Hub credentials
4. Save Template

**Create Endpoint**:
1. Serverless → New Endpoint
2. Select your template
3. GPU Type: RTX 4090 or A4000
4. Workers: Min=0, Max=3
5. Deploy

---

## Checking Build Status

### Via Web UI
1. Templates → Your Template → "Builds" tab
2. Look for error messages in build logs

### Via API
```bash
curl -X POST "https://api.runpod.io/graphql?api_key=${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ myself { templates { id name builds { id status logs } } } }"
  }'
```

---

## Common Error Messages

### "Failed to pull base image"
**Fix**: Use a different base image or check Docker Hub status

### "Package installation failed"
**Fix**: Pin all package versions in requirements.txt

### "Build context too large"
**Fix**: ✅ Already fixed with `.dockerignore`

### "No space left on device"
**Fix**: Use multi-stage build to reduce image size:

```dockerfile
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime as builder
# ... install dependencies ...

FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime
COPY --from=builder /opt/conda /opt/conda
COPY src/ /workspace/src/
CMD ["python3", "-u", "src/rp_handler.py"]
```

---

## Alternative: Build Locally, Push to Registry

If RunPod builds keep failing, build locally:

```bash
# 1. Build
docker build --platform linux/amd64 -t yourusername/dora-wdva:v1.0 -f Dockerfile .

# 2. Test
docker run --rm --gpus all \
  -e RUNPOD_REQUEST_ID=test \
  yourusername/dora-wdva:v1.0 \
  python3 -c "from src.rp_handler import handler; print(handler({'input': {'task': 'inference', 'prompt': 'test'}}))"

# 3. Push
docker push yourusername/dora-wdva:v1.0

# 4. Use in RunPod
# Just reference the image: yourusername/dora-wdva:v1.0
```

---

## Minimal Test Dockerfile

If still having issues, try this minimal version first:

```dockerfile
FROM nvidia/cuda:12.1.0-base-ubuntu22.04

RUN apt-get update && apt-get install -y python3 python3-pip
RUN pip3 install runpod torch transformers peft

WORKDIR /workspace
COPY src/ /workspace/src/

CMD ["python3", "-u", "src/rp_handler.py"]
```

Build and test:
```bash
docker build -t test-minimal -f Dockerfile.minimal .
docker run --rm test-minimal python3 -c "import runpod; print('OK')"
```

---

## Getting Build Logs

If no logs appear in RunPod portal:

1. **Enable verbose logging** in Dockerfile:
   ```dockerfile
   RUN pip install --no-cache-dir --upgrade pip --verbose
   ```

2. **Build locally with progress**:
   ```bash
   docker build --progress=plain -t test -f Dockerfile . 2>&1 | tee build.log
   ```

3. **Check RunPod Discord**: https://discord.gg/runpod
   - Post your build issue in #support
   - Include: repo link, Dockerfile, error message

---

## Next Steps

1. ✅ **Files Created**:
   - `.dockerignore` - Reduces build context
   - `Dockerfile` (root) - RunPod can find it easily

2. **Commit and push**:
   ```bash
   git add .dockerignore Dockerfile RUNPOD_TROUBLESHOOTING.md
   git commit -m "Add RunPod build fixes"
   git push origin main
   ```

3. **Try RunPod build again**:
   - Use GitHub integration with new Dockerfile
   - Or build locally and push image

4. **If still failing**:
   - Check RunPod status: https://status.runpod.io
   - Contact RunPod support with build logs
   - Try alternative: Build locally → Push → Deploy

---

## Success Checklist

- ✅ `.dockerignore` created (reduces build context)
- ✅ `Dockerfile` at repository root
- ✅ Repository is public or RunPod has access
- ✅ Base image is available (check Docker Hub)
- ✅ All dependencies in `requirements.txt`
- ✅ Handler starts with `runpod.serverless.start()`
- ⏳ Commit and push changes
- ⏳ Try RunPod build again

Good luck! 🚀
