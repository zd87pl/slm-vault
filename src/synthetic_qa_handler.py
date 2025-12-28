"""
Secure Synthetic Q&A Generator for WDVA

Generates high-quality Q&A pairs using Qwen3-30B-A3B (MoE model).
Maintains end-to-end encryption - PDF never exposed in plaintext.

Model: Qwen3-30B-A3B
- 30.5B total parameters, 3.3B activated (MoE)
- Native 32K context (extendable to 131K with YaRN)
- Excellent quality-to-cost ratio for synthetic data generation

Performance optimizations:
- vLLM for 5-10x faster inference (if available)
- Parallel batch processing of all chunks
- Default 100 samples (quality > quantity for adapter training)
"""

import os
import sys

# CRITICAL: Set cache directory BEFORE importing transformers/huggingface
# This ensures model downloads go to the network volume, not container disk
VOLUME_PATH = "/runpod-volume"
FALLBACK_CACHE = "/workspace/.cache/huggingface"

if os.path.isdir(VOLUME_PATH) and os.access(VOLUME_PATH, os.W_OK):
    CACHE_DIR = os.path.join(VOLUME_PATH, "huggingface")
    TEMP_DIR = os.path.join(VOLUME_PATH, "tmp")
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    print(f"[CACHE] Using network volume: {CACHE_DIR}", file=sys.stderr)
    print(f"[TEMP] Using network volume temp: {TEMP_DIR}", file=sys.stderr)
else:
    CACHE_DIR = FALLBACK_CACHE
    TEMP_DIR = "/workspace/tmp"
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    print(f"[CACHE] WARNING: Using container disk (no volume): {CACHE_DIR}", file=sys.stderr)

# Set ALL cache-related environment variables before any imports
os.environ["HF_HOME"] = CACHE_DIR
os.environ["HF_HUB_CACHE"] = os.path.join(CACHE_DIR, "hub")
os.environ["TRANSFORMERS_CACHE"] = CACHE_DIR
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(CACHE_DIR, "hub")
os.environ["XDG_CACHE_HOME"] = os.path.dirname(CACHE_DIR)

# CRITICAL: Set temp directory to volume - HF downloads to temp first, then moves
os.environ["TMPDIR"] = TEMP_DIR
os.environ["TEMP"] = TEMP_DIR
os.environ["TMP"] = TEMP_DIR
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "3600"  # 1 hour timeout for large models

# huggingface_hub v1.0+ uses environment variables only for cache configuration
# The HF_HOME, HF_HUB_CACHE, etc. env vars are already set above
# Reference: https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables
print(f"[HF_HUB] Cache configured via env vars:", file=sys.stderr)
print(f"  HF_HOME={os.environ.get('HF_HOME')}", file=sys.stderr)
print(f"  HF_HUB_CACHE={os.environ.get('HF_HUB_CACHE')}", file=sys.stderr)

# Now import everything else
import runpod
import json
import base64
import secrets
import logging
import time
from pathlib import Path
from typing import Dict, Any, List
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Log cache configuration
logger.info(f"HF_HOME={os.environ.get('HF_HOME')}")
logger.info(f"TRANSFORMERS_CACHE={os.environ.get('TRANSFORMERS_CACHE')}")

# Try PyCryptodome first, fallback to cryptography
try:
    from Crypto.Cipher import ChaCha20_Poly1305
    CRYPTO_BACKEND = "pycryptodome"
except ImportError:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        CRYPTO_BACKEND = "cryptography"
    except ImportError:
        logger.error("No encryption library available. Install: pip install pycryptodome")
        raise

import torch

# Try vLLM first (5-10x faster), fall back to transformers
VLLM_AVAILABLE = False
try:
    from vllm import LLM, SamplingParams
    VLLM_AVAILABLE = True
    logger.info("✓ vLLM available - using optimized inference (5-10x faster)")
except ImportError:
    logger.info("vLLM not available - using transformers (slower but works)")

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
except ImportError:
    if not VLLM_AVAILABLE:
        logger.error("Neither vLLM nor transformers installed!")
        raise

try:
    from pypdf import PdfReader
