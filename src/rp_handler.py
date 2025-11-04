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
    - 'train_and_encrypt': Train then encrypt in one job (for stateless workflow)
    - 'inference': Run inference with encrypted adapter

    Args:
        event: RunPod event with 'input' field containing task parameters
        Must include 'user_id' for user isolation

    Returns:
        Dictionary with results or error
    """
    try:
        input_data = event['input']
        task = input_data.get('task', 'inference')
        
        # SECURITY: Require user_id for all operations
        user_id = input_data.get('user_id')
        if not user_id:
            logger.error("user_id is required for all operations")
            return {"error": "user_id is required for security isolation"}

        logger.info(f"Processing task: {task} for user: {user_id}")
        log_memory_stats("Start")

        if task == 'training':
            result = train_dora(input_data, user_id)
        elif task == 'encrypt':
            result = encrypt_dora_adapter(input_data, user_id)
        elif task == 'train_and_encrypt':
            result = train_and_encrypt(input_data, user_id)
        elif task == 'inference':
            result = inference_with_encrypted_dora(input_data, user_id)
        else:
            return {"error": f"Unknown task: {task}"}

        log_memory_stats("End")
        logger.info(f"Task {task} completed successfully for user: {user_id}")
        return result

    except Exception as e:
        logger.error(f"Error in handler: {str(e)}", exc_info=True)
        return {"error": str(e), "traceback": str(e.__traceback__)}


def train_dora(config: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Train TinyLlama (or other model) with DoRA.

    Args:
        config: Training configuration with keys:
            - model_name: HuggingFace model name (default: TinyLlama/TinyLlama-1.1B-Chat-v1.0)
            - rank: DoRA rank (default: 16)
            - alpha: DoRA alpha (default: 32)
            - dropout: DoRA dropout (default: 0.05)
            - dataset: HuggingFace dataset name OR URL to encrypted dataset
            - encryption_key: Hex-encoded encryption key (required if dataset is URL)
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
    from datasets import load_dataset, Dataset
    import requests
    import json
    import base64

    logger.info("Starting DoRA training...")

    # Get config values
    model_name = config.get('model_name', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0')
    rank = config.get('rank', 16)
    alpha = config.get('alpha', 32)
    dropout = config.get('dropout', 0.05)
    dataset_source = config.get('dataset', 'yahma/alpaca-cleaned')
    encryption_key_hex = config.get('encryption_key')
    epochs = config.get('epochs', 3)
    batch_size = config.get('batch_size', 4)
    learning_rate = config.get('learning_rate', 2e-4)
    max_samples = config.get('max_samples', None)

    # Load model with 4-bit quantization (QDoRA)
    logger.info(f"Loading model: {model_name}")

    # Debug: Check CUDA availability
    logger.info(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"CUDA device count: {torch.cuda.device_count()}")
        logger.info(f"CUDA device name: {torch.cuda.get_device_name(0)}")
        logger.info(f"CUDA version: {torch.version.cuda}")

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

    # Load dataset - support both HuggingFace dataset names and encrypted URLs
    if dataset_source.startswith('http://') or dataset_source.startswith('https://'):
        # Encrypted dataset URL - download and decrypt
        logger.info(f"Downloading encrypted dataset from URL: {dataset_source[:50]}...")
        if not encryption_key_hex:
            raise ValueError("encryption_key is required for encrypted dataset URLs")
        
        # Download encrypted dataset
        try:
            response = requests.get(dataset_source, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to download encrypted dataset: {e}")
        
        try:
            encrypted_package = response.json()
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse encrypted dataset as JSON: {e}")
        
        if not isinstance(encrypted_package, dict):
            raise ValueError(f"Expected encrypted package to be a dict, got {type(encrypted_package)}")
        
        # Validate encrypted package structure
        required_fields = ['nonce', 'ciphertext', 'tag', 'algorithm']
        missing_fields = [f for f in required_fields if f not in encrypted_package]
        if missing_fields:
            raise ValueError(f"Encrypted package missing required fields: {missing_fields}")
        
        # Decrypt dataset
        logger.info("Decrypting dataset...")
        encryption_key = bytes.fromhex(encryption_key_hex)
        
        # Decode base64 fields
        try:
            nonce = base64.b64decode(encrypted_package['nonce'])
            ciphertext = base64.b64decode(encrypted_package['ciphertext'])
            tag = base64.b64decode(encrypted_package['tag'])
        except Exception as e:
            raise ValueError(f"Failed to decode encrypted package fields: {e}")
        
        # Determine decryption method based on algorithm field
        algorithm = encrypted_package.get('algorithm', 'XChaCha20-Poly1305')
        
        if algorithm == 'XChaCha20-Poly1305':
            # Use PyCryptodome (XChaCha20-Poly1305 with 24-byte nonce)
            try:
                from Crypto.Cipher import ChaCha20_Poly1305
                cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
                dataset_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            except ImportError:
                raise ValueError("PyCryptodome required for XChaCha20-Poly1305 decryption. Install with: pip install pycryptodome")
            except Exception as e:
                raise ValueError(f"Decryption failed: {e}")
        else:
            # Use cryptography library (ChaCha20-Poly1305 with 12-byte nonce)
            try:
                from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
                cipher = ChaCha20Poly1305(encryption_key)
                dataset_bytes = cipher.decrypt(nonce, ciphertext + tag, None)
            except ImportError:
                raise ValueError("cryptography library required for ChaCha20-Poly1305 decryption. Install with: pip install cryptography")
            except Exception as e:
                raise ValueError(f"Decryption failed: {e}")
        
        # Parse decrypted JSON (Q&A pairs)
        try:
            qa_pairs = json.loads(dataset_bytes.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse decrypted dataset as JSON: {e}")
        
        if not isinstance(qa_pairs, list):
            raise ValueError(f"Expected Q&A pairs to be a list, got {type(qa_pairs)}")
        
        if len(qa_pairs) == 0:
            raise ValueError("Decrypted dataset is empty")
        
        logger.info(f"Decrypted dataset with {len(qa_pairs)} Q&A pairs")
        
        # Validate format
        if not all(isinstance(pair.get('instruction'), str) and isinstance(pair.get('output'), str) for pair in qa_pairs):
            raise ValueError("Invalid Q&A pair format: missing 'instruction' or 'output' fields")
        
        # Convert to HuggingFace dataset format
        # Q&A pairs have 'instruction' and 'output', may not have 'input'
        dataset_dict = {
            'instruction': [pair.get('instruction', '') for pair in qa_pairs],
            'input': [pair.get('input', '') for pair in qa_pairs],  # Empty string if not present
            'output': [pair.get('output', '') for pair in qa_pairs]
        }
        
        # Create dataset and verify columns
        dataset = Dataset.from_dict(dataset_dict)
        logger.info(f"Created dataset with columns: {dataset.column_names}")
        logger.info(f"Dataset sample: {dataset[0] if len(dataset) > 0 else 'empty'}")
        
        # Securely clear decrypted data from memory
        del qa_pairs, dataset_bytes, encryption_key
        
    else:
        # HuggingFace dataset name
        logger.info(f"Loading HuggingFace dataset: {dataset_source}")
        dataset = load_dataset(dataset_source, split="train")

    if max_samples:
        dataset = dataset.select(range(min(max_samples, len(dataset))))
        logger.info(f"Using {len(dataset)} samples")

    # Tokenization function
    def tokenize_function(examples):
        # Handle different dataset formats
        # When batched=True, examples is a dict with lists as values
        logger.debug(f"Tokenizing batch with keys: {list(examples.keys())}")
        
        if 'instruction' in examples and 'output' in examples:
            # Alpaca format
            instructions = examples['instruction']
            outputs = examples['output']
            inputs = examples.get('input', [''] * len(instructions))
            
            texts = []
            for inst, inp, resp in zip(instructions, inputs, outputs):
                if inp:
                    text = f"### Instruction: {inst}\n### Input: {inp}\n### Response: {resp}"
                else:
                    text = f"### Instruction: {inst}\n### Response: {resp}"
                texts.append(text)
        elif 'text' in examples:
            texts = examples['text']
        else:
            raise ValueError(f"Unknown dataset format. Available keys: {list(examples.keys())}")

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

    # Training arguments - use user-specific storage path
    adapter_id = config.get('adapter_id', 'default')
    output_dir = config.get('output_dir', f'/workspace/adapters/{user_id}/{adapter_id}/')
    # Ensure directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Using user-specific storage path: {output_dir}")
    
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
        "user_id": user_id,
        "adapter_path": output_dir,
        "trainable_params": trainable_params,
        "total_params": total_params,
        "train_loss": train_result.training_loss,
        "train_samples": len(tokenized_dataset),
    }


def encrypt_dora_adapter(config: Dict[str, Any], user_id: str) -> Dict[str, Any]:
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
    adapter_id = config.get('adapter_id', 'default')
    # Use user-specific storage path
    output_path = config.get('output_path', f'/workspace/encrypted/{user_id}/{adapter_id}.json')
    # Ensure directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    enable_compression = config.get('enable_compression', True)
    
    logger.info(f"Using user-specific encrypted storage path: {output_path}")

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
        "user_id": user_id,
        "encrypted_path": output_path,
        "encryption_key": key_hex,  # Return key (store securely!)
        "metadata": encrypted_metadata['metadata'],
        "compressed": encrypted_metadata['metadata']['compressed'],
        "original_size_mb": encrypted_metadata['metadata']['original_size_bytes'] / 1024**2,
    }


def train_and_encrypt(config: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Train DoRA adapter and encrypt it in one job (for stateless workflow).

    This combines training and encryption to avoid persistence between jobs.

    Args:
        config: Configuration with keys from both train_dora and encrypt_dora_adapter

    Returns:
        Dictionary with both training and encryption results
    """
    logger.info("Starting combined train + encrypt workflow...")

    # Step 1: Train adapter
    logger.info("Step 1/2: Training DoRA adapter...")
    training_result = train_dora(config, user_id)

    adapter_path = training_result['adapter_path']
    logger.info(f"Training complete. Adapter at: {adapter_path}")

    # Step 2: Encrypt adapter
    logger.info("Step 2/2: Encrypting adapter...")
    encryption_config = {
        'adapter_path': adapter_path,
        'encryption_key': config.get('encryption_key', 'generate'),
        'adapter_id': config.get('adapter_id', 'default'),
        'output_path': config.get('encrypted_output_path', f'/workspace/encrypted/{user_id}/{config.get("adapter_id", "default")}.json'),
        'enable_compression': config.get('enable_compression', True)
    }

    encryption_result = encrypt_dora_adapter(encryption_config, user_id)

    # Combine results
    return {
        "status": "train_and_encrypt_complete",
        "user_id": user_id,
        "training": {
            "adapter_path": training_result['adapter_path'],
            "trainable_params": training_result['trainable_params'],
            "total_params": training_result['total_params'],
            "train_loss": training_result.get('train_loss'),
            "train_samples": training_result['train_samples']
        },
        "encryption": {
            "encrypted_path": encryption_result['encrypted_path'],
            "encryption_key": encryption_result['encryption_key'],
            "original_size_mb": encryption_result['original_size_mb'],
            "compressed": encryption_result['compressed']
        }
    }


