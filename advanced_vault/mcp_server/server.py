"""
MCP Server for Enclave - Privacy-First AI Personal Data Manager

Implements Model Context Protocol server that exposes vault operations
and local agent commands to AI agents (Claude Desktop, Cursor, Copilot, etc.)

Key principle: External AIs command this server, but never see raw document content.
The local agent synthesizes responses from indexed documents.
"""

import json
import os
import logging
import requests
from pathlib import Path
from typing import Any, Sequence, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent

from advanced_vault.core import HybridVault
from advanced_vault.enclave_control import EnclaveRuntime
from advanced_vault.sheriff.core import SheriffCore
from advanced_vault.sheriff.models import AccessDecision
from advanced_vault.mcp_server.consent import ConsentManager
from advanced_vault.mcp_server.activity_logger import ActivityLogger
from advanced_vault.mcp_server.agent import get_agent, LocalAgent
from advanced_vault.wallet import WalletService

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
        self.runtime = EnclaveRuntime(vault_path=str(self.vault_path))
        self.wallet = WalletService(vault_path=str(self.vault_path))

        # Initialize vault (will be lazy-loaded when needed)
        self.vault = None
        self._master_key = None
        
        # Initialize consent manager
        self.consent_manager = ConsentManager(vault_path=str(self.vault_path))
        
        # Initialize activity logger
        self.activity_logger = ActivityLogger(vault_path=str(self.vault_path), runtime=self.runtime)
        
        # Local Data Sheriff core: deny-by-default consent + lease controls
        self.sheriff = SheriffCore(vault_path=str(self.vault_path), runtime=self.runtime)

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
        self._update_runtime_module_status()

        logger.info(f"Initialized Enclave MCP Server at {self.vault_path}")

    def _get_agent(self) -> LocalAgent:
        """Get or create local agent with master key."""
        if self._agent is None:
            # Ensure vault is initialized to get master key
            self._get_vault()
            self._agent = get_agent(
                vault_path=str(self.vault_path),
                master_key=self._master_key
            )
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
                    name="query_knowledge",
                    description="Ask Enclave Vault a knowledge question through the local synthesized-answer path. This is an additive alias for agent_query.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Question to ask about the indexed private knowledge base"
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
                ),
                Tool(
                    name="sheriff.request_access",
                    description="Request access to a resource through Data Sheriff policy engine. Returns ALLOW_WITH_LEASE, PROMPT, or DENY.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "resource": {
                                "type": "string",
                                "description": "Absolute or user-home resource path."
                            },
                            "purpose": {
                                "type": "string",
                                "description": "Human purpose for access request."
                            },
                            "ttl_seconds": {
                                "type": "integer",
                                "description": "Requested lease duration in seconds (default: 900).",
                                "default": 900
                            }
                        },
                        "required": ["resource", "purpose"]
                    }
                ),
                Tool(
                    name="sheriff.read",
                    description="Read a file only when a valid lease_id is provided. Content is redacted by default.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "resource": {
                                "type": "string",
                                "description": "Path to resource."
                            },
                            "lease_id": {
                                "type": "string",
                                "description": "Lease token issued by sheriff.request_access."
                            },
                            "redact": {
                                "type": "boolean",
                                "description": "Whether to apply redaction before returning content (default: true).",
                                "default": True
                            }
                        },
                        "required": ["resource", "lease_id"]
                    }
                ),
                Tool(
                    name="sheriff.list_audit",
                    description="List recent Data Sheriff audit events with optional filters.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Max events to return (default: 50).",
                                "default": 50
                            },
                            "subject": {
                                "type": "string",
                                "description": "Optional subject/app filter."
                            },
                            "resource": {
                                "type": "string",
                                "description": "Optional resource substring filter."
                            },
                            "decision": {
                                "type": "string",
                                "enum": ["ALLOW", "DENY", "PROMPT", "ALLOW_WITH_LEASE"],
                                "description": "Optional decision filter."
                            }
                        }
                    }
                ),
                Tool(
                    name="sheriff.revoke",
                    description="Immediately revoke an active lease by lease_id.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "lease_id": {
                                "type": "string",
                                "description": "Lease token to revoke."
                            }
                        },
                        "required": ["lease_id"]
                    }
                ),
                Tool(
                    name="sheriff.risk_summary",
                    description="Run local risk scan and return classification summary + recommendations.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional scan root paths. Defaults to ~/Documents."
                            },
                            "max_files": {
                                "type": "integer",
                                "description": "Max files scanned (default: 2000).",
                                "default": 2000
                            }
                        }
                    }
                ),
                Tool(
                    name="sheriff.protect_now",
                    description="Create prompt-based protection rules for selected paths.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Paths to protect with consent barrier."
                            }
                        },
                        "required": ["paths"]
                    }
                ),
                Tool(
                    name="sheriff.hardening_report",
                    description="Inspect Claude/Cursor MCP configs and return hardening alerts.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="sheriff.enforcement_status",
                    description="Return status of system-level enforcement backend.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="create_envelope",
                    description="Create a governed mock wallet envelope for local budgeted spend.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "budget": {"type": "number"},
                            "period": {"type": "string", "default": "monthly"},
                            "currency": {"type": "string", "default": "USD"},
                            "requires_approval_above": {"type": "number", "default": 25.0},
                            "max_per_transaction": {"type": "number"},
                            "daily_limit": {"type": "number"}
                        },
                        "required": ["name", "budget"]
                    }
                ),
                Tool(
                    name="list_envelopes",
                    description="List all configured wallet envelopes.",
                    inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="check_budget",
                    description="Inspect the budget state for one wallet envelope.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "envelope": {"type": "string", "description": "Envelope name or id"}
                        },
                        "required": ["envelope"]
                    }
                ),
                Tool(
                    name="request_purchase",
                    description="Request governed spend from a wallet envelope. Requests above policy/envelope threshold may enter approval.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "envelope": {"type": "string"},
                            "amount": {"type": "number"},
                            "merchant": {"type": "string"},
                            "currency": {"type": "string", "default": "USD"},
                            "memo": {"type": "string", "default": ""}
                        },
                        "required": ["envelope", "amount", "merchant"]
                    }
                ),
                Tool(
                    name="approve_purchase",
                    description="Approve a pending wallet purchase request.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "request_id": {"type": "string"},
                            "approver": {"type": "string", "default": "user"}
                        },
                        "required": ["request_id"]
                    }
                ),
                Tool(
                    name="get_transactions",
                    description="List wallet transactions for one envelope or all envelopes.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "envelope": {"type": "string"}
                        }
                    }
                ),
                Tool(
                    name="freeze_all",
                    description="Enable the global kill switch and freeze wallet execution.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "default": "MCP freeze"}
                        }
                    }
                ),
                Tool(
                    name="unfreeze_all",
                    description="Disable the global kill switch and unfreeze wallet execution.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "default": "MCP unfreeze"}
                        }
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
            """Handle tool calls."""
            try:
                args = arguments or {}

                # Request consent before allowing vault access.
                # sheriff.* tools manage consent/leases internally.
                query_preview = ""
                if name == "vault_recall":
                    query_preview = args.get("query", "")
                elif name == "vault_list_entries":
                    query_preview = "List entries"
                elif name == "vault_delete":
                    query_preview = f"Delete {args.get('service', 'entry')}"
                elif name == "vault_store":
                    query_preview = f"Store {args.get('data_type', 'data')}"
                elif name == "agent_query":
                    query_preview = args.get("question", "")[:50]
                elif name == "query_knowledge":
                    query_preview = args.get("question", "")[:50]
                elif name == "agent_summarize":
                    query_preview = f"Summarize: {args.get('topic', '')[:30]}"
                elif name == "agent_draft":
                    query_preview = f"Draft: {args.get('description', '')[:30]}"
                elif name == "agent_status":
                    query_preview = "Check agent status"
                elif name == "sheriff.request_access":
                    purpose = args.get("purpose", "")
                    resource = args.get("resource", "")
                    query_preview = f"{purpose[:30]} -> {resource[:30]}"
                elif name == "sheriff.read":
                    query_preview = f"Read {args.get('resource', '')[:40]}"
                elif name == "sheriff.list_audit":
                    query_preview = "List sheriff audit"
                elif name == "sheriff.revoke":
                    query_preview = f"Revoke lease {args.get('lease_id', '')[:18]}"
                elif name == "sheriff.risk_summary":
                    query_preview = "Run risk summary scan"
                elif name == "sheriff.protect_now":
                    paths = args.get("paths", [])
                    query_preview = f"Protect {len(paths) if isinstance(paths, list) else 0} paths"
                elif name == "sheriff.hardening_report":
                    query_preview = "Run hardening report"
                elif name == "sheriff.enforcement_status":
                    query_preview = "Check enforcement status"
                elif name == "create_envelope":
                    query_preview = f"Create envelope {args.get('name', '')[:30]}"
                elif name == "list_envelopes":
                    query_preview = "List wallet envelopes"
                elif name == "check_budget":
                    query_preview = f"Check budget {args.get('envelope', '')[:30]}"
                elif name == "request_purchase":
                    query_preview = f"Request {args.get('merchant', '')[:30]} ${args.get('amount', 0)}"
                elif name == "approve_purchase":
                    query_preview = f"Approve purchase {args.get('request_id', '')[:18]}"
                elif name == "get_transactions":
                    query_preview = f"Transactions {args.get('envelope', 'all')}"
                elif name == "freeze_all":
                    query_preview = "Freeze all wallet execution"
                elif name == "unfreeze_all":
                    query_preview = "Unfreeze wallet execution"

                # Get app identifier for logging
                app_identifier = self.consent_manager._get_app_identifier()
                module_name = self._module_for_tool(name)
                policy_decision, policy_reason = self.runtime.evaluate_action(
                    agent_id=app_identifier,
                    module=module_name,
                    tool=name,
                    resource=str(args.get("resource") or args.get("service") or args.get("envelope") or ""),
                    amount=float(args.get("amount", 0.0) or 0.0) if "amount" in args else None,
                )
                if policy_decision == "deny":
                    self.runtime.log_event(
                        subject=app_identifier,
                        module=module_name,
                        tool=name,
                        decision="DENY",
                        resource=query_preview,
                        summary=policy_reason,
                        metadata={"arguments": args},
                        source="mcp_server",
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"❌ Shared policy denied {name}: {policy_reason}",
                        )
                    ]

                if not name.startswith("sheriff."):
                    granted = self.consent_manager.request_consent(
                        tool_name=name,
                        query_preview=query_preview,
                    )
                    if not granted:
                        # Log denied access
                        self.activity_logger.log_access(
                            tool_name=name,
                            app_identifier=app_identifier,
                            query_preview=query_preview,
                            granted=False,
                        )
                        return [
                            TextContent(
                                type="text",
                                text=f"❌ Access denied: You did not grant permission for {name}. Please approve the notification to access your vault.",
                            )
                        ]

                # Execute tool and capture result summary
                result_summary = None
                if name == "vault_store":
                    result = await self._handle_store(self._get_vault(), args)
                    result_summary = f"Stored {args.get('data_type', 'data')}"
                elif name == "vault_recall":
                    result = await self._handle_recall(self._get_vault(), args)
                    result_summary = "Query executed"
                elif name == "vault_list_entries":
                    result = await self._handle_list(self._get_vault(), args)
                    # Extract count from result
                    result_text = result[0].text if result else ""
                    if "Found" in result_text:
                        try:
                            count = result_text.split("Found")[1].split("entries")[0].strip()
                            result_summary = f"Found {count} entries"
                        except Exception:
                            result_summary = "Listed entries"
                    else:
                        result_summary = "Listed entries"
                elif name == "vault_delete":
                    result = await self._handle_delete(self._get_vault(), args)
                    result_summary = f"Deleted {args.get('service', 'entry')}"
                elif name == "vault_stats":
                    result = await self._handle_stats(self._get_vault(), args)
                    result_summary = "Retrieved statistics"
                elif name == "langchain_get_secret":
                    result = await self._handle_langchain_get_secret(args)
                    result_summary = f"Retrieved secret for {args.get('service', 'unknown')}"
                elif name == "langchain_query_knowledge":
                    result = await self._handle_langchain_query_knowledge(args)
                    result_summary = "Queried knowledge adapter"
                elif name == "query_knowledge":
                    result = await self._handle_query_knowledge(args)
                    result_summary = "Queried private knowledge"
                elif name == "agent_query":
                    result = await self._handle_agent_query(args)
                    result_summary = "Agent answered question"
                elif name == "agent_summarize":
                    result = await self._handle_agent_summarize(args)
                    result_summary = "Agent generated summary"
                elif name == "agent_draft":
                    result = await self._handle_agent_draft(args)
                    result_summary = "Agent drafted content"
                elif name == "agent_status":
                    result = await self._handle_agent_status(args)
                    result_summary = "Retrieved agent status"
                elif name == "sheriff.request_access":
                    result = await self._handle_sheriff_request_access(args, app_identifier)
                    result_summary = f"Sheriff request_access for {args.get('resource', '')[:40]}"
                elif name == "sheriff.read":
                    result = await self._handle_sheriff_read(args, app_identifier)
                    result_summary = f"Sheriff read {args.get('resource', '')[:40]}"
                elif name == "sheriff.list_audit":
                    result = await self._handle_sheriff_list_audit(args)
                    result_summary = "Sheriff audit listed"
                elif name == "sheriff.revoke":
                    result = await self._handle_sheriff_revoke(args)
                    result_summary = f"Sheriff lease revoked {args.get('lease_id', '')[:18]}"
                elif name == "sheriff.risk_summary":
                    result = await self._handle_sheriff_risk_summary(args)
                    result_summary = "Sheriff risk summary generated"
                elif name == "sheriff.protect_now":
                    result = await self._handle_sheriff_protect_now(args)
                    result_summary = "Sheriff protection rules created"
                elif name == "sheriff.hardening_report":
                    result = await self._handle_sheriff_hardening_report(args)
                    result_summary = "Sheriff hardening report generated"
                elif name == "sheriff.enforcement_status":
                    result = await self._handle_sheriff_enforcement_status(args)
                    result_summary = "Sheriff enforcement status checked"
                elif name == "create_envelope":
                    result = await self._handle_wallet_create_envelope(args)
                    result_summary = f"Created envelope {args.get('name', '')[:30]}"
                elif name == "list_envelopes":
                    result = await self._handle_wallet_list_envelopes(args)
                    result_summary = "Listed wallet envelopes"
                elif name == "check_budget":
                    result = await self._handle_wallet_check_budget(args)
                    result_summary = f"Budget checked for {args.get('envelope', '')[:30]}"
                elif name == "request_purchase":
                    result = await self._handle_wallet_request_purchase(args, app_identifier)
                    result_summary = f"Purchase requested for {args.get('merchant', '')[:30]}"
                elif name == "approve_purchase":
                    result = await self._handle_wallet_approve_purchase(args)
                    result_summary = f"Purchase approved {args.get('request_id', '')[:18]}"
                elif name == "get_transactions":
                    result = await self._handle_wallet_get_transactions(args)
                    result_summary = "Wallet transactions listed"
                elif name == "freeze_all":
                    result = await self._handle_wallet_freeze_all(args)
                    result_summary = "Wallet frozen"
                elif name == "unfreeze_all":
                    result = await self._handle_wallet_unfreeze_all(args)
                    result_summary = "Wallet unfrozen"
                else:
                    raise ValueError(f"Unknown tool: {name}")

                # Log successful access
                self.activity_logger.log_access(
                    tool_name=name,
                    app_identifier=app_identifier,
                    query_preview=query_preview,
                    granted=True,
                    result_summary=result_summary,
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

    async def _handle_query_knowledge(self, args: dict) -> Sequence[TextContent]:
        """Additive alias for the synthesized private knowledge query path."""
        return await self._handle_agent_query(args)

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

    async def _handle_sheriff_request_access(self, args: dict, app_identifier: str) -> Sequence[TextContent]:
        """Handle sheriff.request_access tool call."""
        resource = args.get("resource")
        purpose = args.get("purpose")
        ttl_seconds = int(args.get("ttl_seconds", 900))

        if not resource or not purpose:
            return [TextContent(
                type="text",
                text="❌ Error: 'resource' and 'purpose' are required."
            )]

        result = self.sheriff.request_access(
            subject_app=app_identifier,
            resource=resource,
            purpose=purpose,
            ttl_seconds=ttl_seconds,
        )

        # Bridge PROMPT decisions to existing OS consent flow for MCP agents.
        if result.decision == AccessDecision.PROMPT:
            granted = self.consent_manager.request_consent(
                tool_name="sheriff.request_access",
                query_preview=f"{purpose[:30]} -> {resource[:40]}",
            )
            result = self.sheriff.consent_decide(
                subject_app=app_identifier,
                resource=resource,
                purpose=purpose,
                allow=granted,
                ttl_seconds=ttl_seconds,
            )

        payload = result.model_dump(mode="json")
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    async def _handle_sheriff_read(self, args: dict, app_identifier: str) -> Sequence[TextContent]:
        """Handle sheriff.read tool call."""
        resource = args.get("resource")
        lease_id = args.get("lease_id")
        redact = args.get("redact", True)

        if not resource or not lease_id:
            return [TextContent(
                type="text",
                text="❌ Error: 'resource' and 'lease_id' are required."
            )]

        try:
            content = self.sheriff.read_with_lease(
                subject_app=app_identifier,
                resource=resource,
                lease_id=lease_id,
                redact=bool(redact),
            )
        except PermissionError as e:
            return [TextContent(type="text", text=f"❌ Access denied: {e}")]
        except FileNotFoundError:
            return [TextContent(type="text", text=f"❌ Resource not found: {resource}")]

        max_chars = 20000
        truncated = len(content) > max_chars
        body = content[:max_chars]
        suffix = "\n\n[TRUNCATED]" if truncated else ""
        return [TextContent(type="text", text=f"{body}{suffix}")]

    async def _handle_sheriff_list_audit(self, args: dict) -> Sequence[TextContent]:
        """Handle sheriff.list_audit tool call."""
        limit = int(args.get("limit", 50))
        subject = args.get("subject")
        resource = args.get("resource")
        decision_raw = args.get("decision")

        decision = None
        if decision_raw:
            try:
                decision = AccessDecision(str(decision_raw))
            except ValueError:
                return [TextContent(
                    type="text",
                    text=f"❌ Invalid decision value: {decision_raw}. Allowed: ALLOW, DENY, PROMPT, ALLOW_WITH_LEASE."
                )]

        events = self.sheriff.audit_events(
            limit=limit,
            subject=subject,
            resource=resource,
            decision=decision,
        )
        return [TextContent(type="text", text=json.dumps({"items": events}, indent=2))]

    async def _handle_sheriff_revoke(self, args: dict) -> Sequence[TextContent]:
        """Handle sheriff.revoke tool call."""
        lease_id = args.get("lease_id")
        if not lease_id:
            return [TextContent(
                type="text",
                text="❌ Error: 'lease_id' is required."
            )]

        ok = self.sheriff.revoke_lease(lease_id=lease_id, actor="user")
        if ok:
            return [TextContent(type="text", text=f"✅ Lease revoked: {lease_id}")]
        return [TextContent(type="text", text=f"❌ Lease not found: {lease_id}")]

    async def _handle_sheriff_risk_summary(self, args: dict) -> Sequence[TextContent]:
        """Handle sheriff.risk_summary tool call."""
        paths = args.get("paths")
        max_files = int(args.get("max_files", 2000))
        if paths is not None and not isinstance(paths, list):
            return [TextContent(type="text", text="❌ Error: 'paths' must be an array of strings.")]

        summary = self.sheriff.scan_risk(paths=paths, max_files=max_files)
        payload = summary.model_dump(mode="json")
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    async def _handle_sheriff_protect_now(self, args: dict) -> Sequence[TextContent]:
        """Handle sheriff.protect_now tool call."""
        paths = args.get("paths")
        if not isinstance(paths, list) or not paths:
            return [TextContent(type="text", text="❌ Error: non-empty 'paths' array is required.")]

        rules = self.sheriff.protect_now(paths=paths)
        payload = {"rules": [rule.model_dump(mode="json") for rule in rules], "count": len(rules)}
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    async def _handle_sheriff_hardening_report(self, args: dict) -> Sequence[TextContent]:
        """Handle sheriff.hardening_report tool call."""
        _ = args
        alerts = self.sheriff.hardening_report()
        return [TextContent(type="text", text=json.dumps({"alerts": alerts}, indent=2))]

    async def _handle_sheriff_enforcement_status(self, args: dict) -> Sequence[TextContent]:
        """Handle sheriff.enforcement_status tool call."""
        _ = args
        status = self.sheriff.enforcement_status()
        return [TextContent(type="text", text=json.dumps(status, indent=2))]

    async def _handle_wallet_create_envelope(self, args: dict) -> Sequence[TextContent]:
        """Handle create_envelope tool call."""
        envelope = self.wallet.create_envelope(
            name=args["name"],
            budget=float(args["budget"]),
            period=args.get("period", "monthly"),
            currency=args.get("currency", "USD"),
            requires_approval_above=float(args.get("requires_approval_above", 25.0)),
            max_per_transaction=float(args["max_per_transaction"]) if args.get("max_per_transaction") is not None else None,
            daily_limit=float(args["daily_limit"]) if args.get("daily_limit") is not None else None,
        )
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps(envelope.to_dict(), indent=2))]

    async def _handle_wallet_list_envelopes(self, args: dict) -> Sequence[TextContent]:
        """Handle list_envelopes tool call."""
        _ = args
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps([item.to_dict() for item in self.wallet.list_envelopes()], indent=2))]

    async def _handle_wallet_check_budget(self, args: dict) -> Sequence[TextContent]:
        """Handle check_budget tool call."""
        envelope = args.get("envelope")
        if not envelope:
            return [TextContent(type="text", text="❌ Error: 'envelope' is required.")]
        snapshot = self.wallet.check_budget(envelope)
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps(snapshot, indent=2))]

    async def _handle_wallet_request_purchase(self, args: dict, app_identifier: str) -> Sequence[TextContent]:
        """Handle request_purchase tool call."""
        envelope = args.get("envelope")
        amount = args.get("amount")
        merchant = args.get("merchant")
        if not envelope or amount is None or not merchant:
            return [TextContent(type="text", text="❌ Error: 'envelope', 'amount', and 'merchant' are required.")]

        outcome = self.wallet.request_purchase(
            envelope,
            amount=float(amount),
            merchant=merchant,
            agent_id=app_identifier,
            currency=args.get("currency", "USD"),
            memo=args.get("memo", ""),
        )
        self.runtime.log_event(
            subject=app_identifier,
            module="wallet",
            tool="request_purchase",
            decision=outcome.decision.value.upper(),
            resource=f"{envelope}:{merchant}",
            summary=outcome.reason,
            metadata=outcome.to_dict(),
            source="mcp_wallet",
        )
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps(outcome.to_dict(), indent=2))]

    async def _handle_wallet_approve_purchase(self, args: dict) -> Sequence[TextContent]:
        """Handle approve_purchase tool call."""
        request_id = args.get("request_id")
        if not request_id:
            return [TextContent(type="text", text="❌ Error: 'request_id' is required.")]
        outcome = self.wallet.approve_purchase(
            request_id,
            approver=args.get("approver", "user"),
        )
        self.runtime.log_event(
            subject=args.get("approver", "user"),
            module="wallet",
            tool="approve_purchase",
            decision=outcome.decision.value.upper(),
            resource=request_id,
            summary=outcome.reason,
            metadata=outcome.to_dict(),
            source="mcp_wallet",
        )
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps(outcome.to_dict(), indent=2))]

    async def _handle_wallet_get_transactions(self, args: dict) -> Sequence[TextContent]:
        """Handle get_transactions tool call."""
        envelope = args.get("envelope")
        transactions = self.wallet.get_transactions(envelope)
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps([item.to_dict() for item in transactions], indent=2))]

    async def _handle_wallet_freeze_all(self, args: dict) -> Sequence[TextContent]:
        """Handle freeze_all tool call."""
        reason = args.get("reason", "MCP freeze")
        self.runtime.set_kill_switch(True, reason=reason, actor="mcp")
        payload = self.wallet.freeze_all(reason=reason)
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    async def _handle_wallet_unfreeze_all(self, args: dict) -> Sequence[TextContent]:
        """Handle unfreeze_all tool call."""
        reason = args.get("reason", "MCP unfreeze")
        self.runtime.set_kill_switch(False, reason=reason, actor="mcp")
        payload = self.wallet.unfreeze_all(reason=reason)
        self._update_runtime_module_status()
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    def _module_for_tool(self, tool_name: str) -> str:
        """Map public tool names to shared runtime module names."""
        if tool_name.startswith("sheriff."):
            return "security"
        if tool_name in {
            "create_envelope",
            "list_envelopes",
            "check_budget",
            "request_purchase",
            "approve_purchase",
            "get_transactions",
            "freeze_all",
            "unfreeze_all",
        }:
            return "wallet"
        return "vault"

    def _update_runtime_module_status(self) -> None:
        """Refresh lightweight Vault + Wallet module snapshots."""
        try:
            agent = self._get_agent()
            agent_status = agent.get_status()
            self.runtime.update_module_status(
                "vault",
                status="ready",
                headline="Vault ready",
                details={
                    "document_count": agent_status.get("document_count", 0),
                    "model_loaded": agent_status.get("model_loaded", False),
                    "backend": agent_status.get("backend"),
                    "document_names": [doc.get("name") for doc in agent_status.get("documents", [])[:5]],
                },
            )
        except Exception:
            self.runtime.update_module_status("vault", status="warning", headline="Vault initialized with limited status")

        try:
            self.runtime.update_module_status(
                "wallet",
                status="warning" if self.wallet.store.is_frozen() else "ready",
                headline="Wallet frozen" if self.wallet.store.is_frozen() else "Wallet ready",
                details={
                    "envelope_count": len(self.wallet.list_envelopes()),
                    "pending_count": len(self.wallet.list_pending_requests()),
                    "transaction_count": len(self.wallet.get_transactions()),
                    "frozen": self.wallet.store.is_frozen(),
                },
            )
        except Exception:
            self.runtime.update_module_status("wallet", status="warning", headline="Wallet initialized with limited status")


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
