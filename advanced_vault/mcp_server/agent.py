"""
Local Agent for Enclave -- the primary interface for MCP-based interactions.

External AI assistants (e.g., Claude via MCP) issue high-level commands such as
``query``, ``summarize``, and ``draft``.  The LocalAgent fulfils those commands
by reading documents from the local RAG index, running inference on a local LLM
(Apple Silicon MLX or PyTorch), and returning **synthesised** answers.  Raw
document content is never exposed to the external caller, preserving the
privacy boundary that MCP enforces.

Core capabilities:
- RAG-based document retrieval with configurable similarity thresholds
- Local LLM inference (MLX on Apple Silicon, PyTorch elsewhere)
- Synthesised responses -- external AIs never see raw document text
- Document lifecycle management (add / delete / list)

Which documents the agent reads:
the same encrypted index the Enclave app and ``enclave model ingest`` write
to -- ``<vault>/private_models/<profile>/vault/rag.db`` with that profile's
``master.key``, where ``<vault>`` is ``$VAULT_PATH`` (default ``~/.vault``).
The profile comes from ``private_models.manager.resolve_active_profile()``:
the profile last active in the app, else the first profile by name, else
``workspace``.  Set ``ENCLAVE_PROFILE=<name>`` to pin a profile explicitly.
The profile is re-resolved on every call and the index is reopened only when
another process changes it (``rag.db`` or its saved HNSW index), so documents
added in the app show up without restarting the MCP server.  Reading never
creates an index or a key; a profile with no index yet is reported as having
zero documents, with a hint on how to add some.
"""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants -- extracted so they are easy to find and override.
# ---------------------------------------------------------------------------

# Minimum cosine-similarity score for a RAG chunk to be considered relevant.
RAG_QUERY_THRESHOLD: float = 0.3
RAG_SUMMARY_THRESHOLD: float = 0.25
RAG_DRAFT_THRESHOLD: float = 0.25

# Maximum characters of raw document content passed to the summariser.
SUMMARISE_CONTENT_CHAR_LIMIT: int = 8000

# Fallback context truncation limits (characters) when the LLM is unavailable.
FALLBACK_CONTEXT_SHORT: int = 1000
FALLBACK_CONTEXT_LONG: int = 2000

# Maximum number of documents returned by ``get_status``.
STATUS_MAX_DOCUMENTS: int = 20
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)

# Returned by ``query`` instead of letting the LLM answer without any sources.
NO_MATCH_ANSWER: str = (
    "No indexed documents matched this question, so no answer was generated. "
    "Enclave answers agent queries only from the user's indexed documents."
)


def _sanitize_model_output(text: str) -> str:
    """Remove hidden reasoning tags from model output before returning it."""
    cleaned = THINK_BLOCK_RE.sub("", text or "")
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def _loaded_model_name(engine: Any) -> str:
    """Name of the model the engine runs: its MLX model, or the PyTorch one."""
    if getattr(engine, "backend", None) == "torch":
        return getattr(engine, "MODEL_NAME", None) or "unknown"
    return getattr(engine, "MLX_MODEL_NAME", None) or "unknown"


def _index_signature(db_path: Path) -> tuple:
    """Fingerprint the files another process changes when it edits an index.

    ``rag.db`` changes on every add and delete; ``rag.hnsw`` and
    ``rag.meta.json`` are the saved HNSW index that opening loads.
    ``rag.brute.json`` is deliberately left out: without hnswlib, opening an
    index rebuilds the brute-force vector index from ``rag.db`` and rewrites
    that file, so fingerprinting it would make every call reopen the index.
    """
    entries = []
    for path in (db_path, db_path.with_suffix(".hnsw"), db_path.with_suffix(".meta.json")):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path.name, stat.st_mtime_ns, stat.st_size))
    return str(db_path), tuple(entries)


def _redact_home(text: str) -> str:
    """Show paths under the home directory as ``~/...``, so the external
    caller is not told the local username."""
    home = str(Path.home()).rstrip("/\\")
    if not home:
        return text
    return re.sub(re.escape(home) + r"(?=[/\\'\"\s),]|$)", "~", text)


