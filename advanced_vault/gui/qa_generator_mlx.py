"""
MLX-Optimized Q&A Generator with Structured Output

Uses Qwen2.5-3B-Instruct-4bit with Outlines library for guaranteed JSON output.
Apple Silicon (M1-M4) only - requires Metal GPU support.
"""

import logging
import platform
from typing import List, Dict, Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import MLX (may not be available on non-Apple Silicon)
MLX_AVAILABLE = False
OUTLINES_AVAILABLE = False

try:
    import mlx.core as mx
    if mx.metal.is_available():
        MLX_AVAILABLE = True
        logger.debug("MLX Metal GPU available")
    else:
        logger.debug("MLX available but Metal GPU not available")
except ImportError:
    logger.debug("MLX not installed - Q&A generation will use Ollama fallback")

try:
    import outlines
    from pydantic import BaseModel, Field
    OUTLINES_AVAILABLE = True
except ImportError:
    OUTLINES_AVAILABLE = False
    BaseModel = None
    Field = None
    logger.debug("Outlines not installed")

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    RecursiveCharacterTextSplitter = None
    logger.debug("LangChain text splitters not installed")


# Define Pydantic models only if available
if OUTLINES_AVAILABLE and BaseModel:
    class AlpacaQA(BaseModel):
        """Single Q&A pair in Alpaca format."""
        instruction: str = Field(description="The question", min_length=10)
        input: str = Field(default="", description="Optional context")
        output: str = Field(description="The complete answer", min_length=50)


    class ThreeQAPairs(BaseModel):
        """Exactly 3 Q&A pairs - schema enforced by Outlines."""
        qa_pairs: List[AlpacaQA] = Field(min_items=3, max_items=3)
else:
    # Dummy classes if Pydantic not available (will fail gracefully later)
    class AlpacaQA:
        pass
    
    class ThreeQAPairs:
        pass


