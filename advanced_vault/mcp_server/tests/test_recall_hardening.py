"""
Regression tests for vault_recall secret disclosure and secret values in logs.

- vault_recall used to return a stored secret on loose keyword overlap: an
  agent asking "tell me about stripe" received the raw Stripe key. A value is
  now returned only when the query is exactly the name of one stored entry;
  anything else can at most list matching entry names.
- A tool call denied by the shared policy used to write its full arguments
  (e.g. the secret ``content`` of vault_store) into the audit database.
"""

import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from mcp import types

from advanced_vault.core import HybridVault
from advanced_vault.mcp_server import activity_logger
from advanced_vault.mcp_server.server import VaultMCPServer

STRIPE_SECRET = "sk_live_REALSECRET123"
GITHUB_SECRET = "ghp_GITHUBSECRET456"


def _dump(result):
    return json.dumps(result, default=str)


def _persisted_files_containing(root: Path, needle: str):
    """Every file under ``root`` whose bytes contain ``needle``."""
    return [
        str(path) for path in root.rglob("*")
        if path.is_file() and needle.encode("utf-8") in path.read_bytes()
    ]


@pytest.fixture
def vault(tmp_path):
    vault = HybridVault(master_key=os.urandom(32), kv_db_path=str(tmp_path / "vault.db"))
    vault.store(STRIPE_SECRET, data_type="secret", service="stripe",
                tags=["payment"], description="Production Stripe key")
    vault.store(GITHUB_SECRET, data_type="secret", service="github", tags=["code"])
    yield vault
    vault.close()


class TestRecallRequiresExactName:
    """HybridVault.query releases a stored value only for an exact entry name."""

    def test_tell_me_about_stripe_does_not_return_value(self, vault):
        result = vault.query("tell me about stripe")

        assert result["result"] is None
        assert result["matches"] == ["stripe"]
        assert STRIPE_SECRET not in _dump(result)

    @pytest.mark.parametrize("query", [
        "What's my Stripe API key?",
        "Show me everything about Stripe",
        "stripe payment info",
        "stripe key",
        "stripe production",
    ])
    def test_natural_language_queries_never_return_value(self, vault, query):
        result = vault.query(query)

        assert result.get("result") is None
        assert STRIPE_SECRET not in _dump(result)
        assert GITHUB_SECRET not in _dump(result)
        assert "stripe" in result["matches"]
        # The caller is told which exact name to ask for instead.
        assert "stripe" in result["error"]

    @pytest.mark.parametrize("query", ["stripe", "Stripe", "  STRIPE  "])
    def test_exact_name_returns_value(self, vault, query):
        result = vault.query(query)

        assert result["result"] == STRIPE_SECRET
        assert result["service"] == "stripe"
        assert result["layer"] == 1
        assert "error" not in result

    def test_query_matching_several_entries_returns_names_only(self, vault):
        result = vault.query("stripe and github")

        assert result.get("result") is None
        assert set(result["matches"]) == {"stripe", "github"}
        assert STRIPE_SECRET not in _dump(result)
        assert GITHUB_SECRET not in _dump(result)

    def test_names_differing_only_by_case_are_ambiguous(self, vault):
        vault.store("sk_test_OTHERSECRET", data_type="secret", service="Stripe")

        ambiguous = vault.query("STRIPE")
        assert ambiguous.get("result") is None
        assert sorted(ambiguous["matches"]) == ["Stripe", "stripe"]
        assert STRIPE_SECRET not in _dump(ambiguous)
        assert "sk_test_OTHERSECRET" not in _dump(ambiguous)

        # The verbatim name still selects exactly one entry.
        assert vault.query("stripe")["result"] == STRIPE_SECRET
        assert vault.query("Stripe")["result"] == "sk_test_OTHERSECRET"

    def test_unrelated_query_returns_no_value(self, vault):
        result = vault.query("What's my nonexistent key?")

        assert result.get("result") is None
        assert result.get("error")
        assert STRIPE_SECRET not in _dump(result)
        assert GITHUB_SECRET not in _dump(result)

    def test_knowledge_notes_follow_the_same_rule(self, vault):
        vault.store("Chose Stripe for its webhooks", data_type="knowledge", service="payments-notes")

        fuzzy = _dump(vault.query("why did I choose stripe webhooks"))
        assert "Chose Stripe" not in fuzzy
        assert STRIPE_SECRET not in fuzzy
        assert vault.query("payments-notes")["result"] == "Chose Stripe for its webhooks"


