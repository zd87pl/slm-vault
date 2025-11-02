# Cloud-Based OCR & Q&A Pipeline Architecture

## Hypothetical Architecture: Cloud OCR + Q&A Generation

### Proposed Workflow

```
1. Client: PDF uploaded → Lightweight encryption (XChaCha20-Poly1305)
2. Client: Encrypted PDF → Cloud (RunPod OCR endpoint)
3. Cloud: Decrypt PDF → OCR (Ollama-vision-3.2 or DeepSeekOCR)
4. Cloud: Extract text → Generate Q&A pairs (using LLM)
5. Cloud: Encrypted Q&A dataset → Supabase Storage
6. Cloud: Encrypted dataset → RunPod Finetuning endpoint
7. Cloud: Decrypt in secure enclave → Train adapter
8. Client: Receive encrypted adapter
```

---

## Security Analysis

### Threat Model

**Assumptions:**
- ✅ Client trusts cloud for OCR/Q&A generation (accepts plaintext exposure during processing)
- ✅ Cloud infrastructure is trusted (RunPod, Supabase)
- ✅ Client wants lightweight encryption (no heavy client-side dependencies)

**Security Posture:**
- ⚠️ **Not Zero-Knowledge**: Cloud sees plaintext during OCR and Q&A generation
- ✅ **Encrypted in Transit**: All data encrypted before upload
- ✅ **Encrypted at Rest**: Datasets encrypted in Supabase Storage
- ✅ **Ephemeral Exposure**: Plaintext only in memory during processing
- ✅ **Secure Enclave**: Training happens in TEE (future)

---

## Implementation Architecture

### Component 1: Client-Side Lightweight Encryption

**File:** `advanced_vault/gui/pdf_encryption.py`

```python
"""
Lightweight PDF encryption for cloud OCR pipeline.
Uses XChaCha20-Poly1305 for authenticated encryption.
"""

import os
import base64
from Crypto.Cipher import ChaCha20_Poly1305
from Crypto.Random import get_random_bytes
from typing import Tuple, Dict

class PDFEncryption:
    """Lightweight PDF encryption for cloud pipeline."""
    
    def encrypt_pdf(self, pdf_bytes: bytes, encryption_key: Optional[bytes] = None) -> Tuple[Dict[str, str], bytes]:
        """
        Encrypt PDF with XChaCha20-Poly1305.
        
        Args:
            pdf_bytes: Raw PDF bytes
            encryption_key: Optional encryption key (generated if None)
            
        Returns:
            (encryption_metadata, encrypted_blob)
            - encryption_metadata: Dict with nonce, tag, algorithm (for decryption)
            - encrypted_blob: Encrypted PDF bytes
        """
        if encryption_key is None:
            encryption_key = os.urandom(32)  # 256-bit key
        
        # Generate 192-bit nonce for XChaCha20
        nonce = get_random_bytes(24)
        
        # Encrypt
        cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(pdf_bytes)
        
        # Package metadata (nonce and tag separate from ciphertext)
        metadata = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'algorithm': 'XChaCha20-Poly1305',
            'key_id': base64.b64encode(hashlib.sha256(encryption_key).digest()[:16]).decode('utf-8')  # Key identifier (not the key!)
        }
        
        return metadata, ciphertext
    
    def encrypt_pdf_for_cloud(self, pdf_path: str, user_id: str) -> Tuple[str, Dict[str, str], bytes]:
        """
        Encrypt PDF and prepare for cloud upload.
        
        Args:
            pdf_path: Path to PDF file
            user_id: User identifier
            
        Returns:
            (encryption_key_hex, metadata, encrypted_blob)
        """
        # Read PDF
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Generate encryption key
        encryption_key = os.urandom(32)
        
        # Encrypt
        metadata, encrypted_blob = self.encrypt_pdf(pdf_bytes, encryption_key)
        
        # Return key as hex (will be sent separately to cloud)
        encryption_key_hex = encryption_key.hex()
        
        return encryption_key_hex, metadata, encrypted_blob
```

---

### Component 2: Cloud OCR Endpoint (RunPod)

**File:** `src/rp_ocr_handler.py`

