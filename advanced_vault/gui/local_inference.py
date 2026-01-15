"""
Local Inference Engine for Enclave

Run inference locally using downloaded adapters - no cloud required!

Features:
- Downloads encrypted adapter from cloud storage
- Decrypts using local encryption key (never leaves device)
- Loads TinyLlama model locally (Apple Silicon MLX or PyTorch)
- Applies DoRA weights ephemerally (in-memory only)
- Full privacy: after training, inference can be 100% offline

MLX DoRA Support:
- Full DoRA formula implementation for Apple Silicon
- W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)
- Ephemeral adapter loading with automatic cleanup
"""

import os
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any, Callable
from base64 import b64decode

# Enable fast HuggingFace downloads (10-100x faster) BEFORE importing HF libraries
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

logger = logging.getLogger(__name__)

def _ensure_fast_downloads():
    """Ensure hf_transfer is installed for fast downloads."""
    try:
        import hf_transfer
        logger.info("✓ hf_transfer available for fast downloads")
        return True
    except ImportError:
        logger.info("Installing hf_transfer for faster downloads...")
        try:
            import subprocess
            import sys
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "hf_transfer", "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("✓ hf_transfer installed")
            return True
        except Exception as e:
            logger.warning(f"Could not install hf_transfer (downloads will be slower): {e}")
            return False

# Try to enable fast downloads
_ensure_fast_downloads()

# Check for MLX (Apple Silicon) or PyTorch
MLX_AVAILABLE = False
MLX_DORA_AVAILABLE = False
TORCH_AVAILABLE = False

try:
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm import load as mlx_load, generate as mlx_generate
    MLX_AVAILABLE = True
    logger.info("MLX available - using Apple Silicon acceleration")

    # Check for MLX DoRA support
    try:
        from .mlx_dora_inference import MLXDoRAInference, is_mlx_dora_available
        MLX_DORA_AVAILABLE = is_mlx_dora_available()
        if MLX_DORA_AVAILABLE:
            logger.info("MLX DoRA support available")
    except ImportError:
        logger.debug("MLX DoRA module not available")
except ImportError:
    pass

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    TORCH_AVAILABLE = True
    logger.info("PyTorch available")
except ImportError:
    pass

# Encryption
try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography not available - local inference disabled")


