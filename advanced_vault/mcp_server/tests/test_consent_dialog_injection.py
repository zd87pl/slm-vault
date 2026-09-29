"""
Regression tests: consent dialogs must never run agent-controlled text as code.

The dialog shows a preview of the calling agent's tool arguments (and the tool
name), which an external LLM writes and prompt injection can steer. The Linux
dialog used to run ``bash -c`` with that text interpolated, so a query such as
``$(touch X)`` executed before the user decided. These tests pin the fix: both
dialogs are started from an argv list, never through a shell, and untrusted
text never becomes part of AppleScript source.
"""

import os
import shlex
import subprocess

import pytest

from advanced_vault.mcp_server import consent
from advanced_vault.mcp_server.consent import ConsentDecision, ConsentManager

# Payloads that break out of a shell double-quoted string or an AppleScript
# string literal if either is ever built by interpolation again.
RAW_PAYLOADS = [
    "$(touch X)",
    "`touch X`",
    '"; do shell script "touch X"',
    '\\"; do shell script \\"touch X\\" -- \\',
    "-e do shell script \"touch X\"",
    "<b>markup</b> & 'quotes'",
]

# Payloads the readability sanitizer leaves intact, so they must reach the
# dialog unchanged through the public path.
SANITIZER_PRESERVED_PAYLOADS = [
    "$(touch X)",
    "`touch X`",
    "x; touch X && id | cat",
]

needs_posix_exec = pytest.mark.skipif(
    os.name == "nt", reason="uses a fake zenity shell script on PATH"
)


@pytest.fixture
def manager(tmp_path):
    return ConsentManager(vault_path=str(tmp_path / "vault"))


@pytest.fixture
def run_calls(monkeypatch):
    """Replace subprocess.run; returns the recorded calls and a setter for the result."""
    calls = []
    state = {"returncode": 1, "stdout": "", "raises": None}

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        if state["raises"] is not None:
            raise state["raises"]
        return subprocess.CompletedProcess(args[0], state["returncode"], state["stdout"], "")

    monkeypatch.setattr(consent.subprocess, "run", fake_run)
    return calls, state


def _set_platform(monkeypatch, name):
    monkeypatch.setattr(consent.platform, "system", lambda: name)


def _assert_no_shell(args, kwargs, program):
    argv = args[0]
    assert isinstance(argv, list), "dialog must be started from an argv list"
    assert all(isinstance(a, str) for a in argv)
    assert argv[0] == program
    assert not kwargs.get("shell", False)
    assert "-c" not in argv
    assert not any(os.path.basename(a) in ("bash", "sh", "zsh") for a in argv)


