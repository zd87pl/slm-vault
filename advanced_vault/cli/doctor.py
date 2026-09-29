"""
Environment doctor for Enclave.

Checks the local machine for everything the beta setup needs and prints
actionable fixes. Designed to run with only core dependencies installed —
optional packages are probed, never imported unconditionally.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from advanced_vault.enclave_control.config import (
    SECRETS_TOOLS,
    parse_policy_document,
    upgrade_legacy_default,
)
from advanced_vault.enclave_control.models import AgentPolicy
from advanced_vault.enclave_control.runtime import resolve_agent_policy


PASS = "ok"
WARN = "warn"
FAIL = "fail"

_ICONS = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    fix: str = ""


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str, fix: str = "") -> None:
        self.checks.append(CheckResult(name, status, detail, fix))

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == WARN]

    def to_dict(self) -> dict:
        return {
            "checks": [c.__dict__ for c in self.checks],
            "failures": len(self.failures),
            "warnings": len(self.warnings),
        }


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _total_ram_gb() -> float | None:
    try:
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
    except (OSError, ValueError):
        pass
    if platform.system() == "Darwin":
        import subprocess

        try:
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0:
                return int(out.stdout.strip()) / 1024**3
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return None


# --- MCP server start-up check ---

# Seconds for start-up plus the handshake; stopping the server can add up to ~7 s.
MCP_SERVER_TIMEOUT = 25.0

# Besides a server's configured "env", an MCP client passes through only these
# variables (the default of the official mcp SDK's stdio client).
_CLIENT_INHERITED_ENV = (
    (
        "APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH", "PATHEXT",
        "PROCESSOR_ARCHITECTURE", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "USERNAME", "USERPROFILE",
    )
    if sys.platform == "win32"
    else ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
)
_STDERR_TAIL_LINES = 8
_MCP_SERVER_FIX = 'Run `pip install "mcp>=1.0.0,<2"` (or re-run ./setup.sh), then `enclave doctor` again'
_MCP_SERVER_GENERIC_FIX = (
    "Run `python -m advanced_vault.mcp_server` to see the server's full error "
    "(Ctrl-C to stop), fix it, then `enclave doctor` again"
)
# stderr text that means the installed MCP SDK is the problem: the entry point's
# own guard message, or the 1.x API missing under an unguarded start.
_MCP_SDK_FAILURE_MARKERS = ("enclave-mcp: mcp ", "has no attribute 'list_tools'")


class _MCPProbeError(Exception):
    """The server did not complete the MCP handshake."""


def _pump_lines(stream, lines: queue.Queue) -> None:
    try:
        for line in iter(stream.readline, b""):
            lines.put(line)
    except (OSError, ValueError):
        pass
    finally:
        lines.put(None)  # EOF: the server closed stdout


def _send_message(proc: subprocess.Popen, message: dict) -> None:
    try:
        proc.stdin.write(json.dumps(message).encode("utf-8") + b"\n")
        proc.stdin.flush()
    except OSError:
        pass  # the server is gone; waiting for its reply reports how it exited


def _await_reply(
    proc: subprocess.Popen, lines: queue.Queue, request_id: int, method: str,
    deadline: float, timeout: float,
):
    """Return the result of request ``request_id``, skipping anything else the server sends."""
    while True:
        # Checked on every line, so a server flooding stdout cannot outlast the deadline
        if time.monotonic() >= deadline:
            raise _MCPProbeError(f"no answer to `{method}` within {timeout:g}s")
        try:
            line = lines.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            raise _MCPProbeError(f"no answer to `{method}` within {timeout:g}s") from None
        if line is None:
            try:
                code = proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise _MCPProbeError(f"server closed stdout before answering `{method}`") from None
            raise _MCPProbeError(f"server exited with code {code} before answering `{method}`")
        try:
            message = json.loads(line)
        except ValueError:
            continue  # not JSON-RPC; MCP clients skip such lines as well
        if not isinstance(message, dict) or "method" in message or message.get("id") != request_id:
            continue  # a notification (e.g. a log message) or request, not our reply
        if "error" in message:
            error = message["error"]
            reason = error.get("message", error) if isinstance(error, dict) else error
            raise _MCPProbeError(f"`{method}` failed: {reason}")
        return message.get("result")


def _stop_server(proc: subprocess.Popen) -> None:
    """Shut down like an MCP client: close stdin, then SIGTERM, then SIGKILL."""
    try:
        proc.stdin.close()
    except OSError:
        pass
    for escalate in (None, proc.terminate, proc.kill):
        if escalate is not None:
            escalate()
        try:
            proc.wait(timeout=1)
            return
        except subprocess.TimeoutExpired:
            continue


def _list_mcp_tools(entry: dict, cwd: str, errlog, timeout: float) -> int:
    """Launch an MCP client config entry, run initialize + tools/list, count the tools.

    A minimal newline-delimited JSON-RPC client instead of the mcp SDK's, so the
    check works with any SDK version, including a broken one it is diagnosing.
    The server is always stopped before this returns.
    """
    deadline = time.monotonic() + timeout
    env = {key: os.environ[key] for key in _CLIENT_INHERITED_ENV if key in os.environ}
    env.update(entry.get("env") or {})
    try:
        proc = subprocess.Popen(
            [entry["command"], *entry.get("args", [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errlog,
            env=env,
            cwd=cwd,
        )
    except OSError as exc:
        raise _MCPProbeError(f"could not launch `{entry['command']}`: {exc}") from exc

    lines: queue.Queue = queue.Queue()
    reader = threading.Thread(target=_pump_lines, args=(proc.stdout, lines), daemon=True)
    try:
        reader.start()
        _send_message(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",  # the first revision: every 1.x server accepts it
                "capabilities": {},
                "clientInfo": {"name": "enclave-doctor", "version": "1"},
            },
        })
        _await_reply(proc, lines, 1, "initialize", deadline, timeout)
        _send_message(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send_message(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        result = _await_reply(proc, lines, 2, "tools/list", deadline, timeout)
    finally:
        _stop_server(proc)
        if reader.ident is not None:
            reader.join(timeout=2)
        if not reader.is_alive():
            proc.stdout.close()

    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list):
        raise _MCPProbeError("`tools/list` did not return a tool list")
    return len(tools)


def _stderr_tail(path: str) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 16384))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    tail = [line.rstrip() for line in text.splitlines() if line.strip()][-_STDERR_TAIL_LINES:]
    return "".join(f"\n   │ {line}" for line in tail)


def check_mcp_server(
    timeout: float = MCP_SERVER_TIMEOUT, server_entry: dict | None = None
) -> CheckResult:
    """Start the MCP server exactly as an MCP client would and list its tools.

    The command comes from the code that writes the client config for
    `enclave mcp install` / `enclave mcp config`, but with VAULT_PATH pointing at
    a throwaway directory so the user's real vault is never touched.
    ``server_entry`` replaces that config entry (used by tests).
    """
    name = "MCP server"
    try:
        with tempfile.TemporaryDirectory(prefix="enclave-doctor-", ignore_cleanup_errors=True) as tmp:
            if server_entry is None:
                from advanced_vault.gui.mcp_setup import MCPSetupHelper

                helper = MCPSetupHelper(vault_path=os.path.join(tmp, "vault"))
                server_entry = helper.generate_mcp_server_entry()
            stderr_path = os.path.join(tmp, "server-stderr.log")
            try:
                with open(stderr_path, "wb") as errlog:
                    tool_count = _list_mcp_tools(server_entry, tmp, errlog, timeout)
            except _MCPProbeError as exc:
                tail = _stderr_tail(stderr_path)
                detail = f"{exc}; its stderr ends with:{tail}" if tail else str(exc)
                sdk_problem = any(marker in tail for marker in _MCP_SDK_FAILURE_MARKERS)
                fix = _MCP_SERVER_FIX if sdk_problem else _MCP_SERVER_GENERIC_FIX
                return CheckResult(name, FAIL, detail, fix)
    except OSError as exc:
        return CheckResult(
            name, FAIL, f"could not run the start-up check: {exc}", _MCP_SERVER_GENERIC_FIX
        )
    return CheckResult(name, PASS, f"starts over stdio and lists {tool_count} tools")


# --- Secrets tools policy check ---

POLICY_PATH = "~/.enclave/policies.toml"
_SECRETS_CHECK = "Secrets tools"
_DOCUMENT_TOOLS = '"agent_*", "query_knowledge", "agent_status"'
_OPT_IN_HINT = (
    " To let one app use the secrets tools, add them to that app's own entry instead"
    ' (README: "Letting one app use the secrets tools"). Then fully quit and reopen your AI app.'
)
_TABLE_HEADER = re.compile(r"\s*\[\[?\s*[\w.\"' -]+?\s*\]\]?\s*(?:#.*)?")
_AGENTS_HEADER = re.compile(r"\s*\[\[\s*agents\s*\]\]\s*(?:#.*)?")
_AGENT_ID_KEY = re.compile(r"\s*agent_id\s*=")
_ALLOWED_TOOLS_KEY = re.compile(r"\s*allowed_tools\s*=")


def _agent_entry_lines(text: str, agent_id: str) -> tuple[int, int | None, bool] | None:
    """Locate the [[agents]] entry the policy loader uses for ``agent_id``.

    Returns (line naming the entry, allowed_tools line or None, whether the
    entry has allowed_tools), 1-based, for the last entry with that agent_id
    (the loader keeps the last one), or None if no [[agents]] table has it.
    """
    lines = text.split("\n")
    headers = [i for i, line in enumerate(lines) if _TABLE_HEADER.fullmatch(line)]
    found = None
    for n, start in enumerate(headers):
        if not _AGENTS_HEADER.fullmatch(lines[start]):
            continue
        end = headers[n + 1] if n + 1 < len(headers) else len(lines)
        body = lines[start + 1:end]
        try:
            entry = tomllib.loads("\n".join(body))
        except tomllib.TOMLDecodeError:
            continue
        if str(entry.get("agent_id", "default")) != agent_id:
            continue
        # body[i] is line start + 2 + i, counting from 1.
        id_line = next((start + 2 + i for i, line in enumerate(body) if _AGENT_ID_KEY.match(line)), start + 1)
        tools_line = next((start + 2 + i for i, line in enumerate(body) if _ALLOWED_TOOLS_KEY.match(line)), None)
        found = (id_line, tools_line, "allowed_tools" in entry)
    return found


def _secrets_policy_fix(text: str, path: Path, policy: AgentPolicy) -> str:
    """Exact edit that takes the secrets tools away from unidentified apps."""
    entry = f'the [[agents]] entry with agent_id = "{policy.agent_id}"'
    culprits = [p for p in policy.allowed_tools if p == "*" or any(fnmatch(t, p) for t in SECRETS_TOOLS)]
    remove = ", ".join(json.dumps(p) for p in culprits)
    add_back = ""
    if any(p == "*" or fnmatch(t, p) for p in culprits for t in ("agent_query", "query_knowledge")):
        add_back = f", then add back the document tools, e.g. {_DOCUMENT_TOOLS}"

    located = _agent_entry_lines(text, policy.agent_id)
    raw_agents = tomllib.loads(text).get("agents", [])
    has_entry = any(str(raw.get("agent_id", "default")) == policy.agent_id for raw in raw_agents)
    if not has_entry:
        fix = (
            f'{path} has no [[agents]] entry with agent_id = "default", so apps Enclave cannot '
            f'identify may call every tool: add one with allowed_modules = ["vault"] and '
            f"allowed_tools = [{_DOCUMENT_TOOLS}]."
        )
    elif located is None:
        fix = f"In {path}, remove {remove} from allowed_tools of {entry}{add_back}."
    elif located[1] is not None:
        fix = f"In {path}, line {located[1]} (allowed_tools of {entry}), remove {remove}{add_back}."
    elif not located[2]:
        fix = (
            f"In {path}, {entry} (line {located[0]}) has no allowed_tools, so it allows every "
            f"tool: add allowed_tools = [{_DOCUMENT_TOOLS}] to it."
        )
    else:
        fix = f"In {path}, {entry} (line {located[0]}): remove {remove} from its allowed_tools{add_back}."
    return fix + _OPT_IN_HINT


def check_secrets_policy(policy_path: str | os.PathLike | None = None) -> CheckResult:
    """Warn when apps Enclave cannot identify may call the vault_* secrets tools.

    On a default install every MCP client is identified as `unknown`, which
    gets the `default` entry of policies.toml (or an `unknown` entry, if there
    is one). Only reads the file: the MCP server itself replaces an unmodified
    old default.
    """
    path = Path(policy_path or POLICY_PATH).expanduser()
    if not path.exists():
        return CheckResult(
            _SECRETS_CHECK, PASS,
            f"{path} does not exist yet; the default Enclave writes there gives apps it cannot "
            "identify no vault_* tools",
        )
    try:
        text = path.read_text(encoding="utf-8")
        if upgrade_legacy_default(text) is not None:
            return CheckResult(
                _SECRETS_CHECK, WARN,
                f"{path} is an unmodified default from an older Enclave, which lets apps Enclave "
                "cannot identify (on a default install, every MCP client) use the vault_* secrets "
                "tools; Enclave replaces it automatically, keeping a backup, the next time the "
                "Enclave app or its MCP server starts (including the MCP server check below)",
                "Fully quit and reopen your AI app so its Enclave server restarts, then run "
                "`enclave doctor` again. If this warning stays, Enclave cannot write the file "
                "(it enforces the new default anyway): check the file's permissions",
            )
        policy = resolve_agent_policy(parse_policy_document(text).agents, "unknown")
    except Exception as exc:  # unreadable, invalid TOML, or a shape the loader rejects
        return CheckResult(
            _SECRETS_CHECK, FAIL, f"cannot read {path}: {exc}",
            f"Fix {path} (the MCP server cannot start with it), or move it aside so Enclave "
            "writes a fresh default",
        )

    exposed = [t for t in SECRETS_TOOLS if policy.allows_module("vault") and policy.allows_tool(t)]
    if not exposed:
        return CheckResult(_SECRETS_CHECK, PASS, f"apps Enclave cannot identify get no vault_* tools ({path})")
    return CheckResult(
        _SECRETS_CHECK, WARN,
        f"apps Enclave cannot identify (on a default install, every MCP client) may call "
        f"{', '.join(exposed)}, which expose your stored secrets, through the "
        f"`{policy.agent_id}` entry of {path}",
        _secrets_policy_fix(text, path, policy),
    )


def run_checks(vault_path: str = "~/.vault") -> DoctorReport:
    report = DoctorReport()
    vault_dir = Path(vault_path).expanduser()

    # --- Python ---
    py = sys.version_info
    if (py.major, py.minor) >= (3, 11):
        report.add("Python", PASS, f"{platform.python_version()} at {sys.executable}")
    else:
        report.add(
            "Python",
            FAIL,
            f"{platform.python_version()} — Enclave needs Python 3.11+",
            "Install Python 3.11+ (e.g. `brew install python@3.11`) and re-run setup.sh",
        )

    # --- Platform ---
    system = platform.system()
    if _is_apple_silicon():
        report.add("Platform", PASS, "macOS on Apple Silicon — full local inference supported")
    elif system == "Darwin":
        report.add(
            "Platform",
            WARN,
            "macOS on Intel — MLX unavailable; local inference falls back to PyTorch (slower)",
        )
    else:
        report.add(
            "Platform",
            WARN,
            f"{system} — MLX local inference is Apple Silicon only; RAG/vault features still work",
        )

    # --- RAM ---
    ram = _total_ram_gb()
    if ram is None:
        report.add("Memory", WARN, "Could not determine RAM size")
    elif ram >= 16:
        report.add("Memory", PASS, f"{ram:.0f} GB RAM — comfortable for local models")
    elif ram >= 8:
        report.add(
            "Memory",
            WARN,
            f"{ram:.0f} GB RAM — the default 1.5B model works; larger models may swap",
        )
    else:
        report.add(
            "Memory",
            FAIL,
            f"{ram:.0f} GB RAM — below the 8 GB minimum for local inference",
            "Use RAG-only features, or run on a machine with more RAM",
        )

    # --- Disk ---
    try:
        free_gb = shutil.disk_usage(Path.home()).free / 1024**3
        if free_gb >= 10:
            report.add("Disk space", PASS, f"{free_gb:.0f} GB free")
        else:
            report.add(
                "Disk space",
                WARN,
                f"{free_gb:.0f} GB free — first model download needs ~2 GB",
            )
    except OSError:
        report.add("Disk space", WARN, "Could not determine free disk space")

    # --- Core dependencies ---
    core = ["click", "cryptography", "pydantic", "mcp", "sqlalchemy", "numpy"]
    missing = [m for m in core if not _has_module(m)]
    if not missing:
        report.add("Core dependencies", PASS, "all installed")
    else:
        report.add(
            "Core dependencies",
            FAIL,
            f"missing: {', '.join(missing)}",
            'Run `pip install -e .` (or `./setup.sh`) from the repo root',
        )

    # --- Embeddings backend ---
    if _has_module("fastembed"):
        report.add("Embeddings", PASS, "fastembed (ONNX) available — fast, lightweight")
    elif _has_module("sentence_transformers"):
        report.add("Embeddings", PASS, "sentence-transformers available")
    else:
        report.add(
            "Embeddings",
            FAIL,
            "no embeddings backend found",
            'Run `pip install -e ".[mac]"` to install RAG dependencies',
        )

    # --- Local inference ---
    if _has_module("mlx_lm"):
        report.add("Local LLM (MLX)", PASS, "mlx-lm installed — Apple Silicon inference ready")
    elif _is_apple_silicon():
        report.add(
            "Local LLM (MLX)",
            WARN,
            "mlx-lm not installed — chat with local models unavailable",
            'Run `pip install -e ".[mlx]"` to enable local inference',
        )
    elif _has_module("torch") and _has_module("transformers"):
        report.add("Local LLM (PyTorch)", PASS, "torch + transformers installed")
    else:
        report.add(
            "Local LLM",
            WARN,
            "no local inference backend — RAG search still works",
            'Apple Silicon: `pip install -e ".[mlx]"`; other: `pip install -e ".[cuda]"`',
        )

    # --- GUI ---
    if _has_module("flet"):
        report.add("Desktop GUI", PASS, "flet installed — run `enclave-gui`")
    else:
        report.add(
            "Desktop GUI",
            WARN,
            "flet not installed — GUI unavailable (CLI and MCP server still work)",
            'Run `pip install -e ".[gui]"`',
        )

    # --- Performance extras ---
    if _has_module("hnswlib"):
        report.add("Vector index", PASS, "hnswlib installed — fast HNSW search")
    else:
        report.add(
            "Vector index",
            WARN,
            "hnswlib not installed — falling back to brute-force search (fine below ~1k chunks)",
            'Run `pip install -e ".[mac-performance]"`',
        )

    # --- PDF support ---
    if _has_module("pypdf"):
        report.add("PDF support", PASS, "pypdf installed")
    else:
        report.add("PDF support", WARN, "pypdf not installed — PDF ingestion disabled")

    # --- Vault state ---
    key_path = vault_dir / "master.key"
    if not vault_dir.exists():
        report.add(
            "Vault",
            PASS,
            f"no vault yet at {vault_dir} — one is created on first use",
        )
    elif key_path.exists():
        mode = key_path.stat().st_mode & 0o777
        if mode & 0o077:
            report.add(
                "Vault",
                WARN,
                f"master key at {key_path} is readable by other users (mode {oct(mode)})",
                f"Run `chmod 600 {key_path}`",
            )
        else:
            report.add("Vault", PASS, f"initialized at {vault_dir}, master key protected")
    else:
        report.add("Vault", PASS, f"directory exists at {vault_dir} (no master key yet)")

    # --- Which tools apps Enclave cannot identify get. Runs before the MCP
    # server check, whose server upgrades an unmodified old default. ---
    report.checks.append(check_secrets_policy())

    # --- MCP server (launched the way Claude Desktop / Cursor launch it) ---
    report.checks.append(check_mcp_server())

    # --- Claude Desktop integration ---
    try:
        from advanced_vault.gui.mcp_setup import MCPSetupHelper

        helper = MCPSetupHelper(vault_path=str(vault_dir))
        if helper.detect_claude_desktop():
            if helper._is_target_configured("claude"):
                report.add("Claude Desktop", PASS, "detected and configured for Enclave")
            else:
                report.add(
                    "Claude Desktop",
                    WARN,
                    "detected but Enclave is not configured as an MCP server",
                    "Run `enclave mcp install`",
                )
        else:
            report.add(
                "Claude Desktop",
                WARN,
                "not detected — install it to command Enclave from Claude",
            )
    except Exception as exc:  # pragma: no cover - defensive
        report.add("Claude Desktop", WARN, f"could not check integration: {exc}")

    return report


def print_report(report: DoctorReport, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return

    print("Enclave Doctor")
    print("=" * 50)
    for check in report.checks:
        print(f"{_ICONS[check.status]} {check.name}: {check.detail}")
        if check.fix and check.status != PASS:
            print(f"   ↳ fix: {check.fix}")
    print("=" * 50)
    if report.failures:
        print(f"{len(report.failures)} problem(s) must be fixed before Enclave will run.")
    elif report.warnings:
        print(f"Ready to go — {len(report.warnings)} optional improvement(s) available.")
    else:
        print("Everything looks great. Run `enclave-gui` to start.")
