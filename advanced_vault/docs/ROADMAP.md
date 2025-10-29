# Development Roadmap: Advanced Vault Features

**Start Date:** 2025-10-26
**Branch:** advanced-vault-features
**Status:** 🚧 Planning Phase

---

## Guiding Principles

1. **Preserve Baseline:** Never break existing `src/` functionality
2. **Incremental:** Ship working features early and often
3. **Measured:** Benchmark every change (latency, security, UX)
4. **Research-Ready:** Document novel contributions for papers
5. **Production-Quality:** Real security, not demos

---

## Phase 1: Foundation (Weeks 1-2)

**Goal:** Hybrid vault with exact + fuzzy data storage

### Week 1: Encrypted KV Store
**Target:** Layer 1 - Store API keys without hallucination risk

**Tasks:**
- [ ] Design storage schema (SQLite + E2EE)
- [ ] Implement client-side encryption (XChaCha20-Poly1305)
- [ ] Build CRUD operations (create, read, update, delete)
- [ ] Add metadata search (by service, tags)
- [ ] Write comprehensive tests
- [ ] Benchmark performance

**Deliverables:**
```python
from advanced_vault.encrypted_kv import EncryptedKVStore

store = EncryptedKVStore(master_key)
store.put("stripe", "sk_live_ABC123", tags=["payment"])
key = store.get("stripe")  # Returns exact value
assert key == "sk_live_ABC123"  # No hallucination!
```

**Success Metrics:**
- ✅ Store 1000+ entries
- ✅ Sub-10ms retrieval
- ✅ Zero hallucination (exact match)
- ✅ Security audit passes

**Files Created:**
- `advanced_vault/encrypted_kv/__init__.py`
- `advanced_vault/encrypted_kv/storage.py`
- `advanced_vault/encrypted_kv/models.py`
- `advanced_vault/encrypted_kv/tests/test_storage.py`

---

### Week 2: Smart Router
**Target:** Automatic query classification (exact vs fuzzy)

**Tasks:**
- [ ] Build pattern-based classifier
- [ ] Implement query routing logic
- [ ] Add service name extraction
- [ ] Create unified query interface
- [ ] Write routing tests
- [ ] Measure accuracy

**Deliverables:**
```python
from advanced_vault.core import SmartRouter, HybridVault

vault = HybridVault(master_key)

# Auto-routes to Layer 1 (exact)
vault.query("What's my Stripe API key?")  # → KV store

# Auto-routes to Layer 2 (fuzzy)
vault.query("Why did I choose Stripe?")  # → DoRA inference

# Queries both layers
vault.query("Show me everything about Stripe")  # → Hybrid
```

**Success Metrics:**
- ✅ 90%+ routing accuracy
- ✅ <5ms routing overhead
- ✅ Works with 10+ services

**Files Created:**
- `advanced_vault/core/__init__.py`
- `advanced_vault/core/smart_router.py`
- `advanced_vault/core/hybrid_vault.py`
- `advanced_vault/core/tests/test_router.py`

---

### Week 2: Integration Demo
**Target:** End-to-end hybrid vault demo

**Tasks:**
- [ ] Create `examples/advanced/hybrid_vault_demo.py`
- [ ] Demonstrate exact + fuzzy queries
- [ ] Show routing transparency
- [ ] Record video demo
- [ ] Write blog post

**Demo Script:**
```python
# 1. Store mixed data
vault.store("sk_live_ABC123", type="secret", service="stripe")
vault.store("Chose Stripe for webhook reliability", type="knowledge")

# 2. Query exact data
print(vault.query("What's my Stripe key?"))
# → "sk_live_ABC123" (from KV store)

# 3. Query fuzzy knowledge
print(vault.query("Why did I choose Stripe?"))
# → "You chose Stripe for webhook reliability..." (from DoRA)

# 4. Combined query
print(vault.query("Tell me about my Stripe setup"))
# → Combines KV + DoRA results
```

**Success Metrics:**
- ✅ Demo runs without errors
- ✅ Clear routing visualization
- ✅ User understands hybrid approach

---

## Phase 2: MCP Integration (Weeks 3-4)

**Goal:** Expose vault to AI agents (Claude, Cursor)

