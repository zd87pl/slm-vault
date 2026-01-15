"""
MLX DoRA Inference Engine

Implements DoRA (Weight-Decomposed Low-Rank Adaptation) for MLX on Apple Silicon.

DoRA Formula: W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)
Where:
- W₀: Original pretrained weights
- B, A: Low-rank matrices (from LoRA)
- m: Magnitude vector (DoRA's key innovation)
- ||·||_c: Column-wise L2 norm

This enables efficient fine-tuning with separate direction and magnitude learning.
"""

import os
import io
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple, Callable
from base64 import b64decode
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Check MLX availability
MLX_AVAILABLE = False
try:
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm import load as mlx_load, generate as mlx_generate
    from mlx_lm.models.base import BaseModelArgs
    MLX_AVAILABLE = True
except ImportError:
    logger.debug("MLX not available - MLX DoRA inference disabled")

# Check crypto availability
CRYPTO_AVAILABLE = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    CRYPTO_AVAILABLE = True
except ImportError:
    logger.debug("cryptography not available")


@dataclass
class DoRAWeights:
    """Container for DoRA adapter weights for a single layer."""
    lora_a: Any  # mx.array [r, in_features]
    lora_b: Any  # mx.array [out_features, r]
    magnitude: Optional[Any] = None  # mx.array [out_features] - DoRA specific
    scaling: float = 1.0


class MLXDoRALinear(nn.Module):
    """
    MLX Linear layer with DoRA adaptation applied.

    Implements the DoRA formula:
    W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)

    This replaces the original nn.Linear during inference.
    """

    def __init__(
        self,
        original_weight: mx.array,
        original_bias: Optional[mx.array],
        lora_a: mx.array,
        lora_b: mx.array,
        magnitude: Optional[mx.array] = None,
        scaling: float = 1.0
    ):
        super().__init__()
        self.original_weight = original_weight  # [out_features, in_features]
        self.original_bias = original_bias
        self.lora_a = lora_a  # [r, in_features]
        self.lora_b = lora_b  # [out_features, r]
        self.magnitude = magnitude  # [out_features]
        self.scaling = scaling

        # Precompute the adapted weight for efficiency
        self._adapted_weight = self._compute_adapted_weight()

    def _compute_adapted_weight(self) -> mx.array:
        """Compute W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)"""
        # BA contribution: [out_features, r] @ [r, in_features] = [out_features, in_features]
        ba = mx.matmul(self.lora_b, self.lora_a) * self.scaling

        # Combined weight: W₀ + BA
        combined = self.original_weight + ba

        if self.magnitude is not None:
            # DoRA normalization: normalize rows (output dimension)
            # ||W||_c means column-wise norm, but weights are [out, in] so we norm along axis=1
            row_norms = mx.linalg.norm(combined, axis=1, keepdims=True)
            row_norms = mx.maximum(row_norms, 1e-8)  # Prevent division by zero

            # Normalize direction
            normalized = combined / row_norms

            # Apply magnitude: m ⊙ normalized (broadcast magnitude across input dim)
            adapted = self.magnitude[:, None] * normalized
        else:
            # Standard LoRA without DoRA magnitude
            adapted = combined

        return adapted

    def __call__(self, x: mx.array) -> mx.array:
        """Forward pass with adapted weights."""
        # x: [..., in_features]
        # output: [..., out_features]
        out = mx.matmul(x, self._adapted_weight.T)

        if self.original_bias is not None:
            out = out + self.original_bias

        return out


