"""Tests for EnclaveKnowledgeRetriever."""

import pytest
from unittest.mock import Mock, patch
from langchain.schema import Document
from langchain_enclave.knowledge import EnclaveKnowledgeRetriever
from langchain_enclave.exceptions import PolicyViolationError, AdapterNotFoundError


@pytest.fixture
def knowledge_retriever():
    """Create EnclaveKnowledgeRetriever instance."""
    return EnclaveKnowledgeRetriever(
        adapter_id="adapter-uuid-123",
        api_key="vlt_test123",
        base_url="https://test.example.com"
    )


def test_knowledge_retriever_initialization(knowledge_retriever):
    """Test knowledge retriever initialization."""
    assert knowledge_retriever.adapter_id == "adapter-uuid-123"
    assert knowledge_retriever.temperature == 0.3
    assert knowledge_retriever.max_tokens == 512
    assert knowledge_retriever.client is not None


def test_get_relevant_documents_success(knowledge_retriever):
    """Test successful knowledge retrieval."""
    mock_client = Mock()
    mock_client.query_knowledge.return_value = {
        "success": True,
        "answer": "This is the answer to your question",
        "adapter_id": "adapter-uuid-123"
    }
    knowledge_retriever.client = mock_client
    
    documents = knowledge_retriever._get_relevant_documents("What is this?")
    
    assert len(documents) == 1
    assert isinstance(documents[0], Document)
    assert documents[0].page_content == "This is the answer to your question"
    assert documents[0].metadata["adapter_id"] == "adapter-uuid-123"
    assert documents[0].metadata["source"] == "enclave_dora_adapter"
    
    mock_client.query_knowledge.assert_called_once_with(
        adapter_id="adapter-uuid-123",
        query="What is this?",
        temperature=0.3,
        max_tokens=512
    )


def test_get_relevant_documents_empty_answer(knowledge_retriever):
    """Test handling of empty answer."""
    mock_client = Mock()
    mock_client.query_knowledge.return_value = {
        "success": True,
        "answer": "",
        "adapter_id": "adapter-uuid-123"
    }
    knowledge_retriever.client = mock_client
    
    documents = knowledge_retriever._get_relevant_documents("What is this?")
    
    assert len(documents) == 1
    assert documents[0].page_content == "No answer available"


def test_get_relevant_documents_policy_violation(knowledge_retriever):
    """Test policy violation error."""
    mock_client = Mock()
    mock_client.query_knowledge.side_effect = PolicyViolationError("Access denied")
    knowledge_retriever.client = mock_client
    
    with pytest.raises(PolicyViolationError):
        knowledge_retriever._get_relevant_documents("What is this?")


def test_get_relevant_documents_adapter_not_found(knowledge_retriever):
    """Test adapter not found error."""
    mock_client = Mock()
    mock_client.query_knowledge.side_effect = AdapterNotFoundError("Adapter not found")
    knowledge_retriever.client = mock_client
    
    with pytest.raises(AdapterNotFoundError):
        knowledge_retriever._get_relevant_documents("What is this?")

