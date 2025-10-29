# Advanced Vault Architecture

## Overview

This directory contains advanced features for the WDVA (Weight-Delta Vault Adapter) system, building on top of the proven baseline implementation in `src/`.

**Design Principle:** Preserve existing functionality while adding world-class security and performance features.

---

## Current Baseline (Preserved in `src/`)

### What Works Today
- ✅ DoRA adapter training and encryption
- ✅ Ephemeral in-memory inference
- ✅ Cryptographic deletion (key destruction)
- ✅ RunPod serverless deployment
- ✅ Combined train_and_encrypt workflow
- ✅ Chat template support for TinyLlama

### Baseline Performance
- Encryption: ~2-5 seconds
- Decryption: ~100ms
- Inference: ~200ms
- Total latency: ~300ms

### Security Model
- XChaCha20-Poly1305 authenticated encryption
- 32-byte keys stored in system keychain
- Ephemeral decryption (never persists to disk)
- Right-to-be-forgotten via key destruction

---

## Advanced Features Architecture

### Layer 1: Encrypted KV Store (API Keys, Passwords)
**Location:** `advanced_vault/encrypted_kv/`

**Purpose:** Store exact data (API keys, passwords) with zero hallucination risk

**Components:**
```
encrypted_kv/
├── __init__.py
├── storage.py          # Local SQLite + E2EE operations
├── models.py           # Entry schema, metadata
├── sync.py             # Optional: Cloud sync (ProtonMail model)
└── tests/
```

**Key Features:**
- Client-side only encryption (server never sees plaintext)
- Per-entry unique nonces (semantic security)
- Metadata searchable (service name, tags)
- Actual secrets encrypted
- XChaCha20-Poly1305 (same as DoRA)

**Storage Format:**
```json
{
  "id": "uuid-1",
  "type": "api_key",
  "service": "stripe",
  "encrypted_data": "0x8a7f...",
  "nonce": "0x9b2c...",
  "tags": ["payment", "production"],
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Security Properties:**
- ProtonMail-level E2EE
- Zero-knowledge server (optional cloud sync)
- Exact retrieval (no LLM = no hallucination)

---

### Layer 2: Enhanced DoRA Knowledge (Existing + Improvements)
**Location:** `src/` (baseline) + `advanced_vault/core/` (enhancements)

**Purpose:** Semantic search and reasoning over encrypted personal knowledge

**Enhancements:**
```
core/
├── __init__.py
├── smart_router.py     # Query classifier (exact vs fuzzy)
├── incremental.py      # Incremental training without forgetting
├── replay_buffer.py    # Anti-catastrophic-forgetting
└── tests/
```

**Key Features:**
- Incremental training (low LR, replay buffer)
- Smart query routing (Layer 1 vs Layer 2)
- Multi-domain adapters (health, work, finance)

---

### Layer 3: Homomorphic Encrypted Search (Research)
**Location:** `advanced_vault/homomorphic/`

**Purpose:** Search encrypted adapters WITHOUT full decryption

**Components:**
```
homomorphic/
├── __init__.py
├── encrypted_similarity.py  # Compute similarity in encrypted space
├── paillier.py              # Homomorphic encryption primitives
├── dora_homomorphic.py      # Apply to DoRA low-rank structure
└── tests/
```

**Research Challenge:**
- Leverage DoRA's low-rank structure (A × B)
- Compute approximate similarity via encrypted matrix products
- Only decrypt if threshold exceeded

**Expected Performance:**
- Search 100 adapters: 50MB download → 500KB
- Latency: 300ms → 50ms (most queries)

**Status:** 🔬 Research phase (novel contribution)

---

### Layer 4: MCP Server Integration
**Location:** `advanced_vault/mcp_server/`

**Purpose:** Expose vault to AI agents (Claude, Cursor) via MCP protocol

**Components:**
```
mcp_server/
├── __init__.py
├── server.py           # MCP server implementation
├── tools.py            # vault_store, vault_recall, etc.
├── consent.py          # OS notification consent mechanism
├── permissions.py      # Per-app access control
└── tests/
```

**MCP Tools:**
```python
@mcp.tool()
async def vault_store(content: str, data_type: str, tags: list[str])

@mcp.tool()
async def vault_recall(query: str) -> str

@mcp.tool()
async def vault_list_entries(tag: str = None) -> str

