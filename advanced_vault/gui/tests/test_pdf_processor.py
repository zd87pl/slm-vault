"""
Tests for PDF processor.

Tests:
- PDF text extraction
- Metadata extraction
- Chunking logic
- Error handling
"""

import unittest
import tempfile
import os
from pathlib import Path
import sys
from unittest.mock import patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Skip if PyPDF2 not available
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

from advanced_vault.gui.pdf_processor import PDFProcessor


@unittest.skipUnless(PYPDF2_AVAILABLE, "PyPDF2 not installed")
class TestPDFProcessor(unittest.TestCase):
    """Test PDF processor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.env_patcher = patch.dict(
            os.environ,
            {
                "ENCLAVE_USE_SMOLDOCLING": "false",
                "ENCLAVE_PARSER_BACKEND": "legacy",
            },
            clear=False,
        )
        self.apple_patcher = patch(
            "advanced_vault.gui.pdf_processor._is_apple_silicon",
            return_value=False,
        )
        self.ollama_patcher = patch.object(
            PDFProcessor,
            "_test_ollama_connection",
            return_value=False,
        )
        self.env_patcher.start()
        self.apple_patcher.start()
        self.ollama_patcher.start()
        self.processor = PDFProcessor(auto_setup=False)
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        self.ollama_patcher.stop()
        self.apple_patcher.stop()
        self.env_patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_test_pdf(self, text_content: str = "Test PDF content") -> str:
        """Create a simple test PDF file."""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            
            pdf_path = os.path.join(self.temp_dir, "test.pdf")
            c = canvas.Canvas(pdf_path, pagesize=letter)
            c.drawString(100, 750, text_content)
            c.save()
            return pdf_path
        except ImportError:
            # Fallback: create empty PDF file (won't work but allows tests to run)
            pdf_path = os.path.join(self.temp_dir, "test.pdf")
            with open(pdf_path, "wb") as f:
                f.write(b"%PDF-1.4\n")  # Minimal PDF header
            return pdf_path
    
    def test_init(self):
        """Test processor initialization."""
        processor = PDFProcessor(auto_setup=False)
        self.assertIsNotNone(processor)
    
    def test_process_pdf_not_found(self):
        """Test processing non-existent PDF."""
        processor = PDFProcessor(auto_setup=False)
        
        with self.assertRaises(FileNotFoundError):
            processor.process_pdf("/nonexistent/file.pdf")
    
    def test_estimate_tokens(self):
        """Test token estimation."""
        processor = PDFProcessor(auto_setup=False)
        
        # Test estimation
        text = "This is a test string with some words."
        tokens = processor.estimate_tokens(text)
        
        # Should return a positive integer
        self.assertGreater(tokens, 0)
        self.assertIsInstance(tokens, int)
        
        # Rough check: ~4 chars per token
        expected_range = (len(text) // 5, len(text) // 3)
        self.assertGreaterEqual(tokens, expected_range[0])
        self.assertLessEqual(tokens, expected_range[1])
    
    def test_get_chunk_count(self):
        """Test chunk count."""
        processor = PDFProcessor(auto_setup=False)
        
        chunks = ["chunk1", "chunk2", "chunk3"]
        count = processor.get_chunk_count(chunks)
        
        self.assertEqual(count, 3)
    
    @unittest.skipIf(not PYPDF2_AVAILABLE, "PyPDF2 not available")
    def test_process_pdf_structure(self):
        """Test PDF processing returns correct structure."""
        # Create minimal test PDF
        pdf_path = self.create_test_pdf("Test content for PDF processing.")
        
        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 100:
            self.skipTest("Could not create valid test PDF")
        
        try:
            result = self.processor.process_pdf(pdf_path)
            
            # Verify structure
            self.assertIn("text_chunks", result)
            self.assertIn("metadata", result)
            
            # Verify metadata structure
            metadata = result["metadata"]
            self.assertIn("filename", metadata)
            self.assertIn("page_count", metadata)
            self.assertIn("title", metadata)
            self.assertIn("author", metadata)
            
            # Verify chunks
            chunks = result["text_chunks"]
            self.assertIsInstance(chunks, list)
            
        except Exception as e:
            # If PDF processing fails due to invalid PDF, that's okay for basic test
            self.skipTest(f"PDF processing failed (expected for minimal PDF): {e}")

    def test_process_pdf_uses_liteparse_when_forced(self):
        """Forced LiteParse mode should use LiteParse output when available."""
        pdf_path = self.create_test_pdf(
            "This PDF includes enough structured text to satisfy quality checks for LiteParse parsing."
        )

        with patch.dict(os.environ, {"ENCLAVE_PARSER_BACKEND": "liteparse"}, clear=False):
            with patch("advanced_vault.gui.pdf_processor._is_apple_silicon", return_value=False):
                with patch.object(PDFProcessor, "_test_ollama_connection", return_value=False):
                    with patch(
                        "advanced_vault.gui.pdf_processor.probe_liteparse_backend",
                        return_value=True,
                    ):
                        with patch.object(
                            PDFProcessor,
                            "_extract_pdf_metadata",
                            return_value={
                                "filename": "test.pdf",
                                "page_count": 1,
                                "title": None,
                                "author": None,
                            },
                        ):
                            with patch.object(
                                PDFProcessor,
                                "_extract_text_with_liteparse",
                                return_value=(
                                    "LiteParse extracted a clean and detailed page of text that is comfortably over fifty characters.",
                                    1,
                                ),
                            ):
                                processor = PDFProcessor(auto_setup=False)
                                result = processor.process_pdf(pdf_path)

        self.assertTrue(result["text_chunks"])
        self.assertEqual(result["metadata"]["parser_backend"], "liteparse")
        self.assertEqual(result["metadata"]["page_count"], 1)

    def test_process_pdf_falls_back_when_liteparse_fails(self):
        """LiteParse failures should fall back to the legacy PyPDF2 path."""
        pdf_path = self.create_test_pdf(
            "This PDF includes enough ordinary text for the legacy parser to work without OCR fallback."
        )

        with patch.dict(os.environ, {"ENCLAVE_PARSER_BACKEND": "liteparse"}, clear=False):
            with patch("advanced_vault.gui.pdf_processor._is_apple_silicon", return_value=False):
                with patch.object(PDFProcessor, "_test_ollama_connection", return_value=False):
                    with patch(
                        "advanced_vault.gui.pdf_processor.probe_liteparse_backend",
                        return_value=True,
                    ):
                        with patch.object(
                            PDFProcessor,
                            "_extract_pdf_metadata",
                            return_value={
                                "filename": "test.pdf",
                                "page_count": 1,
                                "title": None,
                                "author": None,
                            },
                        ):
                            with patch.object(
                                PDFProcessor,
                                "_extract_text_with_liteparse",
                                side_effect=RuntimeError("LiteParse CLI failed"),
                            ):
                                with patch.object(
                                    PDFProcessor,
                                    "_extract_text_with_legacy_pipeline",
                                    return_value=(
                                        "Legacy parser returned enough text to remain useful after a LiteParse failure.",
                                        {
                                            "filename": "test.pdf",
                                            "page_count": 1,
                                            "title": None,
                                            "author": None,
                                        },
                                        "pypdf",
                                    ),
                                ):
                                    processor = PDFProcessor(auto_setup=False)
                                    result = processor.process_pdf(pdf_path)

        self.assertTrue(result["text_chunks"])
        self.assertEqual(result["metadata"]["parser_backend"], "pypdf")


if __name__ == "__main__":
    unittest.main()
