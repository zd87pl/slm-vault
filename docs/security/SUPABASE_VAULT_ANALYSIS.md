# Supabase Vault Integration Analysis

## What is Supabase Vault?

Supabase Vault is a PostgreSQL extension that provides:
- **Server-side encryption** using pgcrypto
- Encrypted secret storage in PostgreSQL
- Key management within Supabase
- Functions for encryption/decryption

**Status:** Public Alpha (not production-ready yet)

---

## Current Architecture vs. Supabase Vault

### Current Approach (Plaintext Storage) ❌
```
Dataset (plaintext) 
    → Supabase Storage (plaintext)
    → RunPod downloads (plaintext)
```

### Option 1: Supabase Vault (Server-Side Encryption) ⚠️
```
Dataset (plaintext)
    → Supabase Vault encrypts (server-side)
    → Stored encrypted in PostgreSQL
    → Supabase can decrypt (violates zero-knowledge)
```

**Problem:** Supabase Vault is **server-side encryption** - Supabase can decrypt your data. This violates our zero-knowledge principle.

### Option 2: Client-Side Encryption + Supabase Storage ✅
```
Dataset encrypted client-side (XChaCha20-Poly1305)
    → Supabase Storage (encrypted blob)
    → Supabase never sees plaintext ✅
    → RunPod downloads encrypted blob
    → Decrypts only in secure enclave
```

**Best Approach:** This maintains zero-knowledge while using Supabase Storage.

---

## Recommended Solution: Hybrid Approach

### Use Supabase Storage with Client-Side Encryption

**Architecture:**
1. **Client-side encryption** (before upload)
   - Use XChaCha20-Poly1305 (same as adapters)
   - Generate encryption key client-side
   - Encrypt dataset JSONL file

2. **Store encrypted blob** in Supabase Storage
   - Upload encrypted dataset as binary blob
   - Use RLS policies for access control
   - Supabase never sees plaintext ✅

3. **Secure key storage** (separate from dataset)
   - Store encryption key hash in Supabase (for verification)
   - Actual key stored client-side only (never sent to server)
   - Or: Use Supabase Vault for key storage (optional)

4. **RunPod decryption** (future)
   - Download encrypted dataset
   - Decrypt in secure enclave only
   - Training happens on decrypted data in enclave

---

## Implementation Plan

### Phase 1: Client-Side Dataset Encryption

**File:** `advanced_vault/gui/training_manager.py`

```python
import os
from Crypto.Cipher import ChaCha20_Poly1305
from Crypto.Random import get_random_bytes
import base64

def encrypt_dataset(self, dataset_path: str, encryption_key: bytes) -> str:
    """Encrypt dataset file before upload."""
    # Read dataset
    with open(dataset_path, 'rb') as f:
        dataset_data = f.read()
    
    # Generate nonce
    nonce = get_random_bytes(24)  # 192-bit nonce for XChaCha20
    
    # Encrypt
    cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(dataset_data)
    
    # Package encrypted data
    encrypted_package = {
        'nonce': base64.b64encode(nonce).decode(),
        'ciphertext': base64.b64encode(ciphertext).decode(),
        'tag': base64.b64encode(tag).decode(),
        'algorithm': 'XChaCha20-Poly1305'
    }
    
    # Save encrypted dataset
    encrypted_path = dataset_path + '.encrypted'
    with open(encrypted_path, 'w') as f:
        json.dump(encrypted_package, f)
    
    return encrypted_path

def _upload_dataset_to_supabase_storage(self, encrypted_dataset_path: str) -> Optional[str]:
    """Upload encrypted dataset to Supabase Storage."""
    # Read encrypted package
    with open(encrypted_dataset_path, 'r') as f:
        encrypted_package = json.load(f)
    
    # Upload as binary blob (Supabase sees only encrypted data)
    encrypted_blob = json.dumps(encrypted_package).encode('utf-8')
    
    # Upload to Supabase Storage
    response = self.supabase.storage.from_("datasets").upload(
        path=f"{self.user_id}/{os.path.basename(encrypted_dataset_path)}",
        file=encrypted_blob,
        file_options={"content-type": "application/json"}
    )
    
    # Return signed URL (still encrypted)
    signed_url = self.supabase.storage.from_("datasets").create_signed_url(
        path=f"{self.user_id}/{os.path.basename(encrypted_dataset_path)}",
        expires_in=3600
    )
    
    return signed_url['signedURL']
```

### Phase 2: Update Training Workflow

**Changes needed:**
1. Encrypt dataset before saving locally
2. Upload encrypted dataset to Supabase
3. Send encrypted dataset URL + encryption key to backend
4. Backend forwards to RunPod (still encrypted)
5. RunPod decrypts in secure enclave (future)

**Current code location:** `vault_app.py:1672-1673`
```python
# OLD: Save plaintext dataset
dataset_path = self.training_manager.save_dataset(qa_pairs, dataset_filename)

# NEW: Save and encrypt dataset
dataset_path = self.training_manager.save_dataset(qa_pairs, dataset_filename)
encryption_key = os.urandom(32)  # Already generated
encrypted_dataset_path = self.training_manager.encrypt_dataset(dataset_path, encryption_key)
```

---

## Supabase Vault: When to Use It

### ✅ Good Use Cases for Supabase Vault:
1. **API Keys** (backend secrets)
2. **Environment Variables** (service config)
3. **Service-to-Service Credentials**
4. **Master Key Storage** (if you want server-managed keys)

### ❌ NOT for User Data:
1. **Training Datasets** - Need zero-knowledge (client-side encryption)
2. **User Documents** - Need zero-knowledge
3. **Personal Information** - Need zero-knowledge

---

## Recommendation

**Use Supabase Storage + Client-Side Encryption** (NOT Supabase Vault):

1. ✅ **Maintains zero-knowledge** - Supabase never sees plaintext
2. ✅ **Uses existing infrastructure** - Supabase Storage already configured
3. ✅ **Consistent encryption** - Same XChaCha20-Poly1305 as adapters
4. ✅ **WDVA aligned** - Follows zero-knowledge principles
5. ✅ **Production ready** - Supabase Storage is stable

**Don't use Supabase Vault for datasets because:**
- ❌ Server-side encryption (Supabase can decrypt)
- ❌ Violates zero-knowledge principle
- ❌ Still in Alpha (not production-ready)
- ❌ Designed for secrets, not user data

---

## Next Steps

1. **Implement client-side dataset encryption** in `training_manager.py`
2. **Update upload flow** to encrypt before Supabase Storage
3. **Keep encryption keys client-side only** (never send to backend)
4. **Future: Implement secure enclave decryption** on RunPod

This approach gives us:
- ✅ Zero-knowledge storage
- ✅ Secure cloud storage (Supabase Storage)
- ✅ WDVA compliance
- ✅ Production-ready solution

