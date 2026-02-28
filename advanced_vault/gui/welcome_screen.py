"""Onboarding wizard for first-time users."""

from typing import Callable, Optional

import flet as ft

from light_theme import LightTheme
from localization import get_text


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
        self.completed_steps = set()
        self._step_defs = [
            {"id": "connect", "icon": ft.Icons.CABLE_ROUNDED},
            {"id": "encrypt", "icon": ft.Icons.LOCK_ROUNDED},
            {"id": "train", "icon": ft.Icons.PSYCHOLOGY_ROUNDED},
            {"id": "ask", "icon": ft.Icons.CHAT_ROUNDED},
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
        completed = len(self.completed_steps)
        progress = completed / len(self._step_defs)

        step_cards = [self._build_step_card(step) for step in self._step_defs]

        return ft.Container(
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
            padding=ft.padding.symmetric(horizontal=56, vertical=40),
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
                        size=14,
                        color=LightTheme.TEXT_SECONDARY,
                    ),
                    ft.Container(height=16),
                    ft.Row(
                        [
                            ft.Text(
                                self.t(
                                    "onboarding.progress",
                                    completed=completed,
                                    total=len(self._step_defs),
                                ),
                                size=12,
                                color=LightTheme.TEXT_MUTED,
                            ),
                            ft.Container(expand=True),
                            ft.Text(
                                self.t("onboarding.ttfv"),
                                size=12,
                                color=LightTheme.TEXT_MUTED,
                            ),
                        ],
                    ),
                    ft.ProgressBar(
                        value=progress,
                        color=LightTheme.ACCENT_PRIMARY,
                        bgcolor=LightTheme.BORDER_COLOR,
                        height=8,
                    ),
                    ft.Container(height=18),
                    ft.Column(step_cards, spacing=12),
                    ft.Container(height=18),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                self.t("onboarding.continue"),
                                icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                on_click=self._on_continue,
                                style=ft.ButtonStyle(
                                    bgcolor=LightTheme.ACCENT_PRIMARY,
                                    color="white",
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                    padding=ft.padding.symmetric(horizontal=26, vertical=14),
                                ),
                            ),
                            ft.OutlinedButton(
                                self.t("onboarding.add_sample"),
                                icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                                on_click=self._on_add_sample,
                                style=ft.ButtonStyle(
                                    color=LightTheme.TEXT_PRIMARY,
                                    side=ft.BorderSide(1, LightTheme.BORDER_COLOR),
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
            ),
        )

    def _build_step_card(self, step: dict) -> ft.Container:
        step_id = step["id"]
        step_done = step_id in self.completed_steps
        status_icon = ft.Icons.CHECK_CIRCLE_ROUNDED if step_done else ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED
        status_color = LightTheme.ACCENT_SUCCESS if step_done else LightTheme.TEXT_MUTED

        def _run_step(_):
            self.completed_steps.add(step_id)
            if self.on_step_action:
                self.on_step_action(step_id)
                return
            self.page.update()

        return ft.Container(
            bgcolor=LightTheme.BG_ELEVATED,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            border_radius=12,
            padding=16,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=34,
                                height=34,
                                border_radius=9,
                                bgcolor=LightTheme.ACCENT_PRIMARY + "20",
                                alignment=ft.alignment.center,
                                content=ft.Icon(step["icon"], size=18, color=LightTheme.ACCENT_PRIMARY),
                            ),
                            ft.Container(width=10),
                            ft.Text(
                                self.t(f"onboarding.step.{step_id}.title"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                                color=LightTheme.TEXT_PRIMARY,
                                expand=True,
                            ),
                            ft.Icon(status_icon, size=18, color=status_color),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        self.t(f"onboarding.step.{step_id}.description"),
                        size=13,
                        color=LightTheme.TEXT_SECONDARY,
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        self.t(f"onboarding.step.{step_id}.value"),
                        size=12,
                        color=LightTheme.ACCENT_SUCCESS,
                    ),
                    ft.Container(height=10),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                self.t(f"onboarding.step.{step_id}.cta"),
                                icon=ft.Icons.ARROW_RIGHT_ALT_ROUNDED,
                                on_click=_run_step,
                                style=ft.ButtonStyle(
                                    bgcolor=LightTheme.BG_SECONDARY,
                                    color=LightTheme.TEXT_PRIMARY,
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                        ],
                    ),
                ],
                spacing=0,
            ),
        )

    def _on_continue(self, _):
        self.on_start()

    def _on_add_sample(self, _):
        if self.on_add_sample:
            self.on_add_sample()
