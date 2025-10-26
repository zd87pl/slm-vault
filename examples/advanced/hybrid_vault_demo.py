"""
Hybrid Vault Demo - Week 2

Demonstrates the Smart Router + Hybrid Vault:
- Layer 1 (Encrypted KV): API keys, passwords (exact data)
- Layer 2 (DoRA): Knowledge, context (fuzzy data) - optional
- Smart Router: Automatic query classification

Usage:
    python examples/advanced/hybrid_vault_demo.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault, SmartRouter


def demo_smart_router():
    """Demonstrate the Smart Router's query classification."""
    print("\n" + "="*70)
    print("🧠 SMART ROUTER DEMO - Query Classification")
    print("="*70)

    router = SmartRouter()

    # Test various query types
    test_queries = [
        # EXACT queries (Layer 1: KV Store)
        ("What's my Stripe API key?", "exact"),
        ("Show me GitHub credentials", "exact"),
        ("Get AWS password", "exact"),

        # FUZZY queries (Layer 2: DoRA)
        ("Why did I choose Stripe?", "fuzzy"),
        ("How did I setup GitHub webhooks?", "fuzzy"),
        ("Tell me about my AWS integration", "fuzzy"),

        # HYBRID queries (Both layers)
        ("Show me everything about Stripe", "hybrid"),
        ("Tell me everything on GitHub", "hybrid"),
        ("Stripe setup and credentials", "hybrid"),
    ]

    for query, expected_type in test_queries:
        plan = router.route(query)

        # Status icon
        status = "✅" if plan.strategy.value == expected_type else "❌"

        print(f"\n{status} Query: \"{query}\"")
        print(f"   → Strategy: {plan.strategy.value.upper()}")
        print(f"   → Layer(s): {plan.layer}")
        print(f"   → Service: {plan.service or 'N/A'}")
        print(f"   → Confidence: {plan.confidence:.0%}")


def demo_hybrid_vault_layer1():
    """Demonstrate Hybrid Vault with Layer 1 (Encrypted KV) only."""
    print("\n" + "="*70)
    print("🔐 HYBRID VAULT DEMO - Layer 1 (Encrypted KV Store)")
    print("="*70)

    # Generate master key
    master_key = os.urandom(32)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Initialize vault (Layer 1 only, no DoRA)
        vault = HybridVault(
            master_key=master_key,
            kv_db_path=db_path,
            dora_adapter_path=None,  # Layer 2 disabled for this demo
            enable_router_logging=True
        )

        print("\n📝 Storing secrets (Layer 1)...")

        # Store API keys
        vault.store(
            content="sk_live_ABC123XYZ789",
            data_type="secret",
            service="stripe",
            tags=["payment", "production"],
            description="Stripe production API key"
        )

        vault.store(
            content="ghp_ABC123XYZ789DEF456",
            data_type="secret",
            service="github",
            tags=["git", "production"],
            description="GitHub personal access token"
        )

        vault.store(
            content="AKIAIOSFODNN7EXAMPLE",
            data_type="secret",
            service="aws",
            tags=["cloud", "production"],
            description="AWS access key"
        )

        print("✅ Stored 3 secrets in Layer 1")

        # Query with natural language (auto-routed)
        print("\n🔍 Querying with natural language...")

        queries = [
            "What's my Stripe API key?",
            "Show me GitHub credentials",
            "Get AWS password",
        ]

        for query_text in queries:
            print(f"\n💬 Query: \"{query_text}\"")
            result = vault.query(query_text)

            print(f"   Strategy: {result['strategy']}")
            print(f"   Layer: {result['layer']}")
            print(f"   Service: {result.get('service', 'N/A')}")

            if result.get('result'):
                # Mask secret for display
                secret = result['result']
                masked = secret[:8] + "..." + secret[-4:] if len(secret) > 12 else "***"
                print(f"   ✅ Result: {masked}")
            else:
                print(f"   ❌ Error: {result.get('error', 'Unknown error')}")

        # Test query that doesn't match
        print("\n💬 Query: \"What's my Postgres password?\"")
        result = vault.query("What's my Postgres password?")
        print(f"   Strategy: {result['strategy']}")
        print(f"   ❌ Error: {result.get('error', 'Not found')}")

        # Show vault stats
        print("\n📊 Vault Statistics:")
        stats = vault.get_stats()
        print(f"   Layer 1 entries: {stats['layer_1']['total_entries']}")
        print(f"   Services: {', '.join(stats['layer_1']['services'])}")
        print(f"   Layer 2 initialized: {stats['layer_2']['initialized']}")

        vault.close()

    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


def demo_routing_explanation():
    """Demonstrate the router's explain() method for transparency."""
    print("\n" + "="*70)
    print("📖 ROUTING EXPLANATION - Understanding Router Decisions")
    print("="*70)

    router = SmartRouter()

    queries = [
        "What's my Stripe API key?",
        "Why did I choose Stripe?",
        "Show me everything about Stripe",
    ]

    for query in queries:
        print(router.explain(query))
        print()


def main():
    """Run all demos."""
    print("\n" + "="*70)
    print("🎯 HYBRID VAULT DEMO - Week 2 Implementation")
    print("="*70)
    print("\nThis demo showcases:")
    print("  1. Smart Router: Automatic query classification")
    print("  2. Hybrid Vault: Unified interface for Layer 1 + Layer 2")
    print("  3. Layer 1: Encrypted KV store (ProtonMail-style E2EE)")
    print("  4. Layer 2: DoRA adapters (optional, not shown in this demo)")
    print("\nNote: Layer 2 requires encrypted DoRA adapter (see privacy demo)")

    # Run demos
    demo_smart_router()
    demo_hybrid_vault_layer1()
    demo_routing_explanation()

    print("\n" + "="*70)
    print("✅ DEMO COMPLETE")
    print("="*70)
    print("\nNext steps:")
    print("  - Week 3: MCP integration for Claude Desktop")
    print("  - Week 3: TEE-based private inference")
    print("  - Week 4: Consent mechanism (OS notifications)")
    print("\nSee advanced_vault/docs/ROADMAP.md for full plan")


if __name__ == "__main__":
    main()
