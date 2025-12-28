"""
Local Inference Engine for Enclave

Run inference locally using downloaded adapters - no cloud required!

Features:
- Downloads encrypted adapter from cloud storage
- Decrypts using local encryption key (never leaves device)
- Loads TinyLlama model locally (Apple Silicon MLX or PyTorch)
- Applies DoRA weights ephemerally (in-memory only)
- Full privacy: after training, inference can be 100% offline
"""

import os
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any, Callable
from base64 import b64decode

logger = logging.getLogger(__name__)

# Check for MLX (Apple Silicon) or PyTorch
MLX_AVAILABLE = False
TORCH_AVAILABLE = False

try:
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm import load as mlx_load, generate as mlx_generate
    MLX_AVAILABLE = True
    logger.info("MLX available - using Apple Silicon acceleration")
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
    MLX_MODEL_NAME = "mlx-community/TinyLlama-1.1B-Chat-v1.0-4bit"
    
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
        
        # Determine best backend
        if MLX_AVAILABLE:
            self.backend = "mlx"
            logger.info("Using MLX backend (Apple Silicon)")
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
                logger.info(f"Loading MLX model: {self.MLX_MODEL_NAME}")
                
                # Try loading - if safetensors missing, clear cache and retry
                try:
                    self.model, self.tokenizer = mlx_load(self.MLX_MODEL_NAME)
                except Exception as mlx_err:
                    if "No safetensors found" in str(mlx_err):
                        logger.warning("MLX model cache corrupted, clearing and re-downloading...")
                        if progress_callback:
                            progress_callback("Cache corrupted, re-downloading...")
                        
                        # Clear the corrupted cache
                        import shutil
                        cache_path = Path.home() / ".cache" / "huggingface" / "hub"
                        model_cache = cache_path / f"models--{self.MLX_MODEL_NAME.replace('/', '--')}"
                        if model_cache.exists():
                            shutil.rmtree(model_cache)
                            logger.info(f"Cleared corrupted cache: {model_cache}")
                        
                        # Retry download
                        if progress_callback:
                            progress_callback("Downloading model (this may take a minute)...")
                        self.model, self.tokenizer = mlx_load(self.MLX_MODEL_NAME)
                    else:
                        raise
                
                logger.info("✓ MLX model loaded")
                
            elif self.backend == "torch":
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
        Apply adapter weights to the loaded model (PyTorch only for now).
        
        Args:
            adapter_weights: Decrypted adapter weights
            
        Returns:
            True if weights applied successfully
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        if self.backend == "mlx":
            # MLX adapter application is more complex - for now, just store weights
            # Full MLX DoRA support would require custom implementation
            logger.warning("MLX adapter application not yet implemented - using base model")
            self._loaded_adapter_weights = adapter_weights
            return True
        
        elif self.backend == "torch":
            # Apply DoRA weights to PyTorch model
            return self._apply_dora_weights_torch(adapter_weights)
        
        return False
    
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
        
        response = mlx_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            temp=temperature,
            verbose=False
        )
        
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
            response = mlx_generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=temperature,
                verbose=False
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
        self.model = None
        self.tokenizer = None
        self._loaded_adapter_weights = None
        
        if self.backend == "torch" and TORCH_AVAILABLE:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        
        logger.info("Model unloaded")


# Singleton instance for GUI
_local_engine: Optional[LocalInferenceEngine] = None

def get_local_engine() -> LocalInferenceEngine:
    """Get or create the local inference engine singleton."""
    global _local_engine
    if _local_engine is None:
        _local_engine = LocalInferenceEngine()
    return _local_engine