@mcp.tool()
async def vault_delete(entry_id: str)
```

**Consent Flow:**
1. App requests vault access
2. OS notification pops up
3. User approves/denies
4. Permission stored per-app

**Privacy Innovation:**
- AI agent gets answers, not source data
- Claude never sees vault contents
- Zero-knowledge AI context

---

### Layer 5: Threshold Cryptography (Team Vaults)
**Location:** `advanced_vault/threshold_crypto/`

**Purpose:** Shared team knowledge where no single person holds all keys

**Components:**
```
threshold_crypto/
├── __init__.py
├── shamir.py           # Shamir Secret Sharing
├── team_vault.py       # Multi-party vault operations
├── key_rotation.py     # Proactive secret sharing
└── tests/
```

**Key Features:**
- Split vault key into N shares (e.g., 5)
- Require K shares to decrypt (e.g., 3 of 5)
- Members can leave without re-encrypting
- Query requires multi-party approval

**Use Cases:**
- Startup secrets (2 of 3 founders)
- Healthcare (doctor + nurse)
- Legal (3 of 5 partners)

**Status:** 🔬 Novel application of threshold crypto to neural weights

---

### Layer 6: Speculative Decryption
**Location:** `advanced_vault/speculative/`

**Purpose:** Predict which vault user will query next, decrypt proactively

**Components:**
```
speculative/
├── __init__.py
├── predictor.py        # ML model for vault prediction
├── cache_manager.py    # Decryption cache with TTL
├── features.py         # Time, app, context extraction
└── tests/
```

**Prediction Features:**
```python
{
    "time_of_day": "09:30",      # Work hours → work vault
    "day_of_week": "Monday",     # Weekday → professional
    "active_app": "Cursor",      # IDE → code vault
    "last_query": "database",    # Context carryover
    "query_interval": "2min"     # Rapid → same vault
}
```

**Expected Performance:**
- Cache hit rate: 70-80%
- Perceived latency: 300ms → 50ms

---

### Layer 7: Federated Learning
**Location:** `advanced_vault/federated/`

**Purpose:** Learn from collective patterns without sharing data

**Components:**
```
federated/
├── __init__.py
├── contribution.py     # Upload anonymized patterns
├── differential.py     # Add Laplacian noise (privacy)
├── aggregation.py      # Server-side model aggregation
└── tests/
```

**Privacy Preservation:**
- Extract only metadata patterns (no content)
- Differential privacy (add noise)
- User downloads improved router model

**Benefit:**
- Routing accuracy: 70% → 95%
- New users benefit from community

**Status:** 🔬 First encrypted vault with federated learning

---

### Layer 8: Verifiable Deletion
**Location:** `advanced_vault/core/audit.py`

**Purpose:** Cryptographic proof of deletion (GDPR compliance)

**Components:**
```python
class VerifiableDeletion:
    def delete_with_proof(vault_id) -> DeletionCertificate
    def verify_deletion(cert) -> bool
```

**Proof Components:**
- HSM signature (hardware security module)
- Merkle proof (key no longer exists in keyring)
- Immutable ledger entry
- Timestamp + vault ID

**Compliance:**
- GDPR Article 17 (Right to Erasure)
- HIPAA audit trails
- Legal discovery

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
**Goal:** Basic hybrid vault (Layer 1 + Layer 2 routing)

- [x] Create branch and directory structure
- [ ] Implement encrypted KV store (Layer 1)
- [ ] Implement smart router (query classifier)
- [ ] Write integration tests
- [ ] Update examples to demonstrate hybrid queries

**Deliverable:** Demo showing:
1. Store API key (exact) vs knowledge (fuzzy)
2. Query "What's my Stripe key?" → Layer 1 (exact)
3. Query "Why did I choose Stripe?" → Layer 2 (fuzzy)
4. Query "Show me everything about Stripe" → Both layers

### Phase 2: MCP Integration (Weeks 3-4)
**Goal:** Expose vault to AI agents

- [ ] Implement MCP server
- [ ] Build consent mechanism (OS notifications)
- [ ] Per-app permissions
- [ ] Claude Desktop integration demo
- [ ] Cursor integration demo

**Deliverable:** Video showing:
1. Store secrets via Claude
2. Claude queries vault (with consent)
3. Anthropic never sees raw data

### Phase 3: Performance (Weeks 5-6)
**Goal:** Sub-100ms latency

- [ ] Implement speculative decryption
- [ ] Build prediction model
- [ ] Cache manager with TTL
- [ ] Benchmark improvements

**Deliverable:** Latency report:
- Before: 300ms average
- After: 50ms average (80% cache hit rate)

### Phase 4: Team Features (Weeks 7-8)
**Goal:** Shared team vaults

- [ ] Implement Shamir Secret Sharing
- [ ] Team vault creation/management
- [ ] Multi-party query approval
- [ ] Key rotation

**Deliverable:** Demo:
- 3-person team, 2-of-3 threshold
- Query requires 2 approvals
- Member leaves, no re-encryption needed

### Phase 5: Research Features (Months 3-4)
**Goal:** Novel contributions

- [ ] Homomorphic encrypted search
- [ ] Verifiable deletion certificates
- [ ] Federated learning

**Deliverable:**
- Research paper draft
- Patent applications
- Conference submission

---

## Development Guidelines

### Code Organization
```
slm-vault/
├── src/                          # BASELINE (don't modify)
│   ├── dora_crypto.py
│   ├── ephemeral_inference.py
│   ├── train_dora.py
│   └── rp_handler.py
│
├── advanced_vault/               # NEW FEATURES
│   ├── core/
│   │   ├── smart_router.py      # Routes queries to correct layer
│   │   ├── incremental.py       # Incremental training
│   │   └── audit.py             # Verifiable deletion
│   │
│   ├── encrypted_kv/            # Layer 1: Exact data
│   ├── homomorphic/             # Layer 3: Encrypted search
│   ├── mcp_server/              # Layer 4: MCP integration
│   ├── threshold_crypto/        # Layer 5: Team vaults
│   ├── speculative/             # Layer 6: Predictive caching
│   └── federated/               # Layer 7: Federated learning
│
├── examples/
│   ├── privacy_demo_runpod.py   # BASELINE (working)
│   └── advanced/                # NEW EXAMPLES
│       ├── hybrid_vault_demo.py
│       ├── mcp_integration.py
│       └── team_vault_demo.py
│
└── tests/
    ├── test_baseline.py         # Lock baseline behavior
    └── advanced/                # New tests
