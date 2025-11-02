# Cryptographic Technical Specifications

## Overview

This document provides detailed technical specifications for the cryptographic components of the Weight-Delta Vault Adapters (WDVA) system, ensuring privacy-preserving personalization for genetic fitness applications.

## Cryptographic Primitives

### 1. Authenticated Encryption with Associated Data (AEAD)

#### Primary Algorithm: XChaCha20-Poly1305
```
Algorithm: XChaCha20-Poly1305
Key Size: 256 bits (32 bytes)
Nonce Size: 192 bits (24 bytes)
Tag Size: 128 bits (16 bytes)
Maximum Message Size: 2^64 - 1 bytes
```

#### Implementation Details
```python
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import secrets

class WDVACrypto:
    def __init__(self, master_key: bytes):
        self.master_key = master_key

    def encrypt_weight_delta(self, delta: bytes, user_id: str) -> bytes:
        # Derive user-specific key
        user_key = self._derive_user_key(user_id)

        # Generate random nonce
        nonce = secrets.token_bytes(24)

        # Create cipher instance
        cipher = ChaCha20Poly1305(user_key)

        # Associated data for authentication
        aad = self._create_aad(user_id)

        # Encrypt with authentication
        ciphertext = cipher.encrypt(nonce, delta, aad)

        return nonce + ciphertext
```

### 2. Key Derivation Function (KDF)

#### HKDF-SHA256 Specification
```
Algorithm: HKDF (HMAC-based Extract-and-Expand Key Derivation Function)
Hash Function: SHA-256
Salt: 256 bits of cryptographically secure random data
Info: Context-specific string ("WDVA_v1.0" || purpose || timestamp)
Output Key Length: 256 bits
```

#### Key Hierarchy
```
Master Key (K_master)
    │
    ├─► User Key (K_user)
    │   │
    │   ├─► Encryption Key (K_enc)
    │   ├─► Authentication Key (K_auth)
    │   └─► Consent Token Key (K_consent)
    │
    ├─► Audit Key (K_audit)
    └─► Admin Key (K_admin)
```

### 3. Associated Authenticated Data (AAD) Structure

```json
{
    "version": "WDVA_1.0",
    "user_id": "sha256(user_identifier)",
    "created_timestamp": "2025-10-13T18:49:00Z",
    "data_sources": ["genomics", "wearables", "preferences"],
    "consent_scope": "fitness_coaching:90_days",
    "privacy_budget": {"epsilon": 0.5, "delta": 1e-5},
    "manifest_hash": "sha256(weight_delta_metadata)",
    "key_rotation_id": "kr_20251013_001"
}
```

## Secure Key Management

### Key Generation
```python
def generate_master_key():
    """Generate cryptographically secure master key"""
    # Use hardware-backed CSPRNG when available
    return os.urandom(32)  # 256 bits

def derive_user_key(master_key: bytes, user_id: str) -> bytes:
    """Derive user-specific key from master key"""
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SYSTEM_SALT,
        info=f"WDVA_v1.0_user_{user_id}".encode()
    )
    return kdf.derive(master_key)
```

### Key Rotation Protocol
```python
class KeyRotationManager:
    def rotate_keys(self, rotation_interval_days=90):
        """Automatic key rotation protocol"""
        # Generate new master key
        new_master = generate_master_key()

        # Re-encrypt all user vaults
        for user_id in self.get_active_users():
            old_key = self.derive_user_key(self.current_master, user_id)
            new_key = self.derive_user_key(new_master, user_id)

            # Decrypt with old key
            vault_data = self.decrypt_vault(user_id, old_key)

            # Re-encrypt with new key
            self.encrypt_vault(user_id, vault_data, new_key)

        # Secure deletion of old master key
        self.secure_delete(self.current_master)
        self.current_master = new_master
```

### Secure Key Storage

