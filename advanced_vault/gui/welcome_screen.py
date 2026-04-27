"""Onboarding wizard for first-time users."""

from typing import Callable, Optional

import flet as ft

from light_theme import LightTheme
from localization import get_text
from shell_components import build_button, ButtonVariant


class WelcomeScreen:
    """Step-by-step onboarding view."""

    def __init__(
        self,
        page: ft.Page,
        on_start: Callable[[], None],
        on_add_sample: Optional[Callable[[], None]] = None,
        on_step_action: Optional[Callable[[str], None]] = None,
        translate: Optional[Callable[..., str]] = None,
    ):
        self.page = page
        self.on_start = on_start
        self.on_add_sample = on_add_sample
        self.on_step_action = on_step_action
        self.translate = translate
        self._step_defs = [
            {"id": "add", "icon": ft.Icons.FILE_UPLOAD_ROUNDED},
            {"id": "ask", "icon": ft.Icons.CHAT_ROUNDED},
            {"id": "protect", "icon": ft.Icons.SHIELD_ROUNDED},
        ]

    def t(self, key: str, **kwargs) -> str:
        """Translate key (falls back to EN)."""
        if self.translate:
            try:
                return self.translate(key, **kwargs)
            except Exception:
                return self.translate(key)
        return get_text("en", key, **kwargs)

    def get_view(self) -> ft.Container:
        step_chips = [
            self._build_step_chip(index + 1, step)
            for index, step in enumerate(self._step_defs)
        ]
        trust_badges = ft.Row(
            [
                self._build_trust_badge(ft.Icons.LAPTOP_MAC_ROUNDED, self.t("onboarding.trust.local")),
                self._build_trust_badge(ft.Icons.NO_ACCOUNTS_ROUNDED, self.t("onboarding.trust.account")),
                self._build_trust_badge(ft.Icons.VERIFIED_USER_ROUNDED, self.t("onboarding.trust.control")),
            ],
            spacing=10,
            wrap=True,
        )

        return ft.Container(
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
            padding=ft.padding.symmetric(horizontal=40, vertical=32),
            content=ft.Column(
                [
                    ft.Container(
                        width=760,
                        content=ft.Column(
                            [
                                ft.Text(
                                    self.t("onboarding.title"),
                                    size=34,
                                    weight=ft.FontWeight.BOLD,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Text(
                                    self.t("onboarding.subtitle"),
                                    size=15,
                                    color=LightTheme.TEXT_SECONDARY,
                                ),
                                ft.Container(height=18),
                                trust_badges,
                                ft.Container(height=24),
                                ft.Row(step_chips, spacing=10, wrap=True),
                                ft.Container(height=28),
                                ft.Row(
                                    [
                                        build_button(
                                            self.t("onboarding.primary"),
                                            icon=ft.Icons.FILE_UPLOAD_ROUNDED,
                                            on_click=lambda e: self._run_step_action("add"),
                                            variant=ButtonVariant.PRIMARY,
                                            padding=ft.padding.symmetric(horizontal=26, vertical=14),
                                        ),
                                        build_button(
                                            self.t("onboarding.add_sample"),
                                            icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                                            on_click=self._on_add_sample,
                                            variant=ButtonVariant.OUTLINE,
                                            padding=ft.padding.symmetric(horizontal=26, vertical=14),
                                        ),
                                        build_button(
                                            self.t("onboarding.skip"),
                                            on_click=self._on_continue,
                                            variant=ButtonVariant.GHOST,
                                        ),
                                    ],
                                    spacing=12,
                                    wrap=True,
                                ),
                            ],
                            spacing=0,
                        ),
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _build_step_chip(self, number: int, step: dict) -> ft.Container:
        step_id = step["id"]
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=14,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            content=ft.Row(
                [
                    ft.Container(
                        width=24,
                        height=24,
                        border_radius=999,
                        bgcolor=LightTheme.ACCENT_PRIMARY + "14",
                        alignment=ft.alignment.center,
                        content=ft.Text(
                            str(number),
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color=LightTheme.ACCENT_PRIMARY,
                        ),
                    ),
                    ft.Text(
                        self.t(f"onboarding.step.{step_id}.title"),
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=LightTheme.TEXT_PRIMARY,
                    ),
                ],
                spacing=10,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _build_trust_badge(self, icon: str, label: str) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=14, color=LightTheme.ACCENT_PRIMARY),
                    ft.Text(label, size=12, color=LightTheme.TEXT_PRIMARY),
                ],
                spacing=6,
                tight=True,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=999,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )

    def _run_step_action(self, step_id: str) -> None:
        if self.on_step_action:
            self.on_step_action(step_id)
            return
        self.on_start()

    def _on_continue(self, _):
        self.on_start()

    def _on_add_sample(self, _):
        if self.on_add_sample:
            self.on_add_sample()
