"""
Personal Vault CLI - Main Implementation

Command-line interface for managing secrets and knowledge in the vault.
"""

import os
import sys
import json
import click
from pathlib import Path
from typing import Optional, List

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from advanced_vault.enclave_control import EnclaveRuntime
from advanced_vault.encrypted_kv import QueryFilter
from advanced_vault.private_models import PrivateModelManager
from advanced_vault.sheriff.core import SheriffCore
from advanced_vault.sheriff.models import AccessDecision
from advanced_vault.wallet import WalletService


class VaultCLI:
    """Vault CLI helper class."""

    def __init__(self, vault_path: str = "~/.vault"):
        """Initialize vault CLI."""
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Paths
        self.key_path = self.vault_path / "master.key"
        self.db_path = self.vault_path / "vault.db"

        # Load or generate master key
        if self.key_path.exists():
            with open(self.key_path, "rb") as f:
                self.master_key = f.read()
        else:
            self.master_key = os.urandom(32)
            with open(self.key_path, "wb") as f:
                f.write(self.master_key)
            os.chmod(self.key_path, 0o600)
            click.echo(f"✅ Generated new master key at {self.key_path}")

        # Initialize vault
        self.vault = HybridVault(
            master_key=self.master_key,
            kv_db_path=str(self.db_path),
            enable_router_logging=False
        )

    def close(self):
        """Close vault."""
        if self.vault:
            self.vault.close()


@click.group()
@click.option('--vault-path', default="~/.vault", help='Path to vault directory')
@click.pass_context
def cli(ctx, vault_path):
    """
    Personal Vault CLI - Secure storage for secrets and knowledge

    Examples:
        vault add secret stripe sk_live_ABC123 --tags payment
        vault add note "Stripe setup documentation"
        vault get stripe
        vault list
    """
    ctx.ensure_object(dict)
    ctx.obj['vault_path'] = vault_path


def _get_sheriff(vault_path: str) -> SheriffCore:
    """Create sheriff core for CLI commands."""
    runtime = _get_runtime(vault_path)
    return SheriffCore(vault_path=vault_path, runtime=runtime)


def _get_model_manager(vault_path: str) -> PrivateModelManager:
    """Create a private model manager rooted inside the vault path."""
    root_path = Path(vault_path).expanduser() / "private_models"
    return PrivateModelManager(root_path=str(root_path))


def _get_runtime(vault_path: str) -> EnclaveRuntime:
    """Create the shared control-plane runtime for CLI commands."""
    return EnclaveRuntime(vault_path=vault_path)


def _get_wallet(vault_path: str) -> WalletService:
    """Create a wallet service rooted inside the vault path."""
    return WalletService(vault_path=vault_path)


def _update_wallet_module_status(runtime: EnclaveRuntime, wallet: WalletService) -> None:
    """Persist a lightweight wallet module snapshot for the GUI shell."""
    envelopes = wallet.list_envelopes()
    pending = wallet.list_pending_requests()
    transactions = wallet.get_transactions()
    frozen = wallet.store.is_frozen()
    runtime.update_module_status(
        "wallet",
        status="warning" if frozen else "ready",
        headline=("Wallet frozen" if frozen else "Wallet ready"),
        details={
            "envelope_count": len(envelopes),
            "pending_count": len(pending),
            "transaction_count": len(transactions),
            "frozen": frozen,
        },
    )


@cli.command()
@click.argument('service')
@click.argument('content')
@click.option('--tags', multiple=True, help='Tags for the secret')
@click.option('--description', help='Description of the secret')
@click.pass_context
def add_secret(ctx, service, content, tags, description):
    """
    Add a secret to the vault.

    Examples:
        vault add-secret stripe sk_live_ABC123
        vault add-secret stripe sk_live_ABC123 --tags payment,production
        vault add-secret github ghp_token123 --description "GitHub PAT"
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        entry_id = vault_cli.vault.store(
            content=content,
            data_type="secret",
            service=service,
            tags=list(tags) if tags else [],
            description=description
        )

        click.echo(f"✅ Stored secret for: {service}")
        click.echo(f"   ID: {entry_id[:8]}...")
        if tags:
            click.echo(f"   Tags: {', '.join(tags)}")
        if description:
            click.echo(f"   Description: {description}")
    finally:
        vault_cli.close()


@cli.command()
@click.argument('content')
@click.option('--tags', multiple=True, help='Tags for the note')
@click.option('--description', help='Description of the note')
@click.pass_context
def add_note(ctx, content, tags, description):
    """
    Add a knowledge note to the vault.

    Examples:
        vault add-note "I chose Stripe for best webhook support"
        vault add-note "Setup: Configure webhooks at dashboard.stripe.com" --tags stripe,setup
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        # For Layer 1, we'll store as a note with a special service name
        entry_id = vault_cli.vault.store(
            content=content,
            data_type="secret",  # Using KV store for now
            service=f"note_{entry_id[:8] if 'entry_id' in locals() else 'new'}",
            tags=list(tags) if tags else [],
            description=description or "Knowledge note"
        )

        click.echo(f"✅ Stored note")
        click.echo(f"   ID: {entry_id[:8]}...")
        if tags:
            click.echo(f"   Tags: {', '.join(tags)}")
    finally:
        vault_cli.close()