class TestRedactToolArguments:
    """The shared helper keeps argument names but drops sensitive values."""

    def test_vault_store_content_is_redacted(self):
        redacted = activity_logger.redact_tool_arguments("vault_store", {
            "content": STRIPE_SECRET,
            "data_type": "secret",
            "service": "stripe",
            "tags": ["payment"],
        })

        assert STRIPE_SECRET not in _dump(redacted)
        assert redacted["content"] == f"[redacted: {len(STRIPE_SECRET)} chars]"
        assert redacted["data_type"] == "secret"
        assert redacted["service"] == "stripe"
        assert redacted["tags"] == ["payment"]

    @pytest.mark.parametrize("name", [
        "value", "secret", "password", "token", "api_key", "key",
        "apiKey", "access_token", "client-secret", "PASSWORD",
    ])
    def test_sensitive_names_are_redacted_for_any_tool(self, name):
        redacted = activity_logger.redact_tool_arguments("any_tool", {name: "hunter2", "note": "ok"})

        assert redacted == {name: "[redacted: 7 chars]", "note": "ok"}

    @pytest.mark.parametrize("name", [
        "secrets", "tokens", "passwords", "keys", "api_keys", "values",
        "APIToken", "APISecret", "apitoken", "clientsecret", "privatekey",
        "auth", "authorization", "Authorization", "bearer", "pwd", "cookie",
    ])
    def test_plural_joined_and_auth_names_are_redacted(self, name):
        redacted = activity_logger.redact_tool_arguments("any_tool", {name: "hunter2", "note": "ok"})

        assert redacted == {name: "[redacted: 7 chars]", "note": "ok"}

    def test_nested_and_non_string_values_are_redacted(self):
        redacted = activity_logger.redact_tool_arguments("any_tool", {
            "options": {"password": "hunter2", "retries": 3},
            "items": [{"token": "abc"}],
            "key": 12345,
        })

        assert redacted == {
            "options": {"password": "[redacted: 7 chars]", "retries": 3},
            "items": [{"token": "[redacted: 3 chars]"}],
            "key": "[redacted]",
        }

    def test_names_merely_containing_a_sensitive_word_are_kept(self):
        args = {"max_tokens": 512, "keyword": "stripe", "question": "What is my revenue?"}

        assert activity_logger.redact_tool_arguments("agent_query", args) == args

    def test_input_is_not_modified(self):
        args = {"content": STRIPE_SECRET, "options": {"token": "abc"}}

        activity_logger.redact_tool_arguments("vault_store", args)

        assert args == {"content": STRIPE_SECRET, "options": {"token": "abc"}}

    def test_non_mapping_arguments_are_not_logged(self):
        assert activity_logger.redact_tool_arguments("vault_store", [STRIPE_SECRET]) == {
            "_redacted": "list"
        }

    def test_activity_logger_redacts_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        logger = activity_logger.ActivityLogger(vault_path=str(tmp_path / "vault"))

        logger.log_access(
            tool_name="vault_store",
            app_identifier="unknown",
            query_preview="Store secret",
            metadata={"arguments": {"content": STRIPE_SECRET, "service": "stripe"}},
        )

        assert _persisted_files_containing(tmp_path, STRIPE_SECRET) == []
        entry = logger.get_recent_activity(limit=1)[0]
        assert entry["metadata"]["arguments"]["service"] == "stripe"
        assert entry["metadata"]["arguments"]["content"].startswith("[redacted")


class TestMCPToolCalls:
    """End-to-end through the registered MCP call_tool handler."""

    @pytest.fixture
    def server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        return VaultMCPServer(vault_path=str(tmp_path / "vault"))

    def _as_client(self, monkeypatch, server, app_identifier, consent=True):
        monkeypatch.setattr(server.consent_manager, "_get_app_identifier", lambda: app_identifier)
        monkeypatch.setattr(server.consent_manager, "request_consent", lambda **_: consent)

    async def _call(self, server, name, arguments):
        handler = server.server.request_handlers[types.CallToolRequest]
        request = types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name=name, arguments=arguments),
        )
        result = await handler(request)
        return "\n".join(block.text for block in result.root.content)

    def _audit_events(self, tmp_path):
        with closing(sqlite3.connect(tmp_path / "vault" / "control_plane" / "events.db")) as conn:
            rows = conn.execute("SELECT tool, decision, metadata FROM events").fetchall()
        return [(tool, decision, json.loads(metadata)) for tool, decision, metadata in rows]

    @pytest.mark.asyncio
    async def test_fuzzy_recall_returns_names_not_value(self, monkeypatch, server):
        self._as_client(monkeypatch, server, "unknown")
        server._get_vault().store(STRIPE_SECRET, data_type="secret", service="stripe")

        text = await self._call(server, "vault_recall", {"query": "tell me about stripe"})

        assert STRIPE_SECRET not in text
        assert "stripe" in text

    @pytest.mark.asyncio
    async def test_exact_recall_returns_value(self, monkeypatch, server):
        self._as_client(monkeypatch, server, "unknown")
        server._get_vault().store(STRIPE_SECRET, data_type="secret", service="stripe")

        text = await self._call(server, "vault_recall", {"query": "stripe"})

        assert STRIPE_SECRET in text

    @pytest.mark.asyncio
    async def test_policy_denied_store_keeps_secret_out_of_logs(self, tmp_path, monkeypatch, server, caplog):
        # The default policy does not allow claude-desktop to call vault_* tools.
        self._as_client(monkeypatch, server, "claude-desktop")
        caplog.set_level(logging.DEBUG)

        text = await self._call(server, "vault_store", {
            "content": STRIPE_SECRET, "data_type": "secret", "service": "stripe",
        })

        assert "denied" in text
        assert _persisted_files_containing(tmp_path, STRIPE_SECRET) == []
        assert STRIPE_SECRET not in caplog.text
        denied = [meta for tool, decision, meta in self._audit_events(tmp_path)
                  if tool == "vault_store" and decision == "DENY"]
        assert len(denied) == 1
        arguments = denied[0]["arguments"]
        assert set(arguments) == {"content", "data_type", "service"}
        assert arguments["content"] == f"[redacted: {len(STRIPE_SECRET)} chars]"
        assert arguments["service"] == "stripe"

    @pytest.mark.asyncio
    async def test_consent_denied_store_keeps_secret_out_of_logs(self, tmp_path, monkeypatch, server, caplog):
        self._as_client(monkeypatch, server, "unknown", consent=False)
        caplog.set_level(logging.DEBUG)

        text = await self._call(server, "vault_store", {
            "content": STRIPE_SECRET, "data_type": "secret", "service": "stripe",
        })

        assert "Access denied" in text
        assert _persisted_files_containing(tmp_path, STRIPE_SECRET) == []
        assert STRIPE_SECRET not in caplog.text

    @pytest.mark.asyncio
    async def test_allowed_store_and_recall_keep_secret_out_of_logs(self, tmp_path, monkeypatch, server, caplog):
        self._as_client(monkeypatch, server, "unknown")
        caplog.set_level(logging.DEBUG)

        stored = await self._call(server, "vault_store", {
            "content": STRIPE_SECRET, "data_type": "secret", "service": "stripe",
        })
        recalled = await self._call(server, "vault_recall", {"query": "stripe"})

        assert "Stored stripe secret" in stored
        assert STRIPE_SECRET in recalled
        # vault.db holds only ciphertext; no log or audit file holds the value.
        assert _persisted_files_containing(tmp_path, STRIPE_SECRET) == []
        assert STRIPE_SECRET not in caplog.text
        tools = [tool for tool, decision, _ in self._audit_events(tmp_path) if decision == "ALLOW"]
        assert "vault_store" in tools and "vault_recall" in tools
