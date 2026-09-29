# Enclave

**Privacy-First AI Personal Data Manager**

> Your local agent that external AIs query via MCP — they get answers generated on your machine instead of your files.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)

> **Early beta.** Local chat in the desktop app works only on Apple Silicon
> Macs today, and only document text and secret values are encrypted at rest.
> Read [Known Limitations](#known-limitations) before trusting it with
> sensitive files.

## Quick Start (Apple Silicon Mac)

Local chat needs a Mac with Apple Silicon (M1 or later); 16 GB+ RAM is
recommended. Other machines: see [Platform support](#platform-support).

```bash
git clone https://github.com/zd87pl/slm-vault
cd slm-vault
./setup.sh
```

`setup.sh` creates a `.venv`, detects Apple Silicon, installs the right extras
(MLX local inference, desktop GUI, fast vector search), and finishes with an
environment check. Then:

```bash
source .venv/bin/activate

enclave-gui             # 1. Launch the desktop app
enclave mcp install     # 2. Connect Claude Desktop (merges into your existing config)
enclave doctor          # 3. Anytime something looks off
```

Restart Claude Desktop after step 2 and ask Claude about your documents.
Enclave retrieves the relevant passages and writes the answer locally; Claude
receives that answer, not your files.

> **First run notes**: the install itself is several GB (it includes PyTorch).
> The first chat downloads a ~1 GB local model (Qwen 2.5 1.5B, 4-bit) from
> Hugging Face; the first document you index downloads a ~130 MB embedding
> model. Both are cached afterwards. When an AI app calls Enclave, a consent
> dialog appears: "Allow Once" is the cautious choice (you are asked again
> next time), while "Always Allow" lets that app call every tool its policy
> allows, with no expiry. On a default install Enclave cannot tell AI apps
> apart, so "Always Allow" applies to all of them (see [Consent](#consent)),
> but no app can use the `vault_*` secrets tools until you opt it in. Calls
> are logged locally either way.

### Having trouble?

`enclave doctor` checks Python, RAM, disk, every dependency, your vault, and
the Claude Desktop integration — and prints the exact command to fix anything
that's missing.

## The Problem

Every AI wants your data to be useful. But once you share documents with
Claude, Cursor, or Copilot, you lose control. They see your raw data. You
can't audit access. You can't revoke it.

## The Solution

Enclave is a **local trusted agent** that sits between you and external AIs.

```
External Agent (Claude Desktop / Cursor / Copilot)
        ↓ MCP command: "Summarize Q3 report"
        ↓
┌───────────────────────────────────────┐
│  LOCAL TRUSTED AGENT (Enclave)        │
│  • Full access to your indexed docs   │
│  • Reads & processes locally          │
│  • Generates synthesized response     │
│  • Logs every access                  │
└───────────────────────────────────────┘
        ↓ Response: "Q3 revenue was $4.2M..."
        ↓
External Agent (gets the answer, not the file)
```

External AIs send requests. Enclave retrieves the relevant passages and
generates an answer locally, and the agent receives that answer instead of
your files. This limits bulk copying, but answers can quote or closely
paraphrase your documents, so an agent you allow can still learn whatever it
asks about. **Consent prompts and the activity log are the controls** — see
[Privacy Model](#privacy-model).

## Features

- **Local RAG**: Add documents and ask questions over them with semantic search
- **MCP Integration**: Works with Claude Desktop, Cursor, and any MCP client
- **Encrypted document text**: ChaCha20-Poly1305 for document and chunk text
  in the index (names, embeddings and chat history are not encrypted yet —
  see [What is and isn't encrypted](#what-is-and-isnt-encrypted))
- **Activity Logging**: MCP tool calls are recorded locally with the calling app
- **Consent and Allow-Lists**: A consent prompt per calling app, plus a
  per-app tool allow-list in `~/.enclave/policies.toml` (app detection is
  limited — see [Consent](#consent))
- **Local Inference**: MLX-powered LLM on Apple Silicon (Qwen 2.5 1.5B by default)
- **Desktop GUI**: Flet app; local chat currently needs an Apple Silicon Mac
- **Adapter Training** (experimental, Apple Silicon only): Fine-tune local
  models on your documents

### Performance Optimizations

- **HNSW Index**: Approximate vector search via `hnswlib` (installed by
  `setup.sh`; without it Enclave falls back to brute-force search)
- **E5-small Embeddings**: `intfloat/e5-small-v2`, 384 dimensions
- **Persistent Cache**: Embeddings are cached on disk, so unchanged text is not re-embedded
- **Recursive Chunking**: Chunks split on paragraph and sentence boundaries

## Installation Options

The recommended path is `./setup.sh` (above). If you prefer manual control:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip

# Apple Silicon Mac — everything (MLX + GUI + fast search):
pip install -e ".[mac]"

# Any other machine — GUI + fast search; no MLX, so desktop chat does not
# work and CLI/MCP answers come from a small fallback model (see Platform support):
pip install -e ".[gui,mac-performance]"

# Minimal — CLI + MCP server only (still pulls PyTorch, several GB):
pip install -e .
```

Entry points installed with the package:

| Command | What it does |
|---------|--------------|
| `enclave` | CLI (vault, models, prosumer vaults, doctor, MCP setup) |
| `enclave-gui` | Desktop app |
| `enclave-mcp` | MCP server (stdio) — what Claude Desktop launches |

### Connect Claude Desktop

The easy way — detects Claude Desktop, merges into your existing config
(other MCP servers are preserved; back the file up first if it may not be
valid JSON), and points at the right Python:

```bash
enclave mcp install          # or: enclave mcp install --target cursor
enclave mcp status           # verify detection + configuration
```

Manual way — `enclave mcp config` prints the JSON block to paste into
`~/Library/Application Support/Claude/claude_desktop_config.json`.

Restart Claude Desktop afterwards.

### Index Documents (Python API)

The desktop app and MCP server manage their own encrypted index under
`~/.vault`. For scripting against a separate index:

```python
from advanced_vault.training import RAGIndex
import os

# Generate or load a 32-byte encryption key. Persist the key if you persist
# the index — a new random key cannot decrypt an existing database.
master_key = os.urandom(32)

# Create encrypted index (explicit path keeps this demo self-contained)
with RAGIndex(master_key=master_key, db_path="./demo_rag.db") as index:
    # Add documents
    index.add_document(
        name="Q3 Report",
        content="Revenue increased 15% to $4.2M in Q3..."
    )

    # Search
    results = index.search("What was Q3 revenue?")
    for r in results:
        print(f"{r.document_name}: {r.chunk.content[:100]}...")
```

## MCP Tools

The main tools Enclave exposes to AI agents:

| Tool | Description |
|------|-------------|
| `agent_query` | Ask questions about indexed documents |
| `agent_summarize` | Summarize a topic or document |
| `agent_draft` | Draft content informed by your documents |
| `agent_status` | Check indexed documents and agent status |
| `vault_store` | Store secrets (API keys, passwords) |
| `vault_recall` | Retrieve a stored secret by its exact entry name |

The server also advertises experimental tools: `sheriff_*` file-access
leases (which can return file contents; the default policy blocks them), a
mock wallet, and cloud `langchain_*` tools that do nothing unless configured.

Which tools each app may call is set in `~/.enclave/policies.toml`. On a
default install Enclave cannot tell AI apps apart (see [Consent](#consent)),
so every app gets the file's `default` entry, which allows the `agent_*`
tools and `query_knowledge` but not the `vault_*` secrets tools. To give
them to one app, see
[Letting one app use the secrets tools](#letting-one-app-use-the-secrets-tools).
Earlier versions put `vault_*` in `default`. If you never edited the file,
Enclave replaces it with the new default the next time it starts, keeping
the old one as `policies.toml.bak-<date>`; if you did, `enclave doctor`
tells you which line to change.

**What agents receive**: the `agent_*` tools return text generated locally
from retrieved passages, plus the names of the source documents — not the
files. That text can quote your documents, so treat anything an allowed agent
asks about as shared with it. `vault_recall` returns the stored secret itself.

## Personal Data Vaults

Enclave can sort your documents into **vault categories**, each with an
optional, experimental adapter preset:

| Vault | Documents | AI Adapter |
|-------|-----------|------------|
| 🏥 **Health** | Medical records, prescriptions, lab results | Health Advisor |
| 💰 **Finance** | Bank statements, tax returns, investments | Tax Assistant |
| ⚖️ **Legal** | Contracts, wills, immigration papers | Legal Companion |
| 🧠 **Personal** | Journals, emails, notes, memories | Life Archivist |

### Auto-Classification

Enclave suggests a category from keywords in each file's name and content
(a heuristic, so check the result):

```bash
# Classify a single file
enclave prosumer classify blood_test.pdf

# Classify an entire folder
enclave prosumer classify-folder ~/Documents --recursive
```

### Adapter Training (experimental)

Train a domain-specific adapter on your documents (Apple Silicon only):

```bash
# List training presets
enclave prosumer presets list

# Train via GUI: Drop docs → Click "Train AI"
```

Each preset's system prompt asks the model to stay within limits (these are
instructions to the model, not guarantees):
- **Health Advisor**: Never prescribes, always recommends seeing a doctor
- **Tax Assistant**: Shows calculations, suggests consulting a CPA
- **Legal Companion**: Summarizes only, never gives legal advice

### Encrypted Adapter Backup & Sharing (experimental)

A trained adapter is not a copy of your documents, but it can memorize parts
of them. Treat an exported adapter as being as sensitive as the documents it
was trained on:

```bash
# Export encrypted adapter
enclave prosumer backup export ~/.vault/adapters/health.wdva \
  --name "My Health Advisor" --category health

# Import on another device
enclave prosumer backup import ./health.enclave

# Verify integrity
enclave prosumer backup verify ./health.enclave

# List all backups
enclave prosumer backup list
```

**What's included**: The adapter file exactly as it is on disk (WDVA
adapters are already encrypted; the backup adds no encryption of its own) +
metadata.
**What's NOT included**: The document files themselves, or any key needed to
decrypt the adapter — move that separately if you import on another device.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     External AI Agents                       │
│            (Claude Desktop, Cursor, Copilot)                │
└───────────────────────────┬─────────────────────────────────┘
                            │ MCP Protocol
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Enclave MCP Server                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Consent   │  │   Activity  │  │  Agent Commands     │  │
│  │   Manager   │  │   Logger    │  │  (query/summarize)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────────┐
│   RAG Index   │  │  Local LLM    │  │ Encrypted Vault   │
│  (HNSW+E5)    │  │   (MLX)       │  │ (ChaCha20)        │
└───────────────┘  └───────────────┘  └───────────────────┘
```

## Privacy Model

1. **Documents stay local**: They are indexed and stored on your device. What
   leaves is what Enclave returns to an agent (answers, or a secret via
   `vault_recall`) — and if that agent is a cloud assistant such as Claude, it
   becomes part of that conversation.
2. **Answers, not files**: Agents get locally generated answers and source
   document names. Answers can quote passages, so this limits bulk copying but
   cannot stop an allowed agent from learning what it asks about.
3. **Consent and allow-lists**: See [Consent](#consent).
4. **Audit trail**: MCP tool calls are logged locally with the calling app,
   the tool, and whether it was allowed (`~/.vault/activity.jsonl`, plus a
   policy audit log for calls the allow-list blocks). A call that crashes with
   an unexpected error after consent is not logged.
5. **Encryption at rest (partial)**: See below.

### What is and isn't encrypted

Encrypted with ChaCha20-Poly1305 (random 96-bit nonce per record):

- Document text and chunk text in the RAG index (`rag.db`)
- Secrets and notes stored with `vault_store`, `enclave add-secret` or
  `enclave add-note` (their service names, tags and descriptions are not
  encrypted)

Not encrypted yet:

- File names, full source paths and folder metadata
- Content hashes — an unsalted SHA-256 of each document, which lets anyone
  holding the database check whether it contains a file they already have
- Embeddings/vectors (in `rag.db` and the HNSW index files) and the shared
  embedding cache `~/.enclave/embedding_cache.db`, which keeps entries after a
  document is deleted; embeddings can leak some of the text they came from
- Chat history (`~/.vault/chat_history_<profile>.json`, `~/.vault/question_history.json`)
- Query, activity and audit logs

**The key**: each encrypted database uses a random 32-byte key kept in a
`master.key` file right next to it. There is no passphrase and no OS keychain
yet, so anything that can read that folder — malware running as you, a backup
or sync of the whole folder — can read the vault. The encryption only helps
when a database file is copied without its key file. Turn on FileVault (or
your OS's full-disk encryption).

### Consent

- When an app calls a tool (other than the `sheriff_*` tools, which use
  their own lease flow), Enclave asks in a system dialog. On macOS the choices
  are Allow Once, Always Allow or Deny; the Linux (zenity) dialog also offers
  Deny Always. Until you make a lasting choice you are asked on every call. If
  no dialog can be shown or you don't answer in time, the call is denied.
- **"Always Allow" covers every tool that app's policy allows, with no
  expiry.**
- **App identity is a best guess**, from the `MCP_CLIENT` or `PARENT_PROCESS`
  environment variables (neither is set by `enclave mcp install`) or, if the
  optional `psutil` package is installed, the parent process name. `psutil` is
  not an Enclave dependency, so on a default install Claude Desktop, Cursor
  and every other client are all the same app, `unknown`: they get the
  `default` policy (document tools only, no `vault_*` secrets tools) and they
  share one consent decision — "Always Allow" for one of them approves them
  all.
- To change a decision, **fully quit the AI app first** — the MCP server
  reads `permissions.json` and `policies.toml` only when it starts, and a
  running server can write its old permissions back — then edit and restart
  the app. Remove the app's entry from `~/.vault/permissions.json` to undo
  "Always Allow"; replace it with `{"denied": true}` to block the app
  permanently (macOS has no Deny Always button); edit
  `~/.enclave/policies.toml` to limit which tools an app can call at all.
- The desktop app also shows per-app permission toggles, a Revoke button,
  finer-grained scopes and time-limited access; these are **not enforced yet**.
  Its global kill switch (Settings → Security) is saved to `policies.toml`,
  so it reaches an MCP server that is already running only after the AI app
  restarts.
- **On Windows, consent prompts are not implemented, so every call that needs
  consent is denied.**

#### Letting one app use the secrets tools

No AI app can call the `vault_*` tools until you opt it in:

1. Name the app: in its MCP config (`claude_desktop_config.json` for Claude
   Desktop, `~/.cursor/mcp.json` for Cursor), add
   `"MCP_CLIENT": "claude-desktop"` (or `"cursor"`) to the `"env"` of the
   `enclave` server entry.
2. In `~/.enclave/policies.toml`, add the tools to that app's `[[agents]]`
   entry (`agent_id = "claude-desktop"` or `"cursor"`): for example
   `"vault_recall", "vault_list_entries"` in its `allowed_tools`, or
   `"vault_*"` to also allow storing and deleting.
3. Fully quit and reopen the app.

Naming the app applies everything in its `[[agents]]` entry, not just the tools
you add: the shipped `claude-desktop` and `cursor` entries also allow the
(mock) wallet tools, including `request_purchase` with auto-approval under
$25. Remove `"wallet"` from that entry's `allowed_modules` if you don't want
that.

`MCP_CLIENT` is a label, not proof: any program that starts Enclave's server
with the same label gets that entry (as does, with `psutil` installed, any
app whose process name contains "claude" or "cursor"). Only software already
running as you can do that, and it could read the vault files directly
anyway. Re-running `enclave mcp install` rewrites the server entry without
the label, which takes the secrets tools away again. Never add `vault_*` to
`default` — that gives them to every app Enclave cannot identify, and
`enclave doctor` warns about it.

### Network access

- **Hugging Face Hub**: model downloads on first use; loading a cached model
  may also check the Hub for updates. No document content is sent.
- **npm**: if a PDF has little extractable text and Node's `npx` is on your
  PATH, the parser runs `npx -y @llamaindex/liteparse`, which downloads and
  runs that package. Set `ENCLAVE_LITEPARSE_ALLOW_NPX=false` to prevent this.
- **PyPI**: some desktop-app features (SmolDocling PDF extraction, Q&A
  generation) pip-install missing packages the first time you use them.
- **Ollama** (optional OCR for scanned PDFs, and Q&A generation where MLX is
  unavailable): the desktop app never installs or starts Ollama, and never
  runs an installer script. If Ollama is missing or stopped, it tells you to
  install it from https://ollama.com or start it yourself. It downloads an
  Ollama model (for example `llama3.2-vision:11b`, about 8 GB) only after you
  confirm a prompt that names the model and its size (Settings → Run Local
  Setup). Otherwise it only checks whether Ollama is running on `localhost`
  (or at `OLLAMA_BASE_URL`, if you set it).
- **Cloud backend**: none by default. Unless you set `ENCLAVE_BACKEND_URL`
  (in the environment or in `~/.enclave/config.env`), the desktop app sends
  no backend requests, and on older screens (for example Settings → Advanced
  → System Setup, Training Queue or Activity Log) the app bar's status icon
  has the tooltip "Cloud backend: not configured (local-only)". An empty
  value counts as unset. If you set it, those screens request its `/health`
  endpoint to show whether it is reachable (no vault content is sent), and
  the desktop cloud features use it once you sign in.
- **Cloud features** (desktop cloud sync and sign-in, the MCP `langchain_*`
  tools) are **off by default**; the MCP tools stay inert unless both
  `ENCLAVE_API_KEY` and `ENCLAVE_API_BASE_URL` are set.

## Known Limitations

- **Local chat needs Apple Silicon.** On Intel Macs, Linux and Windows the
  desktop app's chat never sends (it keeps offering a model download), and the
  CLI and MCP server fall back to TinyLlama 1.1B on PyTorch, whose answers are
  poor.
- **Windows**: no setup script, and no consent prompt, so MCP calls are denied.
- **Partial encryption, key stored next to the data** — see
  [What is and isn't encrypted](#what-is-and-isnt-encrypted).
- **Coarse consent**: no expiry; on a default install every AI app is
  `unknown` and they all share one consent decision; opting one app in to the
  secrets tools relies on a label its config declares; revoking access (or
  using the kill switch) takes effect only after the AI app restarts. See
  [Consent](#consent).
- **Documents can steer answers**: retrieved text goes into the local model's
  prompt as-is, so a malicious document can plant instructions in the answer
  an agent receives.
- **Heavy install**: the core install pulls PyTorch — about 5–6 GB on Linux,
  several GB on macOS.
- **No releases yet**: no signed app, installer or PyPI package; install from source.
- **Adapter training and packaging are experimental**, and training needs
  Apple Silicon. Password-protected adapter packages derive their key with a
  single unsalted SHA-256, so use a long random password.

## Project Structure

```
slm-vault/
├── advanced_vault/          # Core application (see advanced_vault/README.md)
│   ├── gui/                 # Desktop GUI (Flet)
│   ├── cli/                 # `enclave` CLI (incl. doctor + MCP setup)
│   ├── training/            # RAG index, embeddings, caching (+ experimental adapter training)
│   ├── prosumer/            # Personal data vaults (Health, Finance, Legal, Personal)
│   └── mcp_server/          # MCP server implementation
├── setup.sh                 # One-command setup (macOS/Linux)
├── docs/                    # Documentation (index: docs/README.md)
├── examples/                # Secrets-store demo scripts
├── scripts/                 # Build, packaging and verification scripts
└── tests/                   # Test suite
```

> **Legacy code lives on the
> [`legacy-archive-2026-09-29`](https://github.com/zd87pl/slm-vault/tree/legacy-archive-2026-09-29)
> branch**, not on `main`: the RunPod cloud-training stack (`src/`, the
> Dockerfiles and RunPod scripts), the sync backend (`advanced_vault/backend/`),
> the browser extension, the LangChain package and the OpenClaw plugin, with
> their docs. That code is unmaintained.

**Not part of the local-only story**: the desktop app's cloud sync, RunPod and
backend-status features (which stay off until you configure a backend URL or
RunPod credentials) and the MCP server's `langchain_*` tools are experimental
or legacy. They are not covered by the privacy model above and may be removed
(see also [Network access](#network-access)).

## Requirements

- Python 3.11+
- For local chat: a Mac with Apple Silicon (M1 or later)
- 8 GB+ RAM (16 GB+ recommended for local LLM)
- Disk: the core install pulls PyTorch (through `sentence-transformers`) —
  about 5–6 GB on Linux, where pip also fetches the CUDA libraries, and
  several GB on macOS — plus about 1.1 GB of models on first use (the non-Mac
  fallback model alone is about 2.2 GB)

### Platform support

| | Apple Silicon Mac | Intel Mac, Linux | Windows |
|---|---|---|---|
| Desktop app chat | Yes (MLX) | No — keeps offering a model download | No |
| CLI and MCP server | Yes | Run, but answers come from TinyLlama 1.1B (PyTorch) and are poor | Same as Linux, and MCP calls are denied (no consent prompt) |
| `setup.sh` | Yes | Yes | No (bash only; install with pip) |

## Advanced Local Training (experimental)

Apple Silicon only. Enclave supports advanced training algorithms via
`mlx-lm-lora` (`pip install -e ".[advanced-training]"`). There is no
evaluation yet showing that adapters answer better than retrieval alone.

| Algorithm | Use Case | Env Var |
|-----------|----------|---------|
| **SFT** (default) | Standard fine-tuning on Q&A pairs | `ENCLAVE_LOCAL_TRAIN_MODE=sft` |
| **DPO** | Preference optimization (good vs bad answers) | `ENCLAVE_LOCAL_TRAIN_MODE=dpo` |
| **ORPO** | Odds-ratio preference optimization | `ENCLAVE_LOCAL_TRAIN_MODE=orpo` |
| **GRPO** | Group-relative policy optimization with custom rewards | `ENCLAVE_LOCAL_TRAIN_MODE=grpo` |
| **SFT+QAT** | Quantization-aware training for smaller adapters | `ENCLAVE_LOCAL_TRAIN_MODE=sft` + `ENCLAVE_LOCAL_QAT=true` |

### Environment Variables

```bash
# Training algorithm
export ENCLAVE_LOCAL_TRAIN_MODE=dpo      # sft | dpo | orpo | grpo

# QAT (Quantization Aware Training)
export ENCLAVE_LOCAL_QAT=true            # true/false

# LoRA hyperparameters
export ENCLAVE_LOCAL_LORA_RANK=8
export ENCLAVE_LOCAL_LORA_ALPHA=16
export ENCLAVE_LOCAL_LR=1e-5
export ENCLAVE_LOCAL_BATCH_SIZE=4

# DPO/ORPO specific
export ENCLAVE_LOCAL_DPO_BETA=0.1

# GRPO specific
export ENCLAVE_LOCAL_GRPO_GROUP_SIZE=4
export ENCLAVE_LOCAL_GRPO_REWARD_COMBO=rag_default  # rag_default | citation_heavy | concise | structured

# Force local vs cloud training
export ENCLAVE_LOCAL_TRAINING=true       # true | false | auto
```

### Package & Share Adapters

The password is turned into a key with a single unsalted SHA-256, which is
weak against guessing — use a long random password.

```bash
# Package a trained adapter (prompts for an encryption password)
enclave model package ~/.enclave/adapters/my_adapter ./my_adapter.enclave \
  --train-mode dpo --qat

# Unpack (prompts for the password)
enclave model unpack ./my_adapter.enclave ~/.enclave/adapters/restored

# Verify integrity (prompts for the password)
enclave model verify ./my_adapter.enclave
```

## Development

```bash
git clone https://github.com/zd87pl/slm-vault
cd slm-vault

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (tests needing missing optional deps skip automatically)
pytest

# Lint (the correctness rules CI enforces)
ruff check advanced_vault/ --select F821,F811,F823,E9,F63,F7

# Type checking
mypy advanced_vault/
```

## Documentation

- [Security policy and threat model](SECURITY.md)
- [MCP server](advanced_vault/mcp_server/README.md) — manual client setup and the `vault_*` secrets tools (its roadmap section is out of date)
- [Private Language Models](docs/PRIVATE_LANGUAGE_MODELS.md) — CLI profiles: ingest, chat, adapters

The [documentation index](docs/README.md) lists the rest; the older notes
there may not match the code.

## Status

- [x] RAG indexing (HNSW acceleration when `hnswlib` is installed)
- [x] E5-small embeddings with persistent cache
- [x] MCP server with agent commands
- [x] ChaCha20-Poly1305 encryption of document text and secret values
- [x] Activity logging and per-app consent (coarse; see [Consent](#consent))
- [x] Desktop GUI (Flet) — local chat on Apple Silicon only
- [x] Local LLM inference (MLX, Apple Silicon)
- [x] Advanced local training (DPO, ORPO, GRPO, QAT via mlx-lm-lora) — experimental
- [x] Encrypted adapter packaging & distribution — experimental
- [x] One-command setup (`setup.sh`, macOS/Linux), `enclave doctor`, `enclave mcp install`
- [ ] Encrypted file names, embeddings, chat history and logs
- [ ] Vault key protected by a passphrase or the OS keychain
- [ ] Usable local chat on Intel Macs, Linux and Windows
- [ ] Fine-grained, expiring consent
- [ ] Multi-device sync (encrypted)
- [ ] Adapter marketplace

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

Please report security issues privately — see [SECURITY.md](SECURITY.md).

## License

Apache License 2.0 - see [LICENSE](LICENSE)

---

**Enclave**: Privacy-first AI. Your data, your control.
