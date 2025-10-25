# DoRA WDVA Improvements Backlog

**Version:** 2.0
**Last Updated:** 2025-01-25
**Status:** Implementation in progress

## Priority Legend
- 🔴 **P0**: Critical (blocking issues, security vulnerabilities)
- 🟠 **P1**: High (major improvements, performance optimizations)
- 🟡 **P2**: Medium (enhancements, nice-to-have features)
- 🟢 **P3**: Low (future considerations, experimental)

## Status Legend
- ✅ **Done**: Implemented and tested
- 🟡 **In Progress**: Currently being worked on
- ⬜ **Planned**: On roadmap but not started
- 🔄 **Blocked**: Waiting on dependencies

---

## Phase 1: Core Implementation ✅

### P0: Critical Components (COMPLETED)
- ✅ **DoRA crypto module with encryption/decryption** (src/dora_crypto.py)
  - XChaCha20-Poly1305 authenticated encryption
  - HKDF-SHA256 key derivation
  - SafeTensors serialization
  - Compression support (zstd)

- ✅ **Ephemeral inference engine** (src/ephemeral_inference.py)
  - In-memory adapter loading
  - State capture and restoration
  - DoRA weight application with proper formula
  - Automatic cleanup

- ✅ **RunPod handler with complete weight application** (src/rp_handler.py)
  - Training endpoint
  - Encryption endpoint
  - Inference endpoint
  - Error handling

### P1: Security Hardening (COMPLETED)
- ✅ **Secure memory zeroing** (src/utils/memory_security.py)
  - ctypes-based memory overwrites
  - CUDA-aware zeroing
  - Dictionary cleanup utilities

- ✅ **Memory locking support** (src/utils/memory_security.py)
  - mlock/munlock for sensitive data
  - Platform-specific implementations (Linux/macOS/Windows)
  - SecureMemoryContext manager

- ✅ **CUDA stream synchronization** (src/utils/cuda_utils.py)
  - Stream context managers
  - Multi-stream support
  - Proper synchronization barriers

### P1: Performance Optimizations (COMPLETED)
- ✅ **LRU adapter caching** (src/utils/adapter_cache.py)
  - Size-based eviction
  - Memory-based eviction
  - Hit rate tracking
  - Secure cleanup on eviction

- ✅ **Complete state restoration** (src/ephemeral_inference.py)
  - Parameter backup/restore
  - Buffer backup/restore
  - Hook preservation (_forward_hooks, _backward_hooks)

---

## Phase 2: Production Hardening 🟡

### P0: Security Critical (IN PROGRESS)

#### 1. Timing Attack Mitigation 🟡
**Status:** Planned
**Priority:** P0
**Effort:** Medium (2-3 days)
**Description:** Add constant-time operations to prevent timing-based information leakage during decryption.

**Implementation:**
```python
# src/dora_crypto.py
def decrypt_and_load_dora_weights_constant_time(self, encrypted_path: str):
    """Decrypt with timing attack mitigation."""
    # Add padding/dummy operations
    start_time = time.perf_counter()

    # Actual decryption
    result = self._decrypt_internal(encrypted_path)

    # Constant-time padding to minimum duration
    elapsed = time.perf_counter() - start_time
    target_time = 0.1  # 100ms minimum
    if elapsed < target_time:
        time.sleep(target_time - elapsed)

    return result
```

**Acceptance Criteria:**
- [ ] Decryption time variance <5% across different adapter sizes
- [ ] Performance overhead <10%
- [ ] Unit tests for timing consistency

#### 2. Audit Logging 🟡
**Status:** Planned
**Priority:** P0
**Effort:** Small (1-2 days)
**Description:** Comprehensive logging of all security-sensitive operations.

**Implementation:**
```python
# src/utils/audit_log.py
class AuditLogger:
    def log_adapter_load(self, adapter_id, user_id, timestamp):
        """Log adapter load event."""

    def log_encryption_event(self, event_type, metadata):
        """Log encryption/decryption events."""

    def log_security_violation(self, violation_type, details):
        """Log security violations."""
```

**Events to Log:**
- Adapter loads/unloads
- Encryption/decryption operations
- Authentication failures
- Memory security events
- Cache operations

**Acceptance Criteria:**
- [ ] All security events logged with timestamps
- [ ] Structured JSON logging format
- [ ] Log rotation and retention policies
- [ ] Integration with SIEM systems

#### 3. Key Rotation Automation ⬜
**Status:** Planned
**Priority:** P1
**Effort:** Medium (3-4 days)
**Description:** Automated key rotation with backward compatibility.

**Implementation:**
```python
# src/dora_crypto.py
class KeyRotationManager:
    def rotate_keys(self, old_key, new_key, adapter_paths):
        """Rotate encryption keys for multiple adapters."""

    def verify_rotation(self, adapter_path, expected_version):
        """Verify adapter is encrypted with correct key version."""

    def rollback_rotation(self, adapter_path, backup_path):
        """Rollback failed key rotation."""
```

