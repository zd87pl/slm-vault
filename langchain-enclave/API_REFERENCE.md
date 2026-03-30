# API Reference

Complete API reference for `langchain-enclave`.

## EnclaveSecretProvider

LangChain Tool for retrieving secrets from Enclave vault.

### Class Definition

```python
class EnclaveSecretProvider(BaseTool):
    name = "enclave_secret_provider"
    description = "Retrieve API keys and secrets from secure Enclave vault"
```

### Initialization

```python
EnclaveSecretProvider(
    api_key: str,
    base_url: str = "https://keen-curiosity-production-1288.up.railway.app",
    **kwargs
)
```

**Parameters:**
- `api_key` (str, required): Enclave API key (starts with `vlt_`)
- `base_url` (str, optional): Backend API URL
- `**kwargs`: Additional arguments passed to `BaseTool`

### Methods

#### `_run(service: Optional[str] = None, tag: Optional[str] = None, tags: Optional[list] = None) -> str`

Retrieve secret with policy enforcement.

**Parameters:**
- `service` (str, optional): Service name (e.g., "openai", "github")
- `tag` (str, optional): Single tag filter
- `tags` (list, optional): Multiple tag filters

**Returns:** Encrypted secret (base64-encoded string)

**Raises:**
- `PolicyViolationError`: If access denied by policy
- `SecretNotFoundError`: If secret not found
- `EnclaveError`: For other errors

**Example:**

```python
tool = EnclaveSecretProvider(api_key="vlt_...")

# Retrieve by service
secret = tool.run("openai")

# Retrieve by tag
secret = tool.run(tag="api-keys")
```

## EnclaveKnowledgeRetriever

LangChain BaseRetriever for querying personalized knowledge via DoRA adapters.

### Class Definition

```python
class EnclaveKnowledgeRetriever(BaseRetriever):
```

### Initialization

```python
EnclaveKnowledgeRetriever(
    adapter_id: str,
    api_key: str,
    base_url: str = "https://keen-curiosity-production-1288.up.railway.app",
    temperature: float = 0.3,
    max_tokens: int = 512,
    **kwargs
)
```

**Parameters:**
- `adapter_id` (str, required): Adapter UUID to query
- `api_key` (str, required): Enclave API key
- `base_url` (str, optional): Backend API URL
- `temperature` (float, optional): Generation temperature (0.0-1.0, default: 0.3)
- `max_tokens` (int, optional): Maximum tokens to generate (default: 512)
- `**kwargs`: Additional arguments passed to `BaseRetriever`

### Methods

#### `_get_relevant_documents(query: str) -> List[Document]`

Query DoRA adapter and return results as Documents.

**Parameters:**
- `query` (str, required): User query string

**Returns:** List of `Document` objects (typically single document with answer)

**Raises:**
- `PolicyViolationError`: If access denied by policy
- `AdapterNotFoundError`: If adapter not found
- `EnclaveError`: For other errors

**Example:**

```python
retriever = EnclaveKnowledgeRetriever(
    adapter_id="uuid-123",
    api_key="vlt_..."
)

documents = retriever.get_relevant_documents("What is this about?")
print(documents[0].page_content)  # Generated answer
```

## EnclaveClient

Base API client for Enclave backend (used internally by tools).

### Class Definition

```python
class EnclaveClient:
```

### Initialization

```python
EnclaveClient(
    api_key: str,
    base_url: str = "https://keen-curiosity-production-1288.up.railway.app"
)
```

### Methods

#### `retrieve_secret(service: Optional[str] = None, tag: Optional[str] = None, tags: Optional[list] = None) -> Dict[str, Any]`

Retrieve secret from Enclave.

**Returns:** Dict with `success`, `secret`, `service`, `entry_id`

#### `list_secrets() -> Dict[str, Any]`

List available secrets (metadata only).

**Returns:** Dict with `secrets` list and `count`

#### `query_knowledge(adapter_id: str, query: str, temperature: float = 0.3, max_tokens: int = 512) -> Dict[str, Any]`

Query knowledge adapter.

**Returns:** Dict with `success`, `answer`, `adapter_id`

#### `list_knowledge_adapters() -> Dict[str, Any]`

List available knowledge adapters.

**Returns:** Dict with `adapters` list and `count`

## LocalEnclaveClient

Local runtime for private files, secrets, and local model chat.

### Class Definition

```python
class LocalEnclaveClient:
```

### Initialization

```python
LocalEnclaveClient(
    vault_path: str = "~/.vault",
    master_key: Optional[bytes] = None,
    vault: Any = None,
    rag_index: Any = None,
    inference_engine: Any = None,
    model_name: Optional[str] = None,
    top_k: int = 5,
    similarity_threshold: float = 0.3,
    max_context_chars: int = 8000,
)
```

