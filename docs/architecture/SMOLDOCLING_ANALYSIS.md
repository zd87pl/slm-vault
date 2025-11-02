# SmolDocling-256M Analysis

## Overview

[SmolDocling-256M-preview-mlx-bf16](https://huggingface.co/docling-project/SmolDocling-256M-preview-mlx-bf16) is a specialized 256M parameter model designed specifically for document processing (OCR + structure extraction).

## Key Features

- ✅ **Very Small**: ~256M parameters (much smaller than 7.8GB llama3.2-vision)
- ✅ **Purpose-Built**: Specifically designed for document processing (not general vision)
- ✅ **Structured Output**: Produces DocTags format (preserves document structure)
- ✅ **OCR + Layout**: Extracts text AND preserves layout/structure
- ✅ **Table/Chart Recognition**: Handles structured data better than general OCR

## Important Limitations

### ⚠️ Apple Silicon Only (MLX Framework)

**Critical:** SmolDocling-MLX only works on **Apple Silicon Macs** (M1/M2/M3). It will **NOT work on Intel Macs** or Linux/Windows.

MLX is Apple's machine learning framework optimized for Apple Silicon. It won't run on Intel processors.

### ⚠️ Different API (Not Ollama-Compatible)

**Current Implementation:** Uses Ollama HTTP API (simple, universal)
```python
# Current Ollama API
response = requests.post(
    "http://localhost:11434/api/generate",
    json={"model": "llama3.2-vision:1b", "images": [image_b64], ...}
)
```

**SmolDocling:** Uses MLX Python library (different API)
```python
# SmolDocling MLX API
from mlx_vlm import load, generate
model, processor = load("docling-project/SmolDocling-256M-preview-mlx-bf16")
output = generate(model, processor, prompt, images, ...)
```

### ⚠️ Structured Output (DocTags Format)

SmolDocling outputs **DocTags format** (structured document representation), not plain text:
```xml
<doctag>
  <paragraph>...</paragraph>
  <table>...</table>
  <heading>...</heading>
</doctag>
```

This needs conversion to plain text for our Q&A generation pipeline.

## Size Comparison

| Model | Size | Platform | API | Output Format |
|-------|------|----------|-----|---------------|
| **Llama 3.2 Vision** | 7.8GB | Universal | Ollama HTTP | Plain text |
| **Llama 3.2 Vision 1B** | ~1-2GB | Universal | Ollama HTTP | Plain text |
| **SmolDocling-256M** | ~500MB-1GB | **Apple Silicon only** | MLX Python | DocTags (structured) |

## Implementation Complexity

### Option 1: Keep Ollama (Current)

**Pros:**
- ✅ Works on all platforms (Mac Intel, Mac Silicon, Linux, Windows)
- ✅ Simple HTTP API
- ✅ Already implemented
- ✅ Users familiar with Ollama ecosystem

**Cons:**
- ⚠️ Larger model (1-2GB vs 500MB)

### Option 2: Add SmolDocling Support (New)

**Pros:**
- ✅ Smaller model (~500MB)
- ✅ Better document structure preservation
- ✅ Purpose-built for documents

**Cons:**
- ❌ **Apple Silicon only** (excludes Intel Macs, Linux, Windows)
- ⚠️ Different API (need new implementation)
- ⚠️ Structured output (need DocTags → plain text conversion)
- ⚠️ Additional dependency (`mlx-vlm`, `docling-core`)
- ⚠️ More complex setup

### Option 3: Hybrid Approach (Recommended)

**Detection:**
```python
import platform

def detect_apple_silicon() -> bool:
    """Check if running on Apple Silicon."""
    if platform.system() != "Darwin":
        return False
    # Check for Apple Silicon
    import subprocess
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True
        )
        return "Apple" in result.stdout
    except:
        return False

# Use SmolDocling on Apple Silicon, Ollama on others
if detect_apple_silicon():
    ocr_engine = "smoldocling"
else:
    ocr_engine = "ollama"
```

**Implementation:**
```python
# In pdf_processor.py
def _extract_text_with_ocr(self, pdf_path: str):
    if self.ocr_engine == "smoldocling":
        return self._extract_with_smoldocling(pdf_path)
    else:
        return self._extract_with_ollama_ocr(pdf_path)
```

## Recommendation

### For Now: **Keep Llama 3.2 Vision 1B** (~1-2GB)

**Reasons:**
1. ✅ **Universal compatibility** - works on all platforms
2. ✅ **Already implemented** - zero additional work
3. ✅ **Good enough** - 1-2GB is acceptable for most users
4. ✅ **Simple** - users already familiar with Ollama

### Future: **Add SmolDocling as Optional Enhancement**

**When to consider:**
- If users specifically request it
- If we target Apple Silicon users primarily
- If we need better document structure preservation
- When MLX support expands to other platforms

**Implementation effort:** Medium (new API, DocTags conversion, platform detection)

## Alternative: Non-MLX SmolDocling?

Check if there's a standard PyTorch/Transformers version:
- [SmolDocling original](https://huggingface.co/ds4sd/SmolDocling-256M-preview) - might work on all platforms
- Requires checking if it can run without MLX

## Summary

**SmolDocling-MLX is great BUT:**
- ❌ **Apple Silicon only** (major limitation)
- ⚠️ Different API (needs new implementation)
- ⚠️ Structured output (needs conversion)

**Recommendation:** Stick with **Llama 3.2 Vision 1B** for now. It's universal, already working, and 1-2GB is reasonable. Consider SmolDocling later if:
1. We have many Apple Silicon users asking for it
2. We need better document structure preservation
3. MLX expands to other platforms

