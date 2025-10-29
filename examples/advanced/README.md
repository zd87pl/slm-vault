# Advanced Vault Examples

Demonstrations of the advanced vault features (Layer 1 + Layer 2 hybrid system).

## Overview

The advanced vault system combines two layers:

- **Layer 1 (Encrypted KV)**: Exact data storage (API keys, passwords, credentials)
  - Client-side encryption (ChaCha20-Poly1305)
  - Sub-10ms lookups
  - Zero hallucination risk
  - ProtonMail-style E2EE

- **Layer 2 (DoRA Knowledge)**: Contextual knowledge storage
  - Encrypted DoRA adapters
  - LLM inference for fuzzy queries
  - Private inference (local or RunPod)

- **Smart Router**: Automatic query classification
  - EXACT → Layer 1 (KV)
  - FUZZY → Layer 2 (DoRA)
  - HYBRID → Both layers

## Demos

### 1. Encrypted KV Demo
**File**: `encrypted_kv_demo.py`

Demonstrates Layer 1 only:
```bash
python examples/advanced/encrypted_kv_demo.py
```

**What it shows**:
- Store API keys with client-side encryption
- Retrieve secrets with exact match (no LLM)
- Search by metadata (tags, service, date)
- Vault statistics

**No requirements** - works standalone.

---

### 2. Hybrid Vault Demo
**File**: `hybrid_vault_demo.py`

Demonstrates Smart Router + Layer 1:
```bash
python examples/advanced/hybrid_vault_demo.py
```

**What it shows**:
- Smart Router query classification
- Layer 1 exact queries (API keys)
- Routing explanations
- Query confidence scores

**No requirements** - Layer 2 disabled for this demo.

---

### 3. Unified Vault Demo ⭐
**File**: `unified_vault_demo.py`

**Complete system demo** - Layer 1 + Layer 2 hybrid:
```bash
# Run without RunPod (simulated Layer 2)
python examples/advanced/unified_vault_demo.py

# Or with real RunPod inference
export RUNPOD_API_KEY=your_key
export RUNPOD_ENDPOINT_ID=your_endpoint_id
python examples/advanced/unified_vault_demo.py
```

**What it shows**:
1. **Layer 1**: Store and retrieve API keys (Stripe, GitHub, AWS)
2. **EXACT queries**: "What's my Stripe API key?" → Layer 1 (sub-10ms)
3. **FUZZY queries**: "Why did I choose Stripe?" → Layer 2 (DoRA)
4. **HYBRID queries**: "Show me everything about Stripe" → Both layers
5. **Vault statistics**: Entries, services, layer status

**Requirements** (optional):
- `RUNPOD_API_KEY` - For real Layer 2 inference
- `RUNPOD_ENDPOINT_ID` - Your deployed endpoint
- Encrypted DoRA adapter from `privacy_demo.py`

Without RunPod, the demo shows simulated Layer 2 responses to illustrate the concept.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HybridVault                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Smart Router                         │  │
│  │  - Pattern matching                               │  │
│  │  - Service extraction                             │  │
│  │  - Confidence scoring                             │  │
│  └───────────────────────────────────────────────────┘  │
│         │                │                │              │
│      EXACT            FUZZY            HYBRID            │
│         │                │                │              │
│         ▼                ▼                ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ Layer 1  │    │ Layer 2  │    │ Layer 1  │          │
│  │   (KV)   │    │  (DoRA)  │    │    +     │          │
│  │          │    │          │    │ Layer 2  │          │
│  │ • Stripe │    │ "Why?"   │    │          │          │
│  │ • GitHub │    │ "How?"   │    │ "Show    │          │
│  │ • AWS    │    │ "Tell me"│    │  all"    │          │
│  └──────────┘    └──────────┘    └──────────┘          │
│      ↓                ↓                ↓                 │
│   sk_live_ABC    "Best DX"    sk_live_ABC + "Best DX"  │
└─────────────────────────────────────────────────────────┘
```

## Query Examples

### EXACT Queries → Layer 1
```python
"What's my Stripe API key?"
"Show me GitHub credentials"
"Get AWS password"
```
→ Routed to Layer 1 (KV Store)
→ <10ms response
→ Zero hallucination risk

### FUZZY Queries → Layer 2
```python
"Why did I choose Stripe?"
"How did I setup GitHub webhooks?"
"Tell me about my AWS infrastructure"
```
→ Routed to Layer 2 (DoRA)
→ ~200-300ms response (LLM inference)
→ Contextual knowledge

### HYBRID Queries → Both Layers
```python
"Show me everything about Stripe"
"Tell me everything on GitHub"
"Stripe setup and credentials"
```
→ Routed to BOTH layers
→ Combined response:
  - Layer 1: Exact API key
  - Layer 2: Setup context/knowledge

## Development Roadmap

See `advanced_vault/docs/ROADMAP.md` for the full 8-week plan:

- ✅ **Week 1**: Encrypted KV Store (Layer 1)
- ✅ **Week 2**: Smart Router + Hybrid Vault
- 📝 **Week 3-4**: MCP Integration + TEE
- 📝 **Week 5-6**: Performance optimization
- 📝 **Week 7-8**: Team features (threshold crypto)

## Test Coverage

Run tests for advanced vault:
```bash
# All tests
python -m pytest tests/ advanced_vault/ -v

# Advanced vault only
python -m pytest advanced_vault/ -v

# Specific component
python -m pytest advanced_vault/core/tests/test_smart_router.py -v
```

**Current Status**: 113/113 tests passing
- 67 baseline tests (DoRA, encryption, inference)
- 26 encrypted KV tests
- 20 smart router tests

## Next Steps

1. **Try the demos** in order (KV → Hybrid → Unified)
2. **Read the architecture docs** in `advanced_vault/docs/`
3. **Enable Layer 2** by running `privacy_demo_runpod.py`
4. **Experiment with queries** and routing patterns

See parent `examples/README.md` for the complete privacy demo workflow.
