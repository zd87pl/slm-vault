"""
Secure Synthetic Q&A Generator for WDVA

Generates 1,000+ Q&A pairs using Qwen3-30B-A3B (MoE model).
Maintains end-to-end encryption - PDF never exposed in plaintext.

Model: Qwen3-30B-A3B
- 30.5B total parameters, 3.3B activated (MoE)
- Native 32K context (extendable to 131K with YaRN)
- Excellent quality-to-cost ratio for synthetic data generation
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

# CRITICAL: Override huggingface_hub constants BEFORE importing transformers
# This is necessary because the library caches these at import time
import huggingface_hub
huggingface_hub.constants.HF_HUB_CACHE = os.path.join(CACHE_DIR, "hub")
huggingface_hub.constants.HUGGINGFACE_HUB_CACHE = os.path.join(CACHE_DIR, "hub")
# Also patch the default cache path function
huggingface_hub.constants.default_cache_path = lambda: CACHE_DIR
print(f"[HF_HUB] Cache overridden to: {huggingface_hub.constants.HF_HUB_CACHE}", file=sys.stderr)

# Now import everything else
import runpod
import json
import base64
import secrets
import logging
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

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    import torch
except ImportError:
    logger.error("transformers not installed. Install: pip install transformers torch")
    raise

try:
    from pypdf import PdfReader
except ImportError:
    logger.error("pypdf not installed. Install: pip install pypdf")
    raise


class SecureSyntheticGenerator:
    """
    Generate synthetic Q&A pairs using Qwen3-30B-A3B.
    
    Maintains end-to-end encryption:
    - PDF encrypted before network transmission
    - Decryption only in this RunPod instance
    - Results encrypted before returning
    """
    
    def __init__(self):
        """Initialize with Qwen3-30B-A3B model."""
        self.model_name = "Qwen/Qwen3-30B-A3B"
        
        logger.info(f"Loading model: {self.model_name}")
        logger.info("Model specs: 30.5B total params, 3.3B activated (MoE), 32K-131K context")
        logger.info(f"Cache directory: {CACHE_DIR}")
        
        # Load model with 4-bit quantization for efficiency
        # MoE models are more efficient than dense models
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )
        
        # CRITICAL: Pass cache_dir explicitly to ensure volume is used
        # Environment variables alone are not reliable
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
        
        logger.info("✓ Model loaded successfully")
    
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
    
    def generate_qa_pairs(self, chunk_text: str, num_pairs: int = 20) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs using Qwen3-30B-A3B.
        
        Args:
            chunk_text: Document chunk to generate Q&A from
            num_pairs: Number of Q&A pairs to generate
            
        Returns:
            List of Q&A pairs [{"question": "...", "answer": "..."}]
        """
        # Format prompt for Qwen3 chat template
        # Qwen3 supports "thinking mode" - we use /no_think for faster, direct output
        messages = [
            {
                "role": "system",
                "content": """You are an expert at creating high-quality training data for fine-tuning language models. 
You MUST output ONLY a valid JSON array - no explanations, no markdown, no additional text.
Each Q&A pair should be comprehensive and directly grounded in the source document."""
            },
            {
                "role": "user",
                "content": f"""/no_think
Generate exactly {num_pairs} question-answer pairs from this document.

DOCUMENT:
{chunk_text}

REQUIREMENTS:
- Questions must be specific, clear, and answerable from the document
- Answers must be 2-4 sentences, comprehensive, and factually grounded
- Include varied question types: factual, conceptual, analytical
- Each pair must relate to the document content
- Output ONLY the JSON array, nothing else

OUTPUT (JSON array only):
[
  {{"question": "...", "answer": "..."}},
  ...
]"""
            }
        ]
        
        # Apply chat template
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        # Tokenize
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        # Generate with lower temperature for consistent JSON output
        logger.debug(f"Generating {num_pairs} Q&A pairs (max_tokens=4096)...")
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=4096,
                temperature=0.4,  # Lower temp for consistent JSON structure
                top_p=0.9,
                top_k=50,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
        
        # Decode response
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=False)
        
        # Extract assistant response (remove prompt)
        if "<|im_start|>assistant" in response:
            assistant_response = response.split("<|im_start|>assistant")[-1]
            assistant_response = assistant_response.replace("<|im_end|>", "").strip()
        else:
            # Fallback: remove prompt tokens
            prompt_tokens = len(inputs['input_ids'][0])
            response_tokens = outputs[0][prompt_tokens:]
            assistant_response = self.tokenizer.decode(response_tokens, skip_special_tokens=True).strip()
        
        # Parse JSON from response
        try:
            # Try to extract JSON array
            if "```json" in assistant_response:
                json_str = assistant_response.split("```json")[1].split("```")[0].strip()
            elif "```" in assistant_response:
                json_str = assistant_response.split("```")[1].split("```")[0].strip()
            else:
                # Find first [ and last ]
                start = assistant_response.find('[')
                end = assistant_response.rfind(']') + 1
                if start >= 0 and end > start:
                    json_str = assistant_response[start:end]
                else:
                    raise ValueError("No JSON array found in response")
            
            qa_pairs = json.loads(json_str)
            
            # Validate format
            if not isinstance(qa_pairs, list):
                raise ValueError(f"Expected list, got {type(qa_pairs)}")
            
            # Convert to standard format with quality validation
            formatted_pairs = []
            rejected_count = 0
            for qa in qa_pairs:
                if isinstance(qa, dict) and "question" in qa and "answer" in qa:
                    question = qa["question"].strip()
                    answer = qa["answer"].strip()
                    
                    # Quality validation
                    if self._validate_qa_pair(question, answer):
                        formatted_pairs.append({
                            "question": question,
                            "answer": answer
                        })
                    else:
                        rejected_count += 1
            
            if rejected_count > 0:
                logger.info(f"Quality filter rejected {rejected_count} pairs")
            logger.info(f"✓ Generated {len(formatted_pairs)} valid Q&A pairs")
            return formatted_pairs
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"Response preview: {assistant_response[:500]}...")
            return []
        except Exception as e:
            logger.error(f"Failed to parse Q&A pairs: {e}")
            return []
    
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
            "target_samples": 1000  # Optional, default 1000
        }
    }
    
    Returns:
    {
        "status": "success",
        "encrypted_dataset": "JSON string with encrypted Q&A pairs",
        "num_samples": 1000
    }
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
        
        # Get target samples
        target_samples = input_data.get('target_samples', 1000)
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
        
        # Split into overlapping chunks
        logger.info("Splitting text into chunks...")
        words = pdf_text.split()
        chunk_size = 500  # words per chunk
        overlap = 100     # overlap between chunks
        
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if len(chunk) > 100:  # Skip tiny chunks
                chunks.append(chunk)
        
        logger.info(f"✓ Split into {len(chunks)} chunks")
        
        # Calculate pairs per chunk
        pairs_per_chunk = max(20, target_samples // len(chunks))
        logger.info(f"Generating {pairs_per_chunk} pairs per chunk...")
        
        # Generate Q&A pairs from each chunk
        all_qa_pairs = []
        for i, chunk in enumerate(chunks):
            logger.info(f"[{i+1}/{len(chunks)}] Generating {pairs_per_chunk} Q&A pairs...")
            
            qa_pairs = generator.generate_qa_pairs(chunk, num_pairs=pairs_per_chunk)
            
            if qa_pairs:
                all_qa_pairs.extend(qa_pairs)
                logger.info(f"  ✓ Generated {len(qa_pairs)} pairs (total: {len(all_qa_pairs)})")
            else:
                logger.warning(f"  ✗ Failed to generate pairs from chunk {i+1}")
        
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

