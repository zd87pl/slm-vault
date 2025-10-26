"""
Core Advanced Vault Components

This module provides the core functionality for the hybrid vault system:
- Smart router for query classification
- Hybrid vault combining Layer 1 and Layer 2

Usage:
    from advanced_vault.core import HybridVault, SmartRouter

    # Initialize hybrid vault
    vault = HybridVault(master_key)

    # Store data (auto-layers)
    vault.store("sk_live_ABC", type="secret", service="stripe")

    # Query (auto-routed)
    result = vault.query("What's my Stripe key?")  # → Layer 1
"""

from .smart_router import SmartRouter, QueryStrategy, QueryPlan
from .hybrid_vault import HybridVault

__all__ = [
    "SmartRouter",
    "QueryStrategy",
    "QueryPlan",
    "HybridVault"
]
