#!/bin/bash
# Build script for Synthetic Q&A Generator Docker image
# Usage: ./docker/build_synthetic_qa.sh [tag]

set -e

TAG=${1:-"synthetic-qa-generator:latest"}
DOCKERFILE="docker/Dockerfile.synthetic_qa"

echo "🔨 Building Synthetic Q&A Generator Docker image..."
echo "📦 Tag: $TAG"
echo "📄 Dockerfile: $DOCKERFILE"
echo ""

# Build from project root
cd "$(dirname "$0")/.."

# Build Docker image
docker build \
    -f "$DOCKERFILE" \
    -t "$TAG" \
    --platform linux/amd64 \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    .

echo ""
echo "✅ Build complete!"
echo "📦 Image: $TAG"
echo ""
echo "🚀 To push to registry:"
echo "   docker push $TAG"
echo ""
echo "📋 To test locally:"
echo "   docker run --gpus all -p 8000:8000 $TAG"

