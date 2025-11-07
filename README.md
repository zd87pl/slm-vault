# Enclave: Secure Vault for Agentic Web

> Secure Secret Storage with User-Controlled Access for AI Agents

## Overview

Enclave is a secure, privacy-preserving vault system that enables AI agents and web applications to access your secrets and knowledge with **explicit user consent**. Built with end-to-end encryption, fine-tuned language models, and Model Context Protocol (MCP) integration. **You control who accesses what, when.**

## The Problem

Current approaches to secret management for AI agents are either:
- **Insecure**: API keys stored in plaintext or weakly encrypted
- **No User Control**: Agents access secrets without explicit permission
- **Fragmented**: Secrets scattered across different services and tools
- **Privacy-Invasive**: Your secrets controlled by third-party services
- **No Audit Trail**: No visibility into who accessed what and when

## Our Solution: Enclave Vault

**Enclave** provides:
- **🔐 End-to-End Encryption**: All secrets encrypted client-side before storage - zero-knowledge architecture
- **👤 User Consent**: Four-button consent system (Allow, Deny, Allow Always, Deny Always) for every access request
- **🌐 Browser Extension**: Chrome/Comet extension for seamless secret management
- **🤖 AI Agent Integration**: MCP server for Claude Desktop, Cursor, and other AI tools
- **📚 Knowledge Extraction**: Fine-tune language models on your documents for personalized AI
- **🔍 Activity Monitoring**: Track all secret access attempts with detailed logs
- **🛡️ Policy-Based Access**: Granular control over which agents can access which secrets
- **☁️ Cloud Sync**: Encrypted synchronization across devices

## Key Differentiators

### 🔒 Privacy by Design
Your secrets are encrypted client-side before storage. The backend never sees plaintext. You can export, delete, or transfer everything at any time.

### 👤 User Control
Every access request requires explicit consent. You decide who can access what, with granular policies and audit logs.

### 🌐 Agentic Web Ready
Built for the agentic web - seamlessly integrates with LangChain, MCP, and other AI agent frameworks.

### 📊 Complete Visibility
Track every access attempt, see who requested what, and when. Full audit trail for security and compliance.

### 🚀 Accessible Everywhere
Manage secrets through browser extension, desktop GUI, CLI, or API - all with the same security guarantees.

## Features

### Core Capabilities
- ✅ **Secret Storage**: Secure storage of API keys, passwords, and credentials
- ✅ **Client-Side Encryption**: AES-GCM encryption with master key derivation
- ✅ **Consent Management**: Four-button system with persistent policies
- ✅ **Browser Extension**: Chrome/Comet extension for easy secret management
- ✅ **MCP Integration**: Model Context Protocol server for AI agent access
- ✅ **LangChain Integration**: Native tools and retrievers for LangChain agents
- ✅ **Activity Logging**: Complete audit trail of all access attempts
- ✅ **Cloud Sync**: Encrypted synchronization across devices

### Security Features
- 🔒 **Zero-Knowledge Architecture**: Backend never sees plaintext secrets
- 🔒 **End-to-End Encryption**: XChaCha20-Poly1305 with HKDF-SHA256 key derivation
- 🔒 **Secure Memory**: Memory locking and secure zeroing
- 🔒 **Policy Enforcement**: Granular access control with rate limiting
- 🔒 **Audit Logging**: Complete visibility into all access attempts

### Knowledge Extraction (Optional)
- 📚 **Document Processing**: Extract knowledge from PDFs and documents
- 🤖 **Fine-Tuned Models**: Train personalized AI models on your data
- 🔐 **Encrypted Adapters**: DoRA adapters encrypted and stored securely
- ⚡ **Ephemeral Inference**: Adapters loaded in-memory only, never persisted

## Quick Start

### Browser Extension

1. **Install Extension**:
   - Open Chrome/Comet and navigate to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select `browser-extension/` directory

2. **Set Master Password**:
   - Click extension icon
   - Set your master password (used to encrypt/decrypt secrets)

3. **Add Your First Secret**:
   - Click "Add Secret"
   - Enter service name (e.g., "openai") and API key
   - Click "Save"

4. **Grant Access to AI Agents**:
   - When an agent requests access, consent popup appears
   - Choose Allow, Deny, Allow Always, or Deny Always

