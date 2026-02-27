"""
Training module for Enclave.

Provides local RAG indexing, embeddings, and MLX-based adapter training.

Performance optimizations (Phases 1-3):
- HNSW index for 10-30x faster vector search
- E5-small embeddings (+15% quality vs MiniLM)
- Persistent embedding cache (2-9x speedup)
- KV caching (TurboRAG pattern)
- ONNX/FastEmbed support for faster inference
"""

from .embeddings import EmbeddingEngine, EmbeddingCache, FastEmbeddingEngine
from .rag_index import RAGIndex, Document, Chunk, RetrievalResult
from .vector_index import VectorIndex, HNSWIndex, BruteForceIndex, create_vector_index
from .kv_cache import RAGCache, QueryCache, ChunkKVCache
from .late_chunking import LateChunker, JinaLateChunker, LateChunk, create_late_chunker

__all__ = [
    # Core RAG
    "RAGIndex",
    "Document",
    "Chunk",
    "RetrievalResult",
    # Embeddings
    "EmbeddingEngine",
    "EmbeddingCache",
    "FastEmbeddingEngine",
    # Vector indexes
    "VectorIndex",
    "HNSWIndex",
    "BruteForceIndex",
    "create_vector_index",
    # Caching
    "RAGCache",
    "QueryCache",
    "ChunkKVCache",
    # Late chunking
    "LateChunker",
    "JinaLateChunker",
    "LateChunk",
    "create_late_chunker",
]
