# Lighter OCR Alternatives to Llama 3.2 Vision (7.8GB)

## Problem
Llama 3.2 Vision is 7.8GB, which is quite large for local deployment. Are there smaller alternatives?

## Options

### Option 1: Smaller Vision LLMs (via Ollama)

**Llama 3.2 Vision 1B** (~1-2GB)
- ✅ Available via Ollama: `ollama pull llama3.2-vision:1b`
- ✅ Same API as current implementation
- ⚠️ Lower quality OCR (but may be acceptable for simple documents)
- ✅ Minimal code changes needed

**SmolVLM2** (~256M-2.2B parameters)
- ✅ Very small (256M version ~500MB-1GB)
- ✅ Available via Ollama: `ollama pull smolvlm2`
- ⚠️ May have lower OCR accuracy
- ✅ Good for simple text extraction

**LLaVA-Mini** (~1-2GB)
- ✅ Efficient single vision token processing
- ✅ Available via Ollama: `ollama pull llava-mini`
- ✅ Good balance of size/quality
- ✅ Supported by Ollama

### Option 2: Dedicated OCR Libraries (Not LLM-based)

**EasyOCR** (~500MB-1GB)
- ✅ Pure OCR (not LLM) - faster, smaller
- ✅ Works offline
- ✅ Good for simple text extraction
- ⚠️ Requires different implementation (not Ollama API)
- ✅ Supports multiple languages
- ✅ Handles rotated text well

**PaddleOCR** (~100-200MB)
- ✅ Very lightweight
- ✅ Fast inference
- ✅ Good accuracy for structured documents
- ⚠️ Different API (not Ollama)
- ✅ Good for simple PDFs

**Tesseract OCR** (~50MB)
- ✅ Smallest option
- ✅ Mature, stable
- ⚠️ Lower quality than modern OCR
- ⚠️ Struggles with complex layouts
- ✅ Good fallback option

### Option 3: Hybrid Approach

**Use PyPDF2 first, then lightweight OCR only if needed**
- ✅ Current implementation already does this
- ✅ Add EasyOCR/Tesseract as fallback instead of vision LLM
- ✅ Only use OCR when PyPDF2 fails
- ✅ Most PDFs don't need OCR anyway

---

## Recommendation

### For Most Users: **Llama 3.2 Vision 1B** (via Ollama)

**Pros:**
- ✅ Same code (just change model name)
- ✅ Still good quality (better than Tesseract)
- ✅ ~1-2GB instead of 7.8GB
- ✅ Zero code changes needed

**Implementation:**
```python
# In ollama_setup.py, change default model:
self.model = ollama_model or os.getenv("OLLAMA_OCR_MODEL", "llama3.2-vision:1b")
```

### For Advanced Users: **EasyOCR** (better quality/size ratio)

**Pros:**
- ✅ Better OCR quality than 1B vision model
- ✅ Smaller than vision LLM
- ✅ Faster inference
- ✅ Purpose-built for OCR

**Cons:**
- ⚠️ Requires additional Python package
- ⚠️ Different API (not Ollama)
- ⚠️ Need to modify code

---

## Size Comparison

| Model/Tool | Size | Quality | Speed | Easy Setup |
|------------|------|---------|-------|------------|
| Llama 3.2 Vision (current) | 7.8GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ Yes |
| Llama 3.2 Vision 1B | ~1-2GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Yes |
| SmolVLM2 256M | ~500MB-1GB | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Yes |
| EasyOCR | ~500MB-1GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⚠️ Medium |
| PaddleOCR | ~100-200MB | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⚠️ Medium |
| Tesseract | ~50MB | ⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Yes |

---

## Quick Implementation: Switch to Llama 3.2 Vision 1B

**File:** `advanced_vault/gui/ollama_setup.py`

```python
# Change line 25:
def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2-vision:1b"):
```

**File:** `advanced_vault/gui/pdf_processor.py`

```python
# Change line 59:
self.ollama_model = ollama_model or os.getenv("OLLAMA_OCR_MODEL", "llama3.2-vision:1b")
```

That's it! No other changes needed. Users just pull the smaller model:
```bash
ollama pull llama3.2-vision:1b
```

---

## Future: EasyOCR Integration (Optional)

If you want even better OCR quality/size ratio, we could add EasyOCR as an alternative:

```python
# In pdf_processor.py
try:
    import easyocr
    reader = easyocr.Reader(['en', 'pl'])  # Support multiple languages
    
    # Convert PDF to images
    images = pdf2image.convert_from_path(pdf_path)
    
    # Extract text from each image
    text_chunks = []
    for img in images:
        results = reader.readtext(img)
        page_text = ' '.join([det[1] for det in results])
        text_chunks.append(page_text)
    
    return '\n\n'.join(text_chunks)
except ImportError:
    # Fallback to Ollama
    return self._extract_text_with_ollama_ocr(pdf_path)
```

---

## My Recommendation

**Start with Llama 3.2 Vision 1B** - it's the easiest change (just modify default model name) and gives you:
- ✅ 75% size reduction (7.8GB → ~1-2GB)
- ✅ Still good OCR quality
- ✅ Zero code changes (just config)
- ✅ Same user experience

If users still want smaller, we can add EasyOCR as an option later.