```

### Testing Strategy
1. **Lock baseline:** Comprehensive tests ensure `src/` behavior never changes
2. **Integration tests:** Test advanced features with baseline
3. **Gradual rollout:** Advanced features opt-in, not forced

### Git Workflow
```bash
# Main branches
main                    # Stable baseline (working demo)
dora-wdva-implementation  # Original feature branch (merge to main)
advanced-vault-features   # This branch (advanced features)

# Feature branches (off advanced-vault-features)
feature/encrypted-kv
feature/mcp-server
feature/homomorphic-search
```

### Merge Strategy
1. Keep `main` stable (only merge proven features)
2. Develop on `advanced-vault-features`
3. When ready, merge specific features to `main`
4. Never break existing `privacy_demo_runpod.py`

---

## Technical Specifications

### Encryption Standards
- **Symmetric:** XChaCha20-Poly1305 (256-bit keys)
- **KDF:** Argon2id (memory-hard, side-channel resistant)
- **Nonces:** 192-bit random (collision-resistant)
- **Signatures:** Ed25519 (for audit trail)

### Performance Targets
| Metric | Baseline | Target |
|--------|----------|--------|
| **Encryption** | 2-5s | 1-2s |
| **Decryption** | 100ms | 50ms |
| **Inference** | 200ms | 150ms |
| **Total Latency** | 300ms | <100ms (cached) |
| **Search 100 Vaults** | N/A | <500ms |

### Security Properties
- ✅ E2EE (server never sees plaintext)
- ✅ Forward secrecy (old data safe if key leaked)
- ✅ Verifiable deletion (cryptographic proof)
- ✅ Zero-knowledge AI (agents don't see source)
- ✅ Threshold sharing (no single point of failure)

---

## API Design

### Unified Interface
```python
from advanced_vault import Vault

# Initialize vault
vault = Vault(master_key="...", mode="hybrid")

# Store data (auto-routes to correct layer)
vault.store("sk_live_ABC123", type="secret", service="stripe")
vault.store("Chose Stripe for webhooks", type="knowledge", tags=["stripe"])

# Query (auto-routes)
vault.query("What's my Stripe key?")        # → Layer 1 (exact)
vault.query("Why did I choose Stripe?")     # → Layer 2 (fuzzy)
vault.query("Show everything about Stripe") # → Both layers
```

### MCP Integration
```python
# In Claude Desktop config
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
```

---

## Success Metrics

### Technical
- [ ] Sub-100ms latency (80% of queries)
- [ ] Zero plaintext leakage (security audit)
- [ ] 95%+ routing accuracy (after federated learning)
- [ ] 10+ concurrent team members supported

### Product
- [ ] Working MCP integration (Claude + Cursor)
- [ ] 1000+ encrypted entries per user
- [ ] Team vault with 5+ members
- [ ] Verifiable deletion certificate generated

### Research
- [ ] Novel homomorphic search algorithm
- [ ] Conference paper accepted (ICML/NeurIPS)
- [ ] Patent filed on threshold DoRA
- [ ] Open-source release (10k+ GitHub stars)

---

## References

### Academic Papers
- DoRA: Weight-Decomposed Low-Rank Adaptation (NVIDIA, ICML 2024)
- Shamir Secret Sharing (Adi Shamir, 1979)
- Differential Privacy (Dwork et al., 2006)
- Federated Learning (McMahan et al., 2017)

### Similar Projects
- ProtonMail (E2EE email)
- 1Password (encrypted password manager)
- Signal (E2EE messaging)
- Bitwarden (open-source secrets)

### Novel Contributions
1. **Semantic search over encrypted neural adapters**
2. **Threshold cryptography for DoRA weights**
3. **Zero-knowledge AI context via MCP**
4. **Federated learning with encrypted adapters**

---

## Contact & Contributions

**Project Lead:** [Your Name]
**Repository:** https://github.com/zd87pl/slm-vault
**Branch:** advanced-vault-features
**Status:** 🚧 Active Development

**Contribution Guidelines:**
1. All PRs must include tests
2. Security changes require review
3. Performance changes require benchmarks
4. Never modify `src/` without reason
