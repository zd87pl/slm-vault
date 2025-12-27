"""Tests for EnclaveClient."""

import pytest
from unittest.mock import Mock, patch
from langchain_enclave.client import EnclaveClient
from langchain_enclave.exceptions import (
    PolicyViolationError,
    SecretNotFoundError,
    AuthenticationError,
    RateLimitExceededError
)


@pytest.fixture
def client():
    """Create EnclaveClient instance."""
    return EnclaveClient(
        api_key="vlt_test123",
        base_url="https://test.example.com"
    )


def test_client_initialization(client):
    """Test client initialization."""
    assert client.api_key == "vlt_test123"
    assert client.base_url == "https://test.example.com"
    assert "Authorization" in client.session.headers
    assert client.session.headers["Authorization"] == "Bearer vlt_test123"


def test_handle_response_success(client):
    """Test successful response handling."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "data": "test"}
    
    result = client._handle_response(mock_response)
    assert result == {"success": True, "data": "test"}


def test_handle_response_authentication_error(client):
    """Test authentication error handling."""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"detail": "Invalid API key"}
    
    with pytest.raises(AuthenticationError):
        client._handle_response(mock_response)


def test_handle_response_policy_violation(client):
    """Test policy violation error handling."""
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.json.return_value = {"detail": "Access denied"}
    
    with pytest.raises(PolicyViolationError):
        client._handle_response(mock_response)


def test_handle_response_rate_limit_exceeded(client):
    """Test rate limit exceeded error handling."""
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.json.return_value = {"detail": "Rate limit exceeded"}
    
    with pytest.raises(RateLimitExceededError):
        client._handle_response(mock_response)


def test_handle_response_secret_not_found(client):
    """Test secret not found error handling."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"detail": "Secret not found"}
    
    with pytest.raises(SecretNotFoundError):
        client._handle_response(mock_response)


@patch('langchain_enclave.client.requests.Session.post')
def test_retrieve_secret_success(mock_post, client):
    """Test successful secret retrieval."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": True,
        "secret": "encrypted_secret_data",
        "service": "openai"
    }
    mock_post.return_value = mock_response
    
    result = client.retrieve_secret(service="openai")
    
    assert result["success"] is True
    assert result["secret"] == "encrypted_secret_data"
    mock_post.assert_called_once()


@patch('langchain_enclave.client.requests.Session.post')
def test_query_knowledge_success(mock_post, client):
    """Test successful knowledge query."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": True,
        "answer": "This is the answer",
        "adapter_id": "adapter1"
    }
    mock_post.return_value = mock_response
    
    result = client.query_knowledge(
        adapter_id="adapter1",
        query="What is this?"
    )
    
    assert result["success"] is True
    assert result["answer"] == "This is the answer"
    mock_post.assert_called_once()