**Features:**
- Versioned encryption (v1, v2, etc.)
- Backward compatibility during migration
- Automated rotation scheduling
- Rollback capabilities

**Acceptance Criteria:**
- [ ] Zero-downtime key rotation
- [ ] Automatic re-encryption of all adapters
- [ ] Version tracking in metadata
- [ ] Rollback on failure

### P1: Performance Optimizations (PLANNED)

#### 4. Lazy Layer-by-Layer Decryption ⬜
**Status:** Planned
**Priority:** P1
**Effort:** Large (5-7 days)
**Description:** Decrypt only the layers needed for inference, reducing latency.

**Current:** Decrypt entire adapter upfront (~150-250ms cold start)
**Target:** Decrypt on-demand per layer (~50-100ms for first layer, then stream rest)

**Implementation:**
```python
# src/dora_crypto.py
class LazyDoRADecryptor:
    def __init__(self, encrypted_path, encryption_key):
        self._load_metadata()
        self._layer_cache = {}

    def get_layer_weights(self, layer_name):
        """Decrypt single layer on-demand."""
        if layer_name not in self._layer_cache:
            self._layer_cache[layer_name] = self._decrypt_layer(layer_name)
        return self._layer_cache[layer_name]
```

**Required Changes:**
- Per-layer encryption in `extract_and_encrypt_dora_weights`
- Layer manifest in encrypted package
- Stream-based decryption
- Progressive cache warming

**Acceptance Criteria:**
- [ ] 60% reduction in cold start latency
- [ ] Memory usage scales with active layers only
- [ ] Backward compatible with full-adapter encryption

#### 5. Multi-GPU Distributed Inference ⬜
**Status:** Planned
**Priority:** P1
**Effort:** Large (7-10 days)
**Description:** Distribute large models across multiple GPUs with adapter support.

**Implementation:**
```python
# src/distributed_inference.py
class DistributedDoRAInference:
    def __init__(self, model_name, encryption_key, device_map):
        """Initialize with custom device map."""
        self.device_map = device_map  # {layer_range: device}

    def inference_distributed(self, encrypted_path, prompt):
        """Run inference across multiple GPUs."""
```

**Features:**
- Automatic layer-to-device mapping
- Per-device adapter caching
- Inter-GPU communication optimization
- Load balancing

**Acceptance Criteria:**
- [ ] Support for 13B+ models
- [ ] Linear scaling up to 4 GPUs
- [ ] Automatic failover on GPU failure

#### 6. CUDA Kernel Optimization for DoRA Merging ⬜
**Status:** Planned
**Priority:** P1
**Effort:** Medium (4-5 days)
**Description:** Fused CUDA kernel for DoRA formula: `W' = m ⊙ ((W₀ + BA) / ||W₀ + BA||c)`

**Current:** Sequential CPU/CUDA operations (~100-150ms for TinyLlama)
**Target:** Fused kernel (~40-60ms, 40-60% improvement)

**Implementation:**
```python
# src/utils/cuda_kernels.py
@torch.jit.script
def fused_dora_merge(W0: torch.Tensor,
                     lora_A: torch.Tensor,
                     lora_B: torch.Tensor,
                     magnitude: torch.Tensor) -> torch.Tensor:
    """Fused CUDA kernel for DoRA merging."""
    BA = torch.mm(lora_B, lora_A)
    new_direction = W0 + BA
    norms = torch.linalg.norm(new_direction, dim=0, keepdim=True)
    return magnitude.unsqueeze(0) * (new_direction / norms)
```

**Optimizations:**
- Fuse matrix multiplication + normalization
- Reduce memory copies
- Stream-parallel execution

**Acceptance Criteria:**
- [ ] 40%+ speedup on adapter merging
- [ ] Lower memory usage than sequential ops
- [ ] Support for all common tensor sizes

### P2: Monitoring & Observability (PLANNED)

#### 7. Metrics Dashboard ⬜
**Status:** Planned
**Priority:** P2
**Effort:** Medium (3-4 days)
**Description:** Real-time monitoring dashboard for adapter operations.

**Metrics to Track:**
- Adapter cache hit rate
- Decryption latency (p50, p95, p99)
- Memory usage trends
- GPU utilization
- Request throughput
- Error rates

**Implementation:**
```python
# src/metrics.py
class MetricsCollector:
    def __init__(self, backend='prometheus'):
        self.backend = backend

    def record_inference(self, latency_ms, cache_hit, adapter_id):
        """Record inference metrics."""

    def record_cache_operation(self, operation, hit, eviction_count):
        """Record cache metrics."""
```

**Integration Points:**
- Prometheus/Grafana
- DataDog
- CloudWatch (for AWS deployments)

