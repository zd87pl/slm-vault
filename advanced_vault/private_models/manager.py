"""Local-first Private Language Model manager built on Enclave primitives."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from advanced_vault.parsing import extract_pdf_text
from advanced_vault.training import MLXTrainer, RAGIndex, TrainingExample

from .adapter_packaging import package_adapter_file, write_adapter_key
from .models import DEFAULT_SYSTEM_PROMPT, PrivateModelProfile, WDVAAdapterReference


LocalInferenceEngine = None
MultiAdapterEngine = None


def _get_local_inference_engine_class():
    """Import the local inference stack only when generation is requested."""
    global LocalInferenceEngine
    if LocalInferenceEngine is None:
        from advanced_vault.gui.local_inference import LocalInferenceEngine as _LocalInferenceEngine

        LocalInferenceEngine = _LocalInferenceEngine
    return LocalInferenceEngine


def _get_multi_adapter_engine_class():
    """Import the multi-adapter runtime only when WDVA adapters are active."""
    global MultiAdapterEngine
    if MultiAdapterEngine is None:
        from advanced_vault.gui.multi_adapter_engine import MultiAdapterEngine as _MultiAdapterEngine

        MultiAdapterEngine = _MultiAdapterEngine
    return MultiAdapterEngine


SUPPORTED_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".csv",
    ".go",
    ".html",
    ".java",
    ".js",
    ".json",
    ".md",
    ".pdf",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

DEFAULT_CONTEXT_RESULTS = 5
DEFAULT_CONTEXT_CHARS = 12000
DEFAULT_HISTORY_TURNS = 6
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _sanitize_model_output(text: str) -> str:
    """Strip hidden reasoning tags from model responses before showing users."""
    cleaned = THINK_BLOCK_RE.sub("", text or "")
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


@dataclass
class IngestResult:
    """Summary of a file ingest operation."""

    added: int
    skipped: int
    documents: List[Dict[str, Any]]


class PrivateModelManager:
    """Manage local profiles that combine RAG context and WDVA adapters."""

    def __init__(self, root_path: str = "~/.vault/private_models"):
        self.root_path = Path(root_path).expanduser()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def create_profile(
        self,
        name: str,
        description: str = "",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        keywords: Optional[Sequence[str]] = None,
        model_name: Optional[str] = None,
    ) -> PrivateModelProfile:
        """Create or overwrite a profile manifest."""
        profile = PrivateModelProfile(
            name=name,
            description=description,
            system_prompt=system_prompt,
            keywords=list(keywords or []),
            model_name=model_name,
        )
        profile_dir = self._profile_dir(name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._save_profile(profile)
        return profile

    def list_profiles(self) -> List[PrivateModelProfile]:
        """List all profiles under the manager root."""
        profiles: List[PrivateModelProfile] = []
        for path in sorted(self.root_path.iterdir()):
            if not path.is_dir():
                continue
            manifest = path / "profile.json"
            if manifest.exists():
                profiles.append(self._load_profile(path.name))
        return profiles

    def get_profile(self, name: str) -> PrivateModelProfile:
        """Load a profile by name."""
        return self._load_profile(name)

    def delete_profile(self, name: str) -> bool:
        """Delete a profile and all local data."""
        profile_dir = self._profile_dir(name)
        if not profile_dir.exists():
            return False
        shutil.rmtree(profile_dir)
        return True

    def open_session(self, name: str) -> "PrivateModelSession":
        """Open a reusable session for chat and ingest."""
        profile = self._load_profile(name)
        return PrivateModelSession(self, profile)

    def attach_wdva_adapter(
        self,
        profile_name: str,
        adapter_name: str,
        encrypted_path: str,
        key_path: str,
        weight: float = 1.0,
        description: str = "",
        keywords: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PrivateModelProfile:
        """Attach or update an encrypted WDVA adapter on a profile."""
        profile = self._load_profile(profile_name)

        updated = False
        for adapter in profile.wdva_adapters:
            if adapter.name == adapter_name:
                adapter.encrypted_path = str(Path(encrypted_path).expanduser())
                adapter.key_path = str(Path(key_path).expanduser())
                adapter.weight = float(weight)
                adapter.description = description
                adapter.keywords = list(keywords or [])
                adapter.metadata = dict(metadata or {})
                updated = True
                break

        if not updated:
            profile.wdva_adapters.append(
                WDVAAdapterReference(
                    name=adapter_name,
                    encrypted_path=str(Path(encrypted_path).expanduser()),
                    key_path=str(Path(key_path).expanduser()),
                    weight=float(weight),
                    description=description,
                    keywords=list(keywords or []),
                    metadata=dict(metadata or {}),
                )
            )

        profile.touch()
        self._save_profile(profile)
        return profile

    def package_wdva_adapter(
        self,
        adapter_source: str,
        output_path: str,
        key_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Path, Path]:
        """Encrypt a local adapter safetensors file into a reusable WDVA package."""
        source_file = self._resolve_adapter_file(Path(adapter_source).expanduser())
        master_key = os.urandom(32)
        packaged_path = package_adapter_file(source_file, output_path, master_key, metadata=metadata)
        key_file = write_adapter_key(key_path, master_key)
        return packaged_path, key_file

    def train_wdva_adapter(
        self,
        profile_name: str,
        adapter_name: str,
        dataset_path: str,
        output_dir: Optional[str] = None,
        model_name: Optional[str] = None,
        epochs: int = 3,
        learning_rate: float = 1e-4,
        batch_size: int = 2,
        max_seq_length: int = 512,
        auto_attach: bool = True,
    ) -> Dict[str, Any]:
        """Train a local MLX WDVA adapter from JSONL chat/qa data."""
        profile = self._load_profile(profile_name)
        examples = self._load_training_examples(dataset_path)

        trainer = MLXTrainer(
            model_name=model_name or profile.model_name,
            output_dir=output_dir or str(self._profile_dir(profile_name) / "trained_adapters"),
            config={
                "epochs": epochs,
                "learning_rate": learning_rate,
                "batch_size": batch_size,
                "max_seq_length": max_seq_length,
                "use_dora": True,
            },
        )
        result = trainer.train(examples, adapter_name)

        adapter_file = self._resolve_adapter_file(result.adapter_path)
        packaged_dir = self._profile_dir(profile_name) / "wdva_packages"
        key_dir = self._profile_dir(profile_name) / "keys"
        packaged_path, key_file = self.package_wdva_adapter(
            str(adapter_file),
            str(packaged_dir / f"{adapter_name}.enc.json"),
            str(key_dir / f"{adapter_name}.key"),
            metadata={
                "profile": profile_name,
                "trained_with_model": result.model_name,
                "num_examples": result.num_examples,
                "epochs": result.epochs,
            },
        )

        if auto_attach:
            self.attach_wdva_adapter(
                profile_name=profile_name,
                adapter_name=adapter_name,
                encrypted_path=str(packaged_path),
                key_path=str(key_file),
                weight=1.0,
                description="Locally trained WDVA adapter",
            )

        return {
            "adapter_dir": str(result.adapter_path),
            "encrypted_adapter_path": str(packaged_path),
            "key_path": str(key_file),
            "num_examples": result.num_examples,
            "epochs": result.epochs,
            "model_name": result.model_name,
        }

    def search(
        self,
        profile_name: str,
        query: str,
        top_k: int = DEFAULT_CONTEXT_RESULTS,
        threshold: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """Search encrypted local context for a profile."""
        session = self.open_session(profile_name)
        try:
            results = session.search(query, top_k=top_k, threshold=threshold)
            return [session._result_to_dict(item) for item in results]
        finally:
            session.close()

    def _load_profile(self, name: str) -> PrivateModelProfile:
        manifest_path = self._profile_dir(name) / "profile.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Profile '{name}' does not exist")
        return PrivateModelProfile.from_dict(json.loads(manifest_path.read_text()))

    def _save_profile(self, profile: PrivateModelProfile) -> None:
        profile_path = self._profile_dir(profile.name)
        profile_path.mkdir(parents=True, exist_ok=True)
        (profile_path / "profile.json").write_text(json.dumps(profile.to_dict(), indent=2))

    def _profile_dir(self, name: str) -> Path:
        return self.root_path / name

    def _profile_vault_path(self, name: str) -> Path:
        return self._profile_dir(name) / "vault"

    def _load_or_create_master_key(self, name: str) -> bytes:
        vault_path = self._profile_vault_path(name)
        vault_path.mkdir(parents=True, exist_ok=True)
        key_path = vault_path / "master.key"
        if key_path.exists():
            return key_path.read_bytes()

        key = os.urandom(32)
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
        return key

    def _open_rag_index(self, name: str) -> RAGIndex:
        master_key = self._load_or_create_master_key(name)
        db_path = self._profile_vault_path(name) / "rag.db"
        return RAGIndex(master_key=master_key, db_path=str(db_path))

    def _normalized_adapter_weights(self, profile: PrivateModelProfile) -> Dict[str, float]:
        total = sum(max(adapter.weight, 0.0) for adapter in profile.wdva_adapters)
        if total <= 0:
            return {adapter.name: 0.0 for adapter in profile.wdva_adapters}
        return {
            adapter.name: max(adapter.weight, 0.0) / total
            for adapter in profile.wdva_adapters
        }

    def _resolve_adapter_file(self, adapter_source: Path) -> Path:
        if adapter_source.is_file():
            return adapter_source

        safetensors = sorted(
            adapter_source.rglob("*.safetensors"),
            key=lambda path: path.stat().st_size,
            reverse=True,
        )
        if not safetensors:
            raise FileNotFoundError(f"No .safetensors adapter found under {adapter_source}")
        return safetensors[0]

    def _load_training_examples(self, dataset_path: str) -> List[TrainingExample]:
        examples: List[TrainingExample] = []
        with open(Path(dataset_path).expanduser(), "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if "messages" in payload:
                    examples.append(TrainingExample(messages=payload["messages"]))
                    continue
                if "question" in payload and "answer" in payload:
                    examples.append(
                        TrainingExample(
                            messages=[
                                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                                {"role": "user", "content": payload["question"]},
                                {"role": "assistant", "content": payload["answer"]},
                            ]
                        )
                    )
                    continue
                raise ValueError(
                    "Unsupported training example format. Expected 'messages' or "
                    "'question'/'answer' keys."
                )

        if not examples:
            raise ValueError("Training dataset is empty")
        return examples


class PrivateModelSession:
    """Interactive session for a single local Private Language Model profile."""

    def __init__(self, manager: PrivateModelManager, profile: PrivateModelProfile):
        self.manager = manager
        self.profile = profile
        self._rag_index: Optional[RAGIndex] = None
        self.history: List[Tuple[str, str]] = []
        self._engine: Optional[Any] = None
        self._engine_kind: Optional[str] = None
        self._active_adapters: List[str] = []

    def close(self) -> None:
        """Release local resources."""
        if self._engine_kind == "multi" and self._engine is not None:
            self._engine.deactivate_adapters()
        if self._rag_index is not None:
            self._rag_index.close()
            self._rag_index = None

    def ingest_paths(self, paths: Sequence[str]) -> IngestResult:
        """Add files and folders to the profile's encrypted local index."""
        documents: List[Dict[str, Any]] = []
        skipped = 0
        rag_index = self._get_rag_index()

        for file_path in self._iter_supported_files(paths):
            try:
                content = self._read_file_content(file_path)
            except Exception:
                skipped += 1
                continue

            if not content.strip():
                skipped += 1
                continue

            doc = rag_index.add_document(
                name=file_path.name,
                content=content,
                source_path=str(file_path),
                metadata={"folder": str(file_path.parent)},
            )
            documents.append(
                {
                    "id": doc.id,
                    "name": doc.name,
                    "source_path": doc.source_path,
                    "chunks": len(doc.chunks),
                }
            )

        return IngestResult(added=len(documents), skipped=skipped, documents=documents)

    def add_document(
        self,
        name: str,
        content: str,
        source_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Add an in-memory document to the encrypted local index."""
        return self._get_rag_index().add_document(
            name=name,
            content=content,
            source_path=source_path,
            metadata=metadata or {},
        )

    def list_documents(self) -> List[Dict[str, Any]]:
        """List indexed documents for the current profile."""
        return self._get_rag_index().list_documents()

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_CONTEXT_RESULTS,
        threshold: float = 0.25,
    ) -> List[Any]:
        """Search local profile context."""
        return self._get_rag_index().search(query=query, top_k=top_k, threshold=threshold)

    def ask(
        self,
        question: str,
        top_k: int = DEFAULT_CONTEXT_RESULTS,
        threshold: float = 0.25,
        max_tokens: int = 512,
        temperature: float = 0.2,
        include_history: bool = True,
    ) -> Dict[str, Any]:
        """Query the local profile with retrieved private context."""
        retrieval_results = self.search(question, top_k=top_k, threshold=threshold)
        context = self._compose_context(retrieval_results)
        sources = [self._result_to_dict(item) for item in retrieval_results]

        try:
            engine = self._ensure_engine()
        except Exception as exc:
            return {
                "answer": (
                    "The local Private Language Model could not start. "
                    "Your files remain local and encrypted, but generation is unavailable "
                    f"until the runtime issue is fixed: {exc}"
                ),
                "sources": sources,
                "profile": self.profile.name,
                "adapters": self._active_adapters,
                "warning": "engine_start_failed",
            }

        if engine is None:
            return {
                "answer": (
                    "A local model backend could not be loaded. "
                    "Your private files remain local and encrypted, but no answer can be "
                    "generated until MLX or another local runtime is available."
                ),
                "sources": sources,
                "profile": self.profile.name,
                "adapters": self._active_adapters,
                "warning": "model_unavailable",
            }

        prompt = self._build_prompt(question, context, include_history=include_history)
        try:
            answer = engine.generate(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:
            return {
                "answer": (
                    "Generation failed after retrieving private local context. "
                    "No raw document text is exposed in this error path."
                ),
                "sources": sources,
                "profile": self.profile.name,
                "adapters": self._active_adapters,
                "warning": f"generation_failed: {exc}",
            }
        answer = _sanitize_model_output(answer)
        self._append_history(question, answer)
        return {
            "answer": answer.strip(),
            "sources": sources,
            "profile": self.profile.name,
            "adapters": self._active_adapters,
        }

    def get_status(self) -> Dict[str, Any]:
        """Return profile summary and local document stats."""
        stats = self._load_index_stats()
        return {
            "profile": self.profile.to_dict(),
            "document_count": stats.get("document_count", 0),
            "chunk_count": stats.get("chunk_count", 0),
            "active_adapters": self._active_adapters,
        }

    def _get_rag_index(self) -> RAGIndex:
        """Open the encrypted index lazily so metadata commands stay lightweight."""
        if self._rag_index is None:
            self._rag_index = self.manager._open_rag_index(self.profile.name)
        return self._rag_index

    def _load_index_stats(self) -> Dict[str, int]:
        """Read persisted index counts without booting the embedding stack."""
        if self._rag_index is not None:
            stats = self._rag_index.stats()
            return {
                "document_count": int(stats.get("document_count", 0)),
                "chunk_count": int(stats.get("chunk_count", 0)),
            }

        db_path = self.manager._profile_vault_path(self.profile.name) / "rag.db"
        if not db_path.exists():
            return {"document_count": 0, "chunk_count": 0}

        with sqlite3.connect(db_path) as conn:
            document_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        return {
            "document_count": int(document_count),
            "chunk_count": int(chunk_count),
        }

    def _ensure_engine(self) -> Optional[Any]:
        if self._engine is not None:
            return self._engine

        if self.profile.wdva_adapters:
            multi_adapter_engine_class = _get_multi_adapter_engine_class()
            engine = multi_adapter_engine_class(
                cache_dir=str(self.manager._profile_dir(self.profile.name) / "models")
            )
            if not engine.load_model(model_path=self.profile.model_name):
                return None
            for adapter in self.profile.wdva_adapters:
                encrypted_bytes = Path(adapter.encrypted_path).expanduser().read_bytes()
                key = Path(adapter.key_path).expanduser().read_bytes()
                engine.register_adapter(
                    adapter.name,
                    encrypted_data=encrypted_bytes,
                    encryption_key=key,
                    metadata=adapter.metadata,
                )
            engine.set_adapters(self.manager._normalized_adapter_weights(self.profile))
            self._engine = engine
            self._engine_kind = "multi"
            self._active_adapters = [adapter.name for adapter in self.profile.wdva_adapters]
            return engine

        local_inference_engine_class = _get_local_inference_engine_class()
        engine = local_inference_engine_class(
            cache_dir=str(self.manager._profile_dir(self.profile.name) / "models")
        )
        self._configure_model(engine)
        if not engine.load_model():
            return None
        self._engine = engine
        self._engine_kind = "local"
        self._active_adapters = []
        return engine

    def _configure_model(self, engine: LocalInferenceEngine) -> None:
        model_name = self.profile.model_name
        if not model_name:
            return

        if hasattr(engine, "MLX_MODEL_CANDIDATES"):
            candidates = [model_name]
            candidates.extend(
                item for item in engine.MLX_MODEL_CANDIDATES if item != model_name
            )
            engine.MLX_MODEL_CANDIDATES = candidates
            engine.MLX_MODEL_NAME = model_name

        if hasattr(engine, "MODEL_NAME"):
            engine.MODEL_NAME = model_name

    def _compose_context(self, results: Sequence[Any]) -> str:
        sections: List[str] = []
        remaining = DEFAULT_CONTEXT_CHARS
        for result in results:
            content = result.chunk.content.strip()
            if not content:
                continue
            snippet = content[: min(len(content), remaining)]
            if not snippet:
                break
            sections.append(f"[Document: {result.document_name}]\n{snippet}")
            remaining -= len(snippet)
            if remaining <= 0:
                break
        return "\n\n".join(sections)

    def _build_prompt(self, question: str, context: str, include_history: bool) -> str:
        history_block = ""
        if include_history and self.history:
            recent = self.history[-DEFAULT_HISTORY_TURNS :]
            history_lines = []
            for previous_question, previous_answer in recent:
                history_lines.append(f"User: {previous_question}")
                history_lines.append(f"Assistant: {previous_answer}")
            history_block = "\nConversation history:\n" + "\n".join(history_lines)

        context_block = context or "No indexed local context matched this question."
        return (
            f"{self.profile.system_prompt}\n\n"
            "You are operating entirely on the user's local device. "
            "Use the provided local context when it is relevant. "
            "If the answer is not supported by the context, say so plainly. "
            "Keep citations to document names only. "
            "Return only the final answer. "
            "Do not narrate your reasoning, planning, or analysis.\n"
            f"{history_block}\n\n"
            f"Local context:\n{context_block}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

    def _append_history(self, question: str, answer: str) -> None:
        self.history.append((question, answer.strip()))
        if len(self.history) > DEFAULT_HISTORY_TURNS:
            self.history = self.history[-DEFAULT_HISTORY_TURNS :]

    def _iter_supported_files(self, paths: Sequence[str]) -> Iterable[Path]:
        for raw_path in paths:
            path = Path(raw_path).expanduser()
            if not path.exists():
                continue
            if path.is_dir():
                for file_path in path.rglob("*"):
                    if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                        yield file_path
            elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield path

    def _read_file_content(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return extract_pdf_text(path).text
        if suffix == ".csv":
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                reader = csv.reader(handle)
                return "\n".join(", ".join(row) for row in reader)
        return path.read_text(encoding="utf-8", errors="ignore")

    def _result_to_dict(self, result: Any) -> Dict[str, Any]:
        excerpt = result.chunk.content.replace("\n", " ").strip()
        if len(excerpt) > 180:
            excerpt = excerpt[:177] + "..."
        return {
            "document_name": result.document_name,
            "document_id": result.document_id,
            "score": round(float(result.score), 4),
            "excerpt": excerpt,
        }
