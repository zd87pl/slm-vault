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
            # Figma-aligned Chat screen: hero + suggestion chips
            self.assertIn("Chat", strings)
            self.assertIn("Ask anything about your files", strings)
            self.assertIn("Summarize my files", strings)
            self.assertIn("Find key facts", strings)
            # Sidebar: 3-item nav
            self.assertIn("Files", strings)
            self.assertIn("Settings", strings)
            # Empty state: chat list has no messages, empty state hero is visible
            self.assertIsNotNone(app.chat_messages_list)
            self.assertIsNotNone(app.workspace_empty_state)
            self.assertTrue(app.workspace_empty_state.visible)

    def test_welcome_screen_uses_simple_three_step_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            app.show_welcome_screen()

            strings = _collect_strings(page.controls[0])
            self.assertIn("Private AI workspace for the agentic web", strings)
            self.assertIn("Add Private Files", strings)
            self.assertIn("Open Investor Demo", strings)
            self.assertIn("Runs on this Mac", strings)
            self.assertIn("Works before cloud setup", strings)
            self.assertIn("Exposure stays under your approval", strings)
            self.assertIn("Add private files", strings)
            self.assertIn("Ask privately", strings)
            self.assertIn("Connect apps safely", strings)
            self.assertTrue(any("ChatGPT-like/MCP tools" in value for value in strings))

    def test_local_first_boot_does_not_require_auth_screen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            page = _FakePage()
            with patch.dict(
                os.environ,
                {
                    "HOME": tmpdir,
                    "ENCLAVE_LOCAL_FIRST": "1",
                    "ENCLAVE_REQUIRE_AUTH": "0",
                },
                clear=False,
            ):
                with patch("advanced_vault.gui.vault_app.AuthScreen", None):
                    with patch.object(VaultApp, "_enter_local_first_mode", autospec=True, return_value=None) as enter_local:
                        VaultApp(page)

            enter_local.assert_called_once()

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
            self.assertTrue(any("pitch.md" in value for value in strings))
            self.assertIn("1 file ready: pitch.md", strings)
            self.assertIn("Ask about your 1 file(s)...", strings)
            self.assertIn("Ask anything about your files", strings)

    def test_workspace_shell_fills_viewport(self) -> None:
        # The chat workspace pins its input bar to the bottom, so the shell
        # must fill the viewport (a plain expanding Container) rather than wrap
        # content in a scrollable ListView that would collapse it to the top.
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            app.show_landing_page()

            shell = page.controls[0]
            content_panel = shell.controls[1]
            self.assertIsInstance(content_panel, ft.Container)
            self.assertTrue(content_panel.expand)
            self.assertNotIsInstance(content_panel.content, ft.ListView)

    def test_scrollable_shell_uses_centered_list(self) -> None:
        # Long, top-anchored pages keep a scrollable ListView.
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            app._render_primary_shell(1, ft.Text("content"), fill=False)

            shell = page.controls[0]
            content_panel = shell.controls[1]
            self.assertIsInstance(content_panel.content, ft.ListView)
            self.assertTrue(content_panel.content.expand)

    def test_workspace_prompts_for_model_download_when_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            with patch.object(
                VaultApp,
                "_get_local_private_model_status",
                return_value={"available": False, "display_name": "Qwen2.5-1.5B-Instruct-4bit"},
            ):
                app.show_landing_page()

            strings = _collect_strings(page.controls[0])
            self.assertIn("Download local model", strings)
            self.assertIn("Download Model", strings)

    def test_connections_view_frames_enclave_as_control_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            app._show_connections_view()

            strings = _collect_strings(page.controls[0])
            self.assertIn("Connect AI Apps", strings)
            self.assertIn("Connect a New App", strings)
            self.assertIn("Investor Demo Flow", strings)
            self.assertIn("Common Agent Paths", strings)
            self.assertIn("Claude Desktop", strings)
            self.assertIn("ChatGPT-like / MCP tools", strings)
            self.assertIn("Browsers / ecommerce automations", strings)
            self.assertIn("Settings", strings)
            self.assertIn("Connect Claude Desktop", strings)
            self.assertIn("Connect Cursor", strings)
            self.assertIn("Copy for OpenClaw / other MCP apps", strings)
            self.assertTrue(any("Ready on this Mac" in value or "Connected" in value or "Not detected" in value for value in strings))
            self.assertTrue(any("ChatGPT-like/MCP tools" in value for value in strings))

    def test_protection_view_frames_exposure_control(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app, page = self._make_app(tmpdir)
            app._show_security_view()

            strings = _collect_strings(page.controls[0])
            self.assertIn("Protection", strings)
            self.assertIn("Exposure Summary", strings)
            self.assertIn("Protected Files", strings)
            self.assertIn("What Left Enclave", strings)
            self.assertIn("Ecommerce & Spend Guardrails", strings)

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
