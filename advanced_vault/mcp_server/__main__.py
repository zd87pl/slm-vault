"""
Main entry point for running the vault MCP server.

Usage:
    python -m advanced_vault.mcp_server
"""

import asyncio
from .server import main

if __name__ == "__main__":
    asyncio.run(main())