@cli.command()
@click.argument('service')
@click.pass_context
def get(ctx, service):
    """
    Get a secret by service name.

    Examples:
        vault get stripe
        vault get github
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        secret = vault_cli.vault.kv_store.get(service)

        if secret:
            click.echo(f"🔐 {service}:")
            click.echo(f"   {secret}")
        else:
            click.echo(f"❌ No secret found for: {service}", err=True)
            sys.exit(1)
    finally:
        vault_cli.close()


@cli.command(name="list")
@click.option('--tag', help='Filter by tag')
@click.option('--service', help='Filter by service')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def list_entries(ctx, tag, service, output_json):
    """
    List all vault entries.

    Examples:
        vault list
        vault list --tag payment
        vault list --service stripe
        vault list --json
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        filter_obj = QueryFilter()
        if tag:
            filter_obj.tags = [tag]
        if service:
            filter_obj.service = service

        entries = vault_cli.vault.kv_store.search(filter_obj)

        if not entries:
            click.echo("No entries found.")
            return

        if output_json:
            # JSON output
            data = []
            for entry in entries:
                data.append({
                    'id': entry.id,
                    'service': entry.service,
                    'type': entry.entry_type.value,
                    'tags': entry.tags,
                    'description': entry.description,
                    'created_at': entry.created_at.isoformat()
                })
            click.echo(json.dumps(data, indent=2))
        else:
            # Human-readable output
            click.echo(f"\n📊 Found {len(entries)} entries:\n")
            for entry in entries:
                click.echo(f"• {entry.service}")
                click.echo(f"  Type: {entry.entry_type.value}")
                if entry.tags:
                    click.echo(f"  Tags: {', '.join(entry.tags)}")
                if entry.description:
                    click.echo(f"  Description: {entry.description}")
                click.echo(f"  Created: {entry.created_at.strftime('%Y-%m-%d %H:%M')}")
                click.echo()
    finally:
        vault_cli.close()


@cli.command()
@click.argument('service')
@click.confirmation_option(prompt='Are you sure you want to delete this secret?')
@click.pass_context
def delete(ctx, service):
    """
    Delete a secret by service name.

    Examples:
        vault delete stripe
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        success = vault_cli.vault.kv_store.delete(service)

        if success:
            click.echo(f"✅ Deleted: {service}")
        else:
            click.echo(f"❌ No entry found for: {service}", err=True)
            sys.exit(1)
    finally:
        vault_cli.close()


@cli.command()
@click.pass_context
def stats(ctx):
    """
    Show vault statistics.

    Examples:
        vault stats
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        stats = vault_cli.vault.get_stats()

        click.echo("\n📊 Vault Statistics\n")
        click.echo("Layer 1 (Encrypted KV Store):")
        click.echo(f"  Total entries: {stats['layer_1']['total_entries']}")
        click.echo(f"  Services: {', '.join(stats['layer_1']['services']) if stats['layer_1']['services'] else 'none'}")
        click.echo(f"  Encryption: ChaCha20-Poly1305")
        click.echo()
        click.echo("Layer 2 (DoRA Knowledge):")
        click.echo(f"  Initialized: {stats['layer_2']['initialized']}")
        click.echo(f"  Status: {'Active' if stats['layer_2']['initialized'] else 'Not configured'}")
        click.echo()
        click.echo(f"Vault path: {vault_cli.vault_path}")
    finally:
        vault_cli.close()


@cli.command()
@click.argument('file', type=click.File('r'))
@click.option('--format', type=click.Choice(['json', '1password', 'lastpass']), default='json', help='Import format')
@click.pass_context
def import_file(ctx, file, format):
    """
    Import secrets from a file.

    Examples:
        vault import secrets.json
        vault import --format 1password export.json
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        if format == 'json':
            data = json.load(file)

            if isinstance(data, list):
                # Array of entries
                for entry in data:
                    vault_cli.vault.store(
                        content=entry['content'],
                        data_type=entry.get('type', 'secret'),
                        service=entry['service'],
                        tags=entry.get('tags', []),
                        description=entry.get('description')
                    )
                click.echo(f"✅ Imported {len(data)} entries")
            else:
                # Single entry
                vault_cli.vault.store(
                    content=data['content'],
                    data_type=data.get('type', 'secret'),
                    service=data['service'],
                    tags=data.get('tags', []),
                    description=data.get('description')
                )
                click.echo(f"✅ Imported 1 entry")
        else:
            click.echo(f"❌ Format '{format}' not yet implemented", err=True)
            sys.exit(1)
    finally:
        vault_cli.close()


@cli.command()
@click.argument('file', type=click.File('w'))
@click.option('--format', type=click.Choice(['json']), default='json', help='Export format')
@click.pass_context
def export(ctx, file, format):
    """
    Export secrets to a file.

    Examples:
        vault export secrets.json
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        entries = vault_cli.vault.kv_store.search(QueryFilter())

        data = []
        for entry in entries:
            # Decrypt and export
            secret = vault_cli.vault.kv_store.get(entry.service)
            data.append({
                'service': entry.service,
                'content': secret,
                'type': entry.entry_type.value,
                'tags': entry.tags,
                'description': entry.description,
                'created_at': entry.created_at.isoformat()
            })

        if format == 'json':
            json.dump(data, file, indent=2)
            click.echo(f"✅ Exported {len(data)} entries to {file.name}")

    finally:
        vault_cli.close()


@cli.command()
@click.argument('query')
@click.pass_context
def query(ctx, query):
    """
    Query the vault using natural language (Smart Router).

    Examples:
        vault query "What's my Stripe API key?"
        vault query "Why did I choose Stripe?"
    """
    vault_cli = VaultCLI(ctx.obj['vault_path'])

    try:
        result = vault_cli.vault.query(query)

        strategy = result.get('strategy', 'unknown')
        layer = result.get('layer') or result.get('layers', 'unknown')

        click.echo(f"\n🔍 Query: {query}")
        click.echo(f"   Strategy: {strategy}")
        click.echo(f"   Layer: {layer}")

        if result.get('error'):
            click.echo(f"   ❌ Error: {result['error']}", err=True)
        elif result.get('result'):
            click.echo(f"   ✅ Result:\n")
            click.echo(f"   {result['result']}")
        else:
            click.echo(f"   ❓ No results found")
    finally:
        vault_cli.close()


@cli.group()
def model():
    """Private Language Model workflows (profiles, local chat, WDVA adapters)."""


