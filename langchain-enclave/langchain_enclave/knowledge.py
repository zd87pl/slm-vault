"""LangChain Retriever for querying Enclave knowledge adapters."""

from typing import List, Optional
import logging

try:
    from langchain.schema import BaseRetriever, Document
except ImportError:
    raise ImportError(
        "langchain is required. Install with: pip install langchain"
    )

from langchain_enclave.client import EnclaveClient
from langchain_enclave.exceptions import (
    PolicyViolationError,
    AdapterNotFoundError,
    EnclaveError
)

logger = logging.getLogger(__name__)


class EnclaveKnowledgeRetriever(BaseRetriever):
    """
    LangChain retriever for personalized knowledge via DoRA adapters.

    This retriever enables LangChain agents to query personalized knowledge
    stored in Enclave DoRA adapters, providing an alternative to traditional
    RAG approaches.

    Example:
        ```python
        from langchain_enclave import EnclaveKnowledgeRetriever
        from langchain.chains import RetrievalQA
        from langchain.chat_models import ChatOpenAI

        retriever = EnclaveKnowledgeRetriever(
            adapter_id="uuid-of-work-docs-adapter",
            api_key="vlt_abc123...",
            base_url="https://your-backend.railway.app"
        )

        # Use in RetrievalQA chain:
        qa = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(),
            retriever=retriever
        )

        answer = qa.run("What's our Q4 revenue target?")
        ```

    Note: This retriever queries DoRA adapters via RunPod inference,
    which may have latency (typically 5-30 seconds per query).
    """

    adapter_id: Optional[str] = None  # Set in __init__
    client: Optional[EnclaveClient] = None  # Set in __init__
    temperature: float = 0.3
    max_tokens: int = 512

    def __init__(
        self,
        adapter_id: str,
        api_key: str,
        base_url: str = "https://keen-curiosity-production-1288.up.railway.app",
        temperature: float = 0.3,
        max_tokens: int = 512,
        **kwargs
    ):
        """
        Initialize Enclave knowledge retriever.

        Args:
            adapter_id: Adapter UUID to query
            api_key: Enclave API key (starts with "vlt_")
            base_url: Base URL of Enclave backend API
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments passed to BaseRetriever
        """
        super().__init__(**kwargs)
        # Set fields after super().__init__ to avoid Pydantic validation issues
        object.__setattr__(self, 'adapter_id', adapter_id)
        object.__setattr__(self, 'client', EnclaveClient(api_key=api_key, base_url=base_url))
        object.__setattr__(self, 'temperature', temperature)
        object.__setattr__(self, 'max_tokens', max_tokens)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        """
        Query DoRA adapter and return results as Documents.

        Args:
            query: User query string

        Returns:
            List of Document objects (typically single document with answer)

        Raises:
            PolicyViolationError: If access denied by policy
            AdapterNotFoundError: If adapter not found
            EnclaveError: For other errors
        """
        try:
            result = self.client.query_knowledge(
                adapter_id=self.adapter_id,
                query=query,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            answer = result.get("answer", "")
            if not answer:
                logger.warning("Empty answer from adapter")
                answer = "No answer available"

            # Create Document with answer and metadata
            document = Document(
                page_content=answer,
                metadata={
                    "adapter_id": self.adapter_id,
                    "query": query,
                    "source": "enclave_dora_adapter"
                }
            )

            logger.info(f"Retrieved knowledge for query: {query[:50]}...")

            return [document]

        except PolicyViolationError as e:
            logger.warning(f"Policy violation: {e}")
            raise
        except AdapterNotFoundError as e:
            logger.warning(f"Adapter not found: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to query knowledge: {e}")
            raise EnclaveError(f"Failed to query knowledge: {str(e)}")

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        """Async version of _get_relevant_documents."""
        # For now, just call sync version
        # TODO: Implement async HTTP client
        return self._get_relevant_documents(query)

