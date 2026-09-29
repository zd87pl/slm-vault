"""The shipped policy keeps the secrets tools away from unidentified MCP clients.

On a default install every MCP client is identified as ``unknown`` and gets the
``default`` entry of ``~/.enclave/policies.toml``. That entry used to allow
the ``vault_*`` tools, so any agent could read stored API keys and passwords
after one consent click. It now allows only the document Q&A tools, and a
policy file that is still exactly an earlier shipped default is replaced by
the current one (keeping a backup); a file the user edited is never rewritten.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from pathlib import Path

import pytest

from advanced_vault.enclave_control import EnclaveRuntime, KillSwitchState
from advanced_vault.enclave_control import config as policy_config
from advanced_vault.enclave_control.config import (
    DEFAULT_POLICY_TOML,
    SECRETS_TOOLS,
    EnclavePolicyConfig,
    parse_policy_document,
)
from advanced_vault.enclave_control.legacy_defaults import LEGACY_DEFAULT_POLICY_TOMLS

# sha256 of DEFAULT_POLICY_TOML in each commit that changed it:
# `git log -p -- advanced_vault/enclave_control/config.py`.
SHIPPED_DEFAULTS_SHA256 = {
    "b5cedcf16f7ae620d53469d3eacccb42ba41f91819e348027e0cc3010d1169ab",  # f6fb215
    "f00a98c16b3bd96e42c906efa5ce3e6d78f9d4925a11d297f46000f51e17eb58",  # b492c3a .. 2ec68a7
}

DOCUMENT_QA_TOOLS = ("agent_query", "agent_summarize", "agent_draft", "agent_status", "query_knowledge")
SHERIFF_TOOLS = (
    "sheriff_request_access", "sheriff_read", "sheriff_list_audit", "sheriff_revoke",
    "sheriff_risk_summary", "sheriff_protect_now", "sheriff_hardening_report",
    "sheriff_enforcement_status",
)
WALLET_TOOLS = (
    "create_envelope", "list_envelopes", "check_budget", "request_purchase",
    "approve_purchase", "get_transactions", "freeze_all", "unfreeze_all",
)
CLOUD_TOOLS = ("langchain_get_secret", "langchain_query_knowledge")
# SheriffCore re-checks the shared policy under these names, with module
# "vault", before it grants a lease or returns a file's content.
SHERIFF_INNER_TOOLS = ("sheriff.request_access", "sheriff.read")


def _module_for(tool: str) -> str:
    if tool.startswith("sheriff_"):
        return "security"
    if tool in WALLET_TOOLS:
        return "wallet"
    return "vault"


@pytest.fixture
def policy_path(tmp_path) -> Path:
    return tmp_path / ".enclave" / "policies.toml"


def _runtime(tmp_path, policy_path) -> EnclaveRuntime:
    return EnclaveRuntime(vault_path=str(tmp_path / "vault"), config_path=str(policy_path))


def _write(path: Path, data: str | bytes, mode: int = 0o644) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.write_bytes(raw)
    path.chmod(mode)
    return raw


def _backups(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.name}.bak-*"))


def _decision(runtime: EnclaveRuntime, tool: str, agent_id: str = "unknown") -> str:
    return runtime.evaluate_action(agent_id=agent_id, module=_module_for(tool), tool=tool)[0]


# --- the shipped default ---------------------------------------------------


class TestShippedDefault:
    @pytest.mark.parametrize("tool", SECRETS_TOOLS)
    def test_unknown_client_is_denied_secrets_tools(self, tmp_path, policy_path, tool):
        assert _decision(_runtime(tmp_path, policy_path), tool) == "deny"

    @pytest.mark.parametrize("tool", DOCUMENT_QA_TOOLS)
    def test_unknown_client_keeps_document_qa_tools(self, tmp_path, policy_path, tool):
        assert _decision(_runtime(tmp_path, policy_path), tool) == "allow"

    @pytest.mark.parametrize("tool", SHERIFF_TOOLS + SHERIFF_INNER_TOOLS + WALLET_TOOLS + CLOUD_TOOLS)
    def test_unknown_client_is_denied_file_wallet_and_cloud_tools(self, tmp_path, policy_path, tool):
        assert _decision(_runtime(tmp_path, policy_path), tool) == "deny"

    def test_default_entry_names_no_secrets_file_wallet_or_cloud_tool(self):
        # Defence in depth: even if someone adds a module to allowed_modules,
        # the default entry's tool list must not open these tools.
        default = parse_policy_document(DEFAULT_POLICY_TOML).agents["default"]

        everything_else = SECRETS_TOOLS + SHERIFF_TOOLS + SHERIFF_INNER_TOOLS + WALLET_TOOLS + CLOUD_TOOLS
        opened = [t for t in everything_else if default.allows_tool(t)]

        assert opened == []
        assert all(default.allows_tool(t) for t in DOCUMENT_QA_TOOLS)

    @pytest.mark.parametrize("agent_id", ["claude-desktop", "cursor", "openclaw"])
    def test_named_client_entries_still_exclude_secrets_tools(self, agent_id):
        policy = parse_policy_document(DEFAULT_POLICY_TOML).agents[agent_id]

        assert not any(policy.allows_tool(t) for t in SECRETS_TOOLS)

    def test_fresh_install_writes_the_current_default(self, tmp_path, policy_path):
        _runtime(tmp_path, policy_path)

        assert policy_path.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML
        assert _backups(policy_path) == []


class TestLegacyDefaults:
    def test_are_exactly_the_texts_that_shipped(self):
        digests = {hashlib.sha256(text.encode("utf-8")).hexdigest() for text in LEGACY_DEFAULT_POLICY_TOMLS}

        assert digests == SHIPPED_DEFAULTS_SHA256

    @pytest.mark.parametrize("legacy", LEGACY_DEFAULT_POLICY_TOMLS)
    def test_each_gave_unknown_clients_the_secrets_tools(self, legacy):
        # The migration exists because of this; if it ever stops being true
        # the text is not one of the vulnerable defaults.
        default = parse_policy_document(legacy).agents["default"]

        assert all(default.allows_tool(t) for t in SECRETS_TOOLS)

    def test_current_default_is_not_a_legacy_default(self):
        assert policy_config.upgrade_legacy_default(DEFAULT_POLICY_TOML) is None


# --- migration of an existing file -----------------------------------------


class TestUpgradeUnmodifiedLegacyDefault:
    @pytest.mark.parametrize("legacy", LEGACY_DEFAULT_POLICY_TOMLS)
    def test_is_replaced_with_a_backup(self, tmp_path, policy_path, legacy, caplog):
        original = _write(policy_path, legacy, mode=0o640)
        caplog.set_level(logging.WARNING, logger=policy_config.__name__)

        runtime = _runtime(tmp_path, policy_path)

        assert policy_path.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML
        assert stat.S_IMODE(policy_path.stat().st_mode) == 0o640
        [backup] = _backups(policy_path)
        assert backup.read_bytes() == original
        assert stat.S_IMODE(backup.stat().st_mode) == 0o640
        # Nothing else (e.g. a temp file) is left behind.
        assert sorted(p.name for p in policy_path.parent.iterdir()) == sorted([policy_path.name, backup.name])
        assert _decision(runtime, "vault_recall") == "deny"
        assert _decision(runtime, "agent_query") == "allow"
        assert str(policy_path) in caplog.text and str(backup) in caplog.text

    def test_is_replaced_only_once(self, tmp_path, policy_path):
        _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[-1])

        runtime = _runtime(tmp_path, policy_path)
        runtime.reload()
        _runtime(tmp_path, policy_path)

        assert len(_backups(policy_path)) == 1
        assert policy_path.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML

    def test_line_endings_and_trailing_whitespace_do_not_count_as_edits(self, tmp_path, policy_path):
        # Python's text mode writes \r\n on Windows; editors may add trailing
        # blanks or blank lines at the end. None of it changes the TOML.
        legacy = LEGACY_DEFAULT_POLICY_TOMLS[-1]
        variant = "\r\n".join(line + (" \t" if i % 3 == 0 else "") for i, line in enumerate(legacy.split("\n")))
        original = _write(policy_path, "\r\n" + variant + "\r\n\r\n")

        runtime = _runtime(tmp_path, policy_path)

        assert policy_path.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML
        [backup] = _backups(policy_path)
        assert backup.read_bytes() == original
        assert _decision(runtime, "vault_recall") == "deny"

    @pytest.mark.parametrize("state", [
        KillSwitchState(enabled=True, reason='incident "42"', updated_at="2026-09-01T10:00:00+00:00"),
        # Switched on and off again in the desktop app: only updated_at changed.
        KillSwitchState(enabled=False, reason="", updated_at="2026-09-02T11:00:00+00:00"),
    ])
    def test_kill_switch_state_is_carried_over(self, tmp_path, policy_path, state):
        # The app itself rewrites the [kill_switch] values; that is not an edit
        # to the policy, and an engaged kill switch must stay engaged.
        _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[-1])
        EnclavePolicyConfig(str(policy_path)).save_kill_switch(state)
        original = policy_path.read_bytes()

        runtime = _runtime(tmp_path, policy_path)

        document = parse_policy_document(policy_path.read_text(encoding="utf-8"))
        assert document.kill_switch == state
        assert runtime.get_kill_switch() == state
        assert document.agents == parse_policy_document(DEFAULT_POLICY_TOML).agents
        [backup] = _backups(policy_path)
        assert backup.read_bytes() == original
        runtime.set_kill_switch(False)
        assert _decision(runtime, "vault_recall") == "deny"

    def test_backup_never_overwrites_or_follows_an_existing_file(self, tmp_path, policy_path, monkeypatch):
        _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[-1])
        monkeypatch.setattr(policy_config, "_backup_stamp", lambda: "20260101-000000")
        taken = policy_path.with_name("policies.toml.bak-20260101-000000")
        taken.write_text("someone else's file")
        outside = tmp_path / "outside.txt"
        outside.write_text("do not touch")
        policy_path.with_name("policies.toml.bak-20260101-000000-1").symlink_to(outside)

        _runtime(tmp_path, policy_path)

        assert taken.read_text() == "someone else's file"
        assert outside.read_text() == "do not touch"
        backup = policy_path.with_name("policies.toml.bak-20260101-000000-2")
        assert backup.read_text(encoding="utf-8") == LEGACY_DEFAULT_POLICY_TOMLS[-1]
        assert policy_path.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML

    def test_symlinked_file_is_upgraded_at_its_target(self, tmp_path, policy_path):
        target = tmp_path / "dotfiles" / "policies.toml"
        _write(target, LEGACY_DEFAULT_POLICY_TOMLS[-1])
        policy_path.parent.mkdir(parents=True)
        policy_path.symlink_to(target)

        runtime = _runtime(tmp_path, policy_path)

        assert policy_path.is_symlink()
        assert target.read_text(encoding="utf-8") == DEFAULT_POLICY_TOML
        assert len(_backups(target)) == 1
        assert _decision(runtime, "vault_recall") == "deny"

    def test_failed_replace_keeps_the_file_but_still_enforces_the_new_default(
        self, tmp_path, policy_path, monkeypatch, caplog
    ):
        original = _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[-1])

        def refuse(*_args, **_kwargs):
            raise PermissionError("read-only file system")

        monkeypatch.setattr(policy_config.os, "replace", refuse)
        caplog.set_level(logging.WARNING, logger=policy_config.__name__)

        runtime = _runtime(tmp_path, policy_path)

        assert policy_path.read_bytes() == original
        assert list(policy_path.parent.iterdir()) == [policy_path]  # no backup or temp file left
        assert _decision(runtime, "vault_recall") == "deny"  # fail closed
        assert "read-only file system" in caplog.text

    def test_read_only_file_is_left_alone_but_the_new_default_is_enforced(
        self, tmp_path, policy_path, monkeypatch
    ):
        original = _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[-1], mode=0o444)
        if getattr(os, "geteuid", lambda: -1)() == 0:
            # root may write anyway; see the file the way its owner would.
            real_access = os.access
            monkeypatch.setattr(
                policy_config.os, "access",
                lambda path, mode, **kw: False if Path(path) == policy_path and mode & os.W_OK
                else real_access(path, mode, **kw),
            )

        runtime = _runtime(tmp_path, policy_path)

        assert policy_path.read_bytes() == original
        assert _backups(policy_path) == []
        assert _decision(runtime, "vault_recall") == "deny"

    def test_an_edit_made_during_the_upgrade_is_not_overwritten(self, tmp_path, policy_path, monkeypatch):
        _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[-1])
        edited = LEGACY_DEFAULT_POLICY_TOMLS[-1] + "\n# edited while Enclave was starting\n"
        real_backup = policy_config._write_backup

        def backup_then_user_edits(path, data, mode):
            backup = real_backup(path, data, mode)
            path.write_text(edited, encoding="utf-8")
            return backup

        monkeypatch.setattr(policy_config, "_write_backup", backup_then_user_edits)

        runtime = _runtime(tmp_path, policy_path)

        assert policy_path.read_text(encoding="utf-8") == edited
        assert _backups(policy_path) == []
        # The file on disk is what is enforced -- here, the user's edited file.
        assert _decision(runtime, "vault_recall") == "allow"


class TestUserModifiedFileIsNeverRewritten:
    @pytest.mark.parametrize("edit", [
        pytest.param(lambda text: text + "# keep vault_* for every app\n", id="comment-added"),
        pytest.param(lambda text: text.replace('"vault_*", ', ""), id="vault-removed-by-hand"),
        pytest.param(lambda text: text.replace("start_hour = 0", "start_hour = 1", 1), id="value-changed"),
        pytest.param(lambda text: text.replace("[[agents]]", "  [[agents]]", 1), id="re-indented"),
        pytest.param(lambda text: text.replace('reason = ""', 'reason = ""  # why', 1), id="kill-switch-comment"),
        pytest.param(
            lambda text: text + '\n[[agents]]\nagent_id = "vscode"\nallowed_tools = ["agent_*"]\n',
            id="entry-added",
        ),
    ])
    @pytest.mark.parametrize("legacy", LEGACY_DEFAULT_POLICY_TOMLS)
    def test_is_left_byte_for_byte(self, tmp_path, policy_path, legacy, edit):
        modified = edit(legacy)
        assert modified != legacy
        original = _write(policy_path, modified)

        runtime = _runtime(tmp_path, policy_path)
        runtime.reload()

        assert policy_path.read_bytes() == original
        assert _backups(policy_path) == []
        expected = parse_policy_document(modified).agents["default"]
        assert runtime.get_agent_policy("unknown") == expected  # the user's policy is what applies

    def test_upgrade_check_rejects_it(self):
        edited = LEGACY_DEFAULT_POLICY_TOMLS[-1] + "# mine\n"

        assert policy_config.upgrade_legacy_default(edited) is None
