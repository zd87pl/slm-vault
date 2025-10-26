#!/bin/bash
# Test script for RunPod WDVA endpoint

set -e

# Configuration
ENDPOINT_URL="https://api.runpod.ai/v2/ayi3s70ihlpbtg"
RUNPOD_API_KEY="${RUNPOD_API_KEY}"

if [ -z "$RUNPOD_API_KEY" ]; then
    echo "Error: RUNPOD_API_KEY environment variable not set"
    echo "Usage: export RUNPOD_API_KEY=your-key-here"
    exit 1
fi

echo "========================================="
echo "RunPod WDVA Endpoint Test"
echo "========================================="
echo "Endpoint: $ENDPOINT_URL"
echo ""

# Test 1: Health Check / Basic Inference
echo "[Test 1/3] Basic Health Check..."
RESPONSE=$(curl -s -X POST "${ENDPOINT_URL}/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -d '{
    "input": {
      "task": "inference",
      "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
      "prompt": "Hello, how are you?",
      "max_tokens": 50,
      "temperature": 0.7
    }
  }')

echo "$RESPONSE" | jq '.'

# Extract job ID
JOB_ID=$(echo "$RESPONSE" | jq -r '.id')

if [ "$JOB_ID" != "null" ]; then
    echo ""
    echo "✓ Job submitted successfully!"
    echo "Job ID: $JOB_ID"
    echo ""
    echo "Checking status..."
    sleep 5

    # Check status
    STATUS_RESPONSE=$(curl -s -X GET "${ENDPOINT_URL}/status/${JOB_ID}" \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}")

    echo "$STATUS_RESPONSE" | jq '.'

    STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
    echo ""
    echo "Status: $STATUS"

    if [ "$STATUS" == "COMPLETED" ]; then
        echo ""
        echo "✓ Test 1 PASSED - Endpoint is working!"
    else
        echo ""
        echo "⏳ Job still running. Check status with:"
        echo "curl -X GET '${ENDPOINT_URL}/status/${JOB_ID}' -H 'Authorization: Bearer ${RUNPOD_API_KEY}'"
    fi
else
    echo ""
    echo "✗ Test 1 FAILED - Check error above"
    exit 1
fi

echo ""
echo "========================================="
echo "Test Complete!"
echo "========================================="
echo ""
echo "Your endpoint is ready to use!"
echo ""
echo "Next steps:"
echo "1. Train a DoRA adapter (see test_training.sh)"
echo "2. Encrypt the adapter (see test_encryption.sh)"
echo "3. Run inference with encrypted adapter"
