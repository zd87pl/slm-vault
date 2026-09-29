"""
The MCP agent must serve the document index the Enclave app and CLI write to.

These tests ingest real files through the CLI (``enclave model ...``) into a
temporary HOME, then build the MCP server with its default configuration and
check that ``agent_status`` / ``agent_query`` see those documents.  Retrieval
uses the real encrypted index and real e5-small embeddings (one model instance
shared by every index, to keep the module fast); only text generation is
replaced by a fake engine, so no network access or LLM is needed.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import advanced_vault.mcp_server.agent as agent_module
from advanced_vault.cli.main import cli
from advanced_vault.mcp_server.agent import LocalAgent
from advanced_vault.mcp_server.server import create_vault_server
from advanced_vault.private_models.manager import (
    ACTIVE_PROFILE_STATE_FILE,
    PROFILE_OVERRIDE_ENV,
    PrivateModelManager,
    resolve_active_profile,
)

LEASE_TEXT = (
    "Residential lease for 12 Harbour Street.\n\n"
    "The tenant pays a security deposit of 2,400 euros before moving in. "
    "Monthly rent is 1,200 euros, due on the first day of each month."
)
RECIPE_TEXT = (
    "Grandma's lemon cake.\n\n"
    "Beat 200 grams of butter with 180 grams of sugar, add four eggs and the "
    "zest of two lemons, then bake for 45 minutes at 170 degrees."
)


class _FakeTokenizer:
    """Minimal chat-template tokenizer that counts how often it is applied."""

    def __init__(self):
        self.template_calls = 0

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        self.template_calls += 1
        rendered = "".join(
            f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>\n"
            for message in messages
        )
        if add_generation_prompt:
            rendered += "<|im_start|>assistant\n"
        return rendered


class _FakeInferenceEngine:
    """Stands in for LocalInferenceEngine; only text generation is faked."""

    MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    MLX_MODEL_NAME = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

    def __init__(self, backend="torch"):
        self.backend = backend
        self.model = object()
        self.tokenizer = _FakeTokenizer()
        self.rendered_prompts = []

    def load_model(self, progress_callback=None, allow_download=True):
        return True

    def generate(self, prompt, max_tokens=256, temperature=0.7):
        # Mirrors LocalInferenceEngine.generate(): the prompt is wrapped as a
        # single user message and rendered with the model's chat template.
        rendered = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
        )
        self.rendered_prompts.append(rendered)
        return "<think>hidden</think>The security deposit is 2,400 euros."


@pytest.fixture(scope="module", autouse=True)
def shared_embeddings():
    """Load e5-small once; every RAGIndex in this module embeds with it."""
    from advanced_vault.training.embeddings import EmbeddingEngine

    engine = EmbeddingEngine(use_persistent_cache=False)
    engine.embed_query("warm up")
    with patch("advanced_vault.training.rag_index.EmbeddingEngine", return_value=engine):
        yield engine


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point HOME at an empty directory, as on a fresh install."""
    # Keep the Hugging Face cache (e5-small) where it is before HOME moves.
    monkeypatch.setenv(
        "HF_HOME",
        os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")),
    )
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv(PROFILE_OVERRIDE_ENV, raising=False)
    agent_module._agent = None
    yield home_dir
    agent_module._agent = None


@pytest.fixture
def engine():
    fake = _FakeInferenceEngine()
    with patch.object(LocalAgent, "_get_inference_engine", return_value=fake):
        yield fake


def _write(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text)
    return path


