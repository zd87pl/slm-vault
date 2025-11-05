# Dockerfile Fixes for Synthetic QA Generator

## Issues Fixed

### 1. Invalid COPY Syntax (Lines 33-34)
**Problem**: 
```dockerfile
COPY config/ /workspace/config/ 2>/dev/null || true
COPY examples/ /workspace/examples/ 2>/dev/null || true
```

**Issue**: Docker COPY commands don't support shell redirection (`2>/dev/null`) or shell operators (`|| true`). COPY either succeeds or fails - it's not a shell command.

**Fix**: Removed optional COPY commands since `config/` and `examples/` are not required for the synthetic QA handler.

### 2. Inline Comments in RUN Command (Lines 24-29)
**Problem**:
```dockerfile
RUN pip install --no-cache-dir \
    # Additional dependencies for Qwen3
    sentencepiece>=0.1.99 \
    # Faster tokenizers
    tokenizers>=0.15.0
```

**Issue**: While Docker supports comments, having them inline in multi-line RUN commands can cause parsing issues in some Docker versions, especially on RunPod's build system.

**Fix**: Removed inline comments - the packages are self-explanatory.

## Final Dockerfile Structure

```dockerfile
# Copy application code (only src/ is required for synthetic QA handler)
COPY src/ /workspace/src/
```

The handler (`src/synthetic_qa_handler.py`) is standalone and doesn't require `config/` or `examples/` directories.

## Verification

To verify the Dockerfile is correct:

```bash
# Check syntax (will fail fast if syntax errors)
docker build -f docker/Dockerfile.synthetic_qa -t test-build . --no-cache 2>&1 | head -50

# Or build locally first before pushing to RunPod
docker build -f docker/Dockerfile.synthetic_qa -t synthetic-qa-generator:latest .
```

## RunPod Build Tips

1. **Build Context**: Ensure you're building from project root where `src/` and `docker/` directories exist
2. **Build Logs**: Check RunPod build logs if it still fails - they'll show the exact error
3. **Layer Caching**: First build will be slow (downloading base image), subsequent builds use cache
4. **Memory**: Ensure RunPod build has enough memory (8GB+ recommended)

## Common RunPod Build Issues

### Build Fails Immediately
- Check Dockerfile syntax (now fixed)
- Verify build context includes required files
- Check base image availability

### Build Fails During Dependency Installation
- Check `docker/requirements.txt` exists
- Verify all package versions are valid
- Check for conflicting dependencies

### Build Succeeds but Handler Fails
- Verify handler file exists: `src/synthetic_qa_handler.py`
- Check Python path in CMD
- Verify all imports are available

## Testing Locally Before RunPod

```bash
# Build locally
docker build -f docker/Dockerfile.synthetic_qa -t synthetic-qa-generator:latest .

# Test handler imports
docker run --rm synthetic-qa-generator:latest \
    python3 -c "import sys; sys.path.insert(0, '/workspace'); from src.synthetic_qa_handler import handler; print('✓ Handler loads')"

# Test RunPod integration
docker run --rm synthetic-qa-generator:latest \
    python3 -c "import runpod; print('✓ RunPod available')"
```