@model.command("create")
@click.argument("name")
@click.option("--description", default="", help="Short description for the profile")
@click.option("--keyword", "keywords", multiple=True, help="Keywords for the profile")
@click.option("--model-name", default=None, help="Preferred local model name/path")
@click.option(
    "--system-prompt",
    default=(
        "You are Enclave, a private local language model. "
        "Use the user's local context carefully and cite document names."
    ),
    help="Profile-specific system prompt",
)
@click.pass_context
def model_create(ctx, name, description, keywords, model_name, system_prompt):
    """Create a Private Language Model profile."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    profile = manager.create_profile(
        name=name,
        description=description,
        system_prompt=system_prompt,
        keywords=list(keywords),
        model_name=model_name,
    )
    click.echo(f"✅ Created profile: {profile.name}")
    if profile.description:
        click.echo(f"   Description: {profile.description}")
    if profile.model_name:
        click.echo(f"   Model: {profile.model_name}")


@model.command("list")
@click.pass_context
def model_list(ctx):
    """List Private Language Model profiles."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    profiles = manager.list_profiles()
    if not profiles:
        click.echo("No private model profiles found.")
        return

    click.echo("\n🧠 Private Language Models\n")
    for profile in profiles:
        click.echo(f"• {profile.name}")
        if profile.description:
            click.echo(f"  {profile.description}")
        click.echo(f"  WDVA adapters: {len(profile.wdva_adapters)}")
        if profile.keywords:
            click.echo(f"  Keywords: {', '.join(profile.keywords)}")
        click.echo()


@model.command("info")
@click.argument("name")
@click.pass_context
def model_info(ctx, name):
    """Show profile details and local index stats."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    session = manager.open_session(name)
    try:
        status = session.get_status()
    finally:
        session.close()

    profile = status["profile"]
    click.echo(f"\n🧠 Profile: {profile['name']}\n")
    if profile.get("description"):
        click.echo(f"Description: {profile['description']}")
    if profile.get("model_name"):
        click.echo(f"Model: {profile['model_name']}")
    click.echo(f"Documents: {status['document_count']}")
    click.echo(f"Chunks: {status['chunk_count']}")
    click.echo(f"WDVA adapters: {len(profile.get('wdva_adapters', []))}")
    for adapter in profile.get("wdva_adapters", []):
        click.echo(f"  • {adapter['name']} (weight={adapter['weight']:.2f})")


@model.command("ingest")
@click.argument("name")
@click.argument("paths", nargs=-1)
@click.pass_context
def model_ingest(ctx, name, paths):
    """Ingest files or folders into a local profile."""
    if not paths:
        click.echo("❌ Provide at least one file or folder to ingest.", err=True)
        sys.exit(1)

    manager = _get_model_manager(ctx.obj["vault_path"])
    session = manager.open_session(name)
    try:
        result = session.ingest_paths(paths)
    finally:
        session.close()

    click.echo(f"✅ Added {result.added} documents")
    if result.skipped:
        click.echo(f"   Skipped: {result.skipped}")
    for doc in result.documents[:10]:
        click.echo(f"   • {doc['name']} ({doc['chunks']} chunks)")


@model.command("chat")
@click.argument("name")
@click.argument("question")
@click.option("--top-k", default=5, show_default=True, help="Number of local chunks to retrieve")
@click.option("--temperature", default=0.2, show_default=True, help="Local generation temperature")
@click.option("--max-tokens", default=512, show_default=True, help="Maximum output tokens")
@click.pass_context
def model_chat(ctx, name, question, top_k, temperature, max_tokens):
    """Ask a Private Language Model a question."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    session = manager.open_session(name)
    try:
        result = session.ask(
            question=question,
            top_k=top_k,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    finally:
        session.close()

    click.echo(f"\n🧠 {name}\n")
    click.echo(result["answer"])
    if result.get("sources"):
        click.echo("\nSources:")
        for source in result["sources"]:
            click.echo(f"  • {source['document_name']} (score={source['score']})")
    if result.get("adapters"):
        click.echo(f"\nWDVA adapters: {', '.join(result['adapters'])}")
    if result.get("warning"):
        click.echo(f"\nWarning: {result['warning']}")


@model.command("repl")
@click.argument("name")
@click.option("--top-k", default=5, show_default=True, help="Number of local chunks to retrieve")
@click.option("--temperature", default=0.2, show_default=True, help="Local generation temperature")
@click.option("--max-tokens", default=512, show_default=True, help="Maximum output tokens")
@click.pass_context
def model_repl(ctx, name, top_k, temperature, max_tokens):
    """Start an interactive local chat session for a profile."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    session = manager.open_session(name)
    click.echo("Type your question and press enter. Type 'exit' to quit.")
    try:
        while True:
            question = click.prompt("you", prompt_suffix=" > ", default="", show_default=False)
            if not question:
                continue
            if question.strip().lower() in {"exit", "quit"}:
                break
            result = session.ask(
                question=question,
                top_k=top_k,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            click.echo(f"\n{name} > {result['answer']}\n")
    finally:
        session.close()


@model.command("package-adapter")
@click.argument("adapter_source")
@click.argument("output_path")
@click.argument("key_path")
@click.pass_context
def model_package_adapter(ctx, adapter_source, output_path, key_path):
    """Encrypt a local adapter safetensors file into a WDVA package."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    packaged_path, key_file = manager.package_wdva_adapter(
        adapter_source=adapter_source,
        output_path=output_path,
        key_path=key_path,
    )
    click.echo(f"✅ Packaged WDVA adapter: {packaged_path}")
    click.echo(f"   Key file: {key_file}")


