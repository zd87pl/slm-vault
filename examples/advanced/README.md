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
  - Enclave no longer ships a Layer 2 inference engine (the legacy engines
    are on the `legacy-archive-2026-09-29` branch), so fuzzy queries fall
    back to Layer 1 entry names

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

## Next Steps

1. **Try the demos** in order (KV → Hybrid)
2. **Experiment with queries** and routing patterns
