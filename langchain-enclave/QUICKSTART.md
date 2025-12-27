# Quick Start Guide

Get started with `langchain-enclave` in 5 minutes.

## Prerequisites

- Python 3.8+
- Enclave account (sign up at your Enclave backend)
- LangChain installed (`pip install langchain`)

## Step 1: Install

```bash
pip install langchain-enclave
```

Or install from source:

```bash
git clone https://github.com/your-org/slm-vault
cd slm-vault/langchain-enclave
pip install -e .
```

## Step 2: Get API Key

1. Log into Enclave GUI
2. Go to "API Keys" section
3. Click "Create API Key"
4. Name it (e.g., `my-langchain-agent`)
5. **Save the key** - shown only once!

## Step 3: Create Policy

Create a policy that allows your agent to access secrets:

```python
import requests
import os

# Get JWT token from GUI login (or use session)
JWT_TOKEN = os.getenv("ENCLAVE_JWT_TOKEN")  # From GUI
BASE_URL = os.getenv("ENCLAVE_BASE_URL", "https://your-backend.railway.app")

# Create policy
policy = {
    "policy_name": "my-first-policy",
    "agent_identifier": "my-langchain-agent",  # Must match API key name!
    "enabled": True,
    "secret_rules": [
        {
            "rule_type": "allow_services",
            "rule_value": {"services": ["openai"]},  # Allow OpenAI secrets
            "priority": 0
        }
    ],
    "knowledge_rules": [],  # No knowledge access for now
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

print(response.json())
```

## Step 4: Store a Secret

Store a secret in Enclave (via GUI or API):

```python
# Via GUI: Go to "Secrets" → Add → Service: "openai", Content: "sk-..."
# Or via API (see Enclave docs)
```

## Step 5: Use in LangChain

```python
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider

# Initialize secret provider
secret_tool = EnclaveSecretProvider(
    api_key="vlt_your_api_key_here",
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

# Agent can now retrieve secrets!
response = agent.run("Get my OpenAI API key")
print(response)
```

## Complete Example

```python
import os
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider

# Configuration
ENCLAVE_API_KEY = os.getenv("ENCLAVE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # For LangChain LLM

if not ENCLAVE_API_KEY:
    print("Set ENCLAVE_API_KEY environment variable")
    exit(1)

# Initialize Enclave tool
secret_tool = EnclaveSecretProvider(
    api_key=ENCLAVE_API_KEY,
    base_url="https://your-backend.railway.app"
)

# Create agent
llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY)
agent = initialize_agent(
    tools=[secret_tool],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True
)

# Use agent
response = agent.run("What's my OpenAI API key?")
print(f"Agent response: {response}")
```

## Troubleshooting

### "Policy violation: Access denied"

- Check that policy exists for your agent identifier
- Verify API key name matches policy `agent_identifier` pattern
- Ensure policy is enabled

### "Secret not found"

- Verify secret exists in Enclave vault
- Check service name matches exactly
- Ensure secret is not soft-deleted

### "No matching policy found"

- Create a policy with `agent_identifier` matching your API key name
- Use wildcards if needed (e.g., `langchain-*`)

## Next Steps

- Read [Integration Guide](../../docs/LANGCHAIN_INTEGRATION.md) for detailed docs
- Check [Policy Guide](../../docs/POLICY_GUIDE.md) for policy examples
- See `examples/` directory for more examples