```python
"""
RunPod handler for OCR + Q&A generation pipeline.
Accepts encrypted PDF, decrypts, performs OCR, generates Q&A.
"""

import json
import base64
from Crypto.Cipher import ChaCha20_Poly1305
from typing import Dict, Any, List
from qa_generator import QAGenerator  # Your existing Q&A generator

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    RunPod handler for OCR + Q&A generation.
    
    Expected input:
    {
        "task": "ocr_qa",
        "encrypted_pdf_base64": "...",
        "encryption_metadata": {
            "nonce": "...",
            "tag": "...",
            "algorithm": "XChaCha20-Poly1305"
        },
        "encryption_key_hex": "...",  # Sent securely via separate channel
        "user_id": "..."
    }
    """
    try:
        input_data = event.get("input", {})
        task = input_data.get("task")
        
        if task == "ocr_qa":
            return handle_ocr_qa(input_data)
        else:
            return {"error": f"Unknown task: {task}"}
            
    except Exception as e:
        return {"error": str(e), "traceback": str(e.__traceback__)}


def handle_ocr_qa(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle OCR + Q&A generation pipeline.
    
    1. Decrypt PDF
    2. Perform OCR (Ollama-vision-3.2 or DeepSeekOCR)
    3. Generate Q&A pairs
    4. Encrypt Q&A dataset
    5. Return encrypted dataset + metadata
    """
    # Extract inputs
    encrypted_pdf_b64 = input_data.get("encrypted_pdf_base64")
    encryption_metadata = input_data.get("encryption_metadata", {})
    encryption_key_hex = input_data.get("encryption_key_hex")
    user_id = input_data.get("user_id")
    
    if not all([encrypted_pdf_b64, encryption_metadata, encryption_key_hex]):
        return {"error": "Missing required fields"}
    
    # Decode encryption key
    encryption_key = bytes.fromhex(encryption_key_hex)
    
    # Decode encrypted PDF
    encrypted_pdf = base64.b64decode(encrypted_pdf_b64)
    
    # Decrypt PDF
    pdf_bytes = decrypt_pdf(encrypted_pdf, encryption_metadata, encryption_key)
    
    # Step 1: OCR (using Ollama-vision-3.2 or DeepSeekOCR)
    text_chunks = perform_ocr(pdf_bytes)
    
    # Step 2: Generate Q&A pairs
    qa_generator = QAGenerator()  # Your existing generator
    qa_pairs = []
    for chunk in text_chunks:
        chunk_qa = qa_generator.generate_qa_pairs(chunk, num_pairs=3)
        qa_pairs.extend(chunk_qa)
    
    # Step 3: Encrypt Q&A dataset IMMEDIATELY
    # Use the same encryption key for consistency
    encrypted_dataset, dataset_metadata = encrypt_qa_dataset(qa_pairs, encryption_key)
    
    # Step 4: Upload to Supabase Storage (encrypted)
    dataset_url = upload_to_supabase_storage(
        encrypted_dataset=encrypted_dataset,
        user_id=user_id,
        metadata=dataset_metadata
    )
    
    # Return result (encrypted dataset URL + metadata)
    return {
        "status": "completed",
        "user_id": user_id,
        "dataset_url": dataset_url,
        "encryption_metadata": dataset_metadata,
        "qa_pairs_count": len(qa_pairs),
        "chunks_processed": len(text_chunks)
    }


def decrypt_pdf(encrypted_pdf: bytes, metadata: Dict[str, str], encryption_key: bytes) -> bytes:
    """Decrypt PDF using XChaCha20-Poly1305."""
    nonce = base64.b64decode(metadata['nonce'])
    tag = base64.b64decode(metadata['tag'])
    
    cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
    pdf_bytes = cipher.decrypt_and_verify(encrypted_pdf, tag)
    
    return pdf_bytes


def perform_ocr(pdf_bytes: bytes) -> List[str]:
    """
    Perform OCR on PDF bytes.
    
    Options:
    1. Ollama-vision-3.2 (local on RunPod worker)
    2. DeepSeekOCR API
    3. PyPDF2 + fallback to OCR if needed
    """
    import tempfile
    import pdf2image
    from PIL import Image
    
    # Save PDF to temp file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    
    try:
        # Convert PDF pages to images
        images = pdf2image.convert_from_path(tmp_path)
        
        # Use Ollama-vision-3.2 for OCR
        text_chunks = []
        for image in images:
            # Convert PIL image to base64
            import io
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_b64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
            
            # Call Ollama vision API
            import requests
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2-vision",
                    "prompt": "Extract all text from this image. Return only the text, no explanations.",
                    "images": [img_b64],
                    "stream": False
                }
            )
            
            if response.status_code == 200:
                text = response.json().get("response", "")
                if text:
                    text_chunks.append(text)
    finally:
        # Cleanup temp file
        import os
        os.unlink(tmp_path)
    
    return text_chunks


def encrypt_qa_dataset(qa_pairs: List[Dict], encryption_key: bytes) -> Tuple[bytes, Dict[str, str]]:
    """Encrypt Q&A dataset immediately after generation."""
    import json
    
    # Serialize Q&A pairs
    dataset_json = json.dumps(qa_pairs).encode('utf-8')
    
    # Encrypt using same method as PDF
    nonce = get_random_bytes(24)
    cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(dataset_json)
    
    # Package encrypted dataset
    encrypted_package = {
        'nonce': base64.b64encode(nonce).decode('utf-8'),
        'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
        'tag': base64.b64encode(tag).decode('utf-8'),
        'algorithm': 'XChaCha20-Poly1305'
    }
    
    encrypted_blob = json.dumps(encrypted_package).encode('utf-8')
    metadata = {
        'nonce': base64.b64encode(nonce).decode('utf-8'),
        'tag': base64.b64encode(tag).decode('utf-8'),
        'algorithm': 'XChaCha20-Poly1305'
    }
    
    return encrypted_blob, metadata
```

