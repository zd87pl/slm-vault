"""
Hybrid Vault

Unified interface combining:
- Layer 1: Encrypted KV store (exact data)
- Layer 2: DoRA adapters (fuzzy knowledge)

The hybrid vault automatically routes queries to the appropriate layer(s)
using the smart router.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from .smart_router import SmartRouter, QueryStrategy
from advanced_vault.encrypted_kv import EncryptedKVStore, EntryType

logger = logging.getLogger(__name__)


class HybridVault:
    """
    Unified vault interface with automatic query routing.

    Combines:
    - Layer 1 (EncryptedKVStore): API keys, passwords, exact data
    - Layer 2 (DoRA): Knowledge, context, fuzzy data

    Usage:
        vault = HybridVault(master_key)

        # Store exact data
        vault.store("sk_live_ABC", type="secret", service="stripe")

        # Store knowledge
        vault.store("Chose Stripe for webhooks", type="knowledge")

        # Query (auto-routed)
        vault.query("What's my Stripe key?")        # → Layer 1
        vault.query("Why did I choose Stripe?")     # → Layer 2
        vault.query("Tell me about Stripe")         # → Hybrid
    """

    def __init__(
        self,
        master_key: bytes,
        kv_db_path: str = "~/.vault/kv_store.db",
        dora_adapter_path: Optional[str] = None,
        enable_router_logging: bool = False
    ):
        """
        Initialize hybrid vault.

        Args:
            master_key: 32-byte encryption key
            kv_db_path: Path to SQLite database
            dora_adapter_path: Path to encrypted DoRA adapter (optional)
            enable_router_logging: Log routing decisions
        """
        self.master_key = master_key

        # Initialize Layer 1: Encrypted KV Store
        self.kv_store = EncryptedKVStore(master_key, db_path=kv_db_path)
        logger.info("Initialized Layer 1 (KV Store)")

        # Initialize Layer 2: DoRA Adapters (optional for now)
        self.dora_adapter_path = dora_adapter_path
        self.dora_engine = None  # Will be initialized when needed
        if dora_adapter_path:
            self._init_dora_layer()

        # Initialize Smart Router
        self.router = SmartRouter()
        self.enable_router_logging = enable_router_logging

        logger.info("Initialized HybridVault")

    def _init_dora_layer(self):
        """Initialize Layer 2 (DoRA adapters)."""
        try:
            # Import here to avoid dependency if not using Layer 2
            import sys
            from pathlib import Path

            # Add src to path to import baseline
            src_path = Path(__file__).parent.parent.parent / "src"
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))

            from ephemeral_inference import EphemeralDoRAInference

            self.dora_engine = EphemeralDoRAInference(
                base_model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                encryption_key=self.master_key,
                enable_cache=True,
                load_in_4bit=True
            )
            logger.info("Initialized Layer 2 (DoRA)")
        except ImportError as e:
            logger.warning(f"Could not initialize Layer 2: {e}")
            self.dora_engine = None

    def store(
        self,
        content: str,
        data_type: str = "secret",  # "secret" or "knowledge"
        service: Optional[str] = None,
        tags: Optional[list] = None,
        description: Optional[str] = None
    ) -> str:
        """
        Store data in appropriate layer.

        Args:
            content: Data to store
            data_type: "secret" (Layer 1) or "knowledge" (Layer 2)
            service: Service name (required for secrets)
            tags: Optional tags
            description: Optional description

        Returns:
            Entry ID or confirmation message
        """
        if data_type == "secret":
            # Layer 1: Exact data
            if not service:
                raise ValueError("service name required for secrets")

            entry_id = self.kv_store.put(
                service=service,
                secret_value=content,
                entry_type=EntryType.SECRET,
                tags=tags,
                description=description
            )

            logger.info(f"Stored secret in Layer 1: {service}")
            return entry_id

        elif data_type == "knowledge":
            # Layer 2: Fuzzy knowledge
            # For now, just acknowledge (full DoRA training in future)
            logger.info(f"Knowledge stored (Layer 2 training not yet implemented)")
            return "knowledge_pending"

        else:
            raise ValueError(f"Unknown data_type: {data_type}")

    def query(self, query_text: str) -> Dict[str, Any]:
        """
        Query vault with automatic routing.

        Args:
            query_text: Natural language query

        Returns:
            Dictionary with:
                - strategy: Routing strategy used
                - layer: Layer(s) queried
                - service: Extracted service (if any)
                - result: Query result(s)
                - metadata: Additional info
        """
        # Route query
        plan = self.router.route(query_text)

        if self.enable_router_logging:
            logger.info(f"Query routed: {plan.strategy.value} (confidence: {plan.confidence:.0%})")

        # Execute based on strategy
        if plan.strategy == QueryStrategy.EXACT:
            return self._query_exact(plan, query_text)

        elif plan.strategy == QueryStrategy.FUZZY:
            return self._query_fuzzy(plan, query_text)

        elif plan.strategy == QueryStrategy.HYBRID:
            return self._query_hybrid(plan, query_text)

    def _query_exact(self, plan, query_text: str) -> Dict[str, Any]:
        """Query Layer 1 (Encrypted KV)."""
        if not plan.service:
            return {
                "strategy": "exact",
                "layer": 1,
                "service": None,
                "result": None,
                "error": "Could not determine service name from query",
                "metadata": {"confidence": plan.confidence}
            }

        # Retrieve from KV store
        secret = self.kv_store.get(plan.service)

        if secret is None:
            return {
                "strategy": "exact",
                "layer": 1,
                "service": plan.service,
                "result": None,
                "error": f"No secret found for service: {plan.service}",
                "metadata": {"confidence": plan.confidence}
            }

        return {
            "strategy": "exact",
            "layer": 1,
            "service": plan.service,
            "result": secret,
            "metadata": {
                "confidence": plan.confidence,
                "reasoning": plan.reasoning
            }
        }

    def _query_fuzzy(self, plan, query_text: str) -> Dict[str, Any]:
        """Query Layer 2 (DoRA adapter)."""
        if self.dora_engine is None:
            return {
                "strategy": "fuzzy",
                "layer": 2,
                "service": plan.service,
                "result": None,
                "error": "Layer 2 (DoRA) not initialized. Set dora_adapter_path in constructor.",
                "metadata": {"confidence": plan.confidence}
            }

        try:
            # Run DoRA inference
            response = self.dora_engine.inference_with_encrypted_adapter(
                encrypted_path=self.dora_adapter_path,
                prompt=query_text,
                max_tokens=150,
                temperature=0.7
            )

            return {
                "strategy": "fuzzy",
                "layer": 2,
                "service": plan.service,
                "result": response["response"],
                "metadata": {
                    "confidence": plan.confidence,
                    "reasoning": plan.reasoning,
                    "dora_metadata": response["metadata"]
                }
            }

        except Exception as e:
            logger.error(f"Layer 2 inference failed: {e}")
            return {
                "strategy": "fuzzy",
                "layer": 2,
                "service": plan.service,
                "result": None,
                "error": f"DoRA inference failed: {str(e)}",
                "metadata": {"confidence": plan.confidence}
            }

    def _query_hybrid(self, plan, query_text: str) -> Dict[str, Any]:
        """Query both layers and combine results."""
        results = {
            "strategy": "hybrid",
            "layers": [1, 2],
            "service": plan.service,
            "results": {},
            "metadata": {"confidence": plan.confidence}
        }

        # Query Layer 1 (exact data)
        if plan.service:
            secret = self.kv_store.get(plan.service)
            if secret:
                results["results"]["exact_data"] = {
                    "service": plan.service,
                    "value": secret
                }

        # Query Layer 2 (knowledge/context)
        if self.dora_engine and self.dora_adapter_path:
            try:
                response = self.dora_engine.inference_with_encrypted_adapter(
                    encrypted_path=self.dora_adapter_path,
                    prompt=query_text,
                    max_tokens=150,
                    temperature=0.7
                )
                results["results"]["knowledge"] = response["response"]
            except Exception as e:
                logger.error(f"Layer 2 failed in hybrid query: {e}")
                results["results"]["knowledge"] = None
                results["error"] = f"Layer 2 failed: {str(e)}"

        return results

    def explain_routing(self, query: str) -> str:
        """
        Explain how a query would be routed.

        Useful for debugging and user transparency.

        Args:
            query: Query to analyze

        Returns:
            Human-readable explanation
        """
        return self.router.explain(query)

    def get_stats(self) -> Dict[str, Any]:
        """Get vault statistics."""
        kv_stats = self.kv_store.get_stats()

        return {
            "layer_1": {
                "total_entries": kv_stats.total_entries,
                "services": kv_stats.services,
                "tags": kv_stats.tags,
                "size_bytes": kv_stats.total_size_bytes
            },
            "layer_2": {
                "initialized": self.dora_engine is not None,
                "adapter_path": self.dora_adapter_path
            }
        }

    def close(self):
        """Close vault and cleanup resources."""
        self.kv_store.close()
        logger.info("HybridVault closed")
