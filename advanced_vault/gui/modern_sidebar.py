"""Minimal Enclave desktop sidebar optimized for stable Flet rendering."""

from typing import Callable, Optional

import flet as ft

from light_theme import LightTheme


class ModernSidebar:
    """Stable sidebar shell for the investor demo."""

    def __init__(
        self,
        on_nav_change: Callable[[int], None],
        selected_index: int = -1,
        translate: Optional[Callable[..., str]] = None,
    ):
        self.on_nav_change = on_nav_change
        self.selected_index = selected_index
        self.translate = translate

    def build(self) -> ft.Container:
        nav_items = [
            ("Workspace", -1),
            ("Library", 0),
            ("Connections", 1),
            ("Security", 2),
        ]

        return ft.Container(
            width=236,
            padding=ft.padding.only(left=16, right=16, top=24, bottom=24),
            content=ft.Column(
                [
                    ft.Text("Enclave", size=18, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                    ft.Text("Private AI", size=11, color=LightTheme.TEXT_MUTED),
                    ft.Container(height=20),
                    *[self._nav_button(label, index) for label, index in nav_items],
                    ft.Container(height=20),
                    self._info_card("MLX Engine", "Unified Memory: 14.2 / 32 GB\nGPU Compute: 12%"),
                    self._info_card("All Local", "No data leaves your device"),
                    ft.Container(height=20),
                    ft.Text("John Doe", size=13, weight=ft.FontWeight.W_500, color=LightTheme.TEXT_PRIMARY),
                    ft.Text("Premium Plan", size=10, color=LightTheme.TEXT_MUTED),
                ],
                spacing=8,
            ),
        )

    def _nav_button(self, label: str, index: int) -> ft.Container:
        is_selected = self.selected_index == index
        return ft.TextButton(
            label,
            on_click=lambda e, idx=index: self.on_nav_change(idx),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=14, vertical=12),
                color=LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.TEXT_MUTED,
            ),
        )

    def _info_card(self, title: str, detail: str) -> ft.Container:
        return ft.Container(
            padding=ft.padding.all(6),
            content=ft.Column(
                [
                    ft.Text(title, size=11, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                    ft.Text(detail, size=10, color=LightTheme.TEXT_MUTED),
                ],
                spacing=6,
            ),
        )
