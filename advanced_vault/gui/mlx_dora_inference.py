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
import re
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple, Callable, Set
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
    MLX_AVAILABLE = True
except ImportError:
    logger.debug("MLX not available - MLX DoRA inference disabled")

    class _MLXUnavailableModule:
        """Stand-in base class so this module stays importable without MLX."""

    class _NNShim:
        Module = _MLXUnavailableModule

    nn = _NNShim()

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

    def clear(self):
        """Clear weight references for cleanup."""
        self.lora_a = None
        self.lora_b = None
        self.magnitude = None


class MLXDoRALinear(nn.Module):
    """
    MLX Linear layer with DoRA adaptation applied.

    Implements the DoRA formula:
    W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)

    This replaces the original nn.Linear during inference.
    """

    def __init__(
        self,
        original_weight: 'mx.array',
        original_bias: Optional['mx.array'],
        lora_a: 'mx.array',
        lora_b: 'mx.array',
        magnitude: Optional['mx.array'] = None,
        scaling: float = 1.0
    ):
        super().__init__()
        # Store as regular attributes (MLX modules use __setattr__)
        self._original_weight = original_weight  # [out_features, in_features]
        self._original_bias = original_bias
        self._lora_a = lora_a  # [r, in_features]
        self._lora_b = lora_b  # [out_features, r]
        self._magnitude = magnitude  # [out_features]
        self._scaling = scaling

        # Precompute the adapted weight for efficiency
        self._adapted_weight = self._compute_adapted_weight()

    def _compute_adapted_weight(self) -> 'mx.array':
        """Compute W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)"""
        # BA contribution: [out_features, r] @ [r, in_features] = [out_features, in_features]
        ba = mx.matmul(self._lora_b, self._lora_a) * self._scaling

        # Combined weight: W₀ + BA
        combined = self._original_weight + ba

        if self._magnitude is not None:
            # DoRA normalization: normalize rows (output dimension)
            # For weight matrix [out, in], we normalize along axis=1 (input features)
            row_norms = mx.linalg.norm(combined, axis=1, keepdims=True)
            row_norms = mx.maximum(row_norms, 1e-8)  # Prevent division by zero

            # Normalize direction
            normalized = combined / row_norms

            # Apply magnitude: m ⊙ normalized (broadcast magnitude across input dim)
            adapted = self._magnitude[:, None] * normalized
        else:
            # Standard LoRA without DoRA magnitude
            adapted = combined

        return adapted

    def __call__(self, x: 'mx.array') -> 'mx.array':
        """Forward pass with adapted weights."""
        # x: [..., in_features]
        # output: [..., out_features]
        out = mx.matmul(x, self._adapted_weight.T)

        if self._original_bias is not None:
            out = out + self._original_bias

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
        self._modified_paths: Set[str] = set()  # Track what we've modified
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

        # Build list of models to try: specified model first, then fallbacks
        models_to_try = [self.model_path]
        for model in self.SUPPORTED_MODELS:
            if model != self.model_path:
                models_to_try.append(model)

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

    def _parse_safetensors_to_mlx(self, data: bytes) -> Dict[str, 'mx.array']:
        """Parse safetensors binary data to MLX arrays."""
        # FIX Bug #2: Use safetensors.numpy.load() for in-memory data, not safe_open
        try:
            from safetensors.numpy import load as load_numpy
            np_weights = load_numpy(data)

            # Convert numpy arrays to MLX arrays
            weights = {}
            for key, np_tensor in np_weights.items():
                weights[key] = mx.array(np_tensor)

            return weights
        except ImportError:
            # Fallback: write to temp file and use safe_open
            import tempfile
            from safetensors import safe_open

            with tempfile.NamedTemporaryFile(suffix='.safetensors', delete=False) as f:
                f.write(data)
                temp_path = f.name

            try:
                weights = {}
                with safe_open(temp_path, framework="numpy") as f:
                    for key in f.keys():
                        np_tensor = f.get_tensor(key)
                        weights[key] = mx.array(np_tensor)
                return weights
            finally:
                os.unlink(temp_path)

    def _group_weights_by_layer(
        self,
        weights: Dict[str, 'mx.array']
    ) -> Dict[str, DoRAWeights]:
        """Group flat weight dict into DoRAWeights per layer."""
        layers: Dict[str, Dict[str, 'mx.array']] = {}

        for key, tensor in weights.items():
            if key == '_type':
                continue

            # FIX Bug #4: Handle various PEFT naming formats
            # Possible formats:
            # - "model.layers.0.self_attn.q_proj.lora_A"
            # - "base_model.model.layers.0.self_attn.q_proj.lora_A.weight"
            # - "base_model.model.layers.0.self_attn.q_proj.lora_A.default"

            # Strip common prefixes
            clean_key = key
            for prefix in ['base_model.model.', 'base_model.']:
                if clean_key.startswith(prefix):
                    clean_key = clean_key[len(prefix):]
                    break

            # Strip common suffixes
            for suffix in ['.weight', '.default']:
                if clean_key.endswith(suffix):
                    clean_key = clean_key[:-len(suffix)]
                    break

            # Parse: "model.layers.0.self_attn.q_proj.lora_A" -> layer_name, weight_type
            parts = clean_key.rsplit('.', 1)
            if len(parts) != 2:
                logger.debug(f"Skipping unparseable key: {key}")
                continue

            layer_name = parts[0]
            weight_type = parts[1]

            # Normalize weight type names
            weight_type_map = {
                'lora_A': 'lora_A',
                'lora_a': 'lora_A',
                'lora_B': 'lora_B',
                'lora_b': 'lora_B',
                'magnitude': 'magnitude',
                'lora_magnitude_vector': 'magnitude',
            }
            weight_type = weight_type_map.get(weight_type, weight_type)

            if layer_name not in layers:
                layers[layer_name] = {}
            layers[layer_name][weight_type] = tensor

        # Convert to DoRAWeights
        dora_weights = {}
        for layer_name, layer_weights in layers.items():
            lora_a = layer_weights.get('lora_A')
            lora_b = layer_weights.get('lora_B')

            if lora_a is None or lora_b is None:
                logger.debug(f"Skipping incomplete layer: {layer_name}")
                continue

            dora_weights[layer_name] = DoRAWeights(
                lora_a=lora_a,
                lora_b=lora_b,
                magnitude=layer_weights.get('magnitude'),
                scaling=1.0
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

        # FIX Bug #6: Track modifications for safe rollback
        try:
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

                # FIX Bug #5: Get bias correctly from MLX Linear
                # MLX nn.Linear stores bias as module.bias (can be None)
                original_bias = getattr(module, 'bias', None)

                # Create DoRA-adapted layer
                dora_layer = MLXDoRALinear(
                    original_weight=module.weight,
                    original_bias=original_bias,
                    lora_a=weights.lora_a,
                    lora_b=weights.lora_b,
                    magnitude=weights.magnitude,
                    scaling=weights.scaling
                )

                # Replace in model
                self._replace_module(name, dora_layer)
                self._modified_paths.add(name)
                modified_count += 1

                logger.debug(f"Applied DoRA to: {name}")

            self._adapter_applied = True
            logger.info(f"✓ Applied DoRA adapter to {modified_count} layers")

            if progress_callback:
                progress_callback(f"Applied to {modified_count} layers")

            return modified_count

        except Exception as e:
            # FIX Bug #6: Rollback on failure
            logger.error(f"Error applying adapter: {e}. Rolling back...")
            self._rollback_modifications()
            raise

    def _rollback_modifications(self):
        """Rollback any partial modifications."""
        for name in list(self._modified_paths):
            if name in self._original_modules:
                try:
                    self._replace_module(name, self._original_modules[name])
                except Exception as e:
                    logger.warning(f"Failed to rollback {name}: {e}")
        self._modified_paths.clear()
        self._original_modules.clear()
        self._adapter_applied = False

    def _iter_named_modules(
        self,
        module: nn.Module,
        prefix: str = ''
    ) -> List[Tuple[str, nn.Module]]:
        """
        Recursively iterate over named modules in MLX model.

        Returns unique (name, module) pairs for all modules in the tree.
        Uses a set to track visited modules and avoid duplicates.
        """
        results = []
        visited = set()  # Track visited module ids to avoid duplicates

        def _recurse(mod: nn.Module, pref: str):
            mod_id = id(mod)
            if mod_id in visited:
                return
            visited.add(mod_id)

            # Add current module if it has a prefix (not root)
            if pref:
                results.append((pref, mod))

            # Check for 'model' attribute (wrapper models)
            if hasattr(mod, 'model') and isinstance(mod.model, nn.Module):
                child_prefix = f"{pref}.model" if pref else "model"
                _recurse(mod.model, child_prefix)

            # Check for 'layers' list (transformer blocks)
            if hasattr(mod, 'layers') and isinstance(mod.layers, list):
                for i, layer in enumerate(mod.layers):
                    if isinstance(layer, nn.Module):
                        layer_prefix = f"{pref}.layers.{i}" if pref else f"layers.{i}"
                        _recurse(layer, layer_prefix)

            # Check common transformer attributes
            common_attrs = [
                'self_attn', 'attention', 'attn',  # Attention modules
                'mlp', 'feed_forward', 'ffn',       # MLP modules
                'q_proj', 'k_proj', 'v_proj', 'o_proj',  # Attention projections
                'gate_proj', 'up_proj', 'down_proj',     # MLP projections
                'embed_tokens', 'lm_head', 'norm',       # Other common modules
                'input_layernorm', 'post_attention_layernorm',
            ]

            for attr_name in common_attrs:
                if hasattr(mod, attr_name):
                    child = getattr(mod, attr_name)
                    if isinstance(child, nn.Module):
                        child_prefix = f"{pref}.{attr_name}" if pref else attr_name
                        _recurse(child, child_prefix)

        _recurse(module, prefix)
        return results

    def _replace_module(self, full_name: str, new_module: nn.Module):
        """
        Replace a module at the given path in the model tree.

        Handles paths like:
        - "model.layers.0.self_attn.q_proj"
        - "layers.0.mlp.gate_proj"
        """
        parts = full_name.split('.')
        parent = self.model

        # Navigate to parent of the target module
        i = 0
        while i < len(parts) - 1:
            part = parts[i]

            if part == 'layers':
                # Next part should be the index
                if i + 1 < len(parts) and parts[i + 1].isdigit():
                    idx = int(parts[i + 1])
                    if not hasattr(parent, 'layers'):
                        raise AttributeError(f"No 'layers' attribute at path position {i}")
                    parent = parent.layers[idx]
                    i += 2  # Skip both 'layers' and the index
                    continue
                else:
                    # 'layers' without numeric index - treat as attribute
                    if hasattr(parent, part):
                        parent = getattr(parent, part)
                    else:
                        raise AttributeError(f"Cannot find '{part}' in path '{full_name}'")
            elif hasattr(parent, part):
                parent = getattr(parent, part)
            else:
                raise AttributeError(f"Cannot find '{part}' in path '{full_name}'")

            i += 1

        # Set the final attribute
        final_name = parts[-1]

        if final_name.isdigit():
            # Handle list assignment (rare case where final part is an index)
            if hasattr(parent, 'layers'):
                parent.layers[int(final_name)] = new_module
            else:
                raise AttributeError(f"Cannot assign to index '{final_name}' - parent has no 'layers'")
        else:
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
        self._modified_paths.clear()
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
        dora_weights = None
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

            # FIX Bug #7: Properly clear weights
            if dora_weights is not None:
                for weights in dora_weights.values():
                    weights.clear()
                dora_weights.clear()

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
        self._modified_paths.clear()
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
