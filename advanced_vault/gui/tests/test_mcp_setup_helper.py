"""Tests for MCP setup helper."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from advanced_vault.gui.mcp_setup import MCPSetupHelper


class TestMCPSetupHelper(unittest.TestCase):
    """Validate MCP setup behavior and backward compatibility."""

    def test_generate_config_uses_sheriff_server(self):
        helper = MCPSetupHelper(vault_path="~/.vault")
        config = helper.generate_mcp_config()
        self.assertIn("mcpServers", config)
        self.assertIn("sheriff", config["mcpServers"])
        self.assertNotIn("enclave", config["mcpServers"])

    def test_merge_migrates_legacy_server_names(self):
        helper = MCPSetupHelper(vault_path="~/.vault")
        existing = {
            "mcpServers": {
                "enclave": {"command": "old"},
                "personal-vault": {"command": "older"},
                "other": {"command": "keep"},
            }
        }
        merged = helper._merge_mcp_servers(existing, helper.generate_mcp_config())
        self.assertIn("sheriff", merged["mcpServers"])
        self.assertIn("other", merged["mcpServers"])
        self.assertNotIn("enclave", merged["mcpServers"])
        self.assertNotIn("personal-vault", merged["mcpServers"])

    def test_auto_configure_claude_writes_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            helper = MCPSetupHelper(vault_path=tmpdir)
            config_path = Path(tmpdir) / "claude_desktop_config.json"

            with patch.object(helper, "detect_claude_desktop", return_value=True):
                with patch.object(helper, "_resolve_config_path", return_value=config_path):
                    result = helper.auto_configure(target="claude")

            self.assertTrue(result.get("success"))
            self.assertTrue(config_path.exists())
            payload = json.loads(config_path.read_text())
            self.assertIn("sheriff", payload.get("mcpServers", {}))

    def test_auto_configure_chatgpt_reports_unsupported(self):
        helper = MCPSetupHelper(vault_path="~/.vault")
        result = helper.auto_configure(target="chatgpt")
        self.assertFalse(result.get("success"))
        self.assertIn("not supported", result.get("error", "").lower())

    def test_get_setup_status_contains_legacy_and_extended_fields(self):
        helper = MCPSetupHelper(vault_path="~/.vault")
        status = helper.get_setup_status()
        self.assertIn("mcp_configured", status)
        self.assertIn("claude_installed", status)
        self.assertIn("cursor_installed", status)
        self.assertIn("chatgpt_installed", status)
        self.assertIn("clients", status)


if __name__ == "__main__":
    unittest.main()
