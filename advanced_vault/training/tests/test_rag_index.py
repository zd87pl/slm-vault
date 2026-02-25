"""
Tests for RAG Index

Comprehensive tests for document indexing, chunking, embedding, and retrieval.
Now includes encryption testing with ChaCha20-Poly1305.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np

# Check if sentence-transformers is available
SENTENCE_TRANSFORMERS_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    pass


def generate_test_key() -> bytes:
    """Generate a random 32-byte key for testing."""
    return os.urandom(32)


class TestRAGIndexBasic(unittest.TestCase):
    """Basic RAG index tests that don't require sentence-transformers."""

    def test_chunk_dataclass(self):
        """Test Chunk dataclass creation and serialization."""
        from advanced_vault.training.rag_index import Chunk

        chunk = Chunk(
            id="chunk-123",
            document_id="doc-456",
            content="This is test content.",
            index=0,
            start_char=0,
            end_char=21,
            metadata={"page": 1}
        )

        self.assertEqual(chunk.id, "chunk-123")
        self.assertEqual(chunk.document_id, "doc-456")
        self.assertEqual(chunk.content, "This is test content.")

        # Test serialization
        d = chunk.to_dict()
        self.assertEqual(d["id"], "chunk-123")
        self.assertEqual(d["metadata"]["page"], 1)

    def test_document_dataclass(self):
        """Test Document dataclass creation and hash generation."""
        from advanced_vault.training.rag_index import Document

        doc = Document(
            id="doc-123",
            name="test.pdf",
            content="Document content here."
        )

        self.assertEqual(doc.id, "doc-123")
        self.assertEqual(doc.name, "test.pdf")
        self.assertIsNotNone(doc.content_hash)
        self.assertEqual(len(doc.content_hash), 64)  # SHA256 hex

        # Test serialization
        d = doc.to_dict()
        self.assertEqual(d["name"], "test.pdf")
        self.assertIn("created_at", d)

    def test_retrieval_result_dataclass(self):
        """Test RetrievalResult dataclass."""
        from advanced_vault.training.rag_index import Chunk, RetrievalResult

        chunk = Chunk(
            id="chunk-1",
            document_id="doc-1",
            content="Test content",
            index=0,
            start_char=0,
            end_char=12
        )

        result = RetrievalResult(
            chunk=chunk,
            score=0.85,
            document_name="test.pdf",
            document_id="doc-1"
        )

        self.assertEqual(result.score, 0.85)
        self.assertEqual(result.document_name, "test.pdf")

        # Test serialization
        d = result.to_dict()
        self.assertEqual(d["score"], 0.85)
        self.assertEqual(d["content"], "Test content")


class TestChunking(unittest.TestCase):
    """Test text chunking functionality."""

    def test_chunk_short_text(self):
        """Test chunking text shorter than chunk size."""
        from advanced_vault.training.rag_index import RAGIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use mock embedding engine
            with patch('advanced_vault.training.rag_index.EmbeddingEngine') as mock_engine:
                mock_instance = MagicMock()
                mock_instance.dimension = 384
                mock_instance.embed_documents.return_value = np.random.rand(1, 384).astype(np.float32)
                mock_engine.return_value = mock_instance

                index = RAGIndex(
                    master_key=generate_test_key(),
                    db_path=f"{tmpdir}/rag.db",
                    chunk_size=500
                )

                chunks = index._chunk_text("Short text.")
                self.assertEqual(len(chunks), 1)
                self.assertEqual(chunks[0][0], "Short text.")

    def test_chunk_long_text(self):
        """Test chunking text longer than chunk size."""
        from advanced_vault.training.rag_index import RAGIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('advanced_vault.training.rag_index.EmbeddingEngine') as mock_engine:
                mock_instance = MagicMock()
                mock_instance.dimension = 384
                mock_engine.return_value = mock_instance

                index = RAGIndex(
                    master_key=generate_test_key(),
                    db_path=f"{tmpdir}/rag.db",
                    chunk_size=50,  # 200 chars with 4x multiplier
                    chunk_overlap=10  # 40 chars overlap
                )

                # Create text with clear sentence boundaries
                text = "This is sentence one. " * 10 + "This is sentence two. " * 10

                chunks = index._chunk_text(text)

                self.assertGreater(len(chunks), 1)

                # Verify chunks don't exceed size (approximately)
                for chunk_text, start, end in chunks:
                    self.assertLessEqual(len(chunk_text), index.chunk_size + 50)

    def test_chunk_preserves_sentence_boundaries(self):
        """Test that chunking prefers sentence boundaries."""
        from advanced_vault.training.rag_index import RAGIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('advanced_vault.training.rag_index.EmbeddingEngine') as mock_engine:
                mock_instance = MagicMock()
                mock_instance.dimension = 384
                mock_engine.return_value = mock_instance

                index = RAGIndex(
                    master_key=generate_test_key(),
                    db_path=f"{tmpdir}/rag.db",
                    chunk_size=20,  # 80 chars
                    chunk_overlap=5
                )

                text = "First sentence. Second sentence. Third sentence. Fourth sentence."

                chunks = index._chunk_text(text)

                # Chunks should try to end at periods
                for chunk_text, _, _ in chunks[:-1]:  # Except possibly the last
                    # Most chunks should end with punctuation
                    if len(chunk_text) > 10:
                        self.assertTrue(
                            chunk_text.rstrip().endswith(('.', '!', '?')) or
                            len(chunk_text) < 20,
                            f"Chunk doesn't end at sentence: {chunk_text}"
                        )


