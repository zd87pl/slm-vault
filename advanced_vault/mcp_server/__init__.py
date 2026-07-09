"""
Enclave MCP Server

Model Context Protocol (MCP) server for exposing the vault
to AI agents like Claude Desktop and Cursor.

Provides tools for:
- Storing secrets and knowledge
- Querying with Smart Router
- Listing vault entries
- Deleting entries

Run it with `enclave-mcp` or `python -m advanced_vault.mcp_server`.
The easiest way to register it with Claude Desktop is `enclave mcp install`.
"""

try:
    from .server import create_vault_server
    __all__ = ["create_vault_server", "main"]
except ImportError:
    # MCP library not installed — submodules still importable directly
    __all__ = ["main"]


def main() -> None:
    """Console entry point for `enclave-mcp` — runs the stdio MCP server."""
    import asyncio

    from .server import main as _async_main

    asyncio.run(_async_main())