### Desktop GUI

```bash
# Launch GUI
./launch_enclave_gui.sh

# Login and start managing secrets
```

### MCP Server

```bash
# Start MCP server
python -m advanced_vault.mcp_server

# Configure in Claude Desktop or Cursor
# MCP server will request consent for each access
```

### LangChain Integration

```python
from langchain_enclave import EnclaveSecretProvider, EnclaveKnowledgeRetriever

# Get secret provider
secret_tool = EnclaveSecretProvider(
    api_key="your-api-key",
    base_url="https://your-backend-url"
)

# Use in LangChain agent
agent = initialize_agent(
    tools=[secret_tool],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION
)
```

## Architecture

```
User → Browser Extension / GUI → Encrypted Storage → Cloud Sync
                ↓
         Consent Manager
                ↓
    AI Agents (MCP/LangChain) → Policy Engine → Encrypted Secrets
```

**Key Components:**
- `browser-extension/`: Chrome/Comet extension for secret management
- `advanced_vault/core/`: Core vault with encryption and storage
- `advanced_vault/mcp_server/`: MCP server for AI agent integration
- `advanced_vault/backend/`: Backend API with policy engine
- `langchain-enclave/`: LangChain integration package

## Installation

### Browser Extension

```bash
# Load unpacked extension in Chrome
# See browser-extension/README.md for details
```

### Desktop GUI

```bash
# Install dependencies
pip install -r advanced_vault/gui/requirements.txt

# Launch GUI
./launch_enclave_gui.sh
```

### Backend API

```bash
# Install dependencies
pip install -r advanced_vault/backend/requirements.txt

# Run backend
cd advanced_vault/backend
uvicorn main:app --reload
```

### LangChain Package

```bash
# Install langchain-enclave
cd langchain-enclave
pip install -e .

# Or from PyPI (when published)
pip install langchain-enclave
```

## Documentation

**📖 [Full Documentation Index](docs/README.md)** - Complete documentation organized by topic

### Quick Links
- **[Browser Extension Setup](docs/BROWSER_EXTENSION_SETUP.md)** - Extension installation and usage
- **[LangChain Integration](docs/LANGCHAIN_INTEGRATION.md)** - Integrate with LangChain agents
- **[MCP Integration](docs/MCP_INTEGRATION.md)** - Set up MCP server
- **[Policy Guide](docs/POLICY_GUIDE.md)** - Configure access policies
- **[API Detection](docs/BROWSER_EXTENSION_API_DETECTION.md)** - Monitor secret access

### Development
- **[Backlog](BACKLOG.md)** - Active development backlog
- **[Roadmap](ROADMAP.md)** - High-level development roadmap

## Security

### Encryption
- **Client-Side**: All secrets encrypted before leaving your device
- **Algorithm**: AES-GCM (browser) / XChaCha20-Poly1305 (backend)
- **Key Derivation**: PBKDF2 (browser) / HKDF-SHA256 (backend)
- **Zero-Knowledge**: Backend never sees plaintext secrets

### Access Control
- **Consent Required**: Every access requires explicit user approval
- **Policy Engine**: Granular rules for agent access
- **Rate Limiting**: Prevent abuse with configurable limits
- **Audit Logging**: Complete trail of all access attempts

### Privacy
- **No Tracking**: No analytics or tracking of your secrets
- **Local-First**: Secrets stored locally, synced optionally
- **Export/Delete**: Full control over your data
- **Right to be Forgotten**: Delete secrets and policies anytime

## Use Cases

### API Key Management
Store API keys for OpenAI, Anthropic, GitHub, Stripe, and more. Grant access to AI agents with explicit consent.

### Secret Sharing
Share secrets with team members or AI agents while maintaining full control and audit trail.

### Knowledge Base
Upload documents and create personalized AI knowledge bases with fine-tuned models.

### Agentic Web Integration
Integrate with LangChain, AutoGPT, and other agent frameworks with policy-based access control.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Copyright © 2025 Zygmunt Dyras. All rights reserved.

**Proprietary Technology**: This software incorporates proprietary technology protected by provisional patent applications. Unauthorized use, reproduction, or distribution is prohibited.

---

**Enclave: Secure secrets for the agentic web. You control who accesses what, when.**
