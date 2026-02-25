"""
Embedding Engine for Enclave.

Provides local embedding generation using sentence-transformers.
Optimized for Apple Silicon with MLX backend when available.
"""

import logging
from typing import List, Optional, Union
from pathlib import Path
import hashlib

import numpy as np

logger = logging.getLogger(__name__)

# Default model (~90MB, good balance of quality and speed)
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Alternative models for different use cases
MODELS = {
    "default": "sentence-transformers/all-MiniLM-L6-v2",       # 90MB, 384 dim
    "fast": "sentence-transformers/all-MiniLM-L6-v2",          # Same, optimized
    "quality": "sentence-transformers/all-mpnet-base-v2",       # 420MB, 768 dim
    "multilingual": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # 470MB
}


class EmbeddingEngine:
    """
    Local embedding generation engine.

    Features:
    - Sentence-transformers backend (CPU/MPS)
    - Automatic batching for efficiency
    - Embedding cache for deduplication
    - Dimension normalization
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Optional[Path] = None,
        device: Optional[str] = None,
        normalize: bool = True
    ):
        """
        Initialize embedding engine.

        Args:
            model_name: HuggingFace model identifier or preset name
            cache_dir: Optional cache directory for model files
            device: Device to use ('cpu', 'mps', 'cuda'). Auto-detected if None.
            normalize: Whether to L2-normalize embeddings (recommended for cosine similarity)
        """
        self.model_name = MODELS.get(model_name, model_name)
        self.cache_dir = cache_dir
        self.normalize = normalize
        self._model = None
        self._device = device
        self._embedding_cache: dict[str, np.ndarray] = {}
        self._dimension: Optional[int] = None

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
            from sentence_transformers import SentenceTransformer

            device = self._get_device()

            model_kwargs = {}
            if self.cache_dir:
                model_kwargs["cache_folder"] = str(self.cache_dir)

            self._model = SentenceTransformer(
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

        # Check cache for existing embeddings
        if use_cache:
            embeddings = []
            texts_to_embed = []
            text_indices = []

            for i, text in enumerate(texts):
                cache_key = self._text_hash(text)
                if cache_key in self._embedding_cache:
                    embeddings.append((i, self._embedding_cache[cache_key]))
                else:
                    texts_to_embed.append(text)
                    text_indices.append(i)

            # Embed texts not in cache
            if texts_to_embed:
                new_embeddings = self._model.encode(
                    texts_to_embed,
                    batch_size=batch_size,
                    show_progress_bar=show_progress,
                    normalize_embeddings=self.normalize,
                    convert_to_numpy=True
                )

                # Cache new embeddings
                for i, (text, emb) in enumerate(zip(texts_to_embed, new_embeddings)):
                    cache_key = self._text_hash(text)
                    self._embedding_cache[cache_key] = emb
                    embeddings.append((text_indices[i], emb))

            # Sort by original index and stack
            embeddings.sort(key=lambda x: x[0])
            result = np.stack([e[1] for e in embeddings])
        else:
            result = self._model.encode(
                texts,
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

        Shorthand for embed() with single text.
        Query embeddings are not cached by default.

        Args:
            query: Query text

        Returns:
            Embedding vector of shape (dimension,)
        """
        return self.embed(query, use_cache=False)

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

    def clear_cache(self):
        """Clear the embedding cache."""
        self._embedding_cache.clear()
        logger.info("Embedding cache cleared")

    @property
    def cache_size(self) -> int:
        """Get number of cached embeddings."""
        return len(self._embedding_cache)
