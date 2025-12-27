"""LangChain Tool for retrieving secrets from Enclave."""

from typing import Optional, Dict, Any
import logging

try:
    from langchain.tools import BaseTool
except ImportError:
    raise ImportError(
        "langchain is required. Install with: pip install langchain"
    )

from langchain_enclave.client import EnclaveClient
from langchain_enclave.exceptions import (
    PolicyViolationError,
    SecretNotFoundError,
    EnclaveError
)

logger = logging.getLogger(__name__)


class EnclaveSecretProvider(BaseTool):
    """
    LangChain tool for retrieving secrets from Enclave vault.

    This tool enables LangChain agents to securely access API keys and credentials
    stored in Enclave, with policy-based access control.

    Example:
        ```python
        from langchain_enclave import EnclaveSecretProvider

        tool = EnclaveSecretProvider(
            api_key="vlt_abc123...",
            base_url="https://your-backend.railway.app"
        )

        # Agent uses this tool:
        secret = tool.run("openai")  # Returns OpenAI API key (encrypted)
        ```

    Note: Secrets are returned encrypted and require client-side decryption
    with the user's master key. For LangChain agents, consider using a
    decrypt helper or pre-decrypted secrets service.
    """

    name: str = "enclave_secret_provider"
    description: str = (
        "Retrieve API keys and secrets from secure Enclave vault. "
        "Input should be a service name (e.g., 'openai', 'github') or a JSON string "
        "with 'service' and optional 'tag' fields. Returns encrypted secret that "
        "needs to be decrypted with master key."
    )
    client: Optional[EnclaveClient] = None  # Set in __init__

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://keen-curiosity-production-1288.up.railway.app",
        **kwargs
    ):
        """
        Initialize Enclave secret provider.

        Args:
            api_key: Enclave API key (starts with "vlt_")
            base_url: Base URL of Enclave backend API
            **kwargs: Additional arguments passed to BaseTool
        """
        super().__init__(**kwargs)
        # Set client after super().__init__ to avoid Pydantic validation issues
        object.__setattr__(self, 'client', EnclaveClient(api_key=api_key, base_url=base_url))

    def _run(
        self,
        service: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list] = None
    ) -> str:
        """
        Retrieve secret with policy enforcement.

        Args:
            service: Service name (e.g., "openai")
            tag: Single tag filter
            tags: Multiple tag filters

        Returns:
            Encrypted secret (base64-encoded string)

        Raises:
            PolicyViolationError: If access denied by policy
            SecretNotFoundError: If secret not found
            EnclaveError: For other errors
        """
        try:
            result = self.client.retrieve_secret(
                service=service,
                tag=tag,
                tags=tags
            )

            # Return encrypted secret (client must decrypt)
            encrypted_secret = result.get("secret", "")
            service_name = result.get("service", service or "unknown")

            logger.info(f"Retrieved secret for service: {service_name}")

            return encrypted_secret

        except PolicyViolationError as e:
            logger.warning(f"Policy violation: {e}")
            raise
        except SecretNotFoundError as e:
            logger.warning(f"Secret not found: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve secret: {e}")
            raise EnclaveError(f"Failed to retrieve secret: {str(e)}")

    async def _arun(
        self,
        service: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list] = None
    ) -> str:
        """Async version of _run."""
        # For now, just call sync version
        # TODO: Implement async HTTP client
        return self._run(service=service, tag=tag, tags=tags)

