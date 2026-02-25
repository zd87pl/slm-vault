"""
Tests for Local Agent

Tests for the local agent that synthesizes responses from indexed documents.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestLocalAgentBasic(unittest.TestCase):
    """Basic local agent tests."""

    def test_agent_initialization(self):
        """Test agent initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('advanced_vault.mcp_server.agent.get_agent') as mock_get:
                from advanced_vault.mcp_server.agent import LocalAgent

                agent = LocalAgent(vault_path=tmpdir)

                self.assertEqual(str(agent.vault_path), tmpdir)
                self.assertIsNone(agent._rag_index)
                self.assertIsNone(agent._inference_engine)

    def test_get_status_no_components(self):
        """Test status when no components are loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            # Patch the imports that might fail
            with patch.object(LocalAgent, '_get_rag_index', return_value=None):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    status = agent.get_status()

                    self.assertFalse(status["ready"])
                    self.assertFalse(status["model_loaded"])
                    self.assertFalse(status["rag_available"])
                    self.assertEqual(status["document_count"], 0)

    def test_query_without_rag(self):
        """Test query when RAG is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            with patch.object(LocalAgent, '_get_rag_index', return_value=None):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    result = agent.query("What is Python?")

                    # Should return error since neither RAG nor model is available
                    self.assertIsNotNone(result.get("error"))

    def test_query_with_mock_rag(self):
        """Test query with mocked RAG index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            # Create mock RAG results
            mock_chunk = MagicMock()
            mock_chunk.content = "Python is a programming language."

            mock_result = MagicMock()
            mock_result.chunk = mock_chunk
            mock_result.document_name = "test.pdf"
            mock_result.score = 0.85

            mock_rag = MagicMock()
            mock_rag.search.return_value = [mock_result]

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    result = agent.query("What is Python?")

                    # Should have sources from RAG
                    self.assertTrue(result.get("rag_used"))
                    self.assertEqual(len(result.get("sources", [])), 1)
                    self.assertEqual(result["sources"][0]["document"], "test.pdf")

    def test_summarize_without_rag(self):
        """Test summarize when RAG is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            with patch.object(LocalAgent, '_get_rag_index', return_value=None):
                agent = LocalAgent(vault_path=tmpdir)
                result = agent.summarize("Python")

                self.assertIsNotNone(result.get("error"))
                self.assertIn("RAG index not available", result["error"])

    def test_draft_without_model(self):
        """Test draft when model is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            with patch.object(LocalAgent, '_get_rag_index', return_value=None):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    result = agent.draft("Write an email about the project")

                    self.assertIsNotNone(result.get("error"))

    def test_add_document(self):
        """Test adding a document via agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_doc = MagicMock()
            mock_doc.id = "doc-123"
            mock_doc.name = "test.pdf"
            mock_doc.chunks = [MagicMock(), MagicMock()]

            mock_rag = MagicMock()
            mock_rag.add_document.return_value = mock_doc

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                agent = LocalAgent(vault_path=tmpdir)
                result = agent.add_document(
                    name="test.pdf",
                    content="Test content here."
                )

                self.assertTrue(result.get("success"))
                self.assertEqual(result["id"], "doc-123")
                self.assertEqual(result["chunks"], 2)

    def test_delete_document(self):
        """Test deleting a document via agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_rag = MagicMock()
            mock_rag.delete_document.return_value = True

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                agent = LocalAgent(vault_path=tmpdir)
                result = agent.delete_document("doc-123")

                self.assertTrue(result["success"])
                mock_rag.delete_document.assert_called_once_with("doc-123")


class TestAgentSingleton(unittest.TestCase):
    """Test agent singleton behavior."""

    def test_get_agent_creates_singleton(self):
        """Test that get_agent creates and returns singleton."""
        import advanced_vault.mcp_server.agent as agent_module

        # Reset singleton
        agent_module._agent = None

        with tempfile.TemporaryDirectory() as tmpdir:
            agent1 = agent_module.get_agent(vault_path=tmpdir)
            agent2 = agent_module.get_agent(vault_path=tmpdir)

            self.assertIs(agent1, agent2)

            # Clean up
            agent_module._agent = None


class TestAgentWithInference(unittest.TestCase):
    """Tests with mocked inference engine."""

    def test_query_with_full_pipeline(self):
        """Test query with both RAG and inference mocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            # Mock RAG
            mock_chunk = MagicMock()
            mock_chunk.content = "Python is great for ML."

            mock_result = MagicMock()
            mock_result.chunk = mock_chunk
            mock_result.document_name = "ml_guide.pdf"
            mock_result.score = 0.9

            mock_rag = MagicMock()
            mock_rag.search.return_value = [mock_result]

            # Mock inference
            mock_engine = MagicMock()
            mock_engine.model = MagicMock()
            mock_engine.tokenizer = MagicMock()
            mock_engine.tokenizer.apply_chat_template.return_value = "formatted prompt"
            mock_engine.generate.return_value = "Python is a versatile programming language."
            mock_engine.MLX_MODEL_NAME = "test-model"

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=mock_engine):
                    agent = LocalAgent(vault_path=tmpdir)
                    agent._model_loaded = True

                    result = agent.query("What is Python?")

                    self.assertIsNone(result.get("error"))
                    self.assertTrue(result["rag_used"])
                    self.assertEqual(result["model_used"], "test-model")
                    self.assertIn("versatile", result["answer"])

    def test_summarize_with_inference(self):
        """Test summarize with mocked components."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            # Mock RAG
            mock_rag = MagicMock()
            mock_rag.list_documents.return_value = [
                {"id": "doc-1", "name": "report.pdf"}
            ]

            mock_doc = MagicMock()
            mock_doc.content = "This is a quarterly report. Revenue increased by 20%."
            mock_rag.get_document.return_value = mock_doc

            # Mock inference
            mock_engine = MagicMock()
            mock_engine.model = MagicMock()
            mock_engine.generate.return_value = "Revenue increased by 20% in Q3."

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=mock_engine):
                    agent = LocalAgent(vault_path=tmpdir)
                    agent._model_loaded = True

                    result = agent.summarize("report")

                    self.assertIsNone(result.get("error"))
                    self.assertIn("20%", result["summary"])
                    self.assertEqual(len(result["sources"]), 1)

    def test_draft_with_context(self):
        """Test draft with document context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            # Mock RAG
            mock_chunk = MagicMock()
            mock_chunk.content = "Project deadline is next Friday."

            mock_result = MagicMock()
            mock_result.chunk = mock_chunk
            mock_result.document_name = "project_notes.txt"
            mock_result.score = 0.8

            mock_rag = MagicMock()
            mock_rag.search.return_value = [mock_result]

            # Mock inference
            mock_engine = MagicMock()
            mock_engine.model = MagicMock()
            mock_engine.generate.return_value = "Dear team, the project deadline is Friday."

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=mock_engine):
                    agent = LocalAgent(vault_path=tmpdir)
                    agent._model_loaded = True

                    result = agent.draft("email about project status", style="professional")

                    self.assertIsNone(result.get("error"))
                    self.assertIn("deadline", result["draft"])
                    self.assertEqual(len(result["sources"]), 1)


if __name__ == "__main__":
    unittest.main()