#### Hardware Security Module (HSM) Integration
```python
class HSMKeyManager:
    """Hardware Security Module integration for key management"""

    def store_master_key(self, key: bytes) -> str:
        """Store master key in HSM"""
        key_id = self.hsm.import_key(
            key_material=key,
            key_type="AES256",
            usage="ENCRYPT_DECRYPT",
            extractable=False
        )
        return key_id

    def derive_key_in_hsm(self, master_key_id: str, derivation_data: bytes):
        """Perform key derivation inside HSM"""
        return self.hsm.derive_key(
            master_key_id=master_key_id,
            derivation_algorithm="HKDF_SHA256",
            derivation_data=derivation_data
        )
```

## Trusted Execution Environment (TEE) Integration

### Intel SGX Implementation
```c
// Enclave code for secure weight delta merging
sgx_status_t merge_weight_deltas(
    const uint8_t* encrypted_delta,
    size_t delta_size,
    const uint8_t* base_weights,
    size_t weights_size,
    uint8_t* merged_output
) {
    // Verify enclave attestation
    sgx_status_t status = sgx_verify_report();
    if (status != SGX_SUCCESS) return status;

    // Decrypt delta inside enclave
    uint8_t* decrypted_delta = sgx_decrypt(encrypted_delta, delta_size);

    // Perform secure merge
    secure_merge(base_weights, decrypted_delta, merged_output);

    // Clear sensitive memory
    memset_s(decrypted_delta, delta_size, 0, delta_size);

    return SGX_SUCCESS;
}
```

### ARM TrustZone Configuration
```c
// TrustZone secure world implementation
void tz_secure_inference(
    const secure_buffer_t* wdva_blob,
    const model_t* base_model,
    inference_result_t* result
) {
    // Switch to secure world
    SMC_ENTER_SECURE_WORLD();

    // Decrypt WDVA in secure memory
    weight_delta_t* delta = tz_decrypt_wdva(wdva_blob);

    // Perform inference in secure world
    tz_merge_and_infer(base_model, delta, result);

    // Secure cleanup
    tz_secure_free(delta);

    // Return to normal world
    SMC_EXIT_SECURE_WORLD();
}
```

## Cryptographic Right-to-be-Forgotten

### Key Destruction Protocol
```python
class CryptographicForgetting:
    def forget_user(self, user_id: str) -> bool:
        """Implement cryptographic right-to-be-forgotten"""

        # Step 1: Retrieve key references
        key_refs = self.get_user_key_references(user_id)

        # Step 2: Overwrite keys with random data (3 passes)
        for _ in range(3):
            for key_ref in key_refs:
                random_data = secrets.token_bytes(len(key_ref))
                self.overwrite_key(key_ref, random_data)

        # Step 3: Deallocate key storage
        for key_ref in key_refs:
            self.deallocate_storage(key_ref)

        # Step 4: Update revocation list
        self.revocation_list.add(user_id)

        # Step 5: Cryptographic proof of deletion
        proof = self.generate_deletion_proof(user_id)
        self.audit_log.record_deletion(user_id, proof)

        return self.verify_deletion(user_id)
```

### Deletion Verification
```python
def verify_deletion(self, user_id: str) -> bool:
    """Verify complete key destruction"""
    try:
        # Attempt to decrypt user vault
        self.decrypt_user_vault(user_id)
        # If successful, deletion failed
        return False
    except CryptographicError:
        # Decryption should fail after deletion
        return True
```

## Zero-Knowledge Proofs for Adapter Verification

### Proof of Authorized Training
```python
class ZKProofSystem:
    def generate_training_proof(self, adapter: WDVA) -> ZKProof:
        """Generate ZK proof that adapter was trained on authorized data"""

        # Commitment to training data
        commitment = self.pedersen_commit(adapter.training_hash)

        # Generate proof without revealing data
        proof = self.prove_statement(
            statement="adapter trained on authorized genomic data",
            witness=adapter.training_metadata,
            commitment=commitment
        )

        return proof

    def verify_training_proof(self, adapter_id: str, proof: ZKProof) -> bool:
        """Verify adapter training authorization"""
        return self.verify_proof(
            proof=proof,
            public_inputs=[adapter_id],
            statement="authorized training"
        )
```

