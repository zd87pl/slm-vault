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
"""

import logging
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


class LocalAgent:
    """
    Local trusted agent that synthesizes responses.

    External AIs command this agent via MCP.
    The agent reads documents locally and returns synthesized answers.
    External AIs never see raw document content.
    """

    def __init__(
        self,
        vault_path: str = "~/.enclave",
        model_name: Optional[str] = None,
        master_key: Optional[bytes] = None
    ):
        """
        Initialize local agent.

        Args:
            vault_path: Base path for agent data
            model_name: Optional specific model to use
            master_key: 32-byte encryption key for RAG index (loaded from vault if not provided)
        """
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self._rag_index = None
        self._inference_engine = None
        self._model_name = model_name
        self._model_loaded = False

        # Handle master key - load from vault if not provided
        if master_key is not None:
            self._master_key = master_key
        else:
            self._master_key = self._load_or_create_master_key()

        logger.info(f"Initialized LocalAgent at {self.vault_path}")

    def _load_or_create_master_key(self) -> bytes:
        """Load existing master key from vault or create a new one."""
        import os
        key_path = self.vault_path / "master.key"

        if key_path.exists():
            with open(key_path, "rb") as f:
                key = f.read()
            logger.info("Loaded existing master key for RAG")
            return key
        else:
            # Generate new master key
            key = os.urandom(32)
            with open(key_path, "wb") as f:
                f.write(key)
            # Set secure permissions
            os.chmod(key_path, 0o600)
            logger.info("Generated new master key for RAG")
            return key

    def _get_rag_index(self) -> Optional["RAGIndex"]:  # noqa: F821
        """Get or create RAG index with encryption."""
        if self._rag_index is None:
            try:
                from advanced_vault.training import RAGIndex
                self._rag_index = RAGIndex(
                    master_key=self._master_key,
                    db_path=str(self.vault_path / "rag.db")
                )
                logger.info("Encrypted RAG index initialized")
            except ImportError as e:
                logger.warning(f"RAG index not available: {e}")
                return None
        return self._rag_index

    def _get_inference_engine(self) -> Optional["LocalInferenceEngine"]:  # noqa: F821
        """Get or create inference engine."""
        if self._inference_engine is None:
            try:
                from advanced_vault.gui.local_inference import LocalInferenceEngine
                self._inference_engine = LocalInferenceEngine(
                    cache_dir=str(self.vault_path / "models")
                )
                logger.info("Inference engine initialized")
            except ImportError as e:
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

        # Get RAG context if available and requested
        context = ""
        if use_rag:
            rag_index = self._get_rag_index()
            if rag_index:
                try:
                    rag_results = rag_index.search(
                        query=question,
                        top_k=5,
                        threshold=RAG_QUERY_THRESHOLD
                    )

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
                except (ValueError, RuntimeError, OSError) as e:
                    logger.error(f"RAG search failed: {e}")

        # Ensure model is loaded
        if not self._ensure_model_loaded():
            # Fallback: return context-only response if no model
            if context:
                result["answer"] = (
                    "Based on the indexed documents, here is relevant information:\n\n"
                    f"{context[:FALLBACK_CONTEXT_LONG]}..."
                )
                result["model_used"] = "context-only (model not available)"
            else:
                result["error"] = "Model not available and no relevant documents found"
            return result

        # Build prompt with context
        engine = self._get_inference_engine()
        result["model_used"] = getattr(engine, 'MLX_MODEL_NAME', 'unknown')

        if context:
            system_prompt = """You are Enclave, a helpful AI assistant with access to the user's private documents.
Answer questions based on the provided context from indexed documents.
Be accurate and cite which documents the information comes from when relevant.
If the context doesn't contain relevant information, say so."""

            prompt = f"""Context from indexed documents:
{context}

Question: {question}

Answer based on the context above:"""
        else:
            system_prompt = """You are Enclave, a helpful AI assistant running locally for privacy.
You don't currently have any documents indexed. Help the user with general questions
or suggest they index documents for context-aware answers."""

            prompt = question

        # Generate response
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]

            # Format with chat template
            if hasattr(engine.tokenizer, 'apply_chat_template'):
                formatted_prompt = engine.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                formatted_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:"

            response = engine.generate(
                formatted_prompt,
                max_tokens=max_response_tokens,
                temperature=temperature
            )

            result["answer"] = response.strip()

        except (RuntimeError, ValueError) as e:
            logger.error(f"Generation failed: {e}")
            result["error"] = str(e)
            if context:
                result["answer"] = f"Generation failed, but found relevant context:\n{context[:FALLBACK_CONTEXT_SHORT]}"

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
            result["error"] = "RAG index not available"
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
                result["summary"] = f"Key points from documents:\n{content[:max_length]}"
                return result

            engine = self._get_inference_engine()
            prompt = f"""Please provide a concise summary of the following content.
Focus on the key points and main ideas. Keep the summary under {max_length} characters.

Content:
{content}

Summary:"""

            result["summary"] = engine.generate(
                prompt,
                max_tokens=max_length // 3,  # Rough token estimate
                temperature=0.3
            ).strip()

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

Context from documents:
{context}

Request: {description}

Draft:"""
        else:
            prompt = f"""Draft the following content.
{style_inst}
Note: No specific documents are indexed, so using general knowledge.

Request: {description}

Draft:"""

        try:
            result["draft"] = engine.generate(
                prompt,
                max_tokens=max_length // 3,
                temperature=0.7
            ).strip()
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
            "backend": None
        }

        # Check inference engine
        engine = self._get_inference_engine()
        if engine:
            status["backend"] = getattr(engine, 'backend', 'unknown')
            if engine.model is not None:
                status["model_loaded"] = True
                status["model_name"] = getattr(engine, 'MLX_MODEL_NAME', 'unknown')

        # Check RAG index
        rag_index = self._get_rag_index()
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
            except (ValueError, RuntimeError, OSError) as e:
                logger.warning(f"Failed to get RAG stats: {e}")

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
        rag_index = self._get_rag_index()
        if rag_index is None:
            return {"error": "RAG index not available"}

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
            return {"error": "RAG index not available"}

        success = rag_index.delete_document(document_id)
        return {"success": success}


# Singleton instance with thread-safe initialization
import threading
_agent: Optional[LocalAgent] = None
_agent_lock = threading.Lock()


def get_agent(
    vault_path: str = "~/.enclave",
    master_key: Optional[bytes] = None
) -> LocalAgent:
    """
    Get or create the local agent singleton (thread-safe).

    Args:
        vault_path: Base path for agent data
        master_key: Optional 32-byte encryption key (loaded from vault if not provided)

    Returns:
        LocalAgent singleton instance
    """
    global _agent
    # Double-checked locking pattern for thread safety
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = LocalAgent(vault_path=vault_path, master_key=master_key)
    return _agent
