"""
Welcome Screen for First-Time Users

Shows onboarding flow with tutorial and sample data options.
"""

import flet as ft
from sleek_theme import SleekTheme
from light_theme import LightTheme
from typing import Callable, Optional

logger = None


class WelcomeScreen:
    """Welcome screen for first-time users."""
    
    def __init__(
        self,
        page: ft.Page,
        on_start: Callable[[], None],
        on_add_sample: Optional[Callable[[], None]] = None
    ):
        """
        Initialize welcome screen.
        
        Args:
            page: Flet page instance
            on_start: Callback when user clicks "Get Started"
            on_add_sample: Optional callback to add sample data
        """
        self.page = page
        self.on_start = on_start
        self.on_add_sample = on_add_sample
        self.skip_tutorial = False
        
    def get_view(self) -> ft.Container:
        """Get the welcome screen view - ProtonVPN-style modern design."""
        return ft.Container(
            content=ft.Column(
                [
                    # Hero section - centered, prominent
                    ft.Container(
                        content=ft.Column(
                            [
                                # Icon with glow effect
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.LOCK_ROUNDED,
                                        size=96,
                                        color=LightTheme.ACCENT_PRIMARY,
                                    ),
                                    padding=32,
                                    border_radius=24,
                                    bgcolor=LightTheme.BG_ELEVATED,
                                    border=ft.border.all(2, LightTheme.ACCENT_PRIMARY + "40"),
                                    # Subtle shadow effect (via elevated background)
                                ),
                                ft.Container(height=40),
                                ft.Text(
                                    "Welcome to Enclave",
                                    size=42,
                                    weight=ft.FontWeight.BOLD,
                                    color=LightTheme.TEXT_PRIMARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=16),
                                ft.Text(
                                    "Your encrypted vault with AI-powered knowledge extraction",
                                    size=17,
                                    color=LightTheme.TEXT_SECONDARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=64),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        alignment=ft.alignment.center,
                        padding=ft.padding.symmetric(horizontal=40),
                    ),
                    
                    # Features list - clean, spaced out
                    ft.Container(
                        content=ft.Column(
                            [
                                self._create_feature_item(
                                    ft.Icons.LOCK_ROUNDED,
                                    "End-to-End Encryption",
                                    "Your data is encrypted before it leaves your device"
                                ),
                                ft.Container(height=24),
                                self._create_feature_item(
                                    ft.Icons.PSYCHOLOGY_ROUNDED,
                                    "AI-Powered Knowledge",
                                    "Train personalized models on your documents"
                                ),
                                ft.Container(height=24),
                                self._create_feature_item(
                                    ft.Icons.CLOUD_DONE_ROUNDED,
                                    "Cloud Sync",
                                    "Sync across devices securely"
                                ),
                                ft.Container(height=24),
                                self._create_feature_item(
                                    ft.Icons.SEARCH_ROUNDED,
                                    "Smart Search",
                                    "Find anything instantly with tags and full-text search"
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=ft.padding.symmetric(horizontal=60),
                    ),
                    
                    ft.Container(height=56),
                    
                    # Action buttons - prominent, well-spaced
                    ft.Container(
                        content=ft.Column(
                            [
                                # Primary CTA - large, prominent
                                ft.ElevatedButton(
                                    "Get Started",
                                    icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                    on_click=self._on_get_started,
                                    style=ft.ButtonStyle(
                                        bgcolor=LightTheme.ACCENT_PRIMARY,
                                        color="white",
                                        padding=ft.padding.symmetric(horizontal=48, vertical=20),
                                        shape=ft.RoundedRectangleBorder(radius=12),
                                        elevation=2,
                                    ),
                                    height=56,
                                ),
                                ft.Container(height=20),
                                
                                # Secondary: Add sample data
                                ft.ElevatedButton(
                                    "Add Sample Data",
                                    icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                                    on_click=self._on_add_sample,
                                    style=ft.ButtonStyle(
                                        bgcolor=LightTheme.BG_ELEVATED,
                                        color=LightTheme.TEXT_PRIMARY,
                                        padding=ft.padding.symmetric(horizontal=40, vertical=16),
                                        shape=ft.RoundedRectangleBorder(radius=12),
                                        side=ft.BorderSide(1.5, LightTheme.BORDER_COLOR),
                                    ),
                                    height=52,
                                ),
                                
                                ft.Container(height=32),
                                
                                # Skip tutorial checkbox - subtle
                                ft.Container(
                                    content=ft.Row(
                                        [
                                            ft.Checkbox(
                                                value=False,
                                                on_change=self._on_checkbox_change,
                                                label=None,
                                                fill_color=LightTheme.ACCENT_PRIMARY,
                                            ),
                                            ft.Text(
                                                "Skip tutorial",
                                                size=13,
                                                color=LightTheme.TEXT_SECONDARY,
                                            ),
                                        ],
                                        spacing=8,
                                        tight=True,
                                    ),
                                    alignment=ft.alignment.center,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        padding=ft.padding.symmetric(horizontal=60),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,  # Allow scroll only if content exceeds viewport
                spacing=0,
            ),
            bgcolor=LightTheme.BG_PRIMARY,
            padding=80,  # More padding for breathing room
            expand=True,
            alignment=ft.alignment.center,
        )
    
    def _create_feature_item(self, icon, title: str, description: str) -> ft.Container:
        """Create a feature item row - clean, modern design."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(
                            icon,
                            size=28,
                            color=LightTheme.ACCENT_PRIMARY,
                        ),
                        padding=14,
                        border_radius=12,
                        bgcolor=LightTheme.ACCENT_PRIMARY + "20",  # Slightly more visible
                    ),
                    ft.Container(width=20),
                    ft.Column(
                        [
                            ft.Text(
                                title,
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Container(height=6),
                            ft.Text(
                                description,
                                size=14,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.padding.symmetric(vertical=12),
        )
    
    def _on_get_started(self, e):
        """Handle Get Started button click."""
        if not self.skip_tutorial:
            # Show tutorial overlay
            self._show_tutorial()
        else:
            # Skip directly to main app
            self.on_start()
    
    def _on_add_sample(self, e):
        """Handle Add Sample Data button click."""
        if self.on_add_sample:
            self.on_add_sample()
        # Then show tutorial or go to main app
        if not self.skip_tutorial:
            self._show_tutorial()
        else:
            self.on_start()
    
    def _on_checkbox_change(self, e):
        """Handle skip tutorial checkbox change."""
        self.skip_tutorial = e.control.value
    
    def _show_tutorial(self):
        """Show interactive tutorial overlay."""
        tutorial_steps = [
            {
                "title": "Step 1: Add Your First Secret",
                "description": "Click the ➕ button in the top-right to add a secret or upload a document.",
                "target": "add_button",
            },
            {
                "title": "Step 2: Upload a PDF",
                "description": "Go to the Knowledge tab to upload PDFs and train AI models on your documents.",
                "target": "knowledge_tab",
            },
            {
                "title": "Step 3: Ask Questions",
                "description": "Your trained models can answer questions about your documents via MCP integration.",
                "target": None,
            },
        ]
        
        # Store tutorial state for later use
        # For now, just proceed to main app
        # TODO: Implement tutorial overlay with highlights
        self.on_start()