def _enclave(*args: str) -> str:
    """Run the real CLI with its default ``--vault-path`` (``~/.vault``)."""
    result = CliRunner().invoke(cli, list(args), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


def _text(contents) -> str:
    return "\n".join(item.text for item in contents)


def test_mcp_serves_documents_ingested_with_the_cli(home, engine):
    lease = _write(home / "docs", "lease.md", LEASE_TEXT)
    _enclave("model", "create", "workspace")
    assert "Added 1 documents" in _enclave("model", "ingest", "workspace", str(lease))

    server = create_vault_server()  # default config: VAULT_PATH unset -> ~/.vault
    agent = server._get_agent()

    status = agent.get_status()
    assert status["document_count"] == 1
    assert [doc["name"] for doc in status["documents"]] == ["lease.md"]
    assert status["profile"] == "workspace"
    expected_db = home / ".vault" / "private_models" / "workspace" / "vault" / "rag.db"
    assert Path(status["index_path"]) == expected_db

    status_text = _text(asyncio.run(server._handle_agent_status({})))
    assert "Documents indexed: 1" in status_text
    assert "lease.md" in status_text
    assert "Profile: workspace" in status_text

    result = agent.query("How much is the security deposit?")
    assert result["error"] is None
    assert result["rag_used"] is True
    assert [source["document"] for source in result["sources"]] == ["lease.md"]
    assert result["answer"] == "The security deposit is 2,400 euros."

    query_text = _text(asyncio.run(
        server._handle_agent_query({"question": "How much is the security deposit?"})
    ))
    assert "lease.md" in query_text

    # The agent read the profile index; it never created a second key or
    # index at the vault root next to the secrets store.
    assert not (home / ".vault" / "rag.db").exists()
    assert not (home / ".vault" / "master.key").exists()


def test_query_templates_prompt_once_and_reports_model_used(home, engine):
    lease = _write(home / "docs", "lease.md", LEASE_TEXT)
    _enclave("model", "create", "workspace")
    _enclave("model", "ingest", "workspace", str(lease))

    agent = create_vault_server()._get_agent()
    result = agent.query("How much is the security deposit?")

    assert result["error"] is None
    assert engine.tokenizer.template_calls == 1
    rendered = engine.rendered_prompts[0]
    assert rendered.count("<|im_start|>") == 2  # one user turn + generation prompt
    assert "How much is the security deposit?" in rendered
    assert "security deposit of 2,400 euros" in rendered  # retrieved context
    # torch backend: TinyLlama ran, not the MLX default candidate.
    assert result["model_used"] == _FakeInferenceEngine.MODEL_NAME

    engine.backend = "mlx"
    assert agent.query("What is the monthly rent?")["model_used"] == _FakeInferenceEngine.MLX_MODEL_NAME
    assert agent.get_status()["model_name"] == _FakeInferenceEngine.MLX_MODEL_NAME


def test_no_index_yet_reports_profile_and_skips_llm(home, engine):
    server = create_vault_server()
    agent = server._get_agent()

    status = agent.get_status()
    assert status["document_count"] == 0
    assert status["rag_available"] is False
    assert status["profile"] == "workspace"
    assert Path(status["index_path"]) == (
        home / ".vault" / "private_models" / "workspace" / "vault" / "rag.db"
    )
    status_text = _text(asyncio.run(server._handle_agent_status({})))
    assert "Profile: workspace" in status_text
    assert "Documents indexed: 0" in status_text

    result = agent.query("How much is the security deposit?")
    assert result["error"] is None
    assert result["sources"] == []
    assert result["rag_used"] is False
    assert result["model_used"] is None
    assert "No indexed documents matched" in result["answer"]
    assert engine.rendered_prompts == []

    # Looking must not create keys or databases anywhere.
    assert list((home / ".vault").rglob("master.key")) == []
    assert list((home / ".vault").rglob("rag.db")) == []


def test_no_matching_documents_returns_explicit_answer_without_llm(home, engine):
    _enclave("model", "create", "workspace")
    manager = PrivateModelManager(root_path=str(home / ".vault" / "private_models"))
    session = manager.open_session("workspace")
    try:
        assert session.list_documents() == []  # creates the (empty) profile index
    finally:
        session.close()

    agent = create_vault_server()._get_agent()
    result = agent.query("How much is the security deposit?")

    assert set(result) == {"answer", "sources", "model_used", "rag_used", "error"}
    assert result["error"] is None
    assert result["sources"] == []
    assert "No indexed documents matched" in result["answer"]
    assert engine.rendered_prompts == []
    assert engine.tokenizer.template_calls == 0


def test_agent_follows_the_profile_the_app_marked_active(home, engine):
    lease = _write(home / "docs", "lease.md", LEASE_TEXT)
    recipe = _write(home / "docs", "cake.md", RECIPE_TEXT)
    _enclave("model", "create", "alpha")
    _enclave("model", "create", "home")
    _enclave("model", "ingest", "alpha", str(recipe))
    _enclave("model", "ingest", "home", str(lease))
    (home / ".vault" / ACTIVE_PROFILE_STATE_FILE).write_text("home\n")

    agent = create_vault_server()._get_agent()
    status = agent.get_status()
    assert status["profile"] == "home"
    assert [doc["name"] for doc in status["documents"]] == ["lease.md"]

    # Switching profiles in the app is picked up by the running server.
    (home / ".vault" / ACTIVE_PROFILE_STATE_FILE).write_text("alpha")
    status = agent.get_status()
    assert status["profile"] == "alpha"
    assert [doc["name"] for doc in status["documents"]] == ["cake.md"]
    assert [s["document"] for s in agent.query("How long does the cake bake?")["sources"]] == ["cake.md"]


def test_agent_sees_documents_added_after_it_opened_the_index(home, engine):
    lease = _write(home / "docs", "lease.md", LEASE_TEXT)
    recipe = _write(home / "docs", "cake.md", RECIPE_TEXT)
    _enclave("model", "create", "workspace")
    _enclave("model", "ingest", "workspace", str(lease))

    agent = create_vault_server()._get_agent()
    assert agent.get_status()["document_count"] == 1
    agent.query("How much is the security deposit?")  # index now open in this process

    # Another process (the app or the CLI) adds a document.
    _enclave("model", "ingest", "workspace", str(recipe))

    assert agent.get_status()["document_count"] == 2
    sources = agent.query("How long does the cake bake at 170 degrees?")["sources"]
    assert "cake.md" in [source["document"] for source in sources]


def test_profile_override_env_var(home, engine, monkeypatch):
    lease = _write(home / "docs", "lease.md", LEASE_TEXT)
    _enclave("model", "create", "workspace")
    _enclave("model", "create", "legal")
    _enclave("model", "ingest", "legal", str(lease))

    monkeypatch.setenv(PROFILE_OVERRIDE_ENV, "legal")
    status = create_vault_server()._get_agent().get_status()
    assert status["profile"] == "legal"
    assert status["document_count"] == 1


def test_resolver_mirrors_the_app_profile_choice(home, monkeypatch):
    vault = home / ".vault"
    manager = PrivateModelManager(root_path=str(vault / "private_models"))

    # Nothing created yet: the app will create "workspace".
    location = resolve_active_profile(str(vault))
    assert (location.profile, location.source, location.profile_exists) == ("workspace", "default", False)
    assert location.db_path == vault / "private_models" / "workspace" / "vault" / "rag.db"
    assert location.key_path == vault / "private_models" / "workspace" / "vault" / "master.key"

    manager.create_profile("zeta")
    manager.create_profile("beta")
    # No persisted choice and no "workspace" profile: first profile by name.
    assert resolve_active_profile(str(vault)).profile == "beta"
    # A stale persisted choice falls back the same way the app does.
    (vault / ACTIVE_PROFILE_STATE_FILE).write_text("deleted-profile")
    location = resolve_active_profile(str(vault))
    assert (location.profile, location.source) == ("beta", "fallback")

    (vault / ACTIVE_PROFILE_STATE_FILE).write_text("zeta")
    location = resolve_active_profile(str(vault))
    assert (location.profile, location.source, location.profile_exists) == ("zeta", "active", True)

    # An explicit choice wins and never silently falls back to another profile.
    monkeypatch.setenv(PROFILE_OVERRIDE_ENV, "missing")
    location = resolve_active_profile(str(vault))
    assert (location.profile, location.source, location.profile_exists) == ("missing", "override", False)
    assert resolve_active_profile(str(vault), profile="beta").profile == "beta"

    for bad_name in ("../zeta", "a/b", "..", "."):
        with pytest.raises(ValueError):
            resolve_active_profile(str(vault), profile=bad_name)

    # Resolving is read-only.
    assert list(vault.rglob("master.key")) == []


def test_invalid_profile_override_is_reported_not_raised(home, engine, monkeypatch):
    monkeypatch.setenv(PROFILE_OVERRIDE_ENV, "../elsewhere")
    server = create_vault_server()
    agent = server._get_agent()

    status = agent.get_status()
    assert status["rag_available"] is False
    assert status["document_count"] == 0
    assert "Invalid profile name" in status["index_error"]

    result = agent.query("anything")
    assert result["sources"] == []
    assert "Invalid profile name" in result["error"]
    assert engine.rendered_prompts == []