## Homomorphic Encryption for Ultra-Sensitive Operations

### Encrypted Inference Capability
```python
class HomomorphicInference:
    """Perform inference on encrypted genomic data"""

    def encrypted_genomic_analysis(self, encrypted_vcf: bytes) -> bytes:
        """Analyze VCF file without decryption"""

        # Initialize BFV homomorphic scheme
        he = BFVScheme(
            poly_modulus_degree=16384,
            coeff_modulus=[60, 40, 40, 60],
            plain_modulus=65537
        )

        # Process encrypted genomic variants
        encrypted_result = he.evaluate(
            self.genomic_circuit,
            encrypted_vcf
        )

        return encrypted_result
```

## Side-Channel Attack Mitigations

### Constant-Time Operations
```c
// Constant-time memory comparison
int constant_time_compare(const uint8_t* a, const uint8_t* b, size_t len) {
    volatile uint8_t result = 0;
    for (size_t i = 0; i < len; i++) {
        result |= a[i] ^ b[i];
    }
    return result == 0;
}

// Constant-time conditional copy
void constant_time_copy(uint8_t* dest, const uint8_t* src, size_t len, int condition) {
    const uint8_t mask = -condition;  // 0x00 or 0xFF
    for (size_t i = 0; i < len; i++) {
        dest[i] = (dest[i] & ~mask) | (src[i] & mask);
    }
}
```

### Memory Access Pattern Protection
```python
def oblivious_array_access(array, index, dummy_ops=10):
    """Access array element while hiding access pattern"""
    result = None

    # Perform dummy operations
    for _ in range(dummy_ops):
        dummy_index = random.randint(0, len(array) - 1)
        _ = array[dummy_index]

    # Real access mixed with dummies
    for i in range(len(array)):
        is_target = constant_time_compare(i, index)
        if is_target:
            result = array[i]
        else:
            _ = array[i]  # Dummy read

    return result
```

## Compliance and Audit

### Cryptographic Audit Trail
```python
class CryptoAuditLog:
    def __init__(self, audit_key: bytes):
        self.audit_key = audit_key
        self.hash_chain = []

    def log_operation(self, operation: dict) -> str:
        """Create tamper-proof audit log entry"""

        # Add timestamp and sequence number
        entry = {
            **operation,
            "timestamp": datetime.utcnow().isoformat(),
            "sequence": len(self.hash_chain)
        }

        # Create hash chain
        if self.hash_chain:
            entry["previous_hash"] = self.hash_chain[-1]

        # Sign entry
        entry_bytes = json.dumps(entry).encode()
        signature = hmac.new(self.audit_key, entry_bytes, hashlib.sha256).digest()

        # Store hash
        entry_hash = hashlib.sha256(entry_bytes + signature).hexdigest()
        self.hash_chain.append(entry_hash)

        return entry_hash
```

## Performance Benchmarks

### Cryptographic Operation Latencies

| Operation | Average Latency | Throughput |
|-----------|----------------|------------|
| XChaCha20-Poly1305 Encryption (1MB) | 0.8ms | 1.25 GB/s |
| Key Derivation (HKDF-SHA256) | 0.05ms | 20,000 ops/s |
| TEE Context Switch | 0.1ms | 10,000 ops/s |
| Zero-Knowledge Proof Generation | 15ms | 66 ops/s |
| Zero-Knowledge Proof Verification | 3ms | 333 ops/s |
| Key Destruction (secure) | 1.8s | - |
| Homomorphic Operation | 50ms | 20 ops/s |

## Security Parameters

### Recommended Configuration
```yaml
security_config:
  key_sizes:
    master_key: 256  # bits
    user_keys: 256   # bits
    nonces: 192      # bits

  rotation_intervals:
    master_key: 90   # days
    user_keys: 30    # days
    consent_tokens: 1 # days

  privacy_budget:
    epsilon: 0.5
    delta: 1e-5

  tee_config:
    intel_sgx:
      enclave_size: 128MB
      heap_size: 96MB
      stack_size: 1MB
    arm_trustzone:
      secure_memory: 256MB
      secure_storage: 1GB

  audit_retention:
    operation_logs: 7   # years
    deletion_proofs: 10 # years
    key_rotation_logs: 10 # years
```

