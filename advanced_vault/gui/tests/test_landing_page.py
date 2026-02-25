"""
Tests for the agent-first landing page and RAG integration.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def generate_test_key() -> bytes:
    """Generate a random 32-byte key for testing."""
    return os.urandom(32)


class TestRAGHelpers(unittest.TestCase):
    """Test the RAG helper methods used by the landing page."""

    def test_get_rag_stats_no_index(self):
        """RAG stats return zeros when no index exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate the _get_rag_stats method
            try:
                from advanced_vault.training import RAGIndex
                rag = RAGIndex(
                    master_key=generate_test_key(),
                    db_path=str(Path(tmpdir) / "rag.db")
                )
                stats = rag.stats()
                self.assertEqual(stats["document_count"], 0)
                self.assertEqual(stats["chunk_count"], 0)
            except ImportError:
                self.skipTest("sentence-transformers not available")

    def test_get_rag_stats_with_mock(self):
        """RAG stats return expected structure with mock."""
        try:
            import advanced_vault.training.rag_index  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            self.skipTest("training module dependencies not available")
        with patch('advanced_vault.training.rag_index.EmbeddingEngine') as mock_engine:
            import numpy as np
            mock_instance = MagicMock()
            mock_instance.dimension = 384
            mock_instance.embed_documents.return_value = np.random.rand(1, 384).astype(np.float32)
            mock_engine.return_value = mock_instance

            from advanced_vault.training import RAGIndex
            with tempfile.TemporaryDirectory() as tmpdir:
                rag = RAGIndex(
                    master_key=generate_test_key(),
                    db_path=str(Path(tmpdir) / "rag.db")
                )
                stats = rag.stats()
                self.assertIn("document_count", stats)
                self.assertIn("chunk_count", stats)
                self.assertEqual(stats["document_count"], 0)

    def test_get_rag_documents_empty(self):
        """RAG documents list is empty when no documents indexed."""
        try:
            import advanced_vault.training.rag_index  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            self.skipTest("training module dependencies not available")
        with patch('advanced_vault.training.rag_index.EmbeddingEngine') as mock_engine:
            mock_instance = MagicMock()
            mock_instance.dimension = 384
            mock_engine.return_value = mock_instance

            from advanced_vault.training import RAGIndex
            with tempfile.TemporaryDirectory() as tmpdir:
                rag = RAGIndex(
                    master_key=generate_test_key(),
                    db_path=str(Path(tmpdir) / "rag.db")
                )
                docs = rag.list_documents()
                self.assertEqual(len(docs), 0)


class TestDocumentIndexing(unittest.TestCase):
    """Test document indexing through the LocalAgent."""

    def test_index_document_via_agent(self):
        """Test indexing a document through LocalAgent.add_document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_rag = MagicMock()
            mock_doc = MagicMock()
            mock_doc.id = "doc-123"
            mock_doc.name = "test.pdf"
            mock_doc.chunks = [MagicMock(), MagicMock(), MagicMock()]
            mock_rag.add_document.return_value = mock_doc

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                agent = LocalAgent(vault_path=tmpdir)
                result = agent.add_document(
                    name="test.pdf",
                    content="This is a test document with important information."
                )

                self.assertTrue(result.get("success"))
                self.assertEqual(result["id"], "doc-123")
                self.assertEqual(result["chunks"], 3)

    def test_index_document_no_rag(self):
        """Test indexing fails gracefully when RAG is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            with patch.object(LocalAgent, '_get_rag_index', return_value=None):
                agent = LocalAgent(vault_path=tmpdir)
                result = agent.add_document(name="test.pdf", content="Content")
                self.assertIn("error", result)


class TestLocalAgentChat(unittest.TestCase):
    """Test the local agent query path used by _send_chat_message."""

    def test_query_returns_answer_with_sources(self):
        """Test that agent query returns answer with source documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_chunk = MagicMock()
            mock_chunk.content = "Revenue was $4.2M in Q3."

            mock_result = MagicMock()
            mock_result.chunk = mock_chunk
            mock_result.document_name = "q3_report.pdf"
            mock_result.score = 0.92

            mock_rag = MagicMock()
            mock_rag.search.return_value = [mock_result]

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    result = agent.query("What was Q3 revenue?")

                    self.assertTrue(result["rag_used"])
                    self.assertEqual(len(result["sources"]), 1)
                    self.assertEqual(result["sources"][0]["document"], "q3_report.pdf")
                    # Without model, answer should contain context
                    self.assertIn("Revenue", result.get("answer", ""))

    def test_query_no_results(self):
        """Test query with no matching documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_rag = MagicMock()
            mock_rag.search.return_value = []

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    result = agent.query("What is quantum computing?")

                    self.assertFalse(result["rag_used"])
                    self.assertIsNotNone(result.get("error"))


if __name__ == "__main__":
    unittest.main()
