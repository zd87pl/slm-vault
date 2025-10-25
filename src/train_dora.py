#!/usr/bin/env python3
"""
Standalone DoRA training script (alternative to Axolotl).

Provides direct PEFT-based training for maximum control and customization.
"""

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import load_dataset
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train DoRA adapter')

    # Model arguments
    parser.add_argument('--model-name', type=str,
                       default='TinyLlama/TinyLlama-1.1B-Chat-v1.0',
                       help='Base model name')

    # DoRA arguments
    parser.add_argument('--rank', type=int, default=16,
                       help='DoRA rank')
    parser.add_argument('--alpha', type=int, default=32,
                       help='DoRA alpha (typically 2× rank)')
    parser.add_argument('--dropout', type=float, default=0.05,
                       help='DoRA dropout')

    # Training arguments
    parser.add_argument('--dataset', type=str, default='yahma/alpaca-cleaned',
                       help='Dataset name or path')
    parser.add_argument('--max-samples', type=int, default=None,
                       help='Maximum number of samples (for quick testing)')
    parser.add_argument('--epochs', type=int, default=3,
                       help='Number of training epochs')
    parser.add_argument('--batch-size', type=int, default=4,
                       help='Per-device training batch size')
    parser.add_argument('--learning-rate', type=float, default=2e-4,
                       help='Learning rate')
    parser.add_argument('--max-length', type=int, default=512,
                       help='Maximum sequence length')

    # System arguments
    parser.add_argument('--output-dir', type=str, default='./outputs/dora-adapter',
                       help='Output directory')
    parser.add_argument('--use-4bit', action='store_true',
                       help='Use 4-bit quantization (QDoRA)')
    parser.add_argument('--use-8bit', action='store_true',
                       help='Use 8-bit quantization')
    parser.add_argument('--gradient-checkpointing', action='store_true', default=True,
                       help='Enable gradient checkpointing')

    return parser.parse_args()


def load_and_prepare_model(args):
    """
    Load base model and apply DoRA configuration.

    Args:
        args: Parsed arguments

    Returns:
        Tuple of (model, tokenizer)
    """
    logger.info(f"Loading model: {args.model_name}")

    # Configure quantization if requested
    quantization_config = None
    if args.use_4bit:
        logger.info("Using 4-bit quantization (QDoRA)")
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )
    elif args.use_8bit:
        logger.info("Using 8-bit quantization")
        quantization_config = BitsAndBytesConfig(
            load_in_8bit=True
        )

    # Load model
    load_kwargs = {
        'torch_dtype': torch.bfloat16,
        'device_map': 'auto',
        'trust_remote_code': True,
    }

    if quantization_config:
        load_kwargs['quantization_config'] = quantization_config

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        **load_kwargs
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Prepare for training
    if quantization_config:
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=args.gradient_checkpointing
        )

    # Configure DoRA
    logger.info(f"Configuring DoRA: rank={args.rank}, alpha={args.alpha}, "
               f"dropout={args.dropout}")

    peft_config = LoraConfig(
        use_dora=True,  # Enable DoRA
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM"
    )

    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    return model, tokenizer


def prepare_dataset(args, tokenizer):
    """
    Load and prepare dataset for training.

    Args:
        args: Parsed arguments
        tokenizer: Tokenizer instance

    Returns:
        Prepared dataset
    """
    logger.info(f"Loading dataset: {args.dataset}")
    dataset = load_dataset(args.dataset, split='train')

    # Limit samples if requested
    if args.max_samples:
        dataset = dataset.select(range(min(args.max_samples, len(dataset))))
        logger.info(f"Using {len(dataset)} samples")

    # Tokenization function
    def tokenize_function(examples):
        # Handle Alpaca format
        if 'instruction' in examples:
            texts = []
            for i in range(len(examples['instruction'])):
                instruction = examples['instruction'][i]
                response = examples['output'][i]
                input_text = examples.get('input', [''] * len(examples['instruction']))[i]

                if input_text:
                    text = f"### Instruction: {instruction}\n### Input: {input_text}\n### Response: {response}"
                else:
                    text = f"### Instruction: {instruction}\n### Response: {response}"

                texts.append(text)
        elif 'text' in examples:
            texts = examples['text']
        else:
            raise ValueError("Unknown dataset format")

        return tokenizer(
            texts,
            truncation=True,
            padding='max_length',
            max_length=args.max_length,
            return_tensors=None
        )

    # Tokenize dataset
    logger.info("Tokenizing dataset...")
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=dataset.column_names,
        desc="Tokenizing"
    )

    logger.info(f"Prepared {len(tokenized_dataset)} training samples")
    return tokenized_dataset


def train(args):
    """
    Main training function.

    Args:
        args: Parsed arguments
    """
    # Load model and tokenizer
    model, tokenizer = load_and_prepare_model(args)

    # Prepare dataset
    train_dataset = prepare_dataset(args, tokenizer)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=1,
        learning_rate=args.learning_rate,
        fp16=False,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",
        optim="adamw_bnb_8bit" if (args.use_4bit or args.use_8bit) else "adamw_torch",
        lr_scheduler_type="cosine",
        warmup_steps=100,
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False
    )

    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=data_collator,
    )

    # Train
    logger.info("Starting training...")
    train_result = trainer.train()

    # Save model
    logger.info(f"Saving model to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Print summary
    logger.info("=" * 80)
    logger.info("Training Complete!")
    logger.info(f"Final loss: {train_result.training_loss:.4f}")
    logger.info(f"Model saved to: {output_dir}")
    logger.info("=" * 80)

    return train_result


def main():
    """Main entry point."""
    args = parse_args()

    logger.info("=" * 80)
    logger.info("DoRA Training")
    logger.info("=" * 80)
    logger.info(f"Model: {args.model_name}")
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"DoRA config: rank={args.rank}, alpha={args.alpha}, dropout={args.dropout}")
    logger.info(f"Training: {args.epochs} epochs, batch_size={args.batch_size}, lr={args.learning_rate}")
    logger.info(f"Quantization: 4bit={args.use_4bit}, 8bit={args.use_8bit}")
    logger.info("=" * 80)

    # Train
    train(args)


if __name__ == '__main__':
    main()
