"""Smoke tests for the investor-demo workspace render path."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import flet as ft

from advanced_vault.gui.vault_app import VaultApp


class _FakeWindow:
    def __init__(self) -> None:
        self.width = 0
        self.height = 0
        self.min_width = 0
        self.min_height = 0

    def center(self) -> None:
        return None


class _FakePage:
    def __init__(self) -> None:
        self.title = ""
        self.theme_mode = None
        self.padding = 0
        self.theme = None
        self.bgcolor = None
        self.overlay = []
        self.controls = []
        self.snack_bar = None
        self.window = _FakeWindow()

    def clean(self) -> None:
        self.controls = []

    def add(self, *controls) -> None:
        self.controls.extend(list(controls))

    def update(self) -> None:
        return None

    def run_task(self, coro) -> None:
        return None


def _collect_strings(node) -> list[str]:
    strings: list[str] = []
    if node is None:
        return strings

    for attr in ("value", "label", "text", "hint_text", "tooltip", "title"):
        value = getattr(node, attr, None)
        if isinstance(value, str) and value:
            strings.append(value)

    content = getattr(node, "content", None)
    if content is not None:
        strings.extend(_collect_strings(content))

    controls = getattr(node, "controls", None)
    if isinstance(controls, list):
        for control in controls:
            strings.extend(_collect_strings(control))

    if isinstance(node, ft.Text):
        strings.append(node.value)
    return strings


class _FakeEngine:
    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> str:
        return "Investor-ready summary generated locally."


class TestWorkspaceDemo(unittest.TestCase):
    """Ensure the workspace always renders as a usable local demo surface."""

    def _make_app(self, home_dir: str) -> tuple[VaultApp, _FakePage]:
        page = _FakePage()
        with patch.dict(
            os.environ,
            {
                "HOME": home_dir,
                "ENCLAVE_LOCAL_FIRST": "1",
                "ENCLAVE_REQUIRE_AUTH": "0",
            },
            clear=False,
        ):
            with patch.object(VaultApp, "check_authentication", autospec=True, return_value=None):
                app = VaultApp(page)
        return app, page

    def test_workspace_renders_empty_state_with_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            app.show_landing_page()

            self.assertTrue(page.controls)
            self.assertIsNotNone(app.chat_input)
            strings = _collect_strings(page.controls[0])
            self.assertIn("Secure Chat Workspace", strings)
            self.assertIn("Add Files", strings)
            self.assertIn("Add Folder", strings)
            self.assertIn("Workspace", strings)
            self.assertGreater(len(app.chat_messages_list.controls), 0)

    def test_workspace_renders_indexed_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            profile = app._ensure_private_model_profile()
            session = app.private_model_manager.open_session(profile.name)
            try:
                session.add_document(
                    name="pitch.md",
                    content="Revenue grew from 1M to 3M while margins improved.",
                    source_path=str(Path(tmpdir) / "pitch.md"),
                )
            finally:
                session.close()

            app._show_workspace_view()
            strings = _collect_strings(page.controls[0])
            self.assertIn("pitch.md", strings)
            self.assertIn("Add Files", strings)
            self.assertIn("Add Folder", strings)
            self.assertIn("Secure Chat Workspace", strings)
            self.assertIn("Ask about your 1 indexed document(s)...", strings)

    def test_local_ingest_and_chat_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, _ = self._make_app(tmpdir)
            profile = app._ensure_private_model_profile()
            session = app.private_model_manager.open_session(profile.name)
            try:
                session.add_document(
                    name="investor_update.txt",
                    content="The pipeline doubled and enterprise pilots converted faster than expected.",
                    source_path=str(Path(tmpdir) / "investor_update.txt"),
                )
                with patch.object(session, "_ensure_engine", return_value=_FakeEngine()):
                    result = session.ask("What happened in the pipeline?")
            finally:
                session.close()

            self.assertIn("Investor-ready summary", result["answer"])
            self.assertTrue(result["sources"])
            self.assertEqual(result["profile"], profile.name)


if __name__ == "__main__":
    unittest.main()
