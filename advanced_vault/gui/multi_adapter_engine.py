"""
Multi-Adapter Engine for MLX DoRA Inference

Supports loading multiple adapters simultaneously with:
- Weighted merging (combine knowledge + style adapters)
- Adapter profiles (quick-switch between saved combinations)
- LRU caching (memory-efficient adapter management)
- Usage audit logging (compliance for confidential data)
- Optional context auto-detection

Example usage:
    engine = MultiAdapterEngine()
    engine.load_model()

    # Register adapters
    engine.register_adapter("company_docs", encrypted_data, key)
    engine.register_adapter("professional_tone", encrypted_data2, key2)

    # Create and activate profile
    engine.save_profile("work", {"company_docs": 0.8, "professional_tone": 0.2})
    engine.activate_profile("work")

    # Generate with merged adapters
    response = engine.generate("What's our refund policy?")
"""

import logging
import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Check for MLX availability
MLX_AVAILABLE = False
try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    pass


@dataclass
class AdapterConfig:
    """Configuration for a registered adapter."""
    name: str
    encrypted_data: bytes
    encryption_key: bytes
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterProfile:
    """Saved adapter combination for quick switching."""
    name: str
    adapters: Dict[str, float]  # adapter_name -> weight
    description: str = ""
    keywords: List[str] = field(default_factory=list)  # For auto-detection
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UsageLogEntry:
    """Audit log entry for adapter usage."""
    timestamp: datetime
    profile_name: Optional[str]
    adapter_names: List[str]
    adapter_weights: Dict[str, float]
    query_hash: str  # SHA-256 hash, not plaintext
    session_id: str


class AdapterLRUCache:
    """
    LRU cache for decrypted adapter weights.

    Keeps most recently used adapters in memory, evicts oldest
    when capacity is reached. Secure cleanup on eviction.
    """

    def __init__(self, max_size: int = 3):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size

    def get(self, name: str) -> Optional[Any]:
        """Get adapter weights, marking as recently used."""
        if name not in self._cache:
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(name)
        return self._cache[name]

    def put(self, name: str, weights: Any):
        """Cache adapter weights, evicting oldest if needed."""
        if name in self._cache:
            self._cache.move_to_end(name)
            self._cache[name] = weights
            return

        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size:
            oldest_name, oldest_weights = self._cache.popitem(last=False)
            self._secure_clear(oldest_weights)
            logger.debug(f"Evicted adapter from cache: {oldest_name}")

        self._cache[name] = weights

    def remove(self, name: str):
        """Remove adapter from cache with secure cleanup."""
        if name in self._cache:
            weights = self._cache.pop(name)
            self._secure_clear(weights)

    def clear(self):
        """Clear all cached adapters with secure cleanup."""
        for name, weights in list(self._cache.items()):
            self._secure_clear(weights)
        self._cache.clear()

    def _secure_clear(self, weights: Any):
        """Securely clear adapter weights from memory."""
        if weights is None:
            return

        # If it's a dict of DoRAWeights, clear each
        if isinstance(weights, dict):
            for key, value in weights.items():
                if hasattr(value, 'clear'):
                    value.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, name: str) -> bool:
        return name in self._cache


