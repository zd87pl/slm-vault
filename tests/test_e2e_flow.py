"""
End-to-end tests for the full pipeline:
PDF upload → RAG indexing → MCP query → activity logged.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestEndToEndFlow(unittest.TestCase):
    """Test the complete flow from document upload to query with activity logging."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_document_to_query_pipeline(self):
        """PDF text → RAG index → agent query → answer with sources."""
        from advanced_vault.mcp_server.agent import LocalAgent

        # Mock RAG with realistic behavior
        mock_chunk = MagicMock()
        mock_chunk.content = "Q3 revenue reached $4.2M, a 20% increase year-over-year."

        mock_search_result = MagicMock()
        mock_search_result.chunk = mock_chunk
        mock_search_result.document_name = "q3_report.pdf"
        mock_search_result.score = 0.91

        mock_doc = MagicMock()
        mock_doc.id = "doc-q3"
        mock_doc.name = "q3_report.pdf"
        mock_doc.chunks = [MagicMock(), MagicMock(), MagicMock()]

        mock_rag = MagicMock()
        mock_rag.add_document.return_value = mock_doc
        mock_rag.search.return_value = [mock_search_result]

        with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
            with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                agent = LocalAgent(vault_path=self.tmpdir)

                # Step 1: Index document (simulates PDF text extraction result)
                pdf_text = "Q3 revenue reached $4.2M, a 20% increase year-over-year."
                add_result = agent.add_document(
                    name="q3_report.pdf",
                    content=pdf_text,
                )
                self.assertTrue(add_result["success"])
                self.assertEqual(add_result["chunks"], 3)

                # Step 2: Query the agent
                query_result = agent.query("What was Q3 revenue?")
                self.assertTrue(query_result["rag_used"])
                self.assertEqual(len(query_result["sources"]), 1)
                self.assertEqual(query_result["sources"][0]["document"], "q3_report.pdf")
                self.assertIn("4.2M", query_result["answer"])

    def test_query_with_activity_logging(self):
        """Query through agent → activity is logged."""
        from advanced_vault.mcp_server.activity_logger import ActivityLogger

        logger = ActivityLogger(vault_path=self.tmpdir)

        # Simulate what the MCP server does when a query comes in
        logger.log_access(
            tool_name="agent_query",
            app_identifier="claude-desktop",
            query_preview="What was Q3 revenue?",
            granted=True,
            result_summary="Found 1 relevant chunk from q3_report.pdf",
        )

        activities = logger.get_recent_activity(limit=10)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["tool_name"], "agent_query")
        self.assertTrue(activities[0]["granted"])
        self.assertIn("Q3 revenue", activities[0]["query_preview"])

    def test_consent_blocks_query(self):
        """Denied agent gets blocked and denial is logged."""
        from advanced_vault.mcp_server.consent import AgentPermission
        from advanced_vault.mcp_server.activity_logger import ActivityLogger

        # Agent with restricted tools
        perm = AgentPermission(
            agent_id="untrusted-agent",
            auto_approve=False,
            denied_tools={"agent_query", "agent_summarize"},
        )

        # Check permission before allowing query
        can_query = perm.can_access_tool("agent_query")
        self.assertFalse(can_query)

        # Log the denial
        logger = ActivityLogger(vault_path=self.tmpdir)
        logger.log_access(
            tool_name="agent_query",
            app_identifier="untrusted-agent",
            query_preview="What are the secrets?",
            granted=False,
            result_summary="Denied: tool not allowed",
        )

        activities = logger.get_recent_activity()
        self.assertEqual(len(activities), 1)
        self.assertFalse(activities[0]["granted"])

    def test_document_restriction_enforcement(self):
        """Agent with document restrictions can only access allowed documents."""
        from advanced_vault.mcp_server.consent import AgentPermission

        perm = AgentPermission(
            agent_id="limited-agent",
            auto_approve=True,
            allowed_documents={"public_report.pdf", "faq.txt"},
        )

        # Allowed documents
        self.assertTrue(perm.can_access_document("public_report.pdf"))
        self.assertTrue(perm.can_access_document("faq.txt"))

        # Denied documents
        self.assertFalse(perm.can_access_document("confidential.pdf"))
        self.assertFalse(perm.can_access_document("secrets.txt"))

    def test_full_pipeline_add_query_delete(self):
        """Add document → query → delete document → query returns nothing."""
        from advanced_vault.mcp_server.agent import LocalAgent

        mock_chunk = MagicMock()
        mock_chunk.content = "Important data about project X."

        mock_search_result = MagicMock()
        mock_search_result.chunk = mock_chunk
        mock_search_result.document_name = "project_x.pdf"
        mock_search_result.score = 0.85

        mock_doc = MagicMock()
        mock_doc.id = "doc-px"
        mock_doc.name = "project_x.pdf"
        mock_doc.chunks = [MagicMock()]

        mock_rag = MagicMock()
        mock_rag.add_document.return_value = mock_doc
        mock_rag.search.side_effect = [
            [mock_search_result],  # First query: found
            [],                     # Second query after delete: nothing
        ]
        mock_rag.delete_document.return_value = True

        with patch.object(LocalAgent, '_get_rag_index', return_value=mock_rag):
            with patch.object(LocalAgent, '_get_inference_engine', return_value=None):
                agent = LocalAgent(vault_path=self.tmpdir)

                # Add
                add_result = agent.add_document(name="project_x.pdf", content="Important data about project X.")
                self.assertTrue(add_result["success"])

                # Query - found
                result1 = agent.query("Tell me about project X")
                self.assertTrue(result1["rag_used"])
                self.assertEqual(len(result1["sources"]), 1)

                # Delete
                del_result = agent.delete_document("doc-px")
                self.assertTrue(del_result["success"])

                # Query again - nothing
                result2 = agent.query("Tell me about project X")
                self.assertFalse(result2["rag_used"])

    def test_activity_search_and_export(self):
        """Log multiple activities → search → export CSV and JSON."""
        import json
        from advanced_vault.mcp_server.activity_logger import ActivityLogger

        logger = ActivityLogger(vault_path=self.tmpdir)

        # Log various activities
        logger.log_access(
            tool_name="agent_query",
            app_identifier="claude-desktop",
            query_preview="Revenue question",
            granted=True,
            result_summary="Found 2 chunks",
        )
        logger.log_access(
            tool_name="vault_store",
            app_identifier="cursor",
            query_preview="Store API key",
            granted=True,
            result_summary="Stored successfully",
        )
        logger.log_access(
            tool_name="agent_query",
            app_identifier="unknown-agent",
            query_preview="Unauthorized query",
            granted=False,
            result_summary="Denied",
        )

        # Search
        revenue_results = logger.search_activity(query="Revenue")
        self.assertEqual(len(revenue_results), 1)

        denied_results = logger.search_activity(granted_filter=False)
        self.assertEqual(len(denied_results), 1)

        query_tool_results = logger.search_activity(tool_filter="agent_query")
        self.assertEqual(len(query_tool_results), 2)

        # Export CSV
        csv_str = logger.export_csv()
        self.assertIn("agent_query", csv_str)
        self.assertIn("vault_store", csv_str)
        lines = csv_str.strip().split("\n")
        self.assertEqual(len(lines), 4)  # Header + 3 rows

        # Export JSON
        json_str = logger.export_json()
        data = json.loads(json_str)
        self.assertEqual(len(data), 3)


if __name__ == "__main__":
    unittest.main()