### Week 3: MCP Server Implementation
**Target:** Basic MCP server with tools

**Tasks:**
- [ ] Set up MCP server boilerplate
- [ ] Implement `vault_store` tool
- [ ] Implement `vault_recall` tool
- [ ] Implement `vault_list_entries` tool
- [ ] Test with Claude Desktop
- [ ] Test with Cursor

**Deliverables:**
```python
# ~/.config/claude/config.json
{
  "mcpServers": {
    "personal-vault": {
      "command": "python",
      "args": ["-m", "advanced_vault.mcp_server"],
      "env": {"VAULT_PATH": "~/.vault"}
    }
  }
}
```

**MCP Tools:**
```
vault_store(content, type, service, tags)
vault_recall(query)
vault_list_entries(tag)
vault_delete(entry_id)
```

**Success Metrics:**
- ✅ Claude Desktop can store/query
- ✅ Cursor can store/query
- ✅ <500ms MCP round-trip

**Files Created:**
- `advanced_vault/mcp_server/__init__.py`
- `advanced_vault/mcp_server/server.py`
- `advanced_vault/mcp_server/tools.py`
- `advanced_vault/mcp_server/tests/test_server.py`

---

### Week 4: Consent Mechanism
**Target:** User approval before vault access

**Tasks:**
- [ ] Implement OS notification system
- [ ] Build permission database
- [ ] Add per-app consent UI
- [ ] Create "Always Allow" option
- [ ] Test deny scenarios
- [ ] Measure UX friction

**Deliverables:**
```python
# OS notification when app queries vault
┌────────────────────────────────────┐
│  Cursor wants to access your vault │
│                                     │
│  Query: "What's my Stripe key?"    │
│                                     │
│  [Allow Once] [Always] [Deny]      │
└────────────────────────────────────┘
```

**Consent Rules:**
```python
# User configures per-app permissions
vault.permissions.set("claude", auto_approve=True)
vault.permissions.set("cursor", auto_approve=True)
vault.permissions.set("unknown", require_approval=True)
```

**Success Metrics:**
- ✅ Notification < 100ms
- ✅ User understands permission request
- ✅ Denial blocks access correctly

**Files Created:**
- `advanced_vault/mcp_server/consent.py`
- `advanced_vault/mcp_server/permissions.py`
- `advanced_vault/mcp_server/notifications.py`

---

### Week 4: Integration Demo
**Target:** Claude queries vault with consent

**Demo Video Script:**
1. Install MCP server
2. Store secret via Claude: "Remember my Stripe key is sk_live_ABC123"
3. Query via Claude: "What's my Stripe key?"
4. Show consent notification
5. Approve → Claude gets key
6. Store knowledge via Cursor: "I chose Stripe for webhooks"
7. Query via Cursor: "Why did I choose Stripe?"
8. Show Anthropic never saw raw data (network logs)

**Success Metrics:**
- ✅ 5-minute setup time
- ✅ Zero failures in demo
- ✅ Clear privacy benefit shown

---

## Phase 3: Performance (Weeks 5-6)

**Goal:** Sub-100ms perceived latency

### Week 5: Speculative Decryption
**Target:** Predict and pre-decrypt likely vaults

**Tasks:**
- [ ] Build lightweight prediction model
- [ ] Extract context features (time, app, query history)
- [ ] Implement decryption cache
- [ ] Add TTL expiration
- [ ] Benchmark cache hit rate
- [ ] Measure latency improvement

**Deliverables:**
```python
# Runs in background
vault.start_prediction_engine()

# Predicts based on context
predictions = [
    ("work_vault", 0.85),  # 85% likely, decrypt now
    ("api_keys", 0.72),    # 72% likely, decrypt now
    ("personal", 0.23)     # 23% likely, skip
]

# User queries → instant if predicted correctly
result = vault.query("...")  # 50ms (was 300ms)
```

**Success Metrics:**
- ✅ 70%+ cache hit rate
- ✅ 50ms average latency (cached)
- ✅ <10MB memory overhead
- ✅ <5% CPU usage (background)

**Files Created:**
- `advanced_vault/speculative/__init__.py`
- `advanced_vault/speculative/predictor.py`
- `advanced_vault/speculative/cache_manager.py`
- `advanced_vault/speculative/features.py`

