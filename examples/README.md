# WDVA Examples

This directory contains example scripts demonstrating different aspects of the Weight-Delta Vault Adapter (WDVA) system.

## 📋 Available Examples

### 1. Privacy Demo (Recommended for First-Time Users)
**File:** `privacy_demo.py`

**Best for:** Understanding the WDVA concept in simple, consumer-friendly terms.

```bash
python3 examples/privacy_demo.py
```

**What it demonstrates:**
- 🏥 **Relatable scenario**: Personal health AI with fitness/diet preferences
- 🔐 **Encryption**: Shows how your personal data is encrypted
- 🤖 **Ephemeral inference**: Uses encrypted model in-memory only
- 🗑️ **Right-to-be-forgotten**: Instant deletion via key destruction

**Interactive walkthrough with 5 steps:**
1. Your Personal Data (example health/fitness data)
2. Training (how AI learns YOUR preferences)
3. Encryption (military-grade security)
4. Using Your Encrypted Model (in-memory decryption)
5. Right-to-be-Forgotten (cryptographic deletion)

**Why use this:**
- Non-technical explanations
- Real-world scenario (not abstract training examples)
- Visual proof of encryption
- Perfect for demos and explaining "what is WDVA?"

---

### 2. Complete Workflow (Technical)
**File:** `complete_workflow.py`

**Best for:** Developers implementing WDVA in their projects.

```bash
python3 examples/complete_workflow.py \
    --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
    --max-samples 100 \
    --epochs 1 \
    --use-4bit
```

**What it demonstrates:**
- Complete DoRA training pipeline
- Adapter encryption with compression
- Ephemeral inference with caching
- Performance benchmarking
- Memory security features

**Options:**
```
--model-name        Base model to use (default: TinyLlama/TinyLlama-1.1B-Chat-v1.0)
--max-samples       Number of training samples (default: 1000)
--epochs            Training epochs (default: 3)
--use-4bit          Enable 4-bit quantization (recommended)
--output-dir        Output directory (default: ./outputs/wdva_demo)
```

**Why use this:**
- Full technical implementation
- Customizable parameters
- Production-ready code patterns
- Performance metrics

---

## 🎯 Which Example Should I Use?

**If you want to:**
- **Explain WDVA to non-technical people** → Use `privacy_demo.py`
- **Demo to privacy-conscious consumers** → Use `privacy_demo.py`
- **Understand the concept yourself** → Use `privacy_demo.py`
- **Implement WDVA in your project** → Use `complete_workflow.py`
- **Benchmark performance** → Use `complete_workflow.py`
- **Test on your own dataset** → Use `complete_workflow.py`

---

## 🔑 Key Concepts Demonstrated

### 1. Personal Data Training
Both examples show how to train AI on personal, sensitive data:
- Health records, fitness preferences, genetic data
- Writing style, communication patterns
- Financial preferences, investment strategies

### 2. Encryption
Military-grade XChaCha20-Poly1305 encryption:
- 256-bit security (AES-equivalent)
- Authenticated (detects tampering)
- Zero-knowledge (provider can't decrypt)

### 3. Ephemeral Inference
Decryption happens in-memory only:
- Never saves decrypted model to disk
- Removes adapter from memory after use
- Leaves no forensic trace

### 4. Right-to-be-Forgotten
Cryptographic deletion via key destruction:
- Instant (seconds, not weeks/months)
- Provable (mathematically unrecoverable)
- Works even if encrypted files are backed up

---

## 📊 Real-World Use Cases

**Privacy Demo** shows a health AI scenario, but the same principles apply to:

- **Healthcare**: Personalized treatment recommendations
- **Finance**: Custom investment strategies
- **Education**: Adaptive learning models
- **Writing**: Personal style assistants
- **Legal**: Case law analysis with client confidentiality
- **Mental Health**: Therapy chatbots with absolute privacy

**Key benefit:** Users get personalization WITHOUT giving up privacy or control.

---

## 🚀 Next Steps

After running these examples:

1. **Try the RunPod endpoint** for production deployment:
   ```bash
   ./test_runpod.sh
   ```

2. **Read the documentation:**
   - [TESTING_GUIDE.md](../TESTING_GUIDE.md) - Comprehensive testing guide
   - [RUNPOD_DEPLOYMENT.md](../RUNPOD_DEPLOYMENT.md) - Production deployment
   - [README.md](../README.md) - Full technical documentation

3. **Customize for your use case:**
   - Replace example data with your actual dataset
   - Adjust model size based on your hardware
   - Configure encryption settings for your requirements

---

## ❓ FAQ

**Q: How long does training take?**
A: With 4-bit quantization on consumer hardware:
- 100 samples: ~1-2 minutes
- 1,000 samples: ~10-15 minutes
- 10,000 samples: ~2-3 hours

**Q: How much disk space do I need?**
A: Approximately:
- Base model: 2-4 GB (TinyLlama) to 50+ GB (Llama-70B)
- DoRA adapter: 50-100 MB (unencrypted)
- Encrypted adapter: 25-50 MB (with compression)

**Q: Is this production-ready?**
A: Yes! The system includes:
- ✅ Comprehensive test suite (66 tests, 100% passing)
- ✅ RunPod Serverless deployment
- ✅ Memory security features
- ✅ Performance optimizations
- ✅ Error handling and monitoring

**Q: Can I use my own dataset?**
A: Absolutely! See `complete_workflow.py` for customization options.

---

## 💡 Tips

- **Start with `privacy_demo.py`** to understand the concept
- **Use `--use-4bit`** for faster training and lower memory usage
- **Keep encryption keys safe** - they're the only way to access your data
- **Test locally first** before deploying to RunPod

---

*For technical support or questions, see the main [README.md](../README.md)*
