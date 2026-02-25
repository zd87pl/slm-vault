"""
Tests for the RAG -> LocalAgent -> MCP pipeline.

Verifies the complete flow from document indexing through agent query
to MCP tool response.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestRAGToAgentPipeline(unittest.TestCase):
    """Test the full RAG to LocalAgent pipeline."""

    def test_add_document_then_query(self):
        """Document added to RAG can be queried through agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            # Mock RAG index
            mock_chunk = MagicMock()
            mock_chunk.content = "Python is a versatile programming language used for AI."

            mock_result = MagicMock()
            mock_result.chunk = mock_chunk
            mock_result.document_name = "python_guide.pdf"
            mock_result.score = 0.88

            mock_doc = MagicMock()
            mock_doc.id = "doc-1"
            mock_doc.name = "python_guide.pdf"
            mock_doc.chunks = [MagicMock(), MagicMock()]

            mock_rag = MagicMock()
            mock_rag.add_document.return_value = mock_doc
            mock_rag.search.return_value = [mock_result]

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)

                    # Add document
                    add_result = agent.add_document(
                        name="python_guide.pdf",
                        content="Python is a versatile programming language used for AI."
                    )
                    self.assertTrue(add_result["success"])

                    # Query
                    query_result = agent.query("What is Python used for?")
                    self.assertTrue(query_result["rag_used"])
                    self.assertEqual(len(query_result["sources"]), 1)
                    self.assertEqual(query_result["sources"][0]["document"], "python_guide.pdf")
                    self.assertIn("Python", query_result["answer"])

    def test_summarize_with_matching_document(self):
        """Summarize finds and uses matching document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_doc_info = {"id": "doc-1", "name": "report.pdf"}
            mock_full_doc = MagicMock()
            mock_full_doc.content = "Q3 revenue increased by 20% to $4.2M."

            mock_rag = MagicMock()
            mock_rag.list_documents.return_value = [mock_doc_info]
            mock_rag.get_document.return_value = mock_full_doc

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    result = agent.summarize("report")

                    self.assertIsNone(result.get("error"))
                    self.assertEqual(len(result["sources"]), 1)
                    self.assertIn("report.pdf", result["sources"][0]["document"])

    def test_agent_status_reflects_rag(self):
        """Agent status includes RAG index statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_rag = MagicMock()
            mock_rag.stats.return_value = {"document_count": 5, "chunk_count": 42}
            mock_rag.list_documents.return_value = [
                {"name": "doc1.pdf", "chunk_count": 10},
                {"name": "doc2.pdf", "chunk_count": 8},
            ]

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                    agent = LocalAgent(vault_path=tmpdir)
                    status = agent.get_status()

                    self.assertTrue(status["rag_available"])
                    self.assertEqual(status["document_count"], 5)
                    self.assertEqual(status["chunk_count"], 42)
                    self.assertEqual(len(status["documents"]), 2)
                    self.assertTrue(status["ready"])

    def test_delete_document_removes_from_index(self):
        """Deleting a document removes it from the RAG index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.agent import LocalAgent

            mock_rag = MagicMock()
            mock_rag.delete_document.return_value = True

            with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
                agent = LocalAgent(vault_path=tmpdir)
                result = agent.delete_document("doc-123")

                self.assertTrue(result["success"])
                mock_rag.delete_document.assert_called_once_with("doc-123")


class TestConsentEnforcement(unittest.TestCase):
    """Test that consent is enforced in the MCP pipeline."""

    def test_agent_permission_tool_check(self):
        """Permission check blocks denied tools."""
        from advanced_vault.mcp_server.consent import AgentPermission

        perm = AgentPermission(
            agent_id="cursor",
            auto_approve=True,
            denied_tools={"vault_store", "vault_delete"},
        )

        self.assertTrue(perm.can_access_tool("agent_query"))
        self.assertTrue(perm.can_access_tool("agent_summarize"))
        self.assertFalse(perm.can_access_tool("vault_store"))
        self.assertFalse(perm.can_access_tool("vault_delete"))

    def test_agent_permission_document_check(self):
        """Permission check restricts document access."""
        from advanced_vault.mcp_server.consent import AgentPermission

        perm = AgentPermission(
            agent_id="claude",
            auto_approve=True,
            allowed_documents={"public_report.pdf"},
        )

        self.assertTrue(perm.can_access_document("public_report.pdf"))
        self.assertFalse(perm.can_access_document("confidential.pdf"))

    def test_unrestricted_permission(self):
        """Unrestricted permission allows all access."""
        from advanced_vault.mcp_server.consent import AgentPermission, AccessScope

        perm = AgentPermission(
            agent_id="claude",
            auto_approve=True,
            scope=AccessScope.ALL,
        )

        self.assertTrue(perm.can_access_tool("agent_query"))
        self.assertTrue(perm.can_access_tool("vault_store"))
        self.assertTrue(perm.can_access_document("any_doc.pdf"))


class TestActivityLogging(unittest.TestCase):
    """Test that activities are logged during the MCP pipeline."""

    def test_activity_logged_on_access(self):
        """Activity is logged when MCP tool is accessed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.activity_logger import ActivityLogger

            logger = ActivityLogger(vault_path=tmpdir)
            logger.log_access(
                tool_name="agent_query",
                app_identifier="claude-desktop",
                query_preview="What is Python?",
                granted=True,
                result_summary="Found 3 chunks",
            )

            activities = logger.get_recent_activity()
            self.assertEqual(len(activities), 1)
            self.assertEqual(activities[0]["tool_name"], "agent_query")
            self.assertTrue(activities[0]["granted"])

    def test_denied_access_logged(self):
        """Denied access is also logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from advanced_vault.mcp_server.activity_logger import ActivityLogger

            logger = ActivityLogger(vault_path=tmpdir)
            logger.log_access(
                tool_name="vault_store",
                app_identifier="unknown-agent",
                query_preview="Store secret",
                granted=False,
                result_summary="Denied by consent manager",
            )

            activities = logger.get_recent_activity()
            self.assertEqual(len(activities), 1)
            self.assertFalse(activities[0]["granted"])


if __name__ == "__main__":
    unittest.main()
