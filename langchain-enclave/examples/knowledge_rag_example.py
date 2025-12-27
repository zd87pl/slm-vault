"""
Example: LangChain RAG using Enclave knowledge adapters.

This example shows how to use EnclaveKnowledgeRetriever to query
personalized knowledge stored in DoRA adapters.
"""

import os
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveKnowledgeRetriever

# Configuration
ENCLAVE_API_KEY = os.getenv("ENCLAVE_API_KEY", "vlt_your_api_key_here")
ENCLAVE_BASE_URL = os.getenv(
    "ENCLAVE_BASE_URL",
    "https://keen-curiosity-production-1288.up.railway.app"
)
ADAPTER_ID = os.getenv("ENCLAVE_ADAPTER_ID", "your-adapter-uuid-here")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def main():
    """Run example RAG with Enclave knowledge retriever."""
    
    print("🚀 Initializing LangChain RAG with Enclave knowledge retriever...")
    
    if not ADAPTER_ID or ADAPTER_ID == "your-adapter-uuid-here":
        print("❌ Error: ENCLAVE_ADAPTER_ID not set.")
        print("   Set ENCLAVE_ADAPTER_ID environment variable to your adapter UUID.")
        print("   You can find adapter IDs in the Enclave GUI under 'Knowledge' section.")
        return
    
    if not OPENAI_API_KEY:
        print("⚠️  Warning: OPENAI_API_KEY not set. Cannot run example.")
        return
    
    # Initialize knowledge retriever
    retriever = EnclaveKnowledgeRetriever(
        adapter_id=ADAPTER_ID,
        api_key=ENCLAVE_API_KEY,
        base_url=ENCLAVE_BASE_URL,
        temperature=0.3,
        max_tokens=512
    )
    
    # Initialize LLM
    llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY)
    
    # Create RetrievalQA chain
    qa = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True
    )
    
    print("\n✅ RAG chain ready! Example queries:")
    print("   - 'What did I write about project X?'")
    print("   - 'Summarize the key points from my work documents'")
    print("   - 'What's our Q4 revenue target?'")
    print("\n⏳ Note: Knowledge queries may take 5-30 seconds (RunPod inference)")
    
    # Example query
    try:
        query = "What information do you have about my work projects?"
        print(f"\n📝 Query: {query}")
        print("⏳ Querying knowledge adapter...")
        
        result = qa.run(query)
        
        print(f"\n📤 Answer: {result}")
        
        # If source documents are returned, show them
        if hasattr(result, 'source_documents'):
            print(f"\n📚 Sources: {len(result.source_documents)} documents")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Ensure ENCLAVE_API_KEY is set correctly")
        print("   2. Verify ADAPTER_ID is correct (UUID format)")
        print("   3. Check that adapter status is 'completed'")
        print("   4. Ensure policy allows access to this adapter")


if __name__ == "__main__":
    main()

