# `advanced_vault` package

The Python package behind Enclave: the desktop app, the `enclave` CLI, the
MCP server and the encrypted document index. For installation, usage, the
privacy model and known limitations, see the [main README](../README.md).

## Layout

| Package | What it holds |
|---------|---------------|
| `cli/` | The `enclave` command, including `enclave doctor` and `enclave mcp install` |
| `gui/` | The Flet desktop app (`enclave-gui`); see [gui/README.md](gui/README.md) |
| `mcp_server/` | The MCP server (`enclave-mcp`), consent prompts and activity log; see [mcp_server/README.md](mcp_server/README.md) |
| `enclave_control/` | Per-app tool allow-lists (`~/.enclave/policies.toml`), kill switch and audit store |
| `private_models/` | Profiles: ingest documents and ask questions over them (the path the GUI and CLI use) |
| `training/` | `RAGIndex`, embeddings, vector search, and the experimental MLX adapter training |
| `parsing/` | Document text extraction shared by ingest paths |
| `prosumer/` | Vault categories (Health, Finance, Legal, Personal), the document classifier and adapter presets |
| `core/`, `encrypted_kv/` | The encrypted secrets store behind the `vault_*` MCP tools, and its query router |
| `sheriff/`, `wallet/` | Experimental file-access leases and a mock wallet, exposed as MCP tools |
| `model_cache.py` | Offline-first loading of cached Hugging Face models |

Tests live in `tests/` directories inside the packages and in the
repository's top-level `tests/` directory. Run them all with `pytest` from the
repository root.

Legacy code that used to live in or next to this package (the RunPod
cloud-training stack, the sync backend, the browser extension, the LangChain
package and several unimplemented research stubs) is preserved on the
`legacy-archive-2026-09-29` branch.
