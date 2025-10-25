"""
LRU adapter cache for hot-swapping between frequently used DoRA adapters.

Enables sub-10ms adapter switching for cached adapters while maintaining
security through proper cleanup of evicted adapters.
"""

import torch
from collections import OrderedDict
from typing import Dict, Optional, Tuple, Any
import hashlib
import logging
import time
from .memory_security import secure_zero_dict, estimate_memory_cost

logger = logging.getLogger(__name__)


class AdapterCache:
    """
    LRU cache for decrypted DoRA adapters with automatic eviction.

    This cache dramatically improves adapter switching performance by keeping
    frequently-used adapters in memory. When the cache is full, least recently
    used adapters are securely zeroed and evicted.

    Features:
    - LRU eviction policy
    - Secure cleanup of evicted adapters
    - Memory usage tracking
    - Cache hit/miss metrics
    """

    def __init__(self, max_size: int = 3, max_memory_mb: Optional[float] = None):
        """
        Initialize adapter cache.

        Args:
            max_size: Maximum number of adapters to cache
            max_memory_mb: Maximum memory in MB. If None, only max_size enforced.
        """
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024 if max_memory_mb else None
        self.cache: OrderedDict[str, Tuple[Dict[str, torch.Tensor], float, int]] = OrderedDict()

        # Metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.current_memory_bytes = 0

        logger.info(f"Initialized AdapterCache with max_size={max_size}, "
                   f"max_memory_mb={max_memory_mb}")

    def _compute_hash(self, adapter_path: str, encryption_key: bytes) -> str:
        """
        Compute unique hash for adapter + key combination.

        Args:
            adapter_path: Path to encrypted adapter
            encryption_key: Encryption key

        Returns:
            SHA256 hash as hex string
        """
        hasher = hashlib.sha256()
        hasher.update(adapter_path.encode('utf-8'))
        hasher.update(encryption_key)
        return hasher.hexdigest()

    def get(self, adapter_path: str, encryption_key: bytes) -> Optional[Dict[str, torch.Tensor]]:
        """
        Get adapter from cache if available.

        Args:
            adapter_path: Path to encrypted adapter
            encryption_key: Encryption key

        Returns:
            Decrypted adapter weights if cached, None otherwise
        """
        cache_key = self._compute_hash(adapter_path, encryption_key)

        if cache_key in self.cache:
            # Cache hit - move to end (most recently used)
            weights, timestamp, size_bytes = self.cache.pop(cache_key)
            self.cache[cache_key] = (weights, time.time(), size_bytes)
            self.hits += 1

            logger.debug(f"Cache HIT for {adapter_path[:50]}... "
                        f"(hit_rate: {self.hit_rate:.2%})")
            return weights
        else:
            # Cache miss
            self.misses += 1
            logger.debug(f"Cache MISS for {adapter_path[:50]}... "
                        f"(hit_rate: {self.hit_rate:.2%})")
            return None

    def put(self, adapter_path: str, encryption_key: bytes,
            weights: Dict[str, torch.Tensor]) -> None:
        """
        Add adapter to cache, evicting LRU entries if necessary.

        Args:
            adapter_path: Path to encrypted adapter
            encryption_key: Encryption key
            weights: Decrypted adapter weights
        """
        cache_key = self._compute_hash(adapter_path, encryption_key)

        # Calculate memory cost
        size_bytes = estimate_memory_cost(weights)

        # Check if we need to evict
        while (len(self.cache) >= self.max_size or
               (self.max_memory_bytes and
                self.current_memory_bytes + size_bytes > self.max_memory_bytes)):
            if len(self.cache) == 0:
                logger.warning(f"Cannot cache adapter: size ({size_bytes / 1024**2:.2f} MB) "
                             f"exceeds max memory")
                return
            self._evict_lru()

        # Add to cache
        self.cache[cache_key] = (weights, time.time(), size_bytes)
        self.current_memory_bytes += size_bytes

        logger.debug(f"Cached adapter {adapter_path[:50]}... "
                    f"({size_bytes / 1024**2:.2f} MB, "
                    f"total: {self.current_memory_bytes / 1024**2:.2f} MB)")

    def _evict_lru(self) -> None:
        """Evict least recently used adapter from cache."""
        if not self.cache:
            return

        # Get LRU entry (first item in OrderedDict)
        cache_key, (weights, timestamp, size_bytes) = self.cache.popitem(last=False)

        # Securely zero weights before eviction
        secure_zero_dict(weights)

        self.current_memory_bytes -= size_bytes
        self.evictions += 1

        logger.debug(f"Evicted LRU adapter ({size_bytes / 1024**2:.2f} MB, "
                    f"age: {time.time() - timestamp:.1f}s)")

    def clear(self) -> None:
        """Clear all cached adapters with secure cleanup."""
        logger.info(f"Clearing adapter cache ({len(self.cache)} adapters, "
                   f"{self.current_memory_bytes / 1024**2:.2f} MB)")

        for cache_key, (weights, _, _) in self.cache.items():
            secure_zero_dict(weights)

        self.cache.clear()
        self.current_memory_bytes = 0

    def remove(self, adapter_path: str, encryption_key: bytes) -> bool:
        """
        Remove specific adapter from cache.

        Args:
            adapter_path: Path to encrypted adapter
            encryption_key: Encryption key

        Returns:
            True if adapter was cached and removed, False otherwise
        """
        cache_key = self._compute_hash(adapter_path, encryption_key)

        if cache_key in self.cache:
            weights, _, size_bytes = self.cache.pop(cache_key)
            secure_zero_dict(weights)
            self.current_memory_bytes -= size_bytes
            logger.debug(f"Removed adapter from cache: {adapter_path[:50]}...")
            return True
        return False

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        """Current number of cached adapters."""
        return len(self.cache)

    @property
    def memory_mb(self) -> float:
        """Current memory usage in MB."""
        return self.current_memory_bytes / 1024**2

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        return {
            'size': self.size,
            'max_size': self.max_size,
            'memory_mb': self.memory_mb,
            'max_memory_mb': self.max_memory_bytes / 1024**2 if self.max_memory_bytes else None,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate': self.hit_rate,
            'total_requests': self.hits + self.misses,
        }

    def log_stats(self) -> None:
        """Log cache statistics."""
        stats = self.get_stats()
        logger.info(
            f"AdapterCache Stats: {stats['size']}/{stats['max_size']} adapters, "
            f"{stats['memory_mb']:.2f} MB, "
            f"hit_rate: {stats['hit_rate']:.2%} "
            f"({stats['hits']}/{stats['total_requests']} requests), "
            f"{stats['evictions']} evictions"
        )

    def __len__(self) -> int:
        """Return number of cached adapters."""
        return len(self.cache)

    def __contains__(self, key: Tuple[str, bytes]) -> bool:
        """Check if adapter is in cache."""
        adapter_path, encryption_key = key
        cache_key = self._compute_hash(adapter_path, encryption_key)
        return cache_key in self.cache

    def __del__(self):
        """Cleanup on destruction."""
        self.clear()
