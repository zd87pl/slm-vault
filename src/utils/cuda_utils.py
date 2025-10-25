"""
CUDA stream synchronization utilities for DoRA adapter operations.

Ensures proper synchronization in multi-stream environments to prevent
race conditions during adapter loading and merging.
"""

import torch
from contextlib import contextmanager
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


def synchronize_cuda_streams(streams: Optional[List[torch.cuda.Stream]] = None) -> None:
    """
    Synchronize CUDA streams to ensure all operations complete.

    Args:
        streams: List of streams to synchronize. If None, synchronizes current stream.
    """
    if not torch.cuda.is_available():
        return

    try:
        if streams is None:
            # Synchronize current stream
            torch.cuda.current_stream().synchronize()
        else:
            # Synchronize all specified streams
            for stream in streams:
                if stream is not None:
                    stream.synchronize()

        # Also do global synchronization to be safe
        torch.cuda.synchronize()

    except Exception as e:
        logger.error(f"Failed to synchronize CUDA streams: {e}")


@contextmanager
def get_current_stream_context(device: Optional[torch.device] = None):
    """
    Context manager that captures and restores the current CUDA stream.

    This is important when temporarily switching streams for adapter operations
    and ensuring we restore the original stream afterward.

    Args:
        device: CUDA device. If None, uses current device.

    Example:
        >>> with get_current_stream_context() as stream:
        ...     # Do work on captured stream
        ...     tensor = tensor.to(stream.device)
        ... # Original stream automatically restored
    """
    if not torch.cuda.is_available():
        yield None
        return

    # Get device
    if device is None:
        if torch.cuda.current_device() >= 0:
            device = torch.device(f'cuda:{torch.cuda.current_device()}')
        else:
            device = torch.device('cuda:0')

    # Capture current stream
    current_stream = torch.cuda.current_stream(device)

    try:
        yield current_stream
    finally:
        # Restore stream and synchronize
        torch.cuda.set_stream(current_stream)
        current_stream.synchronize()


class StreamSynchronizationGuard:
    """
    Guard class to ensure proper CUDA stream synchronization.

    Use this when performing operations that must complete before proceeding,
    especially critical for DoRA adapter merging and inference.
    """

    def __init__(self, streams: Optional[List[torch.cuda.Stream]] = None):
        """
        Initialize synchronization guard.

        Args:
            streams: Streams to synchronize. If None, tracks all created streams.
        """
        self.streams = streams or []
        self.created_streams = []

    def add_stream(self, stream: torch.cuda.Stream):
        """Add a stream to track."""
        self.streams.append(stream)
        self.created_streams.append(stream)

    def synchronize(self):
        """Synchronize all tracked streams."""
        synchronize_cuda_streams(self.streams)

    def __enter__(self):
        """Enter context - start tracking streams."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - synchronize all streams."""
        self.synchronize()


def get_optimal_stream_count(device: Optional[torch.device] = None) -> int:
    """
    Get optimal number of CUDA streams for current GPU.

    Args:
        device: CUDA device to query

    Returns:
        Recommended number of streams for parallel operations
    """
    if not torch.cuda.is_available():
        return 1

    if device is None:
        device = torch.cuda.current_device()
    elif isinstance(device, torch.device):
        device = device.index

    # Get GPU compute capability
    capability = torch.cuda.get_device_capability(device)
    major, minor = capability

    # Heuristic based on compute capability
    if major >= 8:  # Ampere or newer (A100, RTX 40xx)
        return 4
    elif major >= 7:  # Volta/Turing (V100, RTX 20xx/30xx)
        return 3
    else:  # Older GPUs
        return 2


def create_stream_pool(n_streams: Optional[int] = None,
                      device: Optional[torch.device] = None) -> List[torch.cuda.Stream]:
    """
    Create a pool of CUDA streams for parallel operations.

    Args:
        n_streams: Number of streams to create. If None, uses optimal count.
        device: Device to create streams on

    Returns:
        List of CUDA streams
    """
    if not torch.cuda.is_available():
        return []

    if n_streams is None:
        n_streams = get_optimal_stream_count(device)

    if device is None:
        device = torch.cuda.current_device()
    elif isinstance(device, torch.device):
        device = device.index

    streams = []
    for _ in range(n_streams):
        stream = torch.cuda.Stream(device=device)
        streams.append(stream)

    logger.debug(f"Created {n_streams} CUDA streams on device {device}")
    return streams


@contextmanager
def async_operation_context(stream: Optional[torch.cuda.Stream] = None):
    """
    Context manager for async CUDA operations with automatic synchronization.

    Args:
        stream: Stream to use. If None, creates new stream.

    Example:
        >>> with async_operation_context() as stream:
        ...     with torch.cuda.stream(stream):
        ...         # Async operations here
        ...         result = model(input)
        ... # Automatically synchronized here
    """
    if not torch.cuda.is_available():
        yield None
        return

    created_stream = False
    if stream is None:
        stream = torch.cuda.Stream()
        created_stream = True

    try:
        yield stream
    finally:
        # Synchronize stream
        stream.synchronize()

        # Clean up if we created the stream
        if created_stream:
            del stream


def wait_for_streams(target_stream: torch.cuda.Stream,
                     wait_streams: List[torch.cuda.Stream]) -> None:
    """
    Make target stream wait for all wait_streams to complete.

    This is useful for dependency management between parallel operations.

    Args:
        target_stream: Stream that should wait
        wait_streams: Streams to wait for
    """
    if not torch.cuda.is_available():
        return

    for wait_stream in wait_streams:
        if wait_stream is not None and wait_stream != target_stream:
            # Record event on wait_stream and have target_stream wait for it
            event = torch.cuda.Event()
            event.record(wait_stream)
            target_stream.wait_event(event)