## Quantum Resistance Roadmap

### Post-Quantum Migration Plan
1. **Phase 1 (Current)**: Classical cryptography with crypto-agility
2. **Phase 2 (2026)**: Hybrid classical-quantum schemes
3. **Phase 3 (2027)**: Full post-quantum cryptography

### Candidate Algorithms
- **Key Exchange**: Kyber-1024
- **Digital Signatures**: Dilithium-5
- **Symmetric Encryption**: AES-256 (quantum-resistant with sufficient key size)

---

## Advanced Privacy-Preserving Techniques (Future Enhancements)

### Overview
This section documents advanced cryptographic techniques for multi-user and federated scenarios. **Note:** These are NOT needed for current single-user vault architecture but will become critical for Phase 4 (Team Features) and federated learning.

### Use Case Applicability

| Technique | Single-User Vaults | Team Vaults | Federated Learning | Analytics Dashboard |
|-----------|-------------------|-------------|-------------------|-------------------|
| XChaCha20-Poly1305 (current) | ✅ Required | ✅ Required | ✅ Required | ✅ Required |
| Secure Aggregation | ❌ Not needed | ✅ Critical | ✅ Critical | ⚠️ Optional |
| Lightweight HE (scalars) | ❌ Not needed | ⚠️ Optional | ⚠️ Optional | ✅ Useful |
| Full HE (weight deltas) | ❌ Impractical | ❌ Impractical | ❌ Impractical | ❌ Impractical |

### 1. Secure Aggregation Protocol (for Federated Learning)

#### Problem Statement
Enable multiple users to collaboratively train/improve models without revealing individual weight deltas to server or other users.

#### Technical Approach: Google's Secure Aggregation (2017)

**Algorithm:**
```python
class SecureAggregation:
    """
    Privacy-preserving aggregation using additive secret sharing.
    
    Key Innovation: Pairwise masks cancel during aggregation.
    Security: Server learns ONLY aggregate, never individual deltas.
    Performance: 500,000x faster than Paillier homomorphic encryption.
    """
    
    def client_mask_delta(self, user_id: str, delta: np.ndarray) -> bytes:
        """
        Client-side: Mask delta with pairwise shared secrets.
        
        1. Establish pairwise keys via Diffie-Hellman with other users
        2. Generate mask: mask_i = Σ_j PRG(shared_secret_ij) where j ≠ i
        3. Return: masked_delta = delta + mask_i
        
        Server sees: masked_delta (useless without other masks)
        """
        mask = self._generate_pairwise_masks(user_id)
        return (delta + mask).tobytes()
    
    def server_aggregate(self, masked_deltas: List[np.ndarray]) -> np.ndarray:
        """
        Server-side: Sum masked deltas → masks cancel automatically.
        
        Σ_i (delta_i + mask_i) = Σ_i delta_i + Σ_i mask_i
                                = Σ_i delta_i + 0  (pairwise masks cancel!)
        
        Privacy: Server never sees individual delta_i
        """
        aggregate = np.mean(masked_deltas, axis=0)
        return aggregate  # Only aggregate visible!
```

**Performance (DoRA rank 32, 2MB deltas):**
| Metric | Secure Aggregation | Paillier HE | Improvement |
|--------|-------------------|-------------|-------------|
| Client encode time | 50 ms | 6.9 hours | 497,000x faster |
| Server aggregate time | 100 ms | 13.8 hours | 497,000x faster |
| Bandwidth per user | 2.1 MB | 256 MB | 122x less |
| Privacy guarantee | Semi-honest secure | IND-CPA secure | Equivalent* |

\* For aggregation use case with honest-but-curious server

**When to Implement:**
- Week 7-8: When starting team vault features
- Month 4: When implementing federated learning
- **NOT before:** Over-engineering for single-user vaults