class LocalAgent:
    """
    Local trusted agent that synthesizes responses.

    External AIs command this agent via MCP.
    The agent reads documents locally and returns synthesized answers.
    External AIs never see raw document content.
    """

    def __init__(
        self,
        vault_path: str = "~/.vault",
        model_name: Optional[str] = None,
        profile: Optional[str] = None
    ):
        """
        Initialize local agent.

        Args:
            vault_path: Enclave data directory (``$VAULT_PATH``); profile
                indexes live under ``<vault_path>/private_models``
            model_name: Optional specific model to use
            profile: Profile whose index to read (default: ``$ENCLAVE_PROFILE``,
                else the profile active in the Enclave app)
        """
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self._profile = profile
        self._rag_index = None
        self._rag_signature = None
        # Kept across reopens so switching profiles never reloads the model.
        self._embedding_engine = None
        # Set by _get_rag_index(): the resolved profile index, and why it could
        # not be opened (None when it simply does not exist yet).
        self._index_location = None
        self._index_error: Optional[str] = None
        self._inference_engine = None
        self._model_name = model_name
        self._model_loaded = False

        logger.info(f"Initialized LocalAgent at {self.vault_path}")

    def _get_rag_index(self, create: bool = False) -> Optional["RAGIndex"]:  # noqa: F821
        """
        Open the active profile's encrypted index -- the one the app and CLI write to.

        Returns None when there is no index to read: ``_index_error`` then says
        why, or stays None when the profile has no index yet.  Nothing is
        created unless ``create`` is set, and then only for an existing
        profile, in that profile's own directory (as the app's first ingest).
        """
        self._index_error = None
        self._index_location = None
        try:
            from advanced_vault.private_models.manager import (
                PRIVATE_MODELS_DIRNAME,
                PrivateModelManager,
                resolve_active_profile,
            )
            from advanced_vault.training import RAGIndex
        except ImportError as e:
            logger.warning(f"RAG index not available: {e}")
            self._index_error = f"RAG index not available: {e}"
            return None

        try:
            location = resolve_active_profile(str(self.vault_path), profile=self._profile)
        except ValueError as e:
            self._index_error = f"RAG index not available: {e}"
            return None
        except OSError as e:
            # strerror only: str(e) would carry the absolute path.
            reason = e.strerror or type(e).__name__
            self._index_error = f"RAG index not available: cannot read profiles ({reason})"
            return None
        self._index_location = location

        if not location.db_path.exists():
            # Drop any handle on a previous profile's index.  Never close() it:
            # that re-saves its vector index over files another process owns.
            self._rag_index = None
            if not create:
                return None
            if not location.profile_exists:
                self._index_error = f"RAG index not available: {self._setup_hint(location)}"
                return None
            manager = PrivateModelManager(root_path=str(self.vault_path / PRIVATE_MODELS_DIRNAME))
            manager._load_or_create_master_key(location.profile)

        # The app and CLI write to this index from other processes; reopen it
        # when its files change so new documents are searchable here too.
        # Taken before opening, so a write that lands mid-open is not missed.
        signature = _index_signature(location.db_path)
        if self._rag_index is not None and signature == self._rag_signature:
            return self._rag_index

        if not location.key_path.exists():
            # Fail closed: a new key could never decrypt the existing index.
            self._rag_index = None
            self._index_error = (
                f"RAG index not available: the encryption key for profile "
                f"'{location.profile}' is missing, so its documents cannot be read"
            )
            return None

        try:
            # Drop the old handle without close(): that would re-save its
            # vector index over files another process owns.
            self._rag_index = None
            self._rag_index = RAGIndex(
                master_key=location.key_path.read_bytes(),
                db_path=str(location.db_path),
                embedding_engine=self._embedding_engine,
            )
            self._embedding_engine = self._rag_index.embedding_engine
            self._rag_signature = signature
            logger.info(f"Encrypted RAG index opened for profile '{location.profile}'")
        except (ImportError, OSError, ValueError, RuntimeError, sqlite3.Error) as e:
            # ImportError: the embedding backend (sentence-transformers) is
            # only imported when the index loads its model.
            logger.error(f"Failed to open RAG index for profile '{location.profile}': {e}")
            self._rag_index = None
            self._index_error = f"RAG index not available: {_redact_home(str(e))}"
            return None
        return self._rag_index

    def _index_unavailable_reason(self) -> str:
        """Explain why ``_get_rag_index()`` returned None."""
        if self._index_error:
            return self._index_error
        if self._index_location is not None:
            return (
                "RAG index not available: no documents are indexed yet for profile "
                f"'{self._index_location.profile}'"
            )
        return "RAG index not available"

    def _uses_app_vault(self) -> bool:
        """True when this is the vault the Enclave app uses (always ``~/.vault``)."""
        return self.vault_path == Path("~/.vault").expanduser()

    def _enclave_command(self, *args: str) -> str:
        """An ``enclave`` CLI command acting on this agent's vault directory."""
        command = ["enclave"]
        if not self._uses_app_vault():
            vault = _redact_home(str(self.vault_path))
            if any(ch.isspace() for ch in vault):
                # "~" does not expand inside quotes; $HOME does.
                vault = '"' + re.sub(r"^~(?=[/\\]|$)", "$HOME", vault) + '"'
            command += ["--vault-path", vault]
        return " ".join(command + list(args))

    def _setup_hint(self, location: Any) -> str:
        """How to get documents into ``location``'s index (it has none yet).

        ``enclave model ingest`` fails for a profile that does not exist, so
        then the hint says to create it first.  The app is only suggested for
        the vault it uses.
        """
        profile = location.profile
        ingest = f"`{self._enclave_command('model', 'ingest', profile, '<paths>')}`"
        create = f"`{self._enclave_command('model', 'create', profile)}`"
        app = self._uses_app_vault()
        if location.profile_exists:
            how = f"add files in the Enclave app, or run {ingest}" if app else f"run {ingest}"
            return f"Profile '{profile}' has no indexed documents yet: {how}."
        if app:
            how = f"open the Enclave app (or run {create}), then add files in the app or run {ingest}"
        else:
            how = f"run {create}, then {ingest}"
        return f"Profile '{profile}' does not exist yet: {how}."

    def _no_match_answer(self) -> str:
        """Answer returned when retrieval finds nothing to answer from."""
        location = self._index_location
        if location is not None and not location.db_path.exists():
            return f"{NO_MATCH_ANSWER} {self._setup_hint(location)}"
        return NO_MATCH_ANSWER

    def _legacy_index_document_count(self) -> int:
        """Documents in ``$VAULT_PATH/rag.db``, the index older builds wrote.

        The agent no longer reads it; the count only lets ``get_status`` tell
        the user to add those files again.  Opened read-only.
        """
        legacy_db = self.vault_path / "rag.db"
        if not legacy_db.is_file():
            return 0
        try:
            conn = sqlite3.connect(f"{legacy_db.resolve().as_uri()}?mode=ro", uri=True)
            try:
                return int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            finally:
                conn.close()
        except (sqlite3.Error, OSError, RuntimeError, ValueError, TypeError):
            return 0

    def _get_inference_engine(self) -> Optional["LocalInferenceEngine"]:  # noqa: F821
        """Get or create inference engine."""
        if self._inference_engine is None:
            try:
                from advanced_vault.gui.local_inference import LocalInferenceEngine
                self._inference_engine = LocalInferenceEngine(
                    cache_dir=str(self.vault_path / "models")
                )
                logger.info("Inference engine initialized")
            except (ImportError, RuntimeError) as e:
                # RuntimeError: LocalInferenceEngine raises when no ML backend
                # (mlx or torch) is installed — degrade to the safe fallback
                # instead of crashing every agent_* tool.
                logger.warning(f"Inference engine not available: {e}")
                return None
        return self._inference_engine

    def _ensure_model_loaded(self) -> bool:
        """Ensure the inference model is loaded."""
        if self._model_loaded:
            return True

        engine = self._get_inference_engine()
        if engine is None:
            return False

        try:
            success = engine.load_model()
            self._model_loaded = success
            return success
        except (RuntimeError, OSError) as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def query(
        self,
        question: str,
        max_context_tokens: int = 1500,
        max_response_tokens: int = 512,
        temperature: float = 0.7,
        use_rag: bool = True
    ) -> Dict[str, Any]:
        """
        Query the agent with a question.

        The agent retrieves relevant context from indexed documents
        and generates a synthesized response. External callers never
        see raw document content.

        Args:
            question: The question to answer
            max_context_tokens: Maximum tokens for RAG context
            max_response_tokens: Maximum tokens in response
            temperature: Generation temperature
            use_rag: Whether to use RAG for context

        Returns:
            Dict with 'answer', 'sources', 'model_used'
        """
        result = {
            "answer": "",
            "sources": [],
            "model_used": None,
            "rag_used": False,
            "error": None
        }

        # Get RAG context if requested.  Without any retrieved source there is
        # nothing to ground an answer in, so the LLM is not asked at all.
        context = ""
        if use_rag:
            rag_index = self._get_rag_index()
            if rag_index:
                try:
                    rag_index.clear_errors()
                    rag_results = rag_index.search(
                        query=question,
                        top_k=5,
                        threshold=RAG_QUERY_THRESHOLD
                    )
                    decrypt_errors = rag_index.get_last_errors()
                    if not rag_results and isinstance(decrypt_errors, list) and decrypt_errors:
                        # Search skips chunks it cannot decrypt; with nothing
                        # left, "no match" would hide a wrong or rotated key.
                        result["error"] = (
                            f"Document search failed: {len(decrypt_errors)} indexed chunk(s) "
                            "could not be decrypted with the profile's key"
                        )
                        return result

                    if rag_results:
                        context_parts = []
                        for r in rag_results:
                            context_parts.append(r.chunk.content)
                            excerpt = (r.chunk.content or "").replace("\n", " ").strip()
                            if len(excerpt) > 180:
                                excerpt = excerpt[:177] + "..."
                            result["sources"].append({
                                "document": r.document_name,
                                "score": round(r.score, 3),
                                "chunk_index": r.chunk.index,
                                "excerpt": excerpt,
                            })

                        context = "\n\n".join(context_parts)
                        result["rag_used"] = True
                        logger.info(f"Found {len(rag_results)} relevant chunks")
                except (ValueError, RuntimeError, OSError, sqlite3.Error) as e:
                    logger.error(f"RAG search failed: {e}")
                    result["error"] = f"Document search failed: {_redact_home(str(e))}"
                    return result
            elif self._index_error is not None or self._index_location is None:
                # The index could not be read (as opposed to not existing yet).
                result["error"] = self._index_unavailable_reason()
                return result

            if not result["rag_used"]:  # no index yet, or nothing matched
                result["answer"] = self._no_match_answer()
                return result

        # Ensure model is loaded
        if not self._ensure_model_loaded():
            if context:
                result["answer"] = (
                    "Relevant local documents were found, but the local model backend "
                    "is unavailable. No raw document text is exposed in this fallback. "
                    "Install or configure MLX/local inference and try again."
                )
                result["model_used"] = "no-model-safe-fallback"
            else:
                result["error"] = "Model not available and no relevant documents found"
            return result

        # Build prompt with context
        engine = self._get_inference_engine()
        result["model_used"] = _loaded_model_name(engine)

        if context:
            system_prompt = """You are Enclave, a helpful AI assistant with access to the user's private documents.
Answer questions based on the provided context from indexed documents.
Be accurate and cite which documents the information comes from when relevant.
If the context doesn't contain relevant information, say so.
Return only the final answer. Do not narrate your reasoning or planning."""

            prompt = f"""Context from indexed documents:
{context}

Question: {question}

Answer based on the context above:"""
        else:
            system_prompt = """You are Enclave, a helpful AI assistant running locally for privacy.
You don't currently have any documents indexed. Help the user with general questions
or suggest they index documents for context-aware answers.
Return only the final answer. Do not narrate your reasoning or planning."""

            prompt = question

        # Generate response.  engine.generate() applies the model's chat
        # template itself, so pass plain text: templating here as well would
        # nest one chat transcript inside another.
        try:
            response = engine.generate(
                f"{system_prompt}\n\n{prompt}",
                max_tokens=max_response_tokens,
                temperature=temperature
            )

            result["answer"] = _sanitize_model_output(response)

        except (RuntimeError, ValueError) as e:
            logger.error(f"Generation failed: {e}")
            result["error"] = str(e)
            if context:
                result["answer"] = (
                    "Generation failed after retrieving relevant local context. "
                    "No raw document text is exposed in this error path."
                )

        return result

    def summarize(
        self,
        topic_or_document: str,
        max_length: int = 500
    ) -> Dict[str, Any]:
        """
        Summarize a topic or document.

        Args:
            topic_or_document: Topic to summarize or document name
            max_length: Approximate max length of summary

        Returns:
            Dict with 'summary', 'sources'
        """
        result = {
            "summary": "",
            "sources": [],
            "error": None
        }

        # Search for relevant content
        rag_index = self._get_rag_index()
        if rag_index is None:
            result["error"] = self._index_unavailable_reason()
            return result

        try:
            # Try to find specific document first
            documents = rag_index.list_documents()
            matching_doc = None
            for doc in documents:
                if topic_or_document.lower() in doc["name"].lower():
                    matching_doc = doc
                    break

            if matching_doc:
                # Summarize specific document
                full_doc = rag_index.get_document(matching_doc["id"])
                if full_doc:
                    content = full_doc.content[:SUMMARISE_CONTENT_CHAR_LIMIT]
                    result["sources"].append({
                        "document": matching_doc["name"],
                        "type": "full_document"
                    })
            else:
                # Search by topic
                rag_results = rag_index.search(
                    query=topic_or_document,
                    top_k=10,
                    threshold=RAG_SUMMARY_THRESHOLD
                )
                content = "\n\n".join([r.chunk.content for r in rag_results])
                for r in rag_results:
                    if r.document_name not in [s["document"] for s in result["sources"]]:
                        result["sources"].append({
                            "document": r.document_name,
                            "score": round(r.score, 3)
                        })

            if not content:
                result["error"] = "No relevant content found"
                return result

            # Generate summary
            if not self._ensure_model_loaded():
                result["error"] = (
                    "Local model backend unavailable. Summary withheld to avoid "
                    "returning raw document text."
                )
                return result

            engine = self._get_inference_engine()
            prompt = f"""Please provide a concise summary of the following content.
Focus on the key points and main ideas. Keep the summary under {max_length} characters.
Return only the summary. Do not include analysis or hidden reasoning.

Content:
{content}

Summary:"""

            result["summary"] = _sanitize_model_output(engine.generate(
                prompt,
                max_tokens=max_length // 3,  # Rough token estimate
                temperature=0.3
            ))

        except (ValueError, RuntimeError, OSError) as e:
            logger.error(f"Summarization failed: {e}")
            result["error"] = str(e)

        return result

    def draft(
        self,
        description: str,
        style: str = "professional",
        max_length: int = 1000
    ) -> Dict[str, Any]:
        """
        Draft content based on indexed documents.

        Args:
            description: What to draft (e.g., "email about project status")
            style: Writing style (professional, casual, technical)
            max_length: Approximate max length

        Returns:
            Dict with 'draft', 'sources'
        """
        result = {
            "draft": "",
            "sources": [],
            "error": None
        }

        # Get relevant context
        rag_index = self._get_rag_index()
        context = ""
        if rag_index:
            try:
                rag_results = rag_index.search(
                    query=description,
                    top_k=5,
                    threshold=RAG_DRAFT_THRESHOLD
                )
                if rag_results:
                    context = "\n\n".join([r.chunk.content for r in rag_results])
                    for r in rag_results:
                        result["sources"].append({
                            "document": r.document_name,
                            "score": round(r.score, 3)
                        })
            except (ValueError, RuntimeError, OSError) as e:
                logger.warning(f"RAG search for draft failed: {e}")

        # Generate draft
        if not self._ensure_model_loaded():
            result["error"] = "Model not available for drafting"
            return result

        engine = self._get_inference_engine()

        style_instructions = {
            "professional": "Use a professional, formal tone suitable for business communication.",
            "casual": "Use a friendly, casual tone.",
            "technical": "Use precise technical language with appropriate terminology.",
        }

        style_inst = style_instructions.get(style, style_instructions["professional"])

        if context:
            prompt = f"""Draft the following content using information from the provided context.
{style_inst}
Return only the requested draft. Do not include analysis or planning notes.

Context from documents:
{context}

Request: {description}

Draft:"""
        else:
            prompt = f"""Draft the following content.
{style_inst}
Note: No specific documents are indexed, so using general knowledge.
Return only the requested draft. Do not include analysis or planning notes.

Request: {description}

Draft:"""

        try:
            result["draft"] = _sanitize_model_output(engine.generate(
                prompt,
                max_tokens=max_length // 3,
                temperature=0.7
            ))
        except (RuntimeError, ValueError) as e:
            logger.error(f"Draft generation failed: {e}")
            result["error"] = str(e)

        return result

    def get_status(self) -> Dict[str, Any]:
        """
        Get agent status and indexed documents.

        Returns:
            Dict with status information
        """
        status = {
            "ready": False,
            "model_loaded": self._model_loaded,
            "model_name": None,
            "rag_available": False,
            "documents": [],
            "document_count": 0,
            "chunk_count": 0,
            "backend": None,
            "profile": None,
            "profile_exists": False,
            "index_path": None,
            "index_error": None,
            # What to do when the profile has no documents yet (None otherwise).
            "index_hint": None,
            # Documents in an index older builds wrote, which is no longer read.
            "legacy_index_documents": 0
        }

        # Check inference engine
        engine = self._get_inference_engine()
        if engine:
            status["backend"] = getattr(engine, 'backend', 'unknown')
            if engine.model is not None:
                status["model_loaded"] = True
                status["model_name"] = _loaded_model_name(engine)

        # Check RAG index (the active profile's; reported even before it exists)
        rag_index = self._get_rag_index()
        location = self._index_location
        if location is not None:
            status["profile"] = location.profile
            status["profile_exists"] = location.profile_exists
            status["index_path"] = str(location.db_path)
        status["index_error"] = self._index_error
        if rag_index:
            status["rag_available"] = True
            try:
                stats = rag_index.stats()
                status["document_count"] = stats["document_count"]
                status["chunk_count"] = stats["chunk_count"]

                docs = rag_index.list_documents()
                status["documents"] = [
                    {"name": d["name"], "chunks": d["chunk_count"]}
                    for d in docs[:STATUS_MAX_DOCUMENTS]
                ]
            except (ValueError, RuntimeError, OSError, sqlite3.Error) as e:
                logger.warning(f"Failed to get RAG stats: {e}")
        if location is not None and status["index_error"] is None and not status["document_count"]:
            status["index_hint"] = self._setup_hint(location)
        status["legacy_index_documents"] = self._legacy_index_document_count()

        status["ready"] = status["rag_available"] or status["model_loaded"]
        return status

    def add_document(
        self,
        name: str,
        content: str,
        source_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a document to the RAG index.

        Args:
            name: Document name
            content: Document content
            source_path: Optional source file path
            metadata: Optional metadata

        Returns:
            Dict with document info
        """
        rag_index = self._get_rag_index(create=True)
        if rag_index is None:
            return {"error": self._index_unavailable_reason()}

        try:
            doc = rag_index.add_document(
                name=name,
                content=content,
                source_path=source_path,
                metadata=metadata
            )
            return {
                "id": doc.id,
                "name": doc.name,
                "chunks": len(doc.chunks),
                "success": True
            }
        except (ValueError, RuntimeError, OSError) as e:
            logger.error(f"Failed to add document: {e}")
            return {"error": str(e)}

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        Delete a document from the index.

        Args:
            document_id: Document ID to delete

        Returns:
            Dict with success status
        """
        rag_index = self._get_rag_index()
        if rag_index is None:
            return {"error": self._index_unavailable_reason()}

        success = rag_index.delete_document(document_id)
        return {"success": success}


# Singleton instance with thread-safe initialization
import threading
_agent: Optional[LocalAgent] = None
_agent_lock = threading.Lock()


def get_agent(vault_path: str = "~/.vault") -> LocalAgent:
    """
    Get or create the local agent singleton (thread-safe).

    Args:
        vault_path: Enclave data directory (``$VAULT_PATH``); the agent reads
            the active profile's index and key under it

    Returns:
        LocalAgent singleton instance
    """
    global _agent
    # Double-checked locking pattern for thread safety
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = LocalAgent(vault_path=vault_path)
    return _agent
