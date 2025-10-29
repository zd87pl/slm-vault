# Baseline Functionality (Proven & Working)

**Last Verified:** 2025-10-26
**Branch:** main (commit: 65606d3)
**Status:** ✅ All tests passing, RunPod deployment working

---

## Overview

This document captures the **proven, working functionality** of the WDVA system. These features are locked as the baseline - all advanced features must preserve this behavior.

---

## Core Components

### 1. DoRA Training (`src/train_dora.py`)

**Functionality:**
- Fine-tune base model with DoRA adapters
- Support for any HuggingFace causal LM model
- QLoRA/QDoRA (4-bit/8-bit quantization)
- Configurable rank, alpha, learning rate

**Key Functions:**
```python
def train_dora(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Train DoRA adapter on dataset.

    Args:
        config: {
            "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "dataset": "yahma/alpaca-cleaned",
            "max_samples": 50,
            "epochs": 1,
            "batch_size": 4,
            "rank": 16,
            "alpha": 32,
            "output_dir": "/path/to/output"
        }

    Returns:
        {
            "adapter_path": "/path/to/adapter",
            "trainable_params": 1234567,
            "total_params": 1100000000,
            "train_loss": 0.234,
            "train_samples": 50
        }
    """
```

**Performance:**
- Training time: ~30-60 seconds (50 samples, A100)
- Adapter size: ~20-50MB (rank 16)
- Memory: ~8GB GPU

**Tested Models:**
- ✅ TinyLlama-1.1B-Chat-v1.0
- ✅ Llama-2-7B
- ✅ Mistral-7B

---

### 2. DoRA Encryption (`src/dora_crypto.py`)

**Functionality:**
- Extract DoRA weights from trained adapter
- Encrypt with XChaCha20-Poly1305
- Optional compression (zlib)
- Serialize to JSON

**Key Class:**
```python
class EncryptedDoRAManager:
    def encrypt_dora_weights(
        self,
        adapter_path: str,
        output_path: str = None,
        enable_compression: bool = True
    ) -> Dict[str, Any]:
        """
        Encrypt trained DoRA adapter.

        Returns:
            {
                "encrypted_path": "/path/to/encrypted.json",
                "encryption_key": "hex_key_64_chars",
                "original_size_mb": 45.2,
                "encrypted_size_mb": 23.1,
                "compressed": True
            }
        """
```

**Weight Extraction:**
- Handles PEFT >= 0.9.0 ModuleDict structure
- Extracts: lora_A, lora_B, lora_magnitude_vector
- Handles both DoraLinearLayer and DoraConv2dLayer

**Security:**
- XChaCha20-Poly1305 (authenticated encryption)
- 32-byte keys (256-bit security)
- Random nonces per encryption

**Performance:**
- Encryption: 2-5 seconds
- Compression: 40-50% size reduction
- No GPU required

---

### 3. Ephemeral Inference (`src/ephemeral_inference.py`)

**Functionality:**
- Decrypt adapter in-memory only
- Load weights ephemerally (never persists)
- Run inference with adapter
- Clean up weights after use

**Key Class:**
```python
class EphemeralDoRAInference:
    def inference_with_encrypted_adapter(
        self,
        encrypted_path: str,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        do_sample: bool = True
    ) -> Dict[str, Any]:
        """
        Run inference with encrypted adapter.

        Process:
        1. Decrypt adapter (in-memory)
        2. Apply weights to base model
        3. Generate response
        4. Remove weights from memory
        5. Secure zero memory

        Returns:
            {
                "response": "generated text...",
                "prompt": "original prompt",
                "metadata": {
                    "cache_hit": True,
                    "decrypt_time": 0.12,
                    "inference_time": 0.18
                }
            }
        """
```

**Security Features:**
- In-memory only decryption
- Secure memory locking (mlock)
- Secure zeroing after use
- No disk writes

**Performance:**
- Decryption: ~100ms (cache miss)
- Inference: ~200ms
- Cache hit: ~0ms decrypt overhead
- Total: ~300ms (cold), ~200ms (cached)

**Chat Template Support:**
- Auto-detects chat models (TinyLlama-Chat)
- Applies proper formatting
- Falls back to raw prompts for base models

---

### 4. RunPod Handler (`src/rp_handler.py`)

