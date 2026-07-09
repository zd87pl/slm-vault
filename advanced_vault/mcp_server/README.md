# Enclave MCP Server

Model Context Protocol (MCP) server that exposes the Enclave vault to AI agents like Claude Desktop and Cursor.

> **Fastest setup**: from the project root run `enclave mcp install` — it
> detects Claude Desktop / Cursor, uses your venv's Python automatically, and
> merges into the existing config without overwriting other servers. The
> manual steps below are only needed for unusual setups.

## Features

- **vault_store**: Store secrets and knowledge in the vault
- **vault_recall**: Query using natural language (automatic Smart Router)
- **vault_list_entries**: List all vault entries with filtering
- **vault_delete**: Delete entries by service name
- **vault_stats**: View vault statistics

## Installation

### 1. Install the package

```bash
# From the repo root (installs the `enclave` CLI, MCP server, and deps)
pip install -e .
```

### 2. Configure Claude Desktop

Edit your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/claude/claude_desktop_config.json`

Add the vault server:

```json
{
  "mcpServers": {
    "enclave": {
      "command": "/ABSOLUTE/PATH/TO/slm-vault/.venv/bin/python",
      "args": ["-m", "advanced_vault.mcp_server"],
      "env": {
        "VAULT_PATH": "/Users/YOUR_USERNAME/.vault"
      }
    }
  }
}
```

**Important**: use the absolute path to the Python inside the venv where you
installed Enclave (a bare `python` is not on Claude Desktop's PATH), and
replace `/Users/YOUR_USERNAME/.vault` with your actual home directory path.
`enclave mcp config` prints this JSON with the right paths filled in.

### 3. Restart Claude Desktop

After saving the configuration, completely quit and restart Claude Desktop.

## Usage Examples

### Storing Secrets

```
User: "Remember my Stripe API key is sk_live_ABC123XYZ789"

Claude: [calls vault_store with type="secret", service="stripe"]
✅ Stored stripe secret
Type: secret
Service: stripe
```

### Storing Knowledge

```
User: "Note: I chose Stripe because it has the best webhook infrastructure and developer experience"

Claude: [calls vault_store with type="knowledge"]
✅ Stored knowledge
Type: knowledge
Note: Knowledge will be available for fuzzy queries
```

### Querying Secrets (EXACT - Layer 1)

```
User: "What's my Stripe API key?"

Claude: [calls vault_recall]
✅ Found result
Strategy: exact
Layer: 1
Service: stripe

Result:
sk_live_ABC123XYZ789
```

### Querying Knowledge (FUZZY - Layer 2)

```
User: "Why did I choose Stripe?"

Claude: [calls vault_recall]
✅ Found result
Strategy: fuzzy
Layer: 2

Result:
I chose Stripe because it has the best webhook infrastructure and developer experience
```

### Hybrid Queries (Both Layers)

```
User: "Tell me everything about Stripe"

Claude: [calls vault_recall]
✅ Found result
Strategy: hybrid
Layers: [1, 2]
Service: stripe

Result:
[Combines exact API key from Layer 1 + context from Layer 2]
```

### Listing Entries

```
User: "Show me all my stored secrets"

Claude: [calls vault_list_entries]
Found 3 entries:

• stripe
  Type: secret
  Tags: payment, production
  Description: Stripe production API key
  Created: 2025-10-26 14:30

• github
  Type: secret
  Tags: git, production
  Created: 2025-10-26 14:31

• aws
  Type: secret
  Tags: cloud, production
  Created: 2025-10-26 14:32
```

### Vault Statistics

```
User: "Show me my vault stats"

Claude: [calls vault_stats]
📊 Vault Statistics

Layer 1 (Encrypted KV Store):
  Total entries: 3
  Services: aws, github, stripe
  Encryption: ChaCha20-Poly1305

Layer 2 (DoRA Knowledge):
  Initialized: False
  Status: Not configured
```

### Deleting Entries

```
User: "Delete my GitHub credentials"

Claude: [calls vault_delete with service="github"]
✅ Deleted entry for service: github
```

## Architecture

```
┌─────────────────────────────────────────────┐
│           Claude Desktop / Cursor           │
│          (AI Agent with MCP client)         │
└─────────────────┬───────────────────────────┘
                  │ MCP Protocol
                  │ (stdio transport)
┌─────────────────▼───────────────────────────┐
│          Personal Vault MCP Server          │
│  ┌───────────────────────────────────────┐  │
│  │         Smart Router                  │  │
│  │  - Pattern matching                   │  │
│  │  - Query classification               │  │
│  └───────────────────────────────────────┘  │
│         │              │              │      │
│      EXACT          FUZZY         HYBRID     │
│         │              │              │      │
│         ▼              ▼              ▼      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Layer 1  │  │ Layer 2  │  │  Both    │  │
│  │   (KV)   │  │  (DoRA)  │  │ Layers   │  │
│  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────┘
                  │
                  ▼
         ~/.vault/vault.db
      (Encrypted with ChaCha20)
```

## Security

- **Client-side encryption**: All secrets encrypted with ChaCha20-Poly1305
- **Master key**: 32-byte key stored at `~/.vault/master.key` (0600 permissions)
- **Zero hallucination**: Exact data never passes through LLM
- **Isolated storage**: Each vault has its own encryption key

## Troubleshooting

### MCP Server Not Showing in Claude Desktop

1. Check the config file path is correct for your OS
2. Ensure the JSON is valid (no trailing commas)
3. Make sure Python path is correct: `which python`
4. Check Claude Desktop logs for errors

### Import Errors

Make sure you're in the project directory:
```bash
cd /path/to/slm-vault
python -m advanced_vault.mcp_server
```

### Permission Denied on master.key

```bash
chmod 600 ~/.vault/master.key
```

## Development

### Running Locally

```bash
# Test the server
python -m advanced_vault.mcp_server

# Run with custom vault path
VAULT_PATH=/tmp/test_vault python -m advanced_vault.mcp_server
```

### Testing Tools

See `tests/test_server.py` for unit tests.

## Roadmap

- [x] Basic MCP server with tools
- [x] vault_store, vault_recall, vault_list, vault_delete
- [x] Smart Router integration
- [ ] Consent mechanism (Week 4)
- [ ] OS notifications for vault access
- [ ] Per-app permissions

See `advanced_vault/docs/ROADMAP.md` for complete development plan.
