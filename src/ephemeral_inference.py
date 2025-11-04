"""
Ephemeral DoRA inference engine with security-first design.

Features:
- In-memory only adapter loading (never persists to disk)
- Proper CUDA stream synchronization
- Complete state restoration after inference
- Adapter caching with LRU eviction
- Secure memory cleanup
- Forward/backward hook preservation
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Dict, Optional, Tuple, List, Any
import logging
from contextlib import contextmanager
import copy

# Support both import styles (RunPod vs local examples)
try:
    from src.dora_crypto import EncryptedDoRAManager
    from src.utils import (
        AdapterCache,
        secure_zero_dict,
        SecureMemoryContext,
        synchronize_cuda_streams,
        get_current_stream_context,
        log_memory_stats
    )
except ImportError:
    from dora_crypto import EncryptedDoRAManager
    from utils import (
        AdapterCache,
        secure_zero_dict,
        SecureMemoryContext,
        synchronize_cuda_streams,
        get_current_stream_context,
        log_memory_stats
    )

logger = logging.getLogger(__name__)


class EphemeralDoRAInference:
    """
    Memory-efficient DoRA inference with automatic cleanup and caching.

    This engine provides secure, high-performance inference with encrypted DoRA
    adapters. Key features:

    1. **Security**: Adapters never touch disk, aggressive memory cleanup
    2. **Performance**: LRU caching for hot adapters, <5ms switching
    3. **Correctness**: Proper state restoration, CUDA synchronization
    4. **Observability**: Comprehensive metrics and logging
    """

    def __init__(self,
                 base_model_name: str,
                 encryption_key: bytes,
                 device: Optional[str] = None,
                 torch_dtype: Optional[torch.dtype] = None,
                 enable_cache: bool = True,
                 cache_size: int = 3,
                 load_in_4bit: bool = False,
                 load_in_8bit: bool = False):
        """
        Initialize ephemeral inference engine.

        Args:
            base_model_name: HuggingFace model name or path
            encryption_key: 32-byte encryption key for adapters
            device: Device to use ('cuda', 'cpu', or None for auto)
            torch_dtype: Data type for model weights
            enable_cache: Whether to enable adapter caching
            cache_size: Maximum number of adapters to cache
            load_in_4bit: Use 4-bit quantization (QDoRA)
            load_in_8bit: Use 8-bit quantization
        """
        self.base_model_name = base_model_name
        self.encryption_key = encryption_key
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.torch_dtype = torch_dtype or torch.bfloat16

        # Initialize crypto manager
        self.crypto_manager = EncryptedDoRAManager(encryption_key)

        # Initialize adapter cache
        self.cache = AdapterCache(max_size=cache_size) if enable_cache else None

        # Load base model
        logger.info(f"Loading base model: {base_model_name}")
        self.base_model = self._load_base_model(load_in_4bit, load_in_8bit)
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name)

        # Ensure tokenizer has pad token
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Metrics
        self.inference_count = 0
        self.adapter_switches = 0
        self.cache_hits = 0
        self.cache_misses = 0

        logger.info(f"Initialized EphemeralDoRAInference (cache: {enable_cache}, "
                   f"device: {self.device})")

    def _load_base_model(self, load_in_4bit: bool, load_in_8bit: bool):
        """Load base model with optional quantization."""
        load_kwargs = {
            'torch_dtype': self.torch_dtype,
            'device_map': 'auto' if self.device == 'cuda' else self.device,
        }

        if load_in_4bit:
            from transformers import BitsAndBytesConfig
            load_kwargs['quantization_config'] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
            logger.info("Using 4-bit quantization (QDoRA)")
        elif load_in_8bit:
            from transformers import BitsAndBytesConfig
            load_kwargs['quantization_config'] = BitsAndBytesConfig(
                load_in_8bit=True
            )
            logger.info("Using 8-bit quantization")

        model = AutoModelForCausalLM.from_pretrained(
            self.base_model_name,
            **load_kwargs
        )

        model.eval()
        return model

    def inference_with_encrypted_adapter(self,
                                        encrypted_path: str,
                                        prompt: str,
                                        max_tokens: int = 256,
                                        temperature: float = 0.7,
                                        do_sample: bool = True,
                                        **generation_kwargs) -> Dict[str, Any]:
        """
        Run inference with encrypted DoRA adapter.

        Process:
        1. Check cache or decrypt adapter
        2. Capture current model state
        3. Apply DoRA weights ephemerally
        4. Run inference with proper CUDA sync
        5. Restore original state
        6. Cleanup adapter weights

        Args:
            encrypted_path: Path to encrypted adapter
            prompt: Input prompt for generation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            do_sample: Whether to use sampling
            **generation_kwargs: Additional generation arguments

        Returns:
            Dictionary with response and metadata
        """
        import time
        start_time = time.time()

        # Check cache first
        if self.cache:
            cached_weights = self.cache.get(encrypted_path, self.encryption_key)
            if cached_weights is not None:
                decrypted_weights = cached_weights
                self.cache_hits += 1
                cache_hit = True
                logger.debug("Using cached adapter")
            else:
                decrypted_weights = None
                self.cache_misses += 1
                cache_hit = False
        else:
            decrypted_weights = None
            cache_hit = False

        # Decrypt if not cached
        decrypt_time = 0
        if decrypted_weights is None:
            decrypt_start = time.time()
            decrypted_weights = self.crypto_manager.decrypt_and_load_dora_weights(
                encrypted_path,
                lock_memory=True
            )
            decrypt_time = time.time() - decrypt_start

            # Add to cache
            if self.cache:
                self.cache.put(encrypted_path, self.encryption_key, decrypted_weights)

        # Use ephemeral adapter context
        try:
            with self._ephemeral_adapter_context(decrypted_weights) as model:
                # Run inference
                inference_start = time.time()
                response = self._generate(
                    model,
                    prompt,
                    max_tokens,
                    temperature,
                    do_sample,
                    **generation_kwargs
                )
                inference_time = time.time() - inference_start

        finally:
            # If we decrypted fresh (not from cache), clean up
            if not cache_hit and not self.cache:
                secure_zero_dict(decrypted_weights)

        total_time = time.time() - start_time
        self.inference_count += 1
        self.adapter_switches += 1

        # Return response with metadata
        return {
            'response': response,
            'prompt': prompt,
            'metadata': {
                'inference_count': self.inference_count,
                'adapter_switches': self.adapter_switches,
                'cache_hit': cache_hit,
                'timing': {
                    'total_ms': total_time * 1000,
                    'decrypt_ms': decrypt_time * 1000,
                    'inference_ms': inference_time * 1000,
                },
                'cache_stats': self.cache.get_stats() if self.cache else None,
            }
        }

    @contextmanager
    def _ephemeral_adapter_context(self, dora_weights: Dict[str, torch.Tensor]):
        """
        Context manager for ephemeral DoRA adapter loading.

        This ensures:
        1. Original state is captured with hooks
        2. DoRA weights are applied
        3. Original state is fully restored
        4. CUDA streams are synchronized
        """
        # Capture original state
        original_state = self._capture_model_state()

        try:
            # Apply DoRA weights ephemerally
            with get_current_stream_context():
                self._apply_dora_weights_ephemeral(dora_weights)
                synchronize_cuda_streams()

            yield self.base_model

        finally:
            # Restore original state
            with get_current_stream_context():
                self._restore_model_state(original_state)
                synchronize_cuda_streams()

            # Cleanup
            del original_state
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _capture_model_state(self) -> Dict[str, Any]:
        """
        Capture complete model state including hooks and parameters.

        Returns:
            Dictionary with state data
        """
        state = {
            'parameters': {},
            'buffers': {},
            'hooks': {},
        }

        # Capture parameters
        for name, param in self.base_model.named_parameters():
            state['parameters'][name] = param.data.clone()

        # Capture buffers
        for name, buffer in self.base_model.named_buffers():
            state['buffers'][name] = buffer.clone()

        # Capture hooks (important for gradient checkpointing, etc.)
        for name, module in self.base_model.named_modules():
            if hasattr(module, '_forward_hooks') and module._forward_hooks:
                state['hooks'][f'{name}._forward_hooks'] = copy.copy(module._forward_hooks)
            if hasattr(module, '_backward_hooks') and module._backward_hooks:
                state['hooks'][f'{name}._backward_hooks'] = copy.copy(module._backward_hooks)

        return state

    def _restore_model_state(self, state: Dict[str, Any]):
        """
        Restore model to captured state.

        Args:
            state: State dictionary from _capture_model_state
        """
        # Restore parameters
        for name, param in self.base_model.named_parameters():
            if name in state['parameters']:
                param.data.copy_(state['parameters'][name])

        # Restore buffers
        for name, buffer in self.base_model.named_buffers():
            if name in state['buffers']:
                buffer.copy_(state['buffers'][name])

        # Restore hooks
        for name, module in self.base_model.named_modules():
            forward_key = f'{name}._forward_hooks'
            if forward_key in state['hooks']:
                module._forward_hooks = state['hooks'][forward_key]

            backward_key = f'{name}._backward_hooks'
            if backward_key in state['hooks']:
                module._backward_hooks = state['hooks'][backward_key]

    def _apply_dora_weights_ephemeral(self, dora_weights: Dict[str, torch.Tensor]):
        """
        Apply DoRA weights using magnitude-direction decomposition formula.

        DoRA formula: W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)

        Where:
        - m = magnitude vector
        - W₀ = base weight matrix
        - BA = low-rank adaptation (lora_B @ lora_A)
        - ||·||_c = column-wise L2 norm
        - ⊙ = element-wise multiplication

        Args:
            dora_weights: Dictionary of DoRA tensors
        """
        # Group weights by module
        modules_to_update = {}
        for key in dora_weights.keys():
            module_name = key.rsplit('.', 1)[0]
            if module_name not in modules_to_update:
                modules_to_update[module_name] = {}
            weight_type = key.split('.')[-1]
            modules_to_update[module_name][weight_type] = dora_weights[key]

        # Apply DoRA formula to each module
        updated_count = 0
        for name, module in self.base_model.named_modules():
            if name in modules_to_update:
                weights = modules_to_update[name]

                # Get base weights
                if not hasattr(module, 'weight'):
                    logger.warning(f"Module {name} has no weight parameter")
                    continue

                W0 = module.weight.data

                # Get DoRA components
                lora_A = weights.get('lora_A')
                lora_B = weights.get('lora_B')
                magnitude = weights.get('magnitude')

                if lora_A is None or lora_B is None:
                    logger.warning(f"Missing LoRA weights for {name}")
                    continue

                # Move to same device and dtype as base weights
                lora_A = lora_A.to(device=W0.device, dtype=W0.dtype)
                lora_B = lora_B.to(device=W0.device, dtype=W0.dtype)

                # Compute directional update: W₀ + BA
                BA = torch.mm(lora_B, lora_A)
                new_direction = W0 + BA

                if magnitude is not None:
                    # Full DoRA: apply magnitude scaling
                    magnitude = magnitude.to(device=W0.device, dtype=W0.dtype)

                    # Row-wise normalization (normalize each output feature)
                    row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
                    row_norm = torch.clamp(row_norm, min=1e-8)  # Avoid division by zero
                    normalized_direction = new_direction / row_norm

                    # Apply magnitude scaling: m ⊙ normalized_direction (scale each row)
                    W_personalized = magnitude.unsqueeze(1) * normalized_direction
                else:
                    # LoRA fallback (no magnitude)
                    W_personalized = new_direction

                # Apply to module (ephemeral - in memory only)
                module.weight.data = W_personalized
                updated_count += 1

        logger.info(f"Applied DoRA weights to {updated_count} modules (adapter is active)")

    def _generate(self,
                 model,
                 prompt: str,
                 max_tokens: int,
                 temperature: float,
                 do_sample: bool,
                 **kwargs) -> str:
        """
        Generate text using model.

        Args:
            model: Model to use for generation
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            do_sample: Whether to sample
            **kwargs: Additional generation arguments

        Returns:
            Generated text
        """
        # Format prompt to match training format (Alpaca format used during training)
        # Training uses: "### Instruction: {inst}\n### Response: {resp}"
        # So inference MUST use: "### Instruction: {prompt}\n### Response:"
        # CRITICAL: Do NOT use chat template - model was trained on Alpaca format during fine-tuning
        if not prompt.startswith("### Instruction:"):
            formatted_prompt = f"### Instruction: {prompt}\n### Response:"
        else:
            formatted_prompt = prompt
        
        # Log formatted prompt for debugging
        logger.info(f"Formatted prompt (Alpaca format): {formatted_prompt[:200]}...")

        # Tokenize input WITHOUT chat template
        # Important: We must NOT use chat template because the model was fine-tuned on Alpaca format
        # Using chat template would change the tokenization and break the adapter's effectiveness
        inputs = self.tokenizer(formatted_prompt, return_tensors="pt", padding=True, add_special_tokens=True)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        # Generate with adapter weights applied
        logger.debug(f"Generating with max_tokens={max_tokens}, temperature={temperature}, do_sample={do_sample}")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=do_sample,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                **kwargs
            )

        # Decode full output
        full_response = self.tokenizer.decode(outputs[0], skip_special_tokens=False)
        
        # Remove the formatted prompt from the beginning
        # Try exact match first
        if full_response.startswith(formatted_prompt):
            response = full_response[len(formatted_prompt):].strip()
        else:
            # Try stripping tokenized prompt (sometimes tokenization adds spaces/special tokens)
            # Find where the prompt ends in the decoded response
            prompt_tokens = self.tokenizer.encode(formatted_prompt, add_special_tokens=False)
            response_tokens = outputs[0].tolist()
            
            # Find prompt tokens in response and extract everything after
            if len(prompt_tokens) > 0 and len(response_tokens) > len(prompt_tokens):
                # Check if prompt tokens match at the start
                if response_tokens[:len(prompt_tokens)] == prompt_tokens:
                    response_only_tokens = response_tokens[len(prompt_tokens):]
                    response = self.tokenizer.decode(response_only_tokens, skip_special_tokens=True).strip()
                else:
                    # Fallback: decode everything and try to extract response
                    response = full_response.strip()
                    # Try to find "### Response:" marker
                    if "### Response:" in response:
                        response = response.split("### Response:")[-1].strip()
            else:
                # Fallback: just return full response if prompt doesn't match
                response = full_response.strip()
        
        logger.debug(f"Generated response length: {len(response)} chars")
        return response

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get inference metrics.

        Returns:
            Dictionary with metrics
        """
        metrics = {
            'inference_count': self.inference_count,
            'adapter_switches': self.adapter_switches,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': self.cache_hits / max(self.cache_hits + self.cache_misses, 1),
        }

        if self.cache:
            metrics['cache_stats'] = self.cache.get_stats()

        return metrics

    def log_metrics(self):
        """Log current metrics."""
        metrics = self.get_metrics()
        logger.info(f"Inference Metrics: {self.inference_count} inferences, "
                   f"{self.adapter_switches} adapter switches, "
                   f"cache hit rate: {metrics['cache_hit_rate']:.2%}")

        if self.cache:
            self.cache.log_stats()

    def clear_cache(self):
        """Clear adapter cache."""
        if self.cache:
            self.cache.clear()
            logger.info("Adapter cache cleared")

    def __del__(self):
        """Cleanup on destruction."""
        if hasattr(self, 'cache') and self.cache:
            self.cache.clear()
