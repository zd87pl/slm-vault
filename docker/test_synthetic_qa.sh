#!/bin/bash
# Test script for Synthetic Q&A Generator
# Tests the handler with a sample encrypted PDF

set -e

ENDPOINT_ID=${RUNPOD_SYNTHETIC_ENDPOINT_ID:-""}
API_KEY=${RUNPOD_API_KEY:-""}
PDF_PATH=${1:-""}

if [ -z "$ENDPOINT_ID" ] || [ -z "$API_KEY" ]; then
    echo "❌ Error: RUNPOD_SYNTHETIC_ENDPOINT_ID and RUNPOD_API_KEY must be set"
    echo ""
    echo "Usage:"
    echo "  export RUNPOD_SYNTHETIC_ENDPOINT_ID=your_endpoint_id"
    echo "  export RUNPOD_API_KEY=your_api_key"
    echo "  ./docker/test_synthetic_qa.sh /path/to/test.pdf"
    exit 1
fi

if [ -z "$PDF_PATH" ] || [ ! -f "$PDF_PATH" ]; then
    echo "❌ Error: PDF file path required"
    echo ""
    echo "Usage: ./docker/test_synthetic_qa.sh /path/to/test.pdf"
    exit 1
fi

echo "🧪 Testing Synthetic Q&A Generator"
echo "📄 PDF: $PDF_PATH"
echo "🔗 Endpoint: $ENDPOINT_ID"
echo ""

# Generate encryption key
ENCRYPTION_KEY=$(python3 -c "import secrets; print(secrets.token_bytes(32).hex())")
echo "🔑 Generated encryption key"

# Encrypt PDF (simplified - you'd use the actual encryption from qa_generator.py)
echo "🔒 Encrypting PDF..."
# Note: This is a simplified test - actual encryption should use XChaCha20-Poly1305

# Create test payload
PAYLOAD=$(cat <<EOF
{
  "input": {
    "encrypted_pdf": "{\"ciphertext\":\"test\",\"tag\":\"test\",\"nonce\":\"test\"}",
    "encryption_key_hex": "$ENCRYPTION_KEY",
    "target_samples": 100
  }
}
EOF
)

echo "📤 Submitting job to RunPod..."
RESPONSE=$(curl -s -X POST \
    "https://api.runpod.ai/v2/$ENDPOINT_ID/run" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

if [ -z "$JOB_ID" ]; then
    echo "❌ Failed to submit job"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "✅ Job submitted: $JOB_ID"
echo "⏳ Waiting for completion (this may take 15-20 minutes)..."
echo ""

# Poll for status
while true; do
    STATUS_RESPONSE=$(curl -s -X GET \
        "https://api.runpod.ai/v2/$ENDPOINT_ID/status/$JOB_ID" \
        -H "Authorization: Bearer $API_KEY")
    
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
    
    case "$STATUS" in
        "COMPLETED")
            echo "✅ Job completed!"
            echo "$STATUS_RESPONSE" | python3 -m json.tool
            break
            ;;
        "FAILED")
            echo "❌ Job failed!"
            echo "$STATUS_RESPONSE" | python3 -m json.tool
            exit 1
            ;;
        "IN_QUEUE"|"IN_PROGRESS")
            echo "⏳ Status: $STATUS"
            sleep 10
            ;;
        *)
            echo "⚠️  Unknown status: $STATUS"
            sleep 10
            ;;
    esac
done

echo ""
echo "🎉 Test complete!"

