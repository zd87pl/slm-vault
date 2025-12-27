# LangChain Integration Guide

This guide explains how to integrate Enclave with LangChain for secure secrets management and personalized knowledge retrieval.

## Overview

Enclave provides two main integrations for LangChain:

1. **Secrets Provider**: Retrieve API keys and credentials with policy-based access control
2. **Knowledge Retriever**: Query personalized knowledge via DoRA adapters trained on your documents

## Installation

### Python Package

```bash
pip install langchain-enclave
```

### Prerequisites

- Enclave account (sign up at your Enclave backend)
- API key (create one in the Enclave GUI under "API Keys")
- LangChain installed (`pip install langchain`)

## Quick Start

### 1. Create an API Key

1. Log into Enclave GUI
2. Navigate to "API Keys" section
3. Click "Create API Key"
4. Name it (e.g., "langchain-agent-1") - this name will be used as the agent identifier
5. Save the key (shown only once!)

### 2. Set Up a Policy

Before agents can access secrets or knowledge, you need to create a policy:

```python
import requests

API_KEY = "your-jwt-token-here"  # From GUI login
BASE_URL = "https://your-backend.railway.app"

# Create a policy that allows agent "langchain-agent-1" to access OpenAI secrets
policy = {
    "policy_name": "langchain-general",
    "agent_identifier": "langchain-agent-1",  # Matches API key name
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
    headers={"Authorization": f"Bearer {API_KEY}"}
)
```

### 3. Use in LangChain

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

## Secret Retrieval

### Basic Usage

```python
from langchain_enclave import EnclaveSecretProvider

tool = EnclaveSecretProvider(
    api_key="vlt_abc123...",
    base_url="https://your-backend.railway.app"
)

# Retrieve by service name
secret = tool.run("openai")

# Retrieve by tag
secret = tool.run(tag="api-keys")
```

**Note**: Secrets are returned encrypted (base64). You need to decrypt them client-side with your master key. For production, consider using a helper function or pre-decrypted secrets service.

### Policy Rules

Policy rules control which secrets an agent can access:

- **allow_all**: Agent can access all secrets
- **allow_tags**: Agent can access secrets with specific tags
- **allow_services**: Agent can access specific services
- **deny_services**: Explicitly deny access to specific services

Rules are evaluated in priority order (lower priority = evaluated first).

### Example: Restrictive Policy

```python
# Only allow access to trading API keys
policy = {
    "policy_name": "trading-bot",
    "agent_identifier": "trading-bot-*",
    "secret_rules": [
        {
            "rule_type": "allow_tags",
            "rule_value": {"tags": ["trading-api"]},
            "priority": 0
        },
        {
            "rule_type": "deny_services",
            "rule_value": {"services": ["openai"]},  # Explicitly deny OpenAI
            "priority": 1
        }
    ]
}
```

## Knowledge Retrieval

### Basic Usage

```python
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveKnowledgeRetriever

# Initialize retriever
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

answer = qa.run("What's our Q4 revenue target?")
```

### How It Works

1. **Training**: Train a DoRA adapter on your documents using Enclave GUI
2. **Policy Check**: When querying, Enclave checks if the agent's policy allows access to this adapter
3. **Inference**: Backend runs DoRA inference on RunPod (typically 5-30 seconds)
4. **Response**: Returns generated answer wrapped in a LangChain Document

### Policy Rules for Knowledge

- **allow_all**: Agent can query all adapters
- **allow_adapters**: Agent can query specific adapters (by UUID)
- **deny_adapters**: Explicitly deny access to specific adapters

## Hybrid Agent Example

Combine secrets and knowledge in a single agent:

```python
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_enclave import EnclaveSecretProvider, EnclaveKnowledgeRetriever

# Initialize tools
secret_tool = EnclaveSecretProvider(
    api_key="vlt_abc123...",
    base_url="https://your-backend.railway.app"
)

knowledge_retriever = EnclaveKnowledgeRetriever(
    adapter_id="uuid-of-work-docs",
    api_key="vlt_abc123...",
    base_url="https://your-backend.railway.app"
)

# Create agent with secrets
llm = ChatOpenAI(temperature=0)
agent = initialize_agent(
    tools=[secret_tool],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True
)

# Create QA chain with knowledge
qa = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=knowledge_retriever
)

# Use both:
# 1. Agent retrieves API key
api_key = agent.run("Get my OpenAI API key")

# 2. QA chain queries knowledge
answer = qa.run("What did I write about project X?")
```

## Policy Management

### List Policies

```python
import requests

response = requests.get(
    f"{BASE_URL}/api/langchain/policies",
    headers={"Authorization": f"Bearer {JWT_TOKEN}"}
)

policies = response.json()["policies"]
```

### Update Policy

```python
response = requests.patch(
    f"{BASE_URL}/api/langchain/policies/{policy_id}",
    json={
        "enabled": False,  # Disable policy
        "rate_limits": {
            "max_requests_per_hour": 200  # Update rate limit
        }
    },
    headers={"Authorization": f"Bearer {JWT_TOKEN}"}
)
```

### Test Policy

Test a policy before deploying:

```python
response = requests.post(
    f"{BASE_URL}/api/langchain/policies/test",
    json={
        "agent_identifier": "langchain-agent-1",
        "test_type": "secret",
        "service": "openai"
    },
    headers={"Authorization": f"Bearer {JWT_TOKEN}"}
)

result = response.json()
# {"allowed": True, "reason": "Allowed by policy", "policy_id": "..."}
```

## Rate Limiting

Each policy can have rate limits:

- **max_requests_per_hour**: Maximum requests per hour (default: 100)
- **max_requests_per_day**: Maximum requests per day (default: 1000)

If rate limit is exceeded, requests return `403 Forbidden` with a message.

## Security Best Practices

1. **Use Specific Agent Identifiers**: Instead of `langchain-*`, use `langchain-agent-1` for better control
2. **Principle of Least Privilege**: Only grant access to what agents need
3. **Monitor Access Logs**: Check `/api/logs` regularly for suspicious activity
4. **Rotate API Keys**: Revoke and recreate API keys periodically
5. **Test Policies**: Use `/api/langchain/policies/test` before deploying

## Troubleshooting

### "Policy violation: Access denied"

- Check that a policy exists for your agent identifier
- Verify the policy is enabled
- Check rule priorities and ensure they match your request

### "Rate limit exceeded"

- Check current rate limit usage in policy
- Increase limits if needed, or wait for reset

### "Secret not found"

- Verify the secret exists in your vault
- Check service name/tag matches exactly
- Ensure secret is not soft-deleted

### "Adapter not found"

- Verify adapter_id is correct (UUID format)
- Check adapter status is "completed" (not "pending" or "training")
- Ensure adapter belongs to your user account

## API Reference

See the [Backend API documentation](../../advanced_vault/backend/api/langchain.py) for full endpoint details.

## Examples

See `examples/langchain/` directory for complete working examples:

- `secret_agent.py` - Agent that retrieves API keys
- `knowledge_agent.py` - Agent that queries DoRA adapters
- `hybrid_agent.py` - Agent with both secrets + knowledge