def _osascript_parts(argv):
    """Split an osascript argv into (script source lines, run-handler arguments)."""
    assert argv[0] == "osascript"
    separator = argv.index("--")
    options = argv[1:separator]
    assert options[0::2] == ["-e"] * (len(options) // 2)
    assert len(options) % 2 == 0
    return options[1::2], argv[separator + 1:]


# ---------------------------------------------------------------------------
# argv construction with subprocess.run mocked
# ---------------------------------------------------------------------------


class TestLinuxArgv:
    @pytest.mark.parametrize("payload", SANITIZER_PRESERVED_PAYLOADS)
    def test_query_preview_reaches_zenity_verbatim_without_shell(
        self, monkeypatch, manager, run_calls, payload
    ):
        _set_platform(monkeypatch, "Linux")
        calls, _ = run_calls

        decision = manager._show_notification("Claude Desktop", "vault_recall", payload)

        assert decision == ConsentDecision.DENY
        assert len(calls) == 1
        args, kwargs = calls[0]
        _assert_no_shell(args, kwargs, "zenity")
        argv = args[0]
        assert "--no-markup" in argv
        holders = [a for a in argv if payload in a]
        assert len(holders) == 1 and holders[0].startswith("--text=")

    @pytest.mark.parametrize("payload", SANITIZER_PRESERVED_PAYLOADS)
    def test_tool_name_reaches_zenity_verbatim_without_shell(
        self, monkeypatch, manager, run_calls, payload
    ):
        _set_platform(monkeypatch, "Linux")
        calls, _ = run_calls

        manager._show_notification("Claude Desktop", payload, "")

        args, kwargs = calls[0]
        _assert_no_shell(args, kwargs, "zenity")
        holders = [a for a in args[0] if payload in a]
        assert len(holders) == 1 and holders[0].startswith("--text=")

    @pytest.mark.parametrize("payload", RAW_PAYLOADS)
    def test_argv_does_not_depend_on_sanitization(self, payload):
        argv = consent._zenity_argv(title=payload, message=payload)
        baseline = consent._zenity_argv(title="T", message="M")

        # The text lands whole in its own --title=/--text= element; every
        # other element is constant.
        expected = [
            f"--title={payload}" if a == "--title=T"
            else f"--text={payload}\n\nChoose an option:" if a.startswith("--text=M")
            else a
            for a in baseline
        ]
        assert argv == expected

    def test_keeps_buttons_timeout_and_disables_markup(self):
        argv = consent._zenity_argv(title="t", message="m")

        assert argv[:2] == ["zenity", "--question"]
        assert "--no-markup" in argv
        assert [a for a in argv if a.startswith("--extra-button=")] == [
            "--extra-button=Allow Once",
            "--extra-button=Always Allow",
            "--extra-button=Deny Always",
        ]
        assert "--ok-label=Deny" in argv
        assert "--timeout=30" in argv

    def test_exit_code_overrides_are_not_inherited(self, monkeypatch, manager, run_calls):
        # zenity lets these variables remap its exit codes; the decision parser
        # relies on the documented defaults.
        _set_platform(monkeypatch, "Linux")
        monkeypatch.setenv("ZENITY_EXTRA", "0")
        monkeypatch.setenv("DIALOG_OK", "1")
        monkeypatch.setenv("CONSENT_TEST_KEEP", "yes")
        calls, _ = run_calls

        manager._show_notification("Claude Desktop", "vault_recall", "q")

        env = calls[0][1]["env"]
        assert "ZENITY_EXTRA" not in env and "DIALOG_OK" not in env
        assert env["CONSENT_TEST_KEEP"] == "yes"


class TestMacArgv:
    @pytest.mark.parametrize("payload", SANITIZER_PRESERVED_PAYLOADS)
    def test_query_preview_is_argv_data_not_script_source(
        self, monkeypatch, manager, run_calls, payload
    ):
        _set_platform(monkeypatch, "Darwin")
        calls, state = run_calls
        state["returncode"], state["stdout"] = 0, "Deny\n"

        decision = manager._show_notification("Claude Desktop", "vault_recall", payload)

        assert decision == ConsentDecision.DENY
        args, kwargs = calls[0]
        _assert_no_shell(args, kwargs, "osascript")
        script, handler_args = _osascript_parts(args[0])
        assert tuple(script) == consent._OSASCRIPT_DIALOG_SCRIPT
        assert not any(payload in line for line in script)
        assert len(handler_args) == 2
        assert payload in handler_args[0]

    @pytest.mark.parametrize("payload", RAW_PAYLOADS)
    def test_script_source_is_constant_for_any_text(self, payload):
        script, handler_args = _osascript_parts(
            consent._osascript_argv(title=payload, message=payload)
        )

        assert tuple(script) == consent._OSASCRIPT_DIALOG_SCRIPT
        assert not any(payload in line for line in script)
        assert handler_args == [payload, payload]

    def test_script_reads_text_from_argv_and_keeps_buttons(self):
        source = "\n".join(consent._OSASCRIPT_DIALOG_SCRIPT)

        assert source.startswith("on run argv")
        assert source.endswith("end run")
        assert "(item 1 of argv)" in source and "(item 2 of argv)" in source
        assert 'buttons {"Allow Once", "Always Allow", "Deny"}' in source
        assert "do shell script" not in source

    def test_leading_dash_text_cannot_become_an_osascript_option(self):
        argv = consent._osascript_argv(title="-e", message="-l JavaScript")

        assert argv[-3:] == ["--", "-l JavaScript", "-e"]


# ---------------------------------------------------------------------------
# decision parsing for every dialog outcome
# ---------------------------------------------------------------------------


ZENITY_OUTCOMES = [
    # Documented zenity behaviour.
    pytest.param(1, "Allow Once\n", ConsentDecision.ALLOW_ONCE, id="extra-allow-once"),
    pytest.param(1, "Always Allow\n", ConsentDecision.ALLOW_ALWAYS, id="extra-always-allow"),
    pytest.param(1, "Deny Always\n", ConsentDecision.DENY_ALWAYS, id="extra-deny-always"),
    pytest.param(0, "", ConsentDecision.DENY, id="ok-button-labelled-deny"),
    pytest.param(1, "", ConsentDecision.DENY, id="cancel-or-window-closed"),
    pytest.param(5, "", ConsentDecision.DENY, id="timeout"),
    pytest.param(255, "", ConsentDecision.DENY, id="zenity-error"),
    pytest.param(-9, "", ConsentDecision.DENY, id="killed-by-signal"),
    # Anything unexpected fails closed.
    pytest.param(0, "Allow Once\n", ConsentDecision.DENY, id="label-with-ok-exit"),
    pytest.param(5, "Always Allow\n", ConsentDecision.DENY, id="label-with-timeout-exit"),
    pytest.param(1, "allow once\n", ConsentDecision.DENY, id="wrong-case"),
    pytest.param(1, "Allow Once please\n", ConsentDecision.DENY, id="label-prefix"),
    pytest.param(1, "Always Allow\nAllow Once\n", ConsentDecision.DENY, id="two-labels"),
    pytest.param(1, "Deny\n", ConsentDecision.DENY, id="ok-label-on-stdout"),
    pytest.param(1, "127\n", ConsentDecision.DENY, id="old-echo-status"),
    pytest.param(1, None, ConsentDecision.DENY, id="no-stdout"),
]


class TestZenityDecision:
    @pytest.mark.parametrize("returncode, stdout, expected", ZENITY_OUTCOMES)
    def test_parse(self, returncode, stdout, expected):
        assert consent._parse_zenity_result(returncode, stdout) == expected

    @pytest.mark.parametrize("returncode, stdout, expected", ZENITY_OUTCOMES)
    def test_show_notification(
        self, monkeypatch, manager, run_calls, returncode, stdout, expected
    ):
        _set_platform(monkeypatch, "Linux")
        _, state = run_calls
        state["returncode"], state["stdout"] = returncode, stdout

        assert manager._show_notification("Claude Desktop", "vault_recall", "q") == expected

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(FileNotFoundError(2, "No such file", "zenity"), id="zenity-missing"),
            pytest.param(subprocess.TimeoutExpired(["zenity"], 35), id="subprocess-timeout"),
            pytest.param(ValueError("embedded null byte"), id="bad-argv"),
            pytest.param(PermissionError(13, "Permission denied"), id="not-executable"),
            pytest.param(OSError("boom"), id="os-error"),
        ],
    )
    def test_errors_deny(self, monkeypatch, manager, run_calls, error):
        _set_platform(monkeypatch, "Linux")
        _, state = run_calls
        state["raises"] = error

        assert (
            manager._show_notification("Claude Desktop", "vault_recall", "q")
            == ConsentDecision.DENY
        )


