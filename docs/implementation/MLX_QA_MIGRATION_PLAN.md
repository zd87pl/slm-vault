# MLX-Optimized Q&A Generation Migration Plan

## Executive Summary

Migration from TinyLlama 1.1B (Ollama) to MLX-optimized Qwen2.5-3B-Instruct-4bit with structured output generation to solve:
- ❌ Only 1.67 Q&A pairs per chunk (instead of 3)
- ❌ Always requires manual extraction (poor JSON)
- ❌ Incomplete answers (truncated responses)
- ❌ 800-char context limit

**Target:** Guaranteed 3 Q&A pairs with valid JSON in 5-10 seconds per chunk on M2-M4 Air.

---

## Current State Analysis

### Existing Implementation (`qa_generator.py`)

**Architecture:**
- Model: TinyLlama 1.1B via Ollama API
- Format: Q:/A: text (not JSON - TinyLlama can't generate JSON reliably)
- Chunk size: 800 characters (truncated)
- Parsing: Manual extraction with regex (`_extract_qa_manually()`)
- Validation: Lenient fallback (accepts invalid pairs)

**Problems:**
```python
# Current issues
- max_chunk_length = 800  # Too large for TinyLlama
- num_predict = 1500      # Still generates incomplete answers
- temperature = 0.7       # High for creativity but causes inconsistency
- Manual parsing: ~60% success rate
- Average pairs: 1.67/3 (55% of target)
```

**Metrics:**
- JSON parsing success: 0% (always fails, uses manual extraction)
- Pairs per chunk: 1.67 average
- Complete answers: ~70%
- Generation time: 5-10s (acceptable)

---

## Target Architecture

### Recommended Stack (from research)

**Model:** `mlx-community/Qwen2.5-3B-Instruct-4bit`
- Size: 3B parameters, ~3GB RAM (4-bit)
- Performance: 70-90 tokens/sec on M3/M4 Air
- Context: 128K tokens (massive upgrade from TinyLlama)
- JSON capability: Explicitly optimized for structured output
- Multilingual: Superior Polish/English support

**Structured Output:** `outlines` library with MLX backend
- Guaranteed 100% valid JSON (no manual extraction!)
- Pydantic schema enforcement
- Microsecond overhead per token
- Production-ready (used by LM Studio)

**Chunking:** LangChain RecursiveCharacterTextSplitter
- Optimal size: 512 characters (not 800!)
- Overlap: 100 characters (20%)
- Sentence boundary preservation

**Embeddings (optional):** `mlx-community/all-MiniLM-L6-v2-4bit`
- For semantic chunking (future enhancement)
- ~500MB memory

---

## Migration Phases

### Phase 1: Environment Setup (30 minutes)

**Dependencies:**
```bash
pip install mlx-lm outlines mlx-embeddings langchain-text-splitters pydantic
```

**Test MLX availability:**
```python
import mlx.core as mx
print(f"MLX Metal available: {mx.metal.is_available()}")
# Should output: True on Apple Silicon
```

**Model download:**
```python
from mlx_lm import load
model, tokenizer = load("mlx-community/Qwen2.5-3B-Instruct-4bit")
# Downloads ~3GB on first run
```

---

### Phase 2: New QAGenerator Implementation

**File:** `advanced_vault/gui/qa_generator_mlx.py` (new module)

**Key Changes:**

1. **Replace Ollama with MLX:**
```python
# OLD (Ollama)
response = requests.post(f"{ollama_url}/api/generate", json={...})

# NEW (MLX)
import outlines
from mlx_lm import load

model = outlines.models.mlxlm("mlx-community/Qwen2.5-3B-Instruct-4bit")
```

2. **Structured Output with Outlines:**
```python
from pydantic import BaseModel, Field
from typing import List

class AlpacaQA(BaseModel):
    instruction: str = Field(description="The question", min_length=10)
    input: str = Field(default="", description="Optional context")
    output: str = Field(description="The complete answer", min_length=50)

class ThreeQAPairs(BaseModel):
    qa_pairs: List[AlpacaQA] = Field(min_items=3, max_items=3)

# Create generator with schema enforcement
generator = outlines.generate.json(model, ThreeQAPairs)
```

3. **Optimal Chunking:**
```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,        # Changed from 800
    chunk_overlap=100,     # 20% overlap
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""]
)
```

4. **Eliminate Manual Parsing:**
```python
# OLD: Manual extraction with regex
qa_pairs = self._extract_qa_manually(response_text)  # ~60% success

# NEW: Guaranteed valid JSON
result = generator(prompt, max_tokens=800, temperature=0.7)
qa_pairs = result.qa_pairs  # Always valid, always 3 pairs!
```

---

### Phase 3: Integration Points

**Files to modify:**

1. **`qa_generator.py`:**
   - Add `_generate_qa_with_mlx()` method
   - Keep Ollama as fallback for non-Apple Silicon systems
   - Update `generate_qa_pairs()` to prefer MLX

2. **`pdf_processor.py`:**
   - Update chunking: 800 → 512 characters
   - Add sentence boundary preservation

3. **`vault_app.py`:**
   - Update `_setup_qa_model_with_progress()` for MLX model download
   - Update Settings UI to show MLX model status

**Backward Compatibility:**
- Keep Ollama fallback for Linux/Windows users
- Detect Apple Silicon: `platform.machine() == "arm64"`
- Auto-select MLX on Apple Silicon, Ollama elsewhere

---

### Phase 4: Prompt Engineering

**New prompt template (optimized for Qwen2.5):**

```python
def create_qa_prompt(chunk: str, language: str = "auto") -> str:
    lang_instruction = ""
    if language == "auto":
        lang_instruction = "Generate in the SAME LANGUAGE as the source text."
    
    return f"""Generate exactly 3 high-quality question-answer pairs from this text.

REQUIREMENTS:
1. Questions must be clear, specific, and directly answerable from the text
2. Answers must be complete sentences (minimum 50 characters)
3. Cover 3 different aspects or concepts from the text
4. {lang_instruction}

Text: {chunk}

Generate 3 diverse Q&A pairs now:"""
```

**Why different from TinyLlama prompt:**
- Qwen2.5 understands JSON schema (from Outlines)
- No need for Q:/A: format instructions
- Can be more concise (model is smarter)

---

### Phase 5: Performance Validation

**Benchmarks to verify:**

| Metric | TinyLlama (Current) | Qwen2.5-3B (Target) | Status |
|--------|---------------------|---------------------|--------|
| JSON success rate | 0% (manual only) | 100% (Outlines) | ✅ Target |
| Pairs per chunk | 1.67 avg | 3.0 (guaranteed) | ✅ Target |
| Complete answers | ~70% | ~95%+ | ✅ Target |
| Generation time | 5-10s | 5-8s | ✅ Maintain |
| Memory usage | ~1GB | ~3GB | ⚠️ Acceptable |
| Chunk size | 800 chars | 512 chars | ✅ Optimal |

**Test scenarios:**
1. Polish document (check language preservation)
2. English document (check quality)
3. Mixed language (check handling)
4. Long document (check chunking)
5. Technical content (check comprehension)

---

## Implementation Code Structure

### New Class: `MLXQAGenerator`

```python
# advanced_vault/gui/qa_generator_mlx.py

import mlx.core as mx
import outlines
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)

class AlpacaQA(BaseModel):
    instruction: str = Field(description="The question", min_length=10)
    input: str = Field(default="", description="Optional context")
    output: str = Field(description="The complete answer", min_length=50)

class ThreeQAPairs(BaseModel):
    qa_pairs: List[AlpacaQA] = Field(min_items=3, max_items=3)

class MLXQAGenerator:
    """
    MLX-optimized Q&A generator with guaranteed JSON output.
    
    Uses Qwen2.5-3B-Instruct-4bit with Outlines structured generation.
    """
    
    def __init__(self, model_path: str = "mlx-community/Qwen2.5-3B-Instruct-4bit"):
        """
        Initialize MLX Q&A generator.
        
        Args:
            model_path: HuggingFace model path or local path
        """
        if not mx.metal.is_available():
            raise RuntimeError("MLX requires Apple Silicon (Metal GPU)")
        
        logger.info(f"Loading MLX model: {model_path}")
        self.model = outlines.models.mlxlm(model_path)
        self.generator = outlines.generate.json(self.model, ThreeQAPairs)
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        logger.info("MLX Q&A generator initialized")
    
    def chunk_document(self, text: str) -> List[str]:
        """Split document into optimal chunks."""
        chunks = self.text_splitter.split_text(text)
        return [self._clean_chunk(c) for c in chunks]
    
    def _clean_chunk(self, chunk: str) -> str:
        """Ensure chunk ends at sentence boundary."""
        if not chunk.endswith(('.', '!', '?', '"', "'")):
            for sep in ['. ', '! ', '? ']:
                pos = chunk.rfind(sep)
                if pos > len(chunk) * 0.7:
                    return chunk[:pos+1]
        return chunk
    
    def generate_qa_pairs(self, chunk: str, language: str = "auto") -> List[dict]:
        """
        Generate exactly 3 Q&A pairs from chunk.
        
        Args:
            chunk: Text chunk (512 chars optimal)
            language: "auto", "pl", "en" (auto detects)
            
        Returns:
            List of 3 Q&A pairs in Alpaca format
        """
        lang_instruction = ""
        if language == "auto":
            lang_instruction = "Generate in the SAME LANGUAGE as the source text."
        
        prompt = f"""Generate exactly 3 high-quality question-answer pairs from this text.

REQUIREMENTS:
1. Questions must be clear, specific, and directly answerable from the text
2. Answers must be complete sentences (minimum 50 characters)
3. Cover 3 different aspects or concepts from the text
4. {lang_instruction}

Text: {chunk}

Generate 3 diverse Q&A pairs now:"""
        
        try:
            result = self.generator(
                prompt,
                max_tokens=800,
                temperature=0.7
            )
            
            # Convert Pydantic models to dicts
            qa_pairs = []
            for qa in result.qa_pairs:
                qa_pairs.append({
                    "instruction": qa.instruction,
                    "input": qa.input,
                    "output": qa.output
                })
            
            logger.info(f"Generated {len(qa_pairs)} Q&A pairs (guaranteed 3)")
            return qa_pairs
            
        except Exception as e:
            logger.error(f"MLX Q&A generation failed: {e}")
            return []
    
    def is_available(self) -> bool:
        """Check if MLX is available."""
        return mx.metal.is_available()
```

---

## Integration with Existing Code

### Update `qa_generator.py`:

```python
# Add MLX support alongside Ollama

class QAGenerator:
    def __init__(self, ...):
        # ... existing code ...
        
        # Try to initialize MLX (Apple Silicon only)
        self.mlx_generator = None
        if self._is_apple_silicon():
            try:
                import mlx.core as mx
                if mx.metal.is_available():
                    from qa_generator_mlx import MLXQAGenerator
                    self.mlx_generator = MLXQAGenerator()
                    logger.info("MLX Q&A generator available")
            except ImportError:
                logger.debug("MLX not available, using Ollama fallback")
    
    def _is_apple_silicon(self) -> bool:
        """Check if running on Apple Silicon."""
        import platform
        return platform.machine() == "arm64"
    
    def generate_qa_pairs(self, text_chunk: str, num_pairs: int = 3):
        """Generate Q&A pairs with MLX priority, Ollama fallback."""
        
        # Try MLX first (Apple Silicon)
        if self.mlx_generator and self.mlx_generator.is_available():
            try:
                qa_pairs = self.mlx_generator.generate_qa_pairs(text_chunk)
                if qa_pairs and len(qa_pairs) == 3:
                    logger.info(f"MLX generated {len(qa_pairs)} Q&A pairs")
                    return qa_pairs
            except Exception as e:
                logger.debug(f"MLX generation failed: {e}, falling back to Ollama")
        
        # Fallback to Ollama (existing code)
        return self._generate_qa_with_ollama(text_chunk, num_pairs)
```

---

## Migration Checklist

### Pre-Migration

- [ ] Verify Apple Silicon hardware: `sysctl -n machdep.cpu.brand_string`
- [ ] Check available RAM: Need 16GB+ for Qwen2.5-3B (4-bit)
- [ ] Install MLX dependencies: `pip install mlx-lm outlines`
- [ ] Test MLX availability: `python -c "import mlx.core as mx; print(mx.metal.is_available())"`

### Phase 1: Setup (Week 1)

- [ ] Create `qa_generator_mlx.py` module
- [ ] Implement `MLXQAGenerator` class
- [ ] Test model loading: `load("mlx-community/Qwen2.5-3B-Instruct-4bit")`
- [ ] Verify structured output: Test Outlines JSON generation
- [ ] Update chunking: Change 800 → 512 chars in `pdf_processor.py`

### Phase 2: Integration (Week 1-2)

- [ ] Integrate MLXQAGenerator into `qa_generator.py`
- [ ] Add Apple Silicon detection
- [ ] Keep Ollama fallback for non-Apple Silicon
- [ ] Update `setup_qa_model()` for MLX model download
- [ ] Update Settings UI to show MLX status

### Phase 3: Testing (Week 2)

- [ ] Test with Polish documents
- [ ] Test with English documents
- [ ] Test with mixed-language documents
- [ ] Benchmark generation time (target: 5-8s per chunk)
- [ ] Verify 3 Q&A pairs per chunk (guaranteed)
- [ ] Validate JSON output (should be 100%)

### Phase 4: Production (Week 3)

- [ ] Remove manual extraction code (no longer needed!)
- [ ] Update error handling
- [ ] Add logging for MLX vs Ollama usage
- [ ] Update documentation
- [ ] Deploy to users

---

## Performance Expectations

### Before (TinyLlama):

```
Chunk size: 800 chars
Generation: 5-10s
Pairs: 1.67 avg (50% success)
JSON: 0% (always manual extraction)
Complete answers: ~70%
Memory: ~1GB
```

### After (Qwen2.5-3B + Outlines):

```
Chunk size: 512 chars (optimal)
Generation: 5-8s (faster due to better model)
Pairs: 3.0 (100% guaranteed)
JSON: 100% (Outlines enforcement)
Complete answers: ~95%+
Memory: ~3GB (acceptable for 16GB systems)
```

**Improvements:**
- ✅ **80% more pairs** (1.67 → 3.0)
- ✅ **100% JSON success** (0% → 100%)
- ✅ **35% better completeness** (70% → 95%+)
- ✅ **Better chunking** (512 optimal vs 800 too large)

---

## Rollback Plan

If MLX migration causes issues:

1. **Immediate:** Set `USE_MLX = False` env var → falls back to Ollama
2. **Code:** Keep both implementations (MLX + Ollama) active
3. **Detection:** Auto-detect Apple Silicon, use Ollama on other platforms
4. **User choice:** Add Settings toggle "Use MLX (Apple Silicon only)"

---

## Future Enhancements

### Phase 6: Semantic Chunking (Optional)

```python
# Use MLX embeddings for better chunking
from mlx_embeddings.utils import load

emb_model, tokenizer = load("mlx-community/all-MiniLM-L6-v2-4bit")

# Semantic chunking based on similarity
chunks = semantic_chunk(text, target_size=512, similarity_threshold=0.8)
```

### Phase 7: Quality Scoring

```python
# Add quality metrics per Q&A pair
def score_qa_pair(qa_pair, original_chunk):
    """Score Q&A pair quality."""
    scores = {
        "relevance": cosine_similarity(qa_pair.instruction, chunk),
        "completeness": len(qa_pair.output) / expected_length,
        "diversity": uniqueness_score(qa_pair, other_pairs)
    }
    return scores
```

---

## References

### Research Sources

1. **Qwen2.5 Official Blog** (September 2024): "Reliable generation of structured outputs, particularly in JSON format"
2. **Outlines Documentation**: Official MLX backend support
3. **MLX Performance Benchmarks**: M2-M4 Air token/sec measurements
4. **LangChain Text Splitters**: Optimal chunking strategies

### Libraries

- `mlx-lm`: Apple Silicon optimized LLM inference
- `outlines`: Structured output generation (production-ready)
- `langchain-text-splitters`: Optimal chunking
- `mlx-embeddings`: Semantic chunking (optional)

### Model Links

- Qwen2.5-3B-Instruct-4bit: `mlx-community/Qwen2.5-3B-Instruct-4bit`
- Alternative: `mlx-community/Llama-3.2-3B-Instruct-4bit` (fallback)

---

## Decision Points

### When to Migrate?

**✅ Migrate NOW if:**
- You have Apple Silicon hardware (M2-M4)
- You have 16GB+ RAM
- Q&A quality is blocking feature development
- Users report poor Q&A generation

**⏸️ Wait if:**
- Supporting Linux/Windows users (keep Ollama)
- RAM constrained (<16GB)
- Current solution "good enough" for MVP

### Model Choice

**Qwen2.5-3B-Instruct-4bit** (recommended):
- ✅ Best JSON output (explicitly optimized)
- ✅ Best multilingual support
- ✅ Optimal for 16GB RAM
- ✅ 70-90 tokens/sec

**Llama-3.2-3B-Instruct-4bit** (fallback):
- ✅ More community support
- ✅ Battle-tested
- ⚠️ Slightly worse JSON
- ✅ Still good choice

---

**Status:** 📋 Ready for implementation  
**Estimated Effort:** 2-3 weeks  
**Priority:** High (solves critical Q&A quality issues)  
**Risk:** Low (fallback to Ollama available)