@model.command("attach-adapter")
@click.argument("name")
@click.argument("adapter_name")
@click.argument("encrypted_path")
@click.argument("key_path")
@click.option("--weight", default=1.0, show_default=True, help="Adapter mixing weight")
@click.option("--description", default="", help="Adapter description")
@click.option("--keyword", "keywords", multiple=True, help="Adapter keywords")
@click.pass_context
def model_attach_adapter(
    ctx,
    name,
    adapter_name,
    encrypted_path,
    key_path,
    weight,
    description,
    keywords,
):
    """Attach an encrypted WDVA adapter to a profile."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    profile = manager.attach_wdva_adapter(
        profile_name=name,
        adapter_name=adapter_name,
        encrypted_path=encrypted_path,
        key_path=key_path,
        weight=weight,
        description=description,
        keywords=list(keywords),
    )
    click.echo(f"✅ Attached adapter '{adapter_name}' to profile '{profile.name}'")
    click.echo(f"   Total adapters: {len(profile.wdva_adapters)}")


@model.command("train-adapter")
@click.argument("name")
@click.argument("adapter_name")
@click.argument("dataset_path")
@click.option("--epochs", default=3, show_default=True, help="Training epochs")
@click.option("--batch-size", default=2, show_default=True, help="Training batch size")
@click.option("--learning-rate", default=1e-4, show_default=True, help="Learning rate")
@click.option("--max-seq-length", default=512, show_default=True, help="Maximum sequence length")
@click.option("--model-name", default=None, help="Override base model used for local training")
@click.pass_context
def model_train_adapter(
    ctx,
    name,
    adapter_name,
    dataset_path,
    epochs,
    batch_size,
    learning_rate,
    max_seq_length,
    model_name,
):
    """Train and package a local WDVA adapter from JSONL examples."""
    manager = _get_model_manager(ctx.obj["vault_path"])
    result = manager.train_wdva_adapter(
        profile_name=name,
        adapter_name=adapter_name,
        dataset_path=dataset_path,
        model_name=model_name,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        max_seq_length=max_seq_length,
    )
    click.echo(f"✅ Trained WDVA adapter '{adapter_name}'")
    click.echo(f"   Adapter dir: {result['adapter_dir']}")
    click.echo(f"   Encrypted package: {result['encrypted_adapter_path']}")
    click.echo(f"   Key file: {result['key_path']}")


@cli.group()
def wallet():
    """Mock-only governed spend workflows for Enclave Wallet."""


@wallet.command("create-envelope")
@click.argument("name")
@click.argument("budget", type=float)
@click.option("--period", default="monthly", show_default=True)
@click.option("--currency", default="USD", show_default=True)
@click.option("--requires-approval-above", default=25.0, type=float, show_default=True)
@click.option("--max-per-transaction", default=None, type=float)
@click.option("--daily-limit", default=None, type=float)
@click.option("--allow-merchant", "merchant_allowlist", multiple=True)
@click.option("--block-merchant", "merchant_blocklist", multiple=True)
@click.pass_context
def wallet_create_envelope(
    ctx,
    name,
    budget,
    period,
    currency,
    requires_approval_above,
    max_per_transaction,
    daily_limit,
    merchant_allowlist,
    merchant_blocklist,
):
    """Create a local governed spend envelope."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    decision, reason = runtime.evaluate_action(
        agent_id="vault-cli",
        module="wallet",
        tool="create_envelope",
        resource=name,
    )
    if decision == "deny":
        click.echo(f"❌ {reason}", err=True)
        sys.exit(1)

    wallet_service = _get_wallet(ctx.obj["vault_path"])
    envelope = wallet_service.create_envelope(
        name=name,
        budget=budget,
        period=period,
        currency=currency,
        requires_approval_above=requires_approval_above,
        max_per_transaction=max_per_transaction,
        daily_limit=daily_limit,
        merchant_allowlist=list(merchant_allowlist),
        merchant_blocklist=list(merchant_blocklist),
    )
    _update_wallet_module_status(runtime, wallet_service)
    runtime.log_event(
        subject="vault-cli",
        module="wallet",
        tool="create_envelope",
        decision="ALLOW",
        resource=envelope.name,
        summary=f"Created wallet envelope '{envelope.name}'",
        metadata=envelope.to_dict(),
        source="cli",
    )
    click.echo(f"✅ Created envelope: {envelope.name}")
    click.echo(f"   Budget: {envelope.budget:.2f} {envelope.currency}")
    click.echo(f"   Approval threshold: {envelope.requires_approval_above}")


@wallet.command("list-envelopes")
@click.pass_context
def wallet_list_envelopes(ctx):
    """List wallet envelopes."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    decision, reason = runtime.evaluate_action(
        agent_id="vault-cli",
        module="wallet",
        tool="list_envelopes",
    )
    if decision == "deny":
        click.echo(f"❌ {reason}", err=True)
        sys.exit(1)

    wallet_service = _get_wallet(ctx.obj["vault_path"])
    envelopes = wallet_service.list_envelopes()
    _update_wallet_module_status(runtime, wallet_service)
    if not envelopes:
        click.echo("No wallet envelopes.")
        return

    click.echo("\n💳 Wallet Envelopes\n")
    for envelope in envelopes:
        click.echo(f"• {envelope.name}")
        click.echo(f"  Budget: {envelope.budget:.2f} {envelope.currency}")
        click.echo(f"  Available: {envelope.available:.2f} {envelope.currency}")
        click.echo(f"  Status: {envelope.status.value}")
        click.echo()


@wallet.command("check-budget")
@click.argument("envelope")
@click.pass_context
def wallet_check_budget(ctx, envelope):
    """Show current budget snapshot for one envelope."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    decision, reason = runtime.evaluate_action(
        agent_id="vault-cli",
        module="wallet",
        tool="check_budget",
        resource=envelope,
    )
    if decision == "deny":
        click.echo(f"❌ {reason}", err=True)
        sys.exit(1)

    wallet_service = _get_wallet(ctx.obj["vault_path"])
    snapshot = wallet_service.check_budget(envelope)
    _update_wallet_module_status(runtime, wallet_service)
    click.echo(json.dumps(snapshot, indent=2))


