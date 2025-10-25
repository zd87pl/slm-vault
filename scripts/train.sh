#!/bin/bash
# Train DoRA adapter using Axolotl or standalone script

set -e

# Default to standalone training
METHOD="${1:-standalone}"

echo "========================================="
echo "DoRA Training"
echo "========================================="
echo "Method: $METHOD"
echo "========================================="

if [ "$METHOD" = "axolotl" ]; then
    echo ""
    echo "Training with Axolotl..."
    echo ""

    # Check if axolotl is installed
    if ! command -v axolotl &> /dev/null; then
        echo "Installing Axolotl..."
        pip install packaging ninja
        pip install --no-build-isolation 'axolotl[flash-attn,deepspeed]'
    fi

    # Preprocess dataset (optional but recommended)
    echo "Preprocessing dataset..."
    axolotl preprocess config/tinyllama-dora.yml

    # Train
    echo "Starting training..."
    accelerate launch -m axolotl.cli.train config/tinyllama-dora.yml

    echo ""
    echo "✓ Training complete!"
    echo "✓ Adapter saved to ./outputs/tinyllama-dora"

elif [ "$METHOD" = "standalone" ]; then
    echo ""
    echo "Training with standalone script..."
    echo ""

    # Use standalone training script
    python3 src/train_dora.py \
        --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
        --rank 16 \
        --alpha 32 \
        --dropout 0.05 \
        --dataset yahma/alpaca-cleaned \
        --max-samples 1000 \
        --epochs 3 \
        --batch-size 4 \
        --learning-rate 2e-4 \
        --output-dir ./outputs/dora-adapter \
        --use-4bit

    echo ""
    echo "✓ Training complete!"
    echo "✓ Adapter saved to ./outputs/dora-adapter"

else
    echo "Error: Unknown method '$METHOD'"
    echo "Usage: $0 [axolotl|standalone]"
    exit 1
fi

echo ""
echo "========================================="
echo "Next steps:"
echo "  1. Encrypt adapter: ./scripts/encrypt_adapter.sh"
echo "  2. Run inference: python3 examples/complete_workflow.py --skip-training"
echo "========================================="
