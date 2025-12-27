# Changelog

All notable changes to `langchain-enclave` will be documented in this file.

## [0.1.0] - 2024-01-XX

### Added
- Initial release
- `EnclaveSecretProvider` - LangChain Tool for retrieving secrets
- `EnclaveKnowledgeRetriever` - LangChain BaseRetriever for querying DoRA adapters
- `EnclaveClient` - Base API client
- Policy-based access control
- Rate limiting support
- Comprehensive error handling
- Example scripts and documentation

### Features
- Secure secret retrieval with policy enforcement
- Personalized knowledge querying via DoRA adapters
- Wildcard pattern matching for agent identifiers
- Rate limiting per policy
- Audit logging integration

### Documentation
- README with quick start guide
- API reference documentation
- Policy configuration guide
- Example scripts (secrets, knowledge, hybrid)
- Jupyter notebook example

### Testing
- Unit tests for client, secrets, and knowledge components
- Policy engine tests
- Error handling tests