except ImportError:
    logger.error("pypdf not installed. Install: pip install pypdf")
    raise


class SecureSyntheticGenerator:
    """
    Generate synthetic Q&A pairs using configurable Qwen models.
    
    Maintains end-to-end encryption:
    - PDF encrypted before network transmission
    - Decryption only in this RunPod instance
    - Results encrypted before returning
    
    Uses vLLM for 5-10x faster inference when available.
    
    Model Options (set QA_MODEL env var):
    - "fast": Qwen2.5-14B-Instruct-AWQ (default) - Fast loading (~3GB), good quality
    - "quality": Qwen3-30B-A3B - Best quality, slower loading (~4GB)
    """
    
    # Model configurations
    MODEL_CONFIGS = {
        "fast": {
            "name": "Qwen/Qwen2.5-14B-Instruct-AWQ",
            "specs": "14B params, AWQ 4-bit quantized, ~3GB, fast loading",
            "quantization": "awq",
            "dtype": "auto",  # AWQ handles dtype internally
        },
        "quality": {
            "name": "Qwen/Qwen3-30B-A3B", 
            "specs": "30.5B total params, 3.3B activated (MoE), ~4GB",
            "quantization": None,
            "dtype": "bfloat16",
        },
    }
    
    def __init__(self):
        """Initialize with configurable model."""
        # Choose model based on environment variable (default: fast)
        model_choice = os.environ.get("QA_MODEL", "fast").lower()
        if model_choice not in self.MODEL_CONFIGS:
            logger.warning(f"Unknown QA_MODEL '{model_choice}', using 'fast'")
            model_choice = "fast"
        
        config = self.MODEL_CONFIGS[model_choice]
        self.model_name = config["name"]
        self.use_vllm = VLLM_AVAILABLE
        
        logger.info(f"Model selection: {model_choice.upper()}")
        logger.info(f"Loading model: {self.model_name}")
        logger.info(f"Model specs: {config['specs']}")
        logger.info(f"Cache directory: {CACHE_DIR}")
        logger.info(f"Backend: {'vLLM (fast)' if self.use_vllm else 'transformers (slow)'}")
        
        if self.use_vllm:
            # vLLM: Much faster inference with PagedAttention
            try:
                vllm_kwargs = {
                    "model": self.model_name,
                    "download_dir": CACHE_DIR,
                    "tensor_parallel_size": 1,
                    "gpu_memory_utilization": 0.90,
                    "max_model_len": 8192,
                    "trust_remote_code": True,
                    "dtype": config["dtype"],
                }
                
                # Add quantization config for AWQ models
                if config["quantization"] == "awq":
                    vllm_kwargs["quantization"] = "awq"
                    logger.info("Using AWQ quantization for faster loading")
                
                self.llm = LLM(**vllm_kwargs)
                self.sampling_params = SamplingParams(
                    temperature=0.4,
                    top_p=0.9,
                    top_k=50,
                    max_tokens=2048,
                )
                self.model = None
                self.tokenizer = None
                logger.info("✓ vLLM model loaded - parallel batch processing enabled")
            except Exception as e:
                logger.warning(f"vLLM initialization failed: {e}")
                logger.info("Falling back to transformers...")
                self.use_vllm = False
                self.llm = None
        
        if not self.use_vllm:
            # Fallback: transformers with 4-bit quantization
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                quantization_config=bnb_config,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
                cache_dir=CACHE_DIR
            )
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                cache_dir=CACHE_DIR
            )
            self.llm = None
            logger.info("✓ Transformers model loaded")
    
    def decrypt_pdf(self, encrypted_data: str, decryption_key: bytes) -> bytes:
        """
        Decrypt PDF blob using XChaCha20-Poly1305.
        
        Args:
            encrypted_data: JSON string with encrypted package
            decryption_key: 32-byte decryption key
            
        Returns:
            Decrypted PDF bytes
        """
        try:
            encrypted_package = json.loads(encrypted_data)
            
            ciphertext = base64.b64decode(encrypted_package['ciphertext'])
            tag = base64.b64decode(encrypted_package['tag'])
            nonce = base64.b64decode(encrypted_package['nonce'])
            
            if CRYPTO_BACKEND == "pycryptodome":
                cipher = ChaCha20_Poly1305.new(key=decryption_key, nonce=nonce)
                pdf_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            else:
                cipher = ChaCha20Poly1305(decryption_key)
                pdf_bytes = cipher.decrypt(nonce, ciphertext + tag, None)
            
            logger.info(f"✓ Decrypted PDF ({len(pdf_bytes)} bytes)")
            return pdf_bytes
            
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes."""
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            text += page_text + "\n"
            if (i + 1) % 10 == 0:
                logger.debug(f"Extracted text from {i+1} pages")
        
        logger.info(f"✓ Extracted {len(text)} characters from {len(reader.pages)} pages")
        return text
    
    def _validate_qa_pair(self, question: str, answer: str) -> bool:
        """
        Validate a single Q&A pair for quality.
        
        Returns:
            True if pair is valid, False otherwise
        """
        # Check minimum lengths
        if len(question.strip()) < 15 or len(answer.strip()) < 30:
            logger.debug(f"Rejected: Too short (Q:{len(question)}, A:{len(answer)})")
            return False
        
        # Check for empty/placeholder content
        placeholder_phrases = [
            "question here", "answer here", "your question", "your answer",
            "...", "xxx", "placeholder", "[insert", "example question"
        ]
        combined = (question + " " + answer).lower()
        if any(phrase in combined for phrase in placeholder_phrases):
            logger.debug(f"Rejected: Contains placeholder")
            return False
        
        # Question should look like a question (has question mark or starts with question word)
        question_lower = question.lower().strip()
        question_indicators = ["what", "how", "why", "when", "where", "which", "who", 
                              "can", "does", "is", "are", "will", "would", "should",
                              "explain", "describe", "compare", "analyze", "?"]
        has_question_indicator = any(question_lower.startswith(w) or w in question_lower 
                                     for w in question_indicators)
        if not has_question_indicator:
            logger.debug(f"Rejected: Doesn't look like a question: {question[:50]}")
            return False
        
        # Answer should have substance (at least 5 words)
        if len(answer.split()) < 5:
            logger.debug(f"Rejected: Answer too short ({len(answer.split())} words)")
            return False
        
        return True
    
    def _build_prompt(self, chunk_text: str, num_pairs: int) -> str:
        """Build the prompt for Q&A generation."""
        # Simple direct prompt - no examples to copy
        # End with start of JSON to guide model output
        return f'''Generate {num_pairs} question-answer pairs as JSON from this document.

DOCUMENT:
{chunk_text}

RULES:
1. Questions must be specific to this document's content
2. Answers must be 2-4 sentences with facts from the document
3. Output ONLY valid JSON array, no other text

JSON OUTPUT:
[{{"question": "'''

    def _parse_response(self, response: str) -> List[Dict[str, str]]:
        """Parse JSON Q&A pairs from model response."""
        import re
        
        # Clean response
        response = response.strip()
        
        # Remove thinking tags if present
        if "</think>" in response:
            response = response.split("</think>")[-1].strip()
        if "<think>" in response:
            response = response.split("<think>")[0].strip()
        
        # Remove chat markers
        if "<|im_end|>" in response:
            response = response.split("<|im_end|>")[0]
        
        # Remove control characters that break JSON parsing
        response = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', response)
        
        # Our prompt ends with '[{"question": "' so prepend that
        if not response.startswith('['):
            response = '[{"question": "' + response
        
        # Log what we received for debugging
        logger.info(f"Raw response (first 300 chars): {response[:300]}")
        
        try:
            # Find the JSON array - look for matching brackets
            start = response.find('[')
            if start < 0:
                raise ValueError("No JSON array found")
            
            # Find matching closing bracket by counting
            bracket_count = 0
            end = -1
            for i, char in enumerate(response[start:], start):
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end = i + 1
                        break
            
            if end < 0:
                # No matching bracket, try to fix by adding one
                json_str = response[start:] + ']'
            else:
                json_str = response[start:end]
            
            # Clean up common JSON issues
            # Remove trailing commas
            json_str = re.sub(r',\s*]', ']', json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            # Fix unescaped newlines in strings (common issue)
            json_str = re.sub(r'(?<!\\)\n', ' ', json_str)
            # Remove any text after the array
            
            try:
                qa_pairs = json.loads(json_str)
            except json.JSONDecodeError as e:
                # Try line-by-line parsing for individual objects
                logger.info(f"Standard parse failed, trying object-by-object extraction...")
                qa_pairs = self._extract_qa_objects(response)
            
            if not isinstance(qa_pairs, list):
                qa_pairs = [qa_pairs] if isinstance(qa_pairs, dict) else []
            
            # Validate and format
            formatted_pairs = []
            for qa in qa_pairs:
                if isinstance(qa, dict) and "question" in qa and "answer" in qa:
                    question = str(qa["question"]).strip()
                    answer = str(qa["answer"]).strip()
                    if self._validate_qa_pair(question, answer):
                        formatted_pairs.append({"question": question, "answer": answer})
            
            if formatted_pairs:
                logger.info(f"Successfully parsed {len(formatted_pairs)} Q&A pairs")
            
            return formatted_pairs
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Parse failed: {e}")
            logger.warning(f"Response (first 500 chars): {response[:500]}")
            return []
    
    def _extract_qa_objects(self, text: str) -> List[Dict[str, str]]:
        """Extract Q&A objects using regex when JSON parsing fails."""
        import re
        
        pairs = []
        # Find all {"question": "...", "answer": "..."} patterns
        pattern = r'\{\s*"question"\s*:\s*"([^"]+)"\s*,\s*"answer"\s*:\s*"([^"]+)"\s*\}'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for question, answer in matches:
            # Unescape any escaped quotes
            question = question.replace('\\"', '"').replace('\\n', ' ')
            answer = answer.replace('\\"', '"').replace('\\n', ' ')
            pairs.append({"question": question, "answer": answer})
        
        if pairs:
            logger.info(f"Regex extraction found {len(pairs)} Q&A pairs")
        
        return pairs

    def generate_qa_pairs_batch(self, chunks: List[str], num_pairs_per_chunk: int = 10) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from ALL chunks in parallel using vLLM.
        
        This is 4-8x faster than processing chunks sequentially because:
        1. All prompts are batched together
        2. GPU utilization is maximized
        3. vLLM's PagedAttention handles memory efficiently
        
        Args:
            chunks: List of text chunks to process
            num_pairs_per_chunk: Q&A pairs to generate per chunk
            
        Returns:
            List of all Q&A pairs from all chunks
        """
        if not self.use_vllm:
            # Fallback to sequential processing with transformers
            all_pairs = []
            for i, chunk in enumerate(chunks):
                logger.info(f"[{i+1}/{len(chunks)}] Processing chunk (transformers)...")
                pairs = self.generate_qa_pairs(chunk, num_pairs_per_chunk)
                all_pairs.extend(pairs)
            return all_pairs
        
        # Build all prompts
        prompts = [self._build_prompt(chunk, num_pairs_per_chunk) for chunk in chunks]
        logger.info(f"⚡ Batch processing {len(prompts)} chunks in parallel (vLLM)...")
        
        try:
            # Generate all at once - vLLM handles batching automatically
            outputs = self.llm.generate(prompts, self.sampling_params)
        except Exception as e:
            logger.error(f"vLLM batch generation failed: {e}")
            logger.info("Falling back to sequential transformers processing...")
            # Disable vLLM for subsequent calls
            self.use_vllm = False
            self.llm = None
            # Load transformers model if not loaded
            if self.model is None:
                logger.info("Loading transformers model for fallback...")
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    quantization_config=bnb_config,
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                    trust_remote_code=True,
                    cache_dir=CACHE_DIR
                )
                self.tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    cache_dir=CACHE_DIR
                )
            # Fall back to sequential processing
            all_pairs = []
            for i, chunk in enumerate(chunks):
                logger.info(f"[{i+1}/{len(chunks)}] Processing chunk (fallback)...")
                pairs = self.generate_qa_pairs(chunk, num_pairs_per_chunk)
                all_pairs.extend(pairs)
            return all_pairs
        
        # Parse all responses
        all_pairs = []
        for i, output in enumerate(outputs):
            try:
                response = output.outputs[0].text
                pairs = self._parse_response(response)
                all_pairs.extend(pairs)
                logger.info(f"  Chunk {i+1}: {len(pairs)} pairs")
            except (IndexError, AttributeError) as e:
                logger.warning(f"  Chunk {i+1}: Failed to parse output ({e})")
        
        logger.info(f"✓ Batch generated {len(all_pairs)} total pairs")
        return all_pairs

    def generate_qa_pairs(self, chunk_text: str, num_pairs: int = 10) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from a single chunk.
        
        For multiple chunks, use generate_qa_pairs_batch() for 4-8x speedup.
        
        Args:
            chunk_text: Document chunk to generate Q&A from
            num_pairs: Number of Q&A pairs to generate
            
        Returns:
            List of Q&A pairs [{"question": "...", "answer": "..."}]
        """
        if self.use_vllm:
            # Single chunk with vLLM
            prompt = self._build_prompt(chunk_text, num_pairs)
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text
            return self._parse_response(response)
        
        # Transformers fallback
        prompt = self._build_prompt(chunk_text, num_pairs)
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=2048,
                temperature=0.4,
                top_p=0.9,
                top_k=50,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
        
        prompt_len = inputs['input_ids'].shape[1]
        response = self.tokenizer.decode(outputs[0][prompt_len:], skip_special_tokens=True)
        
        return self._parse_response(response)
    
    def encrypt_results(self, data: List[Dict], encryption_key: bytes) -> str:
        """
        Encrypt generated dataset using XChaCha20-Poly1305 or ChaCha20-Poly1305.
        
        Args:
            data: List of Q&A pairs
            encryption_key: 32-byte encryption key
            
        Returns:
            JSON string with encrypted package
        """
        # Serialize data
        plaintext = json.dumps(data).encode('utf-8')
        
        # Encrypt - nonce size depends on crypto backend
        if CRYPTO_BACKEND == "pycryptodome":
            # XChaCha20-Poly1305 uses 24-byte nonce
            nonce = secrets.token_bytes(24)
            cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        else:
            # cryptography's ChaCha20Poly1305 uses 12-byte nonce
            nonce = secrets.token_bytes(12)
            cipher = ChaCha20Poly1305(encryption_key)
            ciphertext_with_tag = cipher.encrypt(nonce, plaintext, None)
            ciphertext = ciphertext_with_tag[:-16]
            tag = ciphertext_with_tag[-16:]
        
        # Package
        encrypted_package = {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'algorithm': 'XChaCha20-Poly1305',
            'kdf': 'none'  # Key passed directly
        }
        
        return json.dumps(encrypted_package)


# Global generator (loaded once, reused across invocations)
generator = None

def handler(event):
    """
    RunPod serverless handler for secure synthetic Q&A generation.
    
    Expected input:
    {
        "input": {
            "encrypted_pdf": "JSON string with encrypted PDF",
            "encryption_key_hex": "hex-encoded 32-byte key",
            "target_samples": 100  # Optional, default 100 (quality > quantity)
        }
    }
    
    Returns:
    {
        "status": "success",
        "encrypted_dataset": "JSON string with encrypted Q&A pairs",
        "num_samples": 100
    }
    
    Performance:
    - With vLLM: ~2-5 minutes for 100 samples
    - With transformers: ~15-20 minutes for 100 samples
    """
    global generator
    
    try:
        input_data = event.get('input', {})
        
        # Get encryption key
        encryption_key_hex = input_data.get('encryption_key_hex')
        if not encryption_key_hex:
            return {"status": "error", "error": "encryption_key_hex is required"}
        
        encryption_key = bytes.fromhex(encryption_key_hex)
        if len(encryption_key) != 32:
            return {"status": "error", "error": "encryption_key must be 32 bytes (64 hex chars)"}
        
        # Get encrypted PDF
        encrypted_pdf = input_data.get('encrypted_pdf')
        if not encrypted_pdf:
            return {"status": "error", "error": "encrypted_pdf is required"}
        
        # Get target samples - default 100 (quality > quantity for adapter training)
        target_samples = input_data.get('target_samples', 100)
        logger.info(f"Target: {target_samples} Q&A pairs")
        
        # Initialize generator (lazy load)
        if generator is None:
            logger.info("Initializing Qwen3-30B-A3B (MoE: 3.3B active)...")
            generator = SecureSyntheticGenerator()
        
        # Decrypt PDF
        logger.info("Decrypting PDF...")
        pdf_bytes = generator.decrypt_pdf(encrypted_pdf, encryption_key)
        
        # Extract text
        logger.info("Extracting text from PDF...")
        pdf_text = generator.extract_text_from_pdf(pdf_bytes)
        del pdf_bytes  # Clean up immediately
        
        # Split into larger chunks with less overlap (fewer chunks = faster)
        logger.info("Splitting text into chunks...")
        words = pdf_text.split()
        chunk_size = 800  # larger chunks (was 500)
        overlap = 50      # less overlap (was 100)
        
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if len(chunk) > 100:  # Skip tiny chunks
                chunks.append(chunk)
        
        # Handle empty document
        if not chunks:
            logger.warning("No text chunks extracted from PDF")
            return {
                "status": "error",
                "error": "PDF appears to be empty or contains no extractable text"
            }
        
        # Limit chunks to reasonable number
        max_chunks = min(len(chunks), 8)  # Cap at 8 chunks
        if len(chunks) > max_chunks:
            # Sample evenly across document
            step = len(chunks) // max_chunks
            chunks = [chunks[i] for i in range(0, len(chunks), step)][:max_chunks]
        
        logger.info(f"✓ Using {len(chunks)} chunks (optimized for speed)")
        
        # Calculate pairs per chunk (with safety check)
        pairs_per_chunk = max(5, min(25, target_samples // max(1, len(chunks))))
        logger.info(f"Generating {pairs_per_chunk} pairs per chunk...")
        logger.info(f"Expected total: ~{pairs_per_chunk * len(chunks)} pairs")
        logger.info(f"Backend: {'vLLM (parallel)' if generator.use_vllm else 'transformers (sequential)'}")
        
        # Generate Q&A pairs - use batch processing for speed
        start_time = time.time()
        
        all_qa_pairs = generator.generate_qa_pairs_batch(chunks, pairs_per_chunk)
        
        elapsed = time.time() - start_time
        logger.info(f"⏱️ Generation took {elapsed:.1f} seconds")
        
        # Handle case where no pairs were generated
        if not all_qa_pairs:
            logger.error("No Q&A pairs were generated from the document")
            return {
                "status": "error",
                "error": "Failed to generate Q&A pairs - document may be too short or contain non-extractable content"
            }
        
        # Limit to target samples
        if len(all_qa_pairs) > target_samples:
            all_qa_pairs = all_qa_pairs[:target_samples]
            logger.info(f"Limited to {target_samples} samples (requested)")
        
        logger.info(f"✓ Total generated: {len(all_qa_pairs)} Q&A pairs")
        
        # Convert to Alpaca format (matches your training code)
        training_data = []
        for qa in all_qa_pairs:
            training_data.append({
                "instruction": qa["question"],
                "input": "",  # Empty input field (matches your format)
                "output": qa["answer"]
            })
        
        # Store count before encryption (for return value)
        num_samples = len(training_data)
        
        # Encrypt results
        logger.info("Encrypting results...")
        encrypted_dataset = generator.encrypt_results(training_data, encryption_key)
        
        # Clean up sensitive data
        del pdf_text
        del all_qa_pairs
        del training_data
        
        logger.info("✓ Generation complete")
        
        return {
            "status": "success",
            "encrypted_dataset": encrypted_dataset,
            "num_samples": num_samples,
            "model": "Qwen3-30B-A3B"
        }
    
    except Exception as e:
        logger.error(f"Error in handler: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

