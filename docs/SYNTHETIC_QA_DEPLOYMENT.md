# Synthetic Q&A Generation Deployment Guide

## Overview

This guide explains how to deploy the synthetic Q&A generation endpoint using Qwen3-235B-A22B-Instruct-2507 on RunPod.

## Architecture

- **Model**: Qwen3-235B-A22B-Instruct-2507 (MoE: 235B total, 22B activated)
- **Context**: Native 256K tokens (extendable to 1M)
- **Quality**: Exceeds Llama-3.1-70B for synthetic data generation
- **Security**: End-to-end encryption (XChaCha20-Poly1305)

## Deployment Steps

### 1. Build Docker Image

The handler is included in your existing Docker image. Ensure `src/synthetic_qa_handler.py` is copied:

```dockerfile
COPY src/synthetic_qa_handler.py /workspace/src/
```

### 2. Create RunPod Serverless Endpoint

1. Go to RunPod Console → Serverless → Create Endpoint
2. **Name**: `wdva-synthetic-qa-generator`
3. **Container**: Your Docker image (same as training/inference)
4. **GPU**: 
   - **Minimum**: A100 80GB (recommended)
   - **Alternative**: H100 80GB (faster, more expensive)
5. **Handler**: `src/synthetic_qa_handler.py`
6. **Workers**: 0-2 (scale to zero when idle)
7. **Timeout**: 3600 seconds (1 hour)
8. **Environment Variables**: None (keys passed per-request)

### 3. Configure GUI

Set environment variable in your GUI environment:

```bash
export RUNPOD_SYNTHETIC_ENDPOINT_ID=your_endpoint_id_here
```

Or configure in your `.env` file:

```env
RUNPOD_SYNTHETIC_ENDPOINT_ID=your_endpoint_id_here
```

### 4. Usage

The system automatically uses synthetic generation when:
- PDF path is available
- RunPod synthetic endpoint is configured
- Fallback to local generation (MLX/Ollama) if synthetic fails

**No user action required** - synthetic generation is automatic!

## Performance

- **Generation Time**: ~15-20 minutes for 1,000 samples
- **Cost**: ~$0.50-0.65 per PDF (A100 80GB)
- **Quality**: High (better than smaller models)
- **Efficiency**: MoE (22B activated) more efficient than dense 70B

## Security

✅ **PDF encrypted** before network transmission  
✅ **Decryption only** in your RunPod instance  
✅ **Key passed per-request** (never stored)  
✅ **Results encrypted** before returning  
✅ **Memory cleaned up** after generation  
✅ **No persistent storage** on RunPod  

## Troubleshooting

### Model Loading Fails

- Ensure GPU has sufficient VRAM (80GB+)
- Check transformers library version (>=4.46.0)
- Verify BitsAndBytesConfig compatibility

### Generation Timeout

- Increase RunPod endpoint timeout to 3600s
- Check GPU availability (A100/H100)
- Verify model download completed

### Encryption Errors

- Ensure `pycryptodome` or `cryptography` installed
- Verify encryption key is 32 bytes (64 hex chars)
- Check nonce generation (24 bytes)

## Monitoring

Check RunPod logs for:
- Model loading progress
- PDF decryption status
- Q&A generation progress
- Encryption status

## Next Steps

1. Deploy endpoint on RunPod
2. Set `RUNPOD_SYNTHETIC_ENDPOINT_ID` environment variable
3. Test with sample PDF
4. Monitor generation time and quality

