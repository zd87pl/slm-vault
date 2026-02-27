"""
Vector Index Abstraction for Enclave.

Provides fast approximate nearest neighbor (ANN) search using HNSW algorithm.
Falls back to brute-force if hnswlib is not available.

Performance:
- HNSW: 10-30x faster than brute-force at 10K+ documents
- Maintains >95% recall with proper tuning
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class VectorIndex(ABC):
    """Abstract base class for vector indexes."""

    @abstractmethod
    def add(self, ids: List[str], embeddings: np.ndarray) -> None:
        """Add vectors to the index."""
        pass

    @abstractmethod
    def search(self, query: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """Search for nearest neighbors. Returns list of (id, score) tuples."""
        pass

    @abstractmethod
    def remove(self, ids: List[str]) -> None:
        """Remove vectors from the index."""
        pass

    @abstractmethod
    def save(self, path: Path) -> None:
        """Persist index to disk."""
        pass

    @abstractmethod
    def load(self, path: Path) -> None:
        """Load index from disk."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all vectors from the index."""
        pass

    @property
    @abstractmethod
    def size(self) -> int:
        """Number of vectors in the index."""
        pass


class HNSWIndex(VectorIndex):
    """
    HNSW (Hierarchical Navigable Small World) index for fast ANN search.

    Uses hnswlib for 10-30x faster search compared to brute-force.
    Maintains >95% recall with default parameters.

    Parameters tuned for 384-dim embeddings (MiniLM/E5-small):
    - M=16: connections per node (good for 384 dims)
    - ef_construction=200: build-time accuracy
    - ef_search=50: query-time accuracy/speed tradeoff
    """

    def __init__(
        self,
        dimension: int = 384,
        max_elements: int = 100000,
        M: int = 16,
        ef_construction: int = 200,
        ef_search: int = 50,
        space: str = "cosine"
    ):
        """
        Initialize HNSW index.

        Args:
            dimension: Vector dimension (384 for MiniLM, E5-small)
            max_elements: Maximum capacity (can be resized)
            M: Number of connections per node (higher = better recall, more memory)
            ef_construction: Build-time search depth (higher = better index, slower build)
            ef_search: Query-time search depth (higher = better recall, slower query)
            space: Distance metric ('cosine', 'l2', 'ip')
        """
        try:
            import hnswlib
            self._hnswlib = hnswlib
        except ImportError:
            raise ImportError(
                "hnswlib not installed. Install with: pip install hnswlib"
            )

        self.dimension = dimension
        self.max_elements = max_elements
        self.M = M
        self.ef_construction = ef_construction
        self.ef_search = ef_search
        self.space = space

        # Map string IDs to integer indices
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._next_idx: int = 0
        self._deleted: set[int] = set()

        self._init_index()

    def _init_index(self):
        """Initialize or reinitialize the HNSW index."""
        self._index = self._hnswlib.Index(space=self.space, dim=self.dimension)
        self._index.init_index(
            max_elements=self.max_elements,
            ef_construction=self.ef_construction,
            M=self.M
        )
        self._index.set_ef(self.ef_search)

    def add(self, ids: List[str], embeddings: np.ndarray) -> None:
        """
        Add vectors to the index.

        Args:
            ids: List of string IDs
            embeddings: numpy array of shape (n, dimension)
        """
        if len(ids) != len(embeddings):
            raise ValueError("Number of ids must match number of embeddings")

        if len(embeddings) == 0:
            return

        # Ensure float32 and normalized for cosine similarity
        embeddings = embeddings.astype(np.float32)

        # Resize if needed
        current_size = self._next_idx - len(self._deleted)
        needed = current_size + len(ids)
        if needed > self.max_elements:
            self._resize(max(needed * 2, self.max_elements * 2))

        # Map IDs to indices
        indices = []
        for id_ in ids:
            if id_ in self._id_to_idx:
                # Update existing - mark old as deleted
                old_idx = self._id_to_idx[id_]
                self._deleted.add(old_idx)

            idx = self._next_idx
            self._id_to_idx[id_] = idx
            self._idx_to_id[idx] = id_
            indices.append(idx)
            self._next_idx += 1

        # Add to HNSW index
        self._index.add_items(embeddings, np.array(indices, dtype=np.int64))

        logger.debug(f"Added {len(ids)} vectors to HNSW index")

    def search(self, query: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Search for nearest neighbors.

        Args:
            query: Query vector of shape (dimension,)
            top_k: Number of results to return

        Returns:
            List of (id, score) tuples, sorted by score descending
        """
        if self.size == 0:
            return []

        query = query.astype(np.float32).reshape(1, -1)

        # Search more than top_k to account for deleted items
        search_k = min(top_k + len(self._deleted), self.size)

        indices, distances = self._index.knn_query(query, k=search_k)

        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx in self._deleted:
                continue

            id_ = self._idx_to_id.get(idx)
            if id_ is None:
                continue

            # Convert distance to similarity score
            # For cosine space, hnswlib returns 1-cosine_similarity
            score = 1.0 - dist

            results.append((id_, float(score)))

            if len(results) >= top_k:
                break

        return results

    def remove(self, ids: List[str]) -> None:
        """
        Mark vectors as deleted (lazy deletion).

        Args:
            ids: List of IDs to remove
        """
        for id_ in ids:
            if id_ in self._id_to_idx:
                idx = self._id_to_idx[id_]
                self._deleted.add(idx)
                del self._id_to_idx[id_]
                del self._idx_to_id[idx]

        logger.debug(f"Marked {len(ids)} vectors as deleted")

    def _resize(self, new_max: int):
        """Resize the index to accommodate more elements."""
        self.max_elements = new_max
        self._index.resize_index(new_max)
        logger.info(f"Resized HNSW index to {new_max} elements")

    def save(self, path: Path) -> None:
        """
        Save index to disk.

        Saves both the HNSW index and ID mappings.
        """
        import json

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save HNSW index
        self._index.save_index(str(path.with_suffix('.hnsw')))

        # Save ID mappings
        metadata = {
            'id_to_idx': self._id_to_idx,
            'idx_to_id': {int(k): v for k, v in self._idx_to_id.items()},
            'next_idx': self._next_idx,
            'deleted': list(self._deleted),
            'dimension': self.dimension,
            'max_elements': self.max_elements,
            'M': self.M,
            'ef_construction': self.ef_construction,
            'ef_search': self.ef_search,
            'space': self.space,
        }
        with open(path.with_suffix('.meta.json'), 'w') as f:
            json.dump(metadata, f)

        logger.info(f"Saved HNSW index to {path}")

    def load(self, path: Path) -> None:
        """Load index from disk."""
        import json

        path = Path(path)

        # Load metadata
        meta_path = path.with_suffix('.meta.json')
        if not meta_path.exists():
            raise FileNotFoundError(f"Index metadata not found: {meta_path}")

        with open(meta_path, 'r') as f:
            metadata = json.load(f)

        self.dimension = metadata['dimension']
        self.max_elements = metadata['max_elements']
        self.M = metadata['M']
        self.ef_construction = metadata['ef_construction']
        self.ef_search = metadata['ef_search']
        self.space = metadata['space']

        self._id_to_idx = metadata['id_to_idx']
        self._idx_to_id = {int(k): v for k, v in metadata['idx_to_id'].items()}
        self._next_idx = metadata['next_idx']
        self._deleted = set(metadata['deleted'])

        # Load HNSW index
        hnsw_path = path.with_suffix('.hnsw')
        if not hnsw_path.exists():
            raise FileNotFoundError(f"HNSW index not found: {hnsw_path}")

        self._index = self._hnswlib.Index(space=self.space, dim=self.dimension)
        self._index.load_index(str(hnsw_path), max_elements=self.max_elements)
        self._index.set_ef(self.ef_search)

        logger.info(f"Loaded HNSW index from {path} ({self.size} vectors)")

    def clear(self) -> None:
        """Clear all vectors and reinitialize."""
        self._id_to_idx.clear()
        self._idx_to_id.clear()
        self._next_idx = 0
        self._deleted.clear()
        self._init_index()
        logger.info("Cleared HNSW index")

    @property
    def size(self) -> int:
        """Number of active vectors in the index."""
        return len(self._id_to_idx)


class BruteForceIndex(VectorIndex):
    """
    Brute-force vector index as fallback.

    Slower but requires no additional dependencies.
    Suitable for <1000 documents.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self._vectors: dict[str, np.ndarray] = {}

    def add(self, ids: List[str], embeddings: np.ndarray) -> None:
        """Add vectors to the index."""
        for id_, emb in zip(ids, embeddings):
            self._vectors[id_] = emb.astype(np.float32)

    def search(self, query: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """Search using brute-force cosine similarity."""
        if not self._vectors:
            return []

        query = query.astype(np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm > 0:
            query = query / query_norm

        scores = []
        for id_, vec in self._vectors.items():
            vec_norm = np.linalg.norm(vec)
            if vec_norm > 0:
                score = float(np.dot(query, vec / vec_norm))
            else:
                score = 0.0
            scores.append((id_, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def remove(self, ids: List[str]) -> None:
        """Remove vectors from the index."""
        for id_ in ids:
            self._vectors.pop(id_, None)

    def save(self, path: Path) -> None:
        """Save index to disk."""
        import json

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'dimension': self.dimension,
            'vectors': {
                id_: vec.tolist() for id_, vec in self._vectors.items()
            }
        }
        with open(path.with_suffix('.brute.json'), 'w') as f:
            json.dump(data, f)

    def load(self, path: Path) -> None:
        """Load index from disk."""
        import json

        path = Path(path)
        with open(path.with_suffix('.brute.json'), 'r') as f:
            data = json.load(f)

        self.dimension = data['dimension']
        self._vectors = {
            id_: np.array(vec, dtype=np.float32)
            for id_, vec in data['vectors'].items()
        }

    def clear(self) -> None:
        """Clear all vectors."""
        self._vectors.clear()

    @property
    def size(self) -> int:
        """Number of vectors in the index."""
        return len(self._vectors)


def create_vector_index(
    dimension: int = 384,
    max_elements: int = 100000,
    prefer_hnsw: bool = True
) -> VectorIndex:
    """
    Factory function to create a vector index.

    Tries HNSW first for performance, falls back to brute-force.

    Args:
        dimension: Vector dimension
        max_elements: Maximum capacity (HNSW only)
        prefer_hnsw: If True, prefer HNSW over brute-force

    Returns:
        VectorIndex instance
    """
    if prefer_hnsw:
        try:
            index = HNSWIndex(dimension=dimension, max_elements=max_elements)
            logger.info("Using HNSW index for fast vector search")
            return index
        except ImportError:
            logger.warning("hnswlib not available, falling back to brute-force")

    logger.info("Using brute-force index (install hnswlib for 10-30x faster search)")
    return BruteForceIndex(dimension=dimension)
