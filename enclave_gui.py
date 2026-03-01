#!/usr/bin/env python3
"""
Enclave GUI - A beautiful Flet-based GUI for the Advanced Vault
"""
import os
import sys
from pathlib import Path

import flet as ft

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from advanced_vault.core import HybridVault
from advanced_vault.encrypted_kv import QueryFilter

# Backend URL
BACKEND_URL = "https://keen-curiosity-production-1288.up.railway.app"


class EnclaveGUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "🔐 Enclave"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.window_width = 1200
        self.page.window_height = 800
        
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
        
        # State
        self.secrets = []
        self.selected_tab = 0
        
        # Build UI
        self.build_ui()
        
        # Load initial data
        self.load_secrets()
    
    def build_ui(self):
        """Build the main UI."""
        # Header
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Text("🔐 Enclave", size=24, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Text("zdyras@gmail.com", size=14, color=ft.colors.GREY_400),
                    ft.IconButton(
                        icon=ft.icons.CLOUD_OUTLINED,
                        tooltip="Sync",
                        on_click=self.sync_clicked
                    ),
                    ft.IconButton(
                        icon=ft.icons.ADD,
                        tooltip="Add Secret",
                        on_click=self.show_add_secret_dialog
                    ),
                    ft.IconButton(
                        icon=ft.icons.REFRESH,
                        tooltip="Refresh",
                        on_click=self.refresh_clicked
                    ),
                    ft.IconButton(
                        icon=ft.icons.LOGOUT,
                        tooltip="Logout",
                        on_click=self.logout_clicked
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=20,
            bgcolor=ft.colors.SURFACE_VARIANT,
        )
        
        # Sidebar
        sidebar = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.icons.VPN_KEY, size=40, color=ft.colors.BLUE),
                                ft.Text("Secrets", size=16),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=20,
                        bgcolor=ft.colors.BLUE_900 if self.selected_tab == 0 else ft.colors.TRANSPARENT,
                        border_radius=10,
                        on_click=lambda _: self.switch_tab(0),
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.icons.LIGHTBULB_OUTLINE, size=40),
                                ft.Text("Knowledge", size=16),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=20,
                        border_radius=10,
                        on_click=lambda _: self.switch_tab(1),
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.icons.BAR_CHART, size=40),
                                ft.Text("Statistics", size=16),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=20,
                        border_radius=10,
                        on_click=lambda _: self.switch_tab(2),
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.icons.SETTINGS, size=40),
                                ft.Text("Settings", size=16),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=20,
                        border_radius=10,
                        on_click=lambda _: self.switch_tab(3),
                    ),
                ],
                spacing=10,
            ),
            width=150,
            bgcolor=ft.colors.SURFACE_VARIANT,
            padding=20,
        )
        
        # Main content area
        self.content_area = ft.Container(
            content=self.build_secrets_view(),
            expand=True,
            padding=20,
        )
        
        # Main layout
        main_content = ft.Row(
            [
                sidebar,
                self.content_area,
            ],
            expand=True,
            spacing=0,
        )
        
        # Add to page
        self.page.add(
            ft.Column(
                [
                    header,
                    main_content,
                ],
                expand=True,
                spacing=0,
            )
        )
    
    def build_secrets_view(self):
        """Build the secrets view."""
        # Search bar
        self.search_field = ft.TextField(
            hint_text="Search secrets...",
            prefix_icon=ft.icons.SEARCH,
            border_radius=10,
            filled=True,
            expand=True,
        )
        
        self.filter_dropdown = ft.Dropdown(
            label="Filter",
            options=[
                ft.dropdown.Option("All"),
                ft.dropdown.Option("Secrets"),
                ft.dropdown.Option("Notes"),
            ],
            value="All",
            width=150,
        )
        
        search_bar = ft.Row(
            [
                self.search_field,
                self.filter_dropdown,
            ],
            spacing=10,
        )
        
        # Secrets list
        self.secrets_list = ft.ListView(
            expand=True,
            spacing=10,
            padding=20,
        )
        
        return ft.Column(
            [
                search_bar,
                ft.Container(height=20),
                self.secrets_list,
            ],
            expand=True,
        )
    
    def load_secrets(self):
        """Load secrets from the vault."""
        try:
            self.secrets_list.controls.clear()
            
            entries = self.vault.kv_store.search(QueryFilter())
            self.secrets = entries
            
            if not entries:
                self.secrets_list.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.icons.VPN_KEY_OFF, size=64, color=ft.colors.GREY_400),
                                ft.Text(
                                    "No secrets yet",
                                    size=20,
                                    color=ft.colors.GREY_400,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Text(
                                    "Click + to add your first secret",
                                    size=14,
                                    color=ft.colors.GREY_500,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=40,
                        alignment=ft.alignment.center,
                    )
                )
            else:
                for entry in entries:
                    self.secrets_list.controls.append(
                        self.build_secret_card(entry)
                    )
            
            # Info footer
            self.secrets_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.icons.BAR_CHART, size=16, color=ft.colors.GREY_400),
                            ft.Text(
                                f"{len(entries)} entries | {len(set(e.service for e in entries))} services",
                                size=12,
                                color=ft.colors.GREY_400,
                            ),
                        ],
                        spacing=5,
                    ),
                    padding=10,
                )
            )
            
            self.page.update()
            
        except Exception as e:
            print(f"Error loading secrets: {e}")
            self.show_error(f"Failed to load secrets: {str(e)}")
    
    def build_secret_card(self, entry):
        """Build a card for a secret entry."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.icons.VPN_KEY, size=32, color=ft.colors.BLUE),
                    ft.Column(
                        [
                            ft.Text(entry.service, size=18, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                f"Created: {entry.created_at.strftime('%Y-%m-%d %H:%M')}",
                                size=12,
                                color=ft.colors.GREY_400,
                            ),
                        ],
                        expand=True,
                        spacing=5,
                    ),
                    ft.IconButton(
                        icon=ft.icons.VISIBILITY,
                        tooltip="View",
                        on_click=lambda _, e=entry: self.view_secret(e),
                    ),
                    ft.IconButton(
                        icon=ft.icons.DELETE,
                        tooltip="Delete",
                        icon_color=ft.colors.RED_400,
                        on_click=lambda _, e=entry: self.delete_secret(e),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=15,
            bgcolor=ft.colors.SURFACE_VARIANT,
            border_radius=10,
        )
    
    def show_add_secret_dialog(self, e):
        """Show the add secret dialog."""
        print("Opening add dialog...")
        
        # Create text fields
        service_field = ft.TextField(
            label="Service Name",
            hint_text="e.g., stripe, github, aws",
            autofocus=True,
            filled=True,
        )
        
        secret_field = ft.TextField(
            label="Secret Value",
            hint_text="Enter your secret",
            password=True,
            can_reveal_password=True,
            filled=True,
            multiline=True,
            min_lines=3,
            max_lines=5,
        )
        
        tags_field = ft.TextField(
            label="Tags (optional)",
            hint_text="comma, separated, tags",
            filled=True,
        )
        
        description_field = ft.TextField(
            label="Description (optional)",
            hint_text="Add a note about this secret",
            filled=True,
            multiline=True,
            min_lines=2,
            max_lines=3,
        )
        
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        def save_secret(e):
            service = service_field.value.strip()
            secret = secret_field.value.strip()
            
            if not service:
                self.show_error("Service name is required")
                return
            
            if not secret:
                self.show_error("Secret value is required")
                return
            
            tags = [t.strip() for t in tags_field.value.split(",") if t.strip()] if tags_field.value else []
            description = description_field.value.strip()
            
            try:
                self.vault.store(
                    content=secret,
                    data_type="secret",
                    service=service,
                    tags=tags,
                    description=description if description else None
                )
                
                close_dialog(e)
                self.load_secrets()
                self.show_success(f"Secret '{service}' added successfully!")
                
            except Exception as ex:
                self.show_error(f"Failed to save secret: {str(ex)}")
        
        # Create dialog
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Add New Secret"),
            content=ft.Container(
                content=ft.Column(
                    [
                        service_field,
                        secret_field,
                        tags_field,
                        description_field,
                    ],
                    spacing=15,
                    tight=True,
                ),
                width=500,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.ElevatedButton("Add Secret", on_click=save_secret),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        print(f"Creating AlertDialog...")
        print(f"Dialog created: {dialog}")
        
        # CRITICAL FIX: Set page.dialog BEFORE opening
        self.page.dialog = dialog
        print(f"Setting page.dialog...")
        print(f"page.dialog set to: {dialog}")
        
        # Now open the dialog
        print(f"Opening dialog...")
        dialog.open = True
        print(f"dialog.open = {dialog.open}")
        
        # Update the page
        print(f"Calling page.update()...")
        self.page.update()
        print(f"✓ Dialog should be visible!")
    
    def view_secret(self, entry):
        """View secret details."""
        try:
            secret_value = self.vault.kv_store.get(entry.service)
            
            def close_dialog(e):
                dialog.open = False
                self.page.update()
            
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Secret: {entry.service}"),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.TextField(
                                label="Service",
                                value=entry.service,
                                read_only=True,
                                filled=True,
                            ),
                            ft.TextField(
                                label="Secret Value",
                                value=secret_value,
                                password=True,
                                can_reveal_password=True,
                                read_only=True,
                                filled=True,
                                multiline=True,
                            ),
                            ft.TextField(
                                label="Tags",
                                value=", ".join(entry.tags) if entry.tags else "None",
                                read_only=True,
                                filled=True,
                            ),
                            ft.TextField(
                                label="Description",
                                value=entry.description or "None",
                                read_only=True,
                                filled=True,
                                multiline=True,
                            ),
                            ft.Text(
                                f"Created: {entry.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                                size=12,
                                color=ft.colors.GREY_400,
                            ),
                        ],
                        spacing=15,
                        tight=True,
                    ),
                    width=500,
                ),
                actions=[
                    ft.TextButton("Close", on_click=close_dialog),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()
            
        except Exception as ex:
            self.show_error(f"Failed to load secret: {str(ex)}")
    
    def delete_secret(self, entry):
        """Delete a secret."""
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        def confirm_delete(e):
            try:
                self.vault.kv_store.delete(entry.service)
                close_dialog(e)
                self.load_secrets()
                self.show_success(f"Secret '{entry.service}' deleted")
            except Exception as ex:
                self.show_error(f"Failed to delete secret: {str(ex)}")
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Secret"),
            content=ft.Text(f"Are you sure you want to delete '{entry.service}'? This cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.ElevatedButton(
                    "Delete",
                    on_click=confirm_delete,
                    bgcolor=ft.colors.RED_400,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()
    
    def show_error(self, message: str):
        """Show an error snackbar."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.colors.RED_400,
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def show_success(self, message: str):
        """Show a success snackbar."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.colors.GREEN_400,
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def switch_tab(self, tab_index: int):
        """Switch to a different tab."""
        self.selected_tab = tab_index
        # Rebuild UI for the selected tab
        # For now, just show a placeholder
        self.show_success(f"Switched to tab {tab_index}")
    
    def sync_clicked(self, e):
        """Handle sync button click."""
        self.show_success("Sync feature coming soon!")
    
    def refresh_clicked(self, e):
        """Handle refresh button click."""
        self.load_secrets()
        self.show_success("Secrets refreshed")
    
    def logout_clicked(self, e):
        """Handle logout button click."""
        self.page.window_destroy()


def main(page: ft.Page):
    """Main entry point for the Flet app."""
    print("🔐 Launching Enclave GUI...")
    print(f"Backend: {BACKEND_URL}")
    print()
    EnclaveGUI(page)


if __name__ == "__main__":
    ft.app(target=main)
