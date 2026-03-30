"""
RAG Index for Enclave.

Provides document chunking, embedding storage, and semantic retrieval.
All data encrypted at rest with ChaCha20-Poly1305 for privacy.

Performance optimizations (Phase 1):
- HNSW index for 10-30x faster search at scale
- Recursive chunking with 400-512 tokens for better recall
- Sentence boundary preservation

Security properties:
- Document content encrypted before storage
- Chunk content encrypted with unique nonce per chunk
- Embeddings stored unencrypted (enables similarity search)
- Master key zeroed on close
"""

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import hashlib

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .embeddings import EmbeddingEngine
from .vector_index import create_vector_index, VectorIndex

logger = logging.getLogger(__name__)

# Default chunking parameters - optimized for recall
# Research shows 400-512 tokens with recursive splitting achieves best results
DEFAULT_CHUNK_SIZE = 450  # tokens (optimized from 500)
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_TOP_K = 5
SIMILARITY_THRESHOLD = 0.3

# Recursive chunking separators (in order of preference)
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]

# Encryption constants
MASTER_KEY_LENGTH = 32  # 256-bit key for ChaCha20-Poly1305
NONCE_LENGTH = 12  # 96-bit nonce


@dataclass
class Chunk:
    """A chunk of text from a document."""

    id: str
    document_id: str
    content: str
    index: int  # Position in document
    start_char: int
    end_char: int
    embedding: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "content": self.content,
            "index": self.index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "metadata": self.metadata,
        }


@dataclass
class Document:
    """A document in the RAG index."""

    id: str
    name: str
    content: str
    source_path: Optional[str] = None
    content_hash: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunks: List[Chunk] = field(default_factory=list)

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "source_path": self.source_path,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "chunk_count": len(self.chunks),
        }


@dataclass
class RetrievalResult:
    """Result from a retrieval query."""

    chunk: Chunk
    score: float
    document_name: str
    document_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.chunk.content,
            "score": float(self.score),
            "document_name": self.document_name,
            "document_id": self.document_id,
            "chunk_index": self.chunk.index,
            "metadata": self.chunk.metadata,
        }


