#!/usr/bin/env python3
"""
Enclave - Secure Encrypted Vault with AI Inference
Beautiful Material Design UI for encrypted vault management
"""

import flet as ft
import os
import sys
import threading
import requests
from pathlib import Path
from typing import Optional
from datetime import datetime
import time

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from advanced_vault.encrypted_kv import QueryFilter
from auth_screen import AuthScreen


class VaultApp:
    """Enclave - Secure Vault GUI Application."""

    def __init__(self, page: ft.Page):
        """Initialize the app."""
        self.page = page
        self.page.title = "🔐 Enclave"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0

        # Backend configuration
        self.backend_url = os.getenv(
            "ENCLAVE_BACKEND_URL",
            "https://keen-curiosity-production-1288.up.railway.app"
        )

        # Authentication state
        self.session_data = None
        self.vault = None

        # RunPod connectivity state
        self.runpod_status = "unknown"  # unknown, connected, disconnected
        self.runpod_endpoint = os.getenv("RUNPOD_ENDPOINT_ID")
        self.runpod_api_key = os.getenv("RUNPOD_API_KEY")
        self.last_check = None

        # Vault setup paths
        self.vault_path = Path("~/.vault").expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self.key_path = self.vault_path / "master.key"
        self.db_path = self.vault_path / "vault.db"

        # UI state
        self.current_view = "secrets"
        self.search_query = ""
        self.selected_type = "all"

        # Check for existing session
        self.check_authentication()

    def check_authentication(self):
        """Check if user is authenticated."""
        # Try to load existing session
        self.session_data = AuthScreen.load_session()

        if self.session_data:
            # User is authenticated, initialize vault
            self.initialize_vault()
            self.build_ui()
        else:
            # Show authentication screen
            self.show_auth_screen()

    def show_auth_screen(self):
        """Show authentication screen."""
        auth_screen = AuthScreen(
            page=self.page,
            backend_url=self.backend_url,
            on_auth_success=self.on_auth_success
        )

        self.page.clean()
        self.page.add(auth_screen.get_view())
        self.page.update()

    def on_auth_success(self, session_data: dict):
        """Called when authentication succeeds."""
        self.session_data = session_data

        # Initialize vault
        self.initialize_vault()

        # Build main UI
        self.page.clean()
        self.build_ui()
        self.page.update()

    def initialize_vault(self):
        """Initialize vault after authentication."""
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

    def logout(self):
        """Logout user."""
        # Clear session
        AuthScreen.clear_session()
        self.session_data = None
        self.vault = None

        # Show auth screen
        self.show_auth_screen()

    def check_runpod_connectivity(self):
        """Check RunPod endpoint connectivity."""
        if not self.runpod_endpoint or not self.runpod_api_key:
            self.runpod_status = "not_configured"
            if hasattr(self, 'connectivity_icon'):
                self.update_connectivity_icon()
                self.page.update()
            return

        # Run in background thread
        def _check():
            try:
                response = requests.get(
                    f"https://api.runpod.io/v2/{self.runpod_endpoint}/health",
                    headers={"Authorization": f"Bearer {self.runpod_api_key}"},
                    timeout=5.0
                )
                if response.status_code == 200:
                    self.runpod_status = "connected"
                else:
                    self.runpod_status = "error"
            except Exception as e:
                self.runpod_status = "disconnected"

            self.last_check = datetime.now()

            # Update UI
            if hasattr(self, 'connectivity_icon'):
                self.update_connectivity_icon()
                self.page.update()

        thread = threading.Thread(target=_check, daemon=True)
        thread.start()

    def update_connectivity_icon(self):
        """Update the connectivity icon based on status."""
        if self.runpod_status == "connected":
            self.connectivity_icon.icon = ft.Icons.CLOUD_DONE
            self.connectivity_icon.icon_color = "#4caf50"  # Green
            self.connectivity_icon.tooltip = "RunPod: Connected ✓"
        elif self.runpod_status == "disconnected":
            self.connectivity_icon.icon = ft.Icons.CLOUD_OFF
            self.connectivity_icon.icon_color = "#f44336"  # Red
            self.connectivity_icon.tooltip = "RunPod: Disconnected"
        elif self.runpod_status == "not_configured":
            self.connectivity_icon.icon = ft.Icons.CLOUD_QUEUE
            self.connectivity_icon.icon_color = "#9e9e9e"  # Gray
            self.connectivity_icon.tooltip = "RunPod: Not configured"
        else:
            self.connectivity_icon.icon = ft.Icons.CLOUD_SYNC
            self.connectivity_icon.icon_color = "#ffc107"  # Amber
            self.connectivity_icon.tooltip = "RunPod: Checking..."

    def build_ui(self):
        """Build the main UI."""
        # Create connectivity indicator
        self.connectivity_icon = ft.IconButton(
            icon=ft.Icons.CLOUD_SYNC,
            icon_color="#9e9e9e",
            tooltip="RunPod: Checking...",
            on_click=lambda _: self.check_runpod_connectivity(),
            icon_size=24
        )

        # User info for app bar
        user_email = self.session_data.get("user", {}).get("email", "User") if self.session_data else "User"

        # App bar
        self.page.appbar = ft.AppBar(
            title=ft.Text("🔐 Enclave", size=20, weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor="#2c2c2c",
            actions=[
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.PERSON, size=16, color="#9e9e9e"),
                        ft.Text(user_email, size=12, color="#9e9e9e"),
                    ], spacing=5),
                    padding=ft.padding.only(right=10),
                ),
                ft.VerticalDivider(width=1, color="#424242"),
                self.connectivity_icon,
                ft.VerticalDivider(width=1, color="#424242"),
                ft.IconButton(
                    ft.Icons.ADD_CIRCLE,
                    tooltip="Add Secret",
                    on_click=self.show_add_dialog,
                    icon_size=28
                ),
                ft.IconButton(
                    ft.Icons.REFRESH,
                    tooltip="Refresh",
                    on_click=lambda _: self.load_secrets(),
                    icon_size=28
                ),
                ft.IconButton(
                    ft.Icons.LOGOUT,
                    tooltip="Logout",
                    on_click=lambda _: self.logout(),
                    icon_size=28,
                    icon_color="#f44336"
                ),
            ],
        )

        # Start initial connectivity check
        self.check_runpod_connectivity()

        # Search bar
        self.search_field = ft.TextField(
            hint_text="Search secrets...",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.on_search_change,
            expand=True,
        )

        # Filter dropdown
        self.type_filter = ft.Dropdown(
            width=150,
            value="all",
            options=[
                ft.dropdown.Option("all", "All"),
                ft.dropdown.Option("secret", "Secrets"),
                ft.dropdown.Option("knowledge", "Knowledge"),
            ],
            on_change=self.on_filter_change,
        )

        # Search row
        search_row = ft.Row(
            [
                self.search_field,
                self.type_filter,
            ],
            spacing=10,
        )

        # Secrets list
        self.secrets_list = ft.Column(
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Stats row
        self.stats_text = ft.Text("", size=12, color="#9e9e9e")

        # Navigation rail
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.KEY_OUTLINED,
                    selected_icon=ft.Icons.KEY,
                    label="Secrets",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.LIGHTBULB_OUTLINED,
                    selected_icon=ft.Icons.LIGHTBULB,
                    label="Knowledge",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.BAR_CHART_OUTLINED,
                    selected_icon=ft.Icons.BAR_CHART,
                    label="Statistics",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Settings",
                ),
            ],
            on_change=self.on_nav_change,
        )

        # Main content
        main_content = ft.Container(
            content=ft.Column(
                [
                    search_row,
                    ft.Divider(height=1),
                    self.secrets_list,
                    ft.Divider(height=1),
                    self.stats_text,
                ],
                spacing=10,
                expand=True,
            ),
            padding=20,
            expand=True,
        )

        # Layout
        self.page.add(
            ft.Row(
                [
                    self.nav_rail,
                    ft.VerticalDivider(width=1),
                    main_content,
                ],
                spacing=0,
                expand=True,
            )
        )

        # Load initial data
        self.load_secrets()

    def load_secrets(self):
        """Load secrets from vault."""
        self.secrets_list.controls.clear()

        # Get all entries
        from advanced_vault.encrypted_kv import QueryFilter, EntryType

        # Create filter based on selected type
        query_filter = QueryFilter()
        if self.selected_type == "secret":
            query_filter.entry_type = EntryType.SECRET
        # Note: "knowledge" entries are not yet stored in KV (Layer 2 not implemented)

        result = self.vault.kv_store.search(query_filter)

        # Convert EncryptedEntry objects to dicts
        entries = []
        for entry in result:
            entries.append({
                'id': entry.id,
                'service': entry.service,
                'data_type': 'secret',  # All KV entries are secrets for now
                'tags': entry.tags,
                'timestamp': entry.updated_at.timestamp() if entry.updated_at else 0,
                'description': entry.description
            })

        # Filter by search query
        if self.search_query:
            entries = [
                e for e in entries
                if self.search_query.lower() in e.get('service', '').lower()
                or self.search_query.lower() in ' '.join(e.get('tags', [])).lower()
            ]

        # Sort by timestamp (newest first)
        entries.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        # Create cards
        if entries:
            for entry in entries:
                card = self.create_secret_card(entry)
                self.secrets_list.controls.append(card)
        else:
            self.secrets_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.LOCK_OPEN, size=64, color="#9e9e9e"),
                            ft.Text("No secrets yet", size=20, weight=ft.FontWeight.BOLD),
                            ft.Text("Click + to add your first secret", color="#9e9e9e"),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    alignment=ft.alignment.center,
                    expand=True,
                )
            )

        # Update stats
        stats = self.vault.get_stats()
        layer1 = stats['layer_1']
        self.stats_text.value = f"📊 {layer1['total_entries']} entries | {len(layer1['services'])} services"

        self.page.update()

    def create_secret_card(self, entry):
        """Create a card for a secret."""
        service = entry.get('service', 'Unknown')
        data_type = entry.get('data_type', 'secret')
        tags = entry.get('tags', [])

        # Icon based on type
        icon = ft.Icons.KEY if data_type == 'secret' else ft.Icons.LIGHTBULB
        color = "#2196f3" if data_type == 'secret' else "#ffc107"

        # Tags chips
        tag_chips = [
            ft.Chip(
                label=ft.Text(tag, size=10),
                bgcolor="#2c2c2c",
                padding=5,
            )
            for tag in tags[:3]  # Show max 3 tags
        ]

        return ft.Card(
            content=ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=color, size=32),
                        ft.Column(
                            [
                                ft.Text(service, weight=ft.FontWeight.BOLD, size=16),
                                ft.Row(tag_chips, spacing=5) if tag_chips else ft.Container(),
                            ],
                            spacing=5,
                            expand=True,
                        ),
                        ft.Row(
                            [
                                ft.IconButton(
                                    ft.Icons.VISIBILITY,
                                    tooltip="View",
                                    on_click=lambda _, e=entry: self.view_secret(e),
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    tooltip="Delete",
                                    on_click=lambda _, e=entry: self.delete_secret(e),
                                    icon_color="#f44336",
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=15,
            ),
        )

    def show_add_dialog(self, e):
        """Show add secret dialog."""
        try:
            print("Opening add dialog...")  # Debug

            service_field = ft.TextField(label="Service (e.g., stripe, github)", autofocus=True)
            content_field = ft.TextField(label="Secret / Knowledge", password=True, multiline=True)
            tags_field = ft.TextField(label="Tags (comma-separated)", hint_text="payment, production")
            description_field = ft.TextField(label="Description (optional)", multiline=True)

            type_radio = ft.RadioGroup(
                content=ft.Row([
                    ft.Radio(value="secret", label="Secret"),
                    ft.Radio(value="knowledge", label="Knowledge"),
                ]),
                value="secret"
            )

            def close_dialog():
                dialog.open = False
                self.page.update()

            def add_entry(e):
                if not service_field.value or not content_field.value:
                    service_field.error_text = "Required" if not service_field.value else None
                    content_field.error_text = "Required" if not content_field.value else None
                    self.page.update()
                    return

                # Parse tags
                tags = [t.strip() for t in tags_field.value.split(',')] if tags_field.value else []

                # Store in vault
                self.vault.store(
                    content=content_field.value,
                    data_type=type_radio.value,
                    service=service_field.value,
                    tags=tags,
                    description=description_field.value or None
                )

                # Show success snackbar
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"✅ Added {service_field.value}"),
                    bgcolor="#4caf50",
                )
                self.page.snack_bar.open = True

                close_dialog()
                self.load_secrets()

            dialog = ft.AlertDialog(
                title=ft.Text("Add Entry"),
                content=ft.Container(
                    content=ft.Column(
                        [
                            type_radio,
                            service_field,
                            content_field,
                            tags_field,
                            description_field,
                        ],
                        spacing=15,
                        tight=True,
                    ),
                    width=500,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: close_dialog()),
                    ft.ElevatedButton("Add", on_click=add_entry),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            self.page.dialog = dialog
            dialog.open = True
            self.page.update()

        except Exception as ex:
            print(f"Error opening add dialog: {ex}")
            import traceback
            traceback.print_exc()
            # Show error to user
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Error: {str(ex)}"),
                bgcolor="#f44336",
            )
            self.page.snack_bar.open = True
            self.page.update()

    def view_secret(self, entry):
        """Show secret details."""
        service = entry.get('service', 'Unknown')

        # Retrieve secret
        secret_value = self.vault.kv_store.get(service)
        result = {"result": secret_value} if secret_value else {"error": "Secret not found"}

        if result.get('error'):
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {result['error']}"),
                bgcolor="#f44336",
            )
            self.page.snack_bar.open = True
            self.page.update()
            return

        content = result.get('result', '')
        data_type = entry.get('data_type', 'secret')
        tags = ', '.join(entry.get('tags', []))
        description = entry.get('description', 'None')

        content_field = ft.TextField(
            value=content,
            multiline=True,
            read_only=True,
            min_lines=3,
            max_lines=10,
        )

        def copy_to_clipboard(e):
            self.page.set_clipboard(content)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("📋 Copied to clipboard"),
                bgcolor="#2196f3",
            )
            self.page.snack_bar.open = True
            self.page.update()

        def close_dialog():
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text(f"🔐 {service}"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"Type: {data_type.title()}", size=12, color="#9e9e9e"),
                        ft.Text(f"Tags: {tags or 'None'}", size=12, color="#9e9e9e"),
                        ft.Text(f"Description: {description}", size=12, color="#9e9e9e"),
                        ft.Divider(),
                        content_field,
                    ],
                    spacing=10,
                    tight=True,
                ),
                width=500,
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda _: close_dialog()),
                ft.ElevatedButton(
                    "Copy",
                    icon=ft.Icons.COPY,
                    on_click=copy_to_clipboard
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def delete_secret(self, entry):
        """Delete a secret."""
        service = entry.get('service', 'Unknown')

        def confirm_delete(e):
            self.vault.kv_store.delete(service)

            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"🗑️ Deleted {service}"),
                bgcolor="#f44336",
            )
            self.page.snack_bar.open = True

            dialog.open = False
            self.page.update()
            self.load_secrets()

        def close_dialog():
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Confirm Delete"),
            content=ft.Text(f"Are you sure you want to delete '{service}'? This cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog()),
                ft.ElevatedButton(
                    "Delete",
                    bgcolor="#f44336",
                    on_click=confirm_delete
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def on_search_change(self, e):
        """Handle search query change."""
        self.search_query = e.control.value
        self.load_secrets()

    def on_filter_change(self, e):
        """Handle filter change."""
        self.selected_type = e.control.value
        self.load_secrets()

    def on_nav_change(self, e):
        """Handle navigation change."""
        index = e.control.selected_index

        if index == 0:  # Secrets
            self.selected_type = "secret"
            self.type_filter.value = "secret"
            self.load_secrets()
        elif index == 1:  # Knowledge
            self.selected_type = "knowledge"
            self.type_filter.value = "knowledge"
            self.load_secrets()
        elif index == 2:  # Statistics
            self.show_statistics()
        elif index == 3:  # Settings
            self.show_settings()

    def show_statistics(self):
        """Show vault statistics."""
        stats = self.vault.get_stats()
        layer1 = stats['layer_1']
        layer2 = stats['layer_2']

        self.secrets_list.controls.clear()
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("📊 Vault Statistics", size=24, weight=ft.FontWeight.BOLD),
                        ft.Divider(),
                        ft.Text(f"Total Entries: {layer1['total_entries']}", size=16),
                        ft.Text(f"Services: {', '.join(layer1['services']) if layer1['services'] else 'None'}", size=14),
                        ft.Divider(),
                        ft.Text("Layer 1: Encrypted KV", size=16, weight=ft.FontWeight.BOLD),
                        ft.Text(f"  Entries: {layer1['total_entries']}", size=14),
                        ft.Divider(),
                        ft.Text("Layer 2: DoRA", size=16, weight=ft.FontWeight.BOLD),
                        ft.Text(f"  Status: {'Active' if layer2['initialized'] else 'Not configured'}", size=14),
                    ],
                    spacing=10,
                ),
                padding=20,
            )
        )
        self.page.update()

    def show_settings(self):
        """Show settings."""
        self.secrets_list.controls.clear()
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("⚙️ Settings", size=24, weight=ft.FontWeight.BOLD),
                        ft.Divider(),
                        ft.Text(f"Vault Path: {self.vault_path}", size=14),
                        ft.Text(f"Master Key: {self.key_path}", size=14),
                        ft.Text(f"Database: {self.db_path}", size=14),
                        ft.Divider(),
                        ft.Text("Encryption: ChaCha20-Poly1305", size=14),
                        ft.Text("Key Size: 32 bytes (256-bit)", size=14),
                    ],
                    spacing=10,
                ),
                padding=20,
            )
        )
        self.page.update()


def main(page: ft.Page):
    """Main entry point."""
    VaultApp(page)


if __name__ == "__main__":
    ft.app(target=main)
