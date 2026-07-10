"""
Q&A Generator Service

Generates Q&A pairs from PDF text chunks using MLX (Apple Silicon), Ollama, or RunPod.
Formats output as Alpaca training dataset (JSONL).

Priority order:
1. MLX (Qwen2.5-3B with Outlines) - Apple Silicon only, guaranteed JSON
2. Ollama (TinyLlama/Llama3.2) - Local fallback
3. RunPod - Cloud fallback
"""

import logging
import requests
import json
import time
import os
import platform
from typing import List, Dict, Any, Optional, Tuple, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# QA generation endpoint environment variable name
# This endpoint is separate from the inference endpoint used by the backend
# Set RUNPOD_QA_ENDPOINT_ID environment variable to configure the QA generation endpoint
SYNTHETIC_QA_ENDPOINT_ID_ENV = "RUNPOD_QA_ENDPOINT_ID"

# API key for QA generation endpoint (can be overridden via environment variable)
# Uses RUNPOD_QA_API_KEY if set, otherwise falls back to RUNPOD_API_KEY
# This allows separate API keys for QA generation vs inference if needed
SYNTHETIC_QA_API_KEY_ENV = "RUNPOD_QA_API_KEY"

# Try to import MLX generator (Apple Silicon only)
try:
    from qa_generator_mlx import MLXQAGenerator
    MLX_MODULE_AVAILABLE = True
except ImportError:
    MLX_MODULE_AVAILABLE = False
    logger.debug("MLX Q&A generator module not available")