class RAGIndex:
    """
    Local RAG index with SQLite backend and encrypted storage.

    Features:
    - Document chunking with configurable overlap
    - Embedding storage and retrieval
    - Semantic search with cosine similarity
    - Document deduplication via content hash
    - Metadata filtering
    - ChaCha20-Poly1305 encryption for all content at rest

    Security properties:
    - Document and chunk content encrypted before storage
    - Unique nonce per chunk (semantic security)
    - Embeddings unencrypted (enables similarity search, but don't reveal text)
    - Master key zeroed on close
    """

    def __init__(
        self,
        master_key: bytes,
        db_path: str = "~/.enclave/rag.db",
        embedding_engine: Optional[EmbeddingEngine] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        use_hnsw: bool = True
    ):
        """
        Initialize RAG index with encryption and HNSW acceleration.

        Args:
            master_key: 32-byte encryption key for ChaCha20-Poly1305
            db_path: Path to SQLite database
            embedding_engine: Optional embedding engine (created if not provided)
            chunk_size: Target chunk size in tokens (default 450, optimized for recall)
            chunk_overlap: Overlap between chunks in tokens
            use_hnsw: If True, use HNSW index for fast search (10-30x faster)

        Raises:
            ValueError: If master_key is not exactly 32 bytes
        """
        if len(master_key) != MASTER_KEY_LENGTH:
            raise ValueError(f"Master key must be exactly {MASTER_KEY_LENGTH} bytes")

        # Store as mutable bytearray for secure zeroing later
        self._master_key = bytearray(master_key)
        self._cipher = ChaCha20Poly1305(bytes(self._master_key))

        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.embedding_engine = embedding_engine or EmbeddingEngine()
        self.chunk_size = chunk_size * 4  # Convert tokens to chars (rough estimate)
        self.chunk_overlap = chunk_overlap * 4

        self._init_db()

        # Initialize HNSW vector index for fast search
        self._use_hnsw = use_hnsw
        self._vector_index: Optional[VectorIndex] = None
        if use_hnsw:
            self._init_vector_index()

        # Track search errors for GUI reporting
        self._last_search_errors: list = []

        logger.info(
            f"Initialized encrypted RAGIndex at {self.db_path} "
            f"(chunk_size={chunk_size}, overlap={chunk_overlap}, hnsw={use_hnsw})"
        )

    def get_last_errors(self) -> list:
        """Get errors from the last search operation."""
        return self._last_search_errors.copy()

    def clear_errors(self):
        """Clear stored errors."""
        self._last_search_errors = []

    def _encrypt(self, plaintext: str, associated_data: str = "") -> Tuple[bytes, bytes]:
        """
        Encrypt plaintext content.

        Args:
            plaintext: Text to encrypt
            associated_data: Additional authenticated data (e.g., document ID)

        Returns:
            Tuple of (ciphertext, nonce)
        """
        nonce = os.urandom(NONCE_LENGTH)
        ciphertext = self._cipher.encrypt(
            nonce,
            plaintext.encode('utf-8'),
            associated_data.encode('utf-8') if associated_data else None
        )
        return ciphertext, nonce

    def _decrypt(self, ciphertext: bytes, nonce: bytes, associated_data: str = "") -> str:
        """
        Decrypt ciphertext content.

        Args:
            ciphertext: Encrypted data
            nonce: Nonce used for encryption
            associated_data: Additional authenticated data (must match encryption)

        Returns:
            Decrypted plaintext

        Raises:
            cryptography.exceptions.InvalidTag: If authentication fails
        """
        plaintext = self._cipher.decrypt(
            nonce,
            ciphertext,
            associated_data.encode('utf-8') if associated_data else None
        )
        return plaintext.decode('utf-8')

    def _init_vector_index(self):
        """Initialize or load the HNSW vector index."""
        dimension = self.embedding_engine.dimension or 384
        index_path = self.db_path.with_suffix('.hnsw')

        self._vector_index = create_vector_index(
            dimension=dimension,
            max_elements=100000,
            prefer_hnsw=True
        )

        # Load existing index if available
        if index_path.with_suffix('.hnsw').exists() or index_path.with_suffix('.meta.json').exists():
            try:
                self._vector_index.load(index_path)
                logger.info(f"Loaded HNSW index with {self._vector_index.size} vectors")
            except Exception as e:
                logger.warning(f"Failed to load HNSW index, will rebuild: {e}")
                self._rebuild_vector_index()
        else:
            # Build index from existing chunks
            self._rebuild_vector_index()

    def _rebuild_vector_index(self):
        """Rebuild the HNSW index from SQLite data."""
        if self._vector_index is None:
            return

        self._vector_index.clear()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL")
            rows = cursor.fetchall()

        if not rows:
            logger.info("No chunks to index")
            return

        ids = []
        embeddings = []
        for chunk_id, emb_bytes in rows:
            if emb_bytes:
                ids.append(chunk_id)
                embeddings.append(np.frombuffer(emb_bytes, dtype=np.float32))

        if ids:
            self._vector_index.add(ids, np.array(embeddings))
            self._save_vector_index()
            logger.info(f"Rebuilt HNSW index with {len(ids)} vectors")

    def _save_vector_index(self):
        """Persist the HNSW index to disk."""
        if self._vector_index is None:
            return

        index_path = self.db_path.with_suffix('.hnsw')
        try:
            self._vector_index.save(index_path)
        except Exception as e:
            logger.warning(f"Failed to save HNSW index: {e}")

    def _init_db(self):
        """Initialize SQLite database schema with encryption support."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if we need to migrate from unencrypted schema
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = {col[1] for col in cursor.fetchall()}

            if "nonce" not in columns and "content" in columns:
                # Migration needed - drop old tables (data loss, but necessary for security)
                logger.warning("Migrating to encrypted schema - existing unencrypted data will be lost")
                conn.execute("DROP TABLE IF EXISTS chunks")
                conn.execute("DROP TABLE IF EXISTS documents")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    content BLOB NOT NULL,
                    nonce BLOB NOT NULL,
                    source_path TEXT,
                    content_hash TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    content BLOB NOT NULL,
                    nonce BLOB NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    start_char INTEGER NOT NULL,
                    end_char INTEGER NOT NULL,
                    embedding BLOB,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_document
                ON chunks(document_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_hash
                ON documents(content_hash)
            """)

            conn.commit()

    def _chunk_text(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Split text into overlapping chunks using recursive splitting.

        Uses a hierarchy of separators (paragraphs > sentences > phrases)
        to preserve semantic boundaries. Research shows this achieves
        5-10% better recall compared to character-based chunking.

        Args:
            text: Text to chunk

        Returns:
            List of (chunk_text, start_char, end_char) tuples
        """
        return self._recursive_chunk(text, 0, CHUNK_SEPARATORS)

    def _recursive_chunk(
        self,
        text: str,
        offset: int,
        separators: List[str]
    ) -> List[Tuple[str, int, int]]:
        """
        Recursively split text using a hierarchy of separators.

        Args:
            text: Text to split
            offset: Character offset in original document
            separators: List of separators to try, in order of preference

        Returns:
            List of (chunk_text, start_char, end_char) tuples
        """
        if not text.strip():
            return []

        # If text fits in a chunk, return it
        if len(text) <= self.chunk_size:
            stripped = text.strip()
            if stripped:
                # Find actual start/end in original text
                start_in_text = text.index(stripped[0]) if stripped else 0
                return [(stripped, offset + start_in_text, offset + start_in_text + len(stripped))]
            return []

        # Find the best separator to use
        separator = None
        for sep in separators:
            if sep in text:
                separator = sep
                break

        # If no separator found, fall back to character-based splitting
        if separator is None:
            return self._character_chunk(text, offset)

        # Split by the separator
        parts = text.split(separator)
        chunks = []
        current_chunk = ""
        current_start = offset

        for i, part in enumerate(parts):
            # Add separator back (except for first part)
            if i > 0:
                part = separator + part

            # Check if adding this part exceeds chunk size
            if len(current_chunk) + len(part) > self.chunk_size:
                # Save current chunk if not empty
                if current_chunk.strip():
                    stripped = current_chunk.strip()
                    start_adj = current_chunk.index(stripped[0]) if stripped else 0
                    chunks.append((
                        stripped,
                        current_start + start_adj,
                        current_start + start_adj + len(stripped)
                    ))

                # Start new chunk with overlap
                if self.chunk_overlap > 0 and current_chunk:
                    # Take last chunk_overlap characters as overlap
                    overlap_text = current_chunk[-self.chunk_overlap:]
                    current_chunk = overlap_text + part
                    current_start = current_start + len(current_chunk) - len(overlap_text) - len(part)
                else:
                    current_chunk = part
                    current_start = offset + sum(len(p) + len(separator) for p in parts[:i]) - len(separator)

                # If this single part is too large, recursively split it
                if len(current_chunk) > self.chunk_size:
                    # Use next separator in hierarchy
                    remaining_seps = separators[separators.index(separator) + 1:] if separator in separators else []
                    if remaining_seps:
                        sub_chunks = self._recursive_chunk(current_chunk, current_start, remaining_seps)
                        chunks.extend(sub_chunks)
                        current_chunk = ""
                    else:
                        # Fall back to character splitting
                        sub_chunks = self._character_chunk(current_chunk, current_start)
                        chunks.extend(sub_chunks)
                        current_chunk = ""
            else:
                current_chunk += part

        # Don't forget the last chunk
        if current_chunk.strip():
            stripped = current_chunk.strip()
            start_adj = current_chunk.index(stripped[0]) if stripped else 0
            chunks.append((
                stripped,
                current_start + start_adj,
                current_start + start_adj + len(stripped)
            ))

        return chunks

    def _character_chunk(self, text: str, offset: int) -> List[Tuple[str, int, int]]:
        """
        Fall back to character-based chunking with sentence boundary preference.

        Args:
            text: Text to chunk
            offset: Character offset in original document

        Returns:
            List of (chunk_text, start_char, end_char) tuples
        """
        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence-ending punctuation
                for i in range(end, max(start + self.chunk_size // 2, start), -1):
                    if text[i - 1] in ".!?\n":
                        end = i
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append((chunk_text, offset + start, offset + end))

            # Move start, accounting for overlap
            start = end - self.chunk_overlap
            if start >= len(text) - self.chunk_overlap:
                break

        return chunks

    def add_document(
        self,
        name: str,
        content: str,
        source_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        update_if_exists: bool = True
    ) -> Document:
        """
        Add a document to the index with encrypted storage.

        Content is encrypted before storage. Embeddings are computed from
        plaintext but stored separately (enabling similarity search).

        Args:
            name: Document name
            content: Document content (will be encrypted)
            source_path: Optional source file path
            metadata: Optional metadata dict
            update_if_exists: If True, update existing document with same hash

        Returns:
            Document object (with plaintext content for caller)

        Raises:
            ValueError: If document with same hash exists and update_if_exists=False
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        metadata = metadata or {}
        now = datetime.utcnow()

        # Encrypt document content (use doc_id as associated data after we have it)
        # We'll re-encrypt with proper associated data below

        with sqlite3.connect(self.db_path) as conn:
            # Check for existing document
            cursor = conn.execute(
                "SELECT id FROM documents WHERE content_hash = ?",
                (content_hash,)
            )
            existing = cursor.fetchone()

            if existing:
                if not update_if_exists:
                    raise ValueError(f"Document with same content already exists: {existing[0]}")
                doc_id = existing[0]
                # Delete old chunks
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
                # Encrypt content with doc_id as associated data
                encrypted_content, doc_nonce = self._encrypt(content, doc_id)
                # Update document
                conn.execute("""
                    UPDATE documents
                    SET name = ?, content = ?, nonce = ?, source_path = ?, updated_at = ?, metadata = ?
                    WHERE id = ?
                """, (name, encrypted_content, doc_nonce, source_path, now.isoformat(), json.dumps(metadata), doc_id))
                logger.info(f"Updated existing document: {doc_id}")
            else:
                doc_id = str(uuid.uuid4())
                # Encrypt content with doc_id as associated data
                encrypted_content, doc_nonce = self._encrypt(content, doc_id)
                conn.execute("""
                    INSERT INTO documents (id, name, content, nonce, source_path, content_hash, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (doc_id, name, encrypted_content, doc_nonce, source_path, content_hash, now.isoformat(), now.isoformat(), json.dumps(metadata)))
                logger.info(f"Added new document: {doc_id}")

            # Create chunks
            chunk_texts = self._chunk_text(content)
            chunks = []

            for i, (chunk_text, start, end) in enumerate(chunk_texts):
                chunk = Chunk(
                    id=str(uuid.uuid4()),
                    document_id=doc_id,
                    content=chunk_text,
                    index=i,
                    start_char=start,
                    end_char=end,
                    metadata={}
                )
                chunks.append(chunk)

            # Generate embeddings in batch (from plaintext, before encryption)
            if chunks:
                chunk_contents = [c.content for c in chunks]
                embeddings = self.embedding_engine.embed_documents(
                    chunk_contents,
                    show_progress=len(chunks) > 10
                )

                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding
                    # Encrypt chunk content with chunk_id as associated data
                    encrypted_chunk, chunk_nonce = self._encrypt(chunk.content, chunk.id)
                    conn.execute("""
                        INSERT INTO chunks (id, document_id, content, nonce, chunk_index, start_char, end_char, embedding, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        chunk.id,
                        chunk.document_id,
                        encrypted_chunk,
                        chunk_nonce,
                        chunk.index,
                        chunk.start_char,
                        chunk.end_char,
                        embedding.tobytes(),
                        json.dumps(chunk.metadata)
                    ))

            conn.commit()

        # Add embeddings to HNSW index for fast search
        if self._vector_index is not None and chunks:
            chunk_ids = [c.id for c in chunks]
            chunk_embeddings = np.array([c.embedding for c in chunks if c.embedding is not None])
            if len(chunk_embeddings) > 0:
                self._vector_index.add(chunk_ids, chunk_embeddings)
                self._save_vector_index()

        doc = Document(
            id=doc_id,
            name=name,
            content=content,  # Return plaintext to caller
            source_path=source_path,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
            metadata=metadata,
            chunks=chunks
        )

        logger.info(f"Indexed document '{name}' with {len(chunks)} encrypted chunks")
        return doc

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = SIMILARITY_THRESHOLD,
        document_ids: Optional[List[str]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """
        Search for relevant chunks with on-demand decryption.

        Uses HNSW index for fast approximate nearest neighbor search (10-30x faster),
        then decrypts matching chunk content before returning results.

        Args:
            query: Search query
            top_k: Maximum number of results
            threshold: Minimum similarity score
            document_ids: Optional list of document IDs to search
            metadata_filter: Optional metadata filter

        Returns:
            List of RetrievalResult objects sorted by relevance (with decrypted content)
        """
        query_embedding = self.embedding_engine.embed_query(query)

        # Use HNSW index for fast search if available and no document filter
        if self._vector_index is not None and self._vector_index.size > 0 and not document_ids:
            return self._search_hnsw(query_embedding, top_k, threshold, metadata_filter)

        # Fall back to brute-force search (for filtered queries or when HNSW unavailable)
        return self._search_brute_force(query_embedding, top_k, threshold, document_ids, metadata_filter)

    def _search_hnsw(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        threshold: float,
        metadata_filter: Optional[Dict[str, Any]]
    ) -> List[RetrievalResult]:
        """
        Fast search using HNSW index.

        10-30x faster than brute-force at scale.
        """
        # Search more candidates to account for threshold/metadata filtering
        search_k = min(top_k * 3, self._vector_index.size)
        candidates = self._vector_index.search(query_embedding, top_k=search_k)

        if not candidates:
            return []

        # Get chunk details from SQLite
        chunk_ids = [c[0] for c in candidates]
        score_map = {c[0]: c[1] for c in candidates}

        placeholders = ",".join("?" * len(chunk_ids))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"""
                SELECT c.id, c.document_id, c.content, c.nonce, c.chunk_index,
                       c.start_char, c.end_char, c.metadata, d.name as document_name
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.id IN ({placeholders})
            """, chunk_ids)
            rows = cursor.fetchall()

        results = []
        decryption_errors = []

        for row in rows:
            chunk_id, doc_id, encrypted_content, nonce, idx, start, end, meta_str, doc_name = row
            score = score_map.get(chunk_id, 0.0)

            if score < threshold:
                continue

            # Apply metadata filter
            chunk_meta = json.loads(meta_str)
            if metadata_filter:
                skip = False
                for key, value in metadata_filter.items():
                    if chunk_meta.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue

            # Decrypt chunk content
            try:
                decrypted_content = self._decrypt(encrypted_content, nonce, chunk_id)
            except Exception as e:
                logger.error(f"Failed to decrypt chunk {chunk_id}: {e}")
                decryption_errors.append({"chunk_id": chunk_id, "error": str(e)})
                continue

            chunk = Chunk(
                id=chunk_id,
                document_id=doc_id,
                content=decrypted_content,
                index=idx,
                start_char=start,
                end_char=end,
                embedding=None,  # Not needed for results
                metadata=chunk_meta
            )

            results.append(RetrievalResult(
                chunk=chunk,
                score=score,
                document_name=doc_name,
                document_id=doc_id
            ))

        # Report decryption errors
        if decryption_errors:
            logger.warning(
                f"HNSW search completed with {len(decryption_errors)} decryption errors. "
                f"Consider rebuilding the index."
            )
            self._last_search_errors = decryption_errors

        # Sort by score and limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _search_brute_force(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        threshold: float,
        document_ids: Optional[List[str]],
        metadata_filter: Optional[Dict[str, Any]]
    ) -> List[RetrievalResult]:
        """
        Brute-force search (fallback for filtered queries).
        """
        with sqlite3.connect(self.db_path) as conn:
            sql = """
                SELECT c.id, c.document_id, c.content, c.nonce, c.chunk_index,
                       c.start_char, c.end_char, c.embedding, c.metadata,
                       d.name as document_name
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
            """
            params: List[Any] = []

            conditions = []
            if document_ids:
                placeholders = ",".join("?" * len(document_ids))
                conditions.append(f"c.document_id IN ({placeholders})")
                params.extend(document_ids)

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            return []

        results = []
        decryption_errors = []

        for row in rows:
            chunk_id, doc_id, encrypted_content, nonce, idx, start, end, emb_bytes, meta_str, doc_name = row

            embedding = np.frombuffer(emb_bytes, dtype=np.float32)
            score = float(np.dot(embedding, query_embedding))

            if score < threshold:
                continue

            # Apply metadata filter
            chunk_meta = json.loads(meta_str)
            if metadata_filter:
                skip = False
                for key, value in metadata_filter.items():
                    if chunk_meta.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue

            # Decrypt chunk content
            try:
                decrypted_content = self._decrypt(encrypted_content, nonce, chunk_id)
            except Exception as e:
                logger.error(f"Failed to decrypt chunk {chunk_id}: {e}")
                decryption_errors.append({"chunk_id": chunk_id, "error": str(e)})
                continue

            chunk = Chunk(
                id=chunk_id,
                document_id=doc_id,
                content=decrypted_content,
                index=idx,
                start_char=start,
                end_char=end,
                embedding=embedding,
                metadata=chunk_meta
            )

            results.append(RetrievalResult(
                chunk=chunk,
                score=score,
                document_name=doc_name,
                document_id=doc_id
            ))

        # Report decryption errors
        if decryption_errors:
            logger.warning(
                f"Brute-force search completed with {len(decryption_errors)} decryption errors. "
                f"Consider rebuilding the index."
            )
            self._last_search_errors = decryption_errors

        # Sort by score and limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def get_context(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        max_tokens: int = 2000,
        include_metadata: bool = False
    ) -> str:
        """
        Get formatted context for a query.

        Args:
            query: Search query
            top_k: Maximum number of chunks
            max_tokens: Approximate maximum tokens in context
            include_metadata: Whether to include document metadata

        Returns:
            Formatted context string
        """
        results = self.search(query, top_k=top_k)

        if not results:
            return ""

        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4  # Rough token-to-char conversion

        for result in results:
            if total_chars >= max_chars:
                break

            part = f"[From: {result.document_name}]\n{result.chunk.content}"
            if include_metadata and result.chunk.metadata:
                part += f"\nMetadata: {json.dumps(result.chunk.metadata)}"

            context_parts.append(part)
            total_chars += len(part)

        return "\n\n---\n\n".join(context_parts)

    def delete_document(self, document_id: str) -> bool:
        """
        Delete a document and its chunks.

        Args:
            document_id: Document ID to delete

        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM documents WHERE id = ?",
                (document_id,)
            )
            row = cursor.fetchone()

            if not row:
                return False

            name = row[0]

            # Get chunk IDs for HNSW removal
            cursor = conn.execute(
                "SELECT id FROM chunks WHERE document_id = ?",
                (document_id,)
            )
            chunk_ids = [r[0] for r in cursor.fetchall()]

            # Remove from HNSW index
            if self._vector_index is not None and chunk_ids:
                self._vector_index.remove(chunk_ids)
                self._save_vector_index()

            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()

            logger.info(f"Deleted document: {name} ({document_id})")
            return True

    def list_documents(self) -> List[Dict[str, Any]]:
        """
        List all documents.

        Returns:
            List of document info dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT d.id, d.name, d.source_path, d.content_hash,
                       d.created_at, d.updated_at, d.metadata,
                       COUNT(c.id) as chunk_count
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                GROUP BY d.id
                ORDER BY d.updated_at DESC
            """)

            documents = []
            for row in cursor.fetchall():
                doc_id, name, source, hash_, created, updated, meta_str, chunk_count = row
                documents.append({
                    "id": doc_id,
                    "name": name,
                    "source_path": source,
                    "content_hash": hash_,
                    "created_at": created,
                    "updated_at": updated,
                    "metadata": json.loads(meta_str),
                    "chunk_count": chunk_count
                })

            return documents

    def get_document(self, document_id: str) -> Optional[Document]:
        """
        Get a document by ID with decrypted content.

        Args:
            document_id: Document ID

        Returns:
            Document object with decrypted content, or None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, name, content, nonce, source_path, content_hash, created_at, updated_at, metadata "
                "FROM documents WHERE id = ?",
                (document_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            doc_id, name, encrypted_content, doc_nonce, source, hash_, created, updated, meta_str = row

            # Decrypt document content
            try:
                content = self._decrypt(encrypted_content, doc_nonce, doc_id)
            except Exception as e:
                logger.error(f"Failed to decrypt document {doc_id}: {e}")
                return None

            # Get chunks with nonces
            cursor = conn.execute(
                "SELECT id, document_id, content, nonce, chunk_index, start_char, end_char, embedding, metadata "
                "FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                (doc_id,)
            )

            chunks = []
            for chunk_row in cursor.fetchall():
                c_id, c_doc, c_encrypted, c_nonce, c_idx, c_start, c_end, c_emb, c_meta = chunk_row
                # Decrypt chunk content
                try:
                    c_content = self._decrypt(c_encrypted, c_nonce, c_id)
                except Exception as e:
                    logger.error(f"Failed to decrypt chunk {c_id}: {e}")
                    continue

                chunks.append(Chunk(
                    id=c_id,
                    document_id=c_doc,
                    content=c_content,
                    index=c_idx,
                    start_char=c_start,
                    end_char=c_end,
                    embedding=np.frombuffer(c_emb, dtype=np.float32) if c_emb else None,
                    metadata=json.loads(c_meta)
                ))

            return Document(
                id=doc_id,
                name=name,
                content=content,
                source_path=source,
                content_hash=hash_,
                created_at=datetime.fromisoformat(created),
                updated_at=datetime.fromisoformat(updated),
                metadata=json.loads(meta_str),
                chunks=chunks
            )

    def stats(self) -> Dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Dictionary with index stats
        """
        with sqlite3.connect(self.db_path) as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            # Note: content is encrypted, so LENGTH gives ciphertext size (slightly larger than plaintext)
            total_encrypted_bytes = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM documents"
            ).fetchone()[0]

        hnsw_stats = {}
        if self._vector_index is not None:
            hnsw_stats = {
                "hnsw_enabled": True,
                "hnsw_size": self._vector_index.size,
            }
        else:
            hnsw_stats = {"hnsw_enabled": False}

        # Avoid lazy-loading the embedding model just to show stats in UI.
        embedding_dimension = getattr(self.embedding_engine, "_dimension", None)
        if embedding_dimension is None and self._vector_index is not None:
            embedding_dimension = getattr(self._vector_index, "dimension", None)
        if embedding_dimension is None:
            embedding_dimension = 0

        return {
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "total_encrypted_bytes": total_encrypted_bytes,
            "embedding_dimension": int(embedding_dimension),
            "embedding_model": self.embedding_engine.model_name,
            "db_path": str(self.db_path),
            "encrypted": True,
            **hnsw_stats,
        }

    def clear(self):
        """Clear all documents, chunks, and HNSW index."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            conn.commit()

        # Clear HNSW index
        if self._vector_index is not None:
            self._vector_index.clear()
            self._save_vector_index()

        logger.info("Cleared RAG index and HNSW index")

    def rebuild_hnsw_index(self):
        """Rebuild the HNSW index from SQLite data."""
        if self._vector_index is None:
            logger.warning("HNSW index not enabled")
            return

        self._rebuild_vector_index()
        logger.info("Rebuilt HNSW index")

    def close(self):
        """Close index, save HNSW, and securely zero master key."""
        # Save HNSW index before closing
        if self._vector_index is not None:
            self._save_vector_index()

        if self._master_key is not None:
            # Zero every byte in place
            for i in range(len(self._master_key)):
                self._master_key[i] = 0
            self._master_key = None

        # Clear cipher reference
        self._cipher = None

        logger.info("Closed RAGIndex and zeroed master key")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures key is zeroed."""
        self.close()
        return False
