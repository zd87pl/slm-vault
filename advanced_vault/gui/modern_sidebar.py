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
        selected_index: int = 0
    ):
        """
        Initialize modern sidebar.
        
        Args:
            on_nav_change: Callback when navigation item is clicked
            selected_index: Currently selected item index
        """
        self.on_nav_change = on_nav_change
        self.selected_index = selected_index
        self._nav_items = []
    
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
        """Build the sidebar component."""
        nav_controls = []
        
        # App branding at top
        nav_controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Text("🔐", size=16),
                                    width=32,
                                    height=32,
                                    border_radius=8,
                                    bgcolor=LightTheme.ACCENT_BLUE_LIGHT,
                                    alignment=ft.alignment.center,
                                ),
                                ft.Container(width=8),
                                ft.Column(
                                    [
                                        ft.Text(
                                            "Enclave",
                                            size=LightTheme.FONT_SIZE_LG,
                                            weight=ft.FontWeight.W_600,
                                            color=LightTheme.TEXT_PRIMARY,
                                        ),
                                        ft.Text(
                                            "Secure Vault",
                                            size=LightTheme.FONT_SIZE_XS,
                                            color=LightTheme.TEXT_MUTED,
                                        ),
                                    ],
                                    spacing=0,
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.padding.all(LightTheme.PADDING_LG),
                border=ft.border.only(bottom=ft.border.BorderSide(1, LightTheme.BORDER_COLOR)),
            )
        )
        
        # Navigation items
        nav_items_column = []
        
        # Home item (always first)
        home_item = {
            "icon": ft.Icons.HOME_OUTLINED,
            "selected": ft.Icons.HOME_ROUNDED,
            "label": "Home",
            "idx": -1
        }
        nav_items_column.append(
            self._create_nav_item(
                icon=home_item["icon"],
                selected_icon=home_item["selected"],
                label=home_item["label"],
                index=home_item["idx"],
                is_selected=self.selected_index == home_item["idx"]
            )
        )
        
        nav_items_column.append(
            ft.Container(
                height=LightTheme.SPACING_MD,
                margin=ft.margin.only(top=LightTheme.SPACING_MD, bottom=LightTheme.SPACING_MD),
            )
        )
        
        # Primary section
        primary_items = [
            {"icon": ft.Icons.KEY_OUTLINED, "selected": ft.Icons.KEY_ROUNDED, "label": "Secrets", "idx": 0},
            {"icon": ft.Icons.LIGHTBULB_OUTLINED, "selected": ft.Icons.LIGHTBULB_ROUNDED, "label": "Knowledge", "idx": 1},
        ]
        
        for item in primary_items:
            nav_items_column.append(
                self._create_nav_item(
                    icon=item["icon"],
                    selected_icon=item["selected"],
                    label=item["label"],
                    index=item["idx"],
                    is_selected=self.selected_index == item["idx"]
                )
            )
        
        nav_items_column.append(
            ft.Container(
                height=LightTheme.SPACING_MD,
                margin=ft.margin.only(top=LightTheme.SPACING_MD, bottom=LightTheme.SPACING_MD),
            )
        )
        
        # Secondary section
        secondary_items = [
            {"icon": ft.Icons.PSYCHOLOGY_OUTLINED, "selected": ft.Icons.PSYCHOLOGY_ROUNDED, "label": "Training", "idx": 2},
            {"icon": ft.Icons.HISTORY_OUTLINED, "selected": ft.Icons.HISTORY_ROUNDED, "label": "Activity", "idx": 3},
            {"icon": ft.Icons.BAR_CHART_OUTLINED, "selected": ft.Icons.BAR_CHART_ROUNDED, "label": "Statistics", "idx": 4},
            {"icon": ft.Icons.SECURITY_OUTLINED, "selected": ft.Icons.SECURITY_ROUNDED, "label": "LangChain", "idx": 6},
        ]
        
        for item in secondary_items:
            nav_items_column.append(
                self._create_nav_item(
                    icon=item["icon"],
                    selected_icon=item["selected"],
                    label=item["label"],
                    index=item["idx"],
                    is_selected=self.selected_index == item["idx"]
                )
            )
        
        nav_items_column.append(
            ft.Container(
                height=LightTheme.SPACING_MD,
                margin=ft.margin.only(top=LightTheme.SPACING_MD, bottom=LightTheme.SPACING_MD),
            )
        )
        
        # Setup/Settings section
        settings_item = {
            "icon": ft.Icons.SETTINGS_OUTLINED,
            "selected": ft.Icons.SETTINGS_ROUNDED,
            "label": "Setup",
            "idx": 5
        }
        
        nav_items_column.append(
            self._create_nav_item(
                icon=settings_item["icon"],
                selected_icon=settings_item["selected"],
                label=settings_item["label"],
                index=settings_item["idx"],
                is_selected=self.selected_index == settings_item["idx"]
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

