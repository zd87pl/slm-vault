"""
PDF processing service for extracting text and metadata from PDF files.

Features:
- Text extraction using PyPDF2 (for text-based PDFs)
- OCR fallback using Ollama Vision models (local, for scanned PDFs)
- Optional SmolDocling OCR (Apple Silicon only, ~500MB vs 1-2GB)
- Intelligent chunking for training
- Metadata extraction (page count, title, author)
- Automatic language detection and preservation
"""

import logging
import os
import base64
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
import PyPDF2
import requests

# Try to import SmolDocling (MLX - Apple Silicon only)
SMOLDOCLING_AVAILABLE = False
try:
    import sys
    if sys.version_info >= (3, 12):  # SmolDocling requires Python 3.12+
        from mlx_vlm import load as mlx_load, generate as mlx_generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config as mlx_load_config, stream_generate
        from docling_core.types.doc import DocTagsDocument, DoclingDocument
        from PIL import Image
        SMOLDOCLING_AVAILABLE = True
except ImportError:
    SMOLDOCLING_AVAILABLE = False

# Import ollama_setup - handle both relative and absolute imports
try:
    from .ollama_setup import OllamaSetup
except (ImportError, ValueError):
    # Fallback: try importing from same directory
    import sys
    from pathlib import Path as PathLib
    ollama_setup_path = PathLib(__file__).parent / "ollama_setup.py"
    if ollama_setup_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("ollama_setup", ollama_setup_path)
        ollama_setup_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ollama_setup_module)
        OllamaSetup = ollama_setup_module.OllamaSetup
    else:
        raise ImportError("Could not import ollama_setup")

logger = logging.getLogger(__name__)


def _is_apple_silicon() -> bool:
    """Check if running on Apple Silicon Mac."""
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=2
        )
        return "Apple" in result.stdout
    except Exception:
        return False


