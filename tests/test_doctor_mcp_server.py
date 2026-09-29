"""`enclave doctor` / `enclave mcp status` start the MCP server like a client would."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from advanced_vault.cli import doctor
from advanced_vault.cli.doctor import FAIL, PASS, CheckResult, check_mcp_server
from advanced_vault.cli.main import cli
from advanced_vault.gui.mcp_setup import MCPSetupHelper

FIX = 'pip install "mcp>=1.0.0,<2"'


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Keep the server's ~/.enclave writes and the probe's temp dirs inside tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    probe_tmp = tmp_path / "probe-tmp"
    probe_tmp.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(tempfile, "tempdir", str(probe_tmp))
    return home, probe_tmp


def _script(tmp_path: Path, name: str, body: str) -> dict:
    path = tmp_path / name
    path.write_text(body)
    return {"command": sys.executable, "args": [str(path)], "env": {}}


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # also succeeds for an unreaped zombie
    except ProcessLookupError:
        return False
    return True


def test_real_server_passes_with_tool_count(isolated_home):
    home, probe_tmp = isolated_home

    result = check_mcp_server(timeout=120)

    assert result.status == PASS, result.detail
    match = re.search(r"lists (\d+) tools", result.detail)
    assert match and int(match.group(1)) > 0
    assert not (home / ".vault").exists()  # the user's default vault is never touched
    assert list(probe_tmp.iterdir()) == []  # throwaway vault removed


def test_server_command_comes_from_mcp_client_config(monkeypatch, isolated_home, tmp_path):
    seen = {}

    def fake_list_tools(entry, cwd, errlog, timeout):
        seen.update(entry=entry, cwd=cwd)
        return 3

    monkeypatch.setattr(doctor, "_list_mcp_tools", fake_list_tools)

    result = check_mcp_server()

    assert result.status == PASS and "3 tools" in result.detail
    vault = seen["entry"]["env"]["VAULT_PATH"]
    expected = MCPSetupHelper(vault_path=vault).generate_mcp_server_entry()
    assert seen["entry"] == expected
    assert Path(vault).parent == Path(seen["cwd"])  # throwaway vault in the probe's temp dir


@pytest.mark.parametrize(
    "tools_reply, status, expected",
    [
        ({"result": {"tools": [{"name": "a"}, {"name": "b"}]}}, PASS, "lists 2 tools"),
        ({"error": {"code": -32601, "message": "Method not found"}}, FAIL, "`tools/list` failed: Method not found"),
    ],
)
def test_handshake_skips_noise_and_reports_the_reply(isolated_home, tmp_path, tools_reply, status, expected):
    entry = _script(
        tmp_path,
        "fake_server.py",
        "import json, sys\n"
        "def send(message):\n"
        "    print(json.dumps({'jsonrpc': '2.0', **message}), flush=True)\n"
        "for raw in sys.stdin:\n"
        "    request = json.loads(raw)\n"
        "    if request.get('method') == 'initialize':\n"
        "        print('stray output that is not JSON-RPC', flush=True)\n"
        "        send({'method': 'notifications/message', 'params': {'level': 'info', 'data': 'hi'}})\n"
        "        send({'id': request['id'], 'result': {'protocolVersion': '2024-11-05', 'capabilities': {},"
        " 'serverInfo': {'name': 'fake', 'version': '0'}}})\n"
        "    elif request.get('method') == 'tools/list':\n"
        f"        send({{'id': request['id'], **{tools_reply!r}}})\n",
    )

    result = check_mcp_server(timeout=60, server_entry=entry)

    assert result.status == status
    assert expected in result.detail


def test_server_that_exits_fails_with_stderr_tail(isolated_home, tmp_path):
    entry = _script(
        tmp_path,
        "crash.py",
        "import sys\n"
        "sys.stderr.write('Traceback (most recent call last):\\n')\n"
        "sys.stderr.write(\"AttributeError: 'Server' object has no attribute 'list_tools'\\n\")\n"
        "sys.exit(1)\n",
    )

    result = check_mcp_server(timeout=60, server_entry=entry)

    assert result.status == FAIL
    assert "exited with code 1" in result.detail
    assert "'Server' object has no attribute 'list_tools'" in result.detail
    assert FIX in result.fix


def test_unrelated_crash_gets_a_generic_fix(isolated_home, tmp_path):
    entry = _script(
        tmp_path,
        "crash_other.py",
        "import sys\n"
        "sys.stderr.write(\"ModuleNotFoundError: No module named 'hnswlib'\\n\")\n"
        "sys.exit(1)\n",
    )

    result = check_mcp_server(timeout=60, server_entry=entry)

    assert result.status == FAIL
    assert "No module named 'hnswlib'" in result.detail
    assert FIX not in result.fix  # the SDK pin would not help here
    assert "python -m advanced_vault.mcp_server" in result.fix


def test_flooding_server_still_times_out(isolated_home, tmp_path):
    entry = _script(
        tmp_path,
        "flood.py",
        "import sys\n"
        "while True:\n"
        "    sys.stdout.write('not json-rpc\\n')\n"
        "    sys.stdout.flush()\n",
    )

    started = time.monotonic()
    result = check_mcp_server(timeout=2, server_entry=entry)

    assert result.status == FAIL
    assert "no answer to `initialize` within 2s" in result.detail
    assert time.monotonic() - started < 2 + 10


@pytest.mark.skipif(sys.platform == "win32", reason="probes the pid with os.kill(pid, 0)")
def test_hanging_server_times_out_and_is_killed(isolated_home, tmp_path):
    pid_file = tmp_path / "server.pid"
    entry = _script(
        tmp_path,
        "hang.py",
        "import os, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)  # force the SIGKILL fallback\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "sys.stderr.write('loading models...\\n')\n"
        "sys.stderr.flush()\n"
        "while True:\n"
        "    time.sleep(1)\n",
    )

    started = time.monotonic()
    result = check_mcp_server(timeout=2, server_entry=entry)
    elapsed = time.monotonic() - started

    assert result.status == FAIL
    assert "no answer to `initialize` within 2s" in result.detail
    assert "loading models..." in result.detail
    assert elapsed < 2 + 15
    assert not _process_exists(int(pid_file.read_text()))  # killed and reaped


def test_missing_server_command_fails(isolated_home, tmp_path):
    entry = {"command": str(tmp_path / "no-such-python"), "args": [], "env": {}}

    result = check_mcp_server(timeout=10, server_entry=entry)

    assert result.status == FAIL
    assert "could not launch" in result.detail


def test_mcp_2_install_fails_with_the_fix(isolated_home, tmp_path):
    # Reproduces a fresh install that resolved mcp 2.x: metadata on PYTHONPATH
    # shadows the real SDK, so the spawned server sees mcp 2.2.0.
    site = tmp_path / "fake-site"
    info = site / "mcp-2.2.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: mcp\nVersion: 2.2.0\n")
    entry = MCPSetupHelper(vault_path=str(tmp_path / "vault")).generate_mcp_server_entry()
    entry["env"]["PYTHONPATH"] = os.pathsep.join([str(site), entry["env"]["PYTHONPATH"]])

    result = check_mcp_server(timeout=120, server_entry=entry)

    assert result.status == FAIL
    assert "mcp 2.2.0 is installed" in result.detail
    assert "Traceback" not in result.detail
    assert FIX in result.fix


def _failing_check(*_args, **_kwargs) -> CheckResult:
    return CheckResult("MCP server", FAIL, "server exited with code 1", doctor._MCP_SERVER_FIX)


def test_doctor_is_not_ready_when_mcp_server_fails(monkeypatch, isolated_home, tmp_path):
    monkeypatch.setattr(doctor, "check_mcp_server", _failing_check)

    result = CliRunner().invoke(cli, ["--vault-path", str(tmp_path / "vault"), "doctor"])

    assert result.exit_code == 1
    assert "❌ MCP server: server exited with code 1" in result.output
    assert FIX in result.output
    assert "Ready to go" not in result.output
    assert "Everything looks great" not in result.output


def test_mcp_status_reports_the_same_check(monkeypatch, isolated_home, tmp_path):
    monkeypatch.setattr(doctor, "check_mcp_server", _failing_check)

    result = CliRunner().invoke(cli, ["--vault-path", str(tmp_path / "vault"), "mcp", "status"])

    assert result.exit_code == 0, result.output
    assert "MCP server self-test: ❌ server exited with code 1" in result.output
    assert FIX in result.output
