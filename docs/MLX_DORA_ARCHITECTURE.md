# MLX DoRA Inference Architecture

This document explains the DoRA (Weight-Decomposed Low-Rank Adaptation) implementation for Apple Silicon using MLX, and the multi-adapter loading system.

## Table of Contents

1. [Overview](#overview)
2. [DoRA Theory](#dora-theory)
3. [MLX Implementation](#mlx-implementation)
4. [Multi-Adapter Engine](#multi-adapter-engine)
5. [Security Model](#security-model)
6. [API Reference](#api-reference)

---

## Overview

The SLM-Vault project provides privacy-preserving fine-tuning and inference for AI models. Key components:

```
┌─────────────────────────────────────────────────────────────────┐
│                        SLM-Vault Stack                          │
├─────────────────────────────────────────────────────────────────┤
│  Browser Extension  │  Desktop GUI  │  CLI  │  MCP Integration  │
├─────────────────────────────────────────────────────────────────┤
│                    Multi-Adapter Engine                         │
│         (Profiles, Weighted Merging, LRU Cache)                 │
├─────────────────────────────────────────────────────────────────┤
│                    MLX DoRA Inference                           │
│            (Apple Silicon Optimized)                            │
├─────────────────────────────────────────────────────────────────┤
│                    Encrypted KV Store                           │
│             (ChaCha20-Poly1305 E2EE)                           │
└─────────────────────────────────────────────────────────────────┘
```

### Why DoRA on MLX?

1. **Privacy**: Adapters stay encrypted until inference time
2. **Efficiency**: MLX leverages Apple Silicon's unified memory
3. **DoRA Advantage**: Better fine-tuning quality than LoRA with same parameter count
4. **Ephemeral Loading**: Adapters exist only in memory during use

---

## DoRA Theory

### The DoRA Formula

DoRA (Weight-Decomposed Low-Rank Adaptation) decomposes weight updates into **magnitude** and **direction** components:

```
W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||_c)
```

Where:
- `W₀` - Original pretrained weights `[out_features, in_features]`
- `B` - Low-rank down-projection `[out_features, rank]`
- `A` - Low-rank up-projection `[rank, in_features]`
- `m` - Learnable magnitude vector `[out_features]`
- `||·||_c` - Column-wise (row) L2 normalization
- `⊙` - Element-wise multiplication (broadcast)

### Visual Breakdown

```
Original Weight (W₀)           LoRA Update (BA)
┌───────────────────┐         ┌───────────────────┐
│                   │         │                   │
│   [out × in]      │    +    │   [out × in]      │
│                   │         │   (rank << in)    │
└───────────────────┘         └───────────────────┘
         │                             │
         └──────────┬──────────────────┘
                    │
                    ▼
            Combined (W₀ + BA)
            ┌───────────────────┐
            │                   │
            │   [out × in]      │
            │                   │
            └───────────────────┘
                    │
                    ▼ Normalize each row
            Direction (normalized)
            ┌───────────────────┐
            │  ||row|| = 1.0    │
            │   [out × in]      │
            │  ||row|| = 1.0    │
            └───────────────────┘
                    │
                    ▼ Scale by magnitude
            ┌─────┐
            │  m  │  [out × 1]
            │ 1.2 │
            │ 0.8 │     ×
            │ ... │
            └─────┘
                    │
                    ▼
            Final Weight (W')
            ┌───────────────────┐
            │  ||row|| = m[0]   │
            │   [out × in]      │
            │  ||row|| = m[1]   │
            └───────────────────┘
```

### Why DoRA > LoRA?

| Aspect | LoRA | DoRA |
|--------|------|------|
| Formula | `W' = W₀ + BA` | `W' = m ⊙ norm(W₀ + BA)` |
| Magnitude control | Implicit | Explicit |
| Direction control | Coupled | Decoupled |
| Fine-tuning quality | Good | Better |
| Extra parameters | None | 1 vector per layer |

DoRA separates **what direction** the weight should point (learned via BA) from **how strong** it should be (learned via m).

---

## MLX Implementation

### Architecture

```
mlx_dora_inference.py
├── DoRAWeights (dataclass)
│   ├── lora_a: mx.array [rank, in_features]
│   ├── lora_b: mx.array [out_features, rank]
│   ├── magnitude: mx.array [out_features] (optional)
│   └── scaling: float
│
├── MLXDoRALinear (nn.Module)
│   ├── _compute_adapted_weight() → implements DoRA formula
│   └── __call__(x) → forward pass with adapted weights
│
└── MLXDoRAInference (main engine)
    ├── load_model() → load base MLX model
    ├── load_encrypted_adapter() → decrypt + parse safetensors
    ├── apply_adapter() → replace Linear layers with DoRA layers
    ├── restore_base_model() → undo adapter application
    └── generate() → text generation
```

### Core Implementation

#### DoRA Linear Layer

```python
class MLXDoRALinear(nn.Module):
    def _compute_adapted_weight(self) -> mx.array:
        # Step 1: Compute BA product
        # B: [out, rank] @ A: [rank, in] = [out, in]
        ba = mx.matmul(self._lora_b, self._lora_a) * self._scaling

        # Step 2: Add to original weights
        combined = self._original_weight + ba

        # Step 3: Apply DoRA normalization if magnitude exists
        if self._magnitude is not None:
            # Normalize each row to unit length
            row_norms = mx.linalg.norm(combined, axis=1, keepdims=True)
            row_norms = mx.maximum(row_norms, 1e-8)  # Prevent div by zero
            normalized = combined / row_norms

            # Scale by learned magnitude
            adapted = self._magnitude[:, None] * normalized
        else:
            # Fall back to standard LoRA
            adapted = combined

        return adapted

    def __call__(self, x: mx.array) -> mx.array:
        # Forward: x @ W'^T + bias
        out = mx.matmul(x, self._adapted_weight.T)
        if self._original_bias is not None:
            out = out + self._original_bias
        return out
```

#### Module Replacement Strategy

The engine replaces specific `nn.Linear` modules in the model:

```python
TARGET_MODULES = [
    'q_proj', 'k_proj', 'v_proj', 'o_proj',  # Attention
    'gate_proj', 'up_proj', 'down_proj',      # MLP
]
```

For a path like `model.layers.0.self_attn.q_proj`:

```
1. Navigate: model → layers[0] → self_attn
2. Store original: self._original_modules["model.layers.0.self_attn.q_proj"] = q_proj
3. Replace: self_attn.q_proj = MLXDoRALinear(...)
```

### Weight Format Compatibility

Supports multiple PEFT naming conventions:

| Format | Example Key |
|--------|-------------|
| Standard | `model.layers.0.self_attn.q_proj.lora_A` |
| PEFT | `base_model.model.layers.0.self_attn.q_proj.lora_A.weight` |
| HuggingFace | `base_model.model.layers.0.self_attn.q_proj.lora_A.default` |

Normalization strips prefixes (`base_model.model.`) and suffixes (`.weight`, `.default`).

---

## Multi-Adapter Engine

### Purpose

Enable loading **multiple adapters simultaneously** with weighted combination:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Multi-Adapter Engine                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Registered Adapters                   Active Profile           │
│  ┌──────────────────┐                 ┌──────────────────┐     │
│  │ company_docs     │──────┐          │ "work" profile   │     │
│  │ professional_tone│──────┼───────►  │ 80% company_docs │     │
│  │ personal_notes   │      │          │ 20% prof_tone    │     │
│  │ code_style       │      │          └──────────────────┘     │
│  └──────────────────┘      │                   │               │
│                            │                   ▼               │
│  LRU Cache (max=3)         │          Weighted Merge           │
│  ┌──────────────────┐      │          ┌──────────────────┐     │
│  │ company_docs ✓   │◄─────┘          │ 0.8×A₁ + 0.2×A₂  │     │
│  │ prof_tone ✓      │                 │ 0.8×B₁ + 0.2×B₂  │     │
│  │ (slot available) │                 │ 0.8×m₁ + 0.2×m₂  │     │
│  └──────────────────┘                 └──────────────────┘     │
│                                                │               │
│                                                ▼               │
│                                       Apply to Model           │
│                                       ┌──────────────────┐     │
│                                       │ MLXDoRALinear    │     │
│                                       │ (merged weights) │     │
│                                       └──────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

#### 1. Adapter Registration

Adapters are stored **encrypted** until activation:

```python
engine.register_adapter(
    name="company_docs",
    encrypted_data=encrypted_safetensors_bytes,
    encryption_key=master_key_bytes,
    metadata={"version": "1.0", "domain": "internal"}
)
```

#### 2. Profiles

Saved combinations for quick switching:

```python
engine.save_profile(
    name="work",
    adapters={"company_docs": 0.8, "professional_tone": 0.2},
    description="Work context with company knowledge",
    keywords=["meeting", "project", "deadline", "client"]
)
```

#### 3. Weighted Merging Algorithm

```python
def merge_adapters(adapters, weights):
    """
    For each layer that exists in any adapter:

    merged_A = Σ (weight_i × adapter_i.lora_a)
    merged_B = Σ (weight_i × adapter_i.lora_b)
    merged_m = Σ (weight_i × adapter_i.magnitude)

    Note: Weights are pre-normalized to sum to 1.0
    """
    for layer_name in all_layers:
        lora_a_sum = None
        for adapter_name, adapter in adapters.items():
            if layer_name in adapter:
                alpha = weights[adapter_name]
                if lora_a_sum is None:
                    lora_a_sum = adapter[layer_name].lora_a * alpha
                else:
                    lora_a_sum += adapter[layer_name].lora_a * alpha
        # ... same for lora_b and magnitude
```

#### 4. LRU Cache

Memory-efficient adapter management:

```
┌────────────────────────────────────────────┐
│           LRU Cache (max_size=3)           │
├────────────────────────────────────────────┤
│                                            │
│  [MRU] company_docs ◄── Recently accessed  │
│        prof_tone                           │
│  [LRU] personal_notes ◄── Evicted next     │
│                                            │
│  On capacity overflow:                     │
│  1. Evict LRU adapter                      │
│  2. Call DoRAWeights.clear()               │
│  3. Add new adapter                        │
│                                            │
└────────────────────────────────────────────┘
```

#### 5. Context Auto-Detection

```python
profiles = {
    "work": keywords=["meeting", "project", "client"],
    "code": keywords=["function", "bug", "error", "deploy"],
}

query = "Fix the bug in the authentication function"
# Matches: "bug", "function" → activates "code" profile
detected = engine.detect_context(query)  # Returns "code"
```

#### 6. Audit Logging

For compliance with confidential data:

```python
{
    "timestamp": "2024-01-15T10:30:00Z",
    "profile": "work",
    "adapters": ["company_docs", "prof_tone"],
    "weights": {"company_docs": 0.8, "prof_tone": 0.2},
    "query_hash": "a3f2b1c4...",  # SHA-256, not plaintext
    "session": "session_abc123"
}
```

---

## Security Model

### Encryption Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      Encryption Flow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Master Password                                                │
│       │                                                         │
│       ▼ PBKDF2 (100k iterations)                               │
│  ┌─────────────────┐                                           │
│  │  Master Key     │ (32 bytes)                                │
│  └─────────────────┘                                           │
│       │                                                         │
│       ├──────────────────────────────────────────────┐         │
│       │                                              │         │
│       ▼ HKDF-SHA256                                  ▼         │
│  ┌─────────────────┐                        ┌───────────────┐  │
│  │ Adapter Key     │                        │ Storage Key   │  │
│  │ (per-adapter)   │                        │ (KV store)    │  │
│  └─────────────────┘                        └───────────────┘  │
│       │                                              │         │
│       ▼ ChaCha20-Poly1305                           ▼         │
│  ┌─────────────────┐                        ┌───────────────┐  │
│  │ Encrypted       │                        │ Encrypted     │  │
│  │ Adapter Weights │                        │ Secrets       │  │
│  └─────────────────┘                        └───────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Ephemeral Adapter Loading

Adapters **never touch disk** during inference:

```
1. Encrypted adapter stored in cloud/local
2. Downloaded to memory (still encrypted)
3. Decrypted in memory → DoRA weights
4. Applied to model (in-memory only)
5. After use: weights.clear() zeros memory
6. Restored: original model weights back
```

### Secure Memory Handling

```python
class DoRAWeights:
    def clear(self):
        """Zero out weight references."""
        self.lora_a = None
        self.lora_b = None
        self.magnitude = None

class EncryptedKVStore:
    def close(self):
        """Secure key zeroing."""
        if self._master_key is not None:
            for i in range(len(self._master_key)):
                self._master_key[i] = 0  # Zero each byte
            self._master_key = None
```

---

## API Reference

### MLXDoRAInference

```python
from advanced_vault.gui.mlx_dora_inference import MLXDoRAInference

engine = MLXDoRAInference(model_path="mlx-community/Qwen2.5-1.5B-Instruct-4bit")

# Load model
engine.load_model(progress_callback=lambda msg: print(msg))

# Load and apply encrypted adapter
with engine.adapter_context(adapter_path, encryption_key) as layers_modified:
    response = engine.generate(
        prompt="What is quantum computing?",
        max_tokens=256,
        temperature=0.7
    )
# Adapter automatically removed after context

# Manual adapter management
dora_weights = engine.load_encrypted_adapter(path, key)
engine.apply_adapter(dora_weights)
response = engine.generate(prompt)
engine.restore_base_model()

# Cleanup
engine.unload()
```

### MultiAdapterEngine

```python
from advanced_vault.gui.multi_adapter_engine import MultiAdapterEngine

engine = MultiAdapterEngine(max_cached_adapters=3)
engine.load_model()

# Register adapters
engine.register_adapter("knowledge", encrypted_data1, key1)
engine.register_adapter("style", encrypted_data2, key2)

# Create profile
engine.save_profile(
    "work",
    adapters={"knowledge": 0.7, "style": 0.3},
    keywords=["meeting", "project"]
)

# Activate and generate
engine.activate_profile("work")
response = engine.chat("Summarize the Q3 results")

# Or auto-detect context
response = engine.chat(
    "Fix the authentication bug",
    auto_detect_context=True
)

# Dynamic weight adjustment
engine.set_adapter_weight("knowledge", 0.9)

# Get stats
stats = engine.get_usage_stats()
log = engine.export_usage_log()

# Cleanup
engine.unload()
```

### Quick Reference

| Method | Purpose |
|--------|---------|
| `register_adapter(name, data, key)` | Register encrypted adapter |
| `save_profile(name, adapters, keywords)` | Save adapter combination |
| `activate_profile(name)` | Switch to profile |
| `set_adapters({name: weight})` | Direct weight control |
| `detect_context(query)` | Auto-detect matching profile |
| `get_usage_stats()` | Usage statistics |
| `export_usage_log()` | Audit trail export |
| `deactivate_adapters()` | Restore base model |

---

## Performance Considerations

### Memory Usage

| Component | Memory |
|-----------|--------|
| Base model (4-bit) | ~1-2 GB |
| DoRA adapter (rank 16) | ~50-100 MB per adapter |
| LRU cache (3 adapters) | ~150-300 MB max |

### Inference Latency

- **Adapter switch**: ~100-500ms (decrypt + apply)
- **Cached adapter switch**: ~50-100ms (apply only)
- **Generation**: Same as base model (weights pre-computed)

### Best Practices

1. **Use profiles** for common combinations
2. **Set `max_cached_adapters`** based on available memory
3. **Use context auto-detection** for seamless UX
4. **Monitor usage stats** for optimization opportunities
