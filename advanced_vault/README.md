# Advanced Vault Features

**Status:** 🚧 Active Development
**Branch:** advanced-vault-features
**Phase:** Foundation (Week 1-2)

---

## Overview

This directory contains advanced features for the WDVA (Weight-Delta Vault Adapter) system. These features build on top of the proven baseline in `src/` while adding world-class security and performance capabilities.

**Key Innovation:** Zero-knowledge AI context - semantic search over encrypted data where the AI understands your information but the server never sees it.

---

## Directory Structure

```
advanced_vault/
├── README.md                    # This file
├── __init__.py                  # Package initialization
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md          # Complete system architecture
│   ├── BASELINE.md              # Current working functionality
│   └── ROADMAP.md               # Development roadmap
│
├── core/                        # Core enhancements
│   ├── smart_router.py          # Query classification (exact vs fuzzy)
│   ├── hybrid_vault.py          # Unified vault interface
│   ├── incremental.py           # Incremental training
│   └── replay_buffer.py         # Anti-catastrophic-forgetting
│
├── encrypted_kv/                # Layer 1: Exact data (API keys)
│   ├── storage.py               # SQLite + E2EE operations
│   ├── models.py                # Entry schema, metadata
│   └── sync.py                  # Optional cloud sync
│
├── mcp_server/                  # MCP protocol integration
│   ├── server.py                # MCP server implementation
│   ├── tools.py                 # vault_store, vault_recall, etc.
│   ├── consent.py               # OS notification consent
│   └── permissions.py           # Per-app access control
│
├── homomorphic/                 # 🔬 Research: Encrypted search
│   ├── encrypted_similarity.py  # Similarity in encrypted space
│   ├── paillier.py              # Homomorphic encryption
│   └── dora_homomorphic.py      # Apply to DoRA weights
│
├── threshold_crypto/            # Team vaults
│   ├── shamir.py                # Shamir Secret Sharing
│   ├── team_vault.py            # Multi-party operations
│   └── key_rotation.py          # Proactive secret sharing
│
├── speculative/                 # Predictive caching
│   ├── predictor.py             # ML model for prediction
│   ├── cache_manager.py         # Decryption cache + TTL
│   └── features.py              # Context feature extraction
│
└── federated/                   # 🔬 Research: Federated learning
    ├── contribution.py          # Upload anonymized patterns
    ├── differential.py          # Differential privacy
    └── aggregation.py           # Server-side aggregation
```

---

## Key Features

### 1. Encrypted KV Store (Layer 1)
**Purpose:** Store exact data (API keys, passwords) without hallucination risk

```python
from advanced_vault.encrypted_kv import EncryptedKVStore

store = EncryptedKVStore(master_key)
store.put("stripe", "sk_live_ABC123", tags=["payment"])
key = store.get("stripe")
assert key == "sk_live_ABC123"  # Exact match, no LLM involved
```

**Status:** Week 1 (In Development)

---

### 2. Smart Router (Core)
**Purpose:** Automatically route queries to correct layer

```python
from advanced_vault.core import HybridVault

vault = HybridVault(master_key)

# Routes to Layer 1 (KV store)
vault.query("What's my Stripe API key?")

# Routes to Layer 2 (DoRA inference)
vault.query("Why did I choose Stripe?")

# Queries both layers
vault.query("Show me everything about Stripe")
```

**Status:** Week 2 (Planned)

---

### 3. MCP Integration
**Purpose:** Expose vault to AI agents (Claude, Cursor)

```python
# In Claude Desktop config
{
  "mcpServers": {
    "personal-vault": {
      "command": "python",
      "args": ["-m", "advanced_vault.mcp_server"]
    }
  }
}
```

**Privacy Innovation:**
- Claude gets answers, not raw data
- Consent required before each query
- Anthropic never sees vault contents

**Status:** Week 3-4 (Planned)

---

### 4. Threshold Crypto (Team Vaults)
**Purpose:** Shared knowledge where no single person holds all keys

```python
from advanced_vault.threshold_crypto import TeamVault

# 5 members, need any 3 to access
team_vault = TeamVault.create(
    members=["alice", "bob", "carol", "dave", "eve"],
    threshold=3
)

# Query requires 3 approvals
result = team_vault.query(
    query="What's our AWS key?",
    approvers=[alice, bob, carol]
)
```

**Status:** Week 7-8 (Planned)

---

### 5. Speculative Decryption
**Purpose:** Predict which vault user will query next, decrypt proactively

**Performance:**
- Before: 300ms (decrypt + inference)
- After: 50ms (cache hit)
- Cache hit rate: 70-80%

**Status:** Week 5-6 (Planned)

---

### 6. Homomorphic Search (Research)
**Purpose:** Search encrypted adapters WITHOUT full decryption

**Innovation:**
- Search 100 vaults: 5GB download → 50MB
- Latency: 30s → 500ms
- Novel contribution to field

**Status:** 🔬 Research Phase (Month 3-4)

---

## Installation

```bash
# Clone repository
git clone https://github.com/zd87pl/slm-vault.git
cd slm-vault

# Switch to feature branch
git checkout advanced-vault-features

# Install dependencies
pip install -r requirements.txt

# Run tests (when available)
pytest advanced_vault/tests/ -v
```

---

## Quick Start

