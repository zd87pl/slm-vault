"""
Late Chunking for Enclave RAG Pipeline.

Implements the late chunking strategy from Jina AI (EMNLP 2024)
for up to +24% MRR improvement over traditional chunking.

Traditional: Chunk first, then embed (loses context)
Late chunking: Embed full document, then chunk (preserves context)

Reference: https://arxiv.org/abs/2409.04701
"""

import logging
from typing import List, Optional, Tuple, Callable
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LateChunk:
    """A chunk created via late chunking."""
    content: str
    embedding: np.ndarray
    start_char: int
    end_char: int
    token_start: int
    token_end: int
    document_context: str  # Full document for reference


class LateChunker:
    """
    Late chunking implementation.

    Instead of chunking text first and then embedding each chunk independently,
    late chunking:
    1. Embeds the full document using a long-context model
    2. Uses token-level embeddings to create chunk embeddings
    3. Each chunk embedding contains context from the full document

    This achieves +24% MRR improvement according to Jina AI research.

    Requirements:
    - Long-context embedding model (e.g., jina-embeddings-v3)
    - Token-level embedding access
    """

    def __init__(
        self,
        chunk_size: int = 450,  # tokens
        chunk_overlap: int = 50,  # tokens
        max_document_length: int = 8192,  # tokens
    ):
        """
        Initialize late chunker.

        Args:
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks in tokens
            max_document_length: Maximum document length to process
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_document_length = max_document_length

        self._tokenizer = None
        self._model = None

    def _load_tokenizer(self):
        """Load tokenizer for token-level operations."""
        if self._tokenizer is not None:
            return

        try:
            from transformers import AutoTokenizer
            # Use a fast tokenizer compatible with most embedding models
            self._tokenizer = AutoTokenizer.from_pretrained(
                "bert-base-uncased",
                use_fast=True
            )
        except ImportError:
            raise ImportError(
                "transformers is required for late chunking. "
                "Install with: pip install transformers"
            )

    def chunk_with_embeddings(
        self,
        text: str,
        token_embeddings: np.ndarray,
        tokens: List[str]
    ) -> List[LateChunk]:
        """
        Create chunks from pre-computed token embeddings.

        This is the core late chunking operation: given token-level embeddings
        from a full document, create chunk embeddings by pooling token embeddings.

        Args:
            text: Original document text
            token_embeddings: Token-level embeddings of shape (n_tokens, dim)
            tokens: List of token strings

        Returns:
            List of LateChunk objects with context-aware embeddings
        """
        if len(token_embeddings) != len(tokens):
            raise ValueError(
                f"Mismatch: {len(token_embeddings)} embeddings vs {len(tokens)} tokens"
            )

        chunks = []
        n_tokens = len(tokens)
        start_token = 0

        while start_token < n_tokens:
            end_token = min(start_token + self.chunk_size, n_tokens)

            # Get token embeddings for this chunk
            chunk_token_embs = token_embeddings[start_token:end_token]

            # Pool token embeddings (mean pooling)
            chunk_embedding = np.mean(chunk_token_embs, axis=0)

            # Normalize
            norm = np.linalg.norm(chunk_embedding)
            if norm > 0:
                chunk_embedding = chunk_embedding / norm

            # Reconstruct chunk text from tokens
            chunk_tokens = tokens[start_token:end_token]
            chunk_text = self._tokens_to_text(chunk_tokens)

            # Estimate character positions
            start_char = self._estimate_char_position(tokens, start_token)
            end_char = self._estimate_char_position(tokens, end_token)

            chunks.append(LateChunk(
                content=chunk_text,
                embedding=chunk_embedding,
                start_char=start_char,
                end_char=end_char,
                token_start=start_token,
                token_end=end_token,
                document_context=text[:500]  # First 500 chars for reference
            ))

            # Move to next chunk with overlap
            start_token = end_token - self.chunk_overlap
            if start_token >= n_tokens - self.chunk_overlap:
                break

        return chunks

    def _tokens_to_text(self, tokens: List[str]) -> str:
        """Convert tokens back to text."""
        # Handle WordPiece/BPE tokenization
        text = ""
        for token in tokens:
            if token.startswith("##"):
                text += token[2:]
            elif token.startswith("Ġ"):  # GPT-style
                text += " " + token[1:]
            elif token in ["[CLS]", "[SEP]", "[PAD]", "<s>", "</s>"]:
                continue
            else:
                if text and not text.endswith(" "):
                    text += " "
                text += token
        return text.strip()

    def _estimate_char_position(self, tokens: List[str], token_idx: int) -> int:
        """
        Estimate character position from token index.

        Computes actual character offset by summing token lengths up to the index.
        """
        if token_idx == 0:
            return 0

        # Sum actual token lengths (accounting for WordPiece/BPE)
        char_pos = 0
        for i, token in enumerate(tokens[:token_idx]):
            if token.startswith("##"):
                char_pos += len(token) - 2  # Exclude "##"
            elif token.startswith("Ġ"):
                char_pos += len(token)  # Include space
            elif token in ["[CLS]", "[SEP]", "[PAD]", "<s>", "</s>"]:
                continue
            else:
                char_pos += len(token) + 1  # Token + space

        return char_pos

    def process_document(
        self,
        text: str,
        get_token_embeddings: Callable[[str], Tuple[np.ndarray, List[str]]]
    ) -> List[LateChunk]:
        """
        Process a document using late chunking.

        Args:
            text: Document text
            get_token_embeddings: Function that returns (token_embeddings, tokens)
                                  for a given text

        Returns:
            List of LateChunk objects
        """
        # Get token-level embeddings from the model
        # Note: The embedding model handles its own tokenization
        token_embeddings, tokens = get_token_embeddings(text)

        # Truncate if too long (after getting embeddings)
        if len(tokens) > self.max_document_length:
            tokens = tokens[:self.max_document_length]
            token_embeddings = token_embeddings[:self.max_document_length]
            logger.warning(
                f"Document truncated to {self.max_document_length} tokens"
            )

        # Create chunks with context-aware embeddings
        return self.chunk_with_embeddings(text, token_embeddings, tokens)


class JinaLateChunker:
    """
    Late chunking using Jina Embeddings API.

    Jina embeddings-v3 supports native late chunking via API.
    This is the easiest way to use late chunking if you have API access.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "jina-embeddings-v3",
        chunk_size: int = 450
    ):
        """
        Initialize Jina late chunker.

        Args:
            api_key: Jina API key (or set JINA_API_KEY env var)
            model: Jina embedding model
            chunk_size: Target chunk size in tokens
        """
        import os
        self.api_key = api_key or os.environ.get("JINA_API_KEY")
        self.model = model
        self.chunk_size = chunk_size

        if not self.api_key:
            logger.warning(
                "No Jina API key provided. Set JINA_API_KEY env var or pass api_key."
            )

    def embed_with_late_chunking(
        self,
        text: str
    ) -> Tuple[List[str], List[np.ndarray]]:
        """
        Embed document with late chunking via Jina API.

        Args:
            text: Document text

        Returns:
            Tuple of (chunks, embeddings)
        """
        if not self.api_key:
            raise ValueError("Jina API key required for late chunking")

        import requests

        response = requests.post(
            "https://api.jina.ai/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "input": [text],
                "model": self.model,
                "late_chunking": True,
                "dimensions": 384  # Match local embedding dimension
            }
        )

        if response.status_code != 200:
            raise RuntimeError(f"Jina API error: {response.text}")

        data = response.json()

        # Extract chunks and embeddings from response
        chunks = []
        embeddings = []

        for item in data.get("data", []):
            if "chunk" in item:
                chunks.append(item["chunk"])
                embeddings.append(np.array(item["embedding"], dtype=np.float32))

        return chunks, embeddings


def create_late_chunker(
    use_jina_api: bool = False,
    jina_api_key: Optional[str] = None,
    chunk_size: int = 450,
    chunk_overlap: int = 50
):
    """
    Factory function to create a late chunker.

    Args:
        use_jina_api: If True, use Jina API for late chunking
        jina_api_key: Jina API key (if using API)
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks

    Returns:
        Late chunker instance
    """
    if use_jina_api:
        return JinaLateChunker(
            api_key=jina_api_key,
            chunk_size=chunk_size
        )
    else:
        return LateChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