---

### Component 3: Secure Key Transmission

**Problem:** How to securely send encryption key to cloud?

**Solution 1: HTTPS + Backend API (Recommended)**

```python
# Client sends encrypted PDF + metadata to backend
# Backend forwards to RunPod with key via secure channel

# Client side:
response = requests.post(
    f"{backend_url}/api/ocr/process",
    headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    },
    json={
        "encrypted_pdf_base64": encrypted_pdf_b64,
        "encryption_metadata": metadata,
        "encryption_key_hex": encryption_key_hex  # Sent via HTTPS
    }
)

# Backend validates user, forwards to RunPod
# Backend never stores the key (ephemeral)
```

**Solution 2: Key Derivation from User Secret**

```python
# Derive encryption key from user's master key + document ID
# Cloud can't decrypt without user's master key (stored client-side only)

def derive_document_key(user_master_key: bytes, document_id: str) -> bytes:
    """Derive document-specific encryption key."""
    import hashlib
    return hashlib.pbkdf2_hmac(
        'sha256',
        user_master_key,
        document_id.encode(),
        100000,
        32
    )

# Client sends document_id + encrypted PDF
# Cloud requests key derivation from client (via secure API)
# Or: Client sends derived key via HTTPS (ephemeral)
```

---

## Security Trade-offs

### ✅ Pros

1. **Lightweight Client**: No heavy OCR dependencies (Ollama, etc.)
2. **Scalable**: Cloud handles OCR for all users
3. **Better OCR Quality**: Can use larger models (DeepSeekOCR, etc.)
4. **Unified Pipeline**: OCR → Q&A → Training all in cloud
5. **Encrypted Storage**: Datasets encrypted before persistence

### ⚠️ Cons

1. **Not Zero-Knowledge**: Cloud sees plaintext during OCR/Q&A
2. **Key Transmission**: Must securely send encryption key to cloud
3. **Trust Dependency**: Requires trust in cloud infrastructure
4. **Regulatory Concerns**: May violate HIPAA/GDPR if processing PHI/PII

---

## Implementation Recommendations

### Phase 1: Proof of Concept

1. **Client-side PDF encryption** (lightweight)
2. **Backend API endpoint** for OCR processing
3. **RunPod OCR handler** (Ollama-vision-3.2)
4. **Secure key transmission** (HTTPS + ephemeral)

### Phase 2: Production Hardening

1. **Secure Enclave (TEE)** for OCR/Q&A processing
2. **Key derivation** from user secrets (no key transmission)
3. **Audit logging** for all access attempts
4. **GDPR/HIPAA compliance** features

### Phase 3: Advanced Security

1. **Homomorphic encryption** for OCR (future)
2. **Federated learning** for Q&A generation
3. **Zero-knowledge proofs** for verification

---

## Comparison with Current Architecture

| Feature | Current (Encrypt Immediately) | Proposed (Cloud OCR) |
|---------|------------------------------|---------------------|
| **Client Dependencies** | Ollama required | None (lightweight) |
| **Zero-Knowledge** | ✅ Yes (local OCR) | ⚠️ No (cloud sees plaintext) |
| **OCR Quality** | Depends on local model | Can use best models |
| **Scalability** | Limited by client | ✅ Cloud scales |
| **Security Posture** | ✅ Highest | ⚠️ Acceptable (for non-sensitive data) |
| **Use Case** | High-security data | Convenience-focused |

---

## Conclusion

**This architecture is viable IF:**
- ✅ Users accept cloud processing plaintext (non-sensitive data)
- ✅ HTTPS + backend API for secure key transmission
- ✅ Encryption at rest for all datasets
- ✅ Future: Secure enclave (TEE) for processing

**Best for:**
- Users who prioritize convenience over absolute zero-knowledge
- Non-sensitive documents (public knowledge, research papers)
- Teams needing cloud scalability

**Not recommended for:**
- Healthcare data (PHI)
- Financial documents
- Legal privileged information
- Any data requiring zero-knowledge compliance

---

## Next Steps

1. Implement proof-of-concept client-side encryption
2. Create backend API endpoint `/api/ocr/process`
3. Deploy RunPod OCR handler
4. Test end-to-end pipeline
5. Evaluate security vs. convenience trade-offs

