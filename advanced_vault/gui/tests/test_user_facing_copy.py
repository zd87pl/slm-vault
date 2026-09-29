"""Regression tests for user-facing GUI copy.

The app used to show investor-demo wording ("Open Investor Demo", "Investor
Demo Flow") and claimed to run "on this Mac" on every platform. These tests
read the localization table and the GUI sources directly, so they run without
flet installed.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from advanced_vault.gui.localization import STRINGS, SUPPORTED_LANGUAGES, get_text

GUI_DIR = Path(__file__).resolve().parents[1]

# Modules whose strings are shown on every platform. local_inference.py is left
# out on purpose: its "on this Mac" messages come from the MLX download path,
# which only runs on Apple Silicon.
PLATFORM_NEUTRAL_MODULES = ("demo_shell.py", "welcome_screen.py", "vault_app.py", "localization.py")

MAC_PATTERN = re.compile(r"\b(?:this Mac|tym Macu)\b")


def _string_constants(path: Path) -> list[str]:
    """Return every string literal in a module, including f-string parts and docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


class TestLocalizedCopy(unittest.TestCase):
    def test_no_investor_wording_in_any_language(self) -> None:
        for language, strings in STRINGS.items():
            for key, value in strings.items():
                with self.subTest(language=language, key=key):
                    self.assertNotIn("investor", value.lower())
                    self.assertNotIn("inwestor", value.lower())

    def test_no_language_claims_to_run_on_a_mac(self) -> None:
        for language, strings in STRINGS.items():
            for key, value in strings.items():
                with self.subTest(language=language, key=key):
                    self.assertIsNone(MAC_PATTERN.search(value))

    def test_onboarding_copy_is_platform_neutral(self) -> None:
        self.assertEqual(get_text("en", "onboarding.trust.local"), "Runs on this computer")
        self.assertEqual(get_text("pl", "onboarding.trust.local"), "Lokalnie na tym komputerze")
        self.assertEqual(get_text("en", "onboarding.add_sample"), "Open Sample Workspace")
        self.assertEqual(
            get_text("en", "onboarding.success.sample", count=4),
            "Sample workspace ready with 4 files. Ask: What blocks autonomous spending above $75?",
        )

    def test_settings_name_the_cipher_the_vault_uses(self) -> None:
        # The local vault uses ChaCha20-Poly1305 with a 96-bit nonce
        # (encrypted_kv/storage.py, training/rag_index.py), not XChaCha20.
        for language in SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                text = get_text(language, "settings.encryption.algorithm")
                self.assertIn("ChaCha20-Poly1305", text)
                self.assertNotIn("XChaCha20", text)

    def test_changed_keys_exist_in_every_language(self) -> None:
        keys = (
            "onboarding.trust.local",
            "local_model.download.required",
            "onboarding.add_sample",
            "settings.encryption.algorithm",
        )
        for language in SUPPORTED_LANGUAGES:
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, STRINGS[language])


class TestGuiSourceCopy(unittest.TestCase):
    def test_gui_modules_have_no_investor_wording(self) -> None:
        offenders = [
            (path.name, value)
            for path in sorted(GUI_DIR.glob("*.py"))
            for value in _string_constants(path)
            if "investor" in value.lower()
        ]
        self.assertEqual(offenders, [])

    def test_shared_shell_does_not_claim_to_run_on_a_mac(self) -> None:
        offenders = [
            (name, value)
            for name in PLATFORM_NEUTRAL_MODULES
            for value in _string_constants(GUI_DIR / name)
            if MAC_PATTERN.search(value)
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
