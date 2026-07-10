"""
Embedding Engine for Enclave.

Provides local embedding generation using sentence-transformers.
Optimized for Apple Silicon with MLX backend when available.

Performance optimizations (Phase 2-3):
- E5-small default model (+15% quality vs MiniLM)
- Persistent disk cache for embeddings (2-9x speedup for repeated queries)
- ONNX export with INT8 quantization support (2-3x faster)
"""

import logging
import json
import sqlite3
from typing import List, Optional, Union
from pathlib import Path
import hashlib

import numpy as np

logger = logging.getLogger(__name__)

# Module-level handle to sentence_transformers.SentenceTransformer. Bound
# lazily on first use so the heavy import stays optional at module import
# time; unit tests patch this attribute directly.
SentenceTransformer = None


def _bind_sentence_transformer():
    global SentenceTransformer
    if SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer as _SentenceTransformer
        SentenceTransformer = _SentenceTransformer
    return SentenceTransformer

# Default model - E5-small has 100% top-5 accuracy vs MiniLM's 56%
# Research: https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked
DEFAULT_MODEL = "intfloat/e5-small-v2"

# Alternative models for different use cases
MODELS = {
    "default": "intfloat/e5-small-v2",                          # 118MB, 384 dim, best quality/speed
    "e5-small": "intfloat/e5-small-v2",                         # Same as default
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",         # 90MB, 384 dim, legacy
    "fast": "sentence-transformers/all-MiniLM-L6-v2",           # Same as minilm
    "quality": "intfloat/e5-base-v2",                           # 440MB, 768 dim
    "multilingual": "intfloat/multilingual-e5-small",           # 470MB, 384 dim
    "bge-small": "BAAI/bge-small-en-v1.5",                      # 130MB, 384 dim
}