class TestOsascriptDecision:
    @pytest.mark.parametrize(
        "returncode, stdout, expected",
        [
            (0, "Allow Once\n", ConsentDecision.ALLOW_ONCE),
            (0, "Always Allow\n", ConsentDecision.ALLOW_ALWAYS),
            (0, "Deny\n", ConsentDecision.DENY),
            (1, "", ConsentDecision.DENY),  # e.g. -128 user cancelled / no UI allowed
            (1, "Allow Once\n", ConsentDecision.DENY),
            (0, "", ConsentDecision.DENY),
            (0, "button returned:Allow Once, extra\n", ConsentDecision.DENY),
            (0, None, ConsentDecision.DENY),
        ],
    )
    def test_show_notification(
        self, monkeypatch, manager, run_calls, returncode, stdout, expected
    ):
        _set_platform(monkeypatch, "Darwin")
        _, state = run_calls
        state["returncode"], state["stdout"] = returncode, stdout

        assert manager._show_notification("Claude Desktop", "vault_recall", "q") == expected

    @pytest.mark.parametrize(
        "error",
        [
            FileNotFoundError(2, "No such file", "osascript"),
            subprocess.TimeoutExpired(["osascript"], 30),
            OSError("boom"),
        ],
    )
    def test_errors_deny(self, monkeypatch, manager, run_calls, error):
        _set_platform(monkeypatch, "Darwin")
        _, state = run_calls
        state["raises"] = error

        assert (
            manager._show_notification("Claude Desktop", "vault_recall", "q")
            == ConsentDecision.DENY
        )