class QAGenerator:
    """
    Service for generating Q&A pairs from PDF chunks.
    
    Priority order:
    1. MLX (Apple Silicon) - Best quality, guaranteed JSON, 3 pairs per chunk
    2. Ollama (local) - Fallback for non-Apple Silicon or if MLX unavailable
    3. RunPod (cloud) - Final fallback
    """
    
    def __init__(self, runpod_endpoint_id: Optional[str] = None, runpod_api_key: Optional[str] = None,
                 ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None):
        """
        Initialize Q&A generator.
        
        Args:
            runpod_endpoint_id: RunPod endpoint ID for inference
            runpod_api_key: RunPod API key
            ollama_base_url: Optional Ollama base URL for fallback (defaults to http://localhost:11434)
            ollama_model: Optional Ollama model for fallback (defaults to tinyllama, can upgrade to llama3.2:3b)
        """
        # Ensure RUNPOD_QA_API_KEY is set by default from RUNPOD_API_KEY
        # This ensures QA generation endpoint works by default
        self._ensure_qa_api_key_set()
        
        self.endpoint_id = runpod_endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        self.api_key = runpod_api_key or os.getenv("RUNPOD_API_KEY")
        self.base_url = f"https://api.runpod.ai/v2/{self.endpoint_id}" if self.endpoint_id else None
        
        # Ollama fallback configuration
        self.ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_QA_MODEL", "tinyllama")
        
        # Try to initialize MLX generator (Apple Silicon only)
        # Use lazy loading - don't load model until first use (to avoid blocking startup)
        self.mlx_generator = None
        self.mlx_initialized = False
        self.mlx_available = False
        
        if MLX_MODULE_AVAILABLE and platform.machine() == "arm64":
            try:
                if MLXQAGenerator.is_available():
                    self.mlx_available = True
                    logger.info("MLX Q&A generator available (will load on first use)")
                else:
                    # Check what's missing and log it
                    logger.info("MLX available but dependencies missing - attempting auto-install on first use")
                    # Will try to install automatically when user clicks Setup
                    self.mlx_available = True  # Set to True so we can try to install dependencies
            except Exception as e:
                logger.debug(f"MLX availability check failed: {e}, will use Ollama fallback")
        
        if not self.endpoint_id or not self.api_key:
            logger.warning("RunPod endpoint not configured. Q&A generation will use MLX/Ollama fallback if available.")
    
    def _ensure_qa_api_key_set(self):
        """
        Ensure RUNPOD_QA_API_KEY is set by default from RUNPOD_API_KEY.
        This ensures the QA generation endpoint works by default when RUNPOD_API_KEY is configured.
        """
        runpod_api_key = os.getenv("RUNPOD_API_KEY")
        qa_api_key = os.getenv(SYNTHETIC_QA_API_KEY_ENV)
        
        if not qa_api_key and runpod_api_key:
            os.environ[SYNTHETIC_QA_API_KEY_ENV] = runpod_api_key
            logger.debug(f"Set {SYNTHETIC_QA_API_KEY_ENV} to RUNPOD_API_KEY by default (QA endpoint will be used)")
        elif qa_api_key:
            logger.debug(f"{SYNTHETIC_QA_API_KEY_ENV} already set (explicit value)")
        elif not runpod_api_key:
            logger.debug("RUNPOD_API_KEY not set - QA generation will use local MLX/Ollama fallback")
    
    def is_ollama_available(self) -> bool:
        """
        Check if Ollama is available for Q&A generation.
        
        Returns:
            True if Ollama is running and accessible
        """
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def is_qa_model_available(self) -> bool:
        """
        Check if Q&A model is available (MLX preferred, Ollama fallback).
        
        Returns:
            True if MLX or Ollama model is available
        """
        # Check MLX first (Apple Silicon) - don't require full initialization
        if self.mlx_available:
            try:
                if MLXQAGenerator.is_available():
                    logger.debug("MLX Q&A model available")
                    return True
            except Exception:
                pass
        
        # Check Ollama fallback
        if not self.is_ollama_available():
            return False
        
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "").lower() for m in models]
                
                # Check for TinyLlama
                if any("tinyllama" in name for name in model_names):
                    return True
                
                # Check for Llama3.2 fallback
                if any("llama3.2" in name and "vision" not in name for name in model_names):
                    return True
        except Exception:
            pass
        
        return False
    
    def setup_qa_model(self, progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None) -> Tuple[bool, str]:
        """
        Setup Q&A model (MLX preferred, Ollama fallback) with progress tracking.
        
        Args:
            progress_callback: Optional callback(message, percent, time_remaining) for progress updates
        
        Returns:
            (success: bool, message: str)
        """
        # Check if MLX is available (Apple Silicon)
        if self.mlx_available:
            # Check if dependencies are installed, try to install if missing
            if not MLXQAGenerator.is_available():
                logger.info("MLX dependencies missing, attempting auto-install...")
                if progress_callback:
                    progress_callback("Installing MLX dependencies (outlines, langchain-text-splitters)...", None, None)
                
                success = self._install_mlx_dependencies(progress_callback)
                if not success:
                    logger.warning("Failed to install MLX dependencies, falling back to Ollama")
                    return False, "Failed to install MLX dependencies. Please install manually: pip install outlines langchain-text-splitters"
            
            # Initialize MLX with progress if not already initialized
            if not self.mlx_initialized:
                try:
                    logger.info("Initializing MLX Q&A generator with progress tracking...")
                    self.mlx_generator = MLXQAGenerator(progress_callback=progress_callback)
                    self.mlx_initialized = True
                    logger.info("MLX Q&A model initialized successfully")
                    return True, "MLX Q&A model ready (Qwen2.5-3B-Instruct-4bit)"
                except Exception as e:
                    logger.error(f"MLX initialization failed: {e}")
                    return False, f"MLX initialization failed: {str(e)}"
            else:
                if progress_callback:
                    progress_callback("MLX Q&A model ready (Qwen2.5-3B)", 100.0, None)
                logger.info("MLX Q&A model already initialized")
                return True, "MLX Q&A model ready (Qwen2.5-3B-Instruct-4bit)"
        
        # Fallback to Ollama setup
        if not self.is_ollama_available():
            return False, "Ollama server is not running. Please start Ollama first."
        
        if self.is_qa_model_available():
            logger.info("Q&A model already available")
            if progress_callback:
                progress_callback("Q&A model already available", 100.0, None)
            return True, "Q&A model already available"
        
        try:
            if progress_callback:
                progress_callback(f"Downloading model {self.ollama_model}...", 0.0, None)
            
            logger.info(f"Downloading Q&A model {self.ollama_model}...")
            
            # Use Ollama API to pull model
            response = requests.post(
                f"{self.ollama_base_url}/api/pull",
                json={"name": self.ollama_model},
                stream=True,
                timeout=600  # 10 minutes timeout
            )
            
            if response.status_code == 200:
                import json
                
                # Track progress
                start_time = time.time()
                last_update_time = start_time
                last_completed = 0
                download_speeds = []
                last_time_remaining_str = None
                last_time_remaining_update = 0
                
                # Stream progress updates
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)
                            
                            # Calculate progress percentage
                            percent = None
                            if total > 0:
                                percent = min(100.0, (completed / total) * 100.0)
                            
                            # Calculate download speed and time remaining
                            time_remaining = None
                            current_time = time.time()
                            
                            if completed > 0 and total > 0 and completed > last_completed:
                                time_diff = current_time - last_update_time
                                if time_diff > 0.5:
                                    bytes_diff = completed - last_completed
                                    speed = bytes_diff / time_diff
                                    download_speeds.append(speed)
                                    
                                    if len(download_speeds) > 10:
                                        download_speeds.pop(0)
                                    
                                    if download_speeds:
                                        avg_speed = sum(download_speeds) / len(download_speeds)
                                        remaining_bytes = total - completed
                                        if avg_speed > 0:
                                            remaining_seconds = remaining_bytes / avg_speed
                                            
                                            time_since_last_update = current_time - last_time_remaining_update
                                            if time_since_last_update >= 3.0:
                                                if remaining_seconds < 60:
                                                    time_remaining = f"{int(remaining_seconds)}s"
                                                elif remaining_seconds < 3600:
                                                    minutes = int(remaining_seconds // 60)
                                                    seconds = int((remaining_seconds % 60) // 5) * 5
                                                    time_remaining = f"{minutes}m {seconds}s"
                                                else:
                                                    hours = int(remaining_seconds // 3600)
                                                    minutes = int((remaining_seconds % 3600) // 60)
                                                    time_remaining = f"{hours}h {minutes}m"
                                                
                                                last_time_remaining_str = time_remaining
                                                last_time_remaining_update = current_time
                                            else:
                                                time_remaining = last_time_remaining_str
                            
                            # Update progress callback
                            if progress_callback:
                                status_msg = status if status else f"Downloading {self.ollama_model}..."
                                progress_callback(status_msg, percent, time_remaining)
                            
                            last_update_time = current_time
                            last_completed = completed
                            
                        except json.JSONDecodeError:
                            continue
                
                # Verify model is available
                time.sleep(2)  # Give Ollama time to register the model
                if self.is_qa_model_available():
                    if progress_callback:
                        progress_callback(f"Model {self.ollama_model} downloaded successfully", 100.0, None)
                    logger.info(f"Model {self.ollama_model} downloaded successfully")
                    return True, f"Model {self.ollama_model} downloaded successfully"
                else:
                    if progress_callback:
                        progress_callback(f"Model downloaded but not available", None, None)
                    logger.warning(f"Model {self.ollama_model} downloaded but not available")
                    return False, f"Model downloaded but not available"
            else:
                error_msg = f"Failed to download model: {response.status_code} {response.text}"
                logger.error(error_msg)
                if progress_callback:
                    progress_callback(f"Model download error: {response.status_code}", None, None)
                return False, error_msg
                
        except Exception as e:
            logger.error(f"Error downloading Q&A model: {e}")
            if progress_callback:
                progress_callback(f"Model download error: {str(e)}", None, None)
            return False, f"Error downloading model: {str(e)}"
    
    def get_qa_status(self) -> dict:
        """
        Get current Q&A generation status.
        
        Returns:
            Dictionary with status information
        """
        mlx_info = None
        if self.mlx_initialized and self.mlx_generator:
            try:
                mlx_info = self.mlx_generator.get_model_info()
            except Exception:
                pass
        
        return {
            "mlx_available": self.mlx_available,
            "mlx_initialized": self.mlx_initialized,
            "mlx_info": mlx_info,
            "ollama_available": self.is_ollama_available(),
            "qa_model_available": self.is_qa_model_available(),
            "model_name": self.ollama_model,
            "ollama_base_url": self.ollama_base_url,
            "preferred_method": "MLX" if self.mlx_available else "Ollama"
        }
    
    def _install_mlx_dependencies(self, progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None) -> bool:
        """
        Automatically install MLX dependencies (outlines, langchain-text-splitters).
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            True if installation successful
        """
        import subprocess
        import sys
        
        dependencies = [
            "outlines>=0.0.46",
            "langchain-text-splitters>=0.3.0"
        ]
        
        for dep in dependencies:
            try:
                if progress_callback:
                    progress_callback(f"Installing {dep}...", None, None)
                
                logger.info(f"Installing {dep}...")
                
                # Try user install first
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--user", dep],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode != 0:
                    # Fallback to break-system-packages
                    logger.debug(f"User install failed for {dep}, trying with --break-system-packages")
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--break-system-packages", dep],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                
                if result.returncode != 0:
                    logger.error(f"Failed to install {dep}: {result.stderr}")
                    return False
                
                logger.info(f"Successfully installed {dep}")
                
            except Exception as e:
                logger.error(f"Error installing {dep}: {e}")
                return False
        
        # Reload module to pick up new imports
        try:
            import importlib
            if MLX_MODULE_AVAILABLE:
                import qa_generator_mlx
                importlib.reload(qa_generator_mlx)
                global MLXQAGenerator
                MLXQAGenerator = qa_generator_mlx.MLXQAGenerator
        except Exception as e:
            logger.warning(f"Could not reload MLX module: {e}")
        
        return True
    
    def _is_chunk_valid(self, text_chunk: str) -> bool:
        """
        Validate if a text chunk is suitable for Q&A generation.
        
        Filters out:
        - Empty or very short chunks
        - Chunks that are just page separators
        - Footer/copyright content
        - Social media comments/metadata
        - Chunks with mostly special characters
        
        Args:
            text_chunk: Text chunk to validate
            
        Returns:
            True if chunk is valid for Q&A generation
        """
        if not text_chunk or len(text_chunk.strip()) < 100:
            return False
        
        chunk_lower = text_chunk.lower().strip()
        
        # Filter out chunks that start with page separator and have minimal content after
        # Common patterns: "--- Page X ---", "--- Page X ---\n\n"
        if chunk_lower.startswith("---"):
            # Remove page separator patterns
            remaining = chunk_lower.replace("---", "").replace("page", "").strip()
            # Remove common punctuation and numbers
            remaining_clean = ''.join(c for c in remaining if c.isalpha() or c.isspace())
            remaining_clean = ' '.join(remaining_clean.split())  # Normalize whitespace
            
            # If very little content after separator, reject
            if len(remaining_clean) < 50 or len(remaining_clean.split()) < 8:
                logger.debug(f"Skipping chunk: Starts with page separator, minimal content ({len(remaining_clean)} chars)")
                return False
        
        # Filter out common footer/copyright patterns
        footer_patterns = [
            "copyright", "©", "all rights reserved",
            "privacy policy", "terms of service",
            "substack", "write a comment", "liked by",
            "discussion about this post", "collection notice"
        ]
        if any(pattern in chunk_lower for pattern in footer_patterns):
            # Check if it's mostly footer (more than 50% matches)
            matches = sum(1 for pattern in footer_patterns if pattern in chunk_lower)
            if matches >= 2:  # Multiple footer patterns = likely footer
                logger.debug("Skipping chunk: Footer/copyright content")
                return False
        
        # Filter out social media comments
        if ("like" in chunk_lower and "reply" in chunk_lower) or \
           ("likes" in chunk_lower and "restacks" in chunk_lower) or \
           ("comments" in chunk_lower and "comment..." in chunk_lower):
            logger.debug("Skipping chunk: Social media comments")
            return False
        
        # Filter out chunks with too many special characters (likely OCR artifacts or metadata)
        text_only = ''.join(c for c in text_chunk if c.isalnum() or c.isspace())
        if len(text_only) < len(text_chunk) * 0.5:  # Less than 50% alphanumeric
            logger.debug("Skipping chunk: Too many special characters")
            return False
        
        # Must have meaningful words (at least 10 words)
        words = chunk_lower.split()
        meaningful_words = [w for w in words if len(w) > 2]  # Exclude very short "words"
        if len(meaningful_words) < 10:
            logger.debug(f"Skipping chunk: Too few meaningful words ({len(meaningful_words)})")
            return False
        
        return True
    
    def generate_qa_pairs(
        self,
        text_chunk: str | List[str],
        num_pairs: int = 3,
        max_pairs: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from a text chunk.
        
        Priority order:
        1. MLX (Apple Silicon) - Best quality, guaranteed 3 pairs, valid JSON
        2. Ollama (local) - Fallback
        3. RunPod (cloud) - Final fallback
        
        Args:
            text_chunk: Text chunk to generate Q&A from
            num_pairs: Number of Q&A pairs to generate (MLX always generates 3)
            
        Returns:
            List of Q&A pairs in format [{"instruction": "question", "output": "answer"}, ...]
        """
        # Backward compatibility: some callers pass list[str] and max_pairs.
        if isinstance(text_chunk, list):
            pairs = self.generate_from_chunks(
                text_chunks=text_chunk,
                user_id="unknown",
                num_pairs_per_chunk=num_pairs
            )
            if max_pairs is not None:
                return pairs[:max_pairs]
            return pairs

        if not text_chunk or not text_chunk.strip():
            return []
        
        # Validate chunk
        if not self._is_chunk_valid(text_chunk):
            logger.debug(f"Skipping invalid chunk (length: {len(text_chunk)})")
            return []
        
        # Try MLX first (Apple Silicon, best quality)
        # Lazy initialization - load model on first use
        if self.mlx_available and not self.mlx_initialized:
            try:
                logger.info("Initializing MLX Q&A generator (first use)...")
                self.mlx_generator = MLXQAGenerator()
                self.mlx_initialized = True
                logger.info("MLX Q&A generator initialized successfully")
                # Status will be updated dynamically in Settings view via get_qa_status()
            except Exception as e:
                logger.warning(f"MLX initialization failed: {e}, will use Ollama fallback")
                self.mlx_available = False
        
        if self.mlx_generator:
            try:
                mlx_pairs = self.mlx_generator.generate_qa_pairs(text_chunk)
                if mlx_pairs and len(mlx_pairs) >= num_pairs:
                    logger.info(f"MLX generated {len(mlx_pairs)} Q&A pairs (guaranteed valid JSON)")
                    return mlx_pairs[:num_pairs]  # Return requested number
            except Exception as e:
                logger.debug(f"MLX generation failed: {e}, falling back to Ollama")
        
        # Try Ollama second (local, privacy-preserving)
        try:
            ollama_pairs = self._generate_qa_with_ollama(text_chunk, num_pairs)
            if ollama_pairs:
                logger.info(f"Ollama generated {len(ollama_pairs)} Q&A pairs")
                return ollama_pairs
        except Exception as e:
            logger.debug(f"Ollama generation failed: {e}")
        
        # Fallback to RunPod if local methods unavailable
        if self.base_url and self.api_key:
            logger.info("Falling back to RunPod for Q&A generation...")
            return self._generate_qa_with_runpod(text_chunk, num_pairs)
        else:
            logger.warning("No Q&A generation method available (MLX/Ollama/RunPod all unavailable)")
            return []
    
    def _generate_qa_with_runpod(self, text_chunk: str, num_pairs: int) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs using RunPod inference.
        
        Args:
            text_chunk: Text to generate Q&A from
            num_pairs: Number of Q&A pairs to generate
            
        Returns:
            List of Q&A pairs
        """
        try:
            # Limit chunk length
            max_chunk_length = 1200
            if len(text_chunk) > max_chunk_length:
                logger.warning(f"Text chunk too long ({len(text_chunk)} chars), truncating to {max_chunk_length}")
                text_chunk = text_chunk[:max_chunk_length] + "..."
            
            # Detect language
            language_hint = ""
            if any(c in text_chunk for c in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ'):
                language_hint = "\nImportant: The text is in Polish. Generate questions and answers in Polish."
            elif any(c in text_chunk for c in 'àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ'):
                language_hint = "\nImportant: Generate questions and answers in the same language as the source text."
            
            # Create concise prompt
            prompt = f"""Create {num_pairs} Q&A pairs from:

{text_chunk}

{language_hint}

JSON format:
[
  {{"instruction": "question", "output": "answer"}},
  {{"instruction": "question", "output": "answer"}},
  {{"instruction": "question", "output": "answer"}}
]"""
            
            # Submit inference job
            payload = {
                "input": {
                    "task": "inference",
                    "prompt": prompt,
                    "max_tokens": 1024,
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "user_id": "qa_generator"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/run",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to submit Q&A generation job: {response.status_code} {response.text}")
                return []
            
            job_data = response.json()
            job_id = job_data.get('id')
            
            if not job_id:
                logger.error(f"No job ID in response: {job_data}")
                return []
            
            # Wait for completion
            result = self._wait_for_completion(job_id, timeout=120)
            
            if not result or "error" in result:
                logger.error(f"Q&A generation failed: {result}")
                return []
            
            response_text = result.get("response", "")
            
            if not response_text:
                logger.warning(f"Empty response from RunPod")
                return []
            
            # Parse response
            qa_pairs = self._parse_qa_response(response_text, num_pairs, text_chunk)
            return qa_pairs
            
        except Exception as e:
            logger.error(f"Error generating Q&A pairs with RunPod: {e}")
            return []
    
    def _generate_qa_with_ollama(self, text_chunk: str, num_pairs: int) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs using local Ollama as fallback.
        
        Args:
            text_chunk: Text to generate Q&A from
            num_pairs: Number of Q&A pairs to generate
            
        Returns:
            List of Q&A pairs
        """
        try:
            # Check if Ollama is available
            try:
                response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
                if response.status_code != 200:
                    logger.debug("Ollama not available for fallback")
                    return []
            except Exception:
                logger.debug("Ollama not available for fallback")
                return []
            
            # Check if model is available
            models_response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            if models_response.status_code == 200:
                models = models_response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                # Try to find a suitable text model (not vision)
                available_model = None
                
                # First try: exact match or TinyLlama
                for model_name in model_names:
                    if self.ollama_model in model_name.lower() or "tinyllama" in model_name.lower():
                        if "vision" not in model_name.lower():
                            available_model = model_name
                            break
                
                # Fallback: try Llama3.2 models if TinyLlama not found
                if not available_model:
                    for model_name in model_names:
                        if "llama3.2" in model_name.lower():
                            if "vision" not in model_name.lower():
                                available_model = model_name
                                break
                
                if not available_model:
                    logger.debug(f"No suitable Ollama model found. Available: {model_names}")
                    return []
                
                logger.info(f"Using Ollama model: {available_model} for Q&A generation")
            else:
                logger.debug("Could not check Ollama models")
                return []
            
            # Limit chunk length for Ollama (TinyLlama has smaller context window)
            max_chunk_length = 800
            truncated_chunk = text_chunk[:max_chunk_length] if len(text_chunk) > max_chunk_length else text_chunk
            
            # Detect language
            language_hint = ""
            if any(c in text_chunk for c in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ'):
                language_hint = "\nImportant: The text is in Polish. Generate questions and answers in Polish."
            elif any(c in text_chunk for c in 'àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ'):
                language_hint = "\nImportant: Generate questions and answers in the same language as the source text."
            
            # Create simpler prompt for TinyLlama (text format instead of JSON)
            # TinyLlama struggles with JSON, so use a simpler format
            prompt = f"""Create {num_pairs} question-answer pairs from this text:

{truncated_chunk}

{language_hint}

IMPORTANT: Each pair must have BOTH a question AND an answer.

Format:
Q: question here
A: answer here

Q: question here
A: answer here

Q: question here
A: answer here"""
            
            # Call Ollama API with slightly higher temperature for TinyLlama
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": available_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,  # Higher temperature for more creative output
                        "num_predict": 1500,  # Much more tokens for complete Q&A pairs (TinyLlama needs space for 3 pairs)
                        "top_p": 0.9,
                        "repeat_penalty": 1.1,  # Prevent repetition
                    }
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")
                
                if response_text:
                    logger.debug(f"Ollama response received ({len(response_text)} chars)")
                    logger.debug(f"Ollama response preview: {response_text[:300]}")
                    # Parse Q&A pairs
                    qa_pairs = self._parse_qa_response(response_text, num_pairs, text_chunk)
                    if qa_pairs:
                        logger.info(f"Ollama generated {len(qa_pairs)} Q&A pairs")
                        # Small delay after successful generation to prevent rate limiting
                        time.sleep(0.5)
                        return qa_pairs
                    else:
                        logger.warning(f"Ollama returned response but no Q&A pairs extracted. Response: {response_text[:500]}")
                        # If we got a response but no pairs, wait a bit before retry or fallback
                        time.sleep(1)
            
            return []
            
        except Exception as e:
            logger.debug(f"Ollama fallback error: {e}")
            return []
    
    def _wait_for_completion(self, job_id: str, timeout: int = 120) -> Optional[Dict[str, Any]]:
        """
        Wait for RunPod job to complete.
        
        Args:
            job_id: RunPod job ID
            timeout: Maximum wait time in seconds
            
        Returns:
            Job result or None if failed/timed out
        """
        start_time = time.time()
        poll_interval = 2
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/status/{job_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    timeout=10
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get job status: {response.status_code}")
                    return None
                
                status_data = response.json()
                status = status_data.get("status")
                
                if status == "COMPLETED":
                    output = status_data.get("output", {})
                    # The response might be directly in output or nested in output.response
                    # Check both formats
                    if isinstance(output, dict):
                        response_text = output.get("response", "")
                        if not response_text and "text" in output:
                            response_text = output.get("text", "")
                        if not response_text:
                            # Sometimes the response is the output itself
                            logger.warning(f"Could not find response in output: {output}")
                            return None
                        
                        return {"response": response_text}
                    else:
                        # Output might be a string directly
                        return {"response": str(output)}
                elif status == "FAILED":
                    error = status_data.get("error", "Unknown error")
                    logger.error(f"Job failed: {error}")
                    return {"error": error}
                
                # Still processing
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error checking job status: {e}")
                return None
        
        logger.error(f"Job timed out after {timeout}s")
        return None
    
    def _is_valid_qa_pair(self, instruction: str, output: str, original_text: str = "") -> bool:
        """
        Validate if a Q&A pair is actually valid (not echo, not empty, meaningful).
        
        Args:
            instruction: Question text
            output: Answer text
            original_text: Original chunk text (optional, for validation)
            
        Returns:
            True if pair is valid
        """
        if not instruction or not output:
            logger.debug("Rejected Q&A pair: Empty instruction or output")
            return False
        
        instruction = str(instruction).strip()
        output = str(output).strip()
        
        # Check minimum length
        if len(instruction) < 10 or len(output) < 10:
            logger.debug(f"Rejected Q&A pair: Too short (instruction: {len(instruction)}, output: {len(output)})")
            return False
        
        # Check if it's echo of the prompt (common patterns)
        prompt_phrases = [
            "you are a helpful assistant",
            "generate exactly",
            "high-quality question-answer pairs",
            "requirements:",
            "each pair must have",
            "format as valid json",
            "return only a valid json"
        ]
        
        combined = (instruction + " " + output).lower()
        prompt_matches = sum(1 for phrase in prompt_phrases if phrase in combined)
        
        # If too many prompt phrases, it's likely echo
        if prompt_matches >= 3:
            logger.warning(f"Rejected Q&A pair: Too many prompt phrases detected (echo) - instruction: '{instruction[:60]}...'")
            return False
        
        # More lenient check for questions - accept imperative forms, statements that could be questions
        # Check if question is actually a question (more lenient)
        question_words = ["what", "who", "where", "when", "why", "how", "which", 
                         "czy", "co", "kto", "gdzie", "kiedy", "dlaczego", "jak",
                         "?", "pytanie"]
        question_indicators = any(word in instruction.lower() for word in question_words)
        
        # Also accept imperative/statement forms that are valid questions
        imperative_starters = ["explain", "describe", "tell", "list", "name", "define",
                              "wyjaśnij", "opisz", "powiedz", "wymień", "zdefiniuj",
                              "what is", "what are", "what does", "what do",
                              "co to", "czym jest", "jak działa"]
        
        starts_with_imperative = any(instruction.lower().startswith(word) for word in imperative_starters)
        
        # Accept if it has question indicators OR starts with imperative/question starter
        if not question_indicators and not starts_with_imperative:
            # Very lenient - accept if it contains any of the original text's key terms
            # This handles cases where question might be phrased differently
            if original_text:
                # Extract key words from original text (simple heuristic)
                original_words = set(word.lower() for word in original_text.split() if len(word) > 4)
                instruction_words = set(word.lower() for word in instruction.split())
                # If instruction shares significant words with original, it's probably valid
                if len(original_words.intersection(instruction_words)) < 1:
                    logger.debug(f"Rejected Q&A pair: Doesn't look like a question and no keyword overlap - '{instruction[:60]}...'")
                    return False
            else:
                logger.debug(f"Rejected Q&A pair: Doesn't look like a question - '{instruction[:60]}...'")
                return False
        
        # Check if answer is too generic or empty (more lenient - at least 3 words)
        if len(output.split()) < 3:
            logger.debug(f"Rejected Q&A pair: Answer too short ({len(output.split())} words)")
            return False
        
        return True
    
    def _parse_qa_response(self, response_text: str, expected_pairs: int, original_chunk: str = "") -> List[Dict[str, str]]:
        """
        Parse Q&A pairs from model response.
        
        Args:
            response_text: Raw response from model
            expected_pairs: Expected number of pairs
            original_chunk: Original text chunk (for validation)
            
        Returns:
            List of Q&A pairs
        """
        qa_pairs = []
        
        if not response_text:
            logger.warning("Empty response text")
            return []
        
        # Check if response is just echo of prompt
        prompt_indicators = [
            "you are a helpful assistant",
            "generate exactly",
            "high-quality question-answer pairs",
            "text:",
            "requirements:",
            "format as valid json array"
        ]
        
        response_lower = response_text.lower()
        echo_score = sum(1 for indicator in prompt_indicators if indicator in response_lower)
        
        if echo_score >= 4:
            logger.warning(f"Response appears to be echo of prompt (detected {echo_score} indicators). Skipping.")
            return []
        
        logger.debug(f"Parsing response (first 500 chars): {response_text[:500]}")
        
        # Try multiple parsing strategies
        # Strategy 1: Find JSON array in response
        try:
            import re
            
            # Look for JSON array: [...]
            json_pattern = r'\[.*?\]'
            matches = re.findall(json_pattern, response_text, re.DOTALL)
            
            if matches:
                # Try the longest match (most likely to be complete)
                json_str = max(matches, key=len)
                pairs = json.loads(json_str)
                
                if isinstance(pairs, list):
                    for pair in pairs:
                        if isinstance(pair, dict):
                            # Handle different formats
                            instruction = pair.get("instruction") or pair.get("question") or pair.get("q")
                            output = pair.get("output") or pair.get("answer") or pair.get("a")
                            
                            if instruction and output:
                                # Validate Q&A pair before adding
                                if self._is_valid_qa_pair(instruction, output, original_chunk):
                                    qa_pairs.append({
                                        "instruction": str(instruction).strip(),
                                        "output": str(output).strip()
                                    })
                                else:
                                    logger.warning(f"Rejected invalid Q&A pair: instruction='{instruction[:80]}...', output='{output[:80]}...'")
                    
                    if qa_pairs:
                        logger.info(f"Successfully parsed {len(qa_pairs)} Q&A pairs from JSON array")
                        return qa_pairs[:expected_pairs]
            
            # Strategy 2: Try to find individual JSON objects
            json_obj_pattern = r'\{\s*"instruction"[^}]*"output"[^}]*\}'
            obj_matches = re.findall(json_obj_pattern, response_text, re.DOTALL)
            
            if obj_matches:
                for obj_str in obj_matches:
                    try:
                        pair = json.loads(obj_str)
                        instruction = pair.get("instruction") or pair.get("question")
                        output = pair.get("output") or pair.get("answer")
                        
                        if instruction and output:
                            # Validate Q&A pair before adding
                            if self._is_valid_qa_pair(instruction, output, original_chunk):
                                qa_pairs.append({
                                    "instruction": str(instruction).strip(),
                                    "output": str(output).strip()
                                })
                            else:
                                logger.warning(f"Rejected invalid Q&A pair (strategy 2): instruction='{instruction[:60]}...'")
                    except:
                        continue
                
                if qa_pairs:
                    logger.info(f"Successfully parsed {len(qa_pairs)} Q&A pairs from JSON objects")
                    return qa_pairs[:expected_pairs]
            
            # Strategy 3: Try direct JSON parse
            try:
                parsed = json.loads(response_text.strip())
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "instruction" in item and "output" in item:
                            instruction = str(item["instruction"]).strip()
                            output = str(item["output"]).strip()
                            # Validate Q&A pair before adding
                            if self._is_valid_qa_pair(instruction, output, original_chunk):
                                qa_pairs.append({
                                    "instruction": instruction,
                                    "output": output
                                })
                            else:
                                logger.warning(f"Rejected invalid Q&A pair (strategy 3): instruction='{instruction[:60]}...'")
                    if qa_pairs:
                        logger.info(f"Successfully parsed {len(qa_pairs)} Q&A pairs from direct JSON")
                        return qa_pairs[:expected_pairs]
            except:
                pass
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
        
        # Strategy 4: Fallback to manual extraction (for Q:/A: format)
        logger.warning("Failed to parse JSON, trying manual extraction")
        qa_pairs = self._extract_qa_manually(response_text)
        
        # Validate manual extraction results
        if qa_pairs:
            validated_pairs = []
            for pair in qa_pairs:
                # More lenient validation for TinyLlama output
                instruction = pair.get("instruction", "").strip()
                output = pair.get("output", "").strip()
                
                # Basic checks: not empty, minimum length, not echo
                if (len(instruction) >= 5 and len(output) >= 10 and 
                    instruction.lower() != output.lower()):
                    # Check for obvious echo phrases
                    combined = (instruction + " " + output).lower()
                    echo_phrases = ["question here", "answer here", "create", "format:", "json array"]
                    if not any(phrase in combined for phrase in echo_phrases):
                        validated_pairs.append({
                            "instruction": instruction,
                            "output": output
                        })
                        if len(validated_pairs) >= expected_pairs:
                            break
            qa_pairs = validated_pairs
        
        # If we still have no valid pairs, try a lenient fallback (but limit to expected_pairs)
        if not qa_pairs:
            logger.warning("No Q&A pairs found with standard parsing. Attempting lenient fallback...")
            qa_pairs = self._extract_qa_lenient_fallback(response_text, original_chunk)
            # Limit lenient fallback to expected_pairs
            qa_pairs = qa_pairs[:expected_pairs]
        
        return qa_pairs[:expected_pairs]
    
    def _extract_qa_lenient_fallback(self, response_text: str, original_chunk: str = "") -> List[Dict[str, str]]:
        """
        Fallback extraction with very lenient validation - only filters obvious echo/empty.
        Used when standard parsing rejects all pairs.
        
        Args:
            response_text: Raw response text
            original_chunk: Original chunk text
            
        Returns:
            List of Q&A pairs (with minimal validation)
        """
        qa_pairs = []
        
        try:
            import re
            import json
            
            # Try to find ANY JSON-like structures
            json_pattern = r'\[.*?\]'
            matches = re.findall(json_pattern, response_text, re.DOTALL)
            
            for json_str in matches:
                try:
                    pairs = json.loads(json_str)
                    if isinstance(pairs, list):
                        for pair in pairs:
                            if isinstance(pair, dict):
                                instruction = pair.get("instruction") or pair.get("question") or pair.get("q")
                                output = pair.get("output") or pair.get("answer") or pair.get("a")
                                
                                if instruction and output:
                                    instruction = str(instruction).strip()
                                    output = str(output).strip()
                                    
                                    # Very lenient validation - only check:
                                    # 1. Not empty
                                    # 2. Not obvious echo (check for prompt phrases)
                                    # 3. Minimum length (10 chars each - more strict)
                                    if len(instruction) >= 10 and len(output) >= 10:
                                        # Check for obvious echo
                                        combined = (instruction + " " + output).lower()
                                        echo_phrases = ["you are a helpful assistant", "generate exactly", 
                                                       "high-quality question-answer pairs", "format as valid json",
                                                       "return json", "json array", "question here", "answer here"]
                                        if not any(phrase in combined for phrase in echo_phrases):
                                            # Basic validation: instruction should not be identical to output
                                            if instruction.lower() != output.lower():
                                                qa_pairs.append({
                                                    "instruction": instruction,
                                                    "output": output
                                                })
                                                logger.info(f"Accepted Q&A pair via lenient fallback: '{instruction[:50]}...'")
                                                # Limit to prevent accepting too many pairs
                                                if len(qa_pairs) >= 10:  # Safety limit
                                                    break
                except:
                    continue
            
            if qa_pairs:
                logger.info(f"Lenient fallback extracted {len(qa_pairs)} Q&A pairs")
            
        except Exception as e:
            logger.debug(f"Lenient fallback extraction failed: {e}")
        
        return qa_pairs
    
    def _extract_qa_manually(self, text: str) -> List[Dict[str, str]]:
        """Fallback manual extraction of Q&A pairs - handles multiple formats."""
        qa_pairs = []
        
        # Look for Q: and A: patterns in various formats
        lines = text.split('\n')
        current_q = None
        current_a = []
        
        for line in lines:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            
            line_lower = line.lower()
            
            # Detect question patterns (multiple formats)
            # Format 1: "1. Q: question" or "1. question"
            # Format 2: "Q: question" or "Question: question"
            # Format 3: "- Q: question" or "- question"
            is_question = False
            question_text = None
            
            # Check for numbered format: "1. Q: ..." or "1. ..." or "1. Q: ... A: ..."
            # Also handle "Question 1:" format
            if line_lower and line_lower[0].isdigit() and '.' in line:
                parts = line.split('.', 1)
                if len(parts) == 2:
                    rest = parts[1].strip()
                    
                    # Check for format "1. Q: question A: answer" (both in one line)
                    if 'Q:' in rest and 'A:' in rest:
                        q_parts = rest.split('Q:', 1)
                        if len(q_parts) == 2:
                            qa_part = q_parts[1].strip()
                            if 'A:' in qa_part:
                                a_parts = qa_part.split('A:', 1)
                                if len(a_parts) == 2:
                                    question_text = a_parts[0].strip()
                                    answer_text = a_parts[1].strip()
                                    # Remove "Answer:" prefix if present
                                    if answer_text.lower().startswith('answer:'):
                                        answer_text = answer_text.split(':', 1)[1].strip()
                                    
                                    if question_text and answer_text and len(answer_text) >= 10:
                                        # Save previous pair if exists
                                        if current_q and current_a:
                                            prev_answer = ' '.join(current_a).strip()
                                            if len(prev_answer) >= 10:
                                                qa_pairs.append({
                                                    "instruction": current_q,
                                                    "output": prev_answer
                                                })
                                        # Add current pair
                                        qa_pairs.append({
                                            "instruction": question_text,
                                            "output": answer_text
                                        })
                                        current_q = None
                                        current_a = []
                                        continue
                    
                    # Check if it has Q: or question marker
                    if rest.lower().startswith('q:') or rest.lower().startswith('question:'):
                        question_text = rest.split(':', 1)[1].strip() if ':' in rest else rest
                        is_question = True
                    # Check if it contains embedded Q: pattern (e.g., "question Q: ...")
                    elif 'Q:' in rest or 'q:' in rest:
                        # Extract question after Q:
                        if 'Q:' in rest:
                            q_parts = rest.split('Q:', 1)
                            if len(q_parts) == 2:
                                question_text = q_parts[1].strip()
                                is_question = True
                        elif 'q:' in rest:
                            q_parts = rest.split('q:', 1)
                            if len(q_parts) == 2:
                                question_text = q_parts[1].strip()
                                is_question = True
                    # Check if it's just a question without Q: prefix
                    elif rest and not rest.lower().startswith('a:') and not rest.lower().startswith('answer:'):
                        # If it ends with '?' or starts with question word, it's likely a question
                        if rest.endswith('?') or any(rest.lower().startswith(word + ' ') for word in 
                                                   ['how', 'what', 'why', 'when', 'where', 'which', 'who', 'do', 'does', 'did', 'are', 'is']):
                            question_text = rest
                            is_question = True
            
            # Check for "Question N:" format (e.g., "Question 1:", "Question 2:")
            elif line_lower.startswith('question ') and ':' in line:
                # Extract number and question text
                # Format: "Question 1: question text" or "Question 1: question text Answer: answer text"
                colon_pos = line.find(':')
                if colon_pos > 0:
                    rest = line[colon_pos + 1:].strip()
                    # Check if answer is in the same line
                    if 'Answer:' in rest or 'answer:' in rest or rest.lower().endswith('answer:'):
                        # Handle case where "Answer:" is at the end (answer in next line)
                        if rest.lower().endswith('answer:') or rest.lower().endswith('answer'):
                            # Answer will be in next line(s)
                            question_text = rest.rstrip('Answer:').rstrip('answer:').strip()
                            is_question = True
                        else:
                            # Split by Answer: or answer:
                            if 'Answer:' in rest:
                                parts = rest.split('Answer:', 1)
                            else:
                                parts = rest.split('answer:', 1)
                            if len(parts) == 2:
                                question_text = parts[0].strip()
                                answer_text = parts[1].strip()
                                # Remove "Answer:" prefix if present
                                if answer_text.lower().startswith('answer:'):
                                    answer_text = answer_text.split(':', 1)[1].strip()
                                
                                if question_text and answer_text and len(answer_text) >= 10:
                                    # Save previous pair if exists
                                    if current_q and current_a:
                                        prev_answer = ' '.join(current_a).strip()
                                        if len(prev_answer) >= 10:
                                            qa_pairs.append({
                                                "instruction": current_q,
                                                "output": prev_answer
                                            })
                                    # Add current pair
                                    qa_pairs.append({
                                        "instruction": question_text,
                                        "output": answer_text
                                    })
                                    current_q = None
                                    current_a = []
                                    continue
                    else:
                        # Just question, answer will be in next line(s)
                        question_text = rest
                        is_question = True
            
            # Check for Q: or Question: prefix
            elif line_lower.startswith('q:') or (line_lower.startswith('question:') and not line_lower.startswith('question ')):
                question_text = line.split(':', 1)[1].strip() if ':' in line else line
                is_question = True
            
            # Check for dash format: "- Q: ..." or "- ..."
            elif line.startswith('-') and len(line) > 2:
                rest = line[1:].strip()
                if rest.lower().startswith('q:') or rest.lower().startswith('question:'):
                    question_text = rest.split(':', 1)[1].strip() if ':' in rest else rest
                    is_question = True
                elif rest and not rest.lower().startswith('a:'):
                    # Might be a question without Q: prefix
                    question_text = rest
                    is_question = True
            
            if is_question and question_text:
                # Save previous pair if exists
                if current_q and current_a:
                    answer_text = ' '.join(current_a).strip()
                    if len(answer_text) >= 10:  # Minimum answer length
                        qa_pairs.append({
                            "instruction": current_q,
                            "output": answer_text
                        })
                # Start new question
                current_q = question_text
                current_a = []
                continue
            
            # Detect answer patterns
            if current_q:
                # Format 1: "A: answer" or "Answer: answer" (standalone line)
                # Also handle indented "   A: answer" format
                line_stripped = line.strip()
                if line_stripped.lower().startswith('a:') or line_stripped.lower().startswith('answer:'):
                    answer_part = line_stripped.split(':', 1)[1].strip() if ':' in line_stripped else line_stripped.strip()
                    if answer_part:
                        current_a.append(answer_part)
                        continue  # Don't process further
                # Format 2: Numbered answer "1. A: ..." or "2. ..."
                elif line_lower and line_lower[0].isdigit() and '.' in line:
                    parts = line.split('.', 1)
                    if len(parts) == 2:
                        rest = parts[1].strip()
                        # Check if it's an answer (starts with A: or just text after number)
                        if rest.lower().startswith('a:') or rest.lower().startswith('answer:'):
                            answer_part = rest.split(':', 1)[1].strip() if ':' in rest else rest
                            if answer_part:
                                current_a.append(answer_part)
                        elif rest and not rest.lower().startswith('q:'):
                            # If it's not a question, it might be an answer continuation
                            # But only if it doesn't look like a new numbered question
                            if not any(word in rest.lower() for word in ['how', 'what', 'why', 'when', 'where', 'which']):
                                current_a.append(rest)
                # Format 2b: Dash after numbered question (e.g., "1. Question\n- Answer")
                elif line.startswith('-') and len(line) > 2 and current_q:
                    # If we have a current question, dash line is likely the answer
                    rest = line[1:].strip()
                    # Remove quotes if present (e.g., '- "Answer text"')
                    if rest.startswith('"') and rest.endswith('"'):
                        rest = rest[1:-1].strip()
                    if rest:
                        current_a.append(rest)
                # Format 3: Dash format "- A: ..." or "- Answer: ..." or continuation
                elif line.startswith('-') and len(line) > 2:
                    rest = line[1:].strip()
                    # Handle "- Answer: ..." format (common in TinyLlama output)
                    if rest.lower().startswith('answer:'):
                        answer_part = rest.split(':', 1)[1].strip() if ':' in rest else rest
                        if answer_part:
                            current_a.append(answer_part)
                    elif rest.lower().startswith('a:'):
                        answer_part = rest.split(':', 1)[1].strip() if ':' in rest else rest
                        if answer_part:
                            current_a.append(answer_part)
                    elif rest:
                        # Continue answer if it doesn't look like a question
                        if not rest.lower().startswith('q:'):
                            current_a.append(rest)
                # Format 4: Answer embedded in line with "A: ..." pattern (e.g., "1. Q: question A: answer")
                elif 'A:' in line or 'Answer:' in line_lower:
                    # Extract answer part after A: or Answer:
                    if 'A:' in line:
                        parts = line.split('A:', 1)
                        if len(parts) == 2:
                            answer_text = parts[1].strip()
                            # Remove "Answer:" prefix if present
                            if answer_text.lower().startswith('answer:'):
                                answer_text = answer_text.split(':', 1)[1].strip()
                            if answer_text:
                                current_a.append(answer_text)
                    elif 'Answer:' in line_lower:
                        parts = line_lower.split('answer:', 1)
                        if len(parts) == 2:
                            answer_text = parts[1].strip()
                            # Remove another "Answer:" prefix if present
                            if answer_text.lower().startswith('answer:'):
                                answer_text = answer_text.split(':', 1)[1].strip()
                            if answer_text:
                                current_a.append(answer_text)
                # Format 5: Continue answer if not JSON-like and not a new question
                elif line and not line.startswith('[') and not line.startswith('{'):
                    # Don't continue if it looks like a new question
                    if not (line_lower.startswith('q:') or line_lower.startswith('question:') or 
                           (line_lower and line_lower[0].isdigit() and '.' in line)):
                        # Also check if line contains question words at start (likely new question)
                        question_starters = ['how', 'what', 'why', 'when', 'where', 'which', 'who']
                        if not any(line_lower.startswith(starter + ' ') for starter in question_starters):
                            current_a.append(line)
        
        # Save last pair
        if current_q and current_a:
            answer_text = ' '.join(current_a).strip()
            if len(answer_text) >= 10:  # Minimum answer length
                qa_pairs.append({
                    "instruction": current_q,
                    "output": answer_text
                })
        
        # Debug: log what we found
        if qa_pairs:
            logger.debug(f"Manual extraction found {len(qa_pairs)} Q&A pairs")
        else:
            logger.debug(f"Manual extraction found no pairs. Response preview: {text[:300]}")
        
        return qa_pairs
    
    def generate_from_chunks(
        self,
        text_chunks: List[str],
        user_id: str = "unknown",
        num_pairs_per_chunk: int = 3
    ) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from multiple text chunks.
        
        Args:
            text_chunks: List of text chunks
            user_id: User ID for tracking
            num_pairs_per_chunk: Number of Q&A pairs per chunk
            
        Returns:
            List of all Q&A pairs in Alpaca format
        """
        all_qa_pairs = []
        
        logger.info(f"Generating Q&A pairs from {len(text_chunks)} chunks for user {user_id}")
        
        valid_chunks = 0
        skipped_chunks = 0
        
        for i, chunk in enumerate(text_chunks):
            logger.info(f"Processing chunk {i+1}/{len(text_chunks)}")
            
            # Validate chunk before processing
            if not self._is_chunk_valid(chunk):
                logger.debug(f"Skipping chunk {i+1}: Invalid or low-quality content (length: {len(chunk)} chars)")
                skipped_chunks += 1
                continue
            
            valid_chunks += 1
            qa_pairs = self.generate_qa_pairs(chunk, num_pairs_per_chunk)
            
            if qa_pairs:
                all_qa_pairs.extend(qa_pairs)
                logger.info(f"Generated {len(qa_pairs)} Q&A pairs from chunk {i+1}")
            else:
                logger.warning(f"Failed to generate Q&A pairs from chunk {i+1} (valid chunk but generation failed)")
                # Log the chunk length for debugging
                logger.debug(f"Chunk {i+1} length: {len(chunk)} chars")
            
            # Avoid aggressive back-to-back requests with Ollama fallback,
            # but keep throughput high for local processing.
            if not self.mlx_generator:
                time.sleep(0.25)
        
        logger.info(f"Q&A generation complete: {valid_chunks} valid chunks processed, {skipped_chunks} skipped")
        logger.info(f"Total Q&A pairs generated: {len(all_qa_pairs)}")
        return all_qa_pairs

    def generate_qa_from_chunks(
        self,
        text_chunks: List[str],
        max_pairs: Optional[int] = None,
        user_id: str = "unknown"
    ) -> List[Dict[str, str]]:
        """
        Backward-compatible alias used by older GUI call sites.
        """
        pairs = self.generate_from_chunks(
            text_chunks=text_chunks,
            user_id=user_id,
            num_pairs_per_chunk=3
        )
        if max_pairs is not None:
            return pairs[:max_pairs]
        return pairs
    
    def save_to_jsonl(self, qa_pairs: List[Dict[str, str]], output_path: str):
        """
        Save Q&A pairs to JSONL file (Alpaca format).
        
        Args:
            qa_pairs: List of Q&A pairs
            output_path: Path to output JSONL file
        """
        with open(output_path, 'w') as f:
            for pair in qa_pairs:
                # Add input field (empty for Alpaca format)
                record = {
                    "instruction": pair.get("instruction", ""),
                    "input": "",  # Empty for simple Q&A
                    "output": pair.get("output", "")
                }
                f.write(json.dumps(record) + '\n')
        
        logger.info(f"Saved {len(qa_pairs)} Q&A pairs to {output_path}")
    
    def generate_synthetic_qa_via_runpod(
        self,
        pdf_path: str,
        target_samples: int = 100,
        encryption_key_hex: Optional[str] = None
    ) -> Tuple[List[Dict[str, str]], str]:
        """
        Generate high-quality Q&A pairs using cloud-based RunPod endpoint (encrypted flow).
        
        This maintains end-to-end encryption:
        1. Encrypt PDF client-side
        2. Send encrypted PDF + key to RunPod
        3. RunPod decrypts, generates Q&A, encrypts results
        4. Return encrypted dataset + encryption key
        
        Performance (with vLLM backend):
        - ~2-5 minutes for 100 samples
        - Quality > quantity for adapter training
        
        Args:
            pdf_path: Path to PDF file
            target_samples: Target number of Q&A pairs (default: 100)
            encryption_key_hex: Optional encryption key (generates new if None)
            
        Returns:
            Tuple of (qa_pairs_list, encryption_key_hex)
        """
        import secrets
        import base64
        
        # Import encryption (use same pattern as training_manager)
        try:
            from Crypto.Cipher import ChaCha20_Poly1305
            from Crypto.Random import get_random_bytes
            CRYPTO_BACKEND_LOCAL = "pycryptodome"
        except ImportError:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
                CRYPTO_BACKEND_LOCAL = "cryptography"
            except ImportError:
                raise RuntimeError("No encryption library available. Install: pip install pycryptodome")
        
        # Generate encryption key if not provided
        if not encryption_key_hex:
            encryption_key = secrets.token_bytes(32)
            encryption_key_hex = encryption_key.hex()
        else:
            encryption_key = bytes.fromhex(encryption_key_hex)
        
        # Read and encrypt PDF
        logger.info(f"Reading PDF: {pdf_path}")
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        logger.info(f"Encrypting PDF ({len(pdf_bytes)} bytes)...")
        
        # Encrypt PDF using XChaCha20-Poly1305 (24-byte nonce) or ChaCha20Poly1305 (12-byte nonce)
        if CRYPTO_BACKEND_LOCAL == "pycryptodome":
            nonce = get_random_bytes(24)  # XChaCha20-Poly1305 uses 24-byte nonce
            cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(pdf_bytes)
        else:
            nonce = secrets.token_bytes(12)  # ChaCha20Poly1305 uses 12-byte nonce
            cipher = ChaCha20Poly1305(encryption_key)
            ciphertext_with_tag = cipher.encrypt(nonce, pdf_bytes, None)
            ciphertext = ciphertext_with_tag[:-16]
            tag = ciphertext_with_tag[-16:]
        
        encrypted_pdf = json.dumps({
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8')
        })
        
        logger.info(f"✓ Encrypted PDF ({len(encrypted_pdf)} bytes)")
        
        # Get synthetic generation endpoint (separate from training/inference)
        # Uses RUNPOD_QA_ENDPOINT_ID environment variable if set
        synthetic_endpoint_id = os.getenv(SYNTHETIC_QA_ENDPOINT_ID_ENV)
        
        if not synthetic_endpoint_id:
            raise RuntimeError(
                f"QA generation endpoint not configured. "
                f"Set {SYNTHETIC_QA_ENDPOINT_ID_ENV} environment variable to configure the QA generation endpoint."
            )
        
        # API key for QA generation endpoint
        # Default behavior: RUNPOD_QA_API_KEY defaults to RUNPOD_API_KEY if not set
        # This ensures QA endpoint works by default when RUNPOD_API_KEY is set
        runpod_api_key = os.getenv("RUNPOD_API_KEY")
        qa_api_key = os.getenv(SYNTHETIC_QA_API_KEY_ENV)
        
        # Set RUNPOD_QA_API_KEY to RUNPOD_API_KEY by default if not explicitly set
        # This ensures the QA endpoint is used by default
        if not qa_api_key and runpod_api_key:
            os.environ[SYNTHETIC_QA_API_KEY_ENV] = runpod_api_key
            qa_api_key = runpod_api_key
            logger.debug(f"Set {SYNTHETIC_QA_API_KEY_ENV} to RUNPOD_API_KEY by default")
        
        # Priority: 1) RUNPOD_QA_API_KEY env var (now set by default), 2) constructor api_key, 3) RUNPOD_API_KEY env var
        api_key = qa_api_key or self.api_key or runpod_api_key
        
        if not api_key:
            raise RuntimeError(
                "RunPod API key not configured for QA generation. "
                f"Set {SYNTHETIC_QA_API_KEY_ENV} or RUNPOD_API_KEY environment variable, "
                "or pass runpod_api_key to QAGenerator constructor."
            )
        
        # Log which API key source is being used (for debugging)
        if qa_api_key and qa_api_key == runpod_api_key:
            logger.debug(f"Using RUNPOD_API_KEY (default) for QA generation endpoint via {SYNTHETIC_QA_API_KEY_ENV}")
        elif qa_api_key:
            logger.debug(f"Using {SYNTHETIC_QA_API_KEY_ENV} for QA generation endpoint")
        elif runpod_api_key:
            logger.debug("Using RUNPOD_API_KEY for QA generation endpoint")
        
        # Send to RunPod synthetic generation endpoint
        # Using QA generation endpoint (separate from inference endpoint)
        logger.info(f"Using QA generation endpoint: {synthetic_endpoint_id}")
        logger.info(f"Sending to RunPod endpoint {synthetic_endpoint_id} for generation...")
        logger.info(f"Target: {target_samples} Q&A pairs")
        
        payload = {
            "input": {
                "encrypted_pdf": encrypted_pdf,
                "encryption_key_hex": encryption_key_hex,
                "target_samples": target_samples
            }
        }
        
        runpod_url = f"https://api.runpod.ai/v2/{synthetic_endpoint_id}/run"
        
        try:
            response = requests.post(
                runpod_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=3600  # 1 hour timeout (generation can take 15-30 minutes)
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Wait for completion (polling)
            job_id = result.get('id')
            if not job_id:
                raise RuntimeError("No job ID returned from RunPod")
            
            logger.info(f"Job submitted: {job_id}. Waiting for completion...")
            
            # Poll for completion
            max_wait = 3600  # 1 hour
            poll_interval = 5  # Check every 5 seconds
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                status_response = requests.get(
                    f"https://api.runpod.ai/v2/{synthetic_endpoint_id}/status/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=30
                )
                
                status_data = status_response.json()
                status = status_data.get("status")
                
                if status == "COMPLETED":
                    output = status_data.get("output", {})
                    if output.get("status") == "success":
                        # Decrypt results
                        logger.info("Decrypting results...")
                        encrypted_dataset = output.get("encrypted_dataset")
                        
                        encrypted_package = json.loads(encrypted_dataset)
                        ciphertext = base64.b64decode(encrypted_package['ciphertext'])
                        tag = base64.b64decode(encrypted_package['tag'])
                        nonce = base64.b64decode(encrypted_package['nonce'])
                        
                        # Handle different nonce sizes from server
                        # Server may use PyCryptodome (24-byte) or cryptography (12-byte)
                        if len(nonce) == 24:
                            # XChaCha20-Poly1305 with 24-byte nonce - requires PyCryptodome
                            try:
                                from Crypto.Cipher import ChaCha20_Poly1305 as PyCryptoChaCha
                                cipher = PyCryptoChaCha.new(key=encryption_key, nonce=nonce)
                                plaintext = cipher.decrypt_and_verify(ciphertext, tag)
                            except ImportError:
                                raise RuntimeError("Server used XChaCha20 (24-byte nonce) but PyCryptodome not installed")
                        elif len(nonce) == 12:
                            # Standard ChaCha20-Poly1305 with 12-byte nonce
                            if CRYPTO_BACKEND_LOCAL == "pycryptodome":
                                cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
                                plaintext = cipher.decrypt_and_verify(ciphertext, tag)
                            else:
                                cipher = ChaCha20Poly1305(encryption_key)
                                plaintext = cipher.decrypt(nonce, ciphertext + tag, None)
                        else:
                            raise RuntimeError(f"Unexpected nonce size: {len(nonce)} bytes")
                        
                        qa_pairs = json.loads(plaintext.decode('utf-8'))
                        
                        logger.info(f"✓ Generated {len(qa_pairs)} Q&A pairs")
                        return qa_pairs, encryption_key_hex
                    else:
                        raise RuntimeError(f"Generation failed: {output.get('error')}")
                
                elif status == "FAILED":
                    error_msg = status_data.get("error", "Unknown error")
                    raise RuntimeError(f"RunPod job failed: {error_msg}")
                
                # Still processing
                time.sleep(poll_interval)
                elapsed = int(time.time() - start_time)
                if elapsed % 30 == 0:  # Log every 30 seconds
                    logger.info(f"Generation in progress... ({elapsed}s elapsed)")
            
            raise TimeoutError("Generation timed out after 1 hour")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to communicate with RunPod: {e}")

