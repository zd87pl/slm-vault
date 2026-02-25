"""
Training module for Enclave.

Provides local RAG indexing, embeddings, and MLX-based adapter training.
"""

from .embeddings import EmbeddingEngine
from .rag_index import RAGIndex, Document, Chunk

__all__ = [
    "EmbeddingEngine",
    "RAGIndex",
    "Document",
    "Chunk",
]
