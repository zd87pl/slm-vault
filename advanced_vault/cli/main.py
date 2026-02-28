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
from advanced_vault.encrypted_kv import QueryFilter
from advanced_vault.sheriff.core import SheriffCore
from advanced_vault.sheriff.models import AccessDecision


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
    return SheriffCore(vault_path=vault_path)


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


if __name__ == '__main__':
    cli()
