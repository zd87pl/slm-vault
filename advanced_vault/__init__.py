"""
Advanced Vault Features

This package contains advanced features for the WDVA (Weight-Delta Vault Adapter) system,
building on top of the proven baseline implementation.

Key Features:
- Encrypted KV store for exact data (API keys, passwords)
- Smart query routing (exact vs fuzzy)
- MCP integration for AI agents
- Threshold cryptography for team vaults
- Speculative decryption for performance
- Homomorphic search (research)
- Federated learning (research)

Usage:
    from advanced_vault import HybridVault

    vault = HybridVault(master_key="...")
    vault.store("sk_live_ABC", type="secret", service="stripe")
    result = vault.query("What's my Stripe key?")
"""

__version__ = "0.1.0"
__status__ = "development"

# Import main interfaces (when implemented)
# from .core import HybridVault, SmartRouter
# from .encrypted_kv import EncryptedKVStore
# from .mcp_server import VaultMCPServer
