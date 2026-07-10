# Enclave

**Privacy-First AI Personal Data Manager**

> Your local agent that external AIs command via MCP — they never see your documents.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)

## Quick Start (macOS, ~5 minutes)

Best experience: a MacBook with Apple Silicon and 16 GB+ RAM — everything runs locally.

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
enclave mcp install     # 2. Connect Claude Desktop (safe: merges, never overwrites)
enclave doctor          # 3. Anytime something looks off
```

Restart Claude Desktop after step 2 and ask Claude about your documents —
Enclave answers locally. Your files never leave your machine.

> **First run notes**: the first chat downloads a ~1 GB local model
> (Qwen 2.5 1.5B, 4-bit) from Hugging Face; the first document you index
> downloads a ~130 MB embedding model. Both are cached afterwards and
> everything then works offline. The first time an AI agent touches your
> vault, macOS shows a consent dialog — choose "Always Allow" for the
> agents you trust; every access is logged either way.

### Having trouble?

`enclave doctor` checks Python, RAM, disk, every dependency, your vault, and
the Claude Desktop integration — and prints the exact command to fix anything
that's missing.

## The Problem

Every AI wants your data to be useful. But once you share documents with
Claude, Cursor, or Copilot, you lose control. They see your raw data. You
can't audit access. You can't revoke it.

**The governance gap is real**: 79% of organizations are adopting agentic AI,
but only 48% have frameworks for limiting AI autonomy.

## The Solution

Enclave is a **local trusted agent** that sits between you and external AIs.

```
External Agent (Claude Desktop / Cursor / Copilot)
        ↓ MCP command: "Summarize Q3 report"
        ↓
┌───────────────────────────────────────┐
│  LOCAL TRUSTED AGENT (Enclave)        │
│  • Full access to your encrypted docs │
│  • Reads & processes locally          │
│  • Generates synthesized response     │
│  • Logs every access                  │
└───────────────────────────────────────┘
        ↓ Response: "Q3 revenue was $4.2M..."
        ↓
External Agent (never saw the actual document)
```

External AIs send commands. Enclave reads your documents locally and returns
synthesized answers. **They never see your raw data.**

## Features

- **Local RAG**: Drop documents, instantly queryable via semantic search
- **MCP Integration**: Works with Claude Desktop, Cursor, and any MCP client
- **Encrypted Storage**: ChaCha20-Poly1305 encryption for all data at rest
- **Activity Logging**: See every command from every AI agent
- **Per-Agent Permissions**: Control what each AI can access
- **Local Inference**: MLX-powered LLM on Apple Silicon (Qwen 2.5, Phi-4, Llama)
- **Desktop GUI**: Native macOS/Windows/Linux application
- **Adapter Training**: Fine-tune local models on your documents

### Performance Optimizations

- **HNSW Index**: 10-30x faster vector search at scale
- **E5-small Embeddings**: +15% retrieval quality vs MiniLM
- **Persistent Cache**: 2-9x speedup for repeated queries
- **Recursive Chunking**: Better recall with semantic boundaries

## Installation Options

The recommended path is `./setup.sh` (above). If you prefer manual control:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip

# Apple Silicon Mac — everything (MLX + GUI + fast search):
pip install -e ".[mac]"

# Any other machine — GUI + fast search, no local LLM:
pip install -e ".[gui,mac-performance]"

# Minimal — CLI + MCP server only:
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
(other MCP servers are preserved), and points at the right Python:

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

Enclave exposes these tools to AI agents:

| Tool | Description |
|------|-------------|
| `agent_query` | Ask questions about indexed documents |
| `agent_summarize` | Summarize a topic or document |
| `agent_draft` | Draft content informed by your documents |
| `agent_status` | Check indexed documents and agent status |
| `vault_store` | Store secrets (API keys, passwords) |
| `vault_recall` | Retrieve secrets with natural language |

**Key principle**: `agent_query` returns synthesized answers, not raw
documents. External AIs never see your actual content.

## Personal Data Vaults

Enclave organizes your documents into **semantic vault categories** with
domain-specific AI adapters:

| Vault | Documents | AI Adapter |
|-------|-----------|------------|
| 🏥 **Health** | Medical records, prescriptions, lab results | Health Advisor |
| 💰 **Finance** | Bank statements, tax returns, investments | Tax Assistant |
| ⚖️ **Legal** | Contracts, wills, immigration papers | Legal Companion |
| 🧠 **Personal** | Journals, emails, notes, memories | Life Archivist |

### Auto-Classification

Drop any file and Enclave automatically detects its type:

```bash
# Classify a single file
enclave prosumer classify blood_test.pdf