@wallet.command("request-purchase")
@click.argument("envelope")
@click.argument("amount", type=float)
@click.argument("merchant")
@click.option("--memo", default="", help="Short note for the request")
@click.option("--agent-id", default="vault-cli", show_default=True)
@click.pass_context
def wallet_request_purchase(ctx, envelope, amount, merchant, memo, agent_id):
    """Submit a governed purchase request."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    policy_decision, policy_reason = runtime.evaluate_action(
        agent_id=agent_id,
        module="wallet",
        tool="request_purchase",
        resource=f"{envelope}:{merchant}",
        amount=amount,
    )
    if policy_decision == "deny":
        runtime.log_event(
            subject=agent_id,
            module="wallet",
            tool="request_purchase",
            decision="DENY",
            resource=f"{envelope}:{merchant}",
            summary=policy_reason,
            metadata={"amount": amount},
            source="cli",
        )
        click.echo(f"❌ {policy_reason}", err=True)
        sys.exit(1)

    wallet_service = _get_wallet(ctx.obj["vault_path"])
    outcome = wallet_service.request_purchase(
        envelope,
        amount=amount,
        merchant=merchant,
        agent_id=agent_id,
        memo=memo,
    )
    _update_wallet_module_status(runtime, wallet_service)
    runtime.log_event(
        subject=agent_id,
        module="wallet",
        tool="request_purchase",
        decision=outcome.decision.value.upper(),
        resource=f"{envelope}:{merchant}",
        summary=outcome.reason or policy_reason,
        metadata=outcome.to_dict(),
        source="cli",
    )
    click.echo(json.dumps(outcome.to_dict(), indent=2))


@wallet.command("approve-purchase")
@click.argument("request_id")
@click.option("--approver", default="user", show_default=True)
@click.pass_context
def wallet_approve_purchase(ctx, request_id, approver):
    """Approve a pending wallet request."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    decision, reason = runtime.evaluate_action(
        agent_id="vault-cli",
        module="wallet",
        tool="approve_purchase",
        resource=request_id,
    )
    if decision == "deny":
        click.echo(f"❌ {reason}", err=True)
        sys.exit(1)

    wallet_service = _get_wallet(ctx.obj["vault_path"])
    outcome = wallet_service.approve_purchase(request_id, approver=approver)
    _update_wallet_module_status(runtime, wallet_service)
    runtime.log_event(
        subject=approver,
        module="wallet",
        tool="approve_purchase",
        decision=outcome.decision.value.upper(),
        resource=request_id,
        summary=outcome.reason,
        metadata=outcome.to_dict(),
        source="cli",
    )
    click.echo(json.dumps(outcome.to_dict(), indent=2))


@wallet.command("transactions")
@click.argument("envelope", required=False)
@click.pass_context
def wallet_transactions(ctx, envelope):
    """List captured transactions."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    decision, reason = runtime.evaluate_action(
        agent_id="vault-cli",
        module="wallet",
        tool="get_transactions",
        resource=envelope or "",
    )
    if decision == "deny":
        click.echo(f"❌ {reason}", err=True)
        sys.exit(1)

    wallet_service = _get_wallet(ctx.obj["vault_path"])
    transactions = wallet_service.get_transactions(envelope)
    _update_wallet_module_status(runtime, wallet_service)
    click.echo(json.dumps([item.to_dict() for item in transactions], indent=2))


@wallet.command("freeze-all")
@click.option("--reason", default="vault-cli kill switch", show_default=True)
@click.pass_context
def wallet_freeze_all(ctx, reason):
    """Enable the global kill switch and freeze the wallet."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    wallet_service = _get_wallet(ctx.obj["vault_path"])
    runtime.set_kill_switch(True, reason=reason, actor="vault-cli")
    state = wallet_service.freeze_all(reason=reason)
    _update_wallet_module_status(runtime, wallet_service)
    click.echo(json.dumps(state, indent=2))


@wallet.command("unfreeze-all")
@click.option("--reason", default="vault-cli resume", show_default=True)
@click.pass_context
def wallet_unfreeze_all(ctx, reason):
    """Disable the global kill switch and unfreeze the wallet."""
    runtime = _get_runtime(ctx.obj["vault_path"])
    wallet_service = _get_wallet(ctx.obj["vault_path"])
    runtime.set_kill_switch(False, reason=reason, actor="vault-cli")
    state = wallet_service.unfreeze_all(reason=reason)
    _update_wallet_module_status(runtime, wallet_service)
    click.echo(json.dumps(state, indent=2))


@cli.group()
def sheriff():
    """Local Data Sheriff commands (scan, protect, consent/lease, audit)."""


