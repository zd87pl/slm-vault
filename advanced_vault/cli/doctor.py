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
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


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


def run_checks(vault_path: str = "~/.vault") -> DoctorReport:
    report = DoctorReport()
    vault_dir = Path(vault_path).expanduser()

    # --- Python ---
    py = sys.version_info
    if (py.major, py.minor) >= (3, 10):
        report.add("Python", PASS, f"{platform.python_version()} at {sys.executable}")
    else:
        report.add(
            "Python",
            FAIL,
            f"{platform.python_version()} — Enclave needs Python 3.10+",
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
