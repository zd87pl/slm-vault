# Quick Start Guide

The canonical quick start lives in the repository README:

**→ [README — Quick Start (macOS, ~5 minutes)](../../README.md#quick-start-macos-5-minutes)**

TL;DR:

```bash
git clone https://github.com/zd87pl/slm-vault
cd slm-vault
./setup.sh
source .venv/bin/activate

enclave-gui             # desktop app
enclave mcp install     # connect Claude Desktop
enclave doctor          # diagnose any problem
```

> Looking for the optional self-hosted sync backend (Supabase)? That is an
> advanced deployment, not part of the local quick start — see
> `advanced_vault/backend/` and install with `pip install -e ".[backend]"`.
