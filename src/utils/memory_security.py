"""
Secure memory management utilities for DoRA adapter weights.

Provides cryptographic-grade memory zeroing and memory locking to prevent
sensitive data from being swapped to disk or recovered through memory forensics.
"""

import torch
import ctypes
import platform
import logging
from typing import Dict, Optional
import gc

logger = logging.getLogger(__name__)


# Platform-specific memory locking
if platform.system() == 'Linux':
    libc = ctypes.CDLL('libc.so.6')
    HAVE_MLOCK = True
elif platform.system() == 'Darwin':  # macOS
    libc = ctypes.CDLL('libc.dylib')
    HAVE_MLOCK = True
elif platform.system() == 'Windows':
    kernel32 = ctypes.windll.kernel32
    HAVE_MLOCK = True
else:
    HAVE_MLOCK = False
    logger.warning(f"Memory locking not supported on {platform.system()}")


def secure_zero_tensor(tensor: torch.Tensor) -> None:
    """
    Securely zero tensor memory to prevent recovery through memory forensics.

    This implements cryptographic-grade memory clearing that overwrites the
    memory location with zeros, ensuring sensitive adapter weights cannot be
    recovered after they're freed.

    Args:
        tensor: PyTorch tensor to securely zero

    Note:
        For CUDA tensors, uses native CUDA zeroing which is secure.
        For CPU tensors, uses ctypes memset to directly overwrite memory.
    """
    if tensor is None:
        return

    try:
        if tensor.is_cuda:
            # GPU memory zeroing - CUDA handles this securely
            tensor.zero_()
            torch.cuda.synchronize(tensor.device)
        else:
            # CPU memory - use ctypes to directly overwrite memory
            if tensor.is_contiguous():
                ctypes.memset(
                    tensor.data_ptr(),
                    0,
                    tensor.numel() * tensor.element_size()
                )
            else:
                # For non-contiguous tensors, zero the contiguous copy
                tensor_contiguous = tensor.contiguous()
                ctypes.memset(
                    tensor_contiguous.data_ptr(),
                    0,
                    tensor_contiguous.numel() * tensor_contiguous.element_size()
                )
                tensor.copy_(tensor_contiguous)
                del tensor_contiguous
    except Exception as e:
        logger.error(f"Failed to securely zero tensor: {e}")
        # Fallback to standard zeroing
        tensor.zero_()


def secure_zero_dict(tensor_dict: Dict[str, torch.Tensor]) -> None:
    """
    Securely zero all tensors in a dictionary and clear the dictionary.

    Args:
        tensor_dict: Dictionary of tensors to securely zero
    """
    if tensor_dict is None:
        return

    for key in list(tensor_dict.keys()):
        tensor = tensor_dict[key]
        if isinstance(tensor, torch.Tensor):
            secure_zero_tensor(tensor)
        del tensor_dict[key]

    tensor_dict.clear()
    gc.collect()


def mlock_tensor(tensor: torch.Tensor) -> bool:
    """
    Lock tensor memory to prevent it from being swapped to disk.

    This is critical for security-sensitive adapter weights that should never
    be persisted to disk, even in swap space.

    Args:
        tensor: PyTorch tensor to lock in physical memory

    Returns:
        True if locking succeeded, False otherwise

    Note:
        Requires appropriate system permissions. May fail on some platforms
        or if memory limits are exceeded.
    """
    if not HAVE_MLOCK:
        logger.warning("Memory locking not available on this platform")
        return False

    if tensor.is_cuda:
        # CUDA memory is already pinned and not swappable
        return True

    try:
        size = tensor.numel() * tensor.element_size()
        ptr = tensor.data_ptr()

        if platform.system() in ['Linux', 'Darwin']:
            # Unix-like systems use mlock
            result = libc.mlock(ctypes.c_void_p(ptr), ctypes.c_size_t(size))
            if result == 0:
                logger.debug(f"Successfully locked {size} bytes at {hex(ptr)}")
                return True
            else:
                logger.warning(f"mlock failed with return code {result}")
                return False
        elif platform.system() == 'Windows':
            # Windows uses VirtualLock
            result = kernel32.VirtualLock(ctypes.c_void_p(ptr), ctypes.c_size_t(size))
            if result != 0:
                logger.debug(f"Successfully locked {size} bytes at {hex(ptr)}")
                return True
            else:
                logger.warning(f"VirtualLock failed")
                return False
    except Exception as e:
        logger.error(f"Failed to lock memory: {e}")
        return False


def munlock_tensor(tensor: torch.Tensor) -> bool:
    """
    Unlock previously locked tensor memory.

    Args:
        tensor: PyTorch tensor to unlock

    Returns:
        True if unlocking succeeded, False otherwise
    """
    if not HAVE_MLOCK:
        return False

    if tensor.is_cuda:
        return True

    try:
        size = tensor.numel() * tensor.element_size()
        ptr = tensor.data_ptr()

        if platform.system() in ['Linux', 'Darwin']:
            result = libc.munlock(ctypes.c_void_p(ptr), ctypes.c_size_t(size))
            return result == 0
        elif platform.system() == 'Windows':
            result = kernel32.VirtualUnlock(ctypes.c_void_p(ptr), ctypes.c_size_t(size))
            return result != 0
    except Exception as e:
        logger.error(f"Failed to unlock memory: {e}")
        return False


class SecureMemoryContext:
    """
    Context manager for secure memory handling of tensors.

    Automatically locks memory on entry and securely zeros + unlocks on exit.

    Example:
        >>> with SecureMemoryContext(sensitive_weights):
        ...     # Work with weights
        ...     output = model(input)
        ... # Weights automatically zeroed and unlocked here
    """

    def __init__(self, tensors: Dict[str, torch.Tensor], lock_memory: bool = True):
        """
        Initialize secure memory context.

        Args:
            tensors: Dictionary of tensors to manage
            lock_memory: Whether to lock memory (prevent swapping)
        """
        self.tensors = tensors
        self.lock_memory = lock_memory
        self.locked = []

    def __enter__(self):
        """Lock tensors in memory if requested."""
        if self.lock_memory:
            for name, tensor in self.tensors.items():
                if isinstance(tensor, torch.Tensor):
                    if mlock_tensor(tensor):
                        self.locked.append((name, tensor))
        return self.tensors

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Securely zero and unlock tensors."""
        # Unlock tensors
        for name, tensor in self.locked:
            munlock_tensor(tensor)

        # Securely zero all tensors
        secure_zero_dict(self.tensors)

        # Force garbage collection
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def estimate_memory_cost(tensor_dict: Dict[str, torch.Tensor]) -> int:
    """
    Estimate total memory cost of tensor dictionary in bytes.

    Args:
        tensor_dict: Dictionary of tensors

    Returns:
        Total memory in bytes
    """
    total_bytes = 0
    for tensor in tensor_dict.values():
        if isinstance(tensor, torch.Tensor):
            total_bytes += tensor.numel() * tensor.element_size()
    return total_bytes


def log_memory_stats(prefix: str = ""):
    """
    Log current memory statistics for debugging.

    Args:
        prefix: Prefix string for log message
    """
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**2
        reserved = torch.cuda.memory_reserved() / 1024**2
        logger.info(
            f"{prefix} CUDA Memory: {allocated:.2f} MB allocated, "
            f"{reserved:.2f} MB reserved"
        )