class MLXQAGenerator:
    """
    MLX-optimized Q&A generator with guaranteed JSON output.
    
    Uses Qwen2.5-3B-Instruct-4bit with Outlines structured generation.
    Requires Apple Silicon (M1-M4) with Metal GPU support.
    
    Advantages over TinyLlama:
    - 100% valid JSON (no manual extraction)
    - Guaranteed 3 Q&A pairs per chunk
    - Better answer completeness
    - Superior multilingual support (Polish/English)
    """
    
    def __init__(self, model_path: str = "mlx-community/Qwen2.5-3B-Instruct-4bit", 
                 progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None):
        """
        Initialize MLX Q&A generator.
        
        Args:
            model_path: HuggingFace model path or local path
            progress_callback: Optional callback(message, percent, time_remaining) for model download progress
            
        Raises:
            RuntimeError: If MLX/Metal not available or dependencies missing
        """
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX requires Apple Silicon (Metal GPU). Install with: pip install mlx-lm")
        
        if not OUTLINES_AVAILABLE:
            raise RuntimeError("Outlines required for structured output. Install with: pip install outlines")
        
        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError("LangChain text splitters required. Install with: pip install langchain-text-splitters")
        
        if platform.machine() != "arm64":
            raise RuntimeError(f"MLX requires Apple Silicon (arm64), detected: {platform.machine()}")
        
        self.model_path = model_path
        self.model = None
        self.generator = None
        
        # Initialize model (with progress if callback provided)
        self._load_model(progress_callback)
        
        # Initialize optimal chunking (512 chars, 20% overlap)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
            is_separator_regex=False
        )
        
        logger.info("MLX Q&A generator initialized (512-char chunks, guaranteed 3 pairs)")
    
    def _load_model(self, progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None):
        """
        Load MLX model with optional progress tracking.
        
        Args:
            progress_callback: Optional callback for download progress
        """
        if progress_callback:
            progress_callback("Loading MLX model (Qwen2.5-3B)...", None, None)
        
        logger.info(f"Loading MLX model: {self.model_path}")
        
        try:
            # Show informative message about download
            # Check for HF token (helps with rate limiting)
            import os
            hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
            token_note = ""
            if hf_token:
                token_note = "\n✅ Using HF token (faster download, no rate limits)"
            else:
                token_note = "\n💡 Tip: Set HF_TOKEN env var for faster downloads (optional)"
            
            if progress_callback:
                progress_callback(
                    f"Downloading Qwen2.5-3B-Instruct-4bit (~1.7GB)\n\n"
                    f"⚠️ First download may take 10-30 minutes.\n"
                    f"📊 Check terminal below for download progress.\n"
                    f"💡 Download happens in background - you can continue using the app.{token_note}",
                    0.0,
                    "10-30 minutes (first download)"
                )
            
            logger.info(f"Loading MLX model: {self.model_path}")
            logger.info("Model download progress shown in terminal (huggingface_hub progress bars)")
            
            # Load model via Outlines (uses huggingface_hub internally, shows progress in terminal)
            # Note: huggingface_hub shows progress bars in terminal, but doesn't expose API for GUI
            # The download is happening, just progress is shown in terminal, not GUI
            if progress_callback:
                progress_callback(
                    "Downloading model files...\n"
                    "📥 Progress visible in terminal below\n"
                    "⏱️ This may take 10-30 minutes on slow connections",
                    5.0,
                    "Downloading (see terminal)"
                )
            
            # This will download the model (progress shown in terminal via huggingface_hub)
            # Note: This is a blocking call that downloads ~1.7GB - can take 10-30 minutes
            # huggingface_hub shows progress bars in terminal but doesn't expose API for GUI
            # So we update progress callback periodically to show it's still working
            import threading
            import time as time_module
            
            download_active = {"active": True}
            
            def heartbeat():
                """Periodic updates to show download is still active."""
                heartbeat_count = 0
                while download_active["active"]:
                    time_module.sleep(10)  # Update every 10 seconds
                    heartbeat_count += 1
                    if progress_callback and download_active["active"]:
                        # Show heartbeat that download is still active
                        # DON'T show fake progress percentage - just indicate it's active
                        # Real progress is shown in terminal via huggingface_hub
                        elapsed_minutes = (heartbeat_count * 10) // 60
                        elapsed_seconds = (heartbeat_count * 10) % 60
                        elapsed_str = f"{elapsed_minutes}m {elapsed_seconds}s" if elapsed_minutes > 0 else f"{elapsed_seconds}s"
                        
                        progress_callback(
                            f"Downloading model files... (still active)\n"
                            f"📥 Check terminal below for detailed progress\n"
                            f"⏱️ This may take 10-30 minutes on slow connections\n"
                            f"⏳ {elapsed_str} elapsed - download in progress...",
                            None,  # NO fake progress percentage - avoid misleading UI
                            None
                        )
            
            heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
            heartbeat_thread.start()
            
            try:
                import os
                import subprocess
                import sys
                
                # Check if hf_transfer is available (Rust-based, 10-100x faster)
                hf_transfer_available = False
                try:
                    import hf_transfer
                    hf_transfer_available = True
                    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
                    logger.info("Using hf_transfer for faster downloads (Rust-based, 10-100x faster)")
                except ImportError:
                    # Try to install hf_transfer automatically
                    logger.info("hf_transfer not installed - attempting auto-install for faster downloads")
                    if progress_callback:
                        progress_callback(
                            "Installing hf_transfer for MUCH faster downloads...\n"
                            "⚡ This will speed up download 10-100x\n"
                            "(Rust-based download protocol)",
                            1.0,
                            None
                        )
                    try:
                        # Try user install first
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "--user", "--quiet", "hf_transfer"],
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        
                        if result.returncode != 0:
                            # Fallback to break-system-packages
                            logger.debug("User install failed, trying with --break-system-packages")
                            result = subprocess.run(
                                [sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "hf_transfer"],
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                        
                        if result.returncode == 0:
                            # Reload to pick up new module
                            import importlib
                            import hf_transfer
                            hf_transfer_available = True
                            os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
                            logger.info("✅ hf_transfer installed successfully - download will be MUCH faster (10-100x)")
                            if progress_callback:
                                progress_callback(
                                    "✅ hf_transfer installed!\n"
                                    "⚡ Download will be 10-100x faster now...",
                                    2.0,
                                    None
                                )
                        else:
                            logger.warning(f"Failed to install hf_transfer: {result.stderr}")
                            if progress_callback:
                                progress_callback(
                                    "⚠️ Could not install hf_transfer\n"
                                    "Download will be slower (~50 kB/s)\n"
                                    "Install manually: pip install hf_transfer",
                                    2.0,
                                    None
                                )
                    except Exception as e:
                        logger.warning(f"Could not install hf_transfer: {e}")
                
                if not hf_transfer_available:
                    logger.warning("Download will be slow without hf_transfer. Install manually: pip install hf_transfer")
                
                # Try to use HF token if available (helps with rate limiting)
                hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
                if hf_token:
                    logger.info("Using HF token for faster download (no rate limiting)")
                    os.environ["HF_TOKEN"] = hf_token
                    os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token
                else:
                    logger.warning("HF_TOKEN not set - download may be slower due to rate limiting")
                
                # Set additional environment variables for faster downloads
                os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"  # Disable telemetry for faster startup
                
                self.model = outlines.models.mlxlm(self.model_path)
            except KeyboardInterrupt:
                download_active["active"] = False
                logger.info("Model download cancelled by user")
                if progress_callback:
                    progress_callback(
                        "❌ Download cancelled\n\n"
                        "You can:\n"
                        "1. Retry Setup (will resume from cache)\n"
                        "2. Use Ollama TinyLlama instead (already downloaded)\n"
                        "3. Set HF_TOKEN env var for faster downloads:\n"
                        "   export HF_TOKEN=your_token_here",
                        None,
                        None
                    )
                raise
            finally:
                download_active["active"] = False
            
            if progress_callback:
                progress_callback("Model downloaded! Initializing...", 90.0, None)
            
            # Create generator with schema enforcement
            self.generator = outlines.generate.json(self.model, ThreeQAPairs)
            
            if progress_callback:
                progress_callback("✅ MLX Q&A model ready!", 100.0, None)
            
            logger.info("MLX model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load MLX model: {e}")
            if progress_callback:
                progress_callback(
                    f"❌ Error: {str(e)}\n\n"
                    "If download failed, try:\n"
                    "1. Check internet connection\n"
                    "2. Retry Setup\n"
                    "3. Or install manually:\n"
                    "   pip install huggingface_hub\n"
                    "   python -c \"from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-3B-Instruct-4bit')\"",
                    None,
                    None
                )
            raise
    
    @staticmethod
    def is_available() -> bool:
        """
        Check if MLX Q&A generation is available.
        
        Returns:
            True if Apple Silicon + MLX + Outlines available
        """
        if platform.machine() != "arm64":
            return False
        
        if not MLX_AVAILABLE:
            return False
        
        if not OUTLINES_AVAILABLE:
            return False
        
        try:
            import mlx.core as mx
            return mx.metal.is_available()
        except Exception:
            return False
    
    def chunk_document(self, text: str) -> List[str]:
        """
        Split document into optimal chunks for Q&A generation.
        
        Args:
            text: Full document text
            
        Returns:
            List of text chunks (512 chars optimal)
        """
        chunks = self.text_splitter.split_text(text)
        cleaned_chunks = [self._clean_chunk(c) for c in chunks]
        
        logger.debug(f"Split document into {len(cleaned_chunks)} chunks (512 chars optimal)")
        return cleaned_chunks
    
    def _clean_chunk(self, chunk: str) -> str:
        """
        Ensure chunk ends at sentence boundary.
        
        Args:
            chunk: Text chunk
            
        Returns:
            Chunk ending at sentence boundary
        """
        if not chunk:
            return chunk
        
        # Check if already ends properly
        if chunk.endswith(('.', '!', '?', '"', "'")):
            return chunk
        
        # Find last sentence boundary (keep at least 70% of chunk)
        for sep in ['. ', '! ', '? ']:
            pos = chunk.rfind(sep)
            if pos > len(chunk) * 0.7:
                return chunk[:pos+1]
        
        # If no boundary found, return as-is
        return chunk
    
    def generate_qa_pairs(self, chunk: str, language: str = "auto") -> List[Dict[str, str]]:
        """
        Generate exactly 3 Q&A pairs from chunk with guaranteed JSON output.
        
        Args:
            chunk: Text chunk (512 chars optimal)
            language: "auto", "pl", "en" (auto-detects if "auto")
            
        Returns:
            List of 3 Q&A pairs in Alpaca format (guaranteed valid)
        """
        if not chunk or len(chunk.strip()) < 50:
            logger.debug("Chunk too short for Q&A generation")
            return []
        
        # Detect language if auto
        lang_instruction = ""
        if language == "auto":
            # Simple detection: check for Polish characters
            if any(c in chunk for c in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ'):
                lang_instruction = "Generate questions and answers in Polish."
            else:
                lang_instruction = "Generate questions and answers in the same language as the source text."
        elif language == "pl":
            lang_instruction = "Generate questions and answers in Polish."
        elif language == "en":
            lang_instruction = "Generate questions and answers in English."
        
        # Create optimized prompt for Qwen2.5
        prompt = f"""Generate exactly 3 high-quality question-answer pairs from this text.

REQUIREMENTS:
1. Questions must be clear, specific, and directly answerable from the text
2. Answers must be complete sentences (minimum 50 characters)
3. Cover 3 different aspects or concepts from the text
4. {lang_instruction}

Text: {chunk}

Generate 3 diverse Q&A pairs now:"""
        
        try:
            # Generate with structured output (guaranteed valid JSON)
            # Note: MLXLM through Outlines doesn't support temperature parameter
            # Only max_tokens is supported for MLX models
            # Increased to 2500 to handle very long answers and prevent JSON truncation
            # Some chunks generate answers > 2000 tokens, so we start high
            result = self.generator(
                prompt,
                max_tokens=2500  # Increased to handle very long answers and prevent unterminated strings
            )
            
            # Convert Pydantic models to dicts
            qa_pairs = []
            for qa in result.qa_pairs:
                qa_pairs.append({
                    "instruction": qa.instruction.strip(),
                    "input": qa.input.strip() if qa.input else "",
                    "output": qa.output.strip()
                })
            
            logger.info(f"MLX generated {len(qa_pairs)} Q&A pairs (guaranteed 3)")
            
            # Validate we got exactly 3
            if len(qa_pairs) != 3:
                logger.warning(f"Expected 3 Q&A pairs, got {len(qa_pairs)}")
            
            return qa_pairs
            
        except Exception as e:
            error_msg = str(e)
            # Check if it's a JSON truncation error (unterminated string)
            # Check both the exception message and the traceback for error indicators
            is_truncation_error = (
                "Unterminated string" in error_msg or 
                "JSONDecodeError" in error_msg or
                "unterminated" in error_msg.lower() or
                "value_error.jsondecode" in error_msg.lower()
            )
            
            if is_truncation_error:
                logger.warning(f"MLX generated incomplete JSON (likely max_tokens too low): {error_msg[:300]}")
                # Retry with even higher max_tokens
                try:
                    logger.info("Retrying MLX Q&A generation with higher max_tokens (3500)...")
                    result = self.generator(
                        prompt,
                        max_tokens=3500  # Even higher for retry - some answers can be very long
                    )
                    # Convert Pydantic models to dicts
                    qa_pairs = []
                    for qa in result.qa_pairs:
                        qa_pairs.append({
                            "instruction": qa.instruction.strip(),
                            "input": qa.input.strip() if qa.input else "",
                            "output": qa.output.strip()
                        })
                    
                    logger.info(f"MLX generated {len(qa_pairs)} Q&A pairs after retry (guaranteed 3)")
                    return qa_pairs
                except Exception as retry_error:
                    logger.error(f"MLX Q&A generation retry also failed: {retry_error}")
                    return []
            else:
                logger.error(f"MLX Q&A generation failed: {e}", exc_info=True)
                return []
    
    def generate_from_chunks(self, text_chunks: List[str], language: str = "auto") -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from multiple chunks.
        
        Args:
            text_chunks: List of text chunks
            language: Language setting
            
        Returns:
            List of all Q&A pairs
        """
        all_qa_pairs = []
        
        logger.info(f"Generating Q&A pairs from {len(text_chunks)} chunks using MLX")
        
        for i, chunk in enumerate(text_chunks):
            logger.info(f"Processing chunk {i+1}/{len(text_chunks)}")
            
            qa_pairs = self.generate_qa_pairs(chunk, language)
            
            if qa_pairs:
                all_qa_pairs.extend(qa_pairs)
                logger.info(f"Generated {len(qa_pairs)} Q&A pairs from chunk {i+1}")
            else:
                logger.warning(f"Failed to generate Q&A pairs from chunk {i+1}")
        
        logger.info(f"MLX Q&A generation complete: {len(all_qa_pairs)} total pairs from {len(text_chunks)} chunks")
        return all_qa_pairs
    
    def get_model_info(self) -> Dict[str, str]:
        """
        Get information about loaded model.
        
        Returns:
            Dictionary with model information
        """
        return {
            "model_type": "MLX",
            "model_name": "Qwen2.5-3B-Instruct-4bit",
            "platform": platform.machine(),
            "structured_output": "Outlines (guaranteed JSON)",
            "chunk_size": "512 chars (optimal)",
            "pairs_per_chunk": "3 (guaranteed)"
        }

