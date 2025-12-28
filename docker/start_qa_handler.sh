#!/bin/bash
# Startup script for Synthetic Q&A Handler
# Handles RunPod Network Volume detection and cache setup

set -e

echo "=== Synthetic Q&A Handler Startup ==="

# Model selection (default: fast)
QA_MODEL=${QA_MODEL:-fast}
export QA_MODEL

echo "Model Mode: $QA_MODEL"
if [ "$QA_MODEL" = "fast" ]; then
    echo "  → Qwen2.5-14B-Instruct-AWQ (14B, AWQ 4-bit, ~3GB, fast loading)"
    MODEL_CACHE_DIR="models--Qwen--Qwen2.5-14B-Instruct-AWQ"
else
    echo "  → Qwen3-30B-A3B (30.5B total, 3.3B active MoE, ~4GB)"
    MODEL_CACHE_DIR="models--Qwen--Qwen3-30B-A3B"
fi
echo ""

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
    if [ -d "/runpod-volume/huggingface/hub/$MODEL_CACHE_DIR" ]; then
        echo "✓ Model already cached - fast startup expected"
    else
        echo "→ Model not cached - first request will download"
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

# Check vLLM availability
echo "Inference Backend:"
python3 -c "
try:
    import vllm
    print(f'  ✓ vLLM {vllm.__version__} (5-10x faster, parallel batching)')
except ImportError:
    print('  → transformers (slower, sequential)')
" || echo "  → transformers (fallback)"
echo ""

echo "Expected performance (QA_MODEL=$QA_MODEL):"
if [ "$QA_MODEL" = "fast" ]; then
    echo "  - Cold start: ~2-3 minutes (model loading)"
    echo "  - Generation: ~1-2 minutes for 100 samples"
else
    echo "  - Cold start: ~5-10 minutes (model loading)"
    echo "  - Generation: ~2-5 minutes for 100 samples"
fi
echo ""

echo "=== Starting Handler ==="
exec python3 -u src/synthetic_qa_handler.py

