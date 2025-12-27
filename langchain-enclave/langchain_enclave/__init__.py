"""LangChain integration for Enclave secure vault."""

from langchain_enclave.secrets import EnclaveSecretProvider
from langchain_enclave.knowledge import EnclaveKnowledgeRetriever
from langchain_enclave.client import EnclaveClient
from langchain_enclave.exceptions import (
    EnclaveError,
    PolicyViolationError,
    SecretNotFoundError,
    AdapterNotFoundError,
    RateLimitExceededError
)

__version__ = "0.1.0"

__all__ = [
    "EnclaveSecretProvider",
    "EnclaveKnowledgeRetriever",
    "EnclaveClient",
    "EnclaveError",
    "PolicyViolationError",
    "SecretNotFoundError",
    "AdapterNotFoundError",
    "RateLimitExceededError",
]