---

### Week 6: Benchmark Suite
**Target:** Comprehensive performance measurements

**Metrics Tracked:**
```
Latency:
- Encryption time
- Decryption time
- Inference time
- End-to-end query time
- Cache hit/miss latency

Throughput:
- Queries per second
- Concurrent users supported
- Max vault size

Memory:
- Peak memory usage
- Cache memory overhead
- GPU memory (inference)

Accuracy:
- Routing accuracy (exact vs fuzzy)
- Prediction accuracy (cache hits)
- Query success rate
```

**Deliverables:**
- Automated benchmark suite
- Performance dashboard
- Before/after comparison
- Regression detection

**Files Created:**
- `advanced_vault/benchmarks/`
- `advanced_vault/benchmarks/latency.py`
- `advanced_vault/benchmarks/throughput.py`
- `advanced_vault/benchmarks/accuracy.py`

---

## Phase 4: Team Features (Weeks 7-8)

**Goal:** Shared team vaults with threshold crypto

### Week 7: Shamir Secret Sharing
**Target:** Split vault keys across team members

**Tasks:**
- [ ] Implement Shamir Secret Sharing
- [ ] Build key split/combine logic
- [ ] Add member management
- [ ] Implement threshold policies
- [ ] Test with 3-of-5, 2-of-3 scenarios
- [ ] Measure overhead

**Deliverables:**
```python
from advanced_vault.threshold_crypto import TeamVault

# Create team vault (5 members, need any 3)
team_vault = TeamVault.create(
    members=["alice", "bob", "carol", "dave", "eve"],
    threshold=3
)

# Query requires 3 members' approval
result = team_vault.query(
    query="What's our AWS key?",
    approvers=[alice, bob, carol]  # 3 of 5
)
```

**Success Metrics:**
- ✅ Support 10+ members
- ✅ <100ms overhead per approver
- ✅ Key shares secure
- ✅ Works with any threshold

**Files Created:**
- `advanced_vault/threshold_crypto/__init__.py`
- `advanced_vault/threshold_crypto/shamir.py`
- `advanced_vault/threshold_crypto/team_vault.py`

---

### Week 8: Key Rotation
**Target:** Update keys without re-encrypting data

**Tasks:**
- [ ] Implement proactive secret sharing
- [ ] Build key rotation protocol
- [ ] Add member add/remove without re-encryption
- [ ] Test rotation scenarios
- [ ] Document best practices

**Deliverables:**
```python
# Add new member without re-encrypting
team_vault.add_member("frank")  # Reshares secrets

# Remove member without re-encrypting
team_vault.remove_member("eve")  # Reshares among remaining

# Rotate keys periodically
team_vault.rotate_keys()  # Proactive security
```

**Success Metrics:**
- ✅ Add/remove <1 second
- ✅ No data re-encryption needed
- ✅ Forward secrecy maintained

---

## Phase 5: Research Features (Months 3-4)

**Goal:** Novel contributions for academic papers

### Homomorphic Encrypted Search
**Status:** 🔬 Research Phase

**Challenge:**
Search 100 encrypted adapters without decrypting all of them.

**Approach:**
1. Leverage DoRA's low-rank structure (A × B)
2. Use Paillier homomorphic encryption
3. Compute similarity in encrypted space
4. Only decrypt if threshold exceeded

**Expected Impact:**
- Search time: 30s → 500ms
- Bandwidth: 5GB → 50MB
- Novel contribution to field

**Timeline:** Month 3-4

---

### Verifiable Deletion
**Status:** 🔬 Production-Ready

**Goal:**
Cryptographic proof that data was deleted (GDPR compliance).

**Approach:**
1. HSM signature on key destruction
2. Merkle proof of key absence
3. Append-only audit ledger
4. Third-party verification

**Expected Impact:**
- GDPR Article 17 compliance
- HIPAA audit trails
- Legal defensibility

**Timeline:** Month 3

---

### Federated Learning
**Status:** 🔬 Research Phase

**Goal:**
Improve routing accuracy via collective intelligence without sharing data.

**Approach:**
1. Extract anonymized usage patterns
2. Add differential privacy (Laplacian noise)
3. Aggregate at server
4. Users download improved models