@sheriff.command("scan")
@click.argument('paths', nargs=-1)
@click.option('--max-files', default=2000, type=int, show_default=True, help='Maximum files to scan')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def sheriff_scan(ctx, paths, max_files, output_json):
    """Scan local files and classify risk."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    summary = sheriff_core.scan_risk(paths=list(paths) if paths else None, max_files=max_files)

    if output_json:
        click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))
        return

    click.echo("\n🛡️ Data Sheriff Risk Summary\n")
    click.echo(f"Scanned files: {summary.total_files}")
    click.echo(f"Critical: {summary.critical_count}")
    click.echo(f"Sensitive: {summary.sensitive_count}")
    click.echo(f"Normal: {summary.normal_count}")

    if summary.recommendations:
        click.echo("\nRecommendations:")
        for rec in summary.recommendations:
            click.echo(f"  • {rec}")

    top = summary.findings[:10]
    if top:
        click.echo("\nTop findings:")
        for finding in top:
            click.echo(f"  • [{finding.label}] score={finding.score} {finding.path}")
            if finding.detected_secrets:
                click.echo(f"    secrets: {', '.join(finding.detected_secrets)}")


@sheriff.command("protect")
@click.argument('paths', nargs=-1)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def sheriff_protect(ctx, paths, output_json):
    """Enable consent barrier rules for selected paths."""
    if not paths:
        click.echo("❌ Error: provide at least one path to protect.", err=True)
        sys.exit(1)
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    rules = sheriff_core.protect_now(paths=list(paths))
    payload = {"count": len(rules), "rules": [r.model_dump(mode="json") for r in rules]}

    if output_json:
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"✅ Enabled consent barrier for {payload['count']} path(s):")
    for rule in rules:
        click.echo(f"  • {rule.path_scope} ({rule.decision})")


@sheriff.command("access")
@click.argument('resource')
@click.argument('purpose')
@click.option('--ttl', 'ttl_seconds', default=900, type=int, show_default=True, help='Lease duration in seconds')
@click.option('--allow-consent', is_flag=True, help='Auto-approve consent when prompt is required')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def sheriff_access(ctx, resource, purpose, ttl_seconds, allow_consent, output_json):
    """Request access and receive lease token when allowed."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    subject_app = "vault-cli"
    result = sheriff_core.request_access(
        subject_app=subject_app,
        resource=resource,
        purpose=purpose,
        ttl_seconds=ttl_seconds,
    )

    if result.decision == AccessDecision.PROMPT:
        approved = allow_consent or click.confirm(
            f"Consent required for {resource}. Approve {ttl_seconds}s lease?",
            default=False,
        )
        result = sheriff_core.consent_decide(
            subject_app=subject_app,
            resource=resource,
            purpose=purpose,
            allow=approved,
            ttl_seconds=ttl_seconds,
        )

    payload = result.model_dump(mode="json")
    if output_json:
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"Decision: {result.decision}")
    click.echo(f"Reason: {result.reason}")
    click.echo(f"Label: {result.label}")
    if result.lease:
        click.echo(f"Lease ID: {result.lease.lease_id}")
        click.echo(f"Expires: {result.lease.expires_at.isoformat()}")


@sheriff.command("read")
@click.argument('resource')
@click.argument('lease_id')
@click.option('--redact/--no-redact', default=True, show_default=True, help='Apply content redaction')
@click.pass_context
def sheriff_read(ctx, resource, lease_id, redact):
    """Read file content using active lease."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    try:
        content = sheriff_core.read_with_lease(
            subject_app="vault-cli",
            resource=resource,
            lease_id=lease_id,
            redact=redact,
        )
    except PermissionError as e:
        click.echo(f"❌ Access denied: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"❌ File not found: {resource}", err=True)
        sys.exit(1)

    click.echo(content)


@sheriff.command("revoke")
@click.argument('lease_id')
@click.pass_context
def sheriff_revoke(ctx, lease_id):
    """Revoke lease token immediately."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    ok = sheriff_core.revoke_lease(lease_id=lease_id, actor="user")
    if ok:
        click.echo(f"✅ Revoked lease: {lease_id}")
    else:
        click.echo(f"❌ Lease not found: {lease_id}", err=True)
        sys.exit(1)


@sheriff.command("audit")
@click.option('--limit', default=50, type=int, show_default=True, help='Max events')
@click.option('--subject', default=None, help='Filter by subject/app')
@click.option('--resource', default=None, help='Filter by resource substring')
@click.option('--decision', type=click.Choice(["ALLOW", "DENY", "PROMPT", "ALLOW_WITH_LEASE"]), default=None)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def sheriff_audit(ctx, limit, subject, resource, decision, output_json):
    """Show audit events."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    decision_filter = AccessDecision(decision) if decision else None
    events = sheriff_core.audit_events(
        limit=limit,
        subject=subject,
        resource=resource,
        decision=decision_filter,
    )

    if output_json:
        click.echo(json.dumps({"items": events}, indent=2))
        return

    if not events:
        click.echo("No audit events.")
        return

    click.echo(f"Audit events ({len(events)}):")
    for event in events:
        click.echo(
            f"  • {event.get('timestamp')} | {event.get('decision')} | {event.get('subject')} | {event.get('action')} | {event.get('resource')}"
        )


@sheriff.command("hardening")
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def sheriff_hardening(ctx, output_json):
    """Check MCP configuration hardening alerts."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    alerts = sheriff_core.hardening_report()
    if output_json:
        click.echo(json.dumps({"alerts": alerts}, indent=2))
        return

    click.echo(f"Hardening alerts: {len(alerts)}")
    for alert in alerts:
        click.echo(f"  • [{alert.get('severity', 'info')}] {alert.get('message')}")
        if alert.get("path"):
            click.echo(f"    path: {alert['path']}")


@sheriff.command("status")
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def sheriff_status(ctx, output_json):
    """Show system enforcement backend status."""
    sheriff_core = _get_sheriff(ctx.obj['vault_path'])
    status = sheriff_core.enforcement_status()

    if output_json:
        click.echo(json.dumps(status, indent=2))
        return

    click.echo(f"Backend: {status['backend']}")
    click.echo(f"Enabled: {status['enabled']}")
    click.echo(f"Mode: {status['mode']}")
    click.echo(f"Message: {status['message']}")


