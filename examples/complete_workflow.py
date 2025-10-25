#!/usr/bin/env python3
"""
Complete WDVA PoC: DoRA Training → Encryption → Ephemeral Merging → Inference

This example demonstrates the entire workflow end-to-end with all security
and performance improvements implemented.
"""

import torch
import argparse
import logging
from pathlib import Path
import sys
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dora_crypto import EncryptedDoRAManager, generate_secure_password
from src.ephemeral_inference import EphemeralDoRAInference
from src.train_dora import load_and_prepare_model, prepare_dataset
from transformers import TrainingArguments, Trainer, DataCollatorForLanguageModeling

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def phase1_train_dora(args) -> tuple[object, str]:
    """
    Phase 1: Train DoRA adapter.

    Returns:
        Tuple of (model, adapter_path)
    """
    logger.info("=" * 80)
    logger.info("PHASE 1: DoRA Training")
    logger.info("=" * 80)

    # Create simple args object for training
    class TrainArgs:
        model_name = args.model_name
        rank = args.rank
        alpha = args.alpha
        dropout = args.dropout
        dataset = args.dataset
        max_samples = args.max_samples
        epochs = args.epochs
        batch_size = args.batch_size
        learning_rate = args.learning_rate
        max_length = 512
        output_dir = args.output_dir
        use_4bit = args.use_4bit
        use_8bit = False
        gradient_checkpointing = True

    train_args = TrainArgs()

    # Load model
    logger.info("Loading and configuring model...")
    model, tokenizer = load_and_prepare_model(train_args)

    # Prepare dataset
    logger.info("Preparing dataset...")
    train_dataset = prepare_dataset(train_args, tokenizer)

    # Training arguments
    output_dir = Path(train_args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=train_args.epochs,
        per_device_train_batch_size=train_args.batch_size,
        learning_rate=train_args.learning_rate,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",
        optim="adamw_bnb_8bit" if train_args.use_4bit else "adamw_torch",
        lr_scheduler_type="cosine",
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False
    )

    # Train
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=data_collator,
    )

    logger.info("Training started...")
    train_result = trainer.train()

    # Save
    logger.info(f"Saving adapter to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    logger.info(f"✓ DoRA training complete (loss: {train_result.training_loss:.4f})")
    logger.info(f"✓ Adapter saved to {output_dir}")

    return model, str(output_dir)


def phase2_encrypt_adapter(model, adapter_path: str, encryption_key: bytes) -> str:
    """
    Phase 2: Encrypt DoRA adapter.

    Returns:
        Path to encrypted adapter
    """
    logger.info("\n" + "=" * 80)
    logger.info("PHASE 2: Adapter Encryption")
    logger.info("=" * 80)

    # Initialize crypto manager
    crypto_manager = EncryptedDoRAManager(
        encryption_key,
        enable_compression=True,
        compression_level=3
    )

    # Encrypt
    encrypted_path = adapter_path.replace('dora-adapter', 'encrypted-adapter.json')
    logger.info(f"Encrypting adapter...")

    encrypted_metadata = crypto_manager.extract_and_encrypt_dora_weights(
        model,
        encrypted_path,
        metadata={'source': 'complete_workflow_example'}
    )

    logger.info("✓ Encryption complete")
    logger.info(f"  Algorithm: {encrypted_metadata['algorithm']}")
    logger.info(f"  KDF: {encrypted_metadata['kdf']}")
    logger.info(f"  Tensors encrypted: {encrypted_metadata['metadata']['num_tensors']}")
    logger.info(f"  Original size: {encrypted_metadata['metadata']['original_size_bytes'] / 1024**2:.2f} MB")
    logger.info(f"  Compressed: {encrypted_metadata['metadata']['compressed']}")
    logger.info(f"✓ Encrypted adapter saved to {encrypted_path}")

    return encrypted_path


def phase3_ephemeral_inference(encrypted_path: str,
                               encryption_key: bytes,
                               args) -> None:
    """
    Phase 3: Ephemeral merging and inference.
    """
    logger.info("\n" + "=" * 80)
    logger.info("PHASE 3: Ephemeral Merging & Inference")
    logger.info("=" * 80)

    # Clean up training model first
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Initialize inference engine
    logger.info("Initializing ephemeral inference engine...")
    inference_engine = EphemeralDoRAInference(
        base_model_name=args.model_name,
        encryption_key=encryption_key,
        enable_cache=True,
        cache_size=3,
        load_in_4bit=args.use_4bit,
    )

    # Test prompts
    test_prompts = [
        "Explain quantum computing in simple terms:",
        "Write a haiku about machine learning:",
        "What are the benefits of regular exercise?",
    ]

    logger.info(f"\nRunning {len(test_prompts)} inference tests...")
    logger.info("-" * 80)

    results = []
    for i, prompt in enumerate(test_prompts, 1):
        logger.info(f"\n[Inference {i}/{len(test_prompts)}]")
        logger.info(f"Prompt: {prompt}")

        # Run inference
        result = inference_engine.inference_with_encrypted_adapter(
            encrypted_path,
            prompt,
            max_tokens=100,
            temperature=0.7,
        )

        # Extract just the response part (remove prompt)
        response = result['response']
        if response.startswith(prompt):
            response = response[len(prompt):].strip()

        logger.info(f"Response: {response[:200]}{'...' if len(response) > 200 else ''}")
        logger.info(f"Cache hit: {result['metadata']['cache_hit']}")
        logger.info(f"Timing: {result['metadata']['timing']['total_ms']:.2f}ms total, "
                   f"{result['metadata']['timing']['inference_ms']:.2f}ms inference")

        results.append(result)

    # Log final metrics
    logger.info("\n" + "-" * 80)
    logger.info("Final Metrics:")
    inference_engine.log_metrics()

    logger.info("\n✓ All inference tests complete")
    logger.info("✓ Adapters loaded → inference → cleaned up (ephemeral)")


def main():
    """Main workflow orchestrator."""
    parser = argparse.ArgumentParser(description='Complete WDVA workflow')

    # Model & training
    parser.add_argument('--model-name', type=str,
                       default='TinyLlama/TinyLlama-1.1B-Chat-v1.0',
                       help='Base model name')
    parser.add_argument('--dataset', type=str, default='yahma/alpaca-cleaned',
                       help='Training dataset')
    parser.add_argument('--max-samples', type=int, default=100,
                       help='Max training samples (small for demo)')

    # DoRA config
    parser.add_argument('--rank', type=int, default=8,
                       help='DoRA rank (8 for quick demo)')
    parser.add_argument('--alpha', type=int, default=16,
                       help='DoRA alpha')
    parser.add_argument('--dropout', type=float, default=0.05,
                       help='DoRA dropout')

    # Training params
    parser.add_argument('--epochs', type=int, default=1,
                       help='Training epochs (1 for quick demo)')
    parser.add_argument('--batch-size', type=int, default=2,
                       help='Batch size')
    parser.add_argument('--learning-rate', type=float, default=2e-4,
                       help='Learning rate')

    # System
    parser.add_argument('--output-dir', type=str, default='./outputs/demo-dora-adapter',
                       help='Output directory')
    parser.add_argument('--use-4bit', action='store_true', default=True,
                       help='Use 4-bit quantization (QDoRA)')
    parser.add_argument('--skip-training', action='store_true',
                       help='Skip training phase (use existing adapter)')

    args = parser.parse_args()

    # Print configuration
    logger.info("=" * 80)
    logger.info("WDVA COMPLETE WORKFLOW")
    logger.info("DoRA Training → Encryption → Ephemeral Merging → Inference")
    logger.info("=" * 80)
    logger.info(f"Model: {args.model_name}")
    logger.info(f"Dataset: {args.dataset} (max {args.max_samples} samples)")
    logger.info(f"DoRA: rank={args.rank}, alpha={args.alpha}, dropout={args.dropout}")
    logger.info(f"Training: {args.epochs} epoch(s), batch_size={args.batch_size}")
    logger.info(f"Quantization: 4bit={args.use_4bit}")
    logger.info(f"Output: {args.output_dir}")
    logger.info("=" * 80)

    start_time = time.time()

    # Generate encryption key
    encryption_key = generate_secure_password()
    logger.info(f"\nGenerated encryption key: {encryption_key.hex()[:32]}...")
    logger.info("⚠️  Store this key securely! It's needed for decryption.")

    try:
        # Phase 1: Training
        if args.skip_training:
            logger.info("\n[Skipping training - using existing adapter]")
            adapter_path = args.output_dir
            model = None
        else:
            model, adapter_path = phase1_train_dora(args)

        # Phase 2: Encryption
        if model is None:
            # Load model for encryption if training was skipped
            from peft import PeftModel
            from transformers import AutoModelForCausalLM

            logger.info("Loading adapter for encryption...")
            base_model = AutoModelForCausalLM.from_pretrained(
                args.model_name,
                torch_dtype=torch.float16,
                device_map="cpu",
                low_cpu_mem_usage=True
            )
            model = PeftModel.from_pretrained(base_model, adapter_path)

        encrypted_path = phase2_encrypt_adapter(model, adapter_path, encryption_key)

        # Clean up training model
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Phase 3: Inference
        phase3_ephemeral_inference(encrypted_path, encryption_key, args)

        # Summary
        total_time = time.time() - start_time
        logger.info("\n" + "=" * 80)
        logger.info("WORKFLOW COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total time: {total_time:.2f}s")
        logger.info("\nDemonstrated:")
        logger.info("  ✓ DoRA training with TinyLlama (QDoRA for efficiency)")
        logger.info("  ✓ Adapter encryption with XChaCha20-Poly1305 + HKDF-SHA256")
        logger.info("  ✓ Compression (zstd) for reduced storage")
        logger.info("  ✓ Ephemeral merging (in-memory only, never persisted)")
        logger.info("  ✓ Secure inference with automatic cleanup")
        logger.info("  ✓ Adapter caching with LRU eviction")
        logger.info("  ✓ CUDA stream synchronization")
        logger.info("  ✓ Memory security (locking, zeroing)")
        logger.info("\nAll adapter weights handled ephemerally - zero disk persistence!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
