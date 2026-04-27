# Enclave

**Privacy-First AI Personal Data Manager**

> Your local agent that external AIs command via MCP — they never see your documents.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)

## The Problem

Every AI wants your data to be useful. But once you share documents with Claude, Cursor, or Copilot, you lose control. They see your raw data. You can't audit access. You can't revoke it.

**The governance gap is real**: 79% of organizations are adopting agentic AI, but only 48% have frameworks for limiting AI autonomy.

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

External AIs send commands. Enclave reads your documents locally and returns synthesized answers. **They never see your raw data.**

## Features

- **Local RAG**: Drop documents, instantly queryable via semantic search
- **MCP Integration**: Works with Claude Desktop, Cursor, Copilot, and any MCP client
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

## Quick Start

### Installation

```bash
# Install from source
git clone https://github.com/your-org/slm-vault
cd slm-vault
python3.11 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[mlx,gui,mac-performance]"

# Verify the local demo path
./.venv/bin/python scripts/verify_local_demo.py
```

### Run the Desktop App

```bash
# Start the GUI
./.venv/bin/python -m advanced_vault.gui.vault_app
```

### Start the MCP Server

```bash
# Start Enclave MCP server
python -m advanced_vault.mcp_server
```

### Connect Claude Desktop

Add to your Claude Desktop MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "enclave": {
      "command": "python",
      "args": ["-m", "advanced_vault.mcp_server"]
    }
  }
}
```

Restart Claude Desktop. Now you can ask Claude about your documents — Enclave handles the rest.

### Index Documents (Python API)

```python
from advanced_vault.training import RAGIndex
import os

# Generate or load a 32-byte encryption key
master_key = os.urandom(32)  # In production, derive from password

# Create encrypted index
with RAGIndex(master_key=master_key) as index:
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

## Personal Data Vaults (New 🆕)

Enclave now organizes your documents into **semantic vault categories** with domain-specific AI adapters:

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
vault prosumer classify blood_test.pdf

# Classify an entire folder
vault prosumer classify-folder ~/Documents --recursive
```

### One-Click Adapter Training

Train a domain-specific AI on your documents:

```bash
# List training presets
vault prosumer presets list

# Train via GUI: Drop docs → Click "Train AI" → Done in 5-15 min
```

Each preset includes safety guardrails:
- **Health Advisor**: Never prescribes, always recommends seeing a doctor
- **Tax Assistant**: Shows calculations, suggests consulting a CPA
- **Legal Companion**: Summarizes only, never gives legal advice

### Encrypted Adapter Backup & Sharing

Your trained adapter contains learned patterns — not your raw documents. Back it up or share it safely:

```bash
# Export encrypted adapter
vault prosumer backup export ~/.vault/adapters/health.wdva \
  --name "My Health Advisor" --category health

# Import on another device
vault prosumer backup import ./health.enclave

# Verify integrity
vault prosumer backup verify ./health.enclave

# List all backups
vault prosumer backup list
```

**What's included**: Encrypted learned weights (WDVA format) + metadata.  
**What's NOT included**: Your raw documents, filenames, or personal data.

**Key principle**: `agent_query` returns synthesized answers, not raw documents. External AIs never see your actual content.

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

## Project Structure

```
slm-vault/
├── advanced_vault/          # Core application
│   ├── gui/                 # Desktop GUI (Flet)
│   ├── training/            # RAG index, embeddings, caching
│   ├── prosumer/            # Personal data vaults (Health, Finance, Legal, Personal)
│   ├── mcp_server/          # MCP server implementation
│   └── backend/             # Supabase integration (optional)
├── browser-extension/       # Browser extension
├── langchain-enclave/       # LangChain integration
├── docs/                    # Documentation
│   ├── architecture/        # Technical architecture
│   ├── deployment/          # Deployment guides
│   └── security/            # Security documentation
└── examples/                # Example scripts
```

## Requirements

- Python 3.10+
- macOS (Apple Silicon recommended), Windows, or Linux
- 8GB+ RAM (16GB+ recommended for local LLM)

### Optional Dependencies

```bash
# Apple Silicon acceleration
pip install mlx mlx-lm

# Advanced training: DPO, ORPO, GRPO, QAT (requires mlx-lm-lora)
pip install "enclave-vault[advanced-training]"

# Fast embeddings (ONNX)
pip install fastembed

# HNSW index (10-30x faster search)
pip install hnswlib

# Desktop GUI
pip install "flet[all]>=0.28.3,<0.29"
```

## Advanced Local Training

Enclave supports advanced training algorithms via `mlx-lm-lora` on Apple Silicon:

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
# Package a trained adapter
vault model package ~/.enclave/adapters/my_adapter ./my_adapter.enclave \
  --train-mode dpo --qat --password

# Unpack
vault model unpack ./my_adapter.enclave ~/.enclave/adapters/restored --password

# Verify integrity
vault model verify ./my_adapter.enclave --password
```

## Development

```bash
# Clone repository
git clone https://github.com/your-org/slm-vault
cd slm-vault

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

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
