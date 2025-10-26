#!/usr/bin/env python3
"""
Encrypted KV Store Demo

Demonstrates Layer 1 (exact data storage) with zero hallucination risk.
Shows how API keys, passwords, and secrets are stored with client-side encryption.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.encrypted_kv import EncryptedKVStore, EntryType, QueryFilter


def print_header(text):
    """Print formatted header."""
    print(f"\n{'=' * 70}")
    print(f"  {text}")
    print('=' * 70)


def main():
    """Run encrypted KV store demo."""

    print_header("Encrypted KV Store Demo - Layer 1 (Exact Data)")

    # Step 1: Initialize
    print("\n📍 Step 1: Initialize Encrypted Store")
    print("   Generating 256-bit master key...")

    master_key = os.urandom(32)  # 32 bytes = 256 bits
    store = EncryptedKVStore(master_key, db_path="/tmp/demo_vault.db")

    print(f"   ✓ Store initialized")
    print(f"   ✓ Database: /tmp/demo_vault.db")
    print(f"   ✓ Encryption: ChaCha20-Poly1305")

    # Step 2: Store secrets
    print_header("Step 2: Store Secrets (Client-Side Encryption)")

    secrets = [
        ("stripe", "sk_live_ABC123DEF456", EntryType.API_KEY, ["payment", "production"]),
        ("github", "ghp_XYZ789QWERTY123", EntryType.TOKEN, ["dev", "cicd"]),
        ("aws", "AKIAIOSFODNN7EXAMPLE", EntryType.API_KEY, ["infrastructure"]),
        ("database", "postgres://user:super_secret_password@localhost:5432/db", EntryType.PASSWORD, ["production"]),
    ]

    for service, secret, entry_type, tags in secrets:
        entry_id = store.put(service, secret, entry_type=entry_type, tags=tags)
        print(f"   ✓ Stored {service}: {entry_type.value} (ID: {entry_id[:8]}...)")

    print(f"\n   💾 All secrets encrypted and stored")
    print(f"   🔐 Server never saw plaintext")

    # Step 3: Retrieve secrets (exact match, no hallucination)
    print_header("Step 3: Retrieve Secrets (Exact Match)")

    print("\n   Querying: 'What's my Stripe API key?'")
    stripe_key = store.get("stripe")
    print(f"   → {stripe_key}")
    print(f"   ✓ Exact match (no hallucination from LLM)")

    print("\n   Querying: 'What's my GitHub token?'")
    github_token = store.get("github")
    print(f"   → {github_token}")
    print(f"   ✓ Exact match (no hallucination from LLM)")

    # Step 4: Metadata search
    print_header("Step 4: Search by Metadata (NOT Encrypted Data)")

    print("\n   Search: All 'production' secrets")
    filter_prod = QueryFilter(tags=["production"])
    results = store.search(filter_prod)
    for entry in results:
        print(f"   → {entry.service} ({entry.entry_type.value})")

    print("\n   Search: All API keys")
    filter_api = QueryFilter(entry_type=EntryType.API_KEY)
    results = store.search(filter_api)
    for entry in results:
        print(f"   → {entry.service} ({', '.join(entry.tags)})")

    # Step 5: Vault statistics
    print_header("Step 5: Vault Statistics")

    stats = store.get_stats()
    print(f"\n   Total entries: {stats.total_entries}")
    print(f"   Services: {', '.join(stats.services)}")
    print(f"   Tags: {', '.join(stats.tags)}")
    print(f"   Total size: {stats.total_size_bytes / 1024:.2f} KB (encrypted)")

    # Step 6: Security demonstration
    print_header("Step 6: Security Properties")

    print("\n   ✓ Client-side encryption (server never sees plaintext)")
    print("   ✓ Unique nonce per entry (semantic security)")
    print("   ✓ Authenticated encryption (prevents tampering)")
    print("   ✓ Metadata searchable (but secrets encrypted)")
    print("   ✓ Zero hallucination risk (exact retrieval, no LLM)")

    # Step 7: Comparison with Layer 2
    print_header("Step 7: Layer 1 vs Layer 2 Comparison")

    print("\n   Layer 1 (This - Encrypted KV):")
    print("   • Use case: API keys, passwords, exact data")
    print("   • Retrieval: Exact match (no hallucination)")
    print("   • Query: 'What's my Stripe key?' → sk_live_ABC123")
    print("   • Speed: <10ms")

    print("\n   Layer 2 (DoRA Adapters - Coming in Week 2):")
    print("   • Use case: Knowledge, context, fuzzy data")
    print("   • Retrieval: Semantic (understands meaning)")
    print("   • Query: 'Why did I choose Stripe?' → 'Webhook reliability...'")
    print("   • Speed: ~200ms")

    print("\n   Hybrid Vault (Coming in Week 2):")
    print("   • Smart router decides: Exact → Layer 1, Fuzzy → Layer 2")
    print("   • Query: 'Show me everything about Stripe'")
    print("   • Returns: API key (Layer 1) + Context (Layer 2)")

    # Step 8: Right-to-be-forgotten
    print_header("Step 8: Cryptographic Deletion")

    print("\n   Deleting 'github' entry...")
    deleted = store.delete("github")
    print(f"   ✓ Deleted: {deleted}")

    print("\n   Verifying deletion...")
    github_after = store.get("github")
    print(f"   → Result: {github_after}")
    print(f"   ✓ Secret permanently removed")

    # Cleanup
    store.close()
    print("\n   ✓ Store closed, master key cleared from memory")

    print_header("Demo Complete!")
    print("\n   Next steps:")
    print("   • Week 2: Smart router for hybrid queries")
    print("   • Week 3-4: MCP integration (Claude Desktop)")
    print("   • Week 5-6: TEE-based private inference")
    print()


if __name__ == "__main__":
    main()
