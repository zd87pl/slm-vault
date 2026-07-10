"""
PDF processing service for extracting text and metadata from PDF files.

Features:
- Text extraction using PyPDF2 (for text-based PDFs)
- Optional LiteParse backend for layout-aware parsing and OCR
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
from typing import Dict, List, Any, Optional, Callable, Tuple

try:
    # pypdf is the maintained successor to PyPDF2 with the same PdfReader API
    import pypdf as PyPDF2
except ImportError:
    import PyPDF2

import requests

from advanced_vault.parsing import extract_pdf_text, has_liteparse_backend, is_text_quality_good

# Try to import LiteParse (Python wrapper around Node CLI)
LITEPARSE_PYTHON_AVAILABLE = False
LiteParse = None
LiteParseError = RuntimeError
try:
    from liteparse import LiteParse
    from liteparse.types import ParseError as LiteParseError
    LITEPARSE_PYTHON_AVAILABLE = True
except ImportError:
    LITEPARSE_PYTHON_AVAILABLE = False

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


def _env_flag(name: str, default: bool) -> bool:
    """Parse boolean environment variables safely."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_int(name: str, default: int) -> int:
    """Parse integer environment variables safely."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer for {name}: {value!r}. Using default {default}.")
        return default


def _env_float(name: str, default: float) -> float:
    """Parse float environment variables safely."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Invalid float for {name}: {value!r}. Using default {default}.")
        return default


