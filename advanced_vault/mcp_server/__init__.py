"""
Personal Vault MCP Server

Model Context Protocol (MCP) server for exposing the advanced vault
to AI agents like Claude Desktop and Cursor.

Provides tools for:
- Storing secrets and knowledge
- Querying with Smart Router
- Listing vault entries
- Deleting entries

Usage:
    # In ~/.config/claude/config.json
    {
      "mcpServers": {
        "personal-vault": {
          "command": "python",
          "args": ["-m", "advanced_vault.mcp_server"],
          "env": {"VAULT_PATH": "~/.vault"}
        }
      }
    }
"""

from .server import create_vault_server

__all__ = ["create_vault_server"]
