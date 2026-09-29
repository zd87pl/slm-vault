"""`enclave doctor` warns when apps Enclave cannot identify may use the secrets tools."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from advanced_vault.cli import doctor
from advanced_vault.cli.doctor import FAIL, PASS, WARN, CheckResult, check_secrets_policy
from advanced_vault.enclave_control.config import DEFAULT_POLICY_TOML, EnclavePolicyConfig
from advanced_vault.enclave_control.legacy_defaults import LEGACY_DEFAULT_POLICY_TOMLS

DEFAULT_TOOLS_LINE = 'allowed_tools = ["agent_*", "query_knowledge", "agent_status"]'


@pytest.fixture
def policy_path(tmp_path) -> Path:
    return tmp_path / ".enclave" / "policies.toml"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _line_of(text: str, needle: str, occurrence: int = 1) -> int:
    """1-based line number of the n-th line of ``text`` that contains ``needle``."""
    hits = [n for n, line in enumerate(text.split("\n"), start=1) if needle in line]
    return hits[occurrence - 1]


def _check(path: Path) -> CheckResult:
    before = path.read_bytes() if path.exists() else None
    result = check_secrets_policy(path)
    # The doctor only reads the policy file; it never creates or rewrites it.
    assert (path.read_bytes() if path.exists() else None) == before
    return result


def test_passes_on_the_current_default(policy_path):
    EnclavePolicyConfig(str(policy_path))  # writes the shipped default

    result = _check(policy_path)

    assert result.status == PASS, result.detail
    assert str(policy_path) in result.detail


def test_passes_before_the_file_exists(policy_path):
    result = _check(policy_path)

    assert result.status == PASS
    assert not policy_path.exists()


def test_passes_when_only_a_named_app_is_opted_in(policy_path):
    # The documented way to give one app the secrets tools.
    text = DEFAULT_POLICY_TOML.replace(
        'agent_id = "claude-desktop"\ntrust_level = "brokered"\nallowed_modules = ["vault", "wallet"]\n'
        'allowed_tools = [',
        'agent_id = "claude-desktop"\ntrust_level = "brokered"\nallowed_modules = ["vault", "wallet"]\n'
        'allowed_tools = ["vault_*", ',
    )
    assert text != DEFAULT_POLICY_TOML
    _write(policy_path, text)

    assert _check(policy_path).status == PASS


def test_warns_with_the_exact_line_when_default_allows_vault_tools(policy_path):
    text = DEFAULT_POLICY_TOML.replace(
        DEFAULT_TOOLS_LINE, 'allowed_tools = ["agent_*", "query_knowledge", "vault_*"]'
    )
    _write(policy_path, text)

    result = _check(policy_path)

    assert result.status == WARN
    assert "vault_recall" in result.detail and "vault_store" in result.detail
    line = _line_of(text, '"vault_*"')
    assert f"In {policy_path}, line {line} " in result.fix
    assert 'agent_id = "default"' in result.fix
    assert 'remove "vault_*"' in result.fix
    assert "add back" not in result.fix  # the document tools are untouched


def test_warns_on_a_user_modified_legacy_default_and_points_at_its_line(policy_path):
    legacy = LEGACY_DEFAULT_POLICY_TOMLS[-1]
    text = legacy + "# I edited this file\n"
    _write(policy_path, text)
    EnclavePolicyConfig(str(policy_path)).load()  # the app leaves an edited file alone

    result = _check(policy_path)

    assert result.status == WARN
    line = _line_of(text, '"vault_*"')
    assert line == 13  # allowed_tools of the `default` entry in every old default
    assert f"line {line} " in result.fix
    assert 'remove "vault_*"' in result.fix


def test_warns_on_an_unmodified_legacy_default_without_touching_it(policy_path):
    _write(policy_path, LEGACY_DEFAULT_POLICY_TOMLS[0])

    result = _check(policy_path)

    assert result.status == WARN
    assert "older" in result.detail and "replaces it automatically" in result.detail
    assert "quit and reopen" in result.fix


def test_wildcard_hint_says_to_add_back_the_document_tools(policy_path):
    wildcard = 'allowed_tools = ["*"]'
    text = DEFAULT_POLICY_TOML.replace(DEFAULT_TOOLS_LINE, wildcard)
    _write(policy_path, text)

    result = _check(policy_path)

    assert result.status == WARN
    assert f"line {_line_of(text, wildcard)} " in result.fix
    assert 'remove "*"' in result.fix
    assert "add back" in result.fix and '"agent_*"' in result.fix


def test_entry_without_allowed_tools_allows_everything(policy_path):
    text = DEFAULT_POLICY_TOML.replace(DEFAULT_TOOLS_LINE + "\n", "")
    _write(policy_path, text)

    result = _check(policy_path)

    assert result.status == WARN
    entry_line = _line_of(text, 'agent_id = "default"')
    assert f"(line {entry_line})" in result.fix
    assert "has no allowed_tools" in result.fix


def test_missing_default_entry_allows_everything(policy_path):
    start = DEFAULT_POLICY_TOML.index('[[agents]]\nagent_id = "default"')
    end = DEFAULT_POLICY_TOML.index("[[agents]]", start + 1)
    _write(policy_path, DEFAULT_POLICY_TOML[:start] + DEFAULT_POLICY_TOML[end:])

    result = _check(policy_path)

    assert result.status == WARN
    assert 'no [[agents]] entry with agent_id = "default"' in result.fix


def test_an_unknown_entry_is_what_unidentified_apps_get(policy_path):
    text = DEFAULT_POLICY_TOML + '\n[[agents]]\nagent_id = "unknown"\nallowed_tools = ["vault_recall"]\n'
    _write(policy_path, text)

    result = _check(policy_path)

    assert result.status == WARN
    assert "vault_recall" in result.detail and "vault_store" not in result.detail
    assert f"line {_line_of(text, 'vault_recall')} " in result.fix
    assert 'agent_id = "unknown"' in result.fix


def test_the_last_of_duplicate_entries_is_the_one_reported(policy_path):
    # The loader keeps the last entry with a given agent_id.
    text = DEFAULT_POLICY_TOML + '\n[[agents]]\nagent_id = "default"\nallowed_tools = ["agent_*", "vault_list_entries"]\n'
    _write(policy_path, text)

    result = _check(policy_path)

    assert result.status == WARN
    assert f"line {_line_of(text, 'vault_list_entries')} " in result.fix
    assert 'remove "vault_list_entries"' in result.fix


def test_passes_when_default_has_no_vault_module(policy_path):
    text = DEFAULT_POLICY_TOML.replace(DEFAULT_TOOLS_LINE, 'allowed_tools = ["*"]').replace(
        'allowed_modules = ["vault"]', "allowed_modules = []", 1
    )
    _write(policy_path, text)

    assert _check(policy_path).status == PASS


@pytest.mark.parametrize("text", [
    pytest.param("[[agents]\nagent_id = ", id="invalid-toml"),
    pytest.param('[agents]\nagent_id = "default"\n', id="table-instead-of-array"),
    pytest.param(b"\xff\xfe", id="not-utf8"),
])
def test_a_policy_the_server_cannot_load_fails(policy_path, text):
    policy_path.parent.mkdir(parents=True)
    policy_path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))

    result = _check(policy_path)

    assert result.status == FAIL
    assert str(policy_path) in result.detail


def test_run_checks_includes_the_policy_check(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(doctor, "check_mcp_server", lambda: CheckResult("MCP server", PASS, "stubbed"))
    _write(home / ".enclave" / "policies.toml", DEFAULT_POLICY_TOML.replace(
        DEFAULT_TOOLS_LINE, 'allowed_tools = ["agent_*", "vault_*"]'
    ))

    report = doctor.run_checks(vault_path=str(tmp_path / "vault"))

    [check] = [c for c in report.checks if c.name == "Secrets tools"]
    assert check.status == WARN
    assert re.search(r"line \d+ ", check.fix)
