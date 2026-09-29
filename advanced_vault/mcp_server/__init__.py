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

import re
import sys
from importlib import metadata, util

# The server is written against the mcp 1.x API (2.0 removed Server.list_tools).
MCP_SDK_FIX = 'pip install "mcp>=1.0.0,<2"'


def _mcp_sdk_version() -> str | None:
    """Version of the installed mcp distribution, read from its metadata."""
    try:
        return metadata.version("mcp")
    except metadata.PackageNotFoundError:
        return None


def mcp_sdk_problem() -> str | None:
    """Explain why the installed MCP SDK cannot run this server, or return None.

    Reads package metadata only and never imports mcp, so it is cheap enough
    to run before any heavy import.
    """
    version = _mcp_sdk_version()
    if version is None:
        if util.find_spec("mcp") is None:
            return "the mcp package is not installed"
        return None  # importable without metadata (e.g. a frozen app): nothing to check
    major = re.match(r"\d+", version)
    if major and int(major.group()) >= 2:
        return f"mcp {version} is installed, but the Enclave MCP server needs the 1.x SDK"
    return None


def exit_if_sdk_incompatible() -> None:
    """Exit with one stderr line (no traceback) when the MCP SDK cannot run the server.

    MCP clients surface the server's stderr to the user.
    """
    problem = mcp_sdk_problem()
    if problem:
        sys.exit(f"enclave-mcp: {problem}. Fix it with: {MCP_SDK_FIX}")


__all__ = ["MCP_SDK_FIX", "exit_if_sdk_incompatible", "main", "mcp_sdk_problem"]

# On an incompatible SDK, skip the server import so main() can explain the
# problem instead of crashing with a traceback.
if mcp_sdk_problem() is None:
    try:
        from .server import create_vault_server
        __all__ += ["create_vault_server"]
    except ImportError:
        # MCP library not installed — submodules still importable directly
        pass


def main() -> None:
    """Console entry point for `enclave-mcp` — runs the stdio MCP server."""
    exit_if_sdk_incompatible()

    import asyncio

    from .server import main as _async_main

    asyncio.run(_async_main())
