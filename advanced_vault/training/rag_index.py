"""
RAG Index for Enclave.

Provides document chunking, embedding storage, and semantic retrieval.
All data encrypted at rest with ChaCha20-Poly1305 for privacy.

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

logger = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 500  # tokens (approximate)
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_TOP_K = 5
SIMILARITY_THRESHOLD = 0.3

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
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    ):
        """
        Initialize RAG index with encryption.

        Args:
            master_key: 32-byte encryption key for ChaCha20-Poly1305
            db_path: Path to SQLite database
            embedding_engine: Optional embedding engine (created if not provided)
            chunk_size: Target chunk size in characters (approx tokens * 4)
            chunk_overlap: Overlap between chunks

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

        # Track search errors for GUI reporting
        self._last_search_errors: list = []

        logger.info(
            f"Initialized encrypted RAGIndex at {self.db_path} "
            f"(chunk_size={chunk_size}, overlap={chunk_overlap})"
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
        Split text into overlapping chunks.

        Args:
            text: Text to chunk

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
                chunks.append((chunk_text, start, end))

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

        Similarity search uses unencrypted embeddings, then decrypts
        matching chunk content before returning results.

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

        with sqlite3.connect(self.db_path) as conn:
            # Build query - include nonce for decryption
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

        # Compute similarities and decrypt matching content
        results = []
        decryption_errors = []  # Track decryption failures for reporting
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

            # Decrypt chunk content (only for results that pass filters)
            try:
                decrypted_content = self._decrypt(encrypted_content, nonce, chunk_id)
            except Exception as e:
                logger.error(f"Failed to decrypt chunk {chunk_id}: {e}")
                decryption_errors.append({"chunk_id": chunk_id, "error": str(e)})
                continue

        # Report decryption errors if any occurred
        if decryption_errors:
            logger.warning(
                f"Search completed with {len(decryption_errors)} decryption errors. "
                f"This may indicate key corruption or database tampering. "
                f"Consider rebuilding the index."
            )
            # Store last errors for GUI access
            self._last_search_errors = decryption_errors

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

        return {
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "total_encrypted_bytes": total_encrypted_bytes,
            "embedding_dimension": self.embedding_engine.dimension,
            "embedding_model": self.embedding_engine.model_name,
            "db_path": str(self.db_path),
            "encrypted": True,
        }

    def clear(self):
        """Clear all documents and chunks."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            conn.commit()

        logger.info("Cleared RAG index")

    def close(self):
        """Close index and securely zero master key."""
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
