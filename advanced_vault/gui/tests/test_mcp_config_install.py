"""Regression tests: `enclave mcp install` must never clobber a client config."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from advanced_vault.gui.mcp_setup import MCPSetupHelper

BACKUP_RE = re.compile(r"^claude_desktop_config\.json\.bak-\d{8}-\d{6}(-\d+)?$")

EXISTING_CONFIG = {
    "globalShortcut": "Ctrl+Space",
    "preferences": {"theme": "dark", "nested": {"keep": [1, 2, 3]}},
    "mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
        "sheriff": {"command": "old-enclave"},
        "github": {"command": "docker", "env": {"GITHUB_TOKEN": "x"}},
    },
}


@pytest.fixture
def helper(tmp_path: Path):
    return MCPSetupHelper(vault_path=str(tmp_path / "vault"))


def _install(helper: MCPSetupHelper, config_path: Path) -> dict:
    with patch.object(helper, "detect_claude_desktop", return_value=True), patch.object(
        helper, "_resolve_config_path", return_value=config_path
    ):
        return helper.auto_configure(target="claude")


def _siblings(config_path: Path) -> list:
    return sorted(p.name for p in config_path.parent.iterdir())


def _backups(config_path: Path) -> list:
    return [p for p in config_path.parent.iterdir() if BACKUP_RE.match(p.name)]


def _assert_untouched(config_path: Path, original: bytes, mtime_ns: int) -> None:
    assert config_path.read_bytes() == original
    assert config_path.stat().st_mtime_ns == mtime_ns
    # No backup, no temp file, nothing else created next to it.
    assert _siblings(config_path) == [config_path.name]


@pytest.mark.parametrize(
    "content",
    [
        '{"mcpServers": {"filesystem": {"command": "npx"}},',  # truncated
        "{'mcpServers': {}}",  # single quotes
        '{"a": 1} // trailing comment',
        "",
        b"\xff\xfe\x00garbage",
    ],
)
def test_malformed_config_is_refused_and_left_untouched(helper, tmp_path, content):
    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir()
    if isinstance(content, bytes):
        config_path.write_bytes(content)
    else:
        config_path.write_text(content, encoding="utf-8")
    original = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns

    result = _install(helper, config_path)

    assert result["success"] is False
    error = result["error"]
    assert str(config_path) in error
    assert "JSON" in error
    assert "Nothing was written" in error
    assert "Fix or move" in error
    _assert_untouched(config_path, original, mtime_ns)


def test_parse_error_detail_is_reported(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text('{\n  "mcpServers": {\n    "a": 1\n  \n', encoding="utf-8")

    result = _install(helper, config_path)

    assert result["success"] is False
    # json's own diagnostic (with line/column) is surfaced to the user.
    assert "line " in result["error"] and "column " in result["error"]


@pytest.mark.parametrize("content", ["[]", '["enclave"]', '"text"', "42", "true", "null"])
def test_valid_json_that_is_not_an_object_is_refused(helper, tmp_path, content):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(content, encoding="utf-8")
    original = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns

    result = _install(helper, config_path)

    assert result["success"] is False
    assert str(config_path) in result["error"]
    assert "not a JSON object" in result["error"]
    _assert_untouched(config_path, original, mtime_ns)


@pytest.mark.parametrize("servers", ["[]", '"enclave"', "1"])
def test_mcp_servers_that_is_not_an_object_is_refused(helper, tmp_path, servers):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text('{"keep": true, "mcpServers": ' + servers + "}", encoding="utf-8")
    original = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns

    result = _install(helper, config_path)

    assert result["success"] is False
    assert "mcpServers" in result["error"]
    _assert_untouched(config_path, original, mtime_ns)


def test_unreadable_config_is_refused(helper, tmp_path):
    # A directory where the file should be cannot be read as a config.
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.mkdir()
    (config_path / "sentinel").write_text("keep")

    result = _install(helper, config_path)

    assert result["success"] is False
    assert str(config_path) in result["error"]
    assert "Nothing was written" in result["error"]
    assert (config_path / "sentinel").read_text() == "keep"
    assert _siblings(config_path) == [config_path.name]


def test_read_only_config_is_refused(helper, tmp_path):
    # os.replace ignores the file's own permissions, so they must be checked.
    # (os.access is patched: permission bits do not bind when tests run as root.)
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps(EXISTING_CONFIG), encoding="utf-8")
    original = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns

    with patch("advanced_vault.gui.mcp_setup.os.access", return_value=False):
        result = _install(helper, config_path)

    assert result["success"] is False
    assert str(config_path) in result["error"]
    assert "not writable" in result["error"]
    _assert_untouched(config_path, original, mtime_ns)


def test_existing_config_is_merged_with_backup_and_atomic_replace(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    original = json.dumps(EXISTING_CONFIG, indent=4).encode("utf-8")
    config_path.write_bytes(original)
    os.chmod(config_path, 0o640)

    with patch("advanced_vault.gui.mcp_setup.os.replace", wraps=os.replace) as replace_spy:
        result = _install(helper, config_path)

    assert result["success"] is True, result
    assert result["changed"] is True

    # Atomic: exactly one os.replace from a temp file in the same directory.
    replace_spy.assert_called_once()
    src, dst = (Path(str(a)) for a in replace_spy.call_args.args)
    assert Path(dst) == config_path
    assert src.parent == config_path.parent
    assert src != config_path
    assert not src.exists()

    # Backup: timestamped sibling holding the exact previous bytes.
    backups = _backups(config_path)
    assert len(backups) == 1
    assert result["backup_path"] == str(backups[0])
    assert backups[0].read_bytes() == original
    assert _siblings(config_path) == sorted([config_path.name, backups[0].name])

    # Merge: unrelated keys and servers preserved, legacy entry migrated.
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["globalShortcut"] == EXISTING_CONFIG["globalShortcut"]
    assert payload["preferences"] == EXISTING_CONFIG["preferences"]
    servers = payload["mcpServers"]
    assert servers["filesystem"] == EXISTING_CONFIG["mcpServers"]["filesystem"]
    assert servers["github"] == EXISTING_CONFIG["mcpServers"]["github"]
    assert "sheriff" not in servers
    assert servers["enclave"] == helper.generate_mcp_server_entry()
    assert set(servers) == {"filesystem", "github", "enclave"}

    # Format: UTF-8, stable 2-space indentation, trailing newline.
    text = config_path.read_text(encoding="utf-8")
    assert text == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    if sys.platform != "win32":
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o640


def test_existing_enclave_entry_is_updated_in_place(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"a": {"command": "a"}, "enclave": {"command": "stale"}, "z": {}}}),
        encoding="utf-8",
    )

    result = _install(helper, config_path)

    assert result["success"] is True
    servers = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]
    assert list(servers) == ["a", "enclave", "z"]
    assert servers["enclave"] == helper.generate_mcp_server_entry()
    assert len(_backups(config_path)) == 1


def test_non_ascii_values_survive_round_trip(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    existing = {"mcpServers": {"notes": {"command": "/Users/zoë/bin/notes", "args": ["日本語"]}}}
    config_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")

    assert _install(helper, config_path)["success"] is True

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["notes"] == existing["mcpServers"]["notes"]


def test_missing_file_and_directory_are_created(helper, tmp_path):
    config_path = tmp_path / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    assert not config_path.parent.exists()

    result = _install(helper, config_path)

    assert result["success"] is True, result
    assert result["backup_path"] is None
    assert json.loads(config_path.read_text(encoding="utf-8")) == helper.generate_mcp_config()
    assert config_path.read_text(encoding="utf-8").endswith("}\n")
    assert _siblings(config_path) == [config_path.name]


def test_missing_file_in_existing_directory_is_created(helper, tmp_path):
    config_path = tmp_path / "mcp.json"

    result = _install(helper, config_path)

    assert result["success"] is True
    assert result["backup_path"] is None
    assert json.loads(config_path.read_text(encoding="utf-8")) == helper.generate_mcp_config()


def test_second_run_is_idempotent(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps(EXISTING_CONFIG), encoding="utf-8")

    first = _install(helper, config_path)
    assert first["success"] is True and first["changed"] is True
    after_first = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns
    siblings = _siblings(config_path)

    with patch("advanced_vault.gui.mcp_setup.os.replace", wraps=os.replace) as replace_spy:
        second = _install(helper, config_path)

    assert second["success"] is True
    assert second["changed"] is False
    assert second["backup_path"] is None
    replace_spy.assert_not_called()
    assert config_path.read_bytes() == after_first
    assert config_path.stat().st_mtime_ns == mtime_ns
    assert _siblings(config_path) == siblings
    assert len(_backups(config_path)) == 1
    assert list(json.loads(after_first)["mcpServers"]).count("enclave") == 1


def test_second_run_after_creating_file_is_idempotent(helper, tmp_path):
    config_path = tmp_path / "new" / "claude_desktop_config.json"

    assert _install(helper, config_path)["changed"] is True
    second = _install(helper, config_path)

    assert second["success"] is True and second["changed"] is False
    assert _siblings(config_path) == [config_path.name]


def test_failed_replace_leaves_original_and_no_temp_file(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps(EXISTING_CONFIG), encoding="utf-8")
    original = config_path.read_bytes()

    with patch("advanced_vault.gui.mcp_setup.os.replace", side_effect=OSError("disk full")):
        result = _install(helper, config_path)

    assert result["success"] is False
    assert "disk full" in result["error"]
    assert config_path.read_bytes() == original
    leftovers = [
        name for name in _siblings(config_path) if name != config_path.name and not BACKUP_RE.match(name)
    ]
    assert leftovers == []


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32", reason="needs POSIX symlinks")
def test_symlinked_config_is_updated_through_the_link(helper, tmp_path):
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    real = dotfiles / "claude_desktop_config.json"
    real.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
    link_dir = tmp_path / "Claude"
    link_dir.mkdir()
    link = link_dir / "claude_desktop_config.json"
    link.symlink_to(real)

    result = _install(helper, link)

    assert result["success"] is True
    assert link.is_symlink()
    servers = json.loads(real.read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"other", "enclave"}


def test_write_config_backs_up_and_replaces_atomically(helper, tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text('{"keep": 1}', encoding="utf-8")

    with patch("advanced_vault.gui.mcp_setup.os.replace", wraps=os.replace) as replace_spy:
        assert helper.write_config({"mcpServers": {}}, config_path=config_path) is True

    replace_spy.assert_called_once()
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"mcpServers": {}}
    backups = _backups(config_path)
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == '{"keep": 1}'


def test_all_clients_reports_failure_when_a_detected_config_is_refused(tmp_path):
    helper = MCPSetupHelper(vault_path=str(tmp_path / "vault"))
    claude_path = tmp_path / "claude" / "claude_desktop_config.json"
    claude_path.parent.mkdir()
    claude_path.write_text("{not json", encoding="utf-8")
    cursor_path = tmp_path / "cursor" / "mcp.json"

    with patch.object(helper, "detect_claude_desktop", return_value=True), patch.object(
        helper, "detect_cursor", return_value=True
    ), patch.object(helper, "get_claude_desktop_config_path", return_value=claude_path), patch.object(
        helper, "get_cursor_config_path", return_value=cursor_path
    ):
        outcome = helper.auto_configure_all_clients()

    assert outcome["success"] is False
    assert outcome["configured_count"] == 1
    assert outcome["results"]["cursor"]["success"] is True
    assert str(claude_path) in outcome["results"]["claude"]["error"]
    assert claude_path.read_text(encoding="utf-8") == "{not json"


# ---------- CLI ----------


def _run_cli(tmp_path: Path, config_path: Path, *args: str):
    from advanced_vault.cli.main import cli

    with patch.object(MCPSetupHelper, "detect_claude_desktop", return_value=True), patch.object(
        MCPSetupHelper, "get_claude_desktop_config_path", return_value=config_path
    ):
        return CliRunner().invoke(cli, ["--vault-path", str(tmp_path / "vault"), "mcp", "install", *args])


def test_cli_install_refuses_malformed_config_with_nonzero_exit(tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text('{"mcpServers": {', encoding="utf-8")

    result = _run_cli(tmp_path, config_path)

    assert result.exit_code != 0
    assert str(config_path) in result.output
    assert "Nothing was written" in result.output
    assert config_path.read_text(encoding="utf-8") == '{"mcpServers": {'
    assert _siblings(config_path) == [config_path.name]


def test_cli_install_reports_backup_location(tmp_path):
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps(EXISTING_CONFIG), encoding="utf-8")

    result = _run_cli(tmp_path, config_path)

    assert result.exit_code == 0, result.output
    backups = _backups(config_path)
    assert len(backups) == 1
    assert str(backups[0]) in result.output


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_constants_are_refused(helper, tmp_path, constant):
    # Python's json accepts these, but Claude Desktop's JSON.parse does not.
    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir()
    config_path.write_text(f'{{"x": {constant}, "mcpServers": {{}}}}', encoding="utf-8")
    original = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns

    result = _install(helper, config_path)

    assert result["success"] is False
    assert "not valid JSON" in result["error"]
    _assert_untouched(config_path, original, mtime_ns)


def test_deeply_nested_config_is_refused_with_config_error(helper, tmp_path):
    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir()
    config_path.write_text('{"x": ' + "[" * 100_000 + "]" * 100_000 + "}", encoding="utf-8")
    original = config_path.read_bytes()
    mtime_ns = config_path.stat().st_mtime_ns

    result = _install(helper, config_path)

    assert result["success"] is False
    assert "Refusing to modify" in result["error"]
    _assert_untouched(config_path, original, mtime_ns)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_backup_is_created_with_the_config_mode_from_the_start(helper, tmp_path):
    # A 0600 config may hold other servers' tokens: its backup must never be
    # created with broader permissions, not even briefly before a chmod.
    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(EXISTING_CONFIG), encoding="utf-8")
    os.chmod(config_path, 0o600)
    original = config_path.read_bytes()

    real_open = os.open
    created_modes = []

    def spy_open(path, flags, mode=0o777, *args, **kwargs):
        if BACKUP_RE.match(Path(path).name):
            created_modes.append((flags, mode))
        return real_open(path, flags, mode, *args, **kwargs)

    with patch("os.open", side_effect=spy_open):
        result = _install(helper, config_path)

    assert result["success"] is True
    backup = Path(result["backup_path"])
    assert backup.read_bytes() == original
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert len(created_modes) == 1
    flags, mode = created_modes[0]
    assert flags & os.O_EXCL and flags & os.O_CREAT
    assert mode == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_symlink_planted_at_backup_name_is_not_followed(helper, tmp_path):
    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(EXISTING_CONFIG), encoding="utf-8")
    victim = tmp_path / "victim.txt"
    stamp = "20260101-000000"
    planted = config_path.with_name(f"{config_path.name}.bak-{stamp}")
    planted.symlink_to(victim)  # dangling: exists() is False, open() would follow it

    with patch("advanced_vault.gui.mcp_setup.time.strftime", return_value=stamp):
        result = _install(helper, config_path)

    assert result["success"] is True
    assert not victim.exists()
    assert planted.is_symlink()
    assert Path(result["backup_path"]).name == f"{config_path.name}.bak-{stamp}-1"
