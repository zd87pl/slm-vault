"""
MCP Server for Personal Vault

Implements Model Context Protocol server that exposes vault operations
to AI agents (Claude Desktop, Cursor, etc.)
"""

import os
import logging
from pathlib import Path
from typing import Any, Sequence

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import AnyUrl

from advanced_vault.core import HybridVault
from advanced_vault.mcp_server.consent import ConsentManager
from advanced_vault.mcp_server.activity_logger import ActivityLogger

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VaultMCPServer:
    """
    MCP Server for Personal Vault.

    Exposes vault operations as MCP tools that AI agents can call.
    """

    def __init__(self, vault_path: str = "~/.vault"):
        """
        Initialize vault MCP server.

        Args:
            vault_path: Base directory for vault storage
        """
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Initialize vault (will be lazy-loaded when needed)
        self.vault = None
        self._master_key = None
        
        # Initialize consent manager
        self.consent_manager = ConsentManager(vault_path=str(self.vault_path))
        
        # Initialize activity logger
        self.activity_logger = ActivityLogger(vault_path=str(self.vault_path))

        # Create MCP server
        self.server = Server("personal-vault")

        # Register tools
        self._register_tools()

        logger.info(f"Initialized Vault MCP Server at {self.vault_path}")

    def _get_vault(self) -> HybridVault:
        """Get or create vault instance."""
        if self.vault is None:
            # Load or generate master key
            key_path = self.vault_path / "master.key"

            if key_path.exists():
                with open(key_path, "rb") as f:
                    self._master_key = f.read()
                logger.info("Loaded existing master key")
            else:
                # Generate new master key
                self._master_key = os.urandom(32)
                with open(key_path, "wb") as f:
                    f.write(self._master_key)
                # Set secure permissions
                os.chmod(key_path, 0o600)
                logger.info("Generated new master key")

            # Initialize vault
            kv_db_path = str(self.vault_path / "vault.db")

            self.vault = HybridVault(
                master_key=self._master_key,
                kv_db_path=kv_db_path,
                enable_router_logging=False  # Don't spam logs in MCP
            )
            logger.info("Initialized HybridVault")

        return self.vault

    def _register_tools(self):
        """Register MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available vault tools."""
            return [
                Tool(
                    name="vault_store",
                    description="Store a secret or knowledge in the vault. Use 'secret' type for API keys, passwords, tokens. Use 'knowledge' type for setup notes, documentation, context.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The content to store (API key, password, or knowledge text)"
                            },
                            "data_type": {
                                "type": "string",
                                "enum": ["secret", "knowledge"],
                                "description": "Type of data: 'secret' for exact data (keys, passwords), 'knowledge' for contextual info"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name (e.g., 'stripe', 'github', 'aws'). Required for secrets."
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional tags for categorization (e.g., ['payment', 'production'])"
                            },
                            "description": {
                                "type": "string",
                                "description": "Optional human-readable description"
                            }
                        },
                        "required": ["content", "data_type"]
                    }
                ),
                Tool(
                    name="vault_recall",
                    description="Query the vault using natural language. Automatically routes to exact data (Layer 1) or knowledge (Layer 2) based on query type. Examples: 'What's my Stripe API key?' (exact), 'Why did I choose Stripe?' (knowledge), 'Show me everything about Stripe' (hybrid).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language query"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="vault_list_entries",
                    description="List all entries in the vault, optionally filtered by tag or service.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tag": {
                                "type": "string",
                                "description": "Optional tag to filter by"
                            },
                            "service": {
                                "type": "string",
                                "description": "Optional service name to filter by"
                            }
                        }
                    }
                ),
                Tool(
                    name="vault_delete",
                    description="Delete an entry from the vault by ID or service name.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "service": {
                                "type": "string",
                                "description": "Service name to delete (e.g., 'stripe')"
                            }
                        },
                        "required": ["service"]
                    }
                ),
                Tool(
                    name="vault_stats",
                    description="Get vault statistics (total entries, services, layer status).",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
            """Handle tool calls."""
            try:
                # Request consent before allowing vault access
                query_preview = ""
                if name == "vault_recall":
                    query_preview = arguments.get("query", "")
                elif name == "vault_list_entries":
                    query_preview = f"List entries"
                elif name == "vault_delete":
                    query_preview = f"Delete {arguments.get('service', 'entry')}"
                elif name == "vault_store":
                    query_preview = f"Store {arguments.get('data_type', 'data')}"
                
                # Get app identifier for logging
                app_identifier = self.consent_manager._get_app_identifier()
                
                # Request consent
                granted = self.consent_manager.request_consent(
                    tool_name=name,
                    query_preview=query_preview
                )
                
                if not granted:
                    # Log denied access
                    self.activity_logger.log_access(
                        tool_name=name,
                        app_identifier=app_identifier,
                        query_preview=query_preview,
                        granted=False
                    )
                    return [TextContent(
                        type="text",
                        text=f"❌ Access denied: You did not grant permission for {name}. Please approve the notification to access your vault."
                    )]
                
                vault = self._get_vault()

                # Execute tool and capture result summary
                result_summary = None
                if name == "vault_store":
                    result = await self._handle_store(vault, arguments)
                    result_summary = f"Stored {arguments.get('data_type', 'data')}"
                elif name == "vault_recall":
                    result = await self._handle_recall(vault, arguments)
                    result_summary = "Query executed"
                elif name == "vault_list_entries":
                    result = await self._handle_list(vault, arguments)
                    # Extract count from result
                    result_text = result[0].text if result else ""
                    if "Found" in result_text:
                        try:
                            count = result_text.split("Found")[1].split("entries")[0].strip()
                            result_summary = f"Found {count} entries"
                        except:
                            result_summary = "Listed entries"
                    else:
                        result_summary = "Listed entries"
                elif name == "vault_delete":
                    result = await self._handle_delete(vault, arguments)
                    result_summary = f"Deleted {arguments.get('service', 'entry')}"
                elif name == "vault_stats":
                    result = await self._handle_stats(vault, arguments)
                    result_summary = "Retrieved statistics"
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
                # Log successful access
                self.activity_logger.log_access(
                    tool_name=name,
                    app_identifier=app_identifier,
                    query_preview=query_preview,
                    granted=True,
                    result_summary=result_summary
                )
                
                return result

            except Exception as e:
                logger.error(f"Tool call failed: {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]

    async def _handle_store(self, vault: HybridVault, args: dict) -> Sequence[TextContent]:
        """Handle vault_store tool call."""
        content = args["content"]
        data_type = args["data_type"]
        service = args.get("service")
        tags = args.get("tags", [])
        description = args.get("description")

        if data_type == "secret" and not service:
            return [TextContent(
                type="text",
                text="Error: 'service' is required for storing secrets"
            )]

        entry_id = vault.store(
            content=content,
            data_type=data_type,
            service=service,
            tags=tags,
            description=description
        )

        if data_type == "secret":
            return [TextContent(
                type="text",
                text=f"✅ Stored {service} secret (ID: {entry_id[:8]}...)\nType: secret\nService: {service}\nTags: {', '.join(tags) if tags else 'none'}"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"✅ Stored knowledge (ID: {entry_id[:8] if entry_id else 'N/A'}...)\nType: knowledge\nNote: Knowledge will be available for fuzzy queries"
            )]

    async def _handle_recall(self, vault: HybridVault, args: dict) -> Sequence[TextContent]:
        """Handle vault_recall tool call."""
        query = args["query"]

        result = vault.query(query)

        strategy = result.get('strategy', 'unknown')
        layer = result.get('layer') or result.get('layers', 'unknown')

        if result.get('error'):
            return [TextContent(
                type="text",
                text=f"❌ Query failed\nStrategy: {strategy}\nLayer: {layer}\nError: {result['error']}"
            )]

        response = result.get('result')
        if response:
            return [TextContent(
                type="text",
                text=f"✅ Found result\nStrategy: {strategy}\nLayer: {layer}\nService: {result.get('service', 'N/A')}\n\nResult:\n{response}"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"❓ No results found\nStrategy: {strategy}\nLayer: {layer}\nQuery: {query}"
            )]

    async def _handle_list(self, vault: HybridVault, args: dict) -> Sequence[TextContent]:
        """Handle vault_list_entries tool call."""
        tag = args.get('tag')
        service = args.get('service')

        # Build filter
        from advanced_vault.encrypted_kv import QueryFilter

        filter_obj = QueryFilter()
        if tag:
            filter_obj.tags = [tag]
        if service:
            filter_obj.service = service

        entries = vault.kv_store.search(filter_obj)

        if not entries:
            return [TextContent(
                type="text",
                text="No entries found matching the filter."
            )]

        lines = [f"Found {len(entries)} entries:\n"]
        for entry in entries:
            lines.append(f"• {entry.service}")
            lines.append(f"  Type: {entry.entry_type.value}")
            lines.append(f"  Tags: {', '.join(entry.tags) if entry.tags else 'none'}")
            if entry.description:
                lines.append(f"  Description: {entry.description}")
            lines.append(f"  Created: {entry.created_at.strftime('%Y-%m-%d %H:%M')}")
            lines.append("")

        return [TextContent(type="text", text="\n".join(lines))]

    async def _handle_delete(self, vault: HybridVault, args: dict) -> Sequence[TextContent]:
        """Handle vault_delete tool call."""
        service = args["service"]

        success = vault.kv_store.delete(service)

        if success:
            return [TextContent(
                type="text",
                text=f"✅ Deleted entry for service: {service}"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"❌ No entry found for service: {service}"
            )]

    async def _handle_stats(self, vault: HybridVault, args: dict) -> Sequence[TextContent]:
        """Handle vault_stats tool call."""
        stats = vault.get_stats()

        layer1 = stats['layer_1']
        layer2 = stats['layer_2']

        lines = [
            "📊 Vault Statistics\n",
            "Layer 1 (Encrypted KV Store):",
            f"  Total entries: {layer1['total_entries']}",
            f"  Services: {', '.join(layer1['services']) if layer1['services'] else 'none'}",
            f"  Encryption: ChaCha20-Poly1305",
            "",
            "Layer 2 (DoRA Knowledge):",
            f"  Initialized: {layer2['initialized']}",
            f"  Status: {'Active' if layer2['initialized'] else 'Not configured'}",
        ]

        return [TextContent(type="text", text="\n".join(lines))]


def create_vault_server(vault_path: str = "~/.vault") -> VaultMCPServer:
    """
    Create and return a Vault MCP server.

    Args:
        vault_path: Base directory for vault storage

    Returns:
        Initialized VaultMCPServer instance
    """
    return VaultMCPServer(vault_path)


# CLI entry point for running as MCP server
async def main():
    """Main entry point for running server."""
    import sys
    from mcp.server.stdio import stdio_server

    # Get vault path from environment or use default
    vault_path = os.environ.get("VAULT_PATH", "~/.vault")

    # Create server
    server_instance = create_vault_server(vault_path)

    # Run with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            server_instance.server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
