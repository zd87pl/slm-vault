"""The desktop app never installs Ollama and pulls Ollama models only when asked.

On machines without Apple Silicon, setting up PDF extraction used to fetch
https://ollama.com/install.sh and pipe it to sh (or run `brew install ollama`
on Intel Macs), then pull llama3.2-vision:11b, with no prompt. That happened on
automatic paths (picking a PDF, Train Model) and from Settings. Now:

- Ollama is never installed; the user gets instructions instead.
- A model is pulled only after the user confirms a prompt that names it and
  its approximate size.
- Detection (is Ollama running, is the model present) talks to localhost only.

Every test pretends to run on Linux so the same code path runs on any CI OS.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import subprocess
import types
import unittest
from collections.abc import Iterator
from unittest.mock import patch

import requests

from advanced_vault.gui.ollama_setup import OllamaSetup, ollama_download_prompt

HAS_FLET = importlib.util.find_spec("flet") is not None
OCR_MODEL = "llama3.2-vision:11b"
QA_MODEL = "tinyllama"


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, lines=()) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self._lines = list(lines)
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def iter_lines(self):
        return iter(self._lines)


class _World:
    """Records subprocesses and HTTP requests; fakes a local Ollama server."""

    def __init__(self, installed: bool, running: bool) -> None:
        self.installed = installed
        self.running = running
        self.models: list[str] = []
        self.commands: list = []
        self.requests: list[tuple[str, str]] = []

    @property
    def pulls(self) -> list[tuple[str, str]]:
        return [(m, u) for m, u in self.requests if u.endswith("/api/pull")]

    def which(self, name, *args, **kwargs):
        return "/usr/local/bin/ollama" if (name == "ollama" and self.installed) else None

    def run(self, cmd, *args, **kwargs):
        self.commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="blocked by test")

    def popen(self, cmd, *args, **kwargs):
        self.commands.append(cmd)
        raise OSError("blocked by test")

    def request(self, method, url, **kwargs):
        # Patched onto requests.Session as a bound method, so no session argument.
        self.requests.append((method.upper(), url))
        if not url.startswith("http://localhost:11434/") or not self.running:
            raise requests.ConnectionError(f"blocked by test: {url}")
        if url.endswith("/api/tags"):
            return _FakeResponse(payload={"models": [{"name": m} for m in self.models]})
        if url.endswith("/api/pull"):
            self.models.append(kwargs["json"]["name"])
            return _FakeResponse(lines=[b'{"status": "success"}'])
        raise requests.ConnectionError(f"unexpected request in test: {method} {url}")


@contextlib.contextmanager
def _fake_world(installed: bool = False, running: bool = False) -> Iterator[_World]:
    world = _World(installed=installed, running=running)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("platform.system", return_value="Linux"))
        stack.enter_context(patch("platform.machine", return_value="x86_64"))
        stack.enter_context(patch("shutil.which", world.which))
        stack.enter_context(patch("subprocess.run", world.run))
        stack.enter_context(patch("subprocess.Popen", world.popen))
        stack.enter_context(patch("subprocess.call", world.run))
        stack.enter_context(patch("subprocess.check_call", world.run))
        stack.enter_context(patch("subprocess.check_output", world.run))
        stack.enter_context(patch("os.system", world.run))
        stack.enter_context(patch.object(requests.Session, "request", world.request))
        stack.enter_context(patch("time.sleep"))
        stack.enter_context(
            patch.dict(
                os.environ,
                {"ENCLAVE_LITEPARSE_ALLOW_NPX": "false", "ENCLAVE_LITEPARSE_AUTO_INSTALL": "false"},
            )
        )
        yield world


class _NoInstallAssertions(unittest.TestCase):
    def assert_nothing_installed_or_pulled(self, world: _World) -> None:
        self.assertEqual(world.commands, [], "no subprocess may run (no curl, brew, sh, ollama)")
        self.assertEqual(world.pulls, [], "no Ollama model may be pulled")
        for method, url in world.requests:
            self.assertEqual(method, "GET")
            self.assertTrue(url.startswith("http://localhost:11434/"), url)


class TestOllamaSetup(_NoInstallAssertions):
    """OllamaSetup detects Ollama but never installs it or pulls unasked."""

    def test_missing_ollama_gets_instructions_not_an_installer(self) -> None:
        with _fake_world(installed=False) as world:
            ok, message = OllamaSetup().setup_ollama()
        self.assertFalse(ok)
        self.assertIn("https://ollama.com", message)
        self.assertIn(f"ollama pull {OCR_MODEL}", message)
        self.assert_nothing_installed_or_pulled(world)

    def test_missing_ollama_on_intel_mac_does_not_use_homebrew(self) -> None:
        with _fake_world(installed=False) as world:
            with patch("platform.system", return_value="Darwin"):
                ok, _ = OllamaSetup().setup_ollama(confirmed_download=True)
        self.assertFalse(ok)
        self.assert_nothing_installed_or_pulled(world)

    def test_missing_model_is_not_pulled_without_confirmation(self) -> None:
        with _fake_world(installed=True, running=True) as world:
            setup = OllamaSetup()
            ok, message = setup.setup_ollama()
            self.assertFalse(setup.download_model())
        self.assertFalse(ok)
        self.assertIn(f"ollama pull {OCR_MODEL}", message)
        self.assertIn("about 8 GB", message)
        self.assert_nothing_installed_or_pulled(world)

    def test_confirmed_download_pulls_the_model(self) -> None:
        with _fake_world(installed=True, running=True) as world:
            ok, _ = OllamaSetup().setup_ollama(confirmed_download=True)
        self.assertTrue(ok)
        self.assertEqual(world.pulls, [("POST", "http://localhost:11434/api/pull")])
        self.assertEqual(world.models, [OCR_MODEL])
        self.assertEqual(world.commands, [])

    def test_download_prompt_names_model_and_size(self) -> None:
        prompt = ollama_download_prompt(OCR_MODEL, "scanned-PDF OCR")
        self.assertIn(OCR_MODEL, prompt)
        self.assertIn("about 8 GB", prompt)
        self.assertIn("about 640 MB", ollama_download_prompt(QA_MODEL, "Q&A"))


class TestPdfProcessorAutoSetup(_NoInstallAssertions):
    """PDFProcessor(auto_setup=True) only detects Ollama."""

    def test_auto_setup_without_ollama_installs_nothing(self) -> None:
        from advanced_vault.gui.pdf_processor import PDFProcessor

        with _fake_world(installed=False) as world:
            processor = PDFProcessor(auto_setup=True)
            text = processor._extract_text_with_ollama_ocr("missing.pdf")
        self.assertFalse(processor.has_document_extraction_backend())
        self.assertEqual(text, "")
        self.assert_nothing_installed_or_pulled(world)

    def test_auto_setup_with_ollama_but_no_model_pulls_nothing(self) -> None:
        from advanced_vault.gui.pdf_processor import PDFProcessor

        with _fake_world(installed=True, running=True) as world:
            processor = PDFProcessor(auto_setup=True)
        self.assertFalse(processor.ollama_available)
        self.assert_nothing_installed_or_pulled(world)


class TestQAGeneratorSetup(_NoInstallAssertions):
    """The Q&A model (Ollama fallback) is pulled only after confirmation."""

    def _generator(self):
        from advanced_vault.gui.qa_generator import QAGenerator

        generator = QAGenerator()
        generator.mlx_available = False
        return generator

    def test_missing_model_is_not_pulled_without_confirmation(self) -> None:
        with _fake_world(installed=True, running=True) as world:
            generator = self._generator()
            self.assertTrue(generator.needs_ollama_download())
            ok, message = generator.setup_qa_model()
        self.assertFalse(ok)
        self.assertIn(f"ollama pull {QA_MODEL}", message)
        self.assert_nothing_installed_or_pulled(world)

    def test_confirmed_download_pulls_the_model(self) -> None:
        with _fake_world(installed=True, running=True) as world:
            ok, _ = self._generator().setup_qa_model(confirmed_download=True)
        self.assertTrue(ok)
        self.assertEqual(len(world.pulls), 1)
        self.assertEqual(world.models, [QA_MODEL])


def _dialog_text(control) -> str:
    """All text in a dialog (title, content and nested controls)."""
    parts = []
    if type(control).__name__ == "Text" and isinstance(control.value, str):
        parts.append(control.value)
    for attr in ("title", "content"):
        child = getattr(control, attr, None)
        if child is not None and not isinstance(child, str):
            parts.append(_dialog_text(child))
    for child in getattr(control, "controls", None) or []:
        parts.append(_dialog_text(child))
    return "\n".join(part for part in parts if part)


@unittest.skipUnless(HAS_FLET, "flet is not installed")
class TestVaultAppOllamaFlows(_NoInstallAssertions):
    """The GUI shows instructions or asks first; it never installs anything."""

    @classmethod
    def setUpClass(cls) -> None:
        from advanced_vault.gui import vault_app

        cls.vault_app = vault_app

    def setUp(self) -> None:
        from advanced_vault.gui.tests.test_no_remote_backend import _FakePage, _isolated_home

        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(_isolated_home())
        stack.enter_context(
            patch.dict(os.environ, {"ENCLAVE_LOCAL_FIRST": "1", "ENCLAVE_REQUIRE_AUTH": "0"})
        )
        with patch.object(self.vault_app.VaultApp, "check_authentication", autospec=True):
            self.app = self.vault_app.VaultApp(_FakePage())
        self.page = self.app.page

    def _dialogs(self) -> list:
        import flet as ft

        return [c for c in self.page.overlay if isinstance(c, ft.AlertDialog)]

    def _click(self, dialog, label: str) -> None:
        button = next(a for a in dialog.actions if getattr(a, "text", None) == label)
        button.on_click(None)

    def test_picking_a_pdf_without_ollama_installs_nothing(self) -> None:
        # _initialize_pdf_processor runs when a PDF is picked, on Train Model,
        # and from Settings -> Run Local Setup.
        with _fake_world(installed=False) as world:
            self.app._initialize_pdf_processor()

        self.assert_nothing_installed_or_pulled(world)
        self.assertFalse(self.app.pdf_processor.has_document_extraction_backend())
        [dialog] = self._dialogs()
        self.assertTrue(dialog.open)
        self.assertIn("https://ollama.com", _dialog_text(dialog))

    def test_run_local_setup_without_ollama_shows_instructions(self) -> None:
        self.app.qa_generator = types.SimpleNamespace(
            get_qa_status=lambda: {"mlx_available": False, "qa_model_available": True}
        )
        with _fake_world(installed=False) as world:
            self.app._run_local_setup()

        self.assert_nothing_installed_or_pulled(world)
        instructions = self._dialogs()[-1]
        self.assertTrue(instructions.open)
        self.assertIn("https://ollama.com", _dialog_text(instructions))

    def test_ocr_model_is_pulled_only_after_confirmation(self) -> None:
        with _fake_world(installed=True, running=True) as world:
            self.app.pdf_processor = types.SimpleNamespace(
                ollama_setup=OllamaSetup(),
                ollama_available=False,
                _test_ollama_connection=lambda: True,
            )
            self.app._setup_ollama_with_progress()

            [prompt] = self._dialogs()
            self.assertIn(OCR_MODEL, _dialog_text(prompt))
            self.assertIn("about 8 GB", _dialog_text(prompt))
            self.assert_nothing_installed_or_pulled(world)

            self._click(prompt, "Download")

        self.assertEqual(len(world.pulls), 1)
        self.assertEqual(world.models, [OCR_MODEL])
        self.assertEqual(world.commands, [])

    def test_ocr_download_can_be_declined(self) -> None:
        with _fake_world(installed=True, running=True) as world:
            self.app.pdf_processor = types.SimpleNamespace(ollama_setup=OllamaSetup())
            self.app._setup_ollama_with_progress()
            [prompt] = self._dialogs()
            self._click(prompt, "Cancel")

        self.assertFalse(prompt.open)
        self.assert_nothing_installed_or_pulled(world)

    def test_qa_model_is_pulled_only_after_confirmation(self) -> None:
        from advanced_vault.gui.qa_generator import QAGenerator

        with _fake_world(installed=True, running=True) as world:
            self.app.qa_generator = QAGenerator()
            self.app.qa_generator.mlx_available = False
            self.app._setup_qa_model_with_progress()

            [prompt] = self._dialogs()
            self.assertIn(QA_MODEL, _dialog_text(prompt))
            self.assertIn("about 640 MB", _dialog_text(prompt))
            self.assert_nothing_installed_or_pulled(world)

            self._click(prompt, "Download")

        self.assertEqual(len(world.pulls), 1)
        self.assertEqual(world.models, [QA_MODEL])


if __name__ == "__main__":
    unittest.main()
