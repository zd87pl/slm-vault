"""Local-first LangChain integration for Enclave.

This module provides a local runtime that works with the monorepo's
private-file workflow:

* encrypted secrets stored in the local vault
* local document ingest into the encrypted RAG index
* local-model chat over private files
* LangChain tool/retriever wrappers for local use

The remote API classes remain available in ``client.py``, ``secrets.py``,
and ``knowledge.py`` for backward compatibility.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from langchain.schema import BaseRetriever, Document
from langchain.tools import BaseTool

from langchain_enclave.exceptions import (
    AdapterNotFoundError,
    EnclaveError,
    SecretNotFoundError,
)

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_VAULT_PATH = "~/.vault"
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.3
DEFAULT_MAX_CONTEXT_CHARS = 8000
DEFAULT_MODEL_CANDIDATES = (
    "mlx-community/Qwen3-0.6B-4bit",
    "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "mlx-community/Llama-3.2-1B-Instruct-4bit",
)

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".rst",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".ini",
    ".log",
}
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _load_or_create_master_key(vault_path: Path) -> bytes:
    """Load the local master key, creating it if needed."""
    vault_path.mkdir(parents=True, exist_ok=True)
    key_path = vault_path / "master.key"

    if key_path.exists():
        return key_path.read_bytes()

    master_key = os.urandom(32)
    key_path.write_bytes(master_key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        logger.debug("Could not set secure permissions on %s", key_path)
    return master_key


def _make_excerpt(text: str, limit: int = 240) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _sanitize_model_output(text: str) -> str:
    cleaned = THINK_BLOCK_RE.sub("", text or "")
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def _should_ingest(path: Path, patterns: Optional[Sequence[str]]) -> bool:
    if patterns:
        return any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns)
    return path.suffix.lower() in TEXT_SUFFIXES or path.suffix.lower() == ".pdf"


def _read_local_text(path: Path) -> str:
    """Read a local file, with optional PDF support when pypdf is installed."""
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise EnclaveError(
                "PDF support requires pypdf. Install it or ingest .txt/.md files."
            ) from exc

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    return path.read_text(encoding="utf-8", errors="ignore")


@dataclass
class LocalSearchHit:
    """Lightweight result record for local knowledge queries."""

    document_name: str
    excerpt: str
    score: float
    chunk_index: int


class LocalEnclaveClient:
    """Local-first runtime for private secrets and files."""

    def __init__(
        self,
        vault_path: str = DEFAULT_LOCAL_VAULT_PATH,
        *,
        master_key: Optional[bytes] = None,
        vault: Any = None,
        rag_index: Any = None,
        inference_engine: Any = None,
        model_name: Optional[str] = None,
        private_model_manager: Any = None,
        profile_name: str = "default",
        use_private_profiles: Optional[bool] = None,
        top_k: int = DEFAULT_TOP_K,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ):
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self._master_key = master_key or _load_or_create_master_key(self.vault_path)
        self._vault = vault
        self._rag_index = rag_index
        self._inference_engine = inference_engine
        self._private_model_manager = private_model_manager
        self.model_name = model_name
        self.profile_name = profile_name
        self.use_private_profiles = use_private_profiles
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.max_context_chars = max_context_chars

    def _build_vault(self) -> Any:
        if self._vault is not None:
            return self._vault

        try:
            from advanced_vault.core import HybridVault
        except ImportError as exc:
            raise EnclaveError(
                "Local Enclave runtime requires the advanced_vault package to be installed."
            ) from exc

        self._vault = HybridVault(
            master_key=self._master_key,
            kv_db_path=str(self.vault_path / "vault.db"),
            enable_router_logging=False,
        )
        return self._vault

    def _build_rag_index(self) -> Any:
        if self._rag_index is not None:
            return self._rag_index

        try:
            from advanced_vault.training import RAGIndex
        except ImportError as exc:
            raise EnclaveError(
                "Local knowledge queries require the advanced_vault training package."
            ) from exc

        self._rag_index = RAGIndex(
            master_key=self._master_key,
            db_path=str(self.vault_path / "rag.db"),
        )
        return self._rag_index

    def _build_private_model_manager(self) -> Any:
        if self._private_model_manager is not None:
            return self._private_model_manager

        try:
            from advanced_vault.private_models import PrivateModelManager
        except ImportError:
            return None

        self._private_model_manager = PrivateModelManager(
            root_path=str(self.vault_path / "private_models")
        )
        return self._private_model_manager

    def _should_use_private_profiles(self) -> bool:
        if self.use_private_profiles is not None:
            return bool(self.use_private_profiles)
        if self._rag_index is not None or self._inference_engine is not None:
            return False
        return self._build_private_model_manager() is not None

    def _ensure_private_profile(self) -> Any:
        manager = self._build_private_model_manager()
        if manager is None:
            return None
        try:
            manager.get_profile(self.profile_name)
        except FileNotFoundError:
            manager.create_profile(
                name=self.profile_name,
                description="Local LangChain private profile",
                model_name=self.model_name,
            )
        return manager

    def _build_inference_engine(self) -> Any:
        if self._inference_engine is not None:
            return self._inference_engine

        try:
            from advanced_vault.gui.local_inference import LocalInferenceEngine
        except ImportError as exc:
            raise EnclaveError(
                "Local model chat requires advanced_vault.gui.local_inference and MLX/PyTorch."
            ) from exc

        engine = LocalInferenceEngine(cache_dir=str(self.vault_path / "models"))
        if self.model_name:
            if hasattr(engine, "MODEL_NAME"):
                engine.MODEL_NAME = self.model_name
            if hasattr(engine, "MLX_MODEL_CANDIDATES"):
                engine.MLX_MODEL_CANDIDATES = [self.model_name]
            if hasattr(engine, "MLX_MODEL_NAME"):
                engine.MLX_MODEL_NAME = self.model_name

        self._inference_engine = engine
        return self._inference_engine

    def load_model(self) -> Dict[str, Any]:
        """Load the local model if the runtime is available."""
        if self._should_use_private_profiles():
            manager = self._ensure_private_profile()
            session = manager.open_session(self.profile_name)
            try:
                engine = session._ensure_engine()
            finally:
                session.close()
            loaded = engine is not None
            return {
                "success": loaded,
                "model_loaded": loaded,
                "model_name": self.model_name,
                "backend": getattr(engine, "backend", "unknown") if engine else None,
                "profile_name": self.profile_name,
            }

        engine = self._build_inference_engine()
        loaded = bool(engine.load_model())
        return {
            "success": loaded,
            "model_loaded": loaded,
            "model_name": getattr(engine, "MLX_MODEL_NAME", getattr(engine, "MODEL_NAME", None)),
            "backend": getattr(engine, "backend", "unknown"),
        }

    def store_secret(
        self,
        service: str,
        content: str,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Store a plaintext secret in the local encrypted vault."""
        vault = self._build_vault()
        entry_id = vault.store(
            content=content,
            data_type="secret",
            service=service,
            tags=tags or [],
            description=description,
        )
        return {
            "success": True,
            "entry_id": entry_id,
            "service": service,
            "tags": tags or [],
            "description": description,
        }

    def retrieve_secret(
        self,
        service: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Retrieve a plaintext secret from the local vault."""
        vault = self._build_vault()
        kv_store = getattr(vault, "kv_store", vault)

        if service:
            secret = kv_store.get(service)
            if secret is not None:
                return {
                    "success": True,
                    "secret": secret,
                    "service": service,
                    "entry_id": service,
                }

        try:
            from advanced_vault.encrypted_kv import QueryFilter
        except ImportError:
            QueryFilter = None

        if QueryFilter is not None:
            filter_obj = QueryFilter()
            if service:
                filter_obj.service = service
            if tag:
                filter_obj.tags = [tag]
            elif tags:
                filter_obj.tags = list(tags)

            entries = kv_store.search(filter_obj)
            if entries:
                entry = entries[0]
                secret = kv_store.get(entry.service)
                if secret is not None:
                    return {
                        "success": True,
                        "secret": secret,
                        "service": entry.service,
                        "entry_id": getattr(entry, "id", entry.service),
                        "tags": getattr(entry, "tags", []) or [],
                    }

        raise SecretNotFoundError(
            f"No local secret found for service={service!r}, tag={tag!r}, tags={tags!r}"
        )

    def list_secrets(self) -> Dict[str, Any]:
        """List local secret metadata only."""
        vault = self._build_vault()
        kv_store = getattr(vault, "kv_store", vault)

        try:
            from advanced_vault.encrypted_kv import QueryFilter
        except ImportError as exc:
            raise EnclaveError("Local secret listing requires advanced_vault.encrypted_kv.") from exc

        entries = kv_store.search(QueryFilter())
        secrets = []
        for entry in entries:
            secrets.append(
                {
                    "id": getattr(entry, "id", None),
                    "service": getattr(entry, "service", None),
                    "type": getattr(getattr(entry, "entry_type", None), "value", "secret"),
                    "tags": getattr(entry, "tags", []) or [],
                    "description": getattr(entry, "description", None),
                    "created_at": getattr(entry, "created_at", None),
                }
            )

        return {"success": True, "secrets": secrets, "count": len(secrets)}

    def add_document(
        self,
        name: str,
        content: str,
        source_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a private document to the local encrypted RAG index."""
        if self._should_use_private_profiles():
            manager = self._ensure_private_profile()
            session = manager.open_session(self.profile_name)
            try:
                doc = session.add_document(
                    name=name,
                    content=content,
                    source_path=source_path,
                    metadata=metadata or {},
                )
            finally:
                session.close()
            return {
                "success": True,
                "id": doc.id,
                "name": doc.name,
                "chunks": len(doc.chunks),
                "source_path": source_path,
                "profile_name": self.profile_name,
            }

        rag_index = self._build_rag_index()
        doc = rag_index.add_document(
            name=name,
            content=content,
            source_path=source_path,
            metadata=metadata or {},
        )
        return {
            "success": True,
            "id": doc.id,
            "name": doc.name,
            "chunks": len(doc.chunks),
            "source_path": source_path,
        }

    def ingest_file(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Read and ingest a single local file."""
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))

        text = _read_local_text(path)
        if not text.strip():
            return {"success": False, "file": str(path), "reason": "empty_file"}

        return self.add_document(
            name=path.name,
            content=text,
            source_path=str(path),
            metadata=metadata or {"file_path": str(path)},
        )

    def ingest_directory(
        self,
        directory: str,
        *,
        patterns: Optional[Sequence[str]] = None,
        recursive: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ingest multiple local files from a directory."""
        base = Path(directory).expanduser()
        if not base.exists() or not base.is_dir():
            raise FileNotFoundError(str(base))

        iterator: Iterable[Path] = base.rglob("*") if recursive else base.glob("*")
        ingested: List[Dict[str, Any]] = []
        skipped: List[str] = []

        for path in iterator:
            if not path.is_file():
                continue
            if not _should_ingest(path, patterns):
                continue
            try:
                ingested.append(
                    self.ingest_file(
                        str(path),
                        metadata={
                            **(metadata or {}),
                            "directory": str(base),
                        },
                    )
                )
            except Exception as exc:
                logger.warning("Skipping %s: %s", path, exc)
                skipped.append(str(path))

        return {
            "success": True,
            "directory": str(base),
            "ingested_count": len(ingested),
            "skipped_count": len(skipped),
            "ingested": ingested,
            "skipped": skipped,
        }

    def list_documents(self) -> Dict[str, Any]:
        """List private documents stored in the local RAG index."""
        if self._should_use_private_profiles():
            manager = self._ensure_private_profile()
            session = manager.open_session(self.profile_name)
            try:
                documents = session.list_documents()
            finally:
                session.close()
            return {
                "success": True,
                "documents": documents,
                "count": len(documents),
                "profile_name": self.profile_name,
            }

        rag_index = self._build_rag_index()
        documents = rag_index.list_documents()
        return {"success": True, "documents": documents, "count": len(documents)}

    def _extractive_answer(self, hits: List[LocalSearchHit], query: str) -> str:
        if not hits:
            return f"No relevant local context found for: {query}"

        lines = ["Top local matches:"]
        for hit in hits[:3]:
            lines.append(f"- {hit.document_name}: {hit.excerpt}")
        return "\n".join(lines)

    def query_knowledge(
        self,
        query: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        use_model: bool = True,
    ) -> Dict[str, Any]:
        """Query the private local document set."""
        if self._should_use_private_profiles():
            manager = self._ensure_private_profile()
            session = manager.open_session(self.profile_name)
            try:
                effective_top_k = top_k or self.top_k
                effective_threshold = (
                    threshold if threshold is not None else self.similarity_threshold
                )
                if use_model:
                    result = session.ask(
                        question=query,
                        top_k=effective_top_k,
                        threshold=effective_threshold,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    hits = session.search(
                        query=query,
                        top_k=effective_top_k,
                        threshold=effective_threshold,
                    )
                    sources = []
                    local_hits = []
                    for hit in hits:
                        excerpt = _make_excerpt(hit.chunk.content)
                        local_hits.append(
                            LocalSearchHit(
                                document_name=hit.document_name,
                                excerpt=excerpt,
                                score=float(hit.score),
                                chunk_index=hit.chunk.index,
                            )
                        )
                        sources.append(
                            {
                                "document_name": hit.document_name,
                                "score": float(hit.score),
                                "chunk_index": hit.chunk.index,
                                "excerpt": excerpt,
                            }
                        )
                    result = {
                        "answer": self._extractive_answer(local_hits, query),
                        "sources": sources,
                        "warning": None,
                        "adapters": [],
                    }
            finally:
                session.close()

            answer = result.get("answer", "")
            return {
                "success": True,
                "query": query,
                "answer": answer,
                "sources": result.get("sources", []),
                "rag_used": bool(result.get("sources")),
                "model_used": self.model_name,
                "warning": result.get("warning"),
                "profile_name": self.profile_name,
                "adapters": result.get("adapters", []),
            }

        rag_index = self._build_rag_index()
        hits = rag_index.search(
            query=query,
            top_k=top_k or self.top_k,
            threshold=threshold if threshold is not None else self.similarity_threshold,
        )

        sources: List[Dict[str, Any]] = []
        local_hits: List[LocalSearchHit] = []
        context_parts: List[str] = []

        for hit in hits:
            excerpt = _make_excerpt(hit.chunk.content)
            local_hits.append(
                LocalSearchHit(
                    document_name=hit.document_name,
                    excerpt=excerpt,
                    score=float(hit.score),
                    chunk_index=hit.chunk.index,
                )
            )
            sources.append(
                {
                    "document_name": hit.document_name,
                    "score": float(hit.score),
                    "chunk_index": hit.chunk.index,
                    "excerpt": excerpt,
                }
            )
            context_parts.append(f"[{hit.document_name}] {hit.chunk.content}")

        if not hits:
            return {
                "success": True,
                "query": query,
                "answer": self._extractive_answer([], query),
                "sources": [],
                "rag_used": False,
                "model_used": None,
            }

        context = "\n\n".join(context_parts)[: self.max_context_chars]
        model_used = None

        if use_model:
            try:
                engine = self._build_inference_engine()
                if getattr(engine, "model", None) is None:
                    engine.load_model()
                if getattr(engine, "model", None) is not None:
                    model_used = getattr(engine, "MLX_MODEL_NAME", getattr(engine, "MODEL_NAME", None))
                    prompt = (
                        "You are a local private assistant. Use only the provided context. "
                        "Return only the final answer and do not narrate your reasoning.\n\n"
                        f"Context:\n{context}\n\n"
                        f"Question: {query}\n\n"
                        "Answer concisely and cite the relevant documents when useful."
                    )
                    answer = engine.generate(
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    answer = _sanitize_model_output(answer)
                else:
                    answer = self._extractive_answer(local_hits, query)
            except Exception as exc:
                logger.warning("Falling back to extractive local answer: %s", exc)
                answer = self._extractive_answer(local_hits, query)
        else:
            answer = self._extractive_answer(local_hits, query)

        return {
            "success": True,
            "query": query,
            "answer": answer,
            "sources": sources,
            "rag_used": True,
            "model_used": model_used,
        }

    def chat(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """Convenience alias for local knowledge queries."""
        return self.query_knowledge(query, **kwargs)

    def get_status(self) -> Dict[str, Any]:
        """Return local runtime status for tools and UI."""
        vault = self._build_vault()
        try:
            secret_count = self.list_secrets()["count"]
        except Exception:
            secret_count = 0

        if self._should_use_private_profiles():
            manager = self._ensure_private_profile()
            session = manager.open_session(self.profile_name)
            try:
                profile_status = session.get_status()
            finally:
                session.close()
            document_count = profile_status.get("document_count", 0)
            model_loaded = False
            backend = None
            model_name = profile_status.get("profile", {}).get("model_name")
            return {
                "success": True,
                "mode": "local",
                "vault_path": str(self.vault_path),
                "secrets_count": secret_count,
                "documents_count": document_count,
                "model_loaded": model_loaded,
                "backend": backend,
                "model_name": model_name,
                "vault_type": type(vault).__name__,
                "profile_name": self.profile_name,
                "active_adapters": profile_status.get("active_adapters", []),
            }

        rag_index = self._build_rag_index()
        try:
            document_count = len(rag_index.list_documents())
        except Exception:
            document_count = 0

        engine = None
        model_loaded = False
        try:
            engine = self._build_inference_engine()
            model_loaded = getattr(engine, "model", None) is not None
        except Exception:
            engine = None

        return {
            "success": True,
            "mode": "local",
            "vault_path": str(self.vault_path),
            "secrets_count": secret_count,
            "documents_count": document_count,
            "model_loaded": model_loaded,
            "backend": getattr(engine, "backend", None) if engine else None,
            "model_name": (
                getattr(engine, "MLX_MODEL_NAME", None)
                if engine is not None
                else None
            ),
            "vault_type": type(vault).__name__,
        }

    def close(self) -> None:
        """Close any open runtime resources."""
        if self._vault is not None and hasattr(self._vault, "close"):
            self._vault.close()


class LocalEnclaveKnowledgeRetriever(BaseRetriever):
    """LangChain retriever backed by the local private-model runtime."""

    client: Optional[LocalEnclaveClient] = None
    top_k: int = DEFAULT_TOP_K
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    temperature: float = 0.2
    max_tokens: int = 512
    use_model: bool = True

    def __init__(
        self,
        vault_path: str = DEFAULT_LOCAL_VAULT_PATH,
        *,
        client: Optional[LocalEnclaveClient] = None,
        top_k: int = DEFAULT_TOP_K,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        temperature: float = 0.2,
        max_tokens: int = 512,
        use_model: bool = True,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        object.__setattr__(
            self,
            "client",
            client or LocalEnclaveClient(vault_path=vault_path),
        )
        object.__setattr__(self, "top_k", top_k)
        object.__setattr__(self, "similarity_threshold", similarity_threshold)
        object.__setattr__(self, "temperature", temperature)
        object.__setattr__(self, "max_tokens", max_tokens)
        object.__setattr__(self, "use_model", use_model)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        result = self.client.query_knowledge(
            query=query,
            top_k=self.top_k,
            threshold=self.similarity_threshold,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            use_model=self.use_model,
        )

        if not result.get("success", False):
            raise AdapterNotFoundError(result.get("answer", "Local query failed"))

        return [
            Document(
                page_content=result["answer"],
                metadata={
                    "source": "local_enclave",
                    "mode": "local",
                    "top_k": self.top_k,
                    "similarity_threshold": self.similarity_threshold,
                    "sources": result.get("sources", []),
                },
            )
        ]

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return self._get_relevant_documents(query)


class LocalEnclaveSecretProvider(BaseTool):
    """LangChain tool for retrieving plaintext secrets from a local vault."""

    name: str = "local_enclave_secret_provider"
    description: str = (
        "Retrieve a secret from the local Enclave vault. "
        "Input should be a service name, optionally with tag filters."
    )
    client: Optional[LocalEnclaveClient] = None

    def __init__(
        self,
        vault_path: str = DEFAULT_LOCAL_VAULT_PATH,
        *,
        client: Optional[LocalEnclaveClient] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        object.__setattr__(
            self,
            "client",
            client or LocalEnclaveClient(vault_path=vault_path),
        )

    def _run(
        self,
        service: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> str:
        if not service and not tag and not tags:
            raise SecretNotFoundError("Provide a service name or tag filter.")

        result = self.client.retrieve_secret(service=service, tag=tag, tags=tags)
        secret = result.get("secret")
        if secret is None:
            raise SecretNotFoundError(
                f"No local secret found for service={service!r}, tag={tag!r}, tags={tags!r}"
            )
        return secret

    async def _arun(
        self,
        service: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> str:
        return self._run(service=service, tag=tag, tags=tags)
