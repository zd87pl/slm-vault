# Community Examples

Ready-to-use examples for sharing with the LangChain community.

## Quick Copy-Paste Examples

### Minimal Example (30 seconds)

```python
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider

# Initialize
secret_tool = EnclaveSecretProvider(
    api_key="vlt_your_key",
    base_url="https://your-backend.railway.app"
)

# Use in agent
agent = initialize_agent(
    tools=[secret_tool],
    llm=ChatOpenAI(),
    agent=AgentType.OPENAI_FUNCTIONS
)

# Agent retrieves secrets!
agent.run("Get my OpenAI API key")
```

### RAG Example (1 minute)

```python
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveKnowledgeRetriever

# Initialize retriever
retriever = EnclaveKnowledgeRetriever(
    adapter_id="your-adapter-uuid",
    api_key="vlt_your_key",
    base_url="https://your-backend.railway.app"
)

# Use in RAG chain
qa = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(),
    retriever=retriever
)

# Query personalized knowledge
answer = qa.run("What's in my documents about project X?")
```

## Use Case Examples

### Use Case 1: Multi-Agent System

```python
# Agent 1: Trading bot (only trading API keys)
trading_tool = EnclaveSecretProvider(
    api_key="vlt_trading_bot_key",
    base_url="https://your-backend.railway.app"
)

# Agent 2: Research assistant (only knowledge)
research_retriever = EnclaveKnowledgeRetriever(
    adapter_id="research-adapter-uuid",
    api_key="vlt_research_bot_key",
    base_url="https://your-backend.railway.app"
)

# Different policies control access per agent
```

### Use Case 2: Secure API Key Rotation

```python
# Store API keys in Enclave
# Agents retrieve them dynamically
# Rotate keys without code changes

secret_tool = EnclaveSecretProvider(api_key="vlt_...")
agent = initialize_agent(tools=[secret_tool], llm=ChatOpenAI())

# Agent always gets latest key
response = agent.run("Get my Stripe API key")
```

### Use Case 3: Personalized Knowledge Base

```python
# Train DoRA adapter on your documents
# Query via LangChain instead of vector search

retriever = EnclaveKnowledgeRetriever(
    adapter_id="work-docs-adapter",
    api_key="vlt_..."
)

qa = RetrievalQA.from_chain_type(llm=ChatOpenAI(), retriever=retriever)

# More accurate than traditional RAG
answer = qa.run("What's our Q4 strategy?")
```

## Comparison Examples

### Traditional vs Enclave Secret Management

**Traditional (hardcoded):**
```python
# ❌ Hardcoded secrets
OPENAI_API_KEY = "sk-abc123..."
```

**With Enclave:**
```python
# ✅ Secure, policy-controlled
from langchain_enclave import EnclaveSecretProvider
tool = EnclaveSecretProvider(api_key="vlt_...")
agent = initialize_agent(tools=[tool], llm=ChatOpenAI())
# Agent retrieves key dynamically
```

### Traditional RAG vs Enclave Knowledge

**Traditional RAG:**
```python
# Vector search over documents
from langchain.vectorstores import Chroma
vectorstore = Chroma.from_documents(documents)
retriever = vectorstore.as_retriever()
```

**Enclave Knowledge:**
```python
# Fine-tuned adapter (more accurate)
from langchain_enclave import EnclaveKnowledgeRetriever
retriever = EnclaveKnowledgeRetriever(
    adapter_id="adapter-uuid",
    api_key="vlt_..."
)
```

## Social Media Snippets

### Twitter Thread

```
🧵 New LangChain integration: langchain-enclave

1/ Secure secrets & personalized knowledge for LangChain agents
2/ Policy-based access control (who can access what)
3/ Rate limiting & audit logging
4/ Works with any LangChain agent

pip install langchain-enclave

#LangChain #AI #Security
```

### LinkedIn Post

```
Excited to share langchain-enclave - a new integration for LangChain that brings enterprise-grade security to AI agents.

Key features:
🔐 Policy-based access control
📚 Personalized knowledge via fine-tuned adapters  
⚡ Rate limiting and audit logging

Perfect for production deployments where security matters.

Try it: pip install langchain-enclave
```

### Reddit Post

```
[P] langchain-enclave - Secure secrets & knowledge for LangChain

Built an integration that adds:
- Secure API key management with policies
- Personalized knowledge via DoRA adapters
- Rate limiting and audit logging

Use cases:
- Multi-agent systems
- Secure credential management
- Personalized RAG

GitHub: [link]
PyPI: pip install langchain-enclave

Open source, MIT licensed. Feedback welcome!
```

