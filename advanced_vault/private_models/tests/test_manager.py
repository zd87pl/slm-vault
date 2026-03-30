"""Tests for the Private Language Model manager."""

from __future__ import annotations

from dataclasses import dataclass

from advanced_vault.private_models.manager import PrivateModelManager


@dataclass
class _FakeChunk:
    content: str


@dataclass
class _FakeResult:
    chunk: _FakeChunk
    document_name: str
    document_id: str
    score: float


@dataclass
class _FakeDocument:
    id: str
    name: str
    source_path: str
    chunks: list


class _FakeRAGIndex:
    def __init__(self, *args, **kwargs):
        self.documents = []

    def add_document(self, name, content, source_path=None, metadata=None):
        doc = _FakeDocument(
            id=f"doc-{len(self.documents) + 1}",
            name=name,
            source_path=source_path or "",
            chunks=[content],
        )
        self.documents.append((doc, content))
        return doc

    def search(self, query, top_k=5, threshold=0.25):
        matches = []
        for index, (doc, content) in enumerate(self.documents[:top_k], start=1):
            matches.append(
                _FakeResult(
                    chunk=_FakeChunk(content=content),
                    document_name=doc.name,
                    document_id=doc.id,
                    score=0.9 - (index * 0.05),
                )
            )
        return matches

    def stats(self):
        return {
            "document_count": len(self.documents),
            "chunk_count": len(self.documents),
        }

    def close(self):
        return None


class _FakeLocalInferenceEngine:
    def __init__(self, *args, **kwargs):
        self.prompts = []

    def load_model(self):
        return True

    def generate(self, prompt, max_tokens=512, temperature=0.2):
        self.prompts.append(prompt)
        return "Local private answer"


def test_profile_create_and_attach_adapter(tmp_path):
    manager = PrivateModelManager(root_path=str(tmp_path / "models"))
    profile = manager.create_profile("work", description="Work PLM")

    adapter_a = tmp_path / "adapter-a.enc.json"
    adapter_b = tmp_path / "adapter-b.enc.json"
    key_a = tmp_path / "adapter-a.key"
    key_b = tmp_path / "adapter-b.key"
    adapter_a.write_text("{}")
    adapter_b.write_text("{}")
    key_a.write_bytes(b"a" * 32)
    key_b.write_bytes(b"b" * 32)

    manager.attach_wdva_adapter(profile.name, "style", str(adapter_a), str(key_a), weight=2.0)
    profile = manager.attach_wdva_adapter(
        profile.name,
        "domain",
        str(adapter_b),
        str(key_b),
        weight=1.0,
    )

    assert len(profile.wdva_adapters) == 2
    weights = {item.name: item.weight for item in profile.wdva_adapters}
    assert weights["style"] == 2.0
    assert weights["domain"] == 1.0


def test_session_ingest_and_ask(monkeypatch, tmp_path):
    monkeypatch.setattr("advanced_vault.private_models.manager.RAGIndex", _FakeRAGIndex)
    monkeypatch.setattr(
        "advanced_vault.private_models.manager.LocalInferenceEngine",
        _FakeLocalInferenceEngine,
    )

    source_file = tmp_path / "notes.txt"
    source_file.write_text("Alpha private memo\nBeta project detail")

    manager = PrivateModelManager(root_path=str(tmp_path / "models"))
    manager.create_profile("research", description="Research profile")
    session = manager.open_session("research")

    try:
        ingest = session.ingest_paths([str(source_file)])
        result = session.ask("What is in my notes?")
    finally:
        session.close()

    assert ingest.added == 1
    assert result["answer"] == "Local private answer"
    assert result["sources"][0]["document_name"] == "notes.txt"


def test_session_safe_fallback_when_generation_fails(monkeypatch, tmp_path):
    class _BrokenLocalInferenceEngine(_FakeLocalInferenceEngine):
        def generate(self, prompt, max_tokens=512, temperature=0.2):
            raise RuntimeError("boom")

    monkeypatch.setattr("advanced_vault.private_models.manager.RAGIndex", _FakeRAGIndex)
    monkeypatch.setattr(
        "advanced_vault.private_models.manager.LocalInferenceEngine",
        _BrokenLocalInferenceEngine,
    )

    source_file = tmp_path / "design.md"
    source_file.write_text("Top secret design details")

    manager = PrivateModelManager(root_path=str(tmp_path / "models"))
    manager.create_profile("design")
    session = manager.open_session("design")

    try:
        session.ingest_paths([str(source_file)])
        result = session.ask("Summarize the design")
    finally:
        session.close()

    assert result["warning"].startswith("generation_failed")
    assert "No raw document text is exposed" in result["answer"]


def test_status_is_lazy_without_loading_rag(monkeypatch, tmp_path):
    class _RAGShouldNotLoad:
        def __init__(self, *args, **kwargs):
            raise AssertionError("RAGIndex should not be created for status-only checks")

    monkeypatch.setattr("advanced_vault.private_models.manager.RAGIndex", _RAGShouldNotLoad)

    manager = PrivateModelManager(root_path=str(tmp_path / "models"))
    manager.create_profile("ops", description="Operations profile")
    session = manager.open_session("ops")

    try:
        status = session.get_status()
    finally:
        session.close()

    assert status["document_count"] == 0
    assert status["chunk_count"] == 0


def test_session_strips_reasoning_tags(monkeypatch, tmp_path):
    class _ThinkingEngine(_FakeLocalInferenceEngine):
        def generate(self, prompt, max_tokens=512, temperature=0.2):
            return "<think>private chain of thought</think>Final user answer"

    monkeypatch.setattr("advanced_vault.private_models.manager.RAGIndex", _FakeRAGIndex)
    monkeypatch.setattr(
        "advanced_vault.private_models.manager.LocalInferenceEngine",
        _ThinkingEngine,
    )

    source_file = tmp_path / "notes.txt"
    source_file.write_text("WDVA adapters help personalize behavior.")

    manager = PrivateModelManager(root_path=str(tmp_path / "models"))
    manager.create_profile("thinking")
    session = manager.open_session("thinking")

    try:
        session.ingest_paths([str(source_file)])
        result = session.ask("What do the notes say?")
    finally:
        session.close()

    assert result["answer"] == "Final user answer"
