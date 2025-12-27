"""Tests for EnclaveSecretProvider."""

import pytest
from unittest.mock import Mock, patch
from langchain_enclave.secrets import EnclaveSecretProvider
from langchain_enclave.exceptions import PolicyViolationError, SecretNotFoundError


@pytest.fixture
def secret_provider():
    """Create EnclaveSecretProvider instance."""
    return EnclaveSecretProvider(
        api_key="vlt_test123",
        base_url="https://test.example.com"
    )


def test_secret_provider_initialization(secret_provider):
    """Test secret provider initialization."""
    assert secret_provider.name == "enclave_secret_provider"
    assert "Retrieve API keys" in secret_provider.description
    assert secret_provider.client is not None


def test_run_success(secret_provider):
    """Test successful secret retrieval."""
    mock_client = Mock()
    mock_client.retrieve_secret.return_value = {
        "success": True,
        "secret": "encrypted_secret",
        "service": "openai"
    }
    secret_provider.client = mock_client
    
    result = secret_provider._run(service="openai")
    
    assert result == "encrypted_secret"
    mock_client.retrieve_secret.assert_called_once_with(
        service="openai",
        tag=None,
        tags=None
    )


def test_run_with_tag(secret_provider):
    """Test secret retrieval with tag."""
    mock_client = Mock()
    mock_client.retrieve_secret.return_value = {
        "success": True,
        "secret": "encrypted_secret",
        "service": "openai"
    }
    secret_provider.client = mock_client
    
    result = secret_provider._run(service="openai", tag="api-keys")
    
    assert result == "encrypted_secret"
    mock_client.retrieve_secret.assert_called_once_with(
        service="openai",
        tag="api-keys",
        tags=None
    )


def test_run_policy_violation(secret_provider):
    """Test policy violation error."""
    mock_client = Mock()
    mock_client.retrieve_secret.side_effect = PolicyViolationError("Access denied")
    secret_provider.client = mock_client
    
    with pytest.raises(PolicyViolationError):
        secret_provider._run(service="openai")


def test_run_secret_not_found(secret_provider):
    """Test secret not found error."""
    mock_client = Mock()
    mock_client.retrieve_secret.side_effect = SecretNotFoundError("Secret not found")
    secret_provider.client = mock_client
    
    with pytest.raises(SecretNotFoundError):
        secret_provider._run(service="nonexistent")

