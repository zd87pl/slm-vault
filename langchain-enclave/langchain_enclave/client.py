"""Base Enclave API client."""

import requests
from typing import Optional, Dict, Any
import logging

from langchain_enclave.exceptions import (
    EnclaveError,
    PolicyViolationError,
    SecretNotFoundError,
    AdapterNotFoundError,
    RateLimitExceededError,
    AuthenticationError
)

logger = logging.getLogger(__name__)


class EnclaveClient:
    """Base client for Enclave API interactions."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://keen-curiosity-production-1288.up.railway.app"
    ):
        """
        Initialize Enclave client.

        Args:
            api_key: Enclave API key (starts with "vlt_")
            base_url: Base URL of Enclave backend API
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response and raise appropriate exceptions.

        Args:
            response: Requests response object

        Returns:
            JSON response data

        Raises:
            AuthenticationError: If API key is invalid
            PolicyViolationError: If access is denied by policy
            RateLimitExceededError: If rate limit exceeded
            SecretNotFoundError: If secret not found
            AdapterNotFoundError: If adapter not found
            EnclaveError: For other errors
        """
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key or authentication failed")

        if response.status_code == 403:
            detail = response.json().get("detail", "Access denied")
            if "rate limit" in detail.lower():
                raise RateLimitExceededError(detail)
            raise PolicyViolationError(detail)

        if response.status_code == 404:
            detail = response.json().get("detail", "Resource not found")
            if "secret" in detail.lower():
                raise SecretNotFoundError(detail)
            if "adapter" in detail.lower():
                raise AdapterNotFoundError(detail)
            raise EnclaveError(detail)

        if response.status_code >= 500:
            detail = response.json().get("detail", "Server error")
            raise EnclaveError(f"Server error: {detail}")

        try:
            return response.json()
        except ValueError:
            raise EnclaveError(f"Invalid JSON response: {response.text}")

    def retrieve_secret(
        self,
        service: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Retrieve secret from Enclave.

        Args:
            service: Service name (e.g., "openai")
            tag: Single tag filter
            tags: Multiple tag filters

        Returns:
            Dict with secret data (encrypted - needs client-side decryption)

        Raises:
            PolicyViolationError: If access denied
            SecretNotFoundError: If secret not found
        """
        url = f"{self.base_url}/api/langchain/secrets/retrieve"
        payload = {}
        if service:
            payload["service"] = service
        if tag:
            payload["tag"] = tag
        if tags:
            payload["tags"] = tags

        response = self.session.post(url, json=payload)
        return self._handle_response(response)

    def list_secrets(self) -> Dict[str, Any]:
        """
        List available secrets (metadata only).

        Returns:
            Dict with list of secrets (metadata only, no encrypted data)
        """
        url = f"{self.base_url}/api/langchain/secrets/list"
        response = self.session.get(url)
        return self._handle_response(response)

    def query_knowledge(
        self,
        adapter_id: str,
        query: str,
        temperature: float = 0.3,
        max_tokens: int = 512
    ) -> Dict[str, Any]:
        """
        Query knowledge adapter.

        Args:
            adapter_id: Adapter UUID
            query: User query
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dict with answer

        Raises:
            PolicyViolationError: If access denied
            AdapterNotFoundError: If adapter not found
        """
        url = f"{self.base_url}/api/langchain/knowledge/query"
        payload = {
            "adapter_id": adapter_id,
            "query": query,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = self.session.post(url, json=payload)
        return self._handle_response(response)

    def list_knowledge_adapters(self) -> Dict[str, Any]:
        """
        List available knowledge adapters.

        Returns:
            Dict with list of adapters (metadata only)
        """
        url = f"{self.base_url}/api/langchain/knowledge/list"
        response = self.session.get(url)
        return self._handle_response(response)