@model.command("package")
@click.argument("adapter_dir")
@click.argument("output_path")
@click.option("--password", prompt=True, hide_input=True, help="Encryption password")
@click.option("--name", default="", help="Adapter name metadata")
@click.option("--description", default="", help="Adapter description")
@click.option("--train-mode", type=click.Choice(["sft", "dpo", "orpo", "grpo"]), default="sft")
@click.option("--qat", is_flag=True, help="Mark as QAT quantized")
@click.option("--qat-bits", type=int, default=8, help="QAT bit width")
@click.option("--base-model", default="", help="Base model name")
@click.option("--format", "output_format", type=click.Choice(["enclave", "zip"]), default="enclave")
@click.pass_context
def model_package(ctx, adapter_dir, output_path, password, name, description, train_mode, qat, qat_bits, base_model, output_format):
    """Package an adapter for distribution."""
    from advanced_vault.training.adapter_packager import AdapterPackager, AdapterMetadata

    packager = AdapterPackager()
    metadata = {
        "name": name or Path(adapter_dir).name,
        "description": description,
        "train_mode": train_mode,
        "qat_enabled": qat,
        "qat_bits": qat_bits,
        "base_model": base_model,
    }
    try:
        result = packager.package_adapter(
            adapter_dir=adapter_dir,
            output_path=output_path,
            password=password,
            metadata=metadata,
            format=output_format,
        )
        click.echo(f"✅ Packaged adapter to {result}")
    except Exception as e:
        click.echo(f"❌ Packaging failed: {e}", err=True)
        sys.exit(1)


@model.command("unpack")
@click.argument("package_path")
@click.argument("output_dir")
@click.option("--password", prompt=True, hide_input=True, help="Decryption password")
@click.pass_context
def model_unpack(ctx, package_path, output_dir, password):
    """Unpack an adapter package."""
    from advanced_vault.training.adapter_packager import AdapterPackager

    packager = AdapterPackager()
    try:
        meta = packager.unpack_adapter(
            package_path=package_path,
            output_dir=output_dir,
            password=password,
        )
        click.echo(f"✅ Unpacked adapter '{meta.name}' to {output_dir}")
        click.echo(f"   Train mode: {meta.train_mode}")
        click.echo(f"   QAT: {meta.qat_enabled} ({meta.qat_bits}-bit)")
        if meta.base_model:
            click.echo(f"   Base model: {meta.base_model}")
    except Exception as e:
        click.echo(f"❌ Unpacking failed: {e}", err=True)
        sys.exit(1)