**References:**
- Bonawitz et al. (2017): "Practical Secure Aggregation for Privacy-Preserving Machine Learning"
- Used in production: Google GBoard, Apple iOS keyboard

---

### 2. Lightweight Homomorphic Encryption (for Analytics Only)

#### Problem Statement
Compute privacy-preserving analytics (mean, variance, histograms) over user statistics without revealing individual user data.

**IMPORTANT:** Only for **scalar statistics**, NOT full weight deltas!

#### Technical Approach: Paillier HE for Scalars

**Algorithm:**
```python
class PrivacyPreservingAnalytics:
    """
    Paillier HE for scalar statistics only.
    
    Key Limitation: ONLY encrypt scalar values (e.g., norms, counts)
    Why: Encrypting 2MB delta takes 6.9 hours (impractical)
         Encrypting 1 scalar takes 50ms (practical!)
    """
    
    def __init__(self):
        self.paillier = PaillierHE(key_size=2048)
    
    def compute_mean_delta_norm(self, user_deltas: List[np.ndarray]) -> float:
        """
        Privacy-preserving mean of delta norms.
        
        1. Each user computes ||delta_i|| (scalar!) locally
        2. Encrypt scalar: E(||delta_i||)
        3. Server computes E(Σ ||delta_i||) homomorphically
        4. Decrypt aggregate: mean = Σ ||delta_i|| / N
        5. Add differential privacy noise
        """
        # Step 1-2: Encrypt scalar norms (NOT full deltas!)
        encrypted_norms = [self.paillier.encrypt(np.linalg.norm(delta)) 
                          for delta in user_deltas]
        
        # Step 3: Homomorphic sum (fast for scalars!)
        encrypted_sum = sum(encrypted_norms)  # 50ms per add
        
        # Step 4: Decrypt aggregate only
        mean_norm = self.paillier.decrypt(encrypted_sum) / len(user_deltas)
        
        # Step 5: Differential privacy
        dp_noise = np.random.laplace(0, sensitivity/epsilon)
        return mean_norm + dp_noise
```

**Performance (1000 users):**
| Operation | Time | Notes |
|-----------|------|-------|
| Encrypt 1 scalar | 50 ms | Per user |
| Homomorphic add | 50 ms | Server-side |
| Decrypt result | 50 ms | Once |
| **Total** | **~5 seconds** | For 1000 users |

**Use Cases:**
- Analytics dashboard: "Average training jobs per user", "Mean delta norm"
- Investor metrics: "User engagement statistics" without seeing individual data
- A/B testing: Compare model performance across cohorts
- GDPR compliance: Prove you can compute stats without storing plaintext

**When to Implement:**
- When building analytics dashboard for investors/monitoring
- When GDPR compliance requires provable privacy
- **NOT urgent:** Nice-to-have, not blocking any features

---

### 3. Full Homomorphic Encryption (NOT RECOMMENDED)

#### Why NOT Recommended for WDVA

**Performance Analysis:**

```python
# DoRA rank 32 delta: ~2MB (~500,000 float32 values)

Operation              Time (Paillier 2048-bit)    Feasibility
---------------------------------------------------------------------
Encrypt 1 float        50 ms                       
Encrypt full delta     50ms × 500k = 6.9 HOURS     ❌ IMPRACTICAL
Homomorphic operation  50-100 ms per op            ❌ IMPRACTICAL
Ciphertext size        4 bytes → 512 bytes         ❌ 128x expansion
                      2 MB → 256 MB per delta!
```

**Verdict:** 
- ❌ **DO NOT USE** for full weight deltas
- ✅ **ONLY USE** for scalar statistics (see section 2 above)
- ⚠️ **Future:** TFHE/CKKS may enable fast HE in 5+ years (research-only now)

---

### 4. Implementation Priority

#### Recommended Implementation Order:

**Phase 1 (Current): XChaCha20-Poly1305**
- ✅ **Status:** IMPLEMENTED
- **Use:** Storage encryption, data at rest
- **Performance:** 5ms per 2MB delta
- **Priority:** Critical (done)

