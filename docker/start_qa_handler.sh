#!/bin/bash
# Startup script for Synthetic Q&A Handler
# Handles RunPod Network Volume detection and cache setup

set -e

echo "=== Synthetic Q&A Handler Startup ==="
echo "Model: Qwen3-30B-A3B (MoE: 30.5B total, 3.3B activated)"

# Check if RunPod Network Volume is mounted
if [ -d "/runpod-volume" ] && [ -w "/runpod-volume" ]; then
    echo "✓ RunPod Network Volume detected at /runpod-volume"
    
    # Create cache directories on volume
    mkdir -p /runpod-volume/huggingface/hub
    mkdir -p /runpod-volume/huggingface/datasets
    
    # Set environment variables to use volume
    export HF_HOME=/runpod-volume/huggingface
    export TRANSFORMERS_CACHE=/runpod-volume/huggingface
    export HF_DATASETS_CACHE=/runpod-volume/huggingface/datasets
    
    # Check available space on volume
    AVAILABLE_GB=$(df -BG /runpod-volume | awk 'NR==2 {print $4}' | sed 's/G//')
    echo "✓ Available space on volume: ${AVAILABLE_GB}GB"
    
    if [ "$AVAILABLE_GB" -lt 10 ]; then
        echo "⚠ Warning: Less than 10GB available. Model download may fail."
    fi
    
    # Check if model is already cached
    if [ -d "/runpod-volume/huggingface/hub/models--Qwen--Qwen3-30B-A3B" ]; then
        echo "✓ Model already cached - fast startup expected"
    else
        echo "→ Model not cached - first request will download (~4GB)"
    fi
else
    echo "⚠ No RunPod Network Volume detected"
    echo "→ Using local cache at /workspace/.cache/huggingface"
    echo "→ Model will be re-downloaded on each cold start!"
    
    # Fall back to local cache
    export HF_HOME=/workspace/.cache/huggingface
    export TRANSFORMERS_CACHE=/workspace/.cache/huggingface
    export HF_DATASETS_CACHE=/workspace/.cache/huggingface/datasets
    
    # Create local cache directories
    mkdir -p /workspace/.cache/huggingface/hub
    mkdir -p /workspace/.cache/huggingface/datasets
    
    # Check available space
    AVAILABLE_GB=$(df -BG /workspace | awk 'NR==2 {print $4}' | sed 's/G//')
    echo "→ Available space: ${AVAILABLE_GB}GB"
    
    if [ "$AVAILABLE_GB" -lt 10 ]; then
        echo "⚠ CRITICAL: Less than 10GB available!"
        echo "→ Consider mounting a Network Volume in RunPod settings"
    fi
fi

# Print final cache location
echo ""
echo "Cache configuration:"
echo "  HF_HOME=$HF_HOME"
echo "  TRANSFORMERS_CACHE=$TRANSFORMERS_CACHE"
echo ""

# Check CUDA availability
echo "CUDA Status:"
python3 -c "import torch; print(f'  PyTorch: {torch.__version__}'); print(f'  CUDA available: {torch.cuda.is_available()}'); print(f'  CUDA version: {torch.version.cuda if torch.cuda.is_available() else \"N/A\"}'); print(f'  GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')" || echo "  ⚠ CUDA check failed"
echo ""

echo "=== Starting Handler ==="
exec python3 -u src/synthetic_qa_handler.py

