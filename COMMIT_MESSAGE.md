# Commit Message: Fix QA Generation Pipeline to Use Cloud Endpoint

## Summary
Fixed critical issues preventing the training pipeline from using the cloud-based RunPod QA generation endpoint. The system was falling back to local MLX models instead of the intended cloud endpoint, resulting in low-quality QA pairs for small PDFs.

## Changes

### 1. QA Generation Endpoint Configuration (`advanced_vault/gui/qa_generator.py`)
- Added `RUNPOD_QA_ENDPOINT_ID` environment variable support
- Endpoint is configurable and separate from inference endpoint
- Requires `RUNPOD_QA_ENDPOINT_ID` to be set for cloud QA generation

### 2. API Key Handling (`advanced_vault/gui/qa_generator.py`, `advanced_vault/gui/vault_app.py`)
- Added `RUNPOD_QA_API_KEY` environment variable support
- Defaults to `RUNPOD_API_KEY` if not explicitly set
- Added `_ensure_qa_api_key_set()` method called at initialization
- Improved logging to show which API key source is being used
- Priority: `RUNPOD_QA_API_KEY` > constructor `api_key` > `RUNPOD_API_KEY`

### 3. PDF Persistence Fix (`advanced_vault/gui/vault_app.py`)
- Changed PDF storage from temporary files to persistent location (`~/.vault/temp_pdfs/`)
- PDFs are now saved with timestamped filenames
- Ensures PDFs exist when training workflow accesses them
- Prevents "file not found" errors during QA generation

### 4. Cryptographic Nonce Size Fix (`advanced_vault/gui/qa_generator.py`)
- Fixed `ValueError: Nonce must be 12 bytes` error
- `cryptography` backend now uses 12-byte nonces (ChaCha20Poly1305 standard)
- `pycryptodome` backend continues using 24-byte nonces (XChaCha20)
- Decryption handles both nonce sizes automatically

### 5. Docker Dependencies (`docker/Dockerfile.synthetic_qa`, `docker/Dockerfile.synthetic_qa.standalone`, `docker/requirements.txt`)
- Added `hf_transfer>=0.1.0` to all Dockerfiles
- Fixes `ValueError: Fast download using 'hf_transfer' is enabled but 'hf_transfer' package is not available`
- Enables faster HuggingFace model downloads on RunPod endpoint

## Files Changed
- `advanced_vault/gui/qa_generator.py` - Endpoint configuration via env var, API key handling, nonce fix
- `advanced_vault/gui/vault_app.py` - PDF persistence, API key initialization, improved logging
- `docker/Dockerfile.synthetic_qa` - Added hf_transfer dependency
- `docker/Dockerfile.synthetic_qa.standalone` - Added hf_transfer dependency
- `docker/requirements.txt` - Added hf_transfer dependency

## Testing
- Verified QA generation uses cloud endpoint when `RUNPOD_API_KEY` is set
- Verified PDF persistence prevents file not found errors
- Verified nonce size fix resolves encryption errors
- Verified hf_transfer installation resolves model download errors

## Impact
- QA generation now reliably uses cloud endpoint instead of local MLX fallback
- Higher quality QA pairs for training adapters
- Improved adapter response quality for small PDF files
- Reduced training failures due to missing files or encryption errors

---

## Suggested Git Command

```bash
git add advanced_vault/gui/qa_generator.py \
        advanced_vault/gui/vault_app.py \
        docker/Dockerfile.synthetic_qa \
        docker/Dockerfile.synthetic_qa.standalone \
        docker/requirements.txt

git commit -m "fix: Use cloud QA generation endpoint instead of local MLX fallback

- Add RUNPOD_QA_ENDPOINT_ID environment variable for QA generation endpoint config
- Add RUNPOD_QA_API_KEY support with automatic fallback to RUNPOD_API_KEY
- Fix PDF persistence by saving to ~/.vault/temp_pdfs/ instead of temp files
- Fix cryptographic nonce size (12 bytes for cryptography backend)
- Add hf_transfer to Dockerfiles for faster HuggingFace downloads

Fixes issues where training pipeline was using local MLX models instead
of cloud endpoint, resulting in low-quality QA pairs for small PDFs."
```

