"""
Example: Hybrid LangChain agent using both Enclave secrets and knowledge.

This example demonstrates a complete agent that can:
1. Retrieve API keys and credentials (secrets)
2. Query personalized knowledge (DoRA adapters)
"""

import os
from langchain.agents import initialize_agent, AgentType
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider, EnclaveKnowledgeRetriever

# Configuration
ENCLAVE_API_KEY = os.getenv("ENCLAVE_API_KEY", "vlt_your_api_key_here")
ENCLAVE_BASE_URL = os.getenv(
    "ENCLAVE_BASE_URL",
    "https://keen-curiosity-production-1288.up.railway.app"
)
ADAPTER_ID = os.getenv("ENCLAVE_ADAPTER_ID", "your-adapter-uuid-here")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def main():
    """Run hybrid agent example."""
    
    print("🚀 Initializing hybrid LangChain agent...")
    print("   - Secrets: EnclaveSecretProvider")
    print("   - Knowledge: EnclaveKnowledgeRetriever")
    
    if not OPENAI_API_KEY:
        print("⚠️  Warning: OPENAI_API_KEY not set. Cannot run example.")
        return
    
    # Initialize Enclave tools
    secret_tool = EnclaveSecretProvider(
        api_key=ENCLAVE_API_KEY,
        base_url=ENCLAVE_BASE_URL
    )
    
    knowledge_retriever = EnclaveKnowledgeRetriever(
        adapter_id=ADAPTER_ID if ADAPTER_ID != "your-adapter-uuid-here" else None,
        api_key=ENCLAVE_API_KEY,
        base_url=ENCLAVE_BASE_URL
    )
    
    # Initialize LLM
    llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY)
    
    # Create agent with secrets
    print("\n📦 Creating agent with secret provider...")
    agent = initialize_agent(
        tools=[secret_tool],
        llm=llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=True
    )
    
    # Create QA chain with knowledge
    if ADAPTER_ID and ADAPTER_ID != "your-adapter-uuid-here":
        print("📚 Creating RAG chain with knowledge retriever...")
        qa = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=knowledge_retriever
        )
    else:
        qa = None
        print("⚠️  Knowledge retriever not configured (ENCLAVE_ADAPTER_ID not set)")
    
    print("\n✅ Hybrid agent ready!")
    print("\n📝 Example workflows:")
    print("   1. Retrieve API key: agent.run('Get my OpenAI API key')")
    if qa:
        print("   2. Query knowledge: qa.run('What did I write about project X?')")
        print("   3. Combined: Use agent to get API key, then use it with knowledge")
    
    # Example 1: Retrieve secret
    try:
        print("\n" + "="*60)
        print("Example 1: Retrieving secret")
        print("="*60)
        query = "Get my OpenAI API key"
        print(f"Query: {query}")
        secret_response = agent.run(query)
        print(f"Response: {secret_response[:100]}... (truncated)")
    except Exception as e:
        print(f"❌ Error retrieving secret: {e}")
    
    # Example 2: Query knowledge
    if qa:
        try:
            print("\n" + "="*60)
            print("Example 2: Querying knowledge")
            print("="*60)
            query = "What information do you have about my work?"
            print(f"Query: {query}")
            print("⏳ Querying knowledge adapter (this may take 10-30 seconds)...")
            knowledge_response = qa.run(query)
            print(f"Response: {knowledge_response}")
        except Exception as e:
            print(f"❌ Error querying knowledge: {e}")
    
    print("\n" + "="*60)
    print("✅ Examples complete!")
    print("="*60)


if __name__ == "__main__":
    main()

