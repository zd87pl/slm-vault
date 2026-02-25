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

- **Local RAG**: Drop documents → instantly queryable via semantic search
- **MCP Integration**: Works with Claude Desktop, Cursor, Copilot, and any MCP client
- **Encrypted Storage**: ChaCha20-Poly1305 encryption for all data
- **Activity Logging**: See every command from every AI agent
- **Per-Agent Permissions**: Control what each AI can access
- **Local Inference**: MLX-powered LLM on Apple Silicon (optional)
- **Adapter Training**: Fine-tune local models on your documents (optional)

## Quick Start

### Installation

```bash
# Install from PyPI
pip install enclave-vault

# Or install with Apple Silicon support
pip install enclave-vault[mlx]
```

### Start the MCP Server

```bash
# Start Enclave MCP server
enclave-mcp
```

### Connect Claude Desktop

Add to your Claude Desktop MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "enclave": {
      "command": "enclave-mcp"
    }
  }
}
```

Restart Claude Desktop. Now you can ask Claude about your documents — Enclave handles the rest.

### Index Documents

```python
from advanced_vault.training import RAGIndex

# Create index
index = RAGIndex()

# Add documents
index.add_document(
    name="Q3 Report",
    content=open("q3_report.pdf").read()
)

# Search
results = index.search("What was Q3 revenue?")
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
│  (Embeddings) │  │   (MLX)       │  │ (ChaCha20)        │
└───────────────┘  └───────────────┘  └───────────────────┘
```

## Privacy Model

1. **Your data stays local**: Documents are indexed and stored on your device
2. **Encryption at rest**: All data encrypted with ChaCha20-Poly1305
3. **Synthesized responses**: External AIs get answers, not raw documents
4. **Consent required**: Every access requires explicit permission
5. **Full audit trail**: See exactly what each AI accessed and when

## Requirements

- Python 3.10+
- macOS (Apple Silicon recommended) or Linux
- 8GB+ RAM (16GB+ recommended for local LLM)

### Optional

- MLX for Apple Silicon acceleration
- sentence-transformers for embeddings
- flet for desktop GUI

## Development

```bash
# Clone repository
git clone https://github.com/enclave-ai/enclave-vault
cd enclave-vault

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
```

## Documentation

- [MCP Integration Guide](docs/MCP_INTEGRATION.md)
- [RAG Index API](docs/RAG_INDEX.md)
- [MLX DoRA Architecture](docs/MLX_DORA_ARCHITECTURE.md)
- [Security Model](docs/SECURITY.md)

## Roadmap

- [x] RAG indexing with semantic search
- [x] MCP server with agent commands
- [x] Encrypted vault storage
- [x] Activity logging
- [ ] Desktop GUI (Flet)
- [ ] Browser extension enhancements
- [ ] Multi-device sync (encrypted)
- [ ] Adapter sharing

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 - see [LICENSE](LICENSE)

---

**Enclave**: Privacy-first AI. Your data, your control.
