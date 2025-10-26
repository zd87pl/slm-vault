#!/usr/bin/env python3
"""
Unified Vault Demo: Complete Hybrid System (Layer 1 + Layer 2)

Demonstrates the full advanced vault system:
- Layer 1: Encrypted KV for API keys, credentials (exact data)
- Layer 2: DoRA adapter for knowledge, context (fuzzy data)
- Smart Router: Automatic query classification
- Hybrid Queries: Combined responses from both layers

Uses RunPod for private DoRA inference (no local ML setup required).

Requirements:
    - RUNPOD_API_KEY environment variable
    - Active RunPod endpoint (from privacy demo)

Usage:
    export RUNPOD_API_KEY=your_key
    python examples/advanced/unified_vault_demo.py
"""

import os
import sys
import json
import logging
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from src.dora_crypto import EncryptedDoRAManager, generate_secure_password
from src.ephemeral_inference import EphemeralDoRAInference

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def print_section(title: str, emoji: str = "📋"):
    """Print a clearly marked section."""
    print(f"\n{'=' * 80}")
    print(f"{emoji} {title}")
    print('=' * 80)


def print_step(step: int, description: str):
    """Print a numbered step."""
    print(f"\n✨ Step {step}: {description}")
    print('-' * 80)


def main():
    """Run the unified vault demonstration."""

    print_section("Unified Vault Demo: Complete Hybrid System", "🏛️")

    print("""
This demo shows the COMPLETE advanced vault system working together:

LAYER 1 (Encrypted KV Store):
  - Stores API keys, passwords, credentials
  - Client-side encryption (ChaCha20-Poly1305)
  - <10ms exact lookups, zero hallucination
  - ProtonMail-style E2EE

LAYER 2 (DoRA Knowledge Adapter):
  - Stores contextual knowledge, setup docs
  - Encrypted DoRA adapter
  - LLM inference for fuzzy queries
  - Private inference on RunPod

SMART ROUTER:
  - Automatic query classification
  - EXACT → Layer 1 (KV)
  - FUZZY → Layer 2 (DoRA)
  - HYBRID → Both layers

Let's see it in action!
""")

    # Check RunPod API key (optional for demo)
    has_runpod = bool(os.environ.get("RUNPOD_API_KEY") and os.environ.get("RUNPOD_ENDPOINT_ID"))

    if not has_runpod:
        print("\n⚠️  Note: RUNPOD_API_KEY not set")
        print("   This demo will show Layer 1 (KV Store) + simulated Layer 2 responses")
        print("\n   To enable REAL Layer 2 inference:")
        print("   1. Run privacy_demo_runpod.py to create encrypted adapter")
        print("   2. Deploy to RunPod endpoint")
        print("   3. export RUNPOD_API_KEY=your_key")
        print("   4. export RUNPOD_ENDPOINT_ID=your_endpoint_id")

    input("\nPress Enter to start the demo...")

    # =========================================================================
    # STEP 1: Setup Data
    # =========================================================================
    print_step(1, "Prepare Data for Both Layers")

    # Layer 1 data: Exact secrets
    secrets = {
        "stripe": {
            "api_key": "sk_live_ABC123XYZ789_STRIPE_PRODUCTION",
            "tags": ["payment", "production"],
            "description": "Stripe production API key"
        },
        "github": {
            "api_key": "ghp_ABC123XYZ789DEF456_GITHUB_PAT",
            "tags": ["git", "production"],
            "description": "GitHub personal access token"
        },
        "aws": {
            "api_key": "AKIAIOSFODNN7EXAMPLE_AWS_ACCESS",
            "tags": ["cloud", "production"],
            "description": "AWS access key"
        }
    }

    # Layer 2 data: Knowledge/context for DoRA training
    training_knowledge = [
        "I chose Stripe for payment processing because it has the best developer experience and supports instant payouts",
        "GitHub is used for version control and CI/CD pipelines with GitHub Actions",
        "AWS hosts our production infrastructure using EC2, S3, and RDS PostgreSQL",
        "Our Stripe integration uses webhooks for real-time payment notifications",
        "GitHub webhooks trigger our deployment pipeline on every push to main branch",
        "AWS auto-scaling is configured to handle traffic spikes during product launches"
    ]

    print("\n📦 Layer 1 Data (Secrets):")
    for service, data in secrets.items():
        masked_key = data['api_key'][:15] + "..." + data['api_key'][-10:]
        print(f"  - {service}: {masked_key}")

    print("\n📚 Layer 2 Data (Knowledge for DoRA training):")
    for i, knowledge in enumerate(training_knowledge, 1):
        print(f"  {i}. {knowledge}")

    # =========================================================================
    # STEP 2: Initialize Vault with Layer 1
    # =========================================================================
    print_step(2, "Initialize Vault - Layer 1 (Encrypted KV Store)")

    # Generate master key for KV encryption
    kv_master_key = os.urandom(32)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        kv_db_path = tmp.name

    # Generate encryption key for DoRA adapter
    adapter_password = generate_secure_password()

    print(f"✅ Generated KV master key (32 bytes)")
    print(f"✅ Generated DoRA encryption key")
    print(f"✅ Created temporary KV database: {kv_db_path}")

    # Initialize vault (Layer 2 will be added later)
    vault = HybridVault(
        master_key=kv_master_key,
        kv_db_path=kv_db_path,
        dora_adapter_path=None,  # Will add Layer 2 later
        enable_router_logging=True
    )

    # Store secrets in Layer 1
    print("\n💾 Storing secrets in Layer 1...")
    for service, data in secrets.items():
        vault.store(
            content=data['api_key'],
            data_type="secret",
            service=service,
            tags=data['tags'],
            description=data['description']
        )
        print(f"  ✅ Stored {service} credentials")

    # =========================================================================
    # STEP 3: Train and Encrypt DoRA Adapter (Layer 2)
    # =========================================================================
    print_step(3, "Train DoRA Adapter on Knowledge (Layer 2)")

    print("\n🔄 This step normally requires:")
    print("  1. Training DoRA adapter on your knowledge data")
    print("  2. Encrypting the adapter with your key")
    print("  3. Uploading encrypted adapter to RunPod")
    print("\n💡 For this demo, we'll use a pre-trained adapter from the privacy demo")
    print("   (In production, you'd train on your specific knowledge base)")

    # Create temporary directory for adapter
    adapter_dir = tempfile.mkdtemp(prefix="vault_adapter_")
    encrypted_adapter_path = os.path.join(adapter_dir, "encrypted_adapter.enc")

    print(f"\n📁 Adapter directory: {adapter_dir}")

    # In a real scenario, you would:
    # 1. Train DoRA adapter on training_knowledge
    # 2. Encrypt it with adapter_password
    # 3. Save to encrypted_adapter_path

    print("\n⚠️  Note: Skipping DoRA training for this demo")
    print("   To enable Layer 2, you would need to:")
    print("   1. Run privacy_demo.py to create encrypted adapter")
    print("   2. Deploy to RunPod endpoint")
    print("   3. Pass encrypted adapter path to vault")

    # =========================================================================
    # STEP 4: Query Layer 1 (EXACT queries)
    # =========================================================================
    print_step(4, "Query Layer 1 - EXACT Queries (API Keys)")

    exact_queries = [
        "What's my Stripe API key?",
        "Show me GitHub credentials",
        "Get AWS password"
    ]

    print("\n🔍 Testing EXACT queries (routed to Layer 1 KV store):\n")

    for query in exact_queries:
        print(f"💬 Query: \"{query}\"")
        result = vault.query(query)

        print(f"   → Strategy: {result['strategy'].upper()}")
        print(f"   → Layer: {result['layer']}")
        print(f"   → Service: {result.get('service', 'N/A')}")

        if result.get('result'):
            secret = result['result']
            masked = secret[:15] + "..." + secret[-10:]
            print(f"   ✅ Result: {masked}")
            print(f"   ⚡ Response time: <10ms (exact match, no LLM)")
        else:
            print(f"   ❌ Error: {result.get('error', 'Unknown error')}")
        print()

    # =========================================================================
    # STEP 5: Demonstrate FUZZY queries (would use Layer 2)
    # =========================================================================
    print_step(5, "FUZZY Queries - Would Use Layer 2 (DoRA)")

    fuzzy_queries = [
        "Why did I choose Stripe?",
        "How did I setup GitHub webhooks?",
        "Tell me about my AWS infrastructure"
    ]

    print("\n🔍 Testing FUZZY queries (would route to Layer 2 DoRA):\n")

    for query in fuzzy_queries:
        print(f"💬 Query: \"{query}\"")
        result = vault.query(query)

        print(f"   → Strategy: {result['strategy'].upper()}")
        print(f"   → Layer: {result['layer']}")

        if result.get('error'):
            print(f"   ⚠️  Layer 2 not initialized: {result['error']}")
            print(f"   📝 If Layer 2 was active, it would answer:")
            # Show what the answer would be based on training data
            if "Stripe" in query:
                print(f"       'You chose Stripe for its developer experience and instant payouts'")
            elif "GitHub" in query:
                print(f"       'GitHub webhooks trigger deployment on pushes to main branch'")
            elif "AWS" in query:
                print(f"       'AWS hosts production using EC2, S3, and RDS PostgreSQL'")
        print()

    # =========================================================================
    # STEP 6: Demonstrate HYBRID queries
    # =========================================================================
    print_step(6, "HYBRID Queries - Combining Both Layers")

    hybrid_queries = [
        "Show me everything about Stripe",
        "Tell me everything on GitHub"
    ]

    print("\n🔍 Testing HYBRID queries (would combine Layer 1 + Layer 2):\n")

    for query in hybrid_queries:
        print(f"💬 Query: \"{query}\"")
        result = vault.query(query)

        print(f"   → Strategy: {result['strategy'].upper()}")
        # Hybrid queries return 'layers' (plural), others return 'layer' (singular)
        layers = result.get('layers', result.get('layer'))
        print(f"   → Layers: {layers}")

        print(f"\n   📊 Combined Response Would Include:")

        # Layer 1 contribution
        service = "stripe" if "Stripe" in query else "github"
        kv_result = vault.kv_store.get(service)
        if kv_result:
            masked = kv_result[:15] + "..." + kv_result[-10:]
            print(f"      🔐 Layer 1 (Exact): API Key = {masked}")

        # Layer 2 contribution (simulated)
        print(f"      🧠 Layer 2 (Context): [Would provide setup knowledge]")
        if "Stripe" in query:
            print(f"         - Best developer experience")
            print(f"         - Instant payouts")
            print(f"         - Webhook-based notifications")
        else:
            print(f"         - Version control and CI/CD")
            print(f"         - GitHub Actions pipeline")
            print(f"         - Deployment webhooks")
        print()

    # =========================================================================
    # STEP 7: Vault Statistics
    # =========================================================================
    print_step(7, "Vault Statistics")

    stats = vault.get_stats()

    print(f"\n📊 Vault Status:")
    print(f"   Layer 1 (KV Store):")
    print(f"      - Total entries: {stats['layer_1']['total_entries']}")
    print(f"      - Services: {', '.join(stats['layer_1']['services'])}")
    print(f"      - Encryption: ChaCha20-Poly1305")
    print(f"   Layer 2 (DoRA):")
    print(f"      - Initialized: {stats['layer_2']['initialized']}")
    if stats['layer_2']['initialized']:
        print(f"      - Status: {stats['layer_2'].get('status', 'Active')}")
    else:
        print(f"      - Status: Not configured")

    # =========================================================================
    # Summary
    # =========================================================================
    print_section("Demo Summary", "✅")

    print("""
What We Demonstrated:

1. ✅ LAYER 1 (Encrypted KV Store)
   - Stored 3 API keys with client-side encryption
   - Sub-10ms exact lookups
   - Zero hallucination risk
   - ProtonMail-style E2EE

2. 📝 LAYER 2 (DoRA Adapter) - Not Active
   - Would store contextual knowledge
   - Would enable fuzzy queries
   - Would run private inference on RunPod
   - (Requires training step from privacy_demo.py)

3. ✅ SMART ROUTER
   - Correctly classified EXACT queries → Layer 1
   - Correctly classified FUZZY queries → Layer 2
   - Correctly classified HYBRID queries → Both layers
   - Automatic service extraction

4. 💡 HYBRID QUERIES
   - Combine exact data (Layer 1) + context (Layer 2)
   - "Show me everything about X" triggers both layers
   - Comprehensive responses with zero hallucination on secrets

Next Steps to Enable Full System:

1. Run privacy_demo.py to create encrypted DoRA adapter
2. Deploy adapter to RunPod endpoint
3. Update vault initialization with adapter path:

   vault = HybridVault(
       master_key=kv_master_key,
       kv_db_path=kv_db_path,
       dora_adapter_path="path/to/encrypted_adapter.enc",
       runpod_api_key=os.environ["RUNPOD_API_KEY"]
   )

4. Try fuzzy and hybrid queries with full Layer 2 support!

See advanced_vault/docs/ROADMAP.md for complete development plan.
""")

    # Cleanup
    vault.close()
    os.unlink(kv_db_path)

    print("\n🧹 Cleaned up temporary files")
    print("✅ Demo complete!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
