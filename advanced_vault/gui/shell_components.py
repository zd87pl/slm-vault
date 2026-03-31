"""Reusable shell presentation helpers for the Enclave desktop app."""

from __future__ import annotations

from typing import Optional

import flet as ft

try:
    from light_theme import LightTheme
except ImportError:  # pragma: no cover - package import fallback
    from .light_theme import LightTheme


def build_status_badge(
    label: str,
    color: Optional[str] = None,
    icon: Optional[str] = None,
    tint: Optional[str] = None,
) -> ft.Container:
    """Small pill badge used across the investor demo shell."""
    badge_color = color or LightTheme.TEXT_MUTED
    badge_tint = tint or (badge_color + "12" if badge_color.startswith("#") else LightTheme.BG_HOVER)
    controls = []
    if icon:
        controls.append(ft.Icon(icon, size=12, color=badge_color))
    controls.append(ft.Text(label, size=11, color=badge_color, weight=ft.FontWeight.W_500))
    return ft.Container(
        content=ft.Row(controls, spacing=6, tight=True),
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        bgcolor=badge_tint,
        border_radius=999,
    )


def build_surface_card(
    content: ft.Control,
    padding: int = 20,
    bgcolor: Optional[str] = None,
) -> ft.Container:
    """Standard elevated card surface for investor-demo views."""
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=bgcolor or LightTheme.BG_ELEVATED,
        border_radius=16,
        border=ft.border.all(1, LightTheme.BORDER_COLOR),
    )


def simple_metric_card(label: str, value: str) -> ft.Container:
    """Small stable metric card for the simplified workspace."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(label, size=11, color=LightTheme.TEXT_MUTED),
                ft.Text(value, size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ],
            spacing=4,
        ),
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
    )
