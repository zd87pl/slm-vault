"""
Modern Sidebar Component for Desktop App Feel

Provides a polished, desktop-app-style sidebar navigation.
"""

import flet as ft
from theme import ModernTheme
from sleek_theme import SleekTheme
from light_theme import LightTheme
from typing import Callable, Optional, List, Dict


class ModernSidebar:
    """Modern sidebar navigation component."""
    
    def __init__(
        self,
        on_nav_change: Callable[[int], None],
        selected_index: int = 0,
        translate: Optional[Callable[..., str]] = None,
    ):
        """
        Initialize modern sidebar.
        
        Args:
            on_nav_change: Callback when navigation item is clicked
            selected_index: Currently selected item index
        """
        self.on_nav_change = on_nav_change
        self.selected_index = selected_index
        self.translate = translate
        self._nav_items = []

    def t(self, key: str, fallback: str) -> str:
        """Translate label if callback is available."""
        if not self.translate:
            return fallback
        try:
            return self.translate(key)
        except Exception:
            return fallback
    
    def add_nav_item(
        self,
        icon: str,
        selected_icon: str,
        label: str,
        badge: Optional[str] = None
    ):
        """Add a navigation item."""
        self._nav_items.append({
            "icon": icon,
            "selected_icon": selected_icon,
            "label": label,
            "badge": badge
        })
    
    def build(self) -> ft.Container:
        """Build the sidebar component with a simple product-focused navigation."""
        nav_controls = []

        # Clean top spacing (branding is in window title)
        nav_controls.append(ft.Container(height=12))

        # Simplified navigation structure (3 items)
        # -1: Workspace
        #  0: Library
        #  2: Security
        nav_items_column = []
        nav_items = [
            {
                "icon": ft.Icons.FORUM_OUTLINED,
                "selected": ft.Icons.FORUM_ROUNDED,
                "label": "Workspace",
                "idx": -1,
            },
            {
                "icon": ft.Icons.FOLDER_OUTLINED,
                "selected": ft.Icons.FOLDER_ROUNDED,
                "label": "Library",
                "idx": 0,
            },
            {
                "icon": ft.Icons.GPP_GOOD_OUTLINED,
                "selected": ft.Icons.GPP_GOOD_ROUNDED,
                "label": "Security",
                "idx": 2,
            },
        ]

        for item in nav_items:
            nav_items_column.append(
                self._create_nav_item(
                    icon=item["icon"],
                    selected_icon=item["selected"],
                    label=item["label"],
                    index=item["idx"],
                    is_selected=self.selected_index == item["idx"],
                )
            )

        nav_controls.append(
            ft.Container(
                content=ft.Column(
                    nav_items_column,
                    spacing=4,
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                expand=True,
            )
        )

        # Build sidebar container
        return ft.Container(
            content=ft.Column(
                nav_controls,
                spacing=0,
                expand=True,
            ),
            width=240,
            bgcolor=LightTheme.BG_SECONDARY,
            border=ft.border.only(right=ft.border.BorderSide(1, LightTheme.BORDER_COLOR)),
        )
    
    def _create_nav_item(
        self,
        icon: str,
        selected_icon: str,
        label: str,
        index: int,
        is_selected: bool
    ) -> ft.Container:
        """Create a navigation item with modern styling."""
        
        # Active indicator (left border)
        active_indicator = ft.Container(
            width=3,
            height=32,
            bgcolor=LightTheme.ACCENT_PRIMARY,
            border_radius=ft.border_radius.only(
                top_right=2,
                bottom_right=2
            ),
            visible=is_selected,
            margin=ft.margin.only(right=8),
        )
        
        # Icon container
        icon_color = LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY
        bg_color = LightTheme.ACCENT_BLUE_LIGHT if is_selected else "transparent"
        
        return ft.Container(
            content=ft.Row(
                [
                    active_indicator,
                    ft.Container(
                        content=ft.Icon(
                            selected_icon if is_selected else icon,
                            size=LightTheme.ICON_SIZE_SM,
                            color=icon_color,
                        ),
                        width=32,
                        height=32,
                        border_radius=8,
                        bgcolor=bg_color,
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(width=8),
                    ft.Text(
                        label,
                        size=LightTheme.FONT_SIZE_BASE,
                        weight=ft.FontWeight.W_500 if is_selected else ft.FontWeight.NORMAL,
                        color=LightTheme.TEXT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.padding.symmetric(horizontal=LightTheme.PADDING_SM, vertical=LightTheme.PADDING_XS),
            border_radius=8,
            bgcolor=LightTheme.BG_HOVER if is_selected else "transparent",
            on_click=lambda e, idx=index: self.on_nav_change(idx),
            tooltip=label,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )
