"""End to end through call_tool: unidentified MCP clients get no secrets tools.

`enclave mcp install` does not tell the server which app is calling, so on a
default install every client -- Claude Desktop, Cursor, anything -- is
``unknown`` and gets the ``default`` policy entry. That entry used to allow the
``vault_*`` tools: after one consent click any agent could read stored API
keys. It now allows only the document Q&A tools; an app gets the secrets tools
only when the user names it (``MCP_CLIENT``) and opts its entry in.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from mcp import types

from advanced_vault.enclave_control.config import DEFAULT_POLICY_TOML, SECRETS_TOOLS
from advanced_vault.enclave_control.legacy_defaults import LEGACY_DEFAULT_POLICY_TOMLS
from advanced_vault.mcp_server.server import VaultMCPServer

# Short test ids instead of the full TOML text
LEGACY_DEFAULT_IDS = ["2026-03", "2026-07"]

STRIPE_SECRET = "sk_live_REALSECRET123"
DOCUMENT_QA_TOOLS = {"agent_query", "agent_summarize", "agent_draft", "agent_status", "query_knowledge"}
SECRETS_TOOL_ARGUMENTS = {
    "vault_recall": {"query": "stripe"},
    "vault_store": {"content": "sk_live_PLANTED", "data_type": "secret", "service": "planted"},
    "vault_list_entries": {},
    "vault_delete": {"service": "stripe"},
    "vault_stats": {},
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name in ("MCP_CLIENT", "PARENT_PROCESS"):
        monkeypatch.delenv(name, raising=False)
    return home


@pytest.fixture
def consent_requests(monkeypatch):
    """Grant every consent prompt, recording which tools asked for one."""
    asked = []

    def grant(*, tool_name, query_preview="", **_):
        asked.append(tool_name)
        return True

    monkeypatch.setattr("advanced_vault.mcp_server.consent.ConsentManager.request_consent",
                        lambda self, **kwargs: grant(**kwargs))
    return asked


def _server(tmp_path) -> VaultMCPServer:
    return VaultMCPServer(vault_path=str(tmp_path / "vault"))


def _as_unknown(monkeypatch, server):
    monkeypatch.setattr(server.consent_manager, "_get_app_identifier", lambda: "unknown")


async def _call(server, name, arguments) -> str:
    handler = server.server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(request)
    return "\n".join(block.text for block in result.root.content)


async def _advertised_tools(server) -> list[str]:
    handler = server.server.request_handlers[types.ListToolsRequest]
    result = await handler(types.ListToolsRequest(method="tools/list"))
    return [tool.name for tool in result.root.tools]


def _audit(tmp_path):
    with closing(sqlite3.connect(tmp_path / "vault" / "control_plane" / "events.db")) as conn:
        rows = conn.execute("SELECT subject, tool, decision FROM events").fetchall()
    return rows


def _persisted_files_containing(root: Path, needle: str):
    return [str(p) for p in root.rglob("*") if p.is_file() and needle.encode() in p.read_bytes()]


@pytest.mark.asyncio
async def test_fresh_install_unknown_client_cannot_recall_or_store_secrets(
    tmp_path, home, monkeypatch, consent_requests
):
    server = _server(tmp_path)
    _as_unknown(monkeypatch, server)
    server._get_vault().store(STRIPE_SECRET, data_type="secret", service="stripe")

    recalled = await _call(server, "vault_recall", {"query": "stripe"})
    stored = await _call(server, "vault_store", {
        "content": "sk_live_PLANTED", "data_type": "secret", "service": "planted",
    })

    assert (home / ".enclave" / "policies.toml").read_text(encoding="utf-8") == DEFAULT_POLICY_TOML
    assert "Shared policy denied vault_recall" in recalled
    assert STRIPE_SECRET not in recalled
    assert "Shared policy denied vault_store" in stored
    assert server._get_vault().query("planted").get("result") is None
    assert _persisted_files_containing(tmp_path, "sk_live_PLANTED") == []
    assert consent_requests == []  # denied before the user is even asked
    denied = {(subject, tool) for subject, tool, decision in _audit(tmp_path) if decision == "DENY"}
    assert {("unknown", "vault_recall"), ("unknown", "vault_store")} <= denied


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(SECRETS_TOOL_ARGUMENTS))
async def test_every_secrets_tool_is_denied_to_unknown_clients(tmp_path, home, monkeypatch, consent_requests, tool):
    server = _server(tmp_path)
    _as_unknown(monkeypatch, server)
    server._get_vault().store(STRIPE_SECRET, data_type="secret", service="stripe")

    text = await _call(server, tool, SECRETS_TOOL_ARGUMENTS[tool])

    assert f"Shared policy denied {tool}" in text
    assert "stripe" not in text.split(":", 1)[1]  # no value, no entry name
    assert server._get_vault().query("stripe")["result"] == STRIPE_SECRET  # vault_delete did nothing


@pytest.mark.asyncio
async def test_unknown_clients_may_call_only_the_document_qa_tools(tmp_path, home):
    # Pins the whole default surface: a new tool that unknown clients can call
    # must be a deliberate change to this set.
    server = _server(tmp_path)
    advertised = await _advertised_tools(server)

    allowed = {
        name for name in advertised
        if server.runtime.evaluate_action(
            agent_id="unknown", module=server._module_for_tool(name), tool=name
        )[0] == "allow"
    }

    assert allowed == DOCUMENT_QA_TOOLS


@pytest.mark.asyncio
async def test_every_advertised_vault_tool_is_a_known_secrets_tool(tmp_path, home):
    # `enclave doctor` checks the policy against SECRETS_TOOLS.
    advertised = await _advertised_tools(_server(tmp_path))

    assert {name for name in advertised if name.startswith("vault_")} == set(SECRETS_TOOLS)


@pytest.mark.asyncio
async def test_unknown_clients_still_reach_the_document_tools(tmp_path, home, monkeypatch, consent_requests):
    server = _server(tmp_path)
    _as_unknown(monkeypatch, server)

    async def fake_status(args):
        return [types.TextContent(type="text", text="status handler reached")]

    monkeypatch.setattr(server, "_handle_agent_status", fake_status)

    text = await _call(server, "agent_status", {})

    assert text == "status handler reached"
    assert consent_requests == ["agent_status"]  # consent is still asked


@pytest.mark.asyncio
async def test_an_app_named_by_mcp_client_and_opted_in_gets_the_secrets_tools(
    tmp_path, home, monkeypatch, consent_requests
):
    # The documented opt-in: the app's MCP config sets MCP_CLIENT, and the
    # user adds vault_* tools to that app's entry in policies.toml.
    server = _server(tmp_path)
    policy_path = home / ".enclave" / "policies.toml"
    entry = 'agent_id = "claude-desktop"\ntrust_level = "brokered"\nallowed_modules = ["vault", "wallet"]\n'
    text = policy_path.read_text(encoding="utf-8")
    opted_in = text.replace(entry + "allowed_tools = [", entry + 'allowed_tools = ["vault_recall", ')
    assert opted_in != text
    policy_path.write_text(opted_in, encoding="utf-8")
    server.runtime.reload()
    server._get_vault().store(STRIPE_SECRET, data_type="secret", service="stripe")

    monkeypatch.setenv("MCP_CLIENT", "claude-desktop")
    recalled = await _call(server, "vault_recall", {"query": "stripe"})
    stored = await _call(server, "vault_store", {"content": "x", "data_type": "secret", "service": "y"})
    monkeypatch.delenv("MCP_CLIENT")
    _as_unknown(monkeypatch, server)
    unknown = await _call(server, "vault_recall", {"query": "stripe"})

    assert STRIPE_SECRET in recalled
    assert "Shared policy denied vault_store" in stored  # only the tools it was given
    assert "Shared policy denied vault_recall" in unknown and STRIPE_SECRET not in unknown


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", LEGACY_DEFAULT_POLICY_TOMLS, ids=LEGACY_DEFAULT_IDS)
async def test_an_old_default_on_disk_is_upgraded_before_the_first_call(
    tmp_path, home, monkeypatch, consent_requests, legacy
):
    policy_path = home / ".enclave" / "policies.toml"
    policy_path.parent.mkdir()
    policy_path.write_text(legacy, encoding="utf-8")

    server = _server(tmp_path)
    _as_unknown(monkeypatch, server)
    server._get_vault().store(STRIPE_SECRET, data_type="secret", service="stripe")
    text = await _call(server, "vault_recall", {"query": "stripe"})

    assert "Shared policy denied vault_recall" in text and STRIPE_SECRET not in text
    assert policy_path.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML
    [backup] = policy_path.parent.glob("policies.toml.bak-*")
    assert backup.read_text(encoding="utf-8") == legacy
