"""
Advanced Vault Features

This package contains advanced features for the WDVA (Weight-Delta Vault Adapter) system,
for the local, encrypted document vault.

Key Features:
- Encrypted KV store for exact data (API keys, passwords)
- Smart query routing (exact vs fuzzy)
- MCP integration for AI agents

Usage:
    from advanced_vault import HybridVault

    vault = HybridVault(master_key="...")
    vault.store("sk_live_ABC", type="secret", service="stripe")
    result = vault.query("stripe")  # values only for an exact entry name
"""

__version__ = "0.1.0"
__status__ = "development"

# Import main interfaces (when implemented)
# from .core import HybridVault, SmartRouter
# from .encrypted_kv import EncryptedKVStore
# from .mcp_server import VaultMCPServer