class MLXDoRAInference:
    """
    MLX-based DoRA inference engine for Apple Silicon.

    Features:
    - Loads encrypted DoRA adapters
    - Applies DoRA weights ephemerally (in-memory only)
    - Supports multiple MLX model architectures
    - Context manager for automatic cleanup
    """

    # Target modules for DoRA (standard LLM projection layers)
    TARGET_MODULES = [
        'q_proj', 'k_proj', 'v_proj', 'o_proj',  # Attention
        'gate_proj', 'up_proj', 'down_proj',      # MLP
    ]

    # Supported MLX models
    SUPPORTED_MODELS = [
        "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
        "mlx-community/Llama-3.2-1B-Instruct-4bit",
        "mlx-community/TinyLlama-1.1B-Chat-v1.0-8bit",
        "mlx-community/SmolLM2-1.7B-Instruct-4bit",
    ]

    def __init__(
        self,
        model_path: Optional[str] = None,
        cache_dir: Optional[str] = None
    ):
        """
        Initialize MLX DoRA inference engine.

        Args:
            model_path: HuggingFace model path or local path
            cache_dir: Directory to cache models
        """
        if not MLX_AVAILABLE:
            raise RuntimeError(
                "MLX not available. Install with: pip install mlx mlx-lm"
            )

        self.model_path = model_path or self.SUPPORTED_MODELS[0]
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.cache/enclave"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.tokenizer = None
        self._original_modules: Dict[str, nn.Module] = {}
        self._adapter_applied = False

    def load_model(
        self,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Load the base MLX model.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            True if model loaded successfully
        """
        if self.model is not None:
            logger.info("Model already loaded")
            return True

        # Try models in order until one works
        models_to_try = [self.model_path] if self.model_path not in self.SUPPORTED_MODELS else self.SUPPORTED_MODELS

        for model_name in models_to_try:
            try:
                if progress_callback:
                    progress_callback(f"Loading {model_name.split('/')[-1]}...")

                logger.info(f"Loading MLX model: {model_name}")
                self.model, self.tokenizer = mlx_load(model_name)
                self.model_path = model_name

                logger.info(f"✓ Loaded MLX model: {model_name}")
                if progress_callback:
                    progress_callback("Model loaded!")
                return True

            except Exception as e:
                logger.warning(f"Failed to load {model_name}: {e}")
                continue

        logger.error("Failed to load any MLX model")
        return False

    def load_encrypted_adapter(
        self,
        adapter_path: str,
        encryption_key: bytes,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, DoRAWeights]:
        """
        Load and decrypt a DoRA adapter.

        Args:
            adapter_path: Path to encrypted adapter JSON file
            encryption_key: 32-byte master encryption key
            progress_callback: Optional progress callback

        Returns:
            Dictionary mapping layer names to DoRAWeights
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library not available")

        if progress_callback:
            progress_callback("Decrypting adapter...")

        # Load encrypted package
        with open(adapter_path, 'r') as f:
            package = json.load(f)

        # Extract components
        salt = b64decode(package['salt'])
        nonce = b64decode(package['nonce'])
        ciphertext = b64decode(package['ciphertext'])
        tag = b64decode(package['tag'])
        metadata = package.get('metadata', {})

        # Derive decryption key using HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"dora-encryption-key-v2",
        )
        decryption_key = hkdf.derive(encryption_key)

        # Decrypt
        cipher = ChaCha20Poly1305(decryption_key)
        aad = json.dumps(metadata, sort_keys=True).encode('utf-8')

        try:
            decrypted_data = cipher.decrypt(nonce, ciphertext + tag, aad)
        except Exception as e:
            raise ValueError(f"Decryption failed - wrong key or corrupted data: {e}")

        # Decompress if needed
        if metadata.get('compressed', False):
            if progress_callback:
                progress_callback("Decompressing...")
            import zstandard as zstd
            decompressor = zstd.ZstdDecompressor()
            decrypted_data = decompressor.decompress(decrypted_data)

        # Parse safetensors and convert to MLX arrays
        if progress_callback:
            progress_callback("Loading weights...")

        adapter_weights = self._parse_safetensors_to_mlx(decrypted_data)

        # Group weights by layer
        dora_weights = self._group_weights_by_layer(adapter_weights)

        logger.info(f"✓ Loaded adapter with {len(dora_weights)} DoRA layers")
        if progress_callback:
            progress_callback(f"Loaded {len(dora_weights)} layers")

        return dora_weights

    def _parse_safetensors_to_mlx(self, data: bytes) -> Dict[str, mx.array]:
        """Parse safetensors binary data to MLX arrays."""
        from safetensors import safe_open

        weights = {}
        with safe_open(io.BytesIO(data), framework="numpy") as f:
            for key in f.keys():
                # Convert numpy to MLX array
                np_tensor = f.get_tensor(key)
                weights[key] = mx.array(np_tensor)

        return weights

    def _group_weights_by_layer(
        self,
        weights: Dict[str, mx.array]
    ) -> Dict[str, DoRAWeights]:
        """Group flat weight dict into DoRAWeights per layer."""
        layers: Dict[str, Dict[str, mx.array]] = {}

        for key, tensor in weights.items():
            if key == '_type':
                continue

            # Parse key: "model.layers.0.self_attn.q_proj.lora_A" -> layer_name, weight_type
            parts = key.rsplit('.', 1)
            if len(parts) != 2:
                continue

            layer_name = parts[0]
            weight_type = parts[1]

            if layer_name not in layers:
                layers[layer_name] = {}
            layers[layer_name][weight_type] = tensor

        # Convert to DoRAWeights
        dora_weights = {}
        for layer_name, layer_weights in layers.items():
            lora_a = layer_weights.get('lora_A')
            lora_b = layer_weights.get('lora_B')

            if lora_a is None or lora_b is None:
                continue

            dora_weights[layer_name] = DoRAWeights(
                lora_a=lora_a,
                lora_b=lora_b,
                magnitude=layer_weights.get('magnitude'),
                scaling=1.0  # Could be configurable
            )

        return dora_weights

    def apply_adapter(
        self,
        dora_weights: Dict[str, DoRAWeights],
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> int:
        """
        Apply DoRA adapter weights to the model.

        Args:
            dora_weights: Dictionary of layer name -> DoRAWeights
            progress_callback: Optional progress callback

        Returns:
            Number of layers modified
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        if self._adapter_applied:
            logger.warning("Adapter already applied. Call restore_base_model() first.")
            return 0

        if progress_callback:
            progress_callback("Applying DoRA weights...")

        modified_count = 0

        # Walk the model tree and find matching layers
        for name, module in self._iter_named_modules(self.model):
            # Check if this module has adapter weights
            if name not in dora_weights:
                continue

            # Check if it's a Linear layer
            if not isinstance(module, nn.Linear):
                continue

            weights = dora_weights[name]

            # Store original for restoration
            self._original_modules[name] = module

            # Create DoRA-adapted layer
            dora_layer = MLXDoRALinear(
                original_weight=module.weight,
                original_bias=getattr(module, 'bias', None),
                lora_a=weights.lora_a,
                lora_b=weights.lora_b,
                magnitude=weights.magnitude,
                scaling=weights.scaling
            )

            # Replace in model
            self._replace_module(name, dora_layer)
            modified_count += 1

            logger.debug(f"Applied DoRA to: {name}")

        self._adapter_applied = True
        logger.info(f"✓ Applied DoRA adapter to {modified_count} layers")

        if progress_callback:
            progress_callback(f"Applied to {modified_count} layers")

        return modified_count

    def _iter_named_modules(self, module: nn.Module, prefix: str = '') -> List[Tuple[str, nn.Module]]:
        """Recursively iterate over named modules."""
        results = [(prefix, module)] if prefix else []

        for name, child in module.children().items() if hasattr(module, 'children') else []:
            full_name = f"{prefix}.{name}" if prefix else name
            results.append((full_name, child))
            results.extend(self._iter_named_modules(child, full_name))

        # Also check if module has 'layers' attribute (common in transformers)
        if hasattr(module, 'layers'):
            for i, layer in enumerate(module.layers):
                layer_name = f"{prefix}.layers.{i}" if prefix else f"layers.{i}"
                results.append((layer_name, layer))
                results.extend(self._iter_named_modules(layer, layer_name))

        # Check for model attribute
        if hasattr(module, 'model') and prefix == '':
            results.extend(self._iter_named_modules(module.model, 'model'))

        return results

    def _replace_module(self, full_name: str, new_module: nn.Module):
        """Replace a module at the given path in the model tree."""
        parts = full_name.split('.')
        parent = self.model

        # Navigate to parent
        for part in parts[:-1]:
            if part.isdigit():
                parent = parent.layers[int(part)]
            elif hasattr(parent, part):
                parent = getattr(parent, part)
            elif hasattr(parent, 'model') and hasattr(parent.model, part):
                parent = getattr(parent.model, part)
            else:
                raise AttributeError(f"Cannot find {part} in path {full_name}")

        # Set the final attribute
        final_name = parts[-1]
        setattr(parent, final_name, new_module)

    def restore_base_model(self):
        """Restore the original model weights (remove adapter)."""
        if not self._adapter_applied:
            return

        for name, original_module in self._original_modules.items():
            try:
                self._replace_module(name, original_module)
            except Exception as e:
                logger.warning(f"Failed to restore {name}: {e}")

        self._original_modules.clear()
        self._adapter_applied = False
        logger.info("✓ Restored base model")

    @contextmanager
    def adapter_context(
        self,
        adapter_path: str,
        encryption_key: bytes,
        progress_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Context manager for ephemeral adapter application.

        Usage:
            with engine.adapter_context(path, key) as layers_modified:
                response = engine.generate(prompt)
            # Adapter automatically removed after context

        Args:
            adapter_path: Path to encrypted adapter
            encryption_key: Decryption key
            progress_callback: Optional progress callback

        Yields:
            Number of layers modified
        """
        try:
            # Load and apply adapter
            dora_weights = self.load_encrypted_adapter(
                adapter_path, encryption_key, progress_callback
            )
            modified = self.apply_adapter(dora_weights, progress_callback)
            yield modified
        finally:
            # Always restore base model
            self.restore_base_model()

            # Securely clear weights from memory
            if 'dora_weights' in locals():
                for weights in dora_weights.values():
                    weights.lora_a = None
                    weights.lora_b = None
                    weights.magnitude = None

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate text using the (optionally adapted) model.

        Args:
            prompt: User prompt/question
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt

        Returns:
            Generated response text
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Format using chat template
        if hasattr(self.tokenizer, 'apply_chat_template'):
            formatted_prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            # Fallback format
            if system_prompt:
                formatted_prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{prompt}</s>\n<|assistant|>\n"
            else:
                formatted_prompt = f"<|user|>\n{prompt}</s>\n<|assistant|>\n"

        # Generate
        try:
            response = mlx_generate(
                self.model,
                self.tokenizer,
                prompt=formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                verbose=False
            )
        except TypeError:
            # Older MLX-LM API without temperature
            response = mlx_generate(
                self.model,
                self.tokenizer,
                prompt=formatted_prompt,
                max_tokens=max_tokens
            )

        return response

    def unload(self):
        """Unload model and free memory."""
        self.restore_base_model()
        self.model = None
        self.tokenizer = None
        self._original_modules.clear()
        logger.info("Model unloaded")


def is_mlx_dora_available() -> bool:
    """Check if MLX DoRA inference is available."""
    return MLX_AVAILABLE and CRYPTO_AVAILABLE


# Convenience function for quick inference
def mlx_dora_inference(
    prompt: str,
    adapter_path: str,
    encryption_key: bytes,
    model_path: Optional[str] = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None
) -> str:
    """
    Convenience function for one-shot DoRA inference.

    Args:
        prompt: User prompt
        adapter_path: Path to encrypted adapter
        encryption_key: 32-byte encryption key
        model_path: Optional model path (uses default if None)
        max_tokens: Max tokens to generate
        temperature: Sampling temperature
        system_prompt: Optional system prompt

    Returns:
        Generated response
    """
    engine = MLXDoRAInference(model_path=model_path)
    engine.load_model()

    with engine.adapter_context(adapter_path, encryption_key):
        return engine.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt
        )
