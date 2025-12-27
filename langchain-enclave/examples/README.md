# Examples

Complete working examples for `langchain-enclave`.

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install langchain-enclave langchain openai
   ```

2. **Set environment variables:**
   ```bash
   export ENCLAVE_API_KEY="vlt_your_api_key_here"
   export ENCLAVE_BASE_URL="https://your-backend.railway.app"  # Optional
   export ENCLAVE_ADAPTER_ID="your-adapter-uuid"  # For knowledge examples
   export OPENAI_API_KEY="sk-your-openai-key"  # For LangChain LLM
   ```

3. **Create a policy** (see [Quick Start](../QUICKSTART.md))

## Examples

### 1. Secrets Example

**File:** `secrets_example.py`

Basic example of retrieving secrets with LangChain agent.

```bash
python examples/secrets_example.py
```

**What it does:**
- Creates a LangChain agent with `EnclaveSecretProvider` tool
- Agent can request secrets (e.g., "Get my OpenAI API key")
- Policy enforcement ensures only authorized access

### 2. Knowledge RAG Example

**File:** `knowledge_rag_example.py`

RAG using personalized knowledge adapters.

```bash
export ENCLAVE_ADAPTER_ID="your-adapter-uuid"
python examples/knowledge_rag_example.py
```

**What it does:**
- Creates a RetrievalQA chain with `EnclaveKnowledgeRetriever`
- Queries DoRA adapter trained on your documents
- Returns personalized answers

### 3. Hybrid Agent Example

**File:** `hybrid_agent_example.py`

Combined agent using both secrets and knowledge.

```bash
export ENCLAVE_ADAPTER_ID="your-adapter-uuid"
python examples/hybrid_agent_example.py
```

**What it does:**
- Agent with secret provider (for API keys)
- RAG chain with knowledge retriever (for documents)
- Demonstrates both capabilities in one workflow

## Customization

All examples use environment variables for configuration. You can:

1. **Modify API endpoints:**
   ```python
   tool = EnclaveSecretProvider(
       api_key=os.getenv("ENCLAVE_API_KEY"),
       base_url=os.getenv("ENCLAVE_BASE_URL", "https://custom-backend.com")
   )
   ```

2. **Adjust generation parameters:**
   ```python
   retriever = EnclaveKnowledgeRetriever(
       adapter_id="uuid",
       api_key="vlt_...",
       temperature=0.7,  # More creative
       max_tokens=1024   # Longer responses
   )
   ```

3. **Add error handling:**
   ```python
   from langchain_enclave.exceptions import PolicyViolationError

   try:
       secret = tool.run("openai")
   except PolicyViolationError:
       print("Access denied - check your policy")
   ```

## Troubleshooting

### "Policy violation: Access denied"
- Verify policy exists for your agent identifier
- Check API key name matches policy pattern
- Ensure policy is enabled

### "Secret not found"
- Verify secret exists in Enclave vault
- Check service name matches exactly

### "Adapter not found"
- Verify adapter_id is correct (UUID format)
- Check adapter status is "completed"

### Import errors
- Ensure `langchain-enclave` is installed: `pip install -e .`
- Check Python version (3.8+)

## Next Steps

- Read [API Reference](../API_REFERENCE.md) for detailed API docs
- Check [Integration Guide](../../docs/LANGCHAIN_INTEGRATION.md) for advanced usage
- See [Policy Guide](../../docs/POLICY_GUIDE.md) for policy examples

