#!/usr/bin/env bash
# Enclave one-command setup.
#
#   ./setup.sh            install into ./.venv with the right extras for this machine
#   ./setup.sh --minimal  core + MCP server only (no GUI, no local LLM)
#
# Safe to re-run: it reuses the existing .venv and upgrades in place.

set -euo pipefail

MINIMAL=0
for arg in "$@"; do
    case "$arg" in
        --minimal) MINIMAL=1 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -6
            exit 0
            ;;
        *) echo "Unknown option: $arg (try --help)"; exit 1 ;;
    esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

cd "$(dirname "$0")"

# --- Pick a Python (3.10+ required, 3.11+ preferred) ---------------------------
PYTHON=""
for candidate in python3.12 python3.11 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    fi
done
[ -n "$PYTHON" ] || fail "Python 3.10+ not found. On macOS: brew install python@3.12"
say "Using $("$PYTHON" --version) at $PYTHON"

# --- Detect platform ------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"
APPLE_SILICON=0
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    APPLE_SILICON=1
    say "Detected macOS on Apple Silicon — enabling MLX local inference"
elif [ "$OS" = "Darwin" ]; then
    say "Detected macOS on Intel — MLX unavailable, installing GUI + RAG only"
else
    say "Detected $OS — installing core + GUI (local LLM via MLX is macOS-only)"
fi

# --- Create / reuse venv --------------------------------------------------------
if [ ! -d .venv ]; then
    say "Creating virtual environment in .venv"
    "$PYTHON" -m venv .venv
else
    say "Reusing existing .venv"
fi
VENV_PY="./.venv/bin/python"
"$VENV_PY" -m pip install --quiet --upgrade pip

# --- Install --------------------------------------------------------------------
if [ "$MINIMAL" = "1" ]; then
    EXTRAS=""
elif [ "$APPLE_SILICON" = "1" ]; then
    EXTRAS="[mac]"
else
    EXTRAS="[gui,mac-performance]"
fi

say "Installing enclave-vault${EXTRAS} (first install downloads ML dependencies — a few minutes)"
"$VENV_PY" -m pip install --upgrade -e ".${EXTRAS}"

# --- Verify ---------------------------------------------------------------------
say "Running environment check"
"$VENV_PY" -m advanced_vault.cli doctor || true

cat <<'NEXT'

Setup complete. Next steps:

  1. Activate the environment:     source .venv/bin/activate
  2. Launch the desktop app:       enclave-gui
  3. Connect Claude Desktop:       enclave mcp install
  4. Re-check anytime:             enclave doctor

NEXT