@model.command("verify")
@click.argument("package_path")
@click.option("--password", prompt=True, hide_input=True, help="Decryption password")
@click.pass_context
def model_verify(ctx, package_path, password):
    """Verify an adapter package integrity."""
    from advanced_vault.training.adapter_packager import AdapterPackager

    packager = AdapterPackager()
    try:
        result = packager.verify_package(package_path, password=password)
        if result["valid"]:
            meta = result["metadata"]
            click.echo(f"✅ Package is valid")
            click.echo(f"   Name: {meta.name}")
            click.echo(f"   Checksum match: {result['checksum_match']}")
        else:
            click.echo(f"❌ Package invalid: {result.get('error')}", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Verification failed: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()


# --- Prosumer CLI Commands ---

@cli.group()
def prosumer():
    """Personal data vault and adapter management for consumers."""
    pass


@prosumer.group()
def vaults():
    """Manage personal data vault categories."""
    pass


@vaults.command("list")
def vaults_list():
    """List all available vault categories."""
    from advanced_vault.prosumer.vault_categories import list_categories
    
    click.echo("📦  Available Vault Categories\n")
    for category in list_categories():
        click.echo(f"{category.icon}  {category.name}")
        click.echo(f"   ID: {category.id}")
        click.echo(f"   Description: {category.description}")
        click.echo(f"   Privacy: {category.privacy_level.value}")
        click.echo(f"   Min docs for training: {category.min_documents_for_training}")
        click.echo(f"   Recommended preset: {category.recommended_preset}")
        click.echo()


@prosumer.command("classify")
@click.argument("file_path")
@click.option("--preview", default=3000, help="Number of chars to extract for content analysis")
@click.pass_context
def prosumer_classify(ctx, file_path, preview):
    """Classify a document into a vault category."""
    from advanced_vault.prosumer.document_classifier import DocumentClassifier
    
    vault_path = ctx.obj.get('vault_path', "~/.vault")
    classifier = DocumentClassifier(vault_path=vault_path)
    
    if not Path(file_path).exists():
        click.echo(f"❌ File not found: {file_path}", err=True)
        sys.exit(1)
    
    click.echo(f"🔍 Classifying {file_path}...")
    result = classifier.classify_file(file_path, extract_content=True, max_preview_chars=preview)
    
    click.echo(f"\n📋  {result.filename}")
    click.echo(f"   Type: {result.detected_type}")
    click.echo(f"   MIME: {result.mime_type}")
    click.echo(f"   Category: {result.category.name} ({result.category.id})")
    click.echo(f"   Confidence: {result.confidence:.1%}")
    
    if result.is_high_confidence:
        click.echo(f"   ✅ High confidence — auto-categorized")
    elif result.needs_review:
        click.echo(f"   ⚠️  Medium confidence — please review")
    else:
        click.echo(f"   ℹ️  Low confidence — placed in Personal Knowledge Vault")
    
    if result.warnings:
        for warning in result.warnings:
            click.echo(f"   ⚠️  {warning}")


@prosumer.command("classify-folder")
@click.argument("folder_path")
@click.option("--recursive/--no-recursive", default=True, help="Scan subdirectories")
@click.option("--max-files", default=1000, help="Maximum files to process")
@click.pass_context
def prosumer_classify_folder(ctx, folder_path, recursive, max_files):
    """Classify all documents in a folder."""
    from advanced_vault.prosumer.document_classifier import DocumentClassifier
    
    vault_path = ctx.obj.get('vault_path', "~/.vault")
    classifier = DocumentClassifier(vault_path=vault_path)
    
    if not Path(folder_path).is_dir():
        click.echo(f"❌ Not a directory: {folder_path}", err=True)
        sys.exit(1)
    
    click.echo(f"📂 Scanning {folder_path}...")
    results = classifier.classify_folder(folder_path, recursive=recursive, max_files=max_files)
    
    summary = classifier.get_category_summary(results)
    
    click.echo(f"\n📊 Classification Summary ({len(results)} files)\n")
    for cat_id, stats in summary.items():
        click.echo(f"{stats['category_name']}: {stats['count']} files "
                   f"(avg confidence: {stats['avg_confidence']:.1%})")
        if stats['needs_review'] > 0:
            click.echo(f"   ⚠️  {stats['needs_review']} need review")


@prosumer.group()
def presets():
    """Manage adapter training presets."""
    pass


@presets.command("list")
def presets_list():
    """List all training presets."""
    from advanced_vault.prosumer.adapter_presets import list_presets
    
    click.echo("🎯  Training Presets\n")
    for preset in list_presets():
        click.echo(f"{preset.icon}  {preset.name} ({preset.id})")
        click.echo(f"   Category: {preset.category_id}")
        click.echo(f"   Method: {preset.training_method.value.upper()}")
        click.echo(f"   Base model: {preset.base_model}")
        click.echo(f"   Est. time: ~{preset.estimated_training_time_minutes} min")
        click.echo(f"   Min docs: {preset.min_documents}")
        if preset.require_disclaimer:
            click.echo(f"   ⚠️  Requires disclaimer")
        click.echo()


@prosumer.group()
def backup():
    """Backup and restore encrypted adapters."""
    pass


@backup.command("export")
@click.argument("adapter_path")
@click.option("--name", default="", help="Adapter name")
@click.option("--category", default="personal", help="Vault category ID")
@click.option("--preset", default="general", help="Training preset ID")
@click.option("--output", default="", help="Output file path")
@click.pass_context
def backup_export(ctx, adapter_path, name, category, preset, output):
    """Export an encrypted adapter to a portable file."""
    from advanced_vault.prosumer.adapter_backup import AdapterBackupManager, BackupFormat
    
    vault_path = ctx.obj.get('vault_path', "~/.vault")
    manager = AdapterBackupManager(vault_path=vault_path)
    
    if not Path(adapter_path).exists():
        click.echo(f"❌ Adapter not found: {adapter_path}", err=True)
        sys.exit(1)
    
    adapter_name = name or Path(adapter_path).stem
    
    try:
        output_path = manager.export_adapter(
            adapter_path=adapter_path,
            adapter_name=adapter_name,
            category_id=category,
            preset_id=preset,
            output_path=output or None,
            format=BackupFormat.ENCLAVE,
        )
        click.echo(f"✅ Exported adapter to: {output_path}")
        click.echo(f"   Format: Enclave package (encrypted + metadata)")
        click.echo(f"   No raw documents included — only encrypted learned weights")
    except Exception as e:
        click.echo(f"❌ Export failed: {e}", err=True)
        sys.exit(1)


@backup.command("import")
@click.argument("backup_path")
@click.option("--verify/--no-verify", default=True, help="Verify integrity after import")
@click.pass_context
def backup_import(ctx, backup_path, verify):
    """Import an adapter from a backup file."""
    from advanced_vault.prosumer.adapter_backup import AdapterBackupManager
    
    vault_path = ctx.obj.get('vault_path', "~/.vault")
    manager = AdapterBackupManager(vault_path=vault_path)
    
    if not Path(backup_path).exists():
        click.echo(f"❌ Backup not found: {backup_path}", err=True)
        sys.exit(1)
    
    try:
        adapter_path, manifest = manager.import_adapter(backup_path, verify_integrity=verify)
        click.echo(f"✅ Imported adapter to: {adapter_path}")
        if manifest:
            click.echo(f"   Name: {manifest.adapter_name}")
            click.echo(f"   Category: {manifest.category_id}")
            click.echo(f"   Documents: {manifest.document_count}")
            click.echo(f"   Training: {manifest.training_method}")
    except Exception as e:
        click.echo(f"❌ Import failed: {e}", err=True)
        sys.exit(1)


@backup.command("list")
@click.pass_context
def backup_list(ctx):
    """List all adapter backups."""
    from advanced_vault.prosumer.adapter_backup import AdapterBackupManager
    
    vault_path = ctx.obj.get('vault_path', "~/.vault")
    manager = AdapterBackupManager(vault_path=vault_path)
    
    backups = manager.list_backups()
    
    if not backups:
        click.echo("📦 No backups found")
        return
    
    click.echo(f"💾  Adapter Backups ({len(backups)} total)\n")
    for backup in backups:
        size_kb = backup['size'] // 1024
        click.echo(f"   {backup['filename']}")
        click.echo(f"      Size: {size_kb} KB  |  Modified: {backup['modified'][:10]}")
        click.echo()


@backup.command("verify")
@click.argument("backup_path")
@click.pass_context
def backup_verify(ctx, backup_path):
    """Verify a backup file's integrity."""
    from advanced_vault.prosumer.adapter_backup import AdapterBackupManager
    
    vault_path = ctx.obj.get('vault_path', "~/.vault")
    manager = AdapterBackupManager(vault_path=vault_path)
    
    if not Path(backup_path).exists():
        click.echo(f"❌ Backup not found: {backup_path}", err=True)
        sys.exit(1)
    
    report = manager.verify_adapter(backup_path)
    
    click.echo(f"🔍 Verification Report: {backup_path}\n")
    click.echo(f"   Exists: {'✅' if report['exists'] else '❌'}")
    click.echo(f"   Readable: {'✅' if report['readable'] else '❌'}")
    click.echo(f"   Encryption detected: {'✅' if report.get('encryption_detected') else '❌'}")
    
    if 'checksum_match' in report and report['checksum_match'] is not None:
        click.echo(f"   Checksum: {'✅ Match' if report['checksum_match'] else '❌ Mismatch'}")
    
    if report.get('errors'):
        for error in report['errors']:
            click.echo(f"   ❌ Error: {error}")
    
    if report.get('warnings'):
        for warning in report['warnings']:
            click.echo(f"   ⚠️  Warning: {warning}")
    
    if report.get('valid'):
        click.echo(f"\n✅ Backup is valid")
    else:
        click.echo(f"\n❌ Backup has issues")
        sys.exit(1)
