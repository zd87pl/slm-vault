#!/bin/bash
# Deploy DoRA WDVA to RunPod Serverless

set -e

# Configuration
IMAGE_NAME="${DOCKER_USERNAME:-yourusername}/dora-wdva"
IMAGE_TAG="${IMAGE_TAG:-latest}"
RUNPOD_ENDPOINT_NAME="${RUNPOD_ENDPOINT_NAME:-dora-wdva-inference}"

echo "========================================="
echo "RunPod Deployment for DoRA WDVA"
echo "========================================="
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Endpoint: $RUNPOD_ENDPOINT_NAME"
echo "========================================="

# Step 1: Build Docker image
echo ""
echo "[1/3] Building Docker image..."
docker build --platform linux/amd64 \
    -t "$IMAGE_NAME:$IMAGE_TAG" \
    -f docker/Dockerfile \
    .

echo "✓ Docker image built successfully"

# Step 2: Push to registry
echo ""
echo "[2/3] Pushing to Docker registry..."
docker push "$IMAGE_NAME:$IMAGE_TAG"

echo "✓ Image pushed successfully"

# Step 3: Deploy to RunPod (requires runpodctl or API)
echo ""
echo "[3/3] Deploying to RunPod..."

if command -v runpodctl &> /dev/null; then
    # Using runpodctl CLI
    echo "Deploying using runpodctl..."
    runpodctl deploy \
        --name "$RUNPOD_ENDPOINT_NAME" \
        --image "$IMAGE_NAME:$IMAGE_TAG" \
        --gpu "RTX 4090" \
        --min-workers 0 \
        --max-workers 3 \
        --idle-timeout 5

    echo "✓ Deployment complete"
else
    echo "⚠️  runpodctl not found. Please deploy manually or use the API."
    echo ""
    echo "Manual deployment steps:"
    echo "1. Go to https://www.runpod.io/console/serverless"
    echo "2. Create new endpoint with image: $IMAGE_NAME:$IMAGE_TAG"
    echo "3. Configure GPU: RTX 4090 or similar"
    echo "4. Set min_workers=0, max_workers=3"
    echo "5. Set idle_timeout=5 minutes"
fi

echo ""
echo "========================================="
echo "Deployment Complete!"
echo "========================================="
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Endpoint: $RUNPOD_ENDPOINT_NAME"
echo ""
echo "Test your endpoint with:"
echo "  curl -X POST https://api.runpod.ai/v2/\$ENDPOINT_ID/run \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'Authorization: Bearer \$RUNPOD_API_KEY' \\"
echo "    -d '{\"input\": {\"task\": \"inference\", \"prompt\": \"Hello world\"}}'"
echo "========================================="
