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
import logging
import base64
import tempfile
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import time

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from advanced_vault.encrypted_kv import QueryFilter, EntryType
from auth_screen import AuthScreen
from cloud_sync import CloudSyncService
from pdf_processor import PDFProcessor
from qa_generator import QAGenerator
from training_manager import TrainingManager
from theme import ModernTheme
from welcome_screen import WelcomeScreen
from error_helper import make_user_friendly, format_error_snackbar

logger = logging.getLogger(__name__)


class VaultApp:
    """Enclave - Secure Vault GUI Application."""

    def __init__(self, page: ft.Page):
        """Initialize the app."""
        self.page = page
        self.page.title = "🔐 Enclave"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        
        # Set up modern theme
        self.page.theme = ft.Theme(
            color_scheme_seed=ModernTheme.ACCENT_PRIMARY,
            font_family="System",
            text_theme=ft.TextTheme(
                display_large=ft.TextStyle(size=57, weight=ft.FontWeight.BOLD),
                display_medium=ft.TextStyle(size=45, weight=ft.FontWeight.BOLD),
                headline_large=ft.TextStyle(size=32, weight=ft.FontWeight.BOLD),
                title_large=ft.TextStyle(size=22, weight=ft.FontWeight.BOLD),
                body_large=ft.TextStyle(size=16),
                body_medium=ft.TextStyle(size=14),
                label_large=ft.TextStyle(size=14, weight=ft.FontWeight.W_500),
            ),
        )
        
        # Set page background
        self.page.bgcolor = ModernTheme.BG_PRIMARY

        # Backend configuration
        self.backend_url = os.getenv(
            "ENCLAVE_BACKEND_URL",
            "https://keen-curiosity-production-1288.up.railway.app"
        )

        # Authentication state
        self.session_data = None
        self.vault = None
        self.cloud_sync = None
        self.pdf_processor = PDFProcessor()
        self.pdf_file_picker = None  # Will be created when Knowledge view is shown
        self.qa_generator = None
        self.training_manager = None

        # Backend connectivity state (for training service)
        self.backend_status = "unknown"  # unknown, connected, disconnected
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
        self._search_timer = None  # For debouncing search
        self._is_processing = False  # Track if async operation is running

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

        # Sync from cloud on login
        self.sync_from_cloud()

        # Check if first-time user
        if self._is_first_time_user():
            # Show welcome screen
            self.show_welcome_screen()
        else:
            # Build main UI directly
            self.page.clean()
            self.build_ui()
            self.page.update()
    
    def _is_first_time_user(self) -> bool:
        """Check if user is first-time (no vault entries)."""
        try:
            if not self.vault:
                return True
            
            # Check if vault has any entries
            query_filter = QueryFilter()
            result = self.vault.kv_store.search(query_filter)
            
            # Also check if database file is new (no entries)
            if not self.db_path.exists() or self.db_path.stat().st_size == 0:
                return True
            
            # Check if we have any entries after sync
            return len(result) == 0
        except Exception as e:
            logger.warning(f"Error checking first-time user status: {e}")
            return True  # Default to showing welcome screen on error
    
    def show_welcome_screen(self):
        """Show welcome screen for first-time users."""
        welcome = WelcomeScreen(
            page=self.page,
            on_start=self._on_welcome_complete,
            on_add_sample=self._add_sample_data
        )
        
        self.page.clean()
        self.page.add(welcome.get_view())
        self.page.update()
    
    def _on_welcome_complete(self):
        """Called when welcome screen is dismissed."""
        self.page.clean()
        self.build_ui()
        self.page.update()
    
    def _add_sample_data(self):
        """Add sample data for first-time users."""
        try:
            if not self.vault:
                logger.error("Vault not initialized")
                return
            
            sample_secrets = [
                {
                    "service": "GitHub",
                    "content": "ghp_example_token_123456789",
                    "tags": ["development", "version-control"],
                    "description": "GitHub Personal Access Token"
                },
                {
                    "service": "AWS",
                    "content": "AKIAIOSFODNN7EXAMPLE",
                    "tags": ["cloud", "infrastructure"],
                    "description": "AWS Access Key"
                },
                {
                    "service": "Stripe",
                    "content": "sk_test_example_placeholder_key_not_real",
                    "tags": ["payment", "production"],
                    "description": "Stripe API Key (example)"
                },
            ]
            
            added_count = 0
            for secret in sample_secrets:
                try:
                    self.vault.store(
                        content=secret["content"],
                        data_type="secret",
                        service=secret["service"],
                        tags=secret["tags"],
                        description=secret["description"]
                    )
                    added_count += 1
                except Exception as e:
                    logger.warning(f"Failed to add sample secret {secret['service']}: {e}")
            
            logger.info(f"Added {added_count} sample secrets")
            
            # Show success message
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ Added {added_count} sample secrets!"),
                bgcolor=ModernTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
            
        except Exception as e:
            logger.error(f"Error adding sample data: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Error adding sample data: {str(e)}"),
                bgcolor=ModernTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
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
        
        # Initialize cloud sync service
        if self.session_data:
            try:
                self.cloud_sync = CloudSyncService(
                    backend_url=self.backend_url,
                    session_data=self.session_data,
                    vault=self.vault.kv_store
                )
                logger.info("Cloud sync service initialized")
            except Exception as e:
                logger.error(f"Failed to initialize cloud sync: {e}")
                self.cloud_sync = None
            
            # Initialize Q&A generator and training manager
            # Note: QAGenerator still uses RunPod directly for now (inference endpoint)
            # TrainingManager uses backend API (backend manages RunPod credentials)
            try:
                # TODO: QAGenerator should also use backend API
                runpod_endpoint = os.getenv("RUNPOD_ENDPOINT_ID")
                runpod_api_key = os.getenv("RUNPOD_API_KEY")
                self.qa_generator = QAGenerator(
                    runpod_endpoint_id=runpod_endpoint,
                    runpod_api_key=runpod_api_key
                ) if runpod_endpoint and runpod_api_key else None
                
                self.training_manager = TrainingManager(
                    backend_url=self.backend_url,
                    session_data=self.session_data,
                    supabase_url=os.getenv("SUPABASE_URL"),
                    supabase_anon_key=os.getenv("SUPABASE_ANON_KEY")
                )
                logger.info("Q&A generator and training manager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize training services: {e}")
                self.qa_generator = None
                self.training_manager = None

    def sync_from_cloud(self):
        """Sync entries from cloud on login."""
        if not self.cloud_sync:
            return
        
        def _sync():
            try:
                cloud_entries = self.cloud_sync.fetch_from_cloud()
                if cloud_entries:
                    # Merge with local entries (cloud wins on conflicts)
                    result = self.cloud_sync.merge_entries(cloud_entries, conflict_resolution="cloud")
                    logger.info(f"Synced {result.get('merged', 0)} entries from cloud")
            except Exception as e:
                logger.error(f"Error syncing from cloud: {e}")
        
        # Run in background thread
        thread = threading.Thread(target=_sync, daemon=True)
        thread.start()

    def logout(self):
        """Logout user."""
        # Clear session
        AuthScreen.clear_session()
        self.session_data = None
        self.vault = None

        # Show auth screen
        self.show_auth_screen()

    def check_backend_connectivity(self):
        """Check backend API connectivity."""
        # Run in background thread
        def _check():
            try:
                response = requests.get(
                    f"{self.backend_url}/health",
                    timeout=5.0
                )
                if response.status_code == 200:
                    self.backend_status = "connected"
                else:
                    self.backend_status = "error"
            except Exception as e:
                self.backend_status = "disconnected"

            self.last_check = datetime.now()

            # Update UI
            if hasattr(self, 'connectivity_icon'):
                self.update_connectivity_icon()
                self.page.update()

        thread = threading.Thread(target=_check, daemon=True)
        thread.start()

    def update_connectivity_icon(self):
        """Update the connectivity icon based on backend status."""
        if not hasattr(self, 'connectivity_icon'):
            return
        
        if self.backend_status == "connected":
            self.connectivity_icon.icon = ft.Icons.CLOUD_DONE_ROUNDED
            self.connectivity_icon.icon_color = ModernTheme.ACCENT_SUCCESS
            self.connectivity_icon.tooltip = "Backend: Connected ✓"
        elif self.backend_status == "disconnected":
            self.connectivity_icon.icon = ft.Icons.CLOUD_OFF_ROUNDED
            self.connectivity_icon.icon_color = ModernTheme.ACCENT_ERROR
            self.connectivity_icon.tooltip = "Backend: Disconnected"
        else:
            self.connectivity_icon.icon = ft.Icons.CLOUD_SYNC_ROUNDED
            self.connectivity_icon.icon_color = ModernTheme.ACCENT_WARNING
            self.connectivity_icon.tooltip = "Backend: Checking..."

    def build_ui(self):
        """Build the main UI."""
        # Create connectivity indicator
        self.connectivity_icon = ft.IconButton(
            icon=ft.Icons.CLOUD_SYNC_ROUNDED,
            icon_color=ModernTheme.TEXT_MUTED,
            tooltip="Backend: Checking...",
            on_click=lambda _: self.check_backend_connectivity(),
            icon_size=24
        )

        # User info for app bar
        user_email = self.session_data.get("user", {}).get("email", "User") if self.session_data else "User"

        # Modern app bar with glassmorphism effect
        self.page.appbar = ft.AppBar(
            title=ft.Row([
                ft.Container(
                    content=ft.Text("🔐", size=24),
                    margin=ft.margin.only(right=8),
                ),
                ft.Text(
                    "Enclave",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=ModernTheme.TEXT_PRIMARY,
                ),
            ]),
            center_title=False,
            bgcolor=ModernTheme.GLASS_BG,
            elevation=0,
            actions=[
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.PERSON_ROUNDED, size=16, color=ModernTheme.TEXT_SECONDARY),
                        ft.Text(user_email, size=12, color=ModernTheme.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                    ], spacing=5),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor=ModernTheme.BG_ELEVATED,
                ),
                ft.Container(width=8),
                ft.VerticalDivider(width=1, color=ModernTheme.BORDER_COLOR),
                ft.Container(width=8),
                self.connectivity_icon,
                ft.Container(width=8),
                ft.VerticalDivider(width=1, color=ModernTheme.BORDER_COLOR),
                ft.Container(width=8),
                ft.IconButton(
                    ft.Icons.ADD_CIRCLE_ROUNDED,
                    tooltip="Add Secret",
                    on_click=self.show_add_dialog,
                    icon_size=28,
                    icon_color=ModernTheme.ACCENT_PRIMARY,
                ),
                ft.IconButton(
                    ft.Icons.REFRESH_ROUNDED,
                    tooltip="Refresh",
                    on_click=lambda _: self.load_secrets(),
                    icon_size=28,
                    icon_color=ModernTheme.TEXT_SECONDARY,
                ),
                ft.IconButton(
                    ft.Icons.LOGOUT_ROUNDED,
                    tooltip="Logout",
                    on_click=lambda _: self.logout(),
                    icon_size=28,
                    icon_color=ModernTheme.ACCENT_ERROR,
                ),
            ],
        )

        # Start initial connectivity check
        self.check_backend_connectivity()

        # Modern search bar
        self.search_field = ft.TextField(
            hint_text="Search secrets...",
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_radius=12,
            filled=True,
            bgcolor=ModernTheme.BG_ELEVATED,
            border_color=ModernTheme.BORDER_COLOR,
            focused_border_color=ModernTheme.ACCENT_PRIMARY,
            color=ModernTheme.TEXT_PRIMARY,
            text_size=14,
            on_change=self.on_search_change,
            expand=True,
            height=48,
        )

        # Modern filter dropdown
        self.type_filter = ft.Dropdown(
            width=150,
            value="all",
            options=[
                ft.dropdown.Option("all", "All"),
                ft.dropdown.Option("secret", "Secrets"),
                ft.dropdown.Option("knowledge", "Knowledge"),
            ],
            on_change=self.on_filter_change,
            border_radius=12,
            bgcolor=ModernTheme.BG_ELEVATED,
            color=ModernTheme.TEXT_PRIMARY,
            focused_border_color=ModernTheme.ACCENT_PRIMARY,
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
        self.stats_text = ft.Text("", size=12, color=ModernTheme.TEXT_MUTED, weight=ft.FontWeight.W_500)

        # Modern navigation rail
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=80,
            min_extended_width=200,
            bgcolor=ModernTheme.BG_SECONDARY,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.KEY_OUTLINED,
                    selected_icon=ft.Icons.KEY_ROUNDED,
                    label="Secrets",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.LIGHTBULB_OUTLINED,
                    selected_icon=ft.Icons.LIGHTBULB_ROUNDED,
                    label="Knowledge",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.TRAIN_OUTLINED,
                    selected_icon=ft.Icons.TRAIN_ROUNDED,
                    label="Training",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.BAR_CHART_OUTLINED,
                    selected_icon=ft.Icons.BAR_CHART_ROUNDED,
                    label="Statistics",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_ROUNDED,
                    label="Settings",
                ),
            ],
            on_change=self.on_nav_change,
        )

        # Main content with modern styling
        main_content = ft.Container(
            content=ft.Column(
                [
                    search_row,
                    ft.Container(height=8),
                    ft.Divider(height=1, color=ModernTheme.BORDER_COLOR),
                    ft.Container(height=8),
                    self.secrets_list,
                    ft.Container(height=8),
                    ft.Divider(height=1, color=ModernTheme.BORDER_COLOR),
                    ft.Container(height=8),
                    self.stats_text,
                ],
                spacing=0,
                expand=True,
            ),
            padding=ft.padding.all(24),
            expand=True,
            bgcolor=ModernTheme.BG_PRIMARY,
        )

        # Layout with modern divider
        self.page.add(
            ft.Row(
                [
                    self.nav_rail,
                    ft.VerticalDivider(width=1, color=ModernTheme.BORDER_COLOR),
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
        # Store header if we're in knowledge view
        header_container = None
        if self.selected_type == "knowledge" and len(self.secrets_list.controls) > 0:
            # Check if first item is the knowledge header
            first_item = self.secrets_list.controls[0]
            if isinstance(first_item, ft.Container) and isinstance(first_item.content, ft.Column):
                col_content = first_item.content.controls
                if col_content and isinstance(col_content[0], ft.Row):
                    row_content = col_content[0].controls
                    if row_content and isinstance(row_content[0], ft.Text) and "Knowledge Base" in str(row_content[0].value):
                        header_container = first_item
        
        self.secrets_list.controls.clear()
        
        # Restore header if we're in knowledge view
        if header_container:
            self.secrets_list.controls.append(header_container)

        # Get all entries
        from advanced_vault.encrypted_kv import QueryFilter, EntryType

        # Create filter based on selected type
        query_filter = QueryFilter()
        if self.selected_type == "secret":
            query_filter.entry_type = EntryType.SECRET
        # Note: "knowledge" entries are not yet stored in KV (Layer 2 not implemented)
        elif self.selected_type == "knowledge":
            # For knowledge, we still search all entries but filter by data_type in tags or description
            pass

        result = self.vault.kv_store.search(query_filter)

        # Convert EncryptedEntry objects to dicts
        entries = []
        for entry in result:
            # Filter knowledge entries if in knowledge view
            if self.selected_type == "knowledge":
                # Check if entry has knowledge tag or is marked as knowledge
                # Knowledge entries are typically tagged with "pdf", "document", or "knowledge"
                if "knowledge" in entry.tags or "pdf" in entry.tags or "document" in entry.tags:
                    entries.append({
                        'id': entry.id,
                        'service': entry.service,
                        'data_type': 'knowledge',
                        'tags': entry.tags,
                        'timestamp': entry.updated_at.timestamp() if entry.updated_at else 0,
                        'description': entry.description
                    })
            else:
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
            # Only show empty message if not in knowledge view (knowledge view has its own header)
            if self.selected_type != "knowledge":
                # Modern empty state
                self.secrets_list.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.LOCK_OPEN_ROUNDED,
                                        size=80,
                                        color=ModernTheme.ACCENT_PRIMARY,
                                    ),
                                    padding=20,
                                    border_radius=20,
                                    bgcolor=ModernTheme.BG_ELEVATED,
                                ),
                                ft.Container(height=24),
                                ft.Text(
                                    "Your vault is empty",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=ModernTheme.TEXT_PRIMARY,
                                ),
                                ft.Container(height=8),
                                ft.Text(
                                    "Add your first secret to get started",
                                    size=14,
                                    color=ModernTheme.TEXT_MUTED,
                                ),
                                ft.Container(height=24),
                                ft.Container(
                                    content=ft.ElevatedButton(
                                        "Add Secret",
                                        icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                                        style=ft.ButtonStyle(
                                            bgcolor=ModernTheme.ACCENT_PRIMARY,
                                            color="white",
                                            shape=ft.RoundedRectangleBorder(radius=12),
                                            padding=ft.padding.symmetric(horizontal=24, vertical=12),
                                        ),
                                        on_click=self.show_add_dialog,
                                    ),
                                    gradient=ModernTheme.get_gradient(ModernTheme.GRADIENT_PRIMARY),
                                    border_radius=12,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        alignment=ft.alignment.center,
                        expand=True,
                        padding=40,
                    )
                )

        # Update stats
        stats = self.vault.get_stats()
        layer1 = stats['layer_1']
        self.stats_text.value = f"📊 {layer1['total_entries']} entries | {len(layer1['services'])} services"

        self.page.update()

    def create_secret_card(self, entry):
        """Create a modern card with elevation and hover effects."""
        service = entry.get('service', 'Unknown')
        data_type = entry.get('data_type', 'secret')
        tags = entry.get('tags', [])

        # Modern icon with gradient background
        icon_colors = ModernTheme.GRADIENT_PRIMARY if data_type == 'secret' else ModernTheme.GRADIENT_SECONDARY
        icon_bg = ft.Container(
            content=ft.Icon(
                ft.Icons.KEY_ROUNDED if data_type == 'secret' else ft.Icons.LIGHTBULB_ROUNDED,
                color=ModernTheme.TEXT_PRIMARY,
                size=24
            ),
            width=48,
            height=48,
            border_radius=12,
            gradient=ModernTheme.get_gradient(icon_colors),
            alignment=ft.alignment.center,
        )

        # Extract training status from tags
        training_status = None
        training_job_id = None
        for tag in tags:
            if tag.startswith("training_status:"):
                training_status = tag.split(":", 1)[1]
            elif tag.startswith("training_job:"):
                training_job_id = tag.split(":", 1)[1]
        
        # Training status badge
        status_badge = None
        if training_status:
            status_colors = {
                "pending": ModernTheme.ACCENT_WARNING,
                "training": ModernTheme.ACCENT_PRIMARY,
                "completed": ModernTheme.ACCENT_SUCCESS,
                "failed": ModernTheme.ACCENT_ERROR
            }
            status_icons = {
                "pending": ft.Icons.HOURGLASS_EMPTY_ROUNDED,
                "training": ft.Icons.TRAIN_ROUNDED,
                "completed": ft.Icons.CHECK_CIRCLE_ROUNDED,
                "failed": ft.Icons.ERROR_ROUNDED
            }
            status_color = status_colors.get(training_status, ModernTheme.TEXT_MUTED)
            status_icon = status_icons.get(training_status, ft.Icons.INFO_ROUNDED)
            
            status_badge = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(status_icon, size=12, color=status_color),
                        ft.Text(
                            training_status.title(),
                            size=10,
                            weight=ft.FontWeight.W_500,
                            color=status_color
                        )
                    ],
                    spacing=4,
                    tight=True
                ),
                bgcolor=status_color + "20",  # 20% opacity
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=8,
                border=ft.border.all(1, status_color + "40"),
            )

        # Modern tag chips (exclude training status tags)
        regular_tags = [t for t in tags if not t.startswith("training_")]
        tag_chips = [
            ft.Container(
                content=ft.Text(tag, size=10, weight=ft.FontWeight.W_500, color=ModernTheme.TEXT_SECONDARY),
                bgcolor=ModernTheme.BG_HOVER,
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=8,
                border=ft.border.all(1, ModernTheme.BORDER_COLOR),
            )
            for tag in regular_tags[:3]  # Show max 3 tags
        ]
        
        # Add status badge to tag row if present
        tag_row_items = tag_chips.copy()
        if status_badge:
            tag_row_items.insert(0, status_badge)

        # Build action buttons with modern styling
        action_buttons = [
            ft.IconButton(
                ft.Icons.VISIBILITY_ROUNDED,
                tooltip="View",
                on_click=lambda _, e=entry: self.view_secret(e),
                icon_color=ModernTheme.TEXT_SECONDARY,
            ),
        ]
        
        # Add "Train Model" button for PDF/knowledge entries
        if "pdf" in tags or "knowledge" in tags or "document" in tags:
            action_buttons.append(
                ft.IconButton(
                    ft.Icons.TRAIN_ROUNDED,
                    tooltip="Train Model",
                    on_click=lambda _, e=entry: self._offer_training_from_entry(e),
                    icon_color=ModernTheme.ACCENT_WARNING,
                )
            )
        
        action_buttons.append(
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE_ROUNDED,
                tooltip="Delete",
                on_click=lambda _, e=entry: self.delete_secret(e),
                icon_color=ModernTheme.ACCENT_ERROR,
            )
        )

        # Modern card with elevation
        return ft.Container(
            content=ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        [
                            icon_bg,
                            ft.Container(width=16),  # Spacing
                            ft.Column(
                                [
                                    ft.Text(
                                        service,
                                        weight=ft.FontWeight.BOLD,
                                        size=16,
                                        color=ModernTheme.TEXT_PRIMARY
                                    ),
                                    ft.Container(height=6),
                                    ft.Row(tag_row_items, spacing=6) if tag_row_items else ft.Container(),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                            ft.Row(
                                action_buttons,
                                spacing=4,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=20,
                ),
                elevation=4,
                color=ModernTheme.BG_ELEVATED,
            ),
            margin=ft.margin.only(bottom=12),
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
        )

    def show_add_dialog(self, e):
        """Show add secret dialog."""
        try:
            logger.debug("Opening add dialog")

            # Close any existing dialogs in overlay
            for overlay_item in list(self.page.overlay):
                if isinstance(overlay_item, ft.AlertDialog) and overlay_item.open:
                    overlay_item.open = False

            service_field = ft.TextField(
                label="Service (e.g., stripe, github)",
                border_radius=8,
                bgcolor=ModernTheme.BG_ELEVATED,
                border_color=ModernTheme.BORDER_COLOR,
                focused_border_color=ModernTheme.ACCENT_PRIMARY,
            )
            content_field = ft.TextField(
                label="Secret / Knowledge",
                password=True,
                multiline=True,
                border_radius=8,
                bgcolor=ModernTheme.BG_ELEVATED,
                border_color=ModernTheme.BORDER_COLOR,
                focused_border_color=ModernTheme.ACCENT_PRIMARY,
            )
            tags_field = ft.TextField(
                label="Tags (comma-separated)",
                hint_text="payment, production",
                border_radius=8,
                bgcolor=ModernTheme.BG_ELEVATED,
                border_color=ModernTheme.BORDER_COLOR,
                focused_border_color=ModernTheme.ACCENT_PRIMARY,
            )
            description_field = ft.TextField(
                label="Description (optional)",
                multiline=True,
                border_radius=8,
                bgcolor=ModernTheme.BG_ELEVATED,
                border_color=ModernTheme.BORDER_COLOR,
                focused_border_color=ModernTheme.ACCENT_PRIMARY,
            )

            type_radio = ft.RadioGroup(
                content=ft.Row([
                    ft.Radio(value="secret", label="Secret"),
                    ft.Radio(value="knowledge", label="Knowledge"),
                ]),
                value="secret"
            )

            def close_dialog():
                if dialog:
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
                entry_id = self.vault.store(
                    content=content_field.value,
                    data_type=type_radio.value,
                    service=service_field.value,
                    tags=tags,
                    description=description_field.value or None
                )

                # Sync to cloud in background (non-critical)
                if self.cloud_sync:
                    try:
                        self.cloud_sync.sync_entry_background(entry_id)
                    except Exception as sync_err:
                        logger.warning(f"Cloud sync failed (non-critical): {sync_err}")
                        # Don't fail the operation - local storage succeeded

                # Show success snackbar
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"✅ Added {service_field.value}"),
                    bgcolor=ModernTheme.ACCENT_SUCCESS,
                )
                self.page.snack_bar.open = True

                close_dialog()
                self.load_secrets()

            logger.debug("Creating AlertDialog")
            # Create dialog content column with all fields - remove scroll, add width
            dialog_content = ft.Column(
                [
                    type_radio,
                    service_field,
                    content_field,
                    tags_field,
                    description_field,
                ],
                spacing=15,
                tight=True,
                width=500,
            )
            
            # Modern dialog styling
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "Add Entry",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ModernTheme.TEXT_PRIMARY,
                ),
                bgcolor=ModernTheme.BG_ELEVATED,
                content=dialog_content,
                actions=[
                    ft.TextButton(
                        "Cancel",
                        on_click=lambda _: close_dialog(),
                        style=ft.ButtonStyle(color=ModernTheme.TEXT_SECONDARY),
                    ),
                    ft.Container(
                        content=ft.ElevatedButton(
                            "Add",
                            icon=ft.Icons.ADD_ROUNDED,
                            style=ft.ButtonStyle(
                                bgcolor=ModernTheme.ACCENT_PRIMARY,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            on_click=add_entry
                        ),
                        gradient=ModernTheme.get_gradient(ModernTheme.GRADIENT_PRIMARY),
                        border_radius=8,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            
            # Add dialog to overlay (the correct way in Flet)
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()

        except Exception as ex:
            logger.error(f"Error opening add dialog: {ex}", exc_info=True)
            user_msg, _ = make_user_friendly(str(ex), context="upload")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=ModernTheme.ACCENT_ERROR,
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
            user_msg, _ = make_user_friendly(result['error'], context="vault")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=ModernTheme.ACCENT_ERROR,
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
            bgcolor=ModernTheme.BG_ELEVATED,
            border_color=ModernTheme.BORDER_COLOR,
            color=ModernTheme.TEXT_PRIMARY,
            border_radius=8,
        )

        def copy_to_clipboard(e):
            self.page.set_clipboard(content)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("📋 Copied to clipboard"),
                bgcolor=ModernTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()

        def close_dialog():
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text(
                f"🔐 {service}",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=ModernTheme.TEXT_PRIMARY,
            ),
            bgcolor=ModernTheme.BG_ELEVATED,
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"Type: {data_type.title()}", size=12, color=ModernTheme.TEXT_MUTED),
                        ft.Text(f"Tags: {tags or 'None'}", size=12, color=ModernTheme.TEXT_MUTED),
                        ft.Text(f"Description: {description}", size=12, color=ModernTheme.TEXT_MUTED),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        content_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=500,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: close_dialog(),
                    style=ft.ButtonStyle(color=ModernTheme.TEXT_SECONDARY),
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Copy",
                        icon=ft.Icons.COPY_ROUNDED,
                        style=ft.ButtonStyle(
                            bgcolor=ModernTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                        on_click=copy_to_clipboard
                    ),
                    gradient=ModernTheme.get_gradient(ModernTheme.GRADIENT_PRIMARY),
                    border_radius=8,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def delete_secret(self, entry):
        """Delete a secret."""
        service = entry.get('service', 'Unknown')

        def confirm_delete(e):
            self.vault.kv_store.delete(service)

            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"🗑️ Deleted {service}"),
                bgcolor=ModernTheme.ACCENT_ERROR,
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

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def on_search_change(self, e):
        """Handle search query change with debouncing."""
        self.search_query = e.control.value
        
        # Cancel existing timer
        if self._search_timer:
            self._search_timer.cancel()
        
        # Debounce search: wait 300ms before executing
        import threading
        self._search_timer = threading.Timer(0.3, self.load_secrets)
        self._search_timer.start()

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
            self.show_knowledge_view()
        elif index == 2:  # Training
            self.show_training_view()
        elif index == 3:  # Statistics
            self.show_statistics()
        elif index == 4:  # Settings
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
                        ft.Text(
                            "📊 Vault Statistics",
                            size=24,
                            weight=ft.FontWeight.BOLD,
                            color=ModernTheme.TEXT_PRIMARY,
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        ft.Text(
                            f"Total Entries: {layer1['total_entries']}",
                            size=16,
                            color=ModernTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            f"Services: {', '.join(layer1['services']) if layer1['services'] else 'None'}",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        ft.Text(
                            "Layer 1: Encrypted KV",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=ModernTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            f"  Entries: {layer1['total_entries']}",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        ft.Text(
                            "Layer 2: DoRA",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=ModernTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            f"  Status: {'Active' if layer2['initialized'] else 'Not configured'}",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                    ],
                    spacing=12,
                ),
                padding=24,
            )
        )
        self.page.update()

    def show_knowledge_view(self):
        """Show knowledge view with PDF upload."""
        self.selected_type = "knowledge"
        self.type_filter.value = "knowledge"
        
        # Create file picker if not already exists
        if not hasattr(self, 'pdf_file_picker') or self.pdf_file_picker is None:
            self.pdf_file_picker = ft.FilePicker(
                on_result=self.on_pdf_selected
            )
            self.page.overlay.append(self.pdf_file_picker)
        
        # Upload button with modern styling
        upload_button = ft.Container(
            content=ft.ElevatedButton(
                "📄 Upload PDF",
                icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                on_click=self._on_upload_click,
                style=ft.ButtonStyle(
                    bgcolor=ModernTheme.ACCENT_PRIMARY,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=12),
                    padding=ft.padding.symmetric(horizontal=24, vertical=12),
                ),
            ),
            gradient=ModernTheme.get_gradient(ModernTheme.GRADIENT_PRIMARY),
            border_radius=12,
        )
        
        # Clear and rebuild knowledge view
        self.secrets_list.controls.clear()
        
        # Knowledge view header with upload button
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "📚 Knowledge Base",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=ModernTheme.TEXT_PRIMARY,
                                ),
                                upload_button,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        ft.Text(
                            "Upload PDF documents to extract knowledge and generate training data.",
                            size=14,
                            color=ModernTheme.TEXT_MUTED
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                    ],
                    spacing=10,
                ),
                padding=20,
            )
        )
        
        # Load existing knowledge entries (these will be added after the header)
        self.load_secrets()
        self.page.update()

    def _on_upload_click(self, e):
        """Handle upload button click."""
        logger.info("Upload PDF button clicked")
        try:
            if not hasattr(self, 'pdf_file_picker') or self.pdf_file_picker is None:
                logger.error("PDF file picker not initialized")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("❌ File picker not initialized. Please restart the app."),
                    bgcolor=ModernTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            logger.debug("Opening file picker...")
            
            # Try to open file picker - on macOS this might need special handling
            try:
                # Workaround for Flet 0.28.3 macOS FilePicker bug
                # Try native macOS dialog if Flet FilePicker fails
                import subprocess
                import json
                
                # Use macOS native file picker as fallback
                logger.debug("Attempting macOS native file picker...")
                result = subprocess.run(
                    [
                        'osascript', '-e',
                        '''
                        set theFile to choose file of type {"PDF"} with prompt "Select PDF File"
                        set theFilePosix to POSIX path of theFile
                        return theFilePosix
                        '''
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    file_path = result.stdout.strip()
                    logger.debug(f"macOS file picker returned: {file_path}")
                    
                    # Create a fake FilePickerResultEvent
                    class FakeFile:
                        def __init__(self, path):
                            self.path = path
                            self.name = Path(path).name
                    
                    class FakeEvent:
                        def __init__(self, file_path):
                            self.files = [FakeFile(file_path)]
                    
                    # Call the handler with fake event
                    fake_event = FakeEvent(file_path)
                    self.on_pdf_selected(fake_event)
                    return
                else:
                    logger.debug(f"macOS file picker cancelled or error: {result.stderr}")
                    
            except FileNotFoundError:
                logger.debug("osascript not found, trying Flet FilePicker")
                # Fall back to Flet FilePicker
                self.pdf_file_picker.pick_files(
                    allowed_extensions=["pdf"],
                    dialog_title="Select PDF File"
                )
            except subprocess.TimeoutExpired:
                logger.debug("File picker timeout")
            except Exception as picker_error:
                logger.debug(f"pick_files() error: {picker_error}")
                # Try Flet FilePicker as fallback
                try:
                    self.pdf_file_picker.pick_files(
                        allowed_extensions=["pdf"],
                        dialog_title="Select PDF File"
                    )
                except Exception as fallback_error:
                    logger.debug(f"Fallback also failed: {fallback_error}")
                    raise
                
            logger.debug("pick_files() called successfully")
            logger.info("File picker opened")
            
            # Force page update
            self.page.update()
        except Exception as ex:
            logger.error(f"Error opening file picker: {ex}", exc_info=True)
            user_msg, _ = make_user_friendly(str(ex), context="upload")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=ModernTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def on_pdf_selected(self, e: ft.FilePickerResultEvent):
        """Handle PDF file selection."""
        logger.info(f"File picker result: {e}")
        logger.info(f"Files: {e.files if e.files else 'None'}")
        if not e.files or len(e.files) == 0:
            logger.info("No file selected")
            return
        
        file_path = e.files[0].path
        filename = e.files[0].name
        logger.info(f"Selected file: {filename} at {file_path}")
        
        # Show processing indicator
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"📄 Processing {filename}..."),
            bgcolor=ModernTheme.ACCENT_PRIMARY,
        )
        self.page.snack_bar.open = True
        self.page.update()
        
        # Process PDF in background thread
        def process_pdf():
            try:
                # Process PDF
                result = self.pdf_processor.process_pdf(file_path)
                
                # Store PDF binary encrypted
                with open(file_path, 'rb') as f:
                    pdf_data = f.read()
                
                # Store as knowledge entry in Layer 1 (for now, until Layer 2 is fully implemented)
                # Use service name as filename, tag it as knowledge/pdf
                entry_id = self.vault.kv_store.put(
                    service=filename,
                    secret_value=base64.b64encode(pdf_data).decode('utf-8'),
                    entry_type=EntryType.OTHER,  # Use OTHER type for knowledge entries
                    tags=["pdf", "document", "knowledge"],
                    description=f"PDF: {result['metadata']['page_count']} pages, {len(result['text_chunks'])} chunks"
                )
                
                logger.info(f"Stored PDF as knowledge entry: {filename} (ID: {entry_id})")
                
                # Sync to cloud (non-critical - don't fail if auth expires)
                if self.cloud_sync:
                    try:
                        self.cloud_sync.sync_entry_background(entry_id)
                    except Exception as sync_err:
                        logger.warning(f"Cloud sync failed (non-critical): {sync_err}")
                        # Don't show error to user - local storage succeeded
                
                # Update UI from main thread (thread-safe)
                def update_ui():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"✅ Processed {filename}: {len(result['text_chunks'])} chunks"),
                        bgcolor=ModernTheme.ACCENT_SUCCESS,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                    self.load_secrets()
                    
                    # Offer to generate Q&A and train model
                    if self.qa_generator and self.training_manager and len(result['text_chunks']) > 0:
                        self._offer_training(filename, result['text_chunks'])
                
                # Schedule UI update on main thread
                # Note: Flet's page.update() is thread-safe when called from background threads
                # But we wrap it in a function to ensure proper execution
                try:
                    # Try run_task if available (some Flet versions)
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_ui)
                    else:
                        # Fallback: direct update (Flet handles thread safety)
                        update_ui()
                except Exception as ui_err:
                    logger.warning(f"UI update error: {ui_err}, trying direct update")
                    update_ui()
                
            except Exception as ex:
                logger.error(f"Error processing PDF: {ex}")
                user_msg, _ = make_user_friendly(str(ex), context="upload")
                
                # Thread-safe error update
                def show_error():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ {user_msg}"),
                        bgcolor=ModernTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(show_error)
                    else:
                        show_error()
                except Exception as ui_err:
                    logger.warning(f"UI update error: {ui_err}, trying direct update")
                    show_error()
        
        thread = threading.Thread(target=process_pdf, daemon=True)
        thread.start()

    def _offer_training(self, filename: str, text_chunks: List[str]):
        """Offer to generate Q&A and train model after PDF processing."""
        # Check if training manager is initialized
        if not self.training_manager:
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Training Service Not Available"),
                content=ft.Text(
                    f"Training service failed to initialize.\n\n"
                    f"Please check:\n"
                    f"• Backend API availability\n"
                    f"• Network connection\n"
                    f"• Your account status"
                ),
                actions=[
                    ft.TextButton("OK", on_click=lambda e: setattr(dialog, 'open', False) or self.page.update()),
                ],
            )
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
            return
        
        # Q&A generator is optional (can train without it)
        if not self.qa_generator:
            logger.warning("Q&A generator not available - training will proceed without Q&A pairs")
        
        def on_yes(e):
            dialog.open = False
            self.page.update()
            self._start_training_workflow(filename, text_chunks)
        
        def on_no(e):
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Generate Training Model?",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=ModernTheme.TEXT_PRIMARY,
            ),
            bgcolor=ModernTheme.BG_ELEVATED,
            content=ft.Text(
                f"Would you like to generate Q&A pairs from this PDF and train a personalized model?\n\n"
                f"This will:\n"
                f"• Generate Q&A pairs from {len(text_chunks)} chunks\n"
                f"• Train a DoRA adapter on your data\n"
                f"• Store encrypted adapter in your vault\n\n"
                f"Note: This may take several minutes.",
                color=ModernTheme.TEXT_SECONDARY,
            ),
            actions=[
                ft.TextButton(
                    "No",
                    on_click=on_no,
                    style=ft.ButtonStyle(color=ModernTheme.TEXT_SECONDARY),
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Yes, Generate Model",
                        icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                        style=ft.ButtonStyle(
                            bgcolor=ModernTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                        on_click=on_yes
                    ),
                    gradient=ModernTheme.get_gradient(ModernTheme.GRADIENT_PRIMARY),
                    border_radius=8,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # Close any existing dialogs
        for overlay_item in list(self.page.overlay):
            if isinstance(overlay_item, ft.AlertDialog) and overlay_item.open:
                overlay_item.open = False
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _offer_training_from_entry(self, entry):
        """Offer training from an existing PDF entry."""
        service = entry.get('service', 'Unknown')
        tags = entry.get('tags', [])
        
        # Extract PDF data from entry
        tmp_path = None
        try:
            secret_value = self.vault.kv_store.get(service)
            if not secret_value:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Could not retrieve PDF data"),
                    bgcolor=ModernTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            # Decode base64 PDF data
            pdf_data = base64.b64decode(secret_value)
            
            # Write to temporary file for processing
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(pdf_data)
            
            # Process PDF to get text chunks
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📄 Processing {service}..."),
                bgcolor=ModernTheme.ACCENT_PRIMARY,
            )
            self.page.snack_bar.open = True
            self.page.update()
            
            result = self.pdf_processor.process_pdf(tmp_path)
            
            # Offer training with the extracted chunks
            self._offer_training(service, result['text_chunks'])
            
        except Exception as ex:
            logger.error(f"Error extracting PDF for training: {ex}")
            user_msg, _ = make_user_friendly(str(ex), context="training")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=ModernTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
        finally:
            # Always cleanup temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_err}")

    def _start_training_workflow(self, filename: str, text_chunks: List[str]):
        """Start Q&A generation and training workflow."""
        def workflow():
            try:
                # Step 1: Generate Q&A pairs
                def update_step1():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text("📝 Generating Q&A pairs..."),
                        bgcolor=ModernTheme.ACCENT_PRIMARY,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_step1)
                    else:
                        update_step1()
                except Exception:
                    update_step1()
                
                qa_pairs = self.qa_generator.generate_from_chunks(
                    text_chunks=text_chunks,
                    user_id=self.session_data.get("user_id"),
                    num_pairs_per_chunk=3
                )
                
                if not qa_pairs:
                    user_msg, _ = make_user_friendly("Failed to generate Q&A pairs from document", context="training")
                    def show_error():
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"❌ {user_msg}"),
                            bgcolor=ModernTheme.ACCENT_ERROR,
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                    try:
                        if hasattr(self.page, 'run_task'):
                            self.page.run_task(show_error)
                        else:
                            show_error()
                    except Exception:
                        show_error()
                    return
                
                # Step 2: Generate encryption key BEFORE saving
                import os
                encryption_key = os.urandom(32)
                encryption_key_hex = encryption_key.hex()
                
                # Step 3: Save dataset ENCRYPTED (never persist plaintext)
                # Encrypts immediately after generation - never saves plaintext
                dataset_filename = f"{filename.replace('.pdf', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                dataset_path = self.training_manager.save_dataset(
                    qa_pairs=qa_pairs,
                    filename=dataset_filename,
                    encryption_key=encryption_key  # Encrypt before saving
                )
                
                logger.info(f"Dataset encrypted and saved: {dataset_path}")
                
                # Step 4: Submit training job
                def update_step4():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text("🚀 Submitting training job..."),
                        bgcolor=ModernTheme.ACCENT_PRIMARY,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_step4)
                    else:
                        update_step4()
                except Exception:
                    update_step4()
                
                result = self.training_manager.submit_training_job(
                    dataset_path=dataset_path,
                    encryption_key_hex=encryption_key_hex,
                    model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                    epochs=3,
                    batch_size=4
                )
                
                # Store training job metadata in vault entry
                # Find the entry by filename and update with job_id
                try:
                    # Search for the entry using QueryFilter
                    from advanced_vault.encrypted_kv import QueryFilter
                    filter = QueryFilter(service=filename, limit=1)
                    entries = self.vault.kv_store.search(filter)
                    if entries:
                        entry = entries[0]
                        # Get decrypted value to re-encrypt with new tags
                        decrypted_value = self.vault.kv_store.get_by_id(entry.id)
                        if decrypted_value:
                            # Update tags to include training job info
                            tags = list(entry.tags) if entry.tags else []
                            # Remove old training tags
                            tags = [t for t in tags if not t.startswith("training_")]
                            # Add new training tags
                            tags.append(f"training_job:{result['adapter_id']}")
                            tags.append(f"training_status:pending")
                            # Update entry with new tags
                            self.vault.kv_store.put(
                                service=entry.service,
                                secret_value=decrypted_value,
                                entry_type=entry.entry_type,
                                tags=tags,
                                description=entry.description,
                                entry_id=entry.id
                            )
                except Exception as update_err:
                    logger.warning(f"Failed to update entry with training metadata: {update_err}")
                
                # Update UI (thread-safe)
                def update_success():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"✅ Training job submitted! Adapter ID: {result['adapter_id'][:8]}..."),
                        bgcolor=ModernTheme.ACCENT_SUCCESS,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                    self.load_secrets()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_success)
                    else:
                        update_success()
                except Exception:
                    update_success()
                
                logger.info(f"Training workflow completed for {filename}")
                
            except Exception as ex:
                logger.error(f"Error in training workflow: {ex}")
                user_msg, _ = make_user_friendly(str(ex), context="training")
                
                def show_error():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ {user_msg}"),
                        bgcolor=ModernTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(show_error)
                    else:
                        show_error()
                except Exception:
                    show_error()
        
        thread = threading.Thread(target=workflow, daemon=True)
        thread.start()

    def show_training_view(self):
        """Show training jobs view."""
        self.secrets_list.controls.clear()
        
        # Fetch training jobs from backend
        jobs = []
        if self.training_manager:
            try:
                response = requests.get(
                    f"{self.backend_url}/api/adapters/adapters",
                    headers=self.training_manager.headers,
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    jobs = data.get("adapters", [])
                else:
                    logger.warning(f"Failed to fetch training jobs: {response.status_code}")
            except Exception as e:
                logger.warning(f"Error fetching training jobs: {e}")
        
        # Training view content
        content_items = [
            ft.Row(
                [
                    ft.Text(
                        "🤖 Training Jobs",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=ModernTheme.TEXT_PRIMARY,
                    ),
                    ft.IconButton(
                        ft.Icons.REFRESH_ROUNDED,
                        tooltip="Refresh",
                        on_click=lambda _: self.show_training_view(),
                        icon_color=ModernTheme.TEXT_SECONDARY,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Divider(color=ModernTheme.BORDER_COLOR),
        ]
        
        if not jobs:
            content_items.append(
                ft.Text(
                    "No training jobs yet. Upload a PDF and train a model to get started!",
                    size=14,
                    color=ModernTheme.TEXT_MUTED
                )
            )
        else:
            # Display jobs
            for job in jobs:
                status = job.get("status", "unknown")
                adapter_id = job.get("adapter_id", "Unknown")
                job_id = job.get("job_id", "N/A")
                created_at = job.get("created_at", "")
                
                status_colors = {
                    "pending": ModernTheme.ACCENT_WARNING,
                    "training": ModernTheme.ACCENT_PRIMARY,
                    "completed": ModernTheme.ACCENT_SUCCESS,
                    "failed": ModernTheme.ACCENT_ERROR
                }
                status_color = status_colors.get(status, ModernTheme.TEXT_MUTED)
                
                job_card = ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                f"Adapter: {adapter_id[:8]}...",
                                                weight=ft.FontWeight.BOLD,
                                                size=16,
                                                color=ModernTheme.TEXT_PRIMARY
                                            ),
                                            ft.Container(
                                                content=ft.Row(
                                                    [
                                                        ft.Icon(
                                                            ft.Icons.TRAIN_ROUNDED if status == "training" else ft.Icons.CHECK_CIRCLE_ROUNDED,
                                                            size=16,
                                                            color=status_color
                                                        ),
                                                        ft.Text(
                                                            status.title(),
                                                            size=12,
                                                            weight=ft.FontWeight.W_500,
                                                            color=status_color
                                                        )
                                                    ],
                                                    spacing=4,
                                                    tight=True
                                                ),
                                                bgcolor=status_color + "20",
                                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                                border_radius=8,
                                                border=ft.border.all(1, status_color + "40"),
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    ft.Container(height=8),
                                    ft.Text(
                                        f"Job ID: {job_id}",
                                        size=12,
                                        color=ModernTheme.TEXT_MUTED
                                    ),
                                    ft.Text(
                                        f"Created: {created_at[:10] if created_at else 'N/A'}",
                                        size=12,
                                        color=ModernTheme.TEXT_MUTED
                                    ),
                                ],
                                spacing=4,
                            ),
                            padding=16,
                        ),
                        elevation=2,
                        color=ModernTheme.BG_ELEVATED,
                    ),
                    margin=ft.margin.only(bottom=12),
                )
                content_items.append(job_card)
        
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(content_items, spacing=10),
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
                        ft.Text(
                            "⚙️ Settings",
                            size=24,
                            weight=ft.FontWeight.BOLD,
                            color=ModernTheme.TEXT_PRIMARY,
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        ft.Text(
                            f"Vault Path: {self.vault_path}",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                        ft.Text(
                            f"Master Key: {self.key_path}",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                        ft.Text(
                            f"Database: {self.db_path}",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                        ft.Divider(color=ModernTheme.BORDER_COLOR),
                        ft.Text(
                            "Encryption: XChaCha20-Poly1305",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                        ft.Text(
                            "Key Size: 32 bytes (256-bit)",
                            size=14,
                            color=ModernTheme.TEXT_SECONDARY,
                        ),
                    ],
                    spacing=12,
                ),
                padding=24,
            )
        )
        self.page.update()


def main(page: ft.Page):
    """Main entry point."""
    VaultApp(page)


if __name__ == "__main__":
    ft.app(target=main)