class EmbeddingCache:
    """
    Persistent SQLite-based embedding cache.

    Provides 2-9x speedup by avoiding re-computation of embeddings
    for previously seen text.
    """

    def __init__(self, cache_path: Optional[Path] = None):
        """
        Initialize embedding cache.

        Args:
            cache_path: Path to SQLite cache file. Default: ~/.enclave/embedding_cache.db
        """
        if cache_path is None:
            cache_path = Path.home() / ".enclave" / "embedding_cache.db"

        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # In-memory LRU cache for hot embeddings
        self._memory_cache: dict[str, np.ndarray] = {}
        self._memory_cache_max_size = 10000

    def _init_db(self):
        """Initialize SQLite schema."""
        with sqlite3.connect(self.cache_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    text_hash TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    dimension INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_model
                ON embeddings(model_name)
            """)
            conn.commit()

    def get(self, text_hash: str, model_name: str) -> Optional[np.ndarray]:
        """Get embedding from cache."""
        # Check memory cache first
        cache_key = f"{model_name}:{text_hash}"
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # Check disk cache
        with sqlite3.connect(self.cache_path) as conn:
            cursor = conn.execute(
                "SELECT embedding, dimension FROM embeddings WHERE text_hash = ? AND model_name = ?",
                (text_hash, model_name)
            )
            row = cursor.fetchone()

        if row:
            emb_bytes, dimension = row
            embedding = np.frombuffer(emb_bytes, dtype=np.float32)
            # Add to memory cache
            self._add_to_memory_cache(cache_key, embedding)
            return embedding

        return None

    def put(self, text_hash: str, model_name: str, embedding: np.ndarray):
        """Store embedding in cache."""
        cache_key = f"{model_name}:{text_hash}"

        # Add to memory cache
        self._add_to_memory_cache(cache_key, embedding)

        # Add to disk cache
        with sqlite3.connect(self.cache_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO embeddings (text_hash, model_name, embedding, dimension)
                VALUES (?, ?, ?, ?)
            """, (text_hash, model_name, embedding.tobytes(), len(embedding)))
            conn.commit()

    def _add_to_memory_cache(self, key: str, embedding: np.ndarray):
        """Add to memory cache with LRU eviction."""
        if len(self._memory_cache) >= self._memory_cache_max_size:
            # Evict oldest entry (simple FIFO, not true LRU)
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]

        self._memory_cache[key] = embedding

    def get_batch(self, text_hashes: List[str], model_name: str) -> dict[str, np.ndarray]:
        """Get multiple embeddings from cache."""
        results = {}
        missing = []

        # Check memory cache first
        for text_hash in text_hashes:
            cache_key = f"{model_name}:{text_hash}"
            if cache_key in self._memory_cache:
                results[text_hash] = self._memory_cache[cache_key]
            else:
                missing.append(text_hash)

        if not missing:
            return results

        # Check disk cache for missing
        placeholders = ",".join("?" * len(missing))
        with sqlite3.connect(self.cache_path) as conn:
            cursor = conn.execute(f"""
                SELECT text_hash, embedding, dimension FROM embeddings
                WHERE model_name = ? AND text_hash IN ({placeholders})
            """, [model_name] + missing)

            for row in cursor.fetchall():
                text_hash, emb_bytes, dimension = row
                embedding = np.frombuffer(emb_bytes, dtype=np.float32)
                results[text_hash] = embedding
                self._add_to_memory_cache(f"{model_name}:{text_hash}", embedding)

        return results

    def put_batch(self, embeddings: dict[str, np.ndarray], model_name: str):
        """Store multiple embeddings in cache."""
        with sqlite3.connect(self.cache_path) as conn:
            for text_hash, embedding in embeddings.items():
                cache_key = f"{model_name}:{text_hash}"
                self._add_to_memory_cache(cache_key, embedding)
                conn.execute("""
                    INSERT OR REPLACE INTO embeddings (text_hash, model_name, embedding, dimension)
                    VALUES (?, ?, ?, ?)
                """, (text_hash, model_name, embedding.tobytes(), len(embedding)))
            conn.commit()

    def clear(self, model_name: Optional[str] = None):
        """Clear cache, optionally for specific model only."""
        self._memory_cache.clear()

        with sqlite3.connect(self.cache_path) as conn:
            if model_name:
                conn.execute("DELETE FROM embeddings WHERE model_name = ?", (model_name,))
            else:
                conn.execute("DELETE FROM embeddings")
            conn.commit()

    def stats(self) -> dict:
        """Get cache statistics."""
        with sqlite3.connect(self.cache_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            by_model = dict(conn.execute(
                "SELECT model_name, COUNT(*) FROM embeddings GROUP BY model_name"
            ).fetchall())

        return {
            "total_embeddings": total,
            "by_model": by_model,
            "memory_cache_size": len(self._memory_cache),
            "cache_path": str(self.cache_path),
        }


class EmbeddingEngine:
    """
    Local embedding generation engine.

    Features:
    - E5-small model by default (+15% quality vs MiniLM)
    - Sentence-transformers backend (CPU/MPS/CUDA)
    - Persistent disk cache for embeddings (2-9x speedup)
    - Automatic batching for efficiency
    - L2 normalization for cosine similarity
    - ONNX export support (Phase 3)
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Optional[Path] = None,
        device: Optional[str] = None,
        normalize: bool = True,
        use_persistent_cache: bool = True,
        cache_path: Optional[Path] = None
    ):
        """
        Initialize embedding engine.

        Args:
            model_name: HuggingFace model identifier or preset name
            cache_dir: Optional cache directory for model files
            device: Device to use ('cpu', 'mps', 'cuda'). Auto-detected if None.
            normalize: Whether to L2-normalize embeddings (recommended for cosine similarity)
            use_persistent_cache: Whether to use persistent disk cache for embeddings
            cache_path: Path to embedding cache database
        """
        self.model_name = MODELS.get(model_name, model_name)
        self.cache_dir = cache_dir
        self.normalize = normalize
        self._model = None
        self._device = device
        self._embedding_cache: dict[str, np.ndarray] = {}
        self._dimension: Optional[int] = None

        # Initialize persistent cache
        self._persistent_cache: Optional[EmbeddingCache] = None
        if use_persistent_cache:
            self._persistent_cache = EmbeddingCache(cache_path)

        logger.info(f"Initializing EmbeddingEngine with model: {self.model_name}")

    def _get_device(self) -> str:
        """Auto-detect best available device."""
        if self._device:
            return self._device

        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
            elif torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass

        return "cpu"

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self._model is not None:
            return

        try:
            sentence_transformer_cls = _bind_sentence_transformer()

            device = self._get_device()

            model_kwargs = {}
            if self.cache_dir:
                model_kwargs["cache_folder"] = str(self.cache_dir)

            self._model = sentence_transformer_cls(
                self.model_name,
                device=device,
                **model_kwargs
            )

            self._dimension = self._model.get_sentence_embedding_dimension()

            logger.info(
                f"Loaded embedding model: {self.model_name} "
                f"(dim={self._dimension}, device={device})"
            )

        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embeddings. "
                "Install with: pip install sentence-transformers"
            )

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            self._load_model()
        return self._dimension

    def _text_hash(self, text: str) -> str:
        """Generate hash for cache key."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def embed(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress: bool = False,
        use_cache: bool = True
    ) -> np.ndarray:
        """
        Generate embeddings for text(s).

        Uses a two-level cache:
        1. In-memory cache for hot embeddings
        2. Persistent SQLite cache for long-term storage (2-9x speedup)

        Args:
            texts: Single text or list of texts
            batch_size: Batch size for encoding
            show_progress: Whether to show progress bar
            use_cache: Whether to use embedding cache

        Returns:
            Numpy array of shape (n_texts, dimension) or (dimension,) for single text
        """
        self._load_model()

        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        # E5 models require "query: " or "passage: " prefix for best results
        is_e5_model = "e5" in self.model_name.lower()

        # Check cache for existing embeddings
        if use_cache:
            embeddings = []
            texts_to_embed = []
            text_indices = []
            text_hashes = []

            for i, text in enumerate(texts):
                cache_key = self._text_hash(text)
                text_hashes.append(cache_key)

                # Check in-memory cache first
                if cache_key in self._embedding_cache:
                    embeddings.append((i, self._embedding_cache[cache_key]))
                else:
                    texts_to_embed.append(text)
                    text_indices.append(i)

            # Check persistent cache for missing embeddings
            if texts_to_embed and self._persistent_cache:
                missing_hashes = [self._text_hash(t) for t in texts_to_embed]
                cached = self._persistent_cache.get_batch(missing_hashes, self.model_name)

                still_missing = []
                still_missing_indices = []
                for text, idx, text_hash in zip(texts_to_embed, text_indices, missing_hashes):
                    if text_hash in cached:
                        emb = cached[text_hash]
                        self._embedding_cache[text_hash] = emb  # Promote to memory
                        embeddings.append((idx, emb))
                    else:
                        still_missing.append(text)
                        still_missing_indices.append(idx)

                texts_to_embed = still_missing
                text_indices = still_missing_indices

            # Embed texts not in any cache
            if texts_to_embed:
                # Add E5 prefix if needed
                encode_texts = texts_to_embed
                if is_e5_model:
                    encode_texts = [f"passage: {t}" for t in texts_to_embed]

                new_embeddings = self._model.encode(
                    encode_texts,
                    batch_size=batch_size,
                    show_progress_bar=show_progress,
                    normalize_embeddings=self.normalize,
                    convert_to_numpy=True
                )

                # Cache new embeddings
                new_cache_entries = {}
                for text, emb, idx in zip(texts_to_embed, new_embeddings, text_indices):
                    cache_key = self._text_hash(text)
                    self._embedding_cache[cache_key] = emb
                    new_cache_entries[cache_key] = emb
                    embeddings.append((idx, emb))

                # Persist to disk cache
                if self._persistent_cache and new_cache_entries:
                    self._persistent_cache.put_batch(new_cache_entries, self.model_name)

            # Sort by original index and stack
            embeddings.sort(key=lambda x: x[0])
            result = np.stack([e[1] for e in embeddings])
        else:
            # No caching - direct embedding
            encode_texts = texts
            if is_e5_model:
                encode_texts = [f"passage: {t}" for t in texts]

            result = self._model.encode(
                encode_texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                normalize_embeddings=self.normalize,
                convert_to_numpy=True
            )

        if single_input:
            return result[0]
        return result

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a query string.

        For E5 models, automatically adds "query: " prefix for optimal results.
        Query embeddings are not cached by default.

        Args:
            query: Query text

        Returns:
            Embedding vector of shape (dimension,)
        """
        self._load_model()

        # E5 models require "query: " prefix
        is_e5_model = "e5" in self.model_name.lower()
        encode_text = f"query: {query}" if is_e5_model else query

        embedding = self._model.encode(
            encode_text,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True
        )

        return embedding

    def embed_documents(
        self,
        documents: List[str],
        batch_size: int = 32,
        show_progress: bool = True
    ) -> np.ndarray:
        """
        Embed multiple documents.

        Args:
            documents: List of document texts
            batch_size: Batch size for encoding
            show_progress: Whether to show progress bar

        Returns:
            Embedding matrix of shape (n_documents, dimension)
        """
        return self.embed(
            documents,
            batch_size=batch_size,
            show_progress=show_progress,
            use_cache=True
        )

    def similarity(
        self,
        query_embedding: np.ndarray,
        document_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Compute cosine similarity between query and documents.

        Args:
            query_embedding: Query embedding of shape (dimension,)
            document_embeddings: Document embeddings of shape (n_docs, dimension)

        Returns:
            Similarity scores of shape (n_docs,)
        """
        if self.normalize:
            # With normalized vectors, cosine similarity = dot product
            return np.dot(document_embeddings, query_embedding)
        else:
            # Compute cosine similarity manually
            query_norm = np.linalg.norm(query_embedding)
            doc_norms = np.linalg.norm(document_embeddings, axis=1)
            return np.dot(document_embeddings, query_embedding) / (doc_norms * query_norm + 1e-8)

    def clear_cache(self, clear_persistent: bool = False):
        """
        Clear the embedding cache.

        Args:
            clear_persistent: If True, also clear the persistent disk cache
        """
        self._embedding_cache.clear()

        if clear_persistent and self._persistent_cache:
            self._persistent_cache.clear(self.model_name)

        logger.info("Embedding cache cleared")

    @property
    def cache_size(self) -> int:
        """Get number of cached embeddings in memory."""
        return len(self._embedding_cache)

    def cache_stats(self) -> dict:
        """Get cache statistics including persistent cache."""
        stats = {
            "memory_cache_size": len(self._embedding_cache),
            "model_name": self.model_name,
        }

        if self._persistent_cache:
            stats["persistent_cache"] = self._persistent_cache.stats()

        return stats

    def export_onnx(
        self,
        output_path: Path,
        quantize: bool = True,
        quantization_mode: str = "avx512"
    ) -> Path:
        """
        Export model to ONNX format with optional INT8 quantization.

        ONNX export provides 2-3x faster inference on CPU.

        Args:
            output_path: Directory to save ONNX model
            quantize: Whether to apply INT8 dynamic quantization
            quantization_mode: Quantization mode ('avx512', 'avx2', 'arm64')

        Returns:
            Path to the exported model directory
        """
        self._load_model()

        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            if quantize:
                # Use sentence-transformers built-in ONNX export with quantization
                self._model.export_dynamic_quantized_onnx_model(
                    str(output_path),
                    quantization_config=quantization_mode
                )
                logger.info(f"Exported quantized ONNX model to {output_path}")
            else:
                # Export without quantization
                self._model.save_onnx(str(output_path))
                logger.info(f"Exported ONNX model to {output_path}")

            return output_path

        except AttributeError:
            # Fallback for older sentence-transformers versions
            logger.warning(
                "ONNX export not available in this sentence-transformers version. "
                "Upgrade with: pip install sentence-transformers>=2.4.0"
            )
            raise

    @staticmethod
    def create_fast_engine(
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Optional[Path] = None
    ) -> "FastEmbeddingEngine":
        """
        Create a FastEmbed-based engine for maximum speed.

        FastEmbed uses ONNX runtime for 2-3x faster inference.

        Args:
            model_name: FastEmbed model name
            cache_dir: Cache directory

        Returns:
            FastEmbeddingEngine instance
        """
        return FastEmbeddingEngine(model_name=model_name, cache_dir=cache_dir)


