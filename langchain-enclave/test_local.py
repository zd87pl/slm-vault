#!/usr/bin/env python3
"""
Local test script for langchain-enclave package.
Tests basic functionality without requiring external dependencies or API keys.
"""

import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent))

print("🧪 Testing langchain-enclave package locally...")
print("=" * 60)
print()

# Test 1: Imports
print("✅ Test 1: Package imports")
try:
    from langchain_enclave import (
        EnclaveSecretProvider,
        EnclaveKnowledgeRetriever,
        EnclaveClient,
        EnclaveError,
        PolicyViolationError,
        SecretNotFoundError,
        AdapterNotFoundError,
        RateLimitExceededError
    )
    print("   ✓ All imports successful")
except Exception as e:
    print(f"   ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Package version
print()
print("✅ Test 2: Package version")
try:
    import langchain_enclave
    print(f"   ✓ Version: {langchain_enclave.__version__}")
    print(f"   ✓ Exports: {len(langchain_enclave.__all__)} items")
except Exception as e:
    print(f"   ✗ Version check failed: {e}")
    sys.exit(1)

# Test 3: Class instantiation
print()
print("✅ Test 3: Class instantiation")
try:
    # Test EnclaveSecretProvider
    tool = EnclaveSecretProvider(
        api_key="vlt_test123",
        base_url="https://test.example.com"
    )
    assert tool.name == "enclave_secret_provider"
    assert tool.client is not None
    print("   ✓ EnclaveSecretProvider instantiated")

    # Test EnclaveKnowledgeRetriever
    retriever = EnclaveKnowledgeRetriever(
        adapter_id="test-uuid-123",
        api_key="vlt_test123",
        base_url="https://test.example.com"
    )
    assert retriever.adapter_id == "test-uuid-123"
    assert retriever.temperature == 0.3
    assert retriever.max_tokens == 512
    assert retriever.client is not None
    print("   ✓ EnclaveKnowledgeRetriever instantiated")

    # Test EnclaveClient
    client = EnclaveClient(
        api_key="vlt_test123",
        base_url="https://test.example.com"
    )
    assert client.api_key == "vlt_test123"
    assert client.base_url == "https://test.example.com"
    print("   ✓ EnclaveClient instantiated")
except Exception as e:
    print(f"   ✗ Instantiation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Exception classes
print()
print("✅ Test 4: Exception classes")
try:
    assert issubclass(PolicyViolationError, EnclaveError)
    assert issubclass(SecretNotFoundError, EnclaveError)
    assert issubclass(AdapterNotFoundError, EnclaveError)
    assert issubclass(RateLimitExceededError, EnclaveError)
    print("   ✓ All exception classes inherit from EnclaveError")
except Exception as e:
    print(f"   ✗ Exception class check failed: {e}")
    sys.exit(1)

# Test 5: Tool attributes
print()
print("✅ Test 5: Tool attributes")
try:
    assert hasattr(tool, 'name')
    assert hasattr(tool, 'description')
    assert hasattr(tool, 'client')
    assert hasattr(tool, '_run')
    assert hasattr(tool, '_arun')
    print("   ✓ EnclaveSecretProvider has all required attributes")
except Exception as e:
    print(f"   ✗ Attribute check failed: {e}")
    sys.exit(1)

# Test 6: Retriever attributes
print()
print("✅ Test 6: Retriever attributes")
try:
    assert hasattr(retriever, 'adapter_id')
    assert hasattr(retriever, 'client')
    assert hasattr(retriever, 'temperature')
    assert hasattr(retriever, 'max_tokens')
    assert hasattr(retriever, '_get_relevant_documents')
    assert hasattr(retriever, '_aget_relevant_documents')
    print("   ✓ EnclaveKnowledgeRetriever has all required attributes")
except Exception as e:
    print(f"   ✗ Attribute check failed: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("🎉 All local tests passed!")
print()
print("📝 Next steps:")
print("   1. Install LangChain: pip install langchain langchain-community")
print("   2. Set ENCLAVE_API_KEY environment variable")
print("   3. Run examples: python examples/secrets_example.py")
print()