### Example 1: Hybrid Vault (Week 2)

```python
from advanced_vault.core import HybridVault

# Initialize
vault = HybridVault(master_key="your-32-byte-key")

# Store exact data
vault.store(
    content="sk_live_ABC123",
    type="secret",
    service="stripe",
    tags=["payment", "production"]
)

# Store fuzzy knowledge
vault.store(
    content="Chose Stripe over PayPal for webhook reliability",
    type="knowledge",
    tags=["stripe", "decisions"]
)

# Query - auto-routes to correct layer
print(vault.query("What's my Stripe key?"))
# → "sk_live_ABC123" (from Layer 1)

print(vault.query("Why did I choose Stripe?"))
# → "You chose Stripe over PayPal..." (from Layer 2)
```

---

### Example 2: MCP Integration (Week 4)

```bash
# Install MCP server
pip install advanced_vault[mcp]

# Configure Claude Desktop
cat ~/.config/claude/config.json
{
  "mcpServers": {
    "personal-vault": {
      "command": "python",
      "args": ["-m", "advanced_vault.mcp_server"],
      "env": {
        "VAULT_PATH": "~/.vault"
      }
    }
  }
}

# Use in Claude
# User: "Remember my Stripe key is sk_live_ABC123"
# Claude: ✓ Stored in vault
#
# User: "What's my Stripe key?"
# [OS notification: "Claude wants to access vault"]
# [User: Allow]
# Claude: sk_live_ABC123
```

---

## Development

### Running Tests

```bash
# Unit tests
pytest advanced_vault/encrypted_kv/tests/ -v
pytest advanced_vault/core/tests/ -v

# Integration tests
pytest advanced_vault/tests/integration/ -v

# Benchmarks
python advanced_vault/benchmarks/latency.py
```

---

### Contributing

1. **Preserve Baseline:** Never modify `src/` without approval
2. **Write Tests:** All new code needs tests
3. **Benchmark:** Measure performance impact
4. **Document:** Update docs for API changes
5. **Security:** Get review for crypto changes

---

## Current Status

### Completed ✅
- [x] Branch created (advanced-vault-features)
- [x] Directory structure set up
- [x] Architecture documented (ARCHITECTURE.md)
- [x] Baseline documented (BASELINE.md)
- [x] Roadmap created (ROADMAP.md)

### In Progress 🚧
- [ ] Encrypted KV store implementation (Week 1)
- [ ] Smart router implementation (Week 2)
- [ ] Hybrid vault demo (Week 2)

### Planned 📋
- [ ] MCP server (Week 3-4)
- [ ] Consent mechanism (Week 4)
- [ ] Speculative decryption (Week 5-6)
- [ ] Team vaults (Week 7-8)
- [ ] Research features (Month 3-4)

---

## Performance Targets

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| **Encryption** | 2-5s | 1-2s | ⏳ |
| **Decryption** | 100ms | 50ms | ⏳ |
| **Inference** | 200ms | 150ms | ⏳ |
| **Total Latency** | 300ms | <100ms (cached) | ⏳ |
| **Search 100 Vaults** | N/A | <500ms | 🔬 |
| **Routing Accuracy** | N/A | 90%+ | ⏳ |

---

## Security Properties

### Baseline (Already Implemented)
✅ E2EE (XChaCha20-Poly1305)
✅ Ephemeral decryption
✅ Cryptographic deletion
✅ No plaintext persistence

### Advanced (In Development)
🚧 ProtonMail-level E2EE (Layer 1)
🚧 Zero-knowledge AI context (MCP)
📋 Threshold cryptography (teams)
🔬 Verifiable deletion certificates
🔬 Homomorphic operations

---

## Documentation

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Complete system architecture
- **[BASELINE.md](docs/BASELINE.md)** - Current working functionality
- **[ROADMAP.md](docs/ROADMAP.md)** - Development timeline
- **[API.md](docs/API.md)** - API reference (coming soon)
- **[SECURITY.md](docs/SECURITY.md)** - Security analysis (coming soon)

---

## Research Contributions

### Potential Papers
1. **"Semantic Search over Encrypted DoRA Adapters"**
   Novel: Homomorphic operations on low-rank neural weights

2. **"Threshold Cryptography for Neural Network Weights"**
   Novel: Shamir sharing applied to DoRA adapters

3. **"Federated Learning with Encrypted Low-Rank Adapters"**
   Novel: Differential privacy on DoRA weight updates

4. **"Zero-Knowledge AI Context via MCP"**
   Novel: Architecture for private AI agent interactions

---

## References

- DoRA Paper: [Weight-Decomposed Low-Rank Adaptation](https://arxiv.org/abs/2402.09353)
- MCP Protocol: [Model Context Protocol](https://github.com/anthropics/mcp)
- Shamir Secret Sharing: [Original Paper](https://dl.acm.org/doi/10.1145/359168.359176)
- Differential Privacy: [The Algorithmic Foundations](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf)

---

## License

Same as parent repository (see root LICENSE file)

---

## Contact

**Repository:** https://github.com/zd87pl/slm-vault
**Branch:** advanced-vault-features
**Issues:** https://github.com/zd87pl/slm-vault/issues

---

**Last Updated:** 2025-10-26
**Next Milestone:** Week 2 - Hybrid vault demo
