"""
PDF processing service for extracting text and metadata from PDF files.

Features:
- Text extraction using PyPDF2
- Intelligent chunking for training
- Metadata extraction (page count, title, author)
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import PyPDF2

logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Service for processing PDF files into chunks suitable for training.
    """
    
    def __init__(self):
        """Initialize PDF processor."""
        pass
    
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