def inference_with_encrypted_dora(config: Dict[str, Any], user_id: str) -> Dict[str, Any]:
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
    adapter_id = config.get('adapter_id')  # For ownership verification
    model_name = config.get('model_name', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0')
    max_tokens = config.get('max_tokens', 256)
    temperature = config.get('temperature', 0.7)
    enable_cache = config.get('enable_cache', True)
    
    # SECURITY: Verify adapter ownership before decryption
    # Note: In production, this would call backend API to verify ownership
    # For now, we log the verification requirement
    if adapter_id:
        logger.info(f"Verifying ownership: adapter_id={adapter_id}, user_id={user_id}")
        # TODO: In production, call backend API: POST /api/adapters/{adapter_id}/verify
        # For now, we trust the user_id comes from authenticated request

    # Check if using encrypted adapter or basic inference
    if encrypted_path and encryption_key_hex:
        logger.info("Starting inference with encrypted adapter...")
        encryption_key = bytes.fromhex(encryption_key_hex)

        # Initialize inference engine
        # CRITICAL: Disable cache temporarily to prevent wrong adapter usage
        # Cache may return adapter from different document if path/key hash collides
        logger.warning("Adapter cache DISABLED to prevent wrong adapter usage - investigating cache key collision")
        inference_engine = EphemeralDoRAInference(
            base_model_name=model_name,
            encryption_key=encryption_key,
            enable_cache=False,  # DISABLED: cache may return wrong adapter
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
        "user_id": user_id,
        "response": result['response'],
        "prompt": result['prompt'],
        "metadata": result['metadata'],
    }


# RunPod serverless start
if __name__ == "__main__":
    logger.info("Starting RunPod handler...")
    runpod.serverless.start({"handler": handler})