**Acceptance Criteria:**
- [ ] Real-time dashboard with 1s refresh
- [ ] Alerts on anomalies (high latency, cache thrashing)
- [ ] Historical trend analysis
- [ ] Export to CSV for analysis

#### 8. Adapter Versioning System ⬜
**Status:** Planned
**Priority:** P2
**Effort:** Medium (3-4 days)
**Description:** Semantic versioning for adapters with compatibility tracking.

**Implementation:**
```python
# src/adapter_registry.py
class AdapterRegistry:
    def register_adapter(self, adapter_id, version, metadata):
        """Register adapter with semantic version."""

    def get_compatible_adapters(self, base_model, min_version):
        """Find compatible adapters for base model."""

    def deprecate_adapter(self, adapter_id, reason):
        """Mark adapter as deprecated."""
```

**Features:**
- Semantic versioning (major.minor.patch)
- Compatibility matrix tracking
- Automatic migration on breaking changes
- Deprecation warnings

**Acceptance Criteria:**
- [ ] Version tracking in encrypted metadata
- [ ] Compatibility checks before loading
- [ ] Migration tools for breaking changes
- [ ] Deprecation lifecycle management

---

## Phase 3: Advanced Features 📋

### P2: Experimental Features (FUTURE)

#### 9. A/B Testing Framework ⬜
**Status:** Planned
**Priority:** P2
**Effort:** Large (5-6 days)
**Description:** Built-in A/B testing for adapter comparison.

**Implementation:**
```python
# src/ab_testing.py
class ABTest:
    def __init__(self, adapter_a, adapter_b, traffic_split=0.5):
        """Initialize A/B test."""

    def route_request(self, request_id):
        """Route request to A or B based on split."""

    def collect_metrics(self):
        """Collect comparison metrics."""
```

**Features:**
- Traffic splitting
- Statistical significance testing
- Automatic winner selection
- Gradual rollout

#### 10. Adapter Compression Optimization ⬜
**Status:** Planned
**Priority:** P3
**Effort:** Medium (3-4 days)
**Description:** Optimize compression for neural network weights.

**Current:** Generic zstd compression (~30-50% reduction)
**Target:** NN-aware compression (~60-70% reduction)

**Techniques:**
- Quantization-aware compression
- Pattern detection in weight matrices
- Delta encoding for similar layers
- Huffman coding for weight distributions

#### 11. Federated Adapter Training ⬜
**Status:** Research
**Priority:** P3
**Effort:** Very Large (15-20 days)
**Description:** Train adapters across multiple nodes without data sharing.

**Implementation:** (Conceptual)
```python
class FederatedDoRATrainer:
    def aggregate_gradients(self, client_updates):
        """Aggregate DoRA gradients from multiple clients."""

    def encrypt_updates(self, local_updates):
        """Encrypt updates before sending to server."""
```

---

## Issue Tracking

### Known Issues
1. **Memory leak in adapter cache** ❌ FIXED v2.0
   - Issue: Tensors not properly cleaned on eviction
   - Fix: Added `secure_zero_dict` in cache eviction path

2. **CUDA out-of-memory on rapid adapter switching** ⚠️ OPEN
   - Impact: P2
   - Workaround: Add delay between switches or reduce cache size
   - Target: Phase 2

3. **Slow decryption on CPU-only systems** ⚠️ OPEN
   - Impact: P3
   - Workaround: Use smaller adapters or GPU instance
   - Target: Phase 3

### Technical Debt
1. **Test coverage <80%** 🟡 IN PROGRESS
   - Current: ~60% coverage
   - Target: 80%+ for production
   - Priority: P1

2. **Missing integration tests for RunPod handler** ⬜ PLANNED
   - Priority: P1
   - Effort: Small (1-2 days)

3. **Documentation needs API reference** ⬜ PLANNED
   - Priority: P2
   - Effort: Medium (2-3 days)

---

## Success Metrics

### Performance Targets
- [x] Adapter switching <10ms (cached): **Achieved: <5ms**
- [x] Cold start <500ms: **Achieved: 150-250ms**
- [ ] Memory usage <1GB (QDoRA): **Current: 0.8-1.0GB** ✅
- [ ] Training cost <$0.50 per 1K samples: **Current: $0.09** ✅

### Security Targets
- [x] Zero disk persistence: **Achieved** ✅
- [x] Authenticated encryption: **Achieved** ✅
- [ ] Timing attack resistance: **Planned Phase 2**
- [ ] Audit logging: **Planned Phase 2**

### Reliability Targets
- [ ] 99.9% uptime (inference): **TBD**
- [ ] <0.1% error rate: **TBD**
- [ ] Automatic failover: **Planned Phase 2**

---

## Contributing

To propose new improvements:
1. Create issue with detailed description
2. Assign priority and effort estimate
3. Link to relevant code sections
4. Propose acceptance criteria

For security issues, please report privately to security@example.com.