def test_request_consent_denies_and_stores_nothing_on_dialog_failure(
    monkeypatch, manager, run_calls
):
    _set_platform(monkeypatch, "Linux")
    _, state = run_calls
    state["raises"] = FileNotFoundError(2, "No such file", "zenity")

    assert manager.request_consent("vault_recall", "q", app_identifier="claude-desktop") is False
    assert manager.get_permissions() == {}


# ---------------------------------------------------------------------------
# end to end: the real dialog code against a fake zenity on PATH
# ---------------------------------------------------------------------------


def _install_fake_zenity(bin_dir, argv_log, stdout="", exit_code=1):
    """Write a zenity stand-in that logs its argv (NUL-separated) and exits."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "zenity"
    lines = ["#!/bin/sh", f"printf '%s\\0' \"$@\" > {shlex.quote(str(argv_log))}"]
    if stdout:
        lines.append(f"printf '%s\\n' {shlex.quote(stdout)}")
    lines.append(f"exit {exit_code}")
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)


@needs_posix_exec
class TestFakeZenityEndToEnd:
    @pytest.fixture
    def env(self, monkeypatch, tmp_path):
        _set_platform(monkeypatch, "Linux")
        # The old code ran bash in the server's working directory, so relative
        # payloads keep the injected command inside the preview's 50 characters.
        workdir = tmp_path / "cwd"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        bin_dir = tmp_path / "bin"
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        return workdir, bin_dir, tmp_path / "zenity-argv"

    @pytest.mark.parametrize(
        "tool_name, query",
        [
            ("vault_recall", "$(touch PWNED)"),
            ("agent_query", "`touch PWNED`"),
            ("$(touch PWNED)", ""),
        ],
    )
    def test_injected_command_does_not_run_and_access_is_denied(
        self, env, manager, tool_name, query
    ):
        workdir, bin_dir, argv_log = env
        _install_fake_zenity(bin_dir, argv_log, stdout="", exit_code=1)

        decision = manager._show_notification("Claude Desktop", tool_name, query)
        granted = manager.request_consent(tool_name, query, app_identifier="claude-desktop")

        assert decision == ConsentDecision.DENY
        assert granted is False
        assert not (workdir / "PWNED").exists()
        assert manager.get_permissions() == {}

        logged = argv_log.read_bytes().split(b"\0")[:-1]
        payload = (query or tool_name).encode()
        holders = [a for a in logged if payload in a]
        assert len(holders) == 1 and holders[0].startswith(b"--text=")
        assert b"--no-markup" in logged

    @pytest.mark.parametrize(
        "stdout, exit_code, expected",
        [
            ("Allow Once", 1, ConsentDecision.ALLOW_ONCE),
            ("Always Allow", 1, ConsentDecision.ALLOW_ALWAYS),
            ("Deny Always", 1, ConsentDecision.DENY_ALWAYS),
            ("", 0, ConsentDecision.DENY),
            ("", 1, ConsentDecision.DENY),
            ("", 5, ConsentDecision.DENY),
            ("Allow Once", 0, ConsentDecision.DENY),
        ],
    )
    def test_real_exec_decisions(self, env, manager, stdout, exit_code, expected):
        workdir, bin_dir, argv_log = env
        _install_fake_zenity(bin_dir, argv_log, stdout=stdout, exit_code=exit_code)

        decision = manager._show_notification("Claude Desktop", "vault_recall", "$(touch PWNED)")

        assert decision == expected
        assert not (workdir / "PWNED").exists()

    def test_missing_zenity_denies(self, env, monkeypatch, manager):
        _, bin_dir, _ = env
        bin_dir.mkdir()
        monkeypatch.setenv("PATH", str(bin_dir))

        assert (
            manager._show_notification("Claude Desktop", "vault_recall", "q")
            == ConsentDecision.DENY
        )
        assert manager.request_consent("vault_recall", "q", app_identifier="x") is False
