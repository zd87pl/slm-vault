#!/bin/bash
# Encrypt DoRA adapter

set -e

# Configuration
ADAPTER_PATH="${1:-./outputs/dora-adapter}"
OUTPUT_PATH="${2:-./outputs/encrypted-adapter.json}"
KEY_FILE="${3:-./outputs/encryption-key.txt}"

echo "========================================="
echo "DoRA Adapter Encryption"
echo "========================================="
echo "Adapter: $ADAPTER_PATH"
echo "Output: $OUTPUT_PATH"
echo "Key file: $KEY_FILE"
echo "========================================="

# Check if adapter exists
if [ ! -d "$ADAPTER_PATH" ]; then
    echo "Error: Adapter directory not found: $ADAPTER_PATH"
    exit 1
fi

# Create Python script to encrypt
cat > /tmp/encrypt_adapter.py << 'EOF'
import sys
import torch
from pathlib import Path
from peft import PeftModel
from transformers import AutoModelForCausalLM
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.dora_crypto import EncryptedDoRAManager, generate_secure_password

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter-path', required=True)
    parser.add_argument('--output-path', required=True)
    parser.add_argument('--key-file', required=True)
    args = parser.parse_args()

    # Generate encryption key
    encryption_key = generate_secure_password()

    # Save key to file
    with open(args.key_file, 'w') as f:
        f.write(encryption_key.hex())

    print(f"Generated encryption key (saved to {args.key_file})")
    print("⚠️  IMPORTANT: Store this key securely!")

    # Load adapter config to get base model
    adapter_config_path = Path(args.adapter_path) / 'adapter_config.json'
    with open(adapter_config_path, 'r') as f:
        adapter_config = json.load(f)

    base_model_name = adapter_config.get('base_model_name_or_path',
                                         'TinyLlama/TinyLlama-1.1B-Chat-v1.0')

    print(f"Loading base model: {base_model_name}")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.float16,
        device_map="cpu",
        low_cpu_mem_usage=True
    )

    print(f"Loading adapter from: {args.adapter_path}")
    model = PeftModel.from_pretrained(base_model, args.adapter_path)

    # Encrypt
    print("Encrypting adapter...")
    manager = EncryptedDoRAManager(
        encryption_key,
        enable_compression=True,
        compression_level=3
    )

    encrypted_metadata = manager.extract_and_encrypt_dora_weights(
        model,
        args.output_path,
        metadata={'adapter_path': args.adapter_path}
    )

    print(f"✓ Encryption complete")
    print(f"  Encrypted file: {args.output_path}")
    print(f"  Original size: {encrypted_metadata['metadata']['original_size_bytes'] / 1024**2:.2f} MB")
    print(f"  Compressed: {encrypted_metadata['metadata']['compressed']}")
    print(f"  Tensors: {encrypted_metadata['metadata']['num_tensors']}")

if __name__ == '__main__':
    main()
EOF

# Run encryption
python3 /tmp/encrypt_adapter.py \
    --adapter-path "$ADAPTER_PATH" \
    --output-path "$OUTPUT_PATH" \
    --key-file "$KEY_FILE"

# Cleanup
rm /tmp/encrypt_adapter.py

echo ""
echo "========================================="
echo "Encryption Complete!"
echo "========================================="
echo "Encrypted adapter: $OUTPUT_PATH"
echo "Encryption key: $KEY_FILE"
echo ""
echo "⚠️  IMPORTANT: Store the encryption key securely!"
echo "    The key is required for decryption."
echo ""
echo "Next steps:"
echo "  1. Store key in secure vault (AWS Secrets Manager, etc.)"
echo "  2. Test inference with encrypted adapter"
echo "========================================="