**Expected Impact:**
- Routing accuracy: 70% → 95%
- New users benefit immediately
- No privacy compromise

**Timeline:** Month 4

---

## Milestones

### Milestone 1: Foundation Complete (Week 2)
- ✅ Encrypted KV store working
- ✅ Smart router 90%+ accurate
- ✅ Hybrid demo runs successfully
- ✅ All tests passing

### Milestone 2: MCP Integration (Week 4)
- ✅ Claude Desktop integration
- ✅ Cursor integration
- ✅ Consent mechanism working
- ✅ Demo video published

### Milestone 3: Performance (Week 6)
- ✅ Sub-100ms latency (cached)
- ✅ 70%+ cache hit rate
- ✅ Benchmark suite complete
- ✅ Performance report published

### Milestone 4: Team Features (Week 8)
- ✅ Threshold crypto working
- ✅ Key rotation implemented
- ✅ 10+ member support
- ✅ Team demo published

### Milestone 5: Research (Month 4)
- ✅ Homomorphic search prototype
- ✅ Verifiable deletion production-ready
- ✅ Federated learning tested
- ✅ Paper(s) submitted

---

## Resource Requirements

### Development
- **Time:** 3-4 months (one developer)
- **Skills:** Python, cryptography, ML, distributed systems
- **Tools:** PyCharm/VSCode, pytest, Docker

### Infrastructure
- **Local:** M-series Mac or Linux workstation
- **Cloud:** RunPod A100 (already provisioned)
- **Storage:** 100GB for experiments
- **Cost:** ~$200/month (RunPod + storage)

### Research
- **Papers to read:** 20-30 (crypto, federated learning, MPC)
- **Experiments:** 50-100 runs
- **Hardware:** A100 GPU for benchmarks

---

## Risk Mitigation

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking baseline | High | Lock tests, separate branch |
| Homomorphic search fails | Medium | Fall back to full decrypt |
| Cache pollution | Low | LRU eviction, memory limits |
| Key rotation bugs | High | Extensive testing, audit |

### Schedule Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Research takes longer | Medium | Ship incremental features |
| MCP spec changes | Low | Monitor MCP repo closely |
| Team features complex | High | Simplify to 2-of-3 first |

### Security Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Side-channel attacks | High | Security audit (Phase 5) |
| Key leakage | Critical | HSM, secure enclaves |
| Consent bypass | High | Penetration testing |

---

## Success Criteria

### Technical Success
- [ ] All baseline tests still pass
- [ ] Sub-100ms latency (80% queries)
- [ ] 90%+ routing accuracy
- [ ] Zero security vulnerabilities
- [ ] 10k+ lines of test coverage

### Product Success
- [ ] Claude Desktop integration demo
- [ ] Cursor integration demo
- [ ] Team vault with 5+ members
- [ ] 1000+ encrypted entries per user
- [ ] Blog post with 1k+ views

### Research Success
- [ ] Novel homomorphic search algorithm
- [ ] Conference paper submitted
- [ ] Patent application filed
- [ ] Open-source release (1k+ stars)

---

## Next Actions

### Immediate (This Week)
1. ✅ Create branch: advanced-vault-features
2. ✅ Set up directory structure
3. ✅ Write architecture docs
4. [ ] Implement encrypted KV store
5. [ ] Write KV store tests

### Next Week
6. [ ] Implement smart router
7. [ ] Create hybrid vault demo
8. [ ] Record demo video
9. [ ] Publish blog post

### Next Month
10. [ ] Build MCP server
11. [ ] Implement consent mechanism
12. [ ] Test with Claude + Cursor
13. [ ] Optimize performance

---

## Communication Plan

### Internal Updates
- Weekly progress reports (this document)
- Git commits with detailed messages
- Test coverage reports

### External Communication
- Blog post (Phase 1 complete)
- Demo videos (each phase)
- Conference paper (Phase 5)
- Open-source release (Phase 5)

---

## References

- **Baseline:** See `BASELINE.md`
- **Architecture:** See `ARCHITECTURE.md`
- **Repository:** https://github.com/zd87pl/slm-vault
- **Branch:** advanced-vault-features

---

**Last Updated:** 2025-10-26
**Next Review:** 2025-11-02 (weekly)