class MultiAdapterEngine:
    """
    Multi-adapter inference engine with profiles and caching.

    Features:
    - Register multiple encrypted adapters
    - Create profiles combining adapters with weights
    - Quick-switch between profiles
    - LRU cache for memory efficiency
    - Audit logging for compliance
    - Optional context auto-detection
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_cached_adapters: int = 3,
        session_id: Optional[str] = None
    ):
        """
        Initialize multi-adapter engine.

        Args:
            cache_dir: Directory for model cache
            max_cached_adapters: Max adapters to keep in memory
            session_id: Session identifier for audit logging
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "enclave"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Core engine (lazy loaded)
        self._base_engine = None
        self._dora_engine = None

        # Adapter management
        self._registered_adapters: Dict[str, AdapterConfig] = {}
        self._adapter_cache = AdapterLRUCache(max_size=max_cached_adapters)

        # Profiles
        self._profiles: Dict[str, AdapterProfile] = {}
        self._active_profile: Optional[str] = None
        self._active_adapters: Dict[str, float] = {}

        # Audit logging
        self._session_id = session_id or self._generate_session_id()
        self._usage_log: List[UsageLogEntry] = []
        self._max_log_entries = 1000

        # State
        self._model_loaded = False
        self._adapters_applied = False

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import os
        return hashlib.sha256(os.urandom(32)).hexdigest()[:16]

    def load_model(self, model_path: Optional[str] = None, progress_callback=None) -> bool:
        """
        Load the base model.

        Args:
            model_path: Optional custom model path
            progress_callback: Optional progress callback

        Returns:
            True if model loaded successfully
        """
        from .local_inference import LocalInferenceEngine

        if self._base_engine is None:
            self._base_engine = LocalInferenceEngine(cache_dir=str(self.cache_dir))

        success = self._base_engine.load_model(progress_callback=progress_callback)
        self._model_loaded = success

        # Get DoRA engine reference
        if success and hasattr(self._base_engine, '_mlx_dora_engine'):
            self._dora_engine = self._base_engine._mlx_dora_engine

        return success

    def register_adapter(
        self,
        name: str,
        encrypted_data: bytes,
        encryption_key: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Register an encrypted adapter for later use.

        Adapters are stored encrypted and only decrypted when activated.

        Args:
            name: Unique adapter name
            encrypted_data: Encrypted adapter safetensors
            encryption_key: Decryption key
            metadata: Optional metadata (description, version, etc.)
        """
        self._registered_adapters[name] = AdapterConfig(
            name=name,
            encrypted_data=encrypted_data,
            encryption_key=encryption_key,
            metadata=metadata or {}
        )
        logger.info(f"Registered adapter: {name}")

    def unregister_adapter(self, name: str):
        """Remove adapter registration and clear from cache."""
        if name in self._registered_adapters:
            del self._registered_adapters[name]
            self._adapter_cache.remove(name)
            logger.info(f"Unregistered adapter: {name}")

    def _load_adapter_weights(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load adapter weights (from cache or decrypt).

        Args:
            name: Adapter name

        Returns:
            Grouped DoRA weights dict, or None if failed
        """
        # Check cache first
        cached = self._adapter_cache.get(name)
        if cached is not None:
            logger.debug(f"Adapter cache hit: {name}")
            return cached

        # Need to decrypt
        if name not in self._registered_adapters:
            logger.error(f"Adapter not registered: {name}")
            return None

        config = self._registered_adapters[name]

        try:
            # Decrypt adapter using in-memory decryption
            decrypted = self._decrypt_adapter_data(
                config.encrypted_data,
                config.encryption_key
            )

            # Group into DoRA weights
            if self._dora_engine is not None:
                grouped = self._dora_engine._group_weights_by_layer(decrypted)
            else:
                grouped = decrypted

            # Cache for later
            self._adapter_cache.put(name, grouped)
            logger.info(f"Decrypted and cached adapter: {name}")

            return grouped

        except Exception as e:
            logger.error(f"Failed to load adapter {name}: {e}")
            return None

    def _decrypt_adapter_data(
        self,
        encrypted_data: bytes,
        encryption_key: bytes
    ) -> Dict[str, Any]:
        """
        Decrypt adapter data in memory.

        Args:
            encrypted_data: Raw encrypted safetensors bytes OR JSON package bytes
            encryption_key: 32-byte encryption key

        Returns:
            Dictionary of weight tensors
        """
        try:
            from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
            from cryptography.hazmat.primitives import hashes
        except ImportError:
            raise RuntimeError("cryptography library not available")

        import json
        from base64 import b64decode

        # Try to parse as JSON package first (encrypted adapter format)
        try:
            package = json.loads(encrypted_data)
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
            decrypted_data = cipher.decrypt(nonce, ciphertext + tag, aad)

            # Decompress if needed
            if metadata.get('compressed', False):
                import zstandard as zstd
                decompressor = zstd.ZstdDecompressor()
                decrypted_data = decompressor.decompress(decrypted_data)

        except (json.JSONDecodeError, KeyError):
            # Not JSON format - assume raw encrypted safetensors with simple encryption
            # Format: nonce (12 bytes) + ciphertext
            if len(encrypted_data) < 12:
                raise ValueError("Encrypted data too short")

            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]

            cipher = ChaCha20Poly1305(encryption_key)
            decrypted_data = cipher.decrypt(nonce, ciphertext, None)

        # Parse safetensors
        return self._parse_safetensors(decrypted_data)

    def _parse_safetensors(self, data: bytes) -> Dict[str, Any]:
        """Parse safetensors bytes to weight dictionary."""
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available")

        try:
            from safetensors.numpy import load as load_numpy
            import numpy as np

            np_weights = load_numpy(data)
            weights = {}
            for key, np_tensor in np_weights.items():
                weights[key] = mx.array(np_tensor)
            return weights
        except ImportError:
            # Fallback to temp file
            import tempfile
            import os
            from safetensors import safe_open

            with tempfile.NamedTemporaryFile(suffix='.safetensors', delete=False) as f:
                f.write(data)
                temp_path = f.name

            try:
                weights = {}
                with safe_open(temp_path, framework="numpy") as f:
                    for key in f.keys():
                        weights[key] = mx.array(f.get_tensor(key))
                return weights
            finally:
                os.unlink(temp_path)

    def save_profile(
        self,
        name: str,
        adapters: Dict[str, float],
        description: str = "",
        keywords: Optional[List[str]] = None
    ):
        """
        Save an adapter combination as a profile.

        Args:
            name: Profile name
            adapters: Dict of adapter_name -> weight (0.0-1.0)
            description: Optional profile description
            keywords: Keywords for auto-detection
        """
        # Validate adapters exist
        for adapter_name in adapters:
            if adapter_name not in self._registered_adapters:
                raise ValueError(f"Adapter not registered: {adapter_name}")

        # Normalize weights
        total = sum(adapters.values())
        if total > 0:
            adapters = {k: v / total for k, v in adapters.items()}

        self._profiles[name] = AdapterProfile(
            name=name,
            adapters=adapters,
            description=description,
            keywords=keywords or []
        )
        logger.info(f"Saved profile: {name} with {len(adapters)} adapters")

    def delete_profile(self, name: str):
        """Delete a saved profile."""
        if name in self._profiles:
            del self._profiles[name]
            if self._active_profile == name:
                self._active_profile = None
                self._active_adapters = {}
            logger.info(f"Deleted profile: {name}")

    def activate_profile(self, name: str) -> bool:
        """
        Activate a saved profile.

        Args:
            name: Profile name

        Returns:
            True if activated successfully
        """
        if name not in self._profiles:
            logger.error(f"Profile not found: {name}")
            return False

        profile = self._profiles[name]
        self._active_profile = name
        self._active_adapters = profile.adapters.copy()

        return self._apply_active_adapters()

    def set_adapters(self, adapters: Dict[str, float]) -> bool:
        """
        Directly set active adapters with weights.

        Args:
            adapters: Dict of adapter_name -> weight

        Returns:
            True if applied successfully
        """
        # Validate
        for name in adapters:
            if name not in self._registered_adapters:
                raise ValueError(f"Adapter not registered: {name}")

        # Normalize
        total = sum(adapters.values())
        if total > 0:
            adapters = {k: v / total for k, v in adapters.items()}

        self._active_profile = None
        self._active_adapters = adapters

        return self._apply_active_adapters()

    def set_adapter_weight(self, name: str, weight: float) -> bool:
        """
        Adjust weight for a single adapter.

        Args:
            name: Adapter name
            weight: New weight (will be normalized)

        Returns:
            True if applied successfully
        """
        if name not in self._active_adapters:
            if name not in self._registered_adapters:
                raise ValueError(f"Adapter not registered: {name}")
            self._active_adapters[name] = weight
        else:
            self._active_adapters[name] = weight

        # Re-normalize
        total = sum(self._active_adapters.values())
        if total > 0:
            self._active_adapters = {k: v / total for k, v in self._active_adapters.items()}

        self._active_profile = None  # Custom configuration
        return self._apply_active_adapters()

    def _apply_active_adapters(self) -> bool:
        """Apply currently active adapters with weighted merging."""
        if not self._model_loaded:
            logger.error("Model not loaded")
            return False

        # Restore base model first
        if self._dora_engine is not None:
            self._dora_engine.restore_base_model()
        self._adapters_applied = False

        if not self._active_adapters:
            logger.info("No active adapters")
            return True

        # Load all required adapters
        loaded_weights: Dict[str, Dict[str, Any]] = {}
        for name in self._active_adapters:
            weights = self._load_adapter_weights(name)
            if weights is None:
                logger.error(f"Failed to load adapter: {name}")
                return False
            loaded_weights[name] = weights

        # Merge adapters
        merged = self._merge_adapter_weights(loaded_weights, self._active_adapters)

        if not merged:
            logger.warning("No weights to merge")
            return False

        # Apply merged weights
        if self._dora_engine is not None:
            try:
                modified = self._dora_engine.apply_adapter(merged)
                self._adapters_applied = modified > 0
                logger.info(f"Applied merged adapters: {list(self._active_adapters.keys())} ({modified} layers)")
                return self._adapters_applied
            except Exception as e:
                logger.error(f"Failed to apply merged adapters: {e}")
                return False

        return False

    def _merge_adapter_weights(
        self,
        all_weights: Dict[str, Dict[str, Any]],
        weights_config: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Merge multiple adapter weights with specified mixing ratios.

        Args:
            all_weights: Dict of adapter_name -> grouped DoRA weights
            weights_config: Dict of adapter_name -> mixing weight

        Returns:
            Merged DoRA weights dict
        """
        if not MLX_AVAILABLE:
            logger.error("MLX not available for merging")
            return {}

        from .mlx_dora_inference import DoRAWeights

        # Collect all layer names across adapters
        all_layers = set()
        for adapter_weights in all_weights.values():
            all_layers.update(adapter_weights.keys())

        merged: Dict[str, DoRAWeights] = {}

        for layer_name in all_layers:
            lora_a_sum = None
            lora_b_sum = None
            magnitude_sum = None
            total_weight = 0.0
            scaling = 1.0
            reference_shape_a = None
            reference_shape_b = None

            for adapter_name, adapter_weights in all_weights.items():
                if layer_name not in adapter_weights:
                    continue

                w = adapter_weights[layer_name]
                alpha = weights_config.get(adapter_name, 0.0)

                if alpha <= 0:
                    continue

                # Shape validation: check if shapes are compatible
                current_shape_a = tuple(w.lora_a.shape)
                current_shape_b = tuple(w.lora_b.shape)

                if reference_shape_a is None:
                    reference_shape_a = current_shape_a
                    reference_shape_b = current_shape_b
                elif current_shape_a != reference_shape_a or current_shape_b != reference_shape_b:
                    logger.warning(
                        f"Shape mismatch in layer {layer_name}: "
                        f"expected A={reference_shape_a}, B={reference_shape_b}, "
                        f"got A={current_shape_a}, B={current_shape_b}. "
                        f"Skipping adapter {adapter_name} for this layer."
                    )
                    continue

                # Accumulate weighted contributions
                if lora_a_sum is None:
                    lora_a_sum = w.lora_a * alpha
                    lora_b_sum = w.lora_b * alpha
                    if w.magnitude is not None:
                        magnitude_sum = w.magnitude * alpha
                    scaling = w.scaling
                else:
                    lora_a_sum = lora_a_sum + w.lora_a * alpha
                    lora_b_sum = lora_b_sum + w.lora_b * alpha
                    if w.magnitude is not None:
                        if magnitude_sum is not None:
                            magnitude_sum = magnitude_sum + w.magnitude * alpha
                        else:
                            magnitude_sum = w.magnitude * alpha

                total_weight += alpha

            # Create merged weights (already weighted, no need to divide)
            if lora_a_sum is not None and total_weight > 0:
                merged[layer_name] = DoRAWeights(
                    lora_a=lora_a_sum,
                    lora_b=lora_b_sum,
                    magnitude=magnitude_sum,
                    scaling=scaling
                )

        return merged

    def deactivate_adapters(self):
        """Deactivate all adapters, restore base model."""
        if self._dora_engine is not None:
            self._dora_engine.restore_base_model()
        self._active_profile = None
        self._active_adapters = {}
        self._adapters_applied = False
        logger.info("Deactivated all adapters")

    def detect_context(self, query: str) -> Optional[str]:
        """
        Detect which profile best matches a query.

        Args:
            query: User query

        Returns:
            Profile name if match found, None otherwise
        """
        query_lower = query.lower()
        best_profile = None
        best_score = 0

        for profile_name, profile in self._profiles.items():
            if not profile.keywords:
                continue

            score = sum(1 for kw in profile.keywords if kw.lower() in query_lower)
            if score > best_score:
                best_score = score
                best_profile = profile_name

        return best_profile if best_score > 0 else None

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        auto_detect_context: bool = False,
        **kwargs
    ) -> str:
        """
        Generate text with active adapters.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            auto_detect_context: Auto-switch profile based on query
            **kwargs: Additional generation parameters

        Returns:
            Generated text
        """
        if not self._model_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Auto-detect context if enabled
        if auto_detect_context and not self._active_adapters:
            detected = self.detect_context(prompt)
            if detected:
                logger.info(f"Auto-detected context: {detected}")
                self.activate_profile(detected)

        # Log usage
        self._log_usage(prompt)

        # Generate
        return self._base_engine.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

    def chat(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        auto_detect_context: bool = True
    ) -> str:
        """
        Chat with active adapters.

        Args:
            query: User query
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            auto_detect_context: Auto-switch profile

        Returns:
            Assistant response
        """
        if not self._model_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Auto-detect context
        if auto_detect_context and not self._active_adapters:
            detected = self.detect_context(query)
            if detected:
                logger.info(f"Auto-detected context: {detected}")
                self.activate_profile(detected)

        # Log usage
        self._log_usage(query)

        # Use base engine's chat
        return self._base_engine.chat(
            query,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

    def _log_usage(self, query: str):
        """Log adapter usage for audit trail."""
        if not self._active_adapters:
            return

        # Hash query for privacy
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        entry = UsageLogEntry(
            timestamp=datetime.utcnow(),
            profile_name=self._active_profile,
            adapter_names=list(self._active_adapters.keys()),
            adapter_weights=self._active_adapters.copy(),
            query_hash=query_hash,
            session_id=self._session_id
        )

        self._usage_log.append(entry)

        # Trim log if too large
        if len(self._usage_log) > self._max_log_entries:
            self._usage_log = self._usage_log[-self._max_log_entries:]

    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get adapter usage statistics.

        Returns:
            Dict with usage stats
        """
        adapter_counts: Dict[str, int] = {}
        profile_counts: Dict[str, int] = {}

        for entry in self._usage_log:
            for name in entry.adapter_names:
                adapter_counts[name] = adapter_counts.get(name, 0) + 1
            if entry.profile_name:
                profile_counts[entry.profile_name] = profile_counts.get(entry.profile_name, 0) + 1

        return {
            "total_queries": len(self._usage_log),
            "adapter_usage": adapter_counts,
            "profile_usage": profile_counts,
            "session_id": self._session_id,
            "active_profile": self._active_profile,
            "active_adapters": self._active_adapters.copy()
        }

    def export_usage_log(self) -> List[Dict[str, Any]]:
        """Export usage log for compliance/audit."""
        return [
            {
                "timestamp": entry.timestamp.isoformat(),
                "profile": entry.profile_name,
                "adapters": entry.adapter_names,
                "weights": entry.adapter_weights,
                "query_hash": entry.query_hash,
                "session": entry.session_id
            }
            for entry in self._usage_log
        ]

    def list_adapters(self) -> List[Dict[str, Any]]:
        """List all registered adapters."""
        return [
            {
                "name": config.name,
                "cached": config.name in self._adapter_cache,
                "active": config.name in self._active_adapters,
                "weight": self._active_adapters.get(config.name, 0.0),
                "metadata": config.metadata
            }
            for config in self._registered_adapters.values()
        ]

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all saved profiles."""
        return [
            {
                "name": profile.name,
                "adapters": profile.adapters,
                "description": profile.description,
                "keywords": profile.keywords,
                "active": profile.name == self._active_profile
            }
            for profile in self._profiles.values()
        ]

    def get_active_config(self) -> Dict[str, Any]:
        """Get current active configuration."""
        return {
            "profile": self._active_profile,
            "adapters": self._active_adapters.copy(),
            "applied": self._adapters_applied,
            "model_loaded": self._model_loaded,
            "cached_adapters": len(self._adapter_cache)
        }

    def unload(self):
        """Unload model and clear all state."""
        # Clear adapters
        self.deactivate_adapters()
        self._adapter_cache.clear()

        # Unload base engine
        if self._base_engine is not None:
            self._base_engine.unload()

        self._model_loaded = False
        self._dora_engine = None
        logger.info("Multi-adapter engine unloaded")


# Convenience function
def create_multi_adapter_engine(
    cache_dir: Optional[str] = None,
    max_cached: int = 3
) -> MultiAdapterEngine:
    """Create a new multi-adapter engine instance."""
    return MultiAdapterEngine(
        cache_dir=cache_dir,
        max_cached_adapters=max_cached
    )
