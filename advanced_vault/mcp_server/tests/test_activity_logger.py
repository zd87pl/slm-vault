"""
Tests for Activity Logger with search, filter, and export.
"""

import json
import tempfile
import unittest
from pathlib import Path


class TestActivityLogger(unittest.TestCase):
    """Test activity logging, search, and export."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        from advanced_vault.mcp_server.activity_logger import ActivityLogger
        self.logger = ActivityLogger(vault_path=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_log_and_retrieve(self):
        """Test logging an activity and retrieving it."""
        self.logger.log_access(
            tool_name="agent_query",
            app_identifier="claude-desktop",
            query_preview="What is the revenue?",
            granted=True,
            result_summary="Found 3 relevant chunks",
        )

        activities = self.logger.get_recent_activity(limit=10)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["tool_name"], "agent_query")
        self.assertTrue(activities[0]["granted"])
        self.assertEqual(activities[0]["result_summary"], "Found 3 relevant chunks")

    def test_log_multiple_entries(self):
        """Test logging multiple activities."""
        for i in range(5):
            self.logger.log_access(
                tool_name=f"tool_{i}",
                app_identifier="claude",
                granted=i % 2 == 0,
            )

        activities = self.logger.get_recent_activity(limit=10)
        self.assertEqual(len(activities), 5)

    def test_search_by_query(self):
        """Test searching activity by text query."""
        self.logger.log_access(
            tool_name="agent_query",
            app_identifier="claude",
            query_preview="What is revenue?",
            granted=True,
        )
        self.logger.log_access(
            tool_name="vault_store",
            app_identifier="cursor",
            query_preview="Store API key",
            granted=True,
        )

        results = self.logger.search_activity(query="revenue")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tool_name"], "agent_query")

    def test_search_by_tool_filter(self):
        """Test filtering by tool name."""
        self.logger.log_access(tool_name="agent_query", app_identifier="claude", granted=True)
        self.logger.log_access(tool_name="vault_store", app_identifier="claude", granted=True)
        self.logger.log_access(tool_name="agent_query", app_identifier="cursor", granted=False)

        results = self.logger.search_activity(tool_filter="agent_query")
        self.assertEqual(len(results), 2)

    def test_search_by_granted_filter(self):
        """Test filtering by granted status."""
        self.logger.log_access(tool_name="a", app_identifier="claude", granted=True)
        self.logger.log_access(tool_name="b", app_identifier="claude", granted=False)
        self.logger.log_access(tool_name="c", app_identifier="claude", granted=True)

        granted = self.logger.search_activity(granted_filter=True)
        self.assertEqual(len(granted), 2)

        denied = self.logger.search_activity(granted_filter=False)
        self.assertEqual(len(denied), 1)

    def test_export_csv(self):
        """Test exporting activities to CSV."""
        self.logger.log_access(
            tool_name="agent_query",
            app_identifier="claude",
            query_preview="Test query",
            granted=True,
            result_summary="Found results",
        )

        csv_str = self.logger.export_csv()
        self.assertIn("timestamp", csv_str)
        self.assertIn("tool_name", csv_str)
        self.assertIn("agent_query", csv_str)
        self.assertIn("Test query", csv_str)

        # Check it's valid CSV
        lines = csv_str.strip().split("\n")
        self.assertEqual(len(lines), 2)  # Header + 1 row

    def test_export_json(self):
        """Test exporting activities to JSON."""
        self.logger.log_access(
            tool_name="agent_query",
            app_identifier="claude",
            granted=True,
        )

        json_str = self.logger.export_json()
        data = json.loads(json_str)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["tool_name"], "agent_query")

    def test_clear_activity(self):
        """Test clearing the activity log."""
        self.logger.log_access(tool_name="a", app_identifier="claude", granted=True)
        self.logger.log_access(tool_name="b", app_identifier="claude", granted=True)

        self.assertEqual(len(self.logger.get_recent_activity()), 2)

        self.logger.clear_activity()
        self.assertEqual(len(self.logger.get_recent_activity()), 0)

    def test_app_name_formatting(self):
        """Test that app identifiers are formatted to friendly names."""
        self.logger.log_access(
            tool_name="agent_query",
            app_identifier="claude-desktop",
            granted=True,
        )

        activities = self.logger.get_recent_activity()
        self.assertIn("Claude", activities[0]["app_name"])
        self.assertIn("MCP", activities[0]["app_name"])

    def test_export_with_provided_activities(self):
        """Test export with explicitly provided activities list."""
        activities = [
            {"timestamp": "2026-01-01T00:00:00", "tool_name": "test", "app_name": "App", "query_preview": "q", "granted": True, "result_summary": "ok"},
        ]

        csv_str = self.logger.export_csv(activities)
        self.assertIn("test", csv_str)

        json_str = self.logger.export_json(activities)
        data = json.loads(json_str)
        self.assertEqual(len(data), 1)


if __name__ == "__main__":
    unittest.main()