@unittest.skipUnless(SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not available")
class TestRAGIndexWithEmbeddings(unittest.TestCase):
    """Tests that require sentence-transformers."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = f"{self.tmpdir}/test_rag.db"
        self.master_key = generate_test_key()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_and_search_document(self):
        """Test adding a document and searching for it with encryption."""
        from advanced_vault.training.rag_index import RAGIndex

        index = RAGIndex(
            master_key=self.master_key,
            db_path=self.db_path,
            chunk_size=100
        )

        # Add document
        doc = index.add_document(
            name="test_doc.txt",
            content="Python is a programming language. It is widely used for machine learning.",
            metadata={"type": "test"}
        )

        self.assertIsNotNone(doc.id)
        self.assertEqual(doc.name, "test_doc.txt")
        self.assertGreater(len(doc.chunks), 0)

        # Search (should decrypt content automatically)
        results = index.search("programming language", top_k=5)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].document_name, "test_doc.txt")
        self.assertGreater(results[0].score, 0.3)
        # Verify decrypted content is readable
        self.assertIn("programming", results[0].chunk.content.lower())

    def test_deduplication(self):
        """Test document deduplication via content hash."""
        from advanced_vault.training.rag_index import RAGIndex

        index = RAGIndex(master_key=self.master_key, db_path=self.db_path)

        content = "This is the same content."

        # Add document
        doc1 = index.add_document(name="doc1.txt", content=content)

        # Add same content again with different name
        doc2 = index.add_document(name="doc2.txt", content=content)

        # Should be same document ID (updated)
        self.assertEqual(doc1.id, doc2.id)

        # Should only have one document
        docs = index.list_documents()
        self.assertEqual(len(docs), 1)

    def test_delete_document(self):
        """Test deleting a document."""
        from advanced_vault.training.rag_index import RAGIndex

        index = RAGIndex(master_key=self.master_key, db_path=self.db_path)

        doc = index.add_document(
            name="to_delete.txt",
            content="This will be deleted."
        )

        # Verify it exists
        self.assertEqual(len(index.list_documents()), 1)

        # Delete
        success = index.delete_document(doc.id)
        self.assertTrue(success)

        # Verify it's gone
        self.assertEqual(len(index.list_documents()), 0)

        # Delete non-existent
        success = index.delete_document("non-existent-id")
        self.assertFalse(success)

    def test_get_context(self):
        """Test getting formatted context for a query."""
        from advanced_vault.training.rag_index import RAGIndex

        index = RAGIndex(master_key=self.master_key, db_path=self.db_path)

        index.add_document(
            name="context_test.txt",
            content="Machine learning is a subset of artificial intelligence. "
                    "Deep learning is a subset of machine learning."
        )

        context = index.get_context("what is deep learning", top_k=3)

        self.assertIn("context_test.txt", context)
        self.assertIn("deep learning", context.lower())

    def test_stats(self):
        """Test index statistics."""
        from advanced_vault.training.rag_index import RAGIndex

        index = RAGIndex(master_key=self.master_key, db_path=self.db_path)

        # Empty stats
        stats = index.stats()
        self.assertEqual(stats["document_count"], 0)
        self.assertEqual(stats["chunk_count"], 0)
        self.assertTrue(stats["encrypted"])

        # Add document
        index.add_document(
            name="stats_test.txt",
            content="Content for stats testing. " * 10
        )

        stats = index.stats()
        self.assertEqual(stats["document_count"], 1)
        self.assertGreater(stats["chunk_count"], 0)
        self.assertEqual(stats["embedding_dimension"], 384)

    def test_clear(self):
        """Test clearing the index."""
        from advanced_vault.training.rag_index import RAGIndex

        index = RAGIndex(master_key=self.master_key, db_path=self.db_path)

        index.add_document(name="doc1.txt", content="Content 1")
        index.add_document(name="doc2.txt", content="Content 2")

        self.assertEqual(len(index.list_documents()), 2)

        index.clear()

        self.assertEqual(len(index.list_documents()), 0)
        self.assertEqual(index.stats()["chunk_count"], 0)

    def test_encryption_verification(self):
        """Test that content is actually encrypted in the database."""
        from advanced_vault.training.rag_index import RAGIndex
        import sqlite3

        index = RAGIndex(master_key=self.master_key, db_path=self.db_path)

        secret_content = "This is my super secret document content!"
        index.add_document(name="secret.txt", content=secret_content)

        # Read raw database to verify content is not plaintext
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT content FROM documents")
            row = cursor.fetchone()
            raw_content = row[0]

            # Content should be bytes (encrypted), not the plaintext string
            self.assertIsInstance(raw_content, bytes)
            # Plaintext should not be visible in raw content
            self.assertNotIn(secret_content.encode(), raw_content)

            # Check chunks too
            cursor = conn.execute("SELECT content FROM chunks")
            for row in cursor.fetchall():
                self.assertIsInstance(row[0], bytes)
                self.assertNotIn(b"secret", row[0])

    def test_wrong_key_fails_decryption(self):
        """Test that wrong key cannot decrypt content."""
        from advanced_vault.training.rag_index import RAGIndex

        # Create index with one key
        index1 = RAGIndex(master_key=self.master_key, db_path=self.db_path)
        index1.add_document(name="test.txt", content="Secret content")
        index1.close()

        # Try to read with different key
        wrong_key = generate_test_key()
        index2 = RAGIndex(master_key=wrong_key, db_path=self.db_path)

        # Search should fail to decrypt (returns empty or logs error)
        results = index2.search("Secret")
        # Results should be empty because decryption fails
        self.assertEqual(len(results), 0)

        # get_document should also fail
        docs = index2.list_documents()
        if docs:
            doc = index2.get_document(docs[0]["id"])
            self.assertIsNone(doc)  # Should return None on decryption failure

    def test_context_manager(self):
        """Test context manager for secure key cleanup."""
        from advanced_vault.training.rag_index import RAGIndex

        with RAGIndex(master_key=self.master_key, db_path=self.db_path) as index:
            index.add_document(name="test.txt", content="Test content")
            self.assertIsNotNone(index._master_key)

        # After context exit, key should be zeroed
        self.assertIsNone(index._master_key)
        self.assertIsNone(index._cipher)


class TestEmbeddingEngine(unittest.TestCase):
    """Tests for the embedding engine."""

    @unittest.skipUnless(SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not available")
    def test_embed_single_text(self):
        """Test embedding a single text."""
        from advanced_vault.training.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()

        embedding = engine.embed("Hello, world!")

        self.assertEqual(embedding.shape, (384,))  # MiniLM dimension
        self.assertAlmostEqual(np.linalg.norm(embedding), 1.0, places=5)

    @unittest.skipUnless(SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not available")
    def test_embed_multiple_texts(self):
        """Test embedding multiple texts."""
        from advanced_vault.training.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()

        texts = ["First text", "Second text", "Third text"]
        embeddings = engine.embed(texts)

        self.assertEqual(embeddings.shape, (3, 384))

    @unittest.skipUnless(SENTENCE_TRANSFORMERS_AVAILABLE, "sentence-transformers not available")
    def test_similarity(self):
        """Test similarity computation."""
        from advanced_vault.training.embeddings import EmbeddingEngine

        engine = EmbeddingEngine()

        query = engine.embed("programming language")
        docs = engine.embed([
            "Python is a programming language",
            "The weather is nice today",
            "Cooking recipes are fun"
        ])

        similarities = engine.similarity(query, docs)

        self.assertEqual(len(similarities), 3)
        # Programming language should be most similar to first doc
        self.assertEqual(np.argmax(similarities), 0)

    def test_embedding_cache(self):
        """Test embedding cache behavior."""
        from advanced_vault.training.embeddings import EmbeddingEngine

        with patch('advanced_vault.training.embeddings.SentenceTransformer') as mock_st:
            mock_model = MagicMock()
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_model.encode.return_value = np.random.rand(1, 384).astype(np.float32)
            mock_st.return_value = mock_model

            engine = EmbeddingEngine()

            # First call
            engine.embed("test text", use_cache=True)
            call_count = mock_model.encode.call_count

            # Second call with same text should use cache
            engine.embed("test text", use_cache=True)
            self.assertEqual(mock_model.encode.call_count, call_count)

            # Cache size should be 1
            self.assertEqual(engine.cache_size, 1)

            # Clear cache
            engine.clear_cache()
            self.assertEqual(engine.cache_size, 0)


if __name__ == "__main__":
    unittest.main()
