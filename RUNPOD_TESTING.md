# RunPod Endpoint Testing Guide

Your endpoint is deployed! 🎉

**Endpoint URL**: `https://api.runpod.ai/v2/ayi3s70ihlpbtg`

## Quick Test

### 1. Set your API key

```bash
export RUNPOD_API_KEY="your-runpod-api-key"
```

### 2. Run the test script

```bash
chmod +x test_runpod.sh
./test_runpod.sh
```

---

## Manual Testing

### Test 1: Basic Health Check (Inference without adapter)

```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{
    "input": {
      "task": "inference",
      "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "prompt": "Hello, how are you?",
      "max_tokens": 50,
      "temperature": 0.7
    }
  }'
```

**Response**:
```json
{
  "id": "some-job-id-here",
  "status": "IN_QUEUE"
}
```

**Check Status**:
```bash
curl -X GET "https://api.runpod.ai/v2/ayi3s70ihlpbtg/status/JOB_ID" \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

---

### Test 2: Train DoRA Adapter

This will train a small DoRA adapter (takes 2-3 minutes with 100 samples):

```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{
    "input": {
      "task": "training",
      "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "dataset_name": "yahma/alpaca-cleaned",
      "max_samples": 100,
      "epochs": 1,
      "use_4bit": true,
      "lora_r": 16,
      "lora_alpha": 32
    }
  }'
```

**Response includes**:
- Trained adapter weights path
- Training metrics
- Model performance

---

### Test 3: Encrypt Adapter

After training, encrypt the adapter:

```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{
    "input": {
      "task": "encrypt",
      "adapter_path": "/workspace/outputs/dora-adapter",
      "encryption_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "enable_compression": true
    }
  }'
```

**Response includes**:
- Encrypted adapter path
- Encryption metadata
- Original vs compressed size

---

### Test 4: Inference with Encrypted Adapter

Run inference using the encrypted adapter:

```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{
    "input": {
      "task": "inference",
      "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "encrypted_adapter_path": "/workspace/outputs/encrypted-adapter.json",
      "encryption_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "prompt": "Explain machine learning:",
      "max_tokens": 256,
      "temperature": 0.7,
      "enable_cache": true
    }
  }'
```

---

## Understanding RunPod Responses

### Job Submitted
```json
{
  "id": "ayi3s70ihlpbtg-abc123def456",
  "status": "IN_QUEUE"
}
```

### Job Running
```json
{
  "id": "ayi3s70ihlpbtg-abc123def456",
  "status": "IN_PROGRESS",
  "executionTime": 1234
}
```

### Job Completed
```json
{
  "id": "ayi3s70ihlpbtg-abc123def456",
  "status": "COMPLETED",
  "output": {
    "text": "Generated response...",
    "prompt": "Original prompt",
    "metadata": {
      "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "cache_hit": false,
      "inference_time_ms": 1234
    }
  },
  "executionTime": 5678
}
```

### Job Failed
```json
{
  "id": "ayi3s70ihlpbtg-abc123def456",
  "status": "FAILED",
  "error": "Error message here"
}
```

---

## Python SDK Example

```python
import runpod
import os

# Set API key
runpod.api_key = os.environ["RUNPOD_API_KEY"]

# Create endpoint
endpoint = runpod.Endpoint("ayi3s70ihlpbtg")

# Run inference
job = endpoint.run({
    "task": "inference",
    "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "prompt": "Hello, how are you?",
    "max_tokens": 50
})

# Wait for result
result = job.output()
print(result)
```

---

## Checking Logs

### Via API
```bash
curl -X GET "https://api.runpod.ai/v2/ayi3s70ihlpbtg/logs/JOB_ID" \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

### Via Web UI
1. Go to: https://www.runpod.io/console/serverless
2. Click your endpoint
3. Click "Requests" tab
4. View individual job logs

---

## Cost Monitoring

Check costs in real-time:

```bash
curl -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ myself { endpoints { id name usage { currentMonth { cost } } } } }"
  }'
```

---

## Expected Performance

| Operation | Cold Start | Warm | Cost |
|-----------|------------|------|------|
| Health check | 30-60s | 1-2s | $0.01 |
| Inference (no adapter) | 30-60s | 1-3s | $0.01-0.02 |
| Inference (cached adapter) | 30-60s | 1-2s | $0.01-0.02 |
| Training (100 samples) | 60-90s | 120-180s | $0.08-0.12 |
| Encryption | 30-60s | 5-10s | $0.01 |

**Note**: First request will be slower due to cold start (model download, container init)

---

## Troubleshooting

### "Worker not available"
- **Cause**: No workers running (scale-to-zero)
- **Solution**: Wait 30-60s for cold start
- **Check**: Status shows "IN_QUEUE" → "IN_PROGRESS"

### "Timeout"
- **Cause**: Job took too long (default: 10 min)
- **Solution**: Reduce `max_samples` or increase timeout in template settings

### "Out of memory"
- **Cause**: GPU ran out of VRAM
- **Solution**: Use `use_4bit: true` or upgrade GPU type

### "Import error"
- **Cause**: Missing dependency
- **Solution**: Check Dockerfile and requirements.txt

### "Authentication failed"
- **Cause**: Wrong or missing API key
- **Solution**: Verify `RUNPOD_API_KEY` is correct

---

## Next Steps

1. ✅ **Test basic inference** (no adapter)
   ```bash
   ./test_runpod.sh
   ```

2. **Train your first adapter**:
   - Use test examples above
   - Start with 100 samples
   - Takes 2-3 minutes

3. **Encrypt and test**:
   - Encrypt the trained adapter
   - Run inference with encrypted adapter
   - Verify cache performance

4. **Production setup**:
   - Increase `max_workers` for high traffic
   - Set up S3 for adapter storage
   - Implement your own key management
   - Add monitoring/alerting

---

## Production Considerations

### Storage
Your adapter files are stored in `/workspace/outputs/` which is **ephemeral**. For production:

```bash
# Upload to S3 after training
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{
    "input": {
      "task": "training",
      "upload_to_s3": true,
      "s3_bucket": "your-bucket",
      "s3_path": "adapters/user-123/adapter.safetensors"
    }
  }'
```

### Key Management
Don't hardcode encryption keys! Use:
- AWS Secrets Manager
- HashiCorp Vault
- Environment variables per user
- Derive from user password with PBKDF2

### Scaling
Configure in template settings:
- **workersMin**: 0 (save costs)
- **workersMax**: 3-10 (based on traffic)
- **idleTimeout**: 5 min (balance cost vs latency)

---

## Support

- **RunPod Docs**: https://docs.runpod.io/serverless
- **RunPod Discord**: https://discord.gg/runpod
- **WDVA Issues**: https://github.com/zd87pl/slm-vault/issues

🚀 **Your endpoint is ready to use!**
