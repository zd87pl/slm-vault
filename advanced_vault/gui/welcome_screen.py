"""
Welcome Screen for First-Time Users

Shows onboarding flow with tutorial and sample data options.
"""

import flet as ft
from theme import ModernTheme
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
        """Get the welcome screen view."""
        return ft.Container(
            content=ft.Column(
                [
                    # Hero section
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.LOCK_ROUNDED,
                                        size=100,
                                        color=ModernTheme.ACCENT_PRIMARY,
                                    ),
                                    padding=30,
                                    border_radius=30,
                                    bgcolor=ModernTheme.BG_ELEVATED,
                                    border=ft.border.all(2, ModernTheme.BORDER_COLOR),
                                ),
                                ft.Container(height=32),
                                ft.Text(
                                    "Welcome to Enclave",
                                    size=42,
                                    weight=ft.FontWeight.BOLD,
                                    color=ModernTheme.TEXT_PRIMARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=12),
                                ft.Text(
                                    "Your encrypted vault with AI training",
                                    size=18,
                                    color=ModernTheme.TEXT_SECONDARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=48),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        alignment=ft.alignment.center,
                    ),
                    
                    # Features list
                    ft.Container(
                        content=ft.Column(
                            [
                                self._create_feature_item(
                                    ft.Icons.LOCK_ROUNDED,
                                    "End-to-End Encryption",
                                    "Your data is encrypted before it leaves your device"
                                ),
                                ft.Container(height=16),
                                self._create_feature_item(
                                    ft.Icons.PSYCHOLOGY_ROUNDED,
                                    "AI-Powered Knowledge",
                                    "Train personalized models on your documents"
                                ),
                                ft.Container(height=16),
                                self._create_feature_item(
                                    ft.Icons.CLOUD_DONE_ROUNDED,
                                    "Cloud Sync",
                                    "Sync across devices securely"
                                ),
                                ft.Container(height=16),
                                self._create_feature_item(
                                    ft.Icons.SEARCH_ROUNDED,
                                    "Smart Search",
                                    "Find anything instantly with tags and full-text search"
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=ft.padding.symmetric(horizontal=40),
                    ),
                    
                    ft.Container(height=48),
                    
                    # Action buttons
                    ft.Container(
                        content=ft.Column(
                            [
                                # Primary CTA
                                ft.ElevatedButton(
                                    "Get Started",
                                    icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                    on_click=self._on_get_started,
                                    style=ft.ButtonStyle(
                                        bgcolor=ModernTheme.ACCENT_PRIMARY,
                                        color="white",
                                        padding=ft.padding.symmetric(horizontal=32, vertical=16),
                                        shape=ft.RoundedRectangleBorder(radius=12),
                                    ),
                                    height=56,
                                ),
                                ft.Container(height=16),
                                
                                # Secondary: Add sample data
                                ft.Container(
                                    content=ft.ElevatedButton(
                                        "Add Sample Data",
                                        icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                                        on_click=self._on_add_sample,
                                        style=ft.ButtonStyle(
                                            bgcolor=ModernTheme.BG_ELEVATED,
                                            color=ModernTheme.TEXT_PRIMARY,
                                            padding=ft.padding.symmetric(horizontal=32, vertical=12),
                                            shape=ft.RoundedRectangleBorder(radius=12),
                                        ),
                                        height=48,
                                    ),
                                    border=ft.border.all(1, ModernTheme.BORDER_COLOR),
                                    border_radius=12,
                                ),
                                
                                ft.Container(height=24),
                                
                                # Skip tutorial checkbox
                                ft.Container(
                                    content=ft.Row(
                                        [
                                            ft.Checkbox(
                                                value=False,
                                                on_change=self._on_checkbox_change,
                                                label=None,
                                            ),
                                            ft.Text(
                                                "Skip tutorial",
                                                size=14,
                                                color=ModernTheme.TEXT_SECONDARY,
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
                        padding=ft.padding.symmetric(horizontal=40),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
            ),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[ModernTheme.BG_PRIMARY, ModernTheme.BG_SECONDARY],
            ),
            padding=40,
            expand=True,
            alignment=ft.alignment.center,
        )
    
    def _create_feature_item(self, icon, title: str, description: str) -> ft.Container:
        """Create a feature item row."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(
                            icon,
                            size=32,
                            color=ModernTheme.ACCENT_PRIMARY,
                        ),
                        padding=12,
                        border_radius=12,
                        bgcolor=ModernTheme.ACCENT_PRIMARY + "20",
                    ),
                    ft.Container(width=16),
                    ft.Column(
                        [
                            ft.Text(
                                title,
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=ModernTheme.TEXT_PRIMARY,
                            ),
                            ft.Container(height=4),
                            ft.Text(
                                description,
                                size=14,
                                color=ModernTheme.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.padding.symmetric(vertical=8),
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