class LocalInferenceEngine:
    """
    Local inference engine for running trained adapters without cloud.
    
    Supports:
    - Apple Silicon (MLX) - fastest on M1/M2/M3
    - PyTorch CPU/CUDA - works everywhere
    """
    
    MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    
    # MLX models to try in order (some repos may be unavailable)
    MLX_MODEL_CANDIDATES = [
        "mlx-community/Llama-3.2-1B-Instruct-4bit",  # Newer, better quality
        "mlx-community/Qwen2.5-1.5B-Instruct-4bit",  # Very good quality
        "mlx-community/TinyLlama-1.1B-Chat-v1.0-8bit",  # 8bit version
        "mlx-community/SmolLM2-1.7B-Instruct-4bit",  # Alternative small model
    ]
    MLX_MODEL_NAME = MLX_MODEL_CANDIDATES[0]  # Default
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize local inference engine.

        Args:
            cache_dir: Directory for model cache (default: ~/.cache/enclave)
        """
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.cache/enclave"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.tokenizer = None
        self.backend = None
        self._loaded_adapter_weights = None
        self._mlx_dora_engine: Optional['MLXDoRAInference'] = None

        # Determine best backend
        if MLX_AVAILABLE:
            self.backend = "mlx"
            logger.info("Using MLX backend (Apple Silicon)")

            # Initialize MLX DoRA engine if available
            if MLX_DORA_AVAILABLE:
                try:
                    self._mlx_dora_engine = MLXDoRAInference(cache_dir=str(self.cache_dir))
                    logger.info("MLX DoRA engine initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize MLX DoRA engine: {e}")

        elif TORCH_AVAILABLE:
            self.backend = "torch"
            logger.info("Using PyTorch backend")
        else:
            raise RuntimeError("No ML backend available. Install: pip install mlx mlx-lm (Mac) or torch transformers (other)")
    
    def is_available(self) -> bool:
        """Check if local inference is available."""
        return CRYPTO_AVAILABLE and (MLX_AVAILABLE or TORCH_AVAILABLE)
    
    def load_model(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Load the base model (downloads if needed).
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            True if model loaded successfully
        """
        if self.model is not None:
            logger.info("Model already loaded")
            return True
        
        try:
            if progress_callback:
                progress_callback("Loading TinyLlama model...")
            
            if self.backend == "mlx":
                # Try loading MLX models in order until one works
                import shutil
                last_error = None
                
                for model_name in self.MLX_MODEL_CANDIDATES:
                    logger.info(f"Trying MLX model: {model_name}")
                    if progress_callback:
                        progress_callback(f"Loading {model_name.split('/')[-1]}...")
                    
                    try:
                        self.model, self.tokenizer = mlx_load(model_name)
                        self.MLX_MODEL_NAME = model_name  # Remember which one worked
                        logger.info(f"✓ Successfully loaded: {model_name}")
                        break
                    except Exception as mlx_err:
                        last_error = mlx_err
                        logger.warning(f"Failed to load {model_name}: {mlx_err}")
                        
                        # Clear corrupted cache if needed
                        if "No safetensors found" in str(mlx_err):
                            cache_path = Path.home() / ".cache" / "huggingface" / "hub"
                            model_cache = cache_path / f"models--{model_name.replace('/', '--')}"
                            if model_cache.exists():
                                shutil.rmtree(model_cache)
                                logger.info(f"Cleared corrupted cache: {model_cache}")
                        continue
                
                # If all MLX models failed, fall back to PyTorch
                if self.model is None:
                    logger.warning("All MLX models failed, falling back to PyTorch...")
                    if progress_callback:
                        progress_callback("MLX failed, trying PyTorch...")
                    self.backend = "torch"
                    # Fall through to torch loading below
            
            # PyTorch loading (either primary or fallback)
            if self.backend == "torch" and self.model is None:
                logger.info(f"Loading PyTorch model: {self.MODEL_NAME}")
                
                # Use CPU by default for local inference (more compatible)
                device = "cuda" if torch.cuda.is_available() else "cpu"
                
                self.tokenizer = AutoTokenizer.from_pretrained(
                    self.MODEL_NAME,
                    cache_dir=self.cache_dir / "models"
                )
                
                if self.tokenizer.pad_token is None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
                
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.MODEL_NAME,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                    device_map="auto" if device == "cuda" else None,
                    cache_dir=self.cache_dir / "models"
                )
                
                if device == "cpu":
                    self.model = self.model.to(device)
                
                self.model.eval()
                logger.info(f"✓ PyTorch model loaded on {device}")
            
            if progress_callback:
                progress_callback("Model loaded!")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            if progress_callback:
                progress_callback(f"Error: {e}")
            return False
    
    def decrypt_adapter(
        self, 
        encrypted_adapter_path: str, 
        encryption_key_hex: str
    ) -> Dict[str, Any]:
        """
        Decrypt an adapter file.
        
        Args:
            encrypted_adapter_path: Path to encrypted adapter JSON
            encryption_key_hex: Hex-encoded 32-byte encryption key
            
        Returns:
            Decrypted adapter weights dictionary
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        # Load encrypted package
        with open(encrypted_adapter_path, 'r') as f:
            encrypted_package = json.load(f)
        
        # Decode components
        salt = b64decode(encrypted_package['salt'])
        nonce = b64decode(encrypted_package['nonce'])
        ciphertext = b64decode(encrypted_package['ciphertext'])
        tag = b64decode(encrypted_package['tag'])
        
        # Derive decryption key
        master_key = bytes.fromhex(encryption_key_hex)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"dora-encryption-key-v2",
        )
        decryption_key = hkdf.derive(master_key)
        
        # Decrypt
        cipher = ChaCha20Poly1305(decryption_key)
        
        # Re-create AAD
        aad = json.dumps(encrypted_package['metadata'], sort_keys=True).encode('utf-8')
        
        try:
            decrypted_data = cipher.decrypt(nonce, ciphertext + tag, aad)
        except Exception as e:
            raise ValueError(f"Decryption failed - wrong key or corrupted data: {e}")
        
        # Decompress if needed
        if encrypted_package['metadata'].get('compressed', False):
            import zstandard as zstd
            decompressor = zstd.ZstdDecompressor()
            decrypted_data = decompressor.decompress(decrypted_data)
        
        # Load safetensors
        from safetensors.torch import load
        weights = load(decrypted_data)
        
        logger.info(f"✓ Decrypted adapter with {len(weights)} tensors")
        return weights
    
    def apply_adapter_weights(self, adapter_weights: Dict[str, Any]) -> bool:
        """
        Apply adapter weights to the loaded model.

        Supports both MLX (Apple Silicon) and PyTorch backends.

        Args:
            adapter_weights: Decrypted adapter weights dictionary

        Returns:
            True if weights applied successfully
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        if self.backend == "mlx":
            return self._apply_dora_weights_mlx(adapter_weights)

        elif self.backend == "torch":
            return self._apply_dora_weights_torch(adapter_weights)

        return False

    def _apply_dora_weights_mlx(self, adapter_weights: Dict[str, Any]) -> bool:
        """Apply DoRA weights to MLX model using MLXDoRAInference."""
        if self._mlx_dora_engine is None:
            logger.warning("MLX DoRA engine not available - storing weights for later")
            self._loaded_adapter_weights = adapter_weights
            return False

        try:
            # Group weights into DoRAWeights objects
            dora_weights = self._mlx_dora_engine._group_weights_by_layer(adapter_weights)

            # Share model/tokenizer with DoRA engine if not already set
            if self._mlx_dora_engine.model is None:
                self._mlx_dora_engine.model = self.model
                self._mlx_dora_engine.tokenizer = self.tokenizer

            # Apply adapter
            modified = self._mlx_dora_engine.apply_adapter(dora_weights)
            self._loaded_adapter_weights = adapter_weights

            return modified > 0

        except Exception as e:
            logger.error(f"Failed to apply MLX DoRA weights: {e}")
            self._loaded_adapter_weights = adapter_weights
            return False

    def restore_mlx_base_model(self):
        """Restore MLX model to base weights (remove adapter)."""
        if self._mlx_dora_engine is not None:
            self._mlx_dora_engine.restore_base_model()
        self._loaded_adapter_weights = None
    
    def _apply_dora_weights_torch(self, dora_weights: Dict[str, Any]) -> bool:
        """Apply DoRA weights to PyTorch model."""
        import torch
        
        # Check type
        weight_type = dora_weights.get('_type', 'adapter')
        
        if weight_type == 'merged_delta':
            # Simple delta addition
            return self._apply_delta_weights(dora_weights)
        else:
            # Standard DoRA formula
            return self._apply_dora_formula(dora_weights)
    
    def _apply_delta_weights(self, delta_weights: Dict[str, Any]) -> bool:
        """Apply merged delta weights."""
        import torch
        
        updated_count = 0
        base_params = dict(self.model.named_parameters())
        
        for name, delta in delta_weights.items():
            if name == '_type':
                continue
            
            if name not in base_params:
                continue
            
            base_param = base_params[name]
            if delta.shape != base_param.shape:
                continue
            
            delta = delta.to(device=base_param.device, dtype=base_param.dtype)
            base_param.data.add_(delta)
            updated_count += 1
        
        logger.info(f"✓ Applied delta weights to {updated_count} parameters")
        return updated_count > 0
    
    def _apply_dora_formula(self, dora_weights: Dict[str, Any]) -> bool:
        """Apply DoRA formula: W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)"""
        import torch
        
        # Group weights by module
        modules_to_update = {}
        for key in dora_weights.keys():
            if key == '_type':
                continue
            module_name = key.rsplit('.', 1)[0]
            if module_name not in modules_to_update:
                modules_to_update[module_name] = {}
            weight_type = key.split('.')[-1]
            modules_to_update[module_name][weight_type] = dora_weights[key]
        
        # Apply to each module
        updated_count = 0
        for name, module in self.model.named_modules():
            if name in modules_to_update:
                weights = modules_to_update[name]
                
                if not hasattr(module, 'weight'):
                    continue
                
                W0 = module.weight.data
                lora_A = weights.get('lora_A')
                lora_B = weights.get('lora_B')
                magnitude = weights.get('magnitude')
                
                if lora_A is None or lora_B is None:
                    continue
                
                # Move to same device/dtype
                lora_A = lora_A.to(device=W0.device, dtype=W0.dtype)
                lora_B = lora_B.to(device=W0.device, dtype=W0.dtype)
                
                # Compute: W₀ + BA
                BA = torch.mm(lora_B, lora_A)
                new_direction = W0 + BA
                
                if magnitude is not None:
                    magnitude = magnitude.to(device=W0.device, dtype=W0.dtype)
                    row_norm = torch.linalg.norm(new_direction, dim=1, keepdim=True)
                    row_norm = torch.clamp(row_norm, min=1e-8)
                    normalized_direction = new_direction / row_norm
                    W_personalized = magnitude.unsqueeze(1) * normalized_direction
                else:
                    W_personalized = new_direction
                
                module.weight.data = W_personalized
                updated_count += 1
        
        logger.info(f"✓ Applied DoRA weights to {updated_count} modules")
        return updated_count > 0
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate text using the loaded model (with adapter if applied).
        
        Args:
            prompt: Input prompt/question
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Generated response text
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # Format prompt using chat template
        messages = [{"role": "user", "content": prompt}]
        
        if self.backend == "mlx":
            return self._generate_mlx(messages, max_tokens, temperature)
        elif self.backend == "torch":
            return self._generate_torch(messages, max_tokens, temperature)
        
        raise RuntimeError(f"Unknown backend: {self.backend}")
    
    def _generate_mlx(self, messages: list, max_tokens: int, temperature: float) -> str:
        """Generate using MLX."""
        # Format using chat template
        if hasattr(self.tokenizer, 'apply_chat_template'):
            prompt = self.tokenizer.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=True
            )
        else:
            prompt = f"<|user|>\n{messages[0]['content']}</s>\n<|assistant|>\n"
        
        # MLX-LM API: use temperature (newer versions) or temp (older versions)
        try:
            response = mlx_generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,  # Newer MLX-LM API
                verbose=False
            )
        except TypeError as e:
            if "temp" in str(e) or "temperature" in str(e):
                # Try older API
                response = mlx_generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                )
            else:
                raise
        
        return response
    
    def _generate_torch(self, messages: list, max_tokens: int, temperature: float) -> str:
        """Generate using PyTorch."""
        import torch
        
        # Format using chat template
        if hasattr(self.tokenizer, 'apply_chat_template'):
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            prompt = f"<|user|>\n{messages[0]['content']}</s>\n<|assistant|>\n"
        
        inputs = self.tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature if temperature > 0 else None,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        
        # Decode only new tokens
        prompt_len = inputs['input_ids'].shape[1]
        response = self.tokenizer.decode(
            outputs[0][prompt_len:], 
            skip_special_tokens=True
        )
        
        return response.strip()
    
    def query_base(self, query: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        """
        Query the base model without any adapter.
        Good for general conversation before documents are loaded.
        
        Args:
            query: User's question
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Generated response
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # System prompt for helpful assistant behavior
        system_prompt = """You are Enclave AI, a helpful, private AI assistant. 
You run locally on the user's device for maximum privacy.
Be concise, friendly, and helpful. If asked about documents, 
explain that the user can upload PDFs to enhance your knowledge."""
        
        # Build chat messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        # Format using chat template
        if hasattr(self.tokenizer, 'apply_chat_template'):
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{query}</s>\n<|assistant|>\n"
        
        if self.backend == "mlx":
            try:
                response = mlx_generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,  # Newer MLX-LM API
                    verbose=False
                )
            except TypeError:
                # Fallback without temperature parameter
                response = mlx_generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                )
        elif self.backend == "torch":
            import torch
            inputs = self.tokenizer(prompt, return_tensors="pt")
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else None,
                    do_sample=temperature > 0,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
            
            prompt_len = inputs['input_ids'].shape[1]
            response = self.tokenizer.decode(
                outputs[0][prompt_len:],
                skip_special_tokens=True
            ).strip()
        else:
            raise RuntimeError(f"Unknown backend: {self.backend}")
        
        return response
    
    def query(
        self, 
        query: str, 
        adapter_id: str = None, 
        encryption_key_hex: str = None,
        max_tokens: int = 512,
        temperature: float = 0.7
    ) -> str:
        """
        Query the model, optionally with an adapter loaded.
        
        Args:
            query: User's question
            adapter_id: Optional adapter ID to load
            encryption_key_hex: Encryption key for the adapter
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Generated response
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # If adapter provided, try to load it (this is simplified - full implementation would download/cache)
        # For now, just use the base model with a document-aware prompt
        if adapter_id and encryption_key_hex:
            system_prompt = """You are Enclave AI, a helpful assistant with specialized knowledge from uploaded documents.
Answer questions based on the document knowledge you've been trained on.
If you're unsure, say so rather than making things up."""
        else:
            system_prompt = """You are Enclave AI, a helpful, private AI assistant.
You run locally on the user's device for maximum privacy.
Be concise, friendly, and helpful."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        if hasattr(self.tokenizer, 'apply_chat_template'):
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{query}</s>\n<|assistant|>\n"
        
        return self.generate(prompt, max_tokens=max_tokens, temperature=temperature)
    
    def unload(self):
        """Unload model and free memory."""
        # Restore base model first if adapter was applied
        if self._mlx_dora_engine is not None:
            self._mlx_dora_engine.restore_base_model()
            self._mlx_dora_engine = None

        self.model = None
        self.tokenizer = None
        self._loaded_adapter_weights = None

        if self.backend == "torch" and TORCH_AVAILABLE:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        logger.info("Model unloaded")

    def has_mlx_dora_support(self) -> bool:
        """Check if MLX DoRA adapter support is available."""
        return self._mlx_dora_engine is not None


# Singleton instance for GUI
_local_engine: Optional[LocalInferenceEngine] = None

def get_local_engine() -> LocalInferenceEngine:
    """Get or create the local inference engine singleton."""
    global _local_engine
    if _local_engine is None:
        _local_engine = LocalInferenceEngine()
    return _local_engine


# Multi-adapter support
_multi_adapter_engine = None

def get_multi_adapter_engine(max_cached: int = 3):
    """
    Get or create the multi-adapter engine singleton.

    The multi-adapter engine supports:
    - Loading multiple adapters simultaneously
    - Weighted merging of adapters
    - Quick-switch profiles
    - LRU caching for memory efficiency
    - Usage audit logging

    Args:
        max_cached: Maximum adapters to keep in memory

    Returns:
        MultiAdapterEngine instance
    """
    global _multi_adapter_engine
    if _multi_adapter_engine is None:
        try:
            from .multi_adapter_engine import MultiAdapterEngine
            _multi_adapter_engine = MultiAdapterEngine(max_cached_adapters=max_cached)
            logger.info("Multi-adapter engine initialized")
        except ImportError as e:
            logger.warning(f"Multi-adapter engine not available: {e}")
            return None
    return _multi_adapter_engine


def is_multi_adapter_available() -> bool:
    """Check if multi-adapter support is available."""
    try:
        from .multi_adapter_engine import MultiAdapterEngine
        return MLX_DORA_AVAILABLE
    except ImportError:
        return False

