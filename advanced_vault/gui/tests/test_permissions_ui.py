"""
Tests for permissions management.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


class TestConsentManagerPermissions(unittest.TestCase):
    """Test the enhanced ConsentManager with per-agent permissions."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = self.tmpdir

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_set_and_get_agent_permission(self):
        """Test saving and retrieving agent permission."""
        from advanced_vault.mcp_server.consent import (
            ConsentManager, AgentPermission, AccessScope
        )

        cm = ConsentManager(vault_path=self.vault_path)
        perm = AgentPermission(
            agent_id="claude-desktop",
            auto_approve=True,
            scope=AccessScope.DOCUMENTS,
            allowed_tools={"agent_query", "agent_summarize"},
        )
        cm.set_agent_permission(perm)

        retrieved = cm.get_agent_permission("claude-desktop")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.agent_id, "claude-desktop")
        self.assertTrue(retrieved.auto_approve)
        self.assertEqual(retrieved.scope, AccessScope.DOCUMENTS)
        self.assertIn("agent_query", retrieved.allowed_tools)

    def test_list_agents(self):
        """Test listing registered agents."""
        from advanced_vault.mcp_server.consent import (
            ConsentManager, AgentPermission, AccessScope
        )

        cm = ConsentManager(vault_path=self.vault_path)

        # Initially empty
        agents = cm.list_agents()
        self.assertEqual(len(agents), 0)

        # Add agents
        cm.set_agent_permission(AgentPermission(agent_id="claude", auto_approve=True))
        cm.set_agent_permission(AgentPermission(agent_id="cursor", auto_approve=False))

        agents = cm.list_agents()
        self.assertEqual(len(agents), 2)
        agent_ids = {a["agent_id"] for a in agents}
        self.assertIn("claude", agent_ids)
        self.assertIn("cursor", agent_ids)

    def test_revoke_permission(self):
        """Test revoking an agent's permission."""
        from advanced_vault.mcp_server.consent import (
            ConsentManager, AgentPermission
        )

        cm = ConsentManager(vault_path=self.vault_path)
        cm.set_agent_permission(AgentPermission(agent_id="claude", auto_approve=True))

        self.assertEqual(len(cm.list_agents()), 1)

        cm.revoke_permission("claude")

        self.assertEqual(len(cm.list_agents()), 0)
        self.assertIsNone(cm.get_agent_permission("claude"))

    def test_time_limited_access(self):
        """Test that time-limited permissions expire correctly."""
        from advanced_vault.mcp_server.consent import (
            ConsentManager, AgentPermission
        )

        cm = ConsentManager(vault_path=self.vault_path)

        # Create an already-expired permission
        expired_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        perm = AgentPermission(
            agent_id="claude",
            auto_approve=True,
            expires_at=expired_time,
        )
        cm.set_agent_permission(perm)

        retrieved = cm.get_agent_permission("claude")
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.is_expired())

    def test_tool_restrictions(self):
        """Test that tool restrictions are enforced."""
        from advanced_vault.mcp_server.consent import (
            AgentPermission
        )

        perm = AgentPermission(
            agent_id="cursor",
            auto_approve=True,
            denied_tools={"vault_store", "vault_delete"},
        )

        self.assertTrue(perm.can_access_tool("agent_query"))
        self.assertFalse(perm.can_access_tool("vault_store"))
        self.assertFalse(perm.can_access_tool("vault_delete"))

    def test_document_restrictions(self):
        """Test per-document access control."""
        from advanced_vault.mcp_server.consent import (
            AgentPermission
        )

        perm = AgentPermission(
            agent_id="cursor",
            auto_approve=True,
            allowed_documents={"report.pdf", "notes.txt"},
        )

        self.assertTrue(perm.can_access_document("report.pdf"))
        self.assertTrue(perm.can_access_document("notes.txt"))
        self.assertFalse(perm.can_access_document("secret.pdf"))

    def test_permission_persistence(self):
        """Test that permissions persist to disk."""
        from advanced_vault.mcp_server.consent import (
            ConsentManager, AgentPermission, AccessScope
        )

        # Save permission
        cm1 = ConsentManager(vault_path=self.vault_path)
        cm1.set_agent_permission(AgentPermission(
            agent_id="claude",
            auto_approve=True,
            scope=AccessScope.SECRETS,
        ))

        # Load in new instance
        cm2 = ConsentManager(vault_path=self.vault_path)
        retrieved = cm2.get_agent_permission("claude")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.scope, AccessScope.SECRETS)


if __name__ == "__main__":
    unittest.main()
