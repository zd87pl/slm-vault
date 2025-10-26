"""
Personal Vault - macOS Menu Bar App

A native macOS menu bar application for managing your personal vault.
Uses rumps (Ridiculously Uncomplicated macOS Python Statusbar apps).
"""

import os
import sys
import rumps
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from advanced_vault.encrypted_kv import QueryFilter


class VaultApp(rumps.App):
    """Personal Vault macOS Menu Bar App."""

    def __init__(self):
        """Initialize the app."""
        super(VaultApp, self).__init__(
            "🔐 Vault",
            icon=None,  # We'll use emoji in title instead
            quit_button=None  # We'll add custom quit
        )

        # Vault setup
        self.vault_path = Path("~/.vault").expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

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

        # Initialize vault
        self.vault = HybridVault(
            master_key=self.master_key,
            kv_db_path=str(self.db_path),
            enable_router_logging=False
        )

        # Build menu
        self.menu = [
            rumps.MenuItem("Add Secret", callback=self.add_secret),
            rumps.MenuItem("Add Note", callback=self.add_note),
            rumps.separator,
            rumps.MenuItem("View Secrets", callback=self.view_secrets),
            rumps.MenuItem("Search...", callback=self.search),
            rumps.separator,
            rumps.MenuItem("Statistics", callback=self.show_stats),
            rumps.MenuItem("Settings", callback=self.show_settings),
            rumps.separator,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

    def add_secret(self, _):
        """Add a new secret to the vault."""
        window = rumps.Window(
            message="Enter secret details:",
            title="Add Secret",
            default_text="",
            ok="Add",
            cancel="Cancel",
            dimensions=(320, 120)
        )

        # Get service name
        service_window = rumps.Window(
            message="Service name (e.g., stripe, github):",
            title="Add Secret - Step 1/2",
            default_text="",
            ok="Next",
            cancel="Cancel"
        )
        service_response = service_window.run()

        if service_response.clicked == 0:  # Cancel
            return

        service = service_response.text.strip()
        if not service:
            rumps.alert("Error", "Service name cannot be empty")
            return

        # Get secret value
        secret_window = rumps.Window(
            message=f"Enter secret for {service}:",
            title="Add Secret - Step 2/2",
            default_text="",
            ok="Add",
            cancel="Cancel",
            dimensions=(320, 80)
        )
        secret_response = secret_window.run()

        if secret_response.clicked == 0:  # Cancel
            return

        secret = secret_response.text.strip()
        if not secret:
            rumps.alert("Error", "Secret cannot be empty")
            return

        # Store in vault
        try:
            self.vault.store(
                content=secret,
                data_type="secret",
                service=service,
                tags=[]
            )
            rumps.notification(
                title="Secret Added",
                subtitle=f"Service: {service}",
                message="Secret stored securely in vault",
                sound=True
            )
        except Exception as e:
            rumps.alert("Error", f"Failed to store secret: {str(e)}")

    def add_note(self, _):
        """Add a knowledge note to the vault."""
        window = rumps.Window(
            message="Enter your note:",
            title="Add Note",
            default_text="",
            ok="Add",
            cancel="Cancel",
            dimensions=(400, 160)
        )
        response = window.run()

        if response.clicked == 1:  # OK
            note = response.text.strip()
            if note:
                try:
                    # Store as a special service
                    import uuid
                    note_id = str(uuid.uuid4())[:8]
                    self.vault.store(
                        content=note,
                        data_type="secret",  # Using KV for now
                        service=f"note_{note_id}",
                        tags=["note"],
                        description="Knowledge note"
                    )
                    rumps.notification(
                        title="Note Added",
                        subtitle="",
                        message="Note stored in vault",
                        sound=True
                    )
                except Exception as e:
                    rumps.alert("Error", f"Failed to store note: {str(e)}")

    def view_secrets(self, _):
        """View all secrets in the vault."""
        try:
            entries = self.vault.kv_store.search(QueryFilter())

            if not entries:
                rumps.alert("Vault", "No secrets stored yet")
                return

            # Create submenu with all secrets
            secrets_menu = []
            for entry in entries:
                # Create a callback to view this secret
                def make_callback(e):
                    def callback(_):
                        self.view_secret_detail(e)
                    return callback

                secrets_menu.append(
                    rumps.MenuItem(entry.service, callback=make_callback(entry))
                )

            # Show in a new window listing
            message = "\n".join([f"• {e.service}" for e in entries])
            rumps.alert(
                title=f"Vault Secrets ({len(entries)})",
                message=message,
                ok="OK"
            )

        except Exception as e:
            rumps.alert("Error", f"Failed to load secrets: {str(e)}")

    def view_secret_detail(self, entry):
        """View details of a specific secret."""
        try:
            secret = self.vault.kv_store.get(entry.service)

            message = f"Service: {entry.service}\n"
            if entry.tags:
                message += f"Tags: {', '.join(entry.tags)}\n"
            if entry.description:
                message += f"Description: {entry.description}\n"
            message += f"\nSecret: {secret}"

            rumps.alert(
                title=entry.service,
                message=message,
                ok="OK"
            )
        except Exception as e:
            rumps.alert("Error", f"Failed to load secret: {str(e)}")

    def search(self, _):
        """Search the vault."""
        window = rumps.Window(
            message="Enter search query:",
            title="Search Vault",
            default_text="",
            ok="Search",
            cancel="Cancel"
        )
        response = window.run()

        if response.clicked == 1 and response.text.strip():
            query = response.text.strip()
            try:
                result = self.vault.query(query)

                strategy = result.get('strategy', 'unknown')
                if result.get('error'):
                    rumps.alert("Search Results", f"Error: {result['error']}")
                elif result.get('result'):
                    message = f"Strategy: {strategy}\n\nResult:\n{result['result']}"
                    rumps.alert("Search Results", message)
                else:
                    rumps.alert("Search Results", "No results found")
            except Exception as e:
                rumps.alert("Error", f"Search failed: {str(e)}")

    def show_stats(self, _):
        """Show vault statistics."""
        try:
            stats = self.vault.get_stats()

            layer1 = stats['layer_1']
            layer2 = stats['layer_2']

            message = f"Layer 1 (Encrypted KV):\n"
            message += f"  Total entries: {layer1['total_entries']}\n"
            message += f"  Services: {', '.join(layer1['services']) if layer1['services'] else 'none'}\n"
            message += f"\nLayer 2 (DoRA):\n"
            message += f"  Status: {'Active' if layer2['initialized'] else 'Not configured'}\n"
            message += f"\nVault path: {self.vault_path}"

            rumps.alert(
                title="Vault Statistics",
                message=message,
                ok="OK"
            )
        except Exception as e:
            rumps.alert("Error", f"Failed to load stats: {str(e)}")

    def show_settings(self, _):
        """Show settings."""
        message = f"Vault Path: {self.vault_path}\n"
        message += f"Master Key: {self.key_path}\n"
        message += f"Database: {self.db_path}\n"
        message += f"\nEncryption: ChaCha20-Poly1305\n"
        message += f"Key Size: 32 bytes (256-bit)"

        rumps.alert(
            title="Vault Settings",
            message=message,
            ok="OK"
        )

    def quit_app(self, _):
        """Quit the application."""
        # Close vault
        if self.vault:
            self.vault.close()
        rumps.quit_application()


def main():
    """Main entry point for the app."""
    VaultApp().run()


if __name__ == "__main__":
    main()
