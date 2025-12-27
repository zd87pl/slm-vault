"""
Example: LangChain agent that retrieves secrets from Enclave.

This example shows how to use EnclaveSecretProvider to enable
a LangChain agent to securely retrieve API keys and credentials.
"""

import os
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI
from langchain_enclave import EnclaveSecretProvider

# Configuration
ENCLAVE_API_KEY = os.getenv("ENCLAVE_API_KEY", "vlt_your_api_key_here")
ENCLAVE_BASE_URL = os.getenv(
    "ENCLAVE_BASE_URL",
    "https://keen-curiosity-production-1288.up.railway.app"
)

# OpenAI API key (for LangChain - this is separate from Enclave)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def main():
    """Run example agent with Enclave secret provider."""
    
    print("🚀 Initializing LangChain agent with Enclave secret provider...")
    
    # Initialize Enclave secret provider
    secret_tool = EnclaveSecretProvider(
        api_key=ENCLAVE_API_KEY,
        base_url=ENCLAVE_BASE_URL
    )
    
    # Initialize LLM (this requires OpenAI API key separately)
    if not OPENAI_API_KEY:
        print("⚠️  Warning: OPENAI_API_KEY not set. Agent will use mock LLM.")
        print("   Set OPENAI_API_KEY environment variable to use real LLM.")
        return
    
    llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY)
    
    # Create agent with Enclave tool
    agent = initialize_agent(
        tools=[secret_tool],
        llm=llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=True
    )
    
    print("\n✅ Agent ready! Example queries:")
    print("   - 'Get my OpenAI API key'")
    print("   - 'Retrieve the GitHub token'")
    print("   - 'What secrets do I have for Stripe?'")
    print("\n💡 Note: Secrets are returned encrypted. Decrypt with your master key.")
    
    # Example query
    try:
        query = "Get my OpenAI API key"
        print(f"\n📝 Query: {query}")
        response = agent.run(query)
        print(f"\n📤 Response: {response}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Ensure ENCLAVE_API_KEY is set correctly")
        print("   2. Check that a policy exists for your agent identifier")
        print("   3. Verify the secret exists in your Enclave vault")


if __name__ == "__main__":
    main()

