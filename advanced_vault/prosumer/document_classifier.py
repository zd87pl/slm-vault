"""
Document Type Classifier

Automatically detects the type and category of uploaded documents
using filename analysis, MIME type detection, and content scanning.

Supports:
- PDF text extraction (via liteparse or fallback)
- Image OCR (via tesseract or liteparse)
- Plain text and structured formats
- Batch classification for folder imports
"""

import re
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
import logging

from .vault_categories import VaultCategory, get_category_for_document, PERSONAL_VAULT

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of document classification."""
    
    filename: str
    category: VaultCategory
    confidence: float
    mime_type: str
    detected_type: str  # "pdf", "image", "text", "spreadsheet", etc.
    content_preview: str = ""
    metadata: Dict[str, Any] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.warnings is None:
            self.warnings = []
    
    @property
    def is_high_confidence(self) -> bool:
        """Whether classification confidence is high enough to auto-categorize."""
        return self.confidence >= 0.6
    
    @property
    def needs_review(self) -> bool:
        """Whether user should review the categorization."""
        return 0.3 <= self.confidence < 0.6
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "category_id": self.category.id,
            "category_name": self.category.name,
            "confidence": round(self.confidence, 3),
            "mime_type": self.mime_type,
            "detected_type": self.detected_type,
            "content_preview": self.content_preview[:200] if self.content_preview else "",
            "metadata": self.metadata,
            "warnings": self.warnings,
            "is_high_confidence": self.is_high_confidence,
            "needs_review": self.needs_review,
        }


class DocumentClassifier:
    """Classifies documents into vault categories."""
    
    # MIME type mapping
    MIME_MAP = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".json": "application/json",
        ".xml": "application/xml",
        ".html": "text/html",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".ofx": "application/x-ofx",
        ".qfx": "application/x-qfx",
        ".hl7": "application/hl7-v2",
    }
    
    def __init__(self, vault_path: str = ""):
        self.vault_path = Path(vault_path) if vault_path else Path.home() / ".vault"
        self._text_extractors = {}
        self._init_extractors()
    
    def _init_extractors(self):
        """Initialize text extraction backends."""
        # Try liteparse first (fast, local)
        try:
            from advanced_vault.parsing.liteparse import extract_text
            self._text_extractors["liteparse"] = extract_text
            logger.info("DocumentClassifier: liteparse backend available")
        except ImportError:
            logger.debug("DocumentClassifier: liteparse not available")
        
        # Fallback to pypdf (or legacy PyPDF2)
        try:
            self._import_pypdf()
            self._text_extractors["pypdf2"] = self._extract_pdf_pypdf2
            logger.info("DocumentClassifier: pypdf backend available")
        except ImportError:
            pass
        
        # Image OCR via pytesseract
        try:
            import pytesseract
            from PIL import Image
            self._text_extractors["tesseract"] = self._extract_image_ocr
            logger.info("DocumentClassifier: Tesseract OCR available")
        except ImportError:
            pass
    
    def classify_file(
        self,
        file_path: str,
        extract_content: bool = True,
        max_preview_chars: int = 3000
    ) -> ClassificationResult:
        """
        Classify a single file.
        
        Args:
            file_path: Path to the file
            extract_content: Whether to extract text for content analysis
            max_preview_chars: Maximum characters to extract for preview
        
        Returns:
            ClassificationResult with category and confidence
        """
        path = Path(file_path)
        filename = path.name
        
        # Detect MIME type
        mime_type = self._detect_mime_type(path)
        detected_type = self._detect_file_type(path, mime_type)
        
        # Extract content preview if requested and possible
        content_preview = ""
        metadata = {}
        warnings = []
        
        if extract_content:
            try:
                content_preview, metadata = self._extract_content(
                    path, max_preview_chars
                )
            except Exception as e:
                warnings.append(f"Could not extract content: {e}")
                logger.warning(f"Content extraction failed for {filename}: {e}")
        
        # Classify
        category, confidence = get_category_for_document(
            filename=filename,
            mime_type=mime_type,
            content_preview=content_preview,
            min_confidence=0.0  # We handle low confidence below
        )
        
        # Boost confidence if we have good content extraction
        if content_preview and len(content_preview) > 500:
            confidence = min(confidence * 1.2, 1.0)
        
        # If still low confidence, default to personal
        if confidence < 0.2:
            category = PERSONAL_VAULT
            confidence = 0.1
            warnings.append("Low confidence classification; placed in Personal Knowledge Vault")
        
        return ClassificationResult(
            filename=filename,
            category=category,
            confidence=confidence,
            mime_type=mime_type,
            detected_type=detected_type,
            content_preview=content_preview[:500] if content_preview else "",
            metadata=metadata,
            warnings=warnings,
        )
    
    def classify_batch(
        self,
        file_paths: List[str],
        extract_content: bool = True
    ) -> List[ClassificationResult]:
        """
        Classify multiple files.
        
        Args:
            file_paths: List of file paths
            extract_content: Whether to extract text content
        
        Returns:
            List of ClassificationResult objects
        """
        results = []
        for file_path in file_paths:
            try:
                result = self.classify_file(file_path, extract_content)
                results.append(result)
            except Exception as e:
                logger.error(f"Classification failed for {file_path}: {e}")
                # Create a fallback result
                results.append(ClassificationResult(
                    filename=Path(file_path).name,
                    category=PERSONAL_VAULT,
                    confidence=0.0,
                    mime_type="unknown",
                    detected_type="unknown",
                    warnings=[f"Classification error: {e}"],
                ))
        return results
    
    def classify_folder(
        self,
        folder_path: str,
        recursive: bool = True,
        max_files: int = 1000
    ) -> List[ClassificationResult]:
        """
        Classify all documents in a folder.
        
        Args:
            folder_path: Path to folder
            recursive: Whether to scan subdirectories
            max_files: Maximum number of files to process
        
        Returns:
            List of ClassificationResult objects
        """
        path = Path(folder_path)
        if not path.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")
        
        file_paths = []
        pattern = "**/*" if recursive else "*"
        
        for file_path in path.glob(pattern):
            if file_path.is_file():
                file_paths.append(str(file_path))
                if len(file_paths) >= max_files:
                    break
        
        logger.info(f"Classifying {len(file_paths)} files from {folder_path}")
        return self.classify_batch(file_paths)
    
    def get_category_summary(
        self,
        results: List[ClassificationResult]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get a summary of classification results by category.
        
        Args:
            results: List of classification results
        
        Returns:
            Dict mapping category_id to summary stats
        """
        summary = {}
        for result in results:
            cat_id = result.category.id
            if cat_id not in summary:
                summary[cat_id] = {
                    "category_name": result.category.name,
                    "count": 0,
                    "avg_confidence": 0.0,
                    "files": [],
                    "needs_review": 0,
                }
            
            summary[cat_id]["count"] += 1
            summary[cat_id]["avg_confidence"] += result.confidence
            summary[cat_id]["files"].append(result.filename)
            if result.needs_review:
                summary[cat_id]["needs_review"] += 1
        
        # Calculate averages
        for cat_id in summary:
            count = summary[cat_id]["count"]
            if count > 0:
                summary[cat_id]["avg_confidence"] = round(
                    summary[cat_id]["avg_confidence"] / count, 3
                )
        
        return summary
    
    def _detect_mime_type(self, path: Path) -> str:
        """Detect MIME type from file extension."""
        ext = path.suffix.lower()
        return self.MIME_MAP.get(ext, "application/octet-stream")
    
    def _detect_file_type(self, path: Path, mime_type: str) -> str:
        """Categorize file into broad type."""
        if mime_type.startswith("application/pdf"):
            return "pdf"
        elif mime_type.startswith("image/"):
            return "image"
        elif mime_type.startswith("text/"):
            return "text"
        elif "spreadsheet" in mime_type or mime_type in ("text/csv", "application/vnd.ms-excel"):
            return "spreadsheet"
        elif "word" in mime_type or mime_type == "application/rtf":
            return "document"
        elif mime_type == "application/json":
            return "json"
        elif mime_type == "application/xml":
            return "xml"
        else:
            return "unknown"
    
    def _extract_content(
        self,
        path: Path,
        max_chars: int
    ) -> Tuple[str, Dict[str, Any]]:
        """Extract text content from a file."""
        mime_type = self._detect_mime_type(path)
        metadata = {"file_size": path.stat().st_size}
        
        # Text files - direct read
        if mime_type.startswith("text/"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                return text[:max_chars], metadata
            except Exception:
                pass
        
        # JSON files
        if mime_type == "application/json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                # Flatten for preview
                text = json.dumps(data, indent=2)[:max_chars]
                return text, metadata
            except Exception:
                pass
        
        # PDF files
        if mime_type == "application/pdf":
            return self._extract_pdf(path, max_chars)
        
        # Image files
        if mime_type.startswith("image/"):
            return self._extract_image(path, max_chars)
        
        # Fallback: try liteparse if available
        if "liteparse" in self._text_extractors:
            try:
                text = self._text_extractors["liteparse"](str(path))
                return text[:max_chars], {"extractor": "liteparse"}
            except Exception:
                pass
        
        return "", metadata
    
    def _extract_pdf(self, path: Path, max_chars: int) -> Tuple[str, Dict[str, Any]]:
        """Extract text from PDF."""
        metadata = {"extractor": "unknown"}
        
        # Try liteparse first
        if "liteparse" in self._text_extractors:
            try:
                text = self._text_extractors["liteparse"](str(path))
                metadata["extractor"] = "liteparse"
                return text[:max_chars], metadata
            except Exception:
                pass
        
        # Try PyPDF2
        if "pypdf2" in self._text_extractors:
            try:
                text = self._text_extractors["pypdf2"](path, max_chars)
                metadata["extractor"] = "pypdf2"
                return text, metadata
            except Exception:
                pass
        
        return "", metadata
    
    @staticmethod
    def _import_pypdf():
        """Import pypdf, falling back to legacy PyPDF2 (same PdfReader API)."""
        try:
            import pypdf
            return pypdf
        except ImportError:
            import PyPDF2
            return PyPDF2

    def _extract_pdf_pypdf2(self, path: Path, max_chars: int) -> str:
        """Extract text using pypdf (or legacy PyPDF2)."""
        pypdf_mod = self._import_pypdf()
        text = ""
        with open(path, "rb") as f:
            reader = pypdf_mod.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
                if len(text) >= max_chars:
                    break
        return text[:max_chars]
    
    def _extract_image(self, path: Path, max_chars: int) -> Tuple[str, Dict[str, Any]]:
        """Extract text from image via OCR."""
        metadata = {"extractor": "unknown"}
        
        # Try liteparse first
        if "liteparse" in self._text_extractors:
            try:
                text = self._text_extractors["liteparse"](str(path))
                metadata["extractor"] = "liteparse"
                return text[:max_chars], metadata
            except Exception:
                pass
        
        # Try tesseract
        if "tesseract" in self._text_extractors:
            try:
                text = self._text_extractors["tesseract"](path, max_chars)
                metadata["extractor"] = "tesseract"
                return text, metadata
            except Exception:
                pass
        
        return "", metadata
    
    def _extract_image_ocr(self, path: Path, max_chars: int) -> str:
        """Extract text from image using Tesseract OCR."""
        import pytesseract
        from PIL import Image
        image = Image.open(path)
        text = pytesseract.image_to_string(image)
        return text[:max_chars]
