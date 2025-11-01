# RunPod Endpoint Testing Guide

## Quick Tests

### 1. Basic Health Check (30 seconds)
```bash
export RUNPOD_API_KEY="your-key-here"
./test_runpod.sh
```

**Tests**: Single inference request, verifies endpoint is working

---

## Comprehensive Testing

### 2. Full Test Suite (5-10 minutes)
```bash
export RUNPOD_API_KEY="your-key-here"
./test_runpod_comprehensive.sh
```

**Tests**:
- ✅ Basic health check
- ✅ Long-form generation (256 tokens)
- ✅ Batch processing (5 concurrent requests)
- ✅ Temperature variation (0.1, 0.7, 1.0)
- ✅ Error handling (invalid inputs)
- ✅ Performance/latency benchmarks
- ✅ Token limit testing
- ✅ Rapid fire (10 concurrent requests)

**Expected output**:
```
========================================
Test Summary
========================================
Total Tests: 8
Passed: 8
Failed: 0

✓ All tests passed!
```

---

### 3. Full Workflow Test (Python)
```bash
export RUNPOD_API_KEY="your-key-here"
python3 test_full_workflow.py
```

**Tests**:
- ✅ Basic inference
- ✅ Performance benchmarks
- ✅ Error handling
- 🔄 **Optional**: Full DoRA workflow (training → encryption → inference)

**Features**:
- Interactive (asks if you want to run full workflow)
- Detailed performance metrics
- Proper error handling
- JSON output formatting

---

## Load Testing

### 4. Stress Test with Apache Bench
```bash
# Install ab (Apache Bench)
# macOS: brew install ab
# Linux: sudo apt-get install apache2-utils

# Create test payload
cat > payload.json << 'EOF'
{
  "input": {
    "task": "inference",
    "prompt": "Hello, how are you?",
    "max_tokens": 50
  }
}
EOF

# Run 100 requests, 10 concurrent
ab -n 100 -c 10 -p payload.json -T application/json \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run"
```

**Metrics to watch**:
- Requests per second
- Mean time per request
- Percentage of failed requests
- 95th percentile latency

---

### 5. Concurrent Load Test (Python)
```python
import concurrent.futures
import requests
import time

ENDPOINT = "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run"
API_KEY = "your-key"

def run_inference(i):
    start = time.time()
    response = requests.post(ENDPOINT,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"input": {"task": "inference", "prompt": f"Request {i}", "max_tokens": 20}}
    )
    return time.time() - start, response.status_code

# Run 50 concurrent requests
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(run_inference, i) for i in range(50)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

# Analyze
times = [r[0] for r in results]
successes = sum(1 for r in results if r[1] == 200)
print(f"Completed: {successes}/50")
print(f"Avg time: {sum(times)/len(times):.2f}s")
print(f"Min: {min(times):.2f}s, Max: {max(times):.2f}s")
```

---

## Realistic Workflow Tests

### Test A: Customer Support Bot
```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "task": "inference",
      "prompt": "Customer: My order #12345 hasn'\''t arrived yet. What should I do?\nSupport:",
      "max_tokens": 150,
      "temperature": 0.7
    }
  }'
```

### Test B: Code Generation
```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "task": "inference",
      "prompt": "Write a Python function to calculate fibonacci numbers:\n\ndef fibonacci(n):",
      "max_tokens": 200,
      "temperature": 0.3
    }
  }'
```

### Test C: Content Summarization
```bash
curl -X POST "https://api.runpod.ai/v2/ayi3s70ihlpbtg/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "task": "inference",
      "prompt": "Summarize this article in 3 bullet points:\n\n[Long article text here...]\n\nSummary:",
      "max_tokens": 150,
      "temperature": 0.5
    }
  }'
```

---

## Performance Benchmarks

### Expected Performance (CPU)
| Metric | Target | Actual |
|--------|--------|--------|
| Cold start | < 60s | ? |
| Warm inference (50 tokens) | < 10s | ? |
| Warm inference (256 tokens) | < 30s | ? |
| Concurrent requests (10) | All complete | ? |

### Expected Performance (GPU - RTX 4090)
| Metric | Target | Actual |
|--------|--------|--------|
| Cold start | < 45s | ? |
| Warm inference (50 tokens) | < 2s | ? |
| Warm inference (256 tokens) | < 5s | ? |
| Concurrent requests (10) | All complete | ? |

---

## Monitoring & Logs

### Check Endpoint Stats
```bash
curl -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ myself { endpoints { id name workers { running idle } } } }"
  }' | jq '.'
```

### View Recent Logs
1. Go to: https://www.runpod.io/console/serverless
2. Click your endpoint
3. Click "Requests" tab
4. View logs for each request

### Get Job Logs (via API)
```bash
JOB_ID="your-job-id"
curl -X GET "https://api.runpod.ai/v2/ayi3s70ihlpbtg/logs/$JOB_ID" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" | jq '.'
```

---

## Cost Analysis

Track your spending:

```bash
# Get usage stats
curl -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ myself { endpoints { id name usage { currentMonth { cost requests } } } } }"
  }' | jq '.'
```

**Typical costs** (RTX 4090):
- Inference (50 tokens): $0.01-0.02
- Inference (256 tokens): $0.02-0.04
- Training (100 samples): $0.10-0.15

---

## Troubleshooting

### High Latency
**Symptoms**: Requests taking > 30s

**Fixes**:
1. Enable GPU workers (not CPU)
2. Increase `max_workers` setting
3. Enable adapter caching
4. Use smaller `max_tokens`

### Frequent Timeouts
**Symptoms**: Jobs timing out

**Fixes**:
1. Increase execution timeout in template
2. Reduce `max_samples` for training
3. Check worker health in console

### High Costs
**Symptoms**: Unexpected charges

**Fixes**:
1. Set `workersMin` to 0 (scale to zero)
2. Reduce `idleTimeout` (e.g., 3 min)
3. Use spot instances instead of on-demand
4. Monitor with cost alerts

---

## Next Steps

After testing:

1. **Production Setup**:
   - Add authentication/API keys
   - Set up monitoring (Datadog, Prometheus)
   - Configure auto-scaling
   - Add rate limiting

2. **Integration**:
   - Integrate with your app
   - Add retry logic
   - Implement caching layer
   - Set up webhooks for async processing

3. **Optimization**:
   - Fine-tune adapter for your use case
   - Optimize prompts for better outputs
   - Test different models (Llama 2, Mistral)
   - Implement prompt caching

---

## Support

- **RunPod Docs**: https://docs.runpod.io/serverless
- **RunPod Discord**: https://discord.gg/runpod
- **Issues**: https://github.com/zd87pl/slm-vault/issues

Happy testing! 🚀