# Classify an entire folder
enclave prosumer classify-folder ~/Documents --recursive
```

### One-Click Adapter Training

Train a domain-specific AI on your documents:

```bash
# List training presets
enclave prosumer presets list

# Train via GUI: Drop docs → Click "Train AI" → Done in 5-15 min
```

Each preset includes safety guardrails:
- **Health Advisor**: Never prescribes, always recommends seeing a doctor
- **Tax Assistant**: Shows calculations, suggests consulting a CPA
- **Legal Companion**: Summarizes only, never gives legal advice

### Encrypted Adapter Backup & Sharing

Your trained adapter contains learned patterns — not your raw documents. Back
it up or share it safely:

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

**What's included**: Encrypted learned weights (WDVA format) + metadata.
**What's NOT included**: Your raw documents, filenames, or personal data.

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

1. **Your data stays local**: Documents are indexed and stored on your device
2. **Encryption at rest**: All content encrypted with ChaCha20-Poly1305
3. **Synthesized responses**: External AIs get answers, not raw documents
4. **Consent required**: Every access requires explicit permission
5. **Full audit trail**: See exactly what each AI accessed and when
6. **Key zeroing**: Encryption keys securely wiped from memory after use

Network access at runtime: Hugging Face (model downloads, first run only).
The optional cloud-sync backend is **off by default** and only used if you
set `ENCLAVE_API_KEY`.

## Project Structure

```
slm-vault/
├── advanced_vault/          # Core application
│   ├── gui/                 # Desktop GUI (Flet)
│   ├── cli/                 # `enclave` CLI (incl. doctor + MCP setup)
│   ├── training/            # RAG index, embeddings, caching
│   ├── prosumer/            # Personal data vaults (Health, Finance, Legal, Personal)
│   ├── mcp_server/          # MCP server implementation
│   └── backend/             # Self-hosted sync backend (optional)
├── setup.sh                 # One-command setup for beta users
├── browser-extension/       # Browser extension
├── langchain-enclave/       # LangChain integration
├── docs/                    # Documentation
├── examples/                # Example scripts
├── src/                     # LEGACY: cloud GPU training (RunPod) — not needed locally
└── tests/                   # Test suite (legacy cloud tests auto-skip)
```

> `src/`, the RunPod scripts, `requirements.txt`, and the Dockerfiles support
> the optional **cloud GPU training** path. Local Mac users never need them.

## Requirements

- Python 3.10+ (3.11 recommended)
- macOS (Apple Silicon recommended), Windows, or Linux
- 8 GB+ RAM (16 GB+ recommended for local LLM)
- ~3 GB disk for dependencies + ~1.5 GB for models (first run)

## Advanced Local Training

Enclave supports advanced training algorithms via `mlx-lm-lora` on Apple
Silicon (`pip install -e ".[advanced-training]"`):

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

# Lint (correctness rules)
ruff check advanced_vault/ --select F,E9

# Type checking
mypy advanced_vault/
```

## Documentation

- [Architecture Overview](docs/architecture/ARCHITECTURE.md)
- [Cryptographic Specs](docs/architecture/CRYPTOGRAPHIC_SPECS.md)
- [MLX DoRA Architecture](docs/MLX_DORA_ARCHITECTURE.md)
- [Security Analysis](docs/security/SECURITY_ANALYSIS_PDF_QA.md)
- [Deployment Guide](docs/deployment/RUNPOD_DEPLOYMENT.md)

## Status

- [x] RAG indexing with HNSW acceleration
- [x] E5-small embeddings with persistent cache
- [x] MCP server with agent commands
- [x] Encrypted vault storage (ChaCha20-Poly1305)
- [x] Activity logging and consent management
- [x] Desktop GUI (Flet)
- [x] Local LLM inference (MLX)
- [x] Browser extension
- [x] Advanced local training (DPO, ORPO, GRPO, QAT via mlx-lm-lora)
- [x] Encrypted adapter packaging & distribution
- [x] One-command setup (`setup.sh`), `enclave doctor`, `enclave mcp install`
- [ ] Multi-device sync (encrypted)
- [ ] Adapter marketplace

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

Apache License 2.0 - see [LICENSE](LICENSE)

---

**Enclave**: Privacy-first AI. Your data, your control.