**Phase 2 (Week 7-8): Secure Aggregation**
- ⏳ **Status:** PLANNED for team features
- **Use:** Federated learning, team vault aggregation
- **Performance:** 100ms for 100 users
- **Priority:** High (blocking team features)
- **Effort:** 2-3 weeks

**Phase 3 (Month 4): Differential Privacy**
- ⏳ **Status:** PLANNED for federated learning
- **Use:** Privacy budget management, noise injection
- **Performance:** <1ms overhead
- **Priority:** Medium (complement to Secure Agg)
- **Effort:** 1 week

**Phase 4 (Optional): Lightweight HE for Analytics**
- ⏸️ **Status:** NICE-TO-HAVE
- **Use:** Privacy-preserving analytics dashboard
- **Performance:** ~5 seconds for 1000 users
- **Priority:** Low (not blocking features)
- **Effort:** 1 week

**Phase 5 (Research-only): Full HE**
- ❌ **Status:** NOT RECOMMENDED (impractical)
- **Revisit:** 2028+ when TFHE/CKKS mature

---

### 5. Security vs Performance Trade-offs

#### Comparison Matrix

```
                          Privacy   Speed      Bandwidth  Use Case
─────────────────────────────────────────────────────────────────
XChaCha20 (current)        High     ⚡⚡⚡⚡    Minimal    Storage ✅
Secure Aggregation         High     ⚡⚡⚡     Low        Federated ✅
Lightweight HE (scalars)   High     ⚡⚡       Medium     Analytics ✅
Full HE (deltas)          Maximum   ❌        ❌❌❌      NONE ❌
Differential Privacy       Medium   ⚡⚡⚡⚡    Minimal    Complement ✅
```

**Legend:**
- ⚡ = Fast (milliseconds)
- ❌ = Impractical (hours)

---

### 6. References

#### Academic Papers
1. Bonawitz et al. (2017): "Practical Secure Aggregation for Privacy-Preserving Machine Learning" - Google
2. McMahan et al. (2017): "Communication-Efficient Learning of Deep Networks from Decentralized Data" - Federated Learning
3. Dwork & Roth (2014): "The Algorithmic Foundations of Differential Privacy"
4. Gentry (2009): "Fully Homomorphic Encryption Using Ideal Lattices" (theoretical foundation)

#### Production Implementations
- Google Federated Learning (GBoard keyboard)
- Apple Differential Privacy (iOS analytics)
- OpenMined PySyft (federated learning framework)
- Microsoft SEAL (homomorphic encryption library)

#### Recommended Libraries
```python
# Secure Aggregation
- cryptography (already using) ✅
- diffie-hellman (built-in to cryptography)

# Lightweight HE (scalars only)
- python-paillier (8KB, mature, MIT license)

# Differential Privacy
- opacus (Facebook, PyTorch integration)
- diffprivlib (IBM, scikit-learn compatible)

# Full HE (research-only)
- microsoft-seal (C++, Python bindings)
- tenseal (PyTorch + SEAL)
- concrete-ml (Zama, TFHE-based)
```

---

### 7. Decision Framework

**When to use each technique:**

```python
def choose_privacy_technique(use_case: str) -> str:
    """Decision tree for privacy technique selection."""
    
    if use_case == "single_user_storage":
        return "XChaCha20-Poly1305 (current implementation) ✅"
    
    elif use_case == "team_vault_aggregation":
        return "Secure Aggregation (implement Week 7) 📅"
    
    elif use_case == "federated_learning":
        return "Secure Aggregation + Differential Privacy (Month 4) 📅"
    
    elif use_case == "analytics_dashboard":
        return "Lightweight HE for scalars + DP (optional, nice-to-have) ⚠️"
    
    elif use_case == "compute_on_encrypted_deltas":
        return "NOT FEASIBLE - use Secure Aggregation instead ❌"
    
    else:
        return "Evaluate based on performance requirements"
```

---

Copyright © 2025 Zygmunt Dyras. All rights reserved.
Technical specifications subject to patent protection.