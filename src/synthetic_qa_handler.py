"""
Secure Synthetic Q&A Generator for WDVA

Generates 1,000+ Q&A pairs using Qwen3-235B-A22B-Instruct-2507 (MoE model).
Maintains end-to-end encryption - PDF never exposed in plaintext.

Model: Qwen3-235B-A22B-Instruct-2507
- 235B total parameters, 22B activated (MoE)
- Native 256K context (extendable to 1M)
- Excellent for high-quality synthetic data generation
"""

import runpod
import json
import base64
import secrets
import logging
import sys
import os
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
    Generate synthetic Q&A pairs using Qwen3-235B-A22B-Instruct-2507.
    
    Maintains end-to-end encryption:
    - PDF encrypted before network transmission
    - Decryption only in this RunPod instance
    - Results encrypted before returning
    """
    
    def __init__(self):
        """Initialize with Qwen3-235B-A22B-Instruct-2507 model."""
        self.model_name = "Qwen/Qwen3-235B-A22B-Instruct-2507"
        
        logger.info(f"Loading model: {self.model_name}")
        logger.info("Model specs: 235B total params, 22B activated (MoE), 256K context")
        
        # Load model with 4-bit quantization for efficiency
        # MoE models are more efficient than dense models
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
            trust_remote_code=True
        )
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True
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
    
    def generate_qa_pairs(self, chunk_text: str, num_pairs: int = 20) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs using Qwen3-235B-A22B-Instruct-2507.
        
        Args:
            chunk_text: Document chunk to generate Q&A from
            num_pairs: Number of Q&A pairs to generate
            
        Returns:
            List of Q&A pairs [{"question": "...", "answer": "..."}]
        """
        # Format prompt for Qwen3 chat template
        messages = [
            {
                "role": "system",
                "content": "You are an expert at creating high-quality training data for fine-tuning language models. Generate diverse, comprehensive question-answer pairs that cover different aspects and cognitive levels."
            },
            {
                "role": "user",
                "content": f"""Generate {num_pairs} diverse question-answer pairs from this document section.

DOCUMENT SECTION:
{chunk_text}

REQUIREMENTS:
1. Create questions testing different cognitive levels:
   - Factual recall: "What is X?"
   - Conceptual understanding: "Why does X work?"
   - Application: "How would you use X?"
   - Analysis: "Compare X and Y"
   - Synthesis: "How could X be improved?"

2. Vary question difficulty (easy, medium, hard)

3. Make answers comprehensive (3-5 sentences) and grounded in the document

4. Ensure questions are specific and answerable from the text

5. Avoid yes/no questions

OUTPUT FORMAT: JSON array with objects containing "question" and "answer" fields.

Example:
[
  {{"question": "What is the main purpose of X?", "answer": "The main purpose of X is..."}},
  {{"question": "How does Y work?", "answer": "Y works by..."}}
]

Generate exactly {num_pairs} Q&A pairs now:"""
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
        
        # Generate
        logger.debug(f"Generating {num_pairs} Q&A pairs (max_tokens=4096)...")
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=4096,
                temperature=0.7,
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
            
            # Convert to standard format
            formatted_pairs = []
            for qa in qa_pairs:
                if isinstance(qa, dict) and "question" in qa and "answer" in qa:
                    formatted_pairs.append({
                        "question": qa["question"].strip(),
                        "answer": qa["answer"].strip()
                    })
            
            logger.info(f"✓ Generated {len(formatted_pairs)} Q&A pairs")
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
        Encrypt generated dataset using XChaCha20-Poly1305.
        
        Args:
            data: List of Q&A pairs
            encryption_key: 32-byte encryption key
            
        Returns:
            JSON string with encrypted package
        """
        # Serialize data
        plaintext = json.dumps(data).encode('utf-8')
        
        # Generate nonce
        nonce = secrets.token_bytes(24)
        
        # Encrypt
        if CRYPTO_BACKEND == "pycryptodome":
            cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        else:
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
            logger.info("Initializing Qwen3-235B-A22B-Instruct-2507...")
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
            "num_samples": len(training_data),
            "model": "Qwen3-235B-A22B-Instruct-2507"
        }
    
    except Exception as e:
        logger.error(f"Error in handler: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

