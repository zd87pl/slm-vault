"""
Hybrid Vault

Unified interface combining:
- Layer 1: Encrypted KV store (exact data)
- Layer 2: DoRA adapters (fuzzy knowledge)

The hybrid vault automatically routes queries to the appropriate layer(s)
using the smart router.
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from .smart_router import SmartRouter, QueryStrategy
from advanced_vault.encrypted_kv import EncryptedKVStore, EntryType, QueryFilter

logger = logging.getLogger(__name__)

# Common words ignored when looking for entries related to a query
_STOP_WORDS = frozenset({
    "my", "the", "a", "an", "is", "are", "what", "show", "get", "give", "find", "retrieve"
})


def _normalize_name(name: str) -> str:
    """Normalize an entry name for comparison (case- and whitespace-insensitive)."""
    return " ".join(name.split()).casefold()


def _names_only_message(names: List[str]) -> str:
    """Explain why no value was returned and which exact names to ask for."""
    return (
        "Values are only returned for an exact entry name. "
        f"Matching entries: {', '.join(names)}. Ask again with one of these names."
    )


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
        vault.query("stripe")                       # → Layer 1 value (exact entry name)
        vault.query("What's my Stripe key?")        # → Layer 1 entry names only
        vault.query("Why did I choose Stripe?")     # → Layer 2
        vault.query("Tell me about Stripe")         # → Hybrid
    """

    def __init__(
        self,
        master_key: bytes,
        kv_db_path: str = "~/.vault/kv_store.db",
        dora_adapter_path: Optional[str] = None,
        runpod_endpoint_id: Optional[str] = None,
        runpod_api_key: Optional[str] = None,
        enable_router_logging: bool = False
    ):
        """
        Initialize hybrid vault.

        Args:
            master_key: 32-byte encryption key for KV encryption
            kv_db_path: Path to SQLite database
            dora_adapter_path: Path to encrypted DoRA adapter (optional)
            runpod_endpoint_id: RunPod endpoint ID for remote inference (optional)
            runpod_api_key: RunPod API key for remote inference (optional)
            enable_router_logging: Log routing decisions
        """
        self.master_key = master_key

        # Initialize Layer 1: Encrypted KV Store
        self.kv_store = EncryptedKVStore(master_key, db_path=kv_db_path)
        logger.info("Initialized Layer 1 (KV Store)")

        # Initialize Layer 2: DoRA Adapters (optional)
        self.dora_adapter_path = dora_adapter_path
        self.runpod_endpoint_id = runpod_endpoint_id
        self.runpod_api_key = runpod_api_key
        self.dora_engine = None  # Will be initialized when needed

        if dora_adapter_path and (runpod_endpoint_id and runpod_api_key):
            self._init_dora_layer_runpod()
        elif dora_adapter_path:
            self._init_dora_layer()

        # Initialize Smart Router
        self.router = SmartRouter()
        self.enable_router_logging = enable_router_logging

        logger.info("Initialized HybridVault")

    def _init_dora_layer(self):
        """Initialize Layer 2 (DoRA adapters) - local inference."""
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
            logger.info("Initialized Layer 2 (DoRA - Local)")
        except ImportError as e:
            logger.warning(f"Could not initialize Layer 2: {e}")
            self.dora_engine = None

    def _init_dora_layer_runpod(self):
        """Initialize Layer 2 (DoRA adapters) - RunPod inference."""
        try:
            # Create RunPod client for remote inference
            from .runpod_client import RunPodDoRAClient

            self.dora_engine = RunPodDoRAClient(
                endpoint_id=self.runpod_endpoint_id,
                api_key=self.runpod_api_key,
                adapter_path=self.dora_adapter_path
            )
            logger.info("Initialized Layer 2 (DoRA - RunPod)")
        except ImportError as e:
            logger.warning(f"Could not initialize RunPod Layer 2: {e}")
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
            # For now, store in Layer 1 KV store as a fallback until full DoRA training is implemented.
            # This ensures knowledge entries are persisted and retrievable immediately.
            service = service or "knowledge"
            entry_id = self.kv_store.put(
                service=service,
                secret_value=content,
                entry_type=EntryType.KNOWLEDGE,
                tags=tags,
                description=description
            )
            logger.info(f"Stored knowledge in Layer 1 fallback: {service} (entry: {entry_id})")
            return entry_id

        else:
            raise ValueError(f"Unknown data_type: {data_type}")

    def query(self, query_text: str) -> Dict[str, Any]:
        """
        Query vault with automatic routing.

        A stored Layer 1 value (secret or note) is returned only when the query
        is exactly the name of one stored entry (case- and whitespace-
        insensitive). Any other query can at most list the names of related
        entries in ``matches`` so the caller can ask again with the exact name;
        it never returns their values.

        Args:
            query_text: Entry name or natural language query

        Returns:
            Dictionary with:
                - strategy: Routing strategy used
                - layer: Layer(s) queried
                - service: Extracted service (if any)
                - result: Query result(s)
                - matches: Names of related entries, when no value is returned
                - metadata: Additional info
        """
        # Layer 1 values are released only for a precise entry name, never on
        # keyword overlap with a natural-language query
        exact = self._query_by_name(query_text)
        if exact is not None:
            return exact

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

    def _query_by_name(self, query_text: str) -> Optional[Dict[str, Any]]:
        """
        Return the stored value when the query is exactly one entry's name.

        Returns None when no entry has that name, so the query is routed as
        natural language instead.
        """
        wanted = _normalize_name(query_text)
        if not wanted:
            return None

        names = [name for name in self.kv_store.list_services() if _normalize_name(name) == wanted]
        if len(names) > 1 and query_text.strip() in names:
            # Names differing only in case are distinct entries; the verbatim
            # name still selects exactly one of them
            names = [query_text.strip()]

        if not names:
            return None
        if len(names) > 1:
            return self._names_only("exact", 1, None, names, confidence=1.0)

        service = names[0]
        return {
            "strategy": "exact",
            "layer": 1,
            "service": service,
            "result": self.kv_store.get(service),
            "metadata": {
                "confidence": 1.0,
                "reasoning": f"Query is the exact name of entry '{service}'"
            }
        }

    def _matching_names(self, query_text: str, service_hint: Optional[str] = None) -> List[str]:
        """
        Names of entries related to a natural-language query, best match first.

        Only entry metadata is compared; values are never decrypted here.
        """
        query_words = set(query_text.lower().split()) - _STOP_WORDS
        hint = _normalize_name(service_hint) if service_hint else None

        scores: Dict[str, float] = {}
        for entry in self.kv_store.search(QueryFilter()):
            # Check if query words appear in service name
            service_lower = entry.service.lower()
            score = len(query_words & set(service_lower.split()))

            # Service name extracted by the router
            if hint and _normalize_name(entry.service) == hint:
                score += 1

            # Also check if query words appear inside the service name
            if any(word in service_lower for word in query_words if len(word) > 2):
                score += 1

            # Also check tags and description
            if entry.tags:
                score += len(query_words & set(" ".join(entry.tags).lower().split())) * 0.5
            if entry.description:
                score += len(query_words & set(entry.description.lower().split())) * 0.3

            if score > scores.get(entry.service, 0):
                scores[entry.service] = score

        return sorted(scores, key=lambda name: (-scores[name], name))

    def _names_only(
        self,
        strategy: str,
        layer,
        service: Optional[str],
        names: List[str],
        confidence: float
    ) -> Dict[str, Any]:
        """Result for a query that is not exactly one entry name: names, never values."""
        return {
            "strategy": strategy,
            "layer": layer,
            "service": service,
            "result": None,
            "matches": names,
            "error": _names_only_message(names),
            "metadata": {"confidence": confidence}
        }

    def _query_exact(self, plan, query_text: str) -> Dict[str, Any]:
        """
        Query Layer 1 (Encrypted KV) with a natural-language query.

        The query is not exactly an entry name (see _query_by_name), so only
        the names of matching entries are returned, never their values.
        """
        names = self._matching_names(query_text, plan.service)
        if names:
            return self._names_only("exact", 1, plan.service, names, plan.confidence)

        # No match found
        if not plan.service:
            return {
                "strategy": "exact",
                "layer": 1,
                "service": None,
                "result": None,
                "error": "Could not determine service name from query and no matching entries found",
                "metadata": {"confidence": plan.confidence}
            }
        else:
            return {
                "strategy": "exact",
                "layer": 1,
                "service": plan.service,
                "result": None,
                "error": f"No secret found for service: {plan.service}",
                "metadata": {"confidence": plan.confidence}
            }

    def _query_fuzzy(self, plan, query_text: str) -> Dict[str, Any]:
        """Query Layer 2 (DoRA adapter)."""
        if self.dora_engine is None or self.dora_adapter_path is None:
            # Fallback to Layer 1 if Layer 2 is not available
            # This handles cases where query was routed to fuzzy but Layer 2 isn't initialized
            logger.warning(f"Layer 2 not available, falling back to Layer 1 for query: {query_text}")

            # List matching Layer 1 entries by name only: a natural-language
            # query must never return a stored value
            names = self._matching_names(query_text, plan.service)
            if names:
                return self._names_only("exact_fallback", 1, plan.service, names, plan.confidence)

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

        # Query Layer 1 (exact data): names of matching entries only, never
        # their values
        names = self._matching_names(query_text, plan.service)
        if names:
            results["matches"] = names
            results["error"] = _names_only_message(names)

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
