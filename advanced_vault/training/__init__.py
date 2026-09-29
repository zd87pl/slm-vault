"""
Training module for Enclave.

Provides local RAG indexing, embeddings, and MLX-based adapter training.

Performance optimizations (Phases 1-3):
- HNSW index for 10-30x faster vector search
- E5-small embeddings (+15% quality vs MiniLM)
- Persistent embedding cache (2-9x speedup)
"""

from .embeddings import EmbeddingEngine, EmbeddingCache
from .rag_index import RAGIndex, Document, Chunk, RetrievalResult
from .vector_index import VectorIndex, HNSWIndex, BruteForceIndex, create_vector_index
from .mlx_trainer import MLXTrainer, TrainingExample, TrainingResult, check_mlx_available, get_recommended_model

try:
    from .mlx_lora_backend import (
        MLXLoRABackend,
        AdvancedTrainingConfig,
        AdvancedTrainingResult,
        TRAIN_MODES,
    )
    from .document_dpo_pipeline import DocumentDPOPipeline, PreferencePair
    from .grpo_rewards import (
        register_enclave_rewards,
        get_reward_function_names,
        build_reward_combo,
    )
    from .adapter_packager import AdapterPackager, AdapterMetadata
    _ADVANCED_EXPORTS = [
        "MLXLoRABackend",
        "AdvancedTrainingConfig",
        "AdvancedTrainingResult",
        "TRAIN_MODES",
        "DocumentDPOPipeline",
        "PreferencePair",
        "register_enclave_rewards",
        "get_reward_function_names",
        "build_reward_combo",
        "AdapterPackager",
        "AdapterMetadata",
    ]
except ImportError:
    _ADVANCED_EXPORTS = []

__all__ = [
    # Core RAG
    "RAGIndex",
    "Document",
    "Chunk",
    "RetrievalResult",
    # Embeddings
    "EmbeddingEngine",
    "EmbeddingCache",
    # Vector indexes
    "VectorIndex",
    "HNSWIndex",
    "BruteForceIndex",
    "create_vector_index",
    # Local MLX training
    "MLXTrainer",
    "TrainingExample",
    "TrainingResult",
    "check_mlx_available",
    "get_recommended_model",
    # Advanced training (mlx-lm-lora)
    *(_ADVANCED_EXPORTS),
]