def _install_smoldocling_dependencies(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    Install SmolDocling dependencies automatically.
    
    Args:
        progress_callback: Optional callback for progress updates
        
    Returns:
        True if installation successful
    """
    try:
        import sys
        
        packages = [
            "mlx>=0.18.0",
            "mlx-vlm>=0.1.0", 
            "docling-core>=1.0.0",
        ]
        
        if progress_callback:
            progress_callback("Instalowanie zależności SmolDocling...")
        
        logger.info("Installing SmolDocling dependencies...")
        
        # Check if we're in a virtual environment
        in_venv = (hasattr(sys, 'real_prefix') or 
                  (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        
        # Determine pip flags based on environment
        # Use --user for system Python, normal install for venv
        pip_flags = []
        if not in_venv:
            # Try --user first (safer)
            pip_flags = ["--user"]
        
        for package in packages:
            if progress_callback:
                progress_callback(f"Instalowanie {package}...")
            logger.info(f"Installing {package}...")
            
            # Try installation with initial flags
            install_cmd = [sys.executable, "-m", "pip", "install"] + pip_flags + [package]
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            # If --user failed with externally-managed-environment, try --break-system-packages
            if result.returncode != 0 and "externally-managed-environment" in result.stderr:
                logger.warning(f"User install failed, trying with --break-system-packages flag...")
                install_cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", package]
                result = subprocess.run(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600
                )
            
            if result.returncode != 0:
                logger.warning(f"Failed to install {package}: {result.stderr}")
                # Continue with other packages
        
        # If we used --user, ensure user site-packages is in sys.path
        if not in_venv and pip_flags:
            import site
            # Add user site-packages to sys.path if not already there
            user_site = site.getusersitepackages()
            if user_site and user_site not in sys.path:
                sys.path.insert(0, user_site)
                logger.info(f"Added user site-packages to path: {user_site}")
        
        # Verify installation
        try:
            from mlx_vlm import load as mlx_load
            from docling_core.types.doc import DocTagsDocument
            logger.info("SmolDocling dependencies installed successfully")
            if progress_callback:
                progress_callback("Zależności SmolDocling zainstalowane")
            return True
        except ImportError as e:
            logger.error(f"SmolDocling dependencies verification failed: {e}")
            logger.error(f"Python path: {sys.path}")
            if progress_callback:
                progress_callback("Weryfikacja zależności nie powiodła się")
            return False
            
    except Exception as e:
        logger.error(f"Error installing SmolDocling dependencies: {e}")
        if progress_callback:
            progress_callback(f"Błąd instalacji: {str(e)}")
        return False


class PDFProcessor:
    """
    Service for processing PDF files into chunks suitable for training.
    
    Supports both text-based PDFs (via PyPDF2) and scanned PDFs (via Ollama OCR).
    """
    
    def __init__(self, ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None, 
                 auto_setup: bool = True, progress_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize PDF processor.
        
        Args:
            ollama_base_url: Optional Ollama base URL. Defaults to http://localhost:11434
            ollama_model: Optional Ollama vision model name. Defaults to 'llama3.2-vision'
            auto_setup: Automatically install/setup OCR if not available. Defaults to True.
            progress_callback: Optional callback function(status_message) for setup progress updates
        """
        self.ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_OCR_MODEL", "llama3.2-vision:1b")
        self.ollama_setup = OllamaSetup(base_url=self.ollama_base_url, model=self.ollama_model)
        
        # Check if SmolDocling should be preferred (Apple Silicon)
        self.prefer_smoldocling = (
            _is_apple_silicon() and 
            os.getenv("ENCLAVE_USE_SMOLDOCLING", "true").lower() == "true"
        )
        
        # Initialize SmolDocling if preferred
        self.smoldocling_available = False
        self.smoldocling_model = None
        self.smoldocling_processor = None
        self.smoldocling_config = None
        
        if self.prefer_smoldocling:
            # Try to use SmolDocling if available
            if SMOLDOCLING_AVAILABLE:
                try:
                    logger.info("Initializing SmolDocling OCR (Apple Silicon optimized)...")
                    model_path = "ds4sd/SmolDocling-256M-preview-mlx-bf16"
                    self.smoldocling_model, self.smoldocling_processor = mlx_load(model_path)
                    self.smoldocling_config = mlx_load_config(model_path)
                    self.smoldocling_available = True
                    logger.info("SmolDocling OCR initialized successfully (~500MB model)")
                except Exception as e:
                    logger.warning(f"SmolDocling initialization failed: {e}. Attempting dependency installation...")
                    self.smoldocling_available = False
                    
                    # Try to install dependencies automatically if auto_setup is enabled
                    if auto_setup:
                        if _install_smoldocling_dependencies(progress_callback=progress_callback):
                            # Retry initialization after installing dependencies
                            try:
                                # Reload imports after installation
                                from mlx_vlm import load as mlx_load
                                from mlx_vlm.utils import load_config as mlx_load_config
                                
                                logger.info("Retrying SmolDocling initialization...")
                                model_path = "ds4sd/SmolDocling-256M-preview-mlx-bf16"
                                self.smoldocling_model, self.smoldocling_processor = mlx_load(model_path)
                                self.smoldocling_config = mlx_load_config(model_path)
                                self.smoldocling_available = True
                                logger.info("SmolDocling OCR initialized successfully after dependency installation")
                            except Exception as e2:
                                logger.error(f"SmolDocling initialization failed after dependency installation: {e2}")
                                self.smoldocling_available = False
            elif auto_setup:
                # Dependencies not available, try to install them
                logger.info("SmolDocling dependencies not found, attempting automatic installation...")
                if _install_smoldocling_dependencies(progress_callback=progress_callback):
                    # Try importing again
                    try:
                        from mlx_vlm import load as mlx_load
                        from mlx_vlm.utils import load_config as mlx_load_config
                        from docling_core.types.doc import DocTagsDocument, DoclingDocument
                        from PIL import Image
                        
                        logger.info("Retrying SmolDocling initialization...")
                        model_path = "ds4sd/SmolDocling-256M-preview-mlx-bf16"
                        self.smoldocling_model, self.smoldocling_processor = mlx_load(model_path)
                        self.smoldocling_config = mlx_load_config(model_path)
                        self.smoldocling_available = True
                        logger.info("SmolDocling OCR initialized successfully (~500MB model)")
                    except Exception as e:
                        logger.warning(f"SmolDocling initialization failed after installation: {e}")
                        self.smoldocling_available = False
        
        # Only setup Ollama if SmolDocling is not available/not preferred
        if not self.smoldocling_available:
            # Test Ollama connection
            self.ollama_available = self._test_ollama_connection()
            
            # Auto-setup Ollama only if SmolDocling is not preferred or not available
            if not self.ollama_available and auto_setup and not self.prefer_smoldocling:
                logger.info("Ollama OCR not available, attempting automatic setup...")
                success, message = self.ollama_setup.setup_ollama(progress_callback=progress_callback)
                if success:
                    self.ollama_available = self._test_ollama_connection()
                    logger.info(f"Ollama OCR setup successful: {message}")
                else:
                    logger.warning(f"Ollama OCR setup failed: {message}")
        else:
            # Skip Ollama setup entirely if SmolDocling is available
            self.ollama_available = False
        
        if self.smoldocling_available:
            logger.info(f"SmolDocling OCR available (~500MB model, Apple Silicon optimized)")
        elif self.ollama_available:
            logger.info(f"Ollama OCR available at {self.ollama_base_url} with model {self.ollama_model}")
        else:
            if self.prefer_smoldocling:
                logger.info("OCR not available. SmolDocling setup failed. Check logs for details.")
            else:
                logger.info(f"OCR not available. Install manually: ollama pull {self.ollama_model}")
    
    def _test_ollama_connection(self) -> bool:
        """Test if Ollama is running and accessible."""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                # Check if the model is available
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                # Check if our model or any vision model is available
                has_model = any(self.ollama_model in name or "vision" in name.lower() or "llava" in name.lower() 
                               for name in model_names)
                if not has_model:
                    logger.warning(f"Ollama is running but model '{self.ollama_model}' not found. Available models: {model_names}")
                    logger.warning(f"Install with: ollama pull {self.ollama_model}")
                return has_model
            return False
        except Exception as e:
            logger.debug(f"Ollama connection test failed: {e}")
            return False
    
    def _is_text_quality_good(self, text: str) -> bool:
        """
        Check if extracted text quality is good enough.
        
        Args:
            text: Extracted text
            
        Returns:
            True if text quality is acceptable
        """
        if not text or len(text.strip()) < 50:
            return False
        
        # Check for high proportion of special characters (OCR artifacts)
        special_chars = '!\"#$%&*()+=[]{}|;:,.<>?/@\\^_`~'
        if len(text) > 100:
            sample = text[:500] if len(text) > 500 else text
            special_char_ratio = sum(1 for c in sample if c in special_chars) / len(sample)
            if special_char_ratio > 0.15:  # More than 15% special chars suggests OCR artifacts
                return False
        
        # Check for meaningful words (at least some Polish/English words)
        words = text.split()
        if len(words) < 10:
            return False
        
        return True
    
    def _convert_pdf_to_images(self, pdf_path: str) -> List[bytes]:
        """
        Convert PDF pages to images for OCR.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of image bytes (one per page) in JPEG format
        """
        try:
            from pdf2image import convert_from_path
            import io
            
            images = convert_from_path(pdf_path, dpi=300)
            image_bytes_list = []
            
            for img in images:
                # Convert PIL Image to JPEG bytes
                img_buffer = io.BytesIO()
                img.save(img_buffer, format='JPEG', quality=95)
                image_bytes_list.append(img_buffer.getvalue())
            
            return image_bytes_list
            
        except ImportError:
            logger.warning("pdf2image not installed. Install with: pip install pdf2image")
            logger.warning("Also requires poppler: brew install poppler (macOS) or apt-get install poppler-utils (Linux)")
            return []
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            return []
    
    def _extract_text_with_smoldocling(self, pdf_path: str, progress_callback: Optional[Callable[[str], None]] = None) -> str:
        """
        Extract text from PDF using SmolDocling MLX model (Apple Silicon only).
        
        Args:
            pdf_path: Path to PDF file
            progress_callback: Optional callback for progress updates
            
        Returns:
            Extracted text (converted from DocTags to plain text)
        """
        if not self.smoldocling_available:
            logger.warning("SmolDocling not available")
            return ""
        
        try:
            # Convert PDF pages to images
            logger.info("Converting PDF pages to images for SmolDocling OCR...")
            image_bytes_list = self._convert_pdf_to_images(pdf_path)
            
            if not image_bytes_list:
                logger.warning("Could not convert PDF pages to images")
                return ""
            
            logger.info(f"Processing {len(image_bytes_list)} pages with SmolDocling OCR...")
            
            full_text = ""
            prompt = "Convert this page to docling."
            
            for page_num, image_bytes in enumerate(image_bytes_list):
                try:
                    if progress_callback:
                        progress_callback(f"Processing page {page_num + 1}/{len(image_bytes_list)} with SmolDocling...")
                    
                    # Convert bytes to PIL Image
                    from io import BytesIO
                    pil_image = Image.open(BytesIO(image_bytes))
                    
                    # Apply chat template
                    formatted_prompt = apply_chat_template(
                        self.smoldocling_processor,
                        self.smoldocling_config,
                        prompt,
                        num_images=1
                    )
                    
                    # Generate DocTags output
                    doctags_output = ""
                    for token in stream_generate(
                        self.smoldocling_model,
                        self.smoldocling_processor,
                        formatted_prompt,
                        [pil_image],
                        max_tokens=4096,
                        verbose=False
                    ):
                        doctags_output += token.text
                        if "</doctag>" in token.text:
                            break
                    
                    # Convert DocTags to DoclingDocument and then to Markdown/plain text
                    try:
                        doctags_doc = DocTagsDocument.from_doctags_and_image_pairs([doctags_output], [pil_image])
                        doc = DoclingDocument.load_from_doctags(doctags_doc, document_name=f"Page{page_num + 1}")
                        
                        # Export as Markdown (plain text format)
                        page_text = doc.export_to_markdown()
                        
                        if page_text:
                            full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
                            full_text += page_text
                            logger.info(f"Extracted text from page {page_num + 1} ({len(page_text)} chars)")
                    except Exception as e:
                        logger.warning(f"Failed to parse DocTags for page {page_num + 1}: {e}")
                        # Fallback: try to extract plain text from DocTags XML
                        import re
                        # Simple extraction of text content from DocTags
                        text_content = re.sub(r'<[^>]+>', '', doctags_output)
                        if text_content.strip():
                            full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
                            full_text += text_content.strip()
                        
                except Exception as e:
                    logger.error(f"Error processing page {page_num + 1} with SmolDocling: {e}")
                    continue
            
            logger.info(f"SmolDocling OCR extraction complete: {len(full_text)} chars total")
            return full_text
            
        except Exception as e:
            logger.error(f"Error in SmolDocling OCR extraction: {e}")
            return ""
    
    def _extract_text_with_ollama_ocr(self, pdf_path: str, progress_callback: Optional[Callable[[str], None]] = None) -> str:
        """
        Extract text from PDF using Ollama Vision model for OCR (local).
        
        Args:
            pdf_path: Path to PDF file
            progress_callback: Optional callback for progress updates
            
        Returns:
            Extracted text
        """
        # Try to setup Ollama if not available (one more attempt)
        if not self.ollama_available:
            logger.info("Ollama not available, attempting setup...")
            success, message = self.ollama_setup.setup_ollama(progress_callback=progress_callback)
            if success:
                self.ollama_available = self._test_ollama_connection()
            else:
                logger.warning(f"Ollama setup failed: {message}")
                return ""
        
        try:
            # Convert PDF pages to images
            logger.info("Converting PDF pages to images for OCR...")
            image_bytes_list = self._convert_pdf_to_images(pdf_path)
            
            if not image_bytes_list:
                logger.warning("Could not convert PDF pages to images")
                return ""
            
            logger.info(f"Processing {len(image_bytes_list)} pages with Ollama OCR...")
            
            full_text = ""
            for page_num, image_bytes in enumerate(image_bytes_list):
                try:
                    # Encode image as base64
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    
                    # Prepare request for Ollama Vision API
                    # Ollama uses a simple API format for vision models
                    payload = {
                        "model": self.ollama_model,
                        "prompt": "Extract all text from this image. Preserve the original language (Polish if present). Include all medical terminology accurately. Return only the extracted text, no additional commentary or formatting.",
                        "images": [image_base64],
                        "stream": False
                    }
                    
                    response = requests.post(
                        f"{self.ollama_base_url}/api/generate",
                        json=payload,
                        timeout=180  # OCR can take time, especially for large images
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        page_text = result.get("response", "").strip()
                        if page_text:
                            full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
                            full_text += page_text
                            logger.info(f"Extracted text from page {page_num + 1} ({len(page_text)} chars)")
                    else:
                        logger.error(f"Ollama OCR API error: {response.status_code} - {response.text}")
                        
                except Exception as e:
                    logger.error(f"Error processing page {page_num + 1} with OCR: {e}")
                    continue
            
            logger.info(f"OCR extraction complete: {len(full_text)} chars total")
            return full_text
            
        except Exception as e:
            logger.error(f"Error in Ollama OCR extraction: {e}")
            return ""
    
    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract text and metadata from PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with:
            - text_chunks: List of text chunks (500-1000 tokens each)
            - metadata: PDF metadata (page_count, title, author, filename)
        """
        try:
            pdf_path_obj = Path(pdf_path)
            if not pdf_path_obj.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
            text_chunks = []
            metadata = {
                "filename": pdf_path_obj.name,
                "page_count": 0,
                "title": None,
                "author": None
            }
            
            # Open PDF
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # Extract metadata
                metadata["page_count"] = len(pdf_reader.pages)
                if pdf_reader.metadata:
                    metadata["title"] = pdf_reader.metadata.get("/Title")
                    metadata["author"] = pdf_reader.metadata.get("/Author")
                
                # Extract text from each page
                full_text = ""
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
                        full_text += page_text
                
                # Check text quality - if poor, try OCR fallback
                if not self._is_text_quality_good(full_text):
                    logger.warning(f"PyPDF2 extracted text quality is poor (length: {len(full_text)}). Trying OCR fallback...")
                    
                    # Try SmolDocling first if available (Apple Silicon)
                    ocr_text = ""
                    if self.smoldocling_available:
                        ocr_text = self._extract_text_with_smoldocling(pdf_path)
                    
                    # Fallback to Ollama if SmolDocling not available or failed
                    if not ocr_text and self.ollama_available:
                        ocr_text = self._extract_text_with_ollama_ocr(pdf_path)
                    
                    if ocr_text and len(ocr_text) > len(full_text) * 1.5:  # OCR gives significantly more text
                        logger.info("Using OCR text (better quality than PyPDF2)")
                        full_text = ocr_text
                    elif not full_text or len(full_text.strip()) < 100:
                        # If PyPDF2 got almost nothing, use OCR even if shorter
                        if ocr_text:
                            logger.info("Using OCR text (PyPDF2 extracted minimal text)")
                            full_text = ocr_text
                
                # Split into chunks (targeting ~300 tokens, ~1200 chars)
                # Model has 2048 token limit, so we need to leave room for prompt + response (~500 tokens)
                # Each chunk should be ~300 tokens (~1200 chars) max
                paragraphs = full_text.split("\n\n")
                current_chunk = ""
                
                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue
                    
                    # If adding this paragraph would exceed ~1200 chars, save current chunk
                    if current_chunk and len(current_chunk) + len(para) > 1200:
                        text_chunks.append(current_chunk.strip())
                        current_chunk = para
                    else:
                        current_chunk += "\n\n" + para if current_chunk else para
                
                # Add final chunk
                if current_chunk.strip():
                    text_chunks.append(current_chunk.strip())
            
            logger.info(f"Processed PDF: {len(text_chunks)} chunks, {metadata['page_count']} pages")
            
            return {
                "text_chunks": text_chunks,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path}: {e}")
            raise
    
    def get_chunk_count(self, text_chunks: List[str]) -> int:
        """Get number of chunks."""
        return len(text_chunks)
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (rough heuristic: ~4 chars per token).
        
        Args:
            text: Text string
            
        Returns:
            Estimated token count
        """
        return len(text) // 4