**Functionality:**
- Serverless handler for RunPod deployment
- Supports multiple tasks
- Stateless workflow optimizations

**Supported Tasks:**

```python
# Task 1: Training
{
    "task": "training",
    "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "dataset": "yahma/alpaca-cleaned",
    "max_samples": 50,
    "epochs": 1,
    "batch_size": 4,
    "rank": 16,
    "alpha": 32,
    "output_dir": "/workspace/output/adapter"
}

# Task 2: Encryption
{
    "task": "encrypt",
    "adapter_path": "/workspace/output/adapter",
    "encryption_key": "generate",  # or hex key
    "output_path": "/workspace/output/adapter.encrypted",
    "enable_compression": True
}

# Task 3: Train + Encrypt (Stateless)
{
    "task": "train_and_encrypt",
    # ... training params ...
    "encryption_key": "generate",
    "encrypted_output_path": "/workspace/output/adapter.encrypted",
    "enable_compression": True
}

# Task 4: Inference
{
    "task": "inference",
    "encrypted_adapter_path": "/workspace/output/adapter.encrypted",
    "encryption_key": "hex_key_64_chars",
    "prompt": "Your question here",
    "max_tokens": 150,
    "temperature": 0.7
}
```

**Why train_and_encrypt:**
- RunPod workers are stateless
- Separate jobs run on different workers
- Files don't persist between jobs
- Combined task ensures atomic operation

**Performance:**
- Cold start: ~30 seconds (first request)
- Warm requests: <1 second overhead
- Training: 30-60 seconds
- Inference: 300ms

---

## Deployment

### Docker Configuration

**Dockerfile:**
```dockerfile
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /workspace

# Install dependencies
COPY docker/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY src/ /workspace/src/
COPY config/ /workspace/config/

# Set environment
ENV TOKENIZERS_PARALLELISM=false
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

CMD ["python3", "-u", "src/rp_handler.py"]
```

**Build Context Optimization:**
- `.dockerignore` excludes: .git/, tests/, cache/
- Build context: ~552KB (down from GBs)
- Layer caching for dependencies

**GPU Support:**
- ✅ NVIDIA A100 SXM (tested)
- ✅ A6000, A40 (compatible)
- ⚠️ RTX 5090 (kernel not in PyTorch 2.5.1)

---

## Examples

### Privacy Demo (RunPod)

**File:** `examples/privacy_demo_runpod.py`

**Workflow:**
1. User setup (concept explanation)
2. Training + encryption (combined job)
3. Inference (with encrypted adapter)
4. Right-to-be-forgotten (key deletion)

**Features:**
- Consumer-friendly explanations
- Interactive prompts
- Visual step indicators
- Error handling with retries

**Performance:**
- Total workflow: ~2-3 minutes
- Training + encryption: 60-90 seconds
- Inference: ~2-5 seconds
- Fully automated (no user intervention)

---

## Testing

### Test Suite

**Location:** `tests/`

**Coverage:**
- ✅ DoRA training (66 tests)
- ✅ Encryption/decryption
- ✅ Ephemeral inference
- ✅ Memory security
- ✅ RunPod handler tasks

**Test Commands:**
```bash
# Full suite
pytest tests/ -v

# Specific tests
pytest tests/test_dora_crypto.py -v
pytest tests/test_ephemeral_inference.py -v

# Full workflow integration
bash tests/test_full_workflow.sh
```

**CI Status:** ✅ All passing (66/66 tests)

---

## Security Properties

### Encryption
- **Algorithm:** XChaCha20-Poly1305
- **Key Size:** 256-bit (32 bytes)
- **Nonce:** 192-bit random
- **Authentication:** Poly1305 MAC
- **Implementation:** Python `cryptography` library

### Memory Security
- **Locking:** mlock() to prevent swapping
- **Zeroing:** secure_zero() after use
- **Context managers:** Auto-cleanup
- **No persistence:** Never writes plaintext to disk

### Right-to-be-Forgotten
- **Method:** Key destruction
- **Effect:** Encrypted data becomes permanently unreadable
- **Verification:** Attempted decryption fails with error
- **Compliance:** GDPR Article 17 compatible

---

## Known Limitations

### Current Constraints
1. **Single-user only:** No multi-user or team features
2. **No incremental training:** Each training is from scratch
3. **No MCP integration:** Manual API calls only
4. **Local key management:** User must store key safely
5. **No consent mechanism:** All queries execute automatically

