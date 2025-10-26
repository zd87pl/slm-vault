"""
Complete RunPod serverless handler for DoRA WDVA operations.

Supports three operation modes:
1. Training: Train TinyLlama with DoRA
2. Encrypt: Encrypt trained DoRA adapter
3. Inference: Run inference with encrypted adapter

This implementation includes the complete weight application logic that was
missing from the reference implementation.
"""

import runpod
import torch
import logging
import sys
import os
from typing import Dict, Any
from pathlib import Path

# Add current directory to path for imports
# rp_handler.py is in /workspace/src/, and we need to import from same directory
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Import local modules (no 'src.' prefix since we're already in src/)
from dora_crypto import EncryptedDoRAManager, generate_secure_password
from ephemeral_inference import EphemeralDoRAInference
from utils import log_memory_stats


def handler(event):
    """
    Main handler for DoRA operations.

    Supported tasks:
    - 'training': Train DoRA adapter
    - 'encrypt': Encrypt trained adapter
    - 'inference': Run inference with encrypted adapter

    Args:
        event: RunPod event with 'input' field containing task parameters

    Returns:
        Dictionary with results or error
    """
    try:
        input_data = event['input']
        task = input_data.get('task', 'inference')

        logger.info(f"Processing task: {task}")
        log_memory_stats("Start")

        if task == 'training':
            result = train_dora(input_data)
        elif task == 'encrypt':
            result = encrypt_dora_adapter(input_data)
        elif task == 'inference':
            result = inference_with_encrypted_dora(input_data)
        else:
            return {"error": f"Unknown task: {task}"}

        log_memory_stats("End")
        logger.info(f"Task {task} completed successfully")
        return result

    except Exception as e:
        logger.error(f"Error in handler: {str(e)}", exc_info=True)
        return {"error": str(e), "traceback": str(e.__traceback__)}


def train_dora(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Train TinyLlama (or other model) with DoRA.

    Args:
        config: Training configuration with keys:
            - model_name: HuggingFace model name (default: TinyLlama/TinyLlama-1.1B-Chat-v1.0)
            - rank: DoRA rank (default: 16)
            - alpha: DoRA alpha (default: 32)
            - dropout: DoRA dropout (default: 0.05)
            - dataset: HuggingFace dataset name
            - epochs: Number of training epochs (default: 3)
            - batch_size: Per-device batch size (default: 4)
            - learning_rate: Learning rate (default: 2e-4)
            - max_samples: Maximum samples to use (optional)

    Returns:
        Dictionary with training results
    """
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
        BitsAndBytesConfig
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import load_dataset

    logger.info("Starting DoRA training...")

    # Get config values
    model_name = config.get('model_name', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0')
    rank = config.get('rank', 16)
    alpha = config.get('alpha', 32)
    dropout = config.get('dropout', 0.05)
    dataset_name = config.get('dataset', 'yahma/alpaca-cleaned')
    epochs = config.get('epochs', 3)
    batch_size = config.get('batch_size', 4)
    learning_rate = config.get('learning_rate', 2e-4)
    max_samples = config.get('max_samples', None)

    # Load model with 4-bit quantization (QDoRA)
    logger.info(f"Loading model: {model_name}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4"
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Prepare for training
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    # Configure DoRA
    logger.info(f"Configuring DoRA: rank={rank}, alpha={alpha}, dropout={dropout}")
    peft_config = LoraConfig(
        use_dora=True,  # Enable DoRA
        r=rank,
        lora_alpha=alpha,
        lora_dropout=dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM"
    )

    model = get_peft_model(model, peft_config)
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f"Trainable params: {trainable_params:,} / {total_params:,} "
               f"({100 * trainable_params / total_params:.2f}%)")

    # Load dataset
    logger.info(f"Loading dataset: {dataset_name}")
    dataset = load_dataset(dataset_name, split="train")

    if max_samples:
        dataset = dataset.select(range(min(max_samples, len(dataset))))
        logger.info(f"Using {len(dataset)} samples")

    # Tokenization function
    def tokenize_function(examples):
        # Handle different dataset formats
        if 'instruction' in examples:
            # Alpaca format
            texts = [
                f"### Instruction: {inst}\n### Response: {resp}"
                for inst, resp in zip(examples['instruction'], examples['output'])
            ]
        elif 'text' in examples:
            texts = examples['text']
        else:
            raise ValueError("Unknown dataset format")

        # Tokenize and add labels for causal LM training
        tokenized = tokenizer(texts, truncation=True, padding='max_length', max_length=512)
        # For causal LM, labels are the same as input_ids (model will shift internally)
        tokenized['labels'] = tokenized['input_ids']
        return tokenized

    # Tokenize dataset
    logger.info("Tokenizing dataset...")
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=dataset.column_names
    )

    # Training arguments
    output_dir = config.get('output_dir', '/workspace/output/dora_adapter')
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=learning_rate,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",  # Disable wandb unless configured
    )

    # Train
    logger.info("Starting training...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )

    train_result = trainer.train()

    # Save adapter
    logger.info(f"Saving adapter to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    return {
        "status": "training_complete",
        "adapter_path": output_dir,
        "trainable_params": trainable_params,
        "total_params": total_params,
        "train_loss": train_result.training_loss,
        "train_samples": len(tokenized_dataset),
    }


def encrypt_dora_adapter(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Encrypt DoRA adapter weights.

    Args:
        config: Configuration with keys:
            - adapter_path: Path to DoRA adapter
            - encryption_key: Hex-encoded encryption key (or 'generate' to create new)
            - output_path: Path for encrypted output (default: encrypted_adapter.json)
            - enable_compression: Whether to compress before encryption (default: True)

    Returns:
        Dictionary with encryption results
    """
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    logger.info("Starting adapter encryption...")

    # Get config
    adapter_path = config['adapter_path']
    key_input = config.get('encryption_key', 'generate')
    output_path = config.get('output_path', '/workspace/output/encrypted_adapter.json')
    enable_compression = config.get('enable_compression', True)

    # Generate or parse encryption key
    if key_input == 'generate':
        encryption_key = generate_secure_password()
        key_hex = encryption_key.hex()
        logger.info("Generated new encryption key")
    else:
        encryption_key = bytes.fromhex(key_input)
        key_hex = key_input

    if len(encryption_key) != 32:
        raise ValueError("Encryption key must be 32 bytes")

    # Initialize crypto manager
    manager = EncryptedDoRAManager(
        encryption_key,
        enable_compression=enable_compression
    )

    # Load model with adapter to extract weights
    logger.info(f"Loading adapter from {adapter_path}")

    # Determine base model from adapter config
    import json
    adapter_config_path = os.path.join(adapter_path, 'adapter_config.json')
    with open(adapter_config_path, 'r') as f:
        adapter_config = json.load(f)

    base_model_name = adapter_config.get('base_model_name_or_path',
                                         'TinyLlama/TinyLlama-1.1B-Chat-v1.0')

    # Load base model (CPU is fine for weight extraction)
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.float16,
        device_map="cpu",
        low_cpu_mem_usage=True
    )

    # Load PEFT adapter
    model = PeftModel.from_pretrained(base_model, adapter_path)

    # Encrypt and save
    logger.info(f"Encrypting adapter to {output_path}")
    encrypted_metadata = manager.extract_and_encrypt_dora_weights(
        model,
        output_path,
        metadata={'adapter_path': adapter_path}
    )

    # Cleanup
    del model
    del base_model
    torch.cuda.empty_cache()

    return {
        "status": "encryption_complete",
        "encrypted_path": output_path,
        "encryption_key": key_hex,  # Return key (store securely!)
        "metadata": encrypted_metadata['metadata'],
        "compressed": encrypted_metadata['metadata']['compressed'],
        "original_size_mb": encrypted_metadata['metadata']['original_size_bytes'] / 1024**2,
    }


def inference_with_encrypted_dora(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run inference with encrypted DoRA adapter.

    This includes the complete weight application logic.

    Args:
        config: Configuration with keys:
            - encrypted_adapter_path: Path to encrypted adapter
            - encryption_key: Hex-encoded encryption key
            - prompt: Input prompt
            - model_name: Base model name (default: TinyLlama/TinyLlama-1.1B-Chat-v1.0)
            - max_tokens: Max tokens to generate (default: 256)
            - temperature: Sampling temperature (default: 0.7)
            - enable_cache: Enable adapter caching (default: True)

    Returns:
        Dictionary with inference results
    """
    # Get config
    encrypted_path = config.get('encrypted_adapter_path')
    encryption_key_hex = config.get('encryption_key')
    prompt = config['prompt']
    model_name = config.get('model_name', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0')
    max_tokens = config.get('max_tokens', 256)
    temperature = config.get('temperature', 0.7)
    enable_cache = config.get('enable_cache', True)

    # Check if using encrypted adapter or basic inference
    if encrypted_path and encryption_key_hex:
        logger.info("Starting inference with encrypted adapter...")
        encryption_key = bytes.fromhex(encryption_key_hex)

        # Initialize inference engine
        inference_engine = EphemeralDoRAInference(
            base_model_name=model_name,
            encryption_key=encryption_key,
            enable_cache=enable_cache,
            load_in_4bit=True,  # Use QDoRA for memory efficiency
        )

        # Run inference
        logger.info(f"Running inference: {prompt[:50]}...")
        result = inference_engine.inference_with_encrypted_adapter(
            encrypted_path=encrypted_path,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        # Basic inference without adapter (for testing)
        logger.info("Starting basic inference (no adapter)...")
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # Load model and tokenizer
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map="auto"
        )
        tokenizer = AutoTokenizer.from_pretrained(model_name)

        # Generate
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=True
        )
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)

        result = {
            "response": text,
            "prompt": prompt,
            "metadata": {
                "model": model_name,
                "cache_hit": False,
                "mode": "basic_inference"
            }
        }

    # Log metrics (only for encrypted adapter mode)
    if encrypted_path and encryption_key_hex:
        inference_engine.log_metrics()

    return {
        "status": "inference_complete",
        "response": result['response'],
        "prompt": result['prompt'],
        "metadata": result['metadata'],
    }


# RunPod serverless start
if __name__ == "__main__":
    logger.info("Starting RunPod handler...")
    runpod.serverless.start({"handler": handler})