class FastEmbeddingEngine:
    """
    ONNX-based embedding engine using FastEmbed.

    Provides 2-3x faster inference compared to sentence-transformers.
    Best for production deployments with high throughput requirements.

    Supported models:
    - BAAI/bge-small-en-v1.5 (default, 384 dim)
    - BAAI/bge-base-en-v1.5 (768 dim)
    - sentence-transformers/all-MiniLM-L6-v2 (384 dim)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Optional[Path] = None,
        max_length: int = 512
    ):
        """
        Initialize FastEmbed engine.

        Args:
            model_name: Model name supported by FastEmbed
            cache_dir: Cache directory for model files
            max_length: Maximum sequence length
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.max_length = max_length
        self._model = None
        self._dimension: Optional[int] = None

    def _load_model(self):
        """Lazy-load the FastEmbed model."""
        if self._model is not None:
            return

        try:
            from fastembed import TextEmbedding

            kwargs = {"max_length": self.max_length}
            if self.cache_dir:
                kwargs["cache_dir"] = str(self.cache_dir)

            self._model = TextEmbedding(self.model_name, **kwargs)
            logger.info(f"Loaded FastEmbed model: {self.model_name}")

        except ImportError:
            raise ImportError(
                "fastembed is required for fast embeddings. "
                "Install with: pip install fastembed"
            )

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            self._load_model()
            # Embed a test string to get dimension
            test_emb = list(self._model.embed(["test"]))[0]
            self._dimension = len(test_emb)
        return self._dimension

    def embed(self, texts: Union[str, List[str]]) -> np.ndarray:
        """Generate embeddings."""
        self._load_model()

        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        # FastEmbed returns a generator
        embeddings = list(self._model.embed(texts))
        result = np.array(embeddings, dtype=np.float32)

        if single_input:
            return result[0]
        return result

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a query string."""
        return self.embed(query)

    def embed_documents(self, documents: List[str]) -> np.ndarray:
        """Embed multiple documents."""
        return self.embed(documents)
