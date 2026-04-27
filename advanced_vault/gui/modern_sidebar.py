"""Figma-aligned Enclave sidebar for the desktop shell."""

from typing import Callable, Optional

import flet as ft

from light_theme import LightTheme


class ModernSidebar:
    """Clean three-item navigation sidebar for the Enclave app."""

    _BORDER_COLOR = "#e0e0e0"

    def __init__(
        self,
        on_nav_change: Callable[[int], None],
        selected_index: int = 0,
        translate: Optional[Callable[..., str]] = None,
        document_count: int = 0,
    ):
        self.on_nav_change = on_nav_change
        self.selected_index = selected_index
        self.translate = translate
        self.document_count = document_count

    def build(self) -> ft.Container:
        return ft.Container(
            width=200,
            bgcolor=LightTheme.BG_SUBTLE,
            border=ft.border.only(right=ft.BorderSide(1, self._BORDER_COLOR)),
            padding=ft.padding.symmetric(horizontal=10, vertical=16),
            content=ft.Column(
                controls=[
                    self._build_logo_area(),
                    ft.Container(height=20),
                    self._build_nav_section(),
                    ft.Container(expand=True),
                    self._build_bottom_section(),
                ],
                spacing=0,
                expand=True,
            ),
        )

    def _build_logo_area(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            width=28,
                            height=28,
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            border_radius=8,
                            alignment=ft.alignment.center,
                            content=ft.Text(
                                "E",
                                size=14,
                                weight=ft.FontWeight.W_700,
                                color=LightTheme.BG_ELEVATED,
                            ),
                        ),
                        ft.Text(
                            self._tr("Enclave"),
                            size=15,
                            weight=ft.FontWeight.W_600,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                ft.Text(
                    self._tr("WORKSPACE"),
                    size=9,
                    weight=ft.FontWeight.W_600,
                    color=LightTheme.TEXT_MUTED,
                ),
            ],
            spacing=0,
        )

    def _build_nav_section(self) -> ft.Column:
        nav_items = [
            (self._tr("Chat"), 0),
            (self._tr("Vaults"), 3),
            (self._tr("Files"), 1),
            (self._tr("Settings"), 2),
        ]
        return ft.Column(
            controls=[self._nav_item(label, index) for label, index in nav_items],
            spacing=6,
        )

    def _nav_item(self, label: str, index: int) -> ft.Container:
        is_selected = self.selected_index == index
        return ft.Container(
            width=180,
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            border_radius=8,
            bgcolor=LightTheme.ACCENT_BLUE_LIGHT if is_selected else None,
            ink=True,
            on_click=lambda e, idx=index: self.on_nav_change(idx),
            content=ft.Text(
                label,
                size=13,
                weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.W_500,
                color=LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY,
            ),
        )

    def _build_bottom_section(self) -> ft.Column:
        file_label = "file" if self.document_count == 1 else "files"
        return ft.Column(
            controls=[
                ft.Container(
                    bgcolor=LightTheme.BG_ELEVATED,
                    border=ft.border.all(1, self._BORDER_COLOR),
                    border_radius=10,
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                f"{self.document_count} {file_label} indexed",
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                self._tr("Local × Private"),
                                size=10,
                                color=LightTheme.TEXT_MUTED,
                            ),
                        ],
                        spacing=4,
                    ),
                ),
                ft.Container(height=10),
                ft.Row(
                    controls=[
                        ft.Container(
                            width=7,
                            height=7,
                            bgcolor=LightTheme.ACCENT_SUCCESS,
                            border_radius=3.5,
                        ),
                        ft.Text(
                            self._tr("Local model active"),
                            size=11,
                            color=LightTheme.TEXT_MUTED,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
        )

    def _tr(self, text: str) -> str:
        if callable(self.translate):
            try:
                return self.translate(text)
            except TypeError:
                return self.translate("sidebar", text)
        return text