### Methods

#### `ingest_file(file_path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

Read a local file and add it to the encrypted RAG index.

#### `ingest_directory(directory: str, patterns: Optional[Sequence[str]] = None, recursive: bool = True, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

Ingest multiple files from a local directory.

#### `chat(query: str, **kwargs) -> Dict[str, Any]`

Convenience alias for local knowledge queries.

#### `query_knowledge(query: str, temperature: float = 0.2, max_tokens: int = 512, top_k: Optional[int] = None, threshold: Optional[float] = None, use_model: bool = True) -> Dict[str, Any]`

Query local files and, when available, generate an answer with a local model.

#### `store_secret(service: str, content: str, tags: Optional[List[str]] = None, description: Optional[str] = None) -> Dict[str, Any]`

Store a plaintext secret in the local encrypted vault.

#### `retrieve_secret(service: Optional[str] = None, tag: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]`

Retrieve a plaintext secret from the local vault.

#### `list_secrets() -> Dict[str, Any]`

List secret metadata only.

#### `list_documents() -> Dict[str, Any]`

List documents in the local encrypted RAG index.

#### `load_model() -> Dict[str, Any]`

Load the local model if available.

## LocalEnclaveKnowledgeRetriever

LangChain retriever backed by the local private-model workflow.

### Class Definition

```python
class LocalEnclaveKnowledgeRetriever(BaseRetriever):
```

### Initialization

```python
LocalEnclaveKnowledgeRetriever(
    vault_path: str = "~/.vault",
    client: Optional[LocalEnclaveClient] = None,
    top_k: int = 5,
    similarity_threshold: float = 0.3,
    temperature: float = 0.2,
    max_tokens: int = 512,
    use_model: bool = True,
    **kwargs
)
```

### Methods

#### `_get_relevant_documents(query: str) -> List[Document]`

Return a single synthesized answer document from local file context.

## LocalEnclaveSecretProvider

LangChain tool for retrieving plaintext secrets from the local vault.

### Class Definition

```python
class LocalEnclaveSecretProvider(BaseTool):
```

### Initialization

```python
LocalEnclaveSecretProvider(
    vault_path: str = "~/.vault",
    client: Optional[LocalEnclaveClient] = None,
    **kwargs
)
```

### Methods

#### `_run(service: Optional[str] = None, tag: Optional[str] = None, tags: Optional[list] = None) -> str`

Retrieve a local plaintext secret.

## Exceptions

### EnclaveError

Base exception for all Enclave errors.

```python
class EnclaveError(Exception):
    pass
```

### PolicyViolationError

Raised when agent violates access policy.

```python
class PolicyViolationError(EnclaveError):
    pass
```

### SecretNotFoundError

Raised when requested secret is not found.

```python
class SecretNotFoundError(EnclaveError):
    pass
```

### AdapterNotFoundError

Raised when requested adapter is not found.

```python
class AdapterNotFoundError(EnclaveError):
    pass
```

### RateLimitExceededError

Raised when rate limit is exceeded.

```python
class RateLimitExceededError(EnclaveError):
    pass
```

### AuthenticationError

Raised when API key authentication fails.

```python
class AuthenticationError(EnclaveError):
    pass
```

## Usage Examples

### Basic Secret Retrieval

```python
from langchain_enclave import EnclaveSecretProvider

tool = EnclaveSecretProvider(api_key="vlt_...")
secret = tool.run("openai")
```

### Secret Retrieval with Error Handling

```python
from langchain_enclave import EnclaveSecretProvider
from langchain_enclave.exceptions import PolicyViolationError, SecretNotFoundError

tool = EnclaveSecretProvider(api_key="vlt_...")

try:
    secret = tool.run("openai")
except PolicyViolationError as e:
    print(f"Access denied: {e}")
except SecretNotFoundError as e:
    print(f"Secret not found: {e}")
```

### Knowledge Query

```python
from langchain_enclave import EnclaveKnowledgeRetriever

retriever = EnclaveKnowledgeRetriever(
    adapter_id="uuid-123",
    api_key="vlt_..."
)

documents = retriever.get_relevant_documents("What did I write about project X?")
answer = documents[0].page_content
```

### Using in LangChain Agent

```python
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider

tool = EnclaveSecretProvider(api_key="vlt_...")
llm = ChatOpenAI()

agent = initialize_agent(
    tools=[tool],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS
)

response = agent.run("Get my OpenAI API key")
```

### Using in RetrievalQA Chain

```python
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveKnowledgeRetriever

retriever = EnclaveKnowledgeRetriever(
    adapter_id="uuid-123",
    api_key="vlt_..."
)

qa = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(),
    retriever=retriever
)

answer = qa.run("What's our Q4 revenue target?")
```
