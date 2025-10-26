#!/bin/bash
# Quick status checker for RunPod jobs

JOB_ID="${1:-f973cb83-4723-4af7-9fdf-166de6b38eb8-u2}"
ENDPOINT_URL="https://api.runpod.ai/v2/ayi3s70ihlpbtg"
RUNPOD_API_KEY="${RUNPOD_API_KEY}"

if [ -z "$RUNPOD_API_KEY" ]; then
    echo "Error: RUNPOD_API_KEY not set"
    exit 1
fi

echo "Checking status for job: $JOB_ID"
echo ""

# Poll until complete or failed
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    RESPONSE=$(curl -s -X GET "${ENDPOINT_URL}/status/${JOB_ID}" \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}")

    STATUS=$(echo "$RESPONSE" | jq -r '.status')

    echo -ne "\r[Attempt $((ATTEMPT+1))/$MAX_ATTEMPTS] Status: $STATUS     "

    if [ "$STATUS" == "COMPLETED" ]; then
        echo ""
        echo ""
        echo "✅ Job COMPLETED!"
        echo ""
        echo "$RESPONSE" | jq '.'
        exit 0
    elif [ "$STATUS" == "FAILED" ]; then
        echo ""
        echo ""
        echo "❌ Job FAILED!"
        echo ""
        echo "$RESPONSE" | jq '.'
        exit 1
    fi

    ATTEMPT=$((ATTEMPT+1))
    sleep 5
done

echo ""
echo ""
echo "⏱️  Job still running after ${MAX_ATTEMPTS} attempts (2.5 minutes)"
echo "Check manually:"
echo "curl -X GET '${ENDPOINT_URL}/status/${JOB_ID}' -H 'Authorization: Bearer \$RUNPOD_API_KEY' | jq '.'"