def probe_liteparse_backend(
    cli_path: Optional[str] = None,
    install_if_not_available: Optional[bool] = None,
) -> bool:
    """
    Check whether LiteParse is usable in the current environment.

    This validates both the Python wrapper and the backing CLI without
    triggering an implicit global install unless explicitly requested.
    """
    _ = cli_path
    _ = install_if_not_available
    return has_liteparse_backend(cli_path=cli_path)


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
            progress_callback("Installing SmolDocling dependencies...")
        
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
                progress_callback(f"Installing {package}...")
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
            progress_callback(f"Installation error: {str(e)}")
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
        # NOTE: llama3.2-vision ships in 11b/90b only; a "1b" tag does not exist
        self.ollama_model = ollama_model or os.getenv("OLLAMA_OCR_MODEL", "llama3.2-vision:11b")
        self.ollama_setup = OllamaSetup(base_url=self.ollama_base_url, model=self.ollama_model)

        self.parser_backend_preference = os.getenv(
            "ENCLAVE_PARSER_BACKEND",
            os.getenv("ENCLAVE_PDF_BACKEND", "auto"),
        ).strip().lower()
        if self.parser_backend_preference == "native":
            self.parser_backend_preference = "legacy"
        if self.parser_backend_preference not in {"auto", "legacy", "liteparse", "pypdf"}:
            logger.warning(
                f"Unknown ENCLAVE_PARSER_BACKEND={self.parser_backend_preference!r}. Falling back to 'auto'."
            )
            self.parser_backend_preference = "auto"

        self.liteparse_auto_install = _env_flag("ENCLAVE_LITEPARSE_AUTO_INSTALL", False)
        self.liteparse_allow_npx = _env_flag("ENCLAVE_LITEPARSE_ALLOW_NPX", True)
        self.liteparse_cli_path = os.getenv("ENCLAVE_LITEPARSE_CLI_PATH")
        self.liteparse_ocr_enabled = _env_flag("ENCLAVE_LITEPARSE_OCR_ENABLED", True)
        self.liteparse_ocr_server_url = os.getenv("ENCLAVE_LITEPARSE_OCR_SERVER_URL")
        self.liteparse_ocr_language = os.getenv("ENCLAVE_LITEPARSE_OCR_LANGUAGE", "en")
        self.liteparse_dpi = _env_int("ENCLAVE_LITEPARSE_DPI", 180)
        self.liteparse_timeout = _env_float("ENCLAVE_LITEPARSE_TIMEOUT", 180.0)
        self.liteparse_precise_bounding_box = _env_flag("ENCLAVE_LITEPARSE_PRECISE_BBOX", True)
        self.liteparse_preserve_small_text = _env_flag("ENCLAVE_LITEPARSE_PRESERVE_SMALL_TEXT", True)
        self.liteparse_available = False
        self.liteparse_last_error = None

        self._initialize_liteparse_backend(progress_callback=progress_callback)

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

    def _initialize_liteparse_backend(
        self, progress_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """Initialize the optional LiteParse backend."""
        if self.parser_backend_preference not in {"auto", "liteparse"}:
            return

        try:
            self.liteparse_available = probe_liteparse_backend(
                cli_path=self.liteparse_cli_path,
                install_if_not_available=self.liteparse_auto_install,
            )
            if self.liteparse_available:
                logger.info("LiteParse backend ready (OCR=%s)", self.liteparse_ocr_enabled)
                if progress_callback:
                    progress_callback("LiteParse parser ready")
            else:
                logger.info("LiteParse backend unavailable; continuing with legacy PDF pipeline.")
        except Exception as exc:
            self.liteparse_last_error = str(exc)
            logger.warning(f"LiteParse backend unavailable, falling back to legacy parser: {exc}")

    def has_document_extraction_backend(self) -> bool:
        """Return whether any enhanced document extraction backend is ready."""
        return self.liteparse_available or self.smoldocling_available or self.ollama_available

    def get_backend_status_label(self) -> str:
        """Return a short UI-friendly label for the active extraction stack."""
        if self.parser_backend_preference == "liteparse" and self.liteparse_available:
            return "LiteParse"
        if self.parser_backend_preference == "auto" and self.liteparse_available:
            return "LiteParse + fallback"
        if self.smoldocling_available:
            return "SmolDocling ~500MB"
        if self.ollama_available:
            return "Ollama"
        return "PyPDF2"

    def _extract_pdf_metadata(self, pdf_path: str) -> Dict[str, Any]:
        """Extract PDF metadata without changing the public return shape."""
        pdf_path_obj = Path(pdf_path)
        metadata = {
            "filename": pdf_path_obj.name,
            "page_count": 0,
            "title": None,
            "author": None,
        }

        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            metadata["page_count"] = len(pdf_reader.pages)
            if pdf_reader.metadata:
                metadata["title"] = pdf_reader.metadata.get("/Title")
                metadata["author"] = pdf_reader.metadata.get("/Author")

        return metadata

    def _chunk_text(self, full_text: str) -> List[str]:
        """Split extracted text into stable training/query chunks."""
        text_chunks: List[str] = []
        chunk_size = 512
        chunk_overlap = 100

        paragraphs = full_text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_chunk and len(current_chunk) + len(para) > chunk_size:
                text_chunks.append(current_chunk.strip())
                overlap_text = (
                    current_chunk[-chunk_overlap:]
                    if len(current_chunk) > chunk_overlap
                    else current_chunk
                )
                current_chunk = overlap_text + "\n\n" + para if overlap_text else para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk.strip():
            text_chunks.append(current_chunk.strip())

        return text_chunks

    def _extract_text_with_liteparse(self, pdf_path: str) -> Tuple[str, int]:
        """Extract text using LiteParse, preserving page boundaries."""
        if not self.liteparse_available:
            return "", 0

        original_env = {
            "ENCLAVE_LITEPARSE_NO_OCR": os.getenv("ENCLAVE_LITEPARSE_NO_OCR"),
            "ENCLAVE_LITEPARSE_DPI": os.getenv("ENCLAVE_LITEPARSE_DPI"),
            "ENCLAVE_LITEPARSE_TIMEOUT_SECONDS": os.getenv("ENCLAVE_LITEPARSE_TIMEOUT_SECONDS"),
            "ENCLAVE_LITEPARSE_MAX_PAGES": os.getenv("ENCLAVE_LITEPARSE_MAX_PAGES"),
        }
        os.environ["ENCLAVE_LITEPARSE_NO_OCR"] = "false" if self.liteparse_ocr_enabled else "true"
        os.environ["ENCLAVE_LITEPARSE_DPI"] = str(self.liteparse_dpi)
        os.environ["ENCLAVE_LITEPARSE_TIMEOUT_SECONDS"] = str(int(self.liteparse_timeout))
        logger.info("Parsing PDF with LiteParse...")
        try:
            result = extract_pdf_text(
                pdf_path,
                backend="liteparse",
                ocr_language=self.liteparse_ocr_language,
                ocr_server_url=self.liteparse_ocr_server_url,
                allow_npx=self.liteparse_allow_npx,
                cli_path=self.liteparse_cli_path,
                quiet=True,
            )
        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        full_text = result.text

        logger.info("LiteParse extraction complete: %s chars", len(full_text))
        return full_text, int(result.metadata.get("page_count", 0))

    def _extract_text_with_legacy_pipeline(
        self, pdf_path: str, metadata: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], str]:
        """Extract text using the existing PyPDF2 + OCR fallback pipeline."""
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)

            metadata["page_count"] = len(pdf_reader.pages)
            if pdf_reader.metadata:
                metadata["title"] = pdf_reader.metadata.get("/Title")
                metadata["author"] = pdf_reader.metadata.get("/Author")

            full_text = ""
            selected_backend = "pypdf"
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
                    full_text += page_text

            if not self._is_text_quality_good(full_text):
                logger.warning(
                    "PyPDF2 extracted text quality is poor (length: %s). Trying OCR fallback...",
                    len(full_text),
                )

                ocr_text = ""
                ocr_backend = selected_backend
                if self.smoldocling_available:
                    ocr_text = self._extract_text_with_smoldocling(pdf_path)
                    if ocr_text:
                        ocr_backend = "smoldocling"

                if not ocr_text and self.ollama_available:
                    ocr_text = self._extract_text_with_ollama_ocr(pdf_path)
                    if ocr_text:
                        ocr_backend = "ollama"

                if ocr_text and len(ocr_text) > len(full_text) * 1.5:
                    logger.info("Using OCR text (better quality than PyPDF2)")
                    full_text = ocr_text
                    selected_backend = ocr_backend
                elif not full_text or len(full_text.strip()) < 100:
                    if ocr_text:
                        logger.info("Using OCR text (PyPDF2 extracted minimal text)")
                        full_text = ocr_text
                        selected_backend = ocr_backend

        return full_text, metadata, selected_backend
    
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
        return is_text_quality_good(text)
    
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
            - text_chunks: List of text chunks (512 chars optimal for MLX Q&A generation)
            - metadata: PDF metadata (page_count, title, author, filename)
        """
        try:
            pdf_path_obj = Path(pdf_path)
            if not pdf_path_obj.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            metadata = self._extract_pdf_metadata(pdf_path)
            full_text = ""
            backend_used = "pypdf"

            if self.parser_backend_preference == "liteparse" and self.liteparse_available:
                try:
                    full_text, liteparse_page_count = self._extract_text_with_liteparse(pdf_path)
                    if liteparse_page_count:
                        metadata["page_count"] = liteparse_page_count
                    if self._is_text_quality_good(full_text):
                        backend_used = "liteparse"
                    else:
                        logger.warning("LiteParse text quality was weak. Falling back to legacy pipeline.")
                        full_text = ""
                except Exception as exc:
                    logger.warning(f"LiteParse parsing failed. Falling back to legacy pipeline: {exc}")
                    full_text = ""

            if not full_text:
                full_text, metadata, backend_used = self._extract_text_with_legacy_pipeline(
                    pdf_path,
                    metadata,
                )

                if (
                    self.parser_backend_preference == "auto"
                    and self.liteparse_available
                    and not self._is_text_quality_good(full_text)
                ):
                    try:
                        liteparse_text, liteparse_page_count = self._extract_text_with_liteparse(pdf_path)
                        if liteparse_page_count:
                            metadata["page_count"] = liteparse_page_count
                        liteparse_good = self._is_text_quality_good(liteparse_text)
                        if liteparse_text and (liteparse_good or len(liteparse_text) > len(full_text) * 1.2):
                            logger.info("Using LiteParse output after weak legacy extraction.")
                            full_text = liteparse_text
                            backend_used = "liteparse"
                    except Exception as exc:
                        logger.warning(f"LiteParse auto-fallback failed, keeping legacy output: {exc}")

            text_chunks = self._chunk_text(full_text)
            metadata["parser_backend"] = backend_used

            logger.info(
                "Processed PDF: %s chunks, %s pages via %s",
                len(text_chunks),
                metadata["page_count"],
                backend_used,
            )

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