### Performance Bottlenecks
1. **Cold start:** 30s (RunPod container initialization)
2. **Download size:** 50MB encrypted adapter per query
3. **No search:** Must know which adapter to query

### Security Gaps
1. **No key rotation:** Same key forever
2. **No audit trail:** Can't prove deletion occurred
3. **Single point of failure:** Lose key = lose data
4. **No team sharing:** Can't share adapter with team

---

## Commit History (Recent)

```
65606d3 Fix empty responses by applying chat template for chat models
baa3346 Fix empty responses - use string-based prompt removal
3096f42 Fix inference to return only generated text, not input prompt
a16aa30 Add stateless train_and_encrypt task for RunPod
a53ad7c Update privacy demo to use stateless train_and_encrypt task
186d3b1 Add RunPod-based privacy demo (no local ML setup required)
```

---

## Dependencies

### Core Requirements
```
torch>=2.5.0
transformers>=4.46.0
peft>=0.13.0
accelerate>=1.1.0
bitsandbytes>=0.44.0
datasets>=3.0.0
cryptography>=41.0.0
runpod>=1.5.0
```

### System Requirements
- Python 3.9+
- CUDA 12.4+ (for GPU)
- 16GB RAM minimum
- 8GB VRAM (GPU)

---

## API Reference

### Training API
```python
from src.train_dora import train_dora

result = train_dora({
    "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "dataset": "yahma/alpaca-cleaned",
    "max_samples": 50,
    "epochs": 1,
    "batch_size": 4,
    "rank": 16,
    "alpha": 32,
    "output_dir": "/path/to/output"
})

print(result["adapter_path"])
```

### Encryption API
```python
from src.dora_crypto import EncryptedDoRAManager

manager = EncryptedDoRAManager(encryption_key)
result = manager.encrypt_dora_weights(
    adapter_path="/path/to/adapter",
    output_path="/path/to/encrypted.json",
    enable_compression=True
)

print(result["encryption_key"])
```

### Inference API
```python
from src.ephemeral_inference import EphemeralDoRAInference

engine = EphemeralDoRAInference(
    base_model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    encryption_key=bytes.fromhex(key_hex),
    enable_cache=True,
    load_in_4bit=True
)

result = engine.inference_with_encrypted_adapter(
    encrypted_path="/path/to/encrypted.json",
    prompt="Your question here",
    max_tokens=150,
    temperature=0.7
)

print(result["response"])
```

---

## Success Criteria

This baseline is considered "working" if:

✅ **Training:** Can train DoRA adapter on any dataset
✅ **Encryption:** Can encrypt adapter weights to JSON
✅ **Inference:** Can decrypt and run inference correctly
✅ **RunPod:** Deployed endpoint responds to all tasks
✅ **Demo:** privacy_demo_runpod.py completes successfully
✅ **Tests:** All 66 tests pass
✅ **Security:** No plaintext ever persists to disk

**Current Status:** ✅ All criteria met (as of 2025-10-26)

---

## Maintenance

### How to Verify Baseline
```bash
# 1. Run full test suite
pytest tests/ -v

# 2. Run integration test
bash tests/test_full_workflow.sh

# 3. Test RunPod demo
export RUNPOD_API_KEY="your-key"
python examples/privacy_demo_runpod.py
```

### When to Update This Document
- Any change to core functionality in `src/`
- Any change to public APIs
- Any new security properties
- Any performance improvements
- Any new tested models

### Baseline Freeze Policy
- `src/` code changes require approval
- Must maintain backward compatibility
- Tests must continue passing
- Performance must not degrade
- Security properties must be preserved

---

## Next Steps (Advanced Features)

See `ARCHITECTURE.md` for planned advanced features that build on this baseline:

1. **Encrypted KV Store:** Exact data storage (API keys)
2. **Smart Router:** Query classification (exact vs fuzzy)
3. **MCP Integration:** Expose to AI agents
4. **Threshold Crypto:** Team vaults
5. **Homomorphic Search:** Search without decryption
6. **Speculative Decryption:** Predictive caching
7. **Federated Learning:** Collective intelligence
8. **Verifiable Deletion:** Cryptographic proofs

**All advanced features must preserve this baseline functionality.**
