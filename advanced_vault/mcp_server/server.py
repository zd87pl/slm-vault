"""
MCP Server for Enclave - Privacy-First AI Personal Data Manager

Implements Model Context Protocol server that exposes vault operations
and local agent commands to AI agents (Claude Desktop, Cursor, Copilot, etc.)

Key principle: External AIs command this server, but never see raw document content.
The local agent synthesizes responses from indexed documents.
"""

import os
import logging
import requests
from pathlib import Path
from typing import Any, Sequence, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import AnyUrl

from advanced_vault.core import HybridVault
from advanced_vault.mcp_server.consent import ConsentManager
from advanced_vault.mcp_server.activity_logger import ActivityLogger
from advanced_vault.mcp_server.agent import get_agent, LocalAgent

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

        # API configuration (for LangChain tools)
        # Can be set via environment variable or configured later
        self.api_key = os.getenv("ENCLAVE_API_KEY")
        self.api_base_url = os.getenv(
            "ENCLAVE_API_BASE_URL",
            "https://keen-curiosity-production-1288.up.railway.app"
        )

        # Create MCP server
        self.server = Server("enclave-vault")

        # Initialize local agent for synthesized responses
        self._agent: Optional[LocalAgent] = None

        # Register tools
        self._register_tools()

        logger.info(f"Initialized Enclave MCP Server at {self.vault_path}")

    def _get_agent(self) -> LocalAgent:
        """Get or create local agent."""
        if self._agent is None:
            self._agent = get_agent(vault_path=str(self.vault_path))
        return self._agent

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
                ),
                Tool(
                    name="langchain_get_secret",
                    description="Retrieve a secret from Enclave vault with policy enforcement (LangChain integration). Requires API key configuration. Returns encrypted secret that needs client-side decryption.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "service": {
                                "type": "string",
                                "description": "Service name (e.g., 'openai', 'github')"
                            },
                            "tag": {
                                "type": "string",
                                "description": "Optional tag filter"
                            }
                        },
                        "required": ["service"]
                    }
                ),
                Tool(
                    name="langchain_query_knowledge",
                    description="Query a knowledge adapter via DoRA inference (LangChain integration). Requires API key configuration and adapter_id.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "adapter_id": {
                                "type": "string",
                                "description": "Adapter UUID to query"
                            },
                            "query": {
                                "type": "string",
                                "description": "User query to ask the adapter"
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Generation temperature (0.0-1.0, default: 0.3)",
                                "default": 0.3
                            },
                            "max_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens to generate (default: 512)",
                                "default": 512
                            }
                        },
                        "required": ["adapter_id", "query"]
                    }
                ),
                # Agent Tools - External AIs command the local agent, never see raw documents
                Tool(
                    name="agent_query",
                    description="Ask the local Enclave agent a question. The agent reads indexed documents locally and returns a synthesized answer. External AIs never see raw document content - only the agent's response. Use this for questions about user's documents.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Question to ask the local agent"
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Generation temperature (0.0-1.0, default: 0.7)",
                                "default": 0.7
                            }
                        },
                        "required": ["question"]
                    }
                ),
                Tool(
                    name="agent_summarize",
                    description="Ask the local agent to summarize a topic or document. The agent generates a summary from indexed documents without exposing raw content.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Topic to summarize or document name"
                            },
                            "max_length": {
                                "type": "integer",
                                "description": "Approximate maximum length of summary (default: 500)",
                                "default": 500
                            }
                        },
                        "required": ["topic"]
                    }
                ),
                Tool(
                    name="agent_draft",
                    description="Ask the local agent to draft content based on indexed documents. Useful for emails, reports, or other content that should draw from user's documents.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "What to draft (e.g., 'email about project status')"
                            },
                            "style": {
                                "type": "string",
                                "enum": ["professional", "casual", "technical"],
                                "description": "Writing style (default: professional)",
                                "default": "professional"
                            }
                        },
                        "required": ["description"]
                    }
                ),
                Tool(
                    name="agent_status",
                    description="Get the status of the local Enclave agent including indexed documents, model status, and capabilities.",
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
                    query_preview = "List entries"
                elif name == "vault_delete":
                    query_preview = f"Delete {arguments.get('service', 'entry')}"
                elif name == "vault_store":
                    query_preview = f"Store {arguments.get('data_type', 'data')}"
                elif name == "agent_query":
                    query_preview = arguments.get("question", "")[:50]
                elif name == "agent_summarize":
                    query_preview = f"Summarize: {arguments.get('topic', '')[:30]}"
                elif name == "agent_draft":
                    query_preview = f"Draft: {arguments.get('description', '')[:30]}"
                elif name == "agent_status":
                    query_preview = "Check agent status"
                
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
                elif name == "langchain_get_secret":
                    result = await self._handle_langchain_get_secret(arguments)
                    result_summary = f"Retrieved secret for {arguments.get('service', 'unknown')}"
                elif name == "langchain_query_knowledge":
                    result = await self._handle_langchain_query_knowledge(arguments)
                    result_summary = "Queried knowledge adapter"
                elif name == "agent_query":
                    result = await self._handle_agent_query(arguments)
                    result_summary = "Agent answered question"
                elif name == "agent_summarize":
                    result = await self._handle_agent_summarize(arguments)
                    result_summary = "Agent generated summary"
                elif name == "agent_draft":
                    result = await self._handle_agent_draft(arguments)
                    result_summary = "Agent drafted content"
                elif name == "agent_status":
                    result = await self._handle_agent_status(arguments)
                    result_summary = "Retrieved agent status"
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

    async def _handle_langchain_get_secret(self, args: dict) -> Sequence[TextContent]:
        """Handle langchain_get_secret tool call."""
        if not self.api_key:
            return [TextContent(
                type="text",
                text="❌ Error: Enclave API key not configured. Set ENCLAVE_API_KEY environment variable."
            )]

        service = args.get("service")
        tag = args.get("tag")

        try:
            url = f"{self.api_base_url}/api/langchain/secrets/retrieve"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {}
            if service:
                payload["service"] = service
            if tag:
                payload["tag"] = tag

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 401:
                return [TextContent(
                    type="text",
                    text="❌ Error: Invalid API key. Please check your ENCLAVE_API_KEY."
                )]
            elif response.status_code == 403:
                error_detail = response.json().get("detail", "Access denied")
                return [TextContent(
                    type="text",
                    text=f"❌ Policy violation: {error_detail}"
                )]
            elif response.status_code == 404:
                return [TextContent(
                    type="text",
                    text=f"❌ Secret not found for service: {service}"
                )]
            elif response.status_code >= 500:
                return [TextContent(
                    type="text",
                    text=f"❌ Server error: {response.json().get('detail', 'Unknown error')}"
                )]

            result = response.json()
            encrypted_secret = result.get("secret", "")
            service_name = result.get("service", service)

            return [TextContent(
                type="text",
                text=f"✅ Retrieved secret for {service_name}\n\n"
                     f"Encrypted secret (base64): {encrypted_secret[:50]}...\n\n"
                     f"Note: This secret is encrypted and requires client-side decryption with your master key."
            )]

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to retrieve secret via API: {e}")
            return [TextContent(
                type="text",
                text=f"❌ Network error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Unexpected error in langchain_get_secret: {e}")
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    async def _handle_langchain_query_knowledge(self, args: dict) -> Sequence[TextContent]:
        """Handle langchain_query_knowledge tool call."""
        if not self.api_key:
            return [TextContent(
                type="text",
                text="❌ Error: Enclave API key not configured. Set ENCLAVE_API_KEY environment variable."
            )]

        adapter_id = args.get("adapter_id")
        query = args.get("query")
        temperature = args.get("temperature", 0.3)
        max_tokens = args.get("max_tokens", 512)

        if not adapter_id or not query:
            return [TextContent(
                type="text",
                text="❌ Error: adapter_id and query are required"
            )]

        try:
            url = f"{self.api_base_url}/api/langchain/knowledge/query"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "adapter_id": adapter_id,
                "query": query,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            response = requests.post(url, json=payload, headers=headers, timeout=180)

            if response.status_code == 401:
                return [TextContent(
                    type="text",
                    text="❌ Error: Invalid API key. Please check your ENCLAVE_API_KEY."
                )]
            elif response.status_code == 403:
                error_detail = response.json().get("detail", "Access denied")
                return [TextContent(
                    type="text",
                    text=f"❌ Policy violation: {error_detail}"
                )]
            elif response.status_code == 404:
                return [TextContent(
                    type="text",
                    text=f"❌ Adapter not found: {adapter_id}"
                )]
            elif response.status_code >= 500:
                return [TextContent(
                    type="text",
                    text=f"❌ Server error: {response.json().get('detail', 'Unknown error')}"
                )]

            result = response.json()
            answer = result.get("answer", "")

            if not answer:
                return [TextContent(
                    type="text",
                    text="❌ No answer returned from adapter"
                )]

            return [TextContent(
                type="text",
                text=f"✅ Knowledge Query Result\n\n"
                     f"Query: {query}\n"
                     f"Adapter: {adapter_id}\n\n"
                     f"Answer:\n{answer}"
            )]

        except requests.exceptions.Timeout:
            return [TextContent(
                type="text",
                text="❌ Timeout: Knowledge query took too long (>3 minutes). Try again or check adapter status."
            )]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query knowledge via API: {e}")
            return [TextContent(
                type="text",
                text=f"❌ Network error: {str(e)}"
            )]
        except Exception as e:
            logger.error(f"Unexpected error in langchain_query_knowledge: {e}")
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    async def _handle_agent_query(self, args: dict) -> Sequence[TextContent]:
        """
        Handle agent_query tool call.

        The local agent reads indexed documents and synthesizes an answer.
        External AIs never see raw document content.
        """
        question = args.get("question", "")
        temperature = args.get("temperature", 0.7)

        if not question:
            return [TextContent(
                type="text",
                text="❌ Error: Question is required"
            )]

        try:
            agent = self._get_agent()
            result = agent.query(
                question=question,
                temperature=temperature
            )

            if result.get("error"):
                return [TextContent(
                    type="text",
                    text=f"❌ Agent error: {result['error']}"
                )]

            # Format response
            lines = ["✅ Agent Response\n"]
            lines.append(result["answer"])

            if result.get("sources"):
                lines.append("\n---")
                lines.append("Sources consulted:")
                for src in result["sources"][:5]:
                    lines.append(f"  • {src['document']} (relevance: {src['score']})")

            if result.get("model_used"):
                lines.append(f"\nModel: {result['model_used']}")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"Agent query failed: {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=f"❌ Agent query failed: {str(e)}"
            )]

    async def _handle_agent_summarize(self, args: dict) -> Sequence[TextContent]:
        """Handle agent_summarize tool call."""
        topic = args.get("topic", "")
        max_length = args.get("max_length", 500)

        if not topic:
            return [TextContent(
                type="text",
                text="❌ Error: Topic is required"
            )]

        try:
            agent = self._get_agent()
            result = agent.summarize(
                topic_or_document=topic,
                max_length=max_length
            )

            if result.get("error"):
                return [TextContent(
                    type="text",
                    text=f"❌ Summarization failed: {result['error']}"
                )]

            lines = [f"✅ Summary: {topic}\n"]
            lines.append(result["summary"])

            if result.get("sources"):
                lines.append("\n---")
                lines.append("Based on:")
                for src in result["sources"][:5]:
                    lines.append(f"  • {src['document']}")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"Agent summarize failed: {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=f"❌ Summarization failed: {str(e)}"
            )]

    async def _handle_agent_draft(self, args: dict) -> Sequence[TextContent]:
        """Handle agent_draft tool call."""
        description = args.get("description", "")
        style = args.get("style", "professional")

        if not description:
            return [TextContent(
                type="text",
                text="❌ Error: Description is required"
            )]

        try:
            agent = self._get_agent()
            result = agent.draft(
                description=description,
                style=style
            )

            if result.get("error"):
                return [TextContent(
                    type="text",
                    text=f"❌ Draft generation failed: {result['error']}"
                )]

            lines = [f"✅ Draft ({style} style)\n"]
            lines.append(result["draft"])

            if result.get("sources"):
                lines.append("\n---")
                lines.append("Informed by:")
                for src in result["sources"][:3]:
                    lines.append(f"  • {src['document']}")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"Agent draft failed: {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=f"❌ Draft generation failed: {str(e)}"
            )]

    async def _handle_agent_status(self, args: dict) -> Sequence[TextContent]:
        """Handle agent_status tool call."""
        try:
            agent = self._get_agent()
            status = agent.get_status()

            lines = [
                "📊 Enclave Agent Status\n",
                f"Ready: {'✅ Yes' if status['ready'] else '❌ No'}",
                f"Backend: {status.get('backend', 'unknown')}",
                f"Model loaded: {'✅ Yes' if status['model_loaded'] else '❌ No'}",
            ]

            if status.get("model_name"):
                lines.append(f"Model: {status['model_name']}")

            lines.append(f"\nRAG Index: {'✅ Available' if status['rag_available'] else '❌ Not available'}")
            lines.append(f"Documents indexed: {status['document_count']}")
            lines.append(f"Total chunks: {status['chunk_count']}")

            if status.get("documents"):
                lines.append("\nIndexed documents:")
                for doc in status["documents"][:10]:
                    lines.append(f"  • {doc['name']} ({doc['chunks']} chunks)")
                if len(status["documents"]) > 10:
                    lines.append(f"  ... and {len(status['documents']) - 10} more")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"Agent status failed: {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=f"❌ Status check failed: {str(e)}"
            )]


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
