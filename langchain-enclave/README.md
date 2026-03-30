# langchain-enclave

🔐 **Secure secrets and personalized knowledge for LangChain agents**

`langchain-enclave` integrates [Enclave](https://github.com/your-org/slm-vault) with LangChain, enabling agents to securely access API keys, credentials, and personalized knowledge with policy-based authorization.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

✨ **Secure Secrets Management**
- Retrieve API keys and credentials with policy-based access control
- Encrypted storage with client-side decryption
- Rate limiting and audit logging

🧠 **Personalized Knowledge**
- Query DoRA adapters trained on your documents
- Alternative to traditional RAG with fine-tuned knowledge
- Policy-controlled access to knowledge adapters

🏠 **Local-First Workflow**
- Ingest local files into the encrypted private RAG index
- Chat locally over your own files without a remote backend
- Use local LangChain retrievers and tools for OpenClaw or agent workflows

🔒 **Policy-Based Security**
- Fine-grained access control per agent
- Wildcard pattern matching for agent identifiers
- Rate limiting and access logging

## Installation

```bash
pip install langchain-enclave
```

For the local-first workflow in this monorepo, install the repo root in editable mode so
`advanced_vault` is importable:

```bash
cd /path/to/slm-vault
pip install -e .
```

## Local-First Quick Start

```python
from langchain_enclave import LocalEnclaveClient, LocalEnclaveKnowledgeRetriever

client = LocalEnclaveClient(vault_path="~/.vault", profile_name="research")
client.ingest_directory("/path/to/private/files")

result = client.chat("What are the main themes across my files?")
print(result["answer"])

retriever = LocalEnclaveKnowledgeRetriever(vault_path="~/.vault")
docs = retriever.get_relevant_documents("Summarize the files")
print(docs[0].page_content)
```

When `advanced_vault.private_models` is available, the local client uses the same
Private Language Model profile runtime as the CLI and OpenClaw plugin. That means:

- encrypted file context stays under one named profile
- WDVA adapters attach to the same profile used by local chat
- LangChain, CLI, and OpenClaw can share one local private knowledge boundary

The local client supports:

- `ingest_file()` and `ingest_directory()` for private files
- `store_secret()` and `retrieve_secret()` for local secrets
- `chat()` and `query_knowledge()` for local file Q&A
- `LocalEnclaveSecretProvider` and `LocalEnclaveKnowledgeRetriever` for LangChain

## Quick Start

### 1. Get Your API Key

1. Sign up at [Enclave](https://your-backend.railway.app) (or use your existing account)
2. Navigate to "API Keys" section
3. Create a new API key (name it, e.g., `langchain-agent-1`)
4. Save the key - it's shown only once!

### 2. Create a Policy

Before agents can access secrets, create a policy:

```python
import requests

# Use your JWT token from GUI login
JWT_TOKEN = "your-jwt-token"
BASE_URL = "https://your-backend.railway.app"

policy = {
    "policy_name": "langchain-general",
    "agent_identifier": "langchain-agent-1",  # Matches your API key name
    "enabled": True,
    "secret_rules": [
        {
            "rule_type": "allow_services",
            "rule_value": {"services": ["openai", "anthropic"]},
            "priority": 0
        }
    ],
    "knowledge_rules": [
        {
            "rule_type": "allow_all",
            "rule_value": {},
            "priority": 0
        }
    ],
    "rate_limits": {
        "max_requests_per_hour": 100,
        "max_requests_per_day": 1000
    }
}

response = requests.post(
    f"{BASE_URL}/api/langchain/policies",
    json=policy,
    headers={"Authorization": f"Bearer {JWT_TOKEN}"}
)
```

### 3. Use in LangChain

#### Secrets Provider

```python
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider

# Initialize secret provider
secret_tool = EnclaveSecretProvider(
    api_key="vlt_abc123...",  # Your API key
    base_url="https://your-backend.railway.app"
)

# Create agent
llm = ChatOpenAI(temperature=0)
agent = initialize_agent(
    tools=[secret_tool],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True
)

# Agent can now retrieve secrets
response = agent.run("Get my OpenAI API key")
```

#### Knowledge Retriever

```python
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveKnowledgeRetriever

# Initialize knowledge retriever
retriever = EnclaveKnowledgeRetriever(
    adapter_id="uuid-of-your-adapter",
    api_key="vlt_abc123...",
    base_url="https://your-backend.railway.app"
)

# Use in RetrievalQA chain
qa = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(),
    retriever=retriever
)

answer = qa.run("What's in my work documents about project X?")
```

## Examples

See the `examples/` directory for complete working examples:

- **`secrets_example.py`** - Agent that retrieves API keys
- **`knowledge_rag_example.py`** - RAG with personalized knowledge
- **`hybrid_agent_example.py`** - Combined secrets + knowledge

Run an example:

```bash
export ENCLAVE_API_KEY="vlt_your_key_here"
export OPENAI_API_KEY="sk-your-openai-key"
python examples/secrets_example.py
```

## API Reference

### EnclaveSecretProvider

LangChain Tool for retrieving secrets.

```python
from langchain_enclave import EnclaveSecretProvider

tool = EnclaveSecretProvider(
    api_key="vlt_...",
    base_url="https://your-backend.railway.app"
)

# Use in agent
secret = tool.run("openai")  # Returns encrypted secret
```

**Parameters:**
- `api_key` (str): Enclave API key (starts with `vlt_`)
- `base_url` (str): Backend API URL (default: production URL)

**Returns:** Encrypted secret (base64-encoded string) - requires client-side decryption

### EnclaveKnowledgeRetriever

LangChain BaseRetriever for querying personalized knowledge.

```python
from langchain_enclave import EnclaveKnowledgeRetriever

retriever = EnclaveKnowledgeRetriever(
    adapter_id="uuid",
    api_key="vlt_...",
    base_url="https://your-backend.railway.app",
    temperature=0.3,
    max_tokens=512
)

# Use in RetrievalQA
documents = retriever.get_relevant_documents("What is this about?")
```

**Parameters:**
- `adapter_id` (str): Adapter UUID to query
- `api_key` (str): Enclave API key
- `base_url` (str): Backend API URL
- `temperature` (float): Generation temperature (0.0-1.0, default: 0.3)
- `max_tokens` (int): Maximum tokens to generate (default: 512)

**Returns:** List of `Document` objects with answers

### LocalEnclaveClient

Local runtime for private files and vault access.

```python
from langchain_enclave import LocalEnclaveClient

client = LocalEnclaveClient(vault_path="~/.vault")
client.ingest_directory("/path/to/files")
answer = client.chat("What did I write about project X?")
```

Optional arguments:

- `profile_name`: named Private Language Model profile to use locally
- `use_private_profiles`: force profile mode on or off

### LocalEnclaveKnowledgeRetriever

LangChain retriever backed by the local private-model workflow.

```python
from langchain_enclave import LocalEnclaveKnowledgeRetriever

retriever = LocalEnclaveKnowledgeRetriever(vault_path="~/.vault")
docs = retriever.get_relevant_documents("Summarize my notes")
```

### LocalEnclaveSecretProvider

LangChain tool for retrieving plaintext secrets from the local vault.

```python
from langchain_enclave import LocalEnclaveSecretProvider

tool = LocalEnclaveSecretProvider(vault_path="~/.vault")
secret = tool.run("openai")
```

## Policy Configuration

Policies control what agents can access. Key concepts:

- **Agent Identifier**: Derived from API key name (e.g., `langchain-agent-1`)
- **Pattern Matching**: Supports wildcards (e.g., `langchain-*` matches all agents starting with `langchain-`)
- **Rule Types**: `allow_all`, `allow_services`, `allow_tags`, `deny_services`
- **Rate Limits**: Per-policy limits (requests/hour, requests/day)

See [Policy Guide](../../docs/POLICY_GUIDE.md) for detailed examples.

## Use Cases

### 1. Secure API Key Management

Instead of hardcoding API keys, store them in Enclave and let agents retrieve them:

```python
# Agent can request: "Get my Stripe API key"
# Enclave checks policy → returns encrypted key → agent decrypts → uses key
```

### 2. Personalized RAG

Train DoRA adapters on your documents, then query them via LangChain:

```python
# Traditional RAG: Vector search over documents
# Enclave RAG: Query fine-tuned adapter trained on your documents
# → More accurate, personalized answers
```

### 3. Multi-Agent Systems

Different agents with different access levels:

```python
# Trading bot: Only trading API keys
# Research assistant: Only knowledge adapters
# General assistant: Both secrets and knowledge
```

## Security

- **Encryption**: All secrets encrypted with ChaCha20-Poly1305
- **Policy Enforcement**: Every request checked against policies
- **Rate Limiting**: Built-in protection against abuse
- **Audit Logging**: All access attempts logged

## Requirements

- Python 3.8+
- LangChain 0.0.200+
- Enclave account and API key

## Documentation

- [Integration Guide](../../docs/LANGCHAIN_INTEGRATION.md) - Complete integration guide
- [Policy Guide](../../docs/POLICY_GUIDE.md) - Policy configuration examples
- [API Reference](../../docs/API_REFERENCE.md) - Full API documentation

## Contributing

Contributions welcome! Please see our [Contributing Guide](../../CONTRIBUTING.md).

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/slm-vault/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/slm-vault/discussions)
- **Email**: support@enclave.dev

## Related Projects

- [Enclave](https://github.com/your-org/slm-vault) - Main Enclave vault project
- [LangChain](https://github.com/langchain-ai/langchain) - LangChain framework
