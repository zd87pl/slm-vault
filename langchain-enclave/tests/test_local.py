"""Tests for local-first Enclave LangChain integrations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from langchain_enclave.local import (
    LocalEnclaveClient,
    LocalEnclaveKnowledgeRetriever,
    LocalEnclaveSecretProvider,
)
from langchain_enclave.exceptions import SecretNotFoundError


class FakeKVStore:
    def __init__(self):
        self.entries = {}

    def put(self, service, secret_value, entry_type=None, tags=None, description=None):
        entry_id = f"{service}-entry"
        self.entries[service] = SimpleNamespace(
            id=entry_id,
            service=service,
            value=secret_value,
            tags=tags or [],
            description=description,
            entry_type=SimpleNamespace(value="secret"),
            created_at=datetime.now(timezone.utc),
        )
        return entry_id

    def get(self, service):
        entry = self.entries.get(service)
        return entry.value if entry else None

    def search(self, _query_filter):
        return list(self.entries.values())


class FakeVault:
    def __init__(self):
        self.kv_store = FakeKVStore()
        self.closed = False

    def store(self, content, data_type, service, tags=None, description=None):
        if data_type != "secret":
            raise ValueError("FakeVault only supports secrets")
        return self.kv_store.put(
            service=service,
            secret_value=content,
            tags=tags or [],
            description=description,
        )

    def close(self):
        self.closed = True


class FakeRAGIndex:
    def __init__(self):
        self.documents = []

    def add_document(self, name, content, source_path=None, metadata=None, update_if_exists=True):
        document = SimpleNamespace(
            id=f"{name}-id",
            name=name,
            content=content,
            source_path=source_path,
            metadata=metadata or {},
            chunks=[
                SimpleNamespace(
                    id=f"{name}-chunk",
                    document_id=f"{name}-id",
                    content=content,
                    index=0,
                )
            ],
        )
        self.documents.append(document)
        return document

    def search(self, query, top_k=5, threshold=0.3, document_ids=None, metadata_filter=None):
        if not self.documents:
            return []
        doc = self.documents[0]
        return [
            SimpleNamespace(
                document_name=doc.name,
                score=0.99,
                chunk=SimpleNamespace(content=doc.content, index=0),
            )
        ]

    def list_documents(self):
        return [{"id": doc.id, "name": doc.name, "chunk_count": len(doc.chunks)} for doc in self.documents]


class FakeEngine:
    backend = "mlx"
    MLX_MODEL_NAME = "fake-local-model"

    def __init__(self):
        self.model = object()
        self.loaded = False
        self.prompts = []

    def load_model(self):
        self.loaded = True
        return True

    def generate(self, prompt, max_tokens=512, temperature=0.2):
        self.prompts.append(prompt)
        return "Synthesized local answer"


class FakePrivateProfileManager:
    def __init__(self):
        self.profiles = {}
        self.documents = []

    def get_profile(self, name):
        if name not in self.profiles:
            raise FileNotFoundError(name)
        return self.profiles[name]

    def create_profile(self, name, description="", model_name=None):
        self.profiles[name] = {
            "name": name,
            "description": description,
            "model_name": model_name,
        }
        return self.profiles[name]

    def open_session(self, name):
        if name not in self.profiles:
            self.create_profile(name)
        return FakePrivateSession(self, name)


class FakePrivateSession:
    def __init__(self, manager, profile_name):
        self.manager = manager
        self.profile_name = profile_name

    def add_document(self, name, content, source_path=None, metadata=None):
        document = SimpleNamespace(
            id=f"{name}-profile-id",
            name=name,
            source_path=source_path,
            metadata=metadata or {},
            chunks=[SimpleNamespace(content=content)],
        )
        self.manager.documents.append(document)
        return document

    def list_documents(self):
        return [
            {"id": doc.id, "name": doc.name, "chunk_count": len(doc.chunks)}
            for doc in self.manager.documents
        ]

    def search(self, query, top_k=5, threshold=0.3):
        if not self.manager.documents:
            return []
        doc = self.manager.documents[0]
        return [
            SimpleNamespace(
                document_name=doc.name,
                document_id=doc.id,
                score=0.91,
                chunk=SimpleNamespace(content=doc.chunks[0].content, index=0),
            )
        ]

    def ask(self, question, top_k=5, threshold=0.3, temperature=0.2, max_tokens=512):
        return {
            "answer": "Profile-backed answer",
            "sources": [
                {
                    "document_name": self.manager.documents[0].name,
                    "score": 0.91,
                    "excerpt": self.manager.documents[0].chunks[0].content,
                }
            ]
            if self.manager.documents
            else [],
            "adapters": ["wdva-style"],
        }

    def get_status(self):
        return {
            "document_count": len(self.manager.documents),
            "chunk_count": len(self.manager.documents),
            "active_adapters": ["wdva-style"] if self.manager.documents else [],
            "profile": self.manager.profiles[self.profile_name],
        }

    def close(self):
        return None


@pytest.fixture
def local_client(tmp_path):
    return LocalEnclaveClient(
        vault_path=str(tmp_path),
        vault=FakeVault(),
        rag_index=FakeRAGIndex(),
        inference_engine=FakeEngine(),
    )


def test_local_client_secret_round_trip(local_client):
    local_client.store_secret(
        service="openai",
        content="sk-local-secret",
        tags=["api"],
        description="Local secret",
    )

    result = local_client.retrieve_secret(service="openai")
    assert result["success"] is True
    assert result["secret"] == "sk-local-secret"
    assert result["service"] == "openai"


def test_local_client_ingest_and_chat(local_client, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "notes.md").write_text("We chose Stripe because of webhooks.", encoding="utf-8")
    (docs_dir / "roadmap.txt").write_text("Local chat and adapter tuning are next.", encoding="utf-8")

    ingest = local_client.ingest_directory(str(docs_dir))
    assert ingest["success"] is True
    assert ingest["ingested_count"] == 2

    answer = local_client.chat("Why did we choose Stripe?")
    assert answer["success"] is True
    assert answer["answer"] == "Synthesized local answer"
    assert "Context:" in local_client._inference_engine.prompts[0]


def test_local_retriever_wraps_local_answer(local_client):
    local_client.add_document(
        name="notes.md",
        content="We chose Stripe because of webhook reliability.",
    )
    retriever = LocalEnclaveKnowledgeRetriever(client=local_client)
    docs = retriever.get_relevant_documents("Summarize the docs")

    assert len(docs) == 1
    assert docs[0].page_content == "Synthesized local answer"
    assert docs[0].metadata["mode"] == "local"


def test_local_client_strips_reasoning_tags(tmp_path):
    thinking_engine = FakeEngine()
    thinking_engine.generate = lambda prompt, max_tokens=512, temperature=0.2: (
        "<think>hidden</think>Visible local answer"
    )

    client = LocalEnclaveClient(
        vault_path=str(tmp_path),
        vault=FakeVault(),
        rag_index=FakeRAGIndex(),
        inference_engine=thinking_engine,
    )
    client.add_document(name="notes.md", content="Private note")

    answer = client.chat("Summarize the note")
    assert answer["answer"] == "Visible local answer"


def test_local_secret_tool_wraps_local_secret(local_client):
    local_client.store_secret(service="github", content="ghp_local_secret")
    tool = LocalEnclaveSecretProvider(client=local_client)
    assert tool._run(service="github") == "ghp_local_secret"


def test_local_secret_tool_raises_for_missing_secret(local_client):
    tool = LocalEnclaveSecretProvider(client=local_client)
    with pytest.raises(SecretNotFoundError):
        tool._run(service="missing")


def test_local_client_can_use_private_model_profiles(tmp_path):
    client = LocalEnclaveClient(
        vault_path=str(tmp_path),
        vault=FakeVault(),
        private_model_manager=FakePrivateProfileManager(),
        profile_name="team-notes",
    )

    client.add_document(name="notes.md", content="WDVA adapters personalize local behavior.")
    answer = client.chat("How do adapters help?")
    status = client.get_status()

    assert answer["success"] is True
    assert answer["answer"] == "Profile-backed answer"
    assert answer["profile_name"] == "team-notes"
    assert status["documents_count"] == 1
    assert status["profile_name"] == "team-notes"
