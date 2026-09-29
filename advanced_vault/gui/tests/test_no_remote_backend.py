"""The desktop app makes no cloud-backend requests unless the user configures one.

ENCLAVE_BACKEND_URL used to default to a hard-coded Railway development
server, and several screens requested its /health endpoint. There is no
default any more: an unset or empty value (from the environment or from
~/.enclave/config.env) means "not configured", and nothing may touch the
network for the backend.

The config tests need no GUI dependencies; the VaultApp tests need flet and
use a fake page, so they run headless.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import socket
import tempfile
import types
import unittest
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from advanced_vault.gui import config_loader

BACKEND_KEY = "ENCLAVE_BACKEND_URL"
EXAMPLE_URL = "https://backend.example.test"
NOT_CONFIGURED_LABEL = "Cloud backend: not configured (local-only)"
HAS_FLET = importlib.util.find_spec("flet") is not None


@contextlib.contextmanager
def _isolated_home(config_env: str | None = None, **env: str) -> Iterator[str]:
    """Use a temporary HOME (optionally with ~/.enclave/config.env) and set env vars.

    ENCLAVE_BACKEND_URL is removed from the environment first, so each test
    starts from "nothing configured"; os.environ is restored on exit.
    """
    with tempfile.TemporaryDirectory() as home:
        if config_env is not None:
            config_path = Path(home) / ".enclave" / "config.env"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(config_env, encoding="utf-8")
        with patch.dict(os.environ, {"HOME": home}, clear=False):
            os.environ.pop(BACKEND_KEY, None)
            os.environ.update(env)
            yield home


@contextlib.contextmanager
def _network_forbidden(testcase: unittest.TestCase) -> Iterator[None]:
    """Fail the test if anything tries to reach the network.

    Each entry point raises if called. Because callers may swallow that
    exception, every mock is also checked after the block.
    """
    targets = [
        (requests.Session, "request"),
        (urllib.request, "urlopen"),
        (urllib.request.OpenerDirector, "open"),
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (socket, "create_connection"),
    ]
    if importlib.util.find_spec("httpx") is not None:
        import httpx

        targets += [(httpx.Client, "send"), (httpx.AsyncClient, "send")]

    with contextlib.ExitStack() as stack:
        mocks = {
            f"{getattr(owner, '__name__', owner)}.{name}": stack.enter_context(
                patch.object(
                    owner,
                    name,
                    MagicMock(side_effect=AssertionError(f"network call via {name}")),
                )
            )
            for owner, name in targets
        }
        yield
    for label, mock in mocks.items():
        testcase.assertFalse(mock.called, f"unexpected network call via {label}: {mock.call_args}")


class TestBackendUrlConfig(unittest.TestCase):
    """config_loader resolves the backend URL; unset or empty means not configured."""

    def test_no_remote_endpoint_is_built_in(self) -> None:
        self.assertEqual(config_loader.DEFAULT_CONFIG[BACKEND_KEY], "")
        for key, value in config_loader.DEFAULT_CONFIG.items():
            with self.subTest(key=key):
                self.assertNotIn("railway.app", value)

    def test_nothing_configured_means_no_backend(self) -> None:
        with _isolated_home():
            self.assertEqual(config_loader.get_config()[BACKEND_KEY], "")
            self.assertIsNone(config_loader.get_backend_url())

    def test_backend_is_optional_for_validation(self) -> None:
        with _isolated_home():
            _, missing = config_loader.validate_config()
        self.assertNotIn(BACKEND_KEY, missing)

    def test_environment_url_is_used(self) -> None:
        with _isolated_home(**{BACKEND_KEY: EXAMPLE_URL + "/"}):
            self.assertEqual(config_loader.get_backend_url(), EXAMPLE_URL)

    def test_config_file_url_is_used(self) -> None:
        with _isolated_home(config_env=f"{BACKEND_KEY}={EXAMPLE_URL}\n"):
            self.assertEqual(config_loader.get_backend_url(), EXAMPLE_URL)

    def test_empty_environment_variable_means_not_configured(self) -> None:
        with _isolated_home(**{BACKEND_KEY: ""}):
            self.assertIsNone(config_loader.get_backend_url())

    def test_empty_environment_variable_overrides_config_file(self) -> None:
        # The environment has the highest priority, including when it is empty.
        with _isolated_home(config_env=f"{BACKEND_KEY}={EXAMPLE_URL}\n", **{BACKEND_KEY: ""}):
            self.assertIsNone(config_loader.get_backend_url())

    def test_empty_config_file_line_means_not_configured(self) -> None:
        with _isolated_home(config_env=f"{BACKEND_KEY}=\n"):
            self.assertIsNone(config_loader.get_backend_url())

    def test_blank_value_means_not_configured(self) -> None:
        with _isolated_home(**{BACKEND_KEY: "   "}):
            self.assertIsNone(config_loader.get_backend_url())

    def test_apply_config_does_not_export_a_backend(self) -> None:
        with _isolated_home():
            config_loader.apply_config()
            self.assertIsNone(os.environ.get(BACKEND_KEY))

    def test_apply_config_keeps_an_empty_environment_variable(self) -> None:
        with _isolated_home(config_env=f"{BACKEND_KEY}={EXAMPLE_URL}\n", **{BACKEND_KEY: ""}):
            config_loader.apply_config()
            self.assertEqual(os.environ[BACKEND_KEY], "")


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


class _InlineThread:
    """Stand-in for threading.Thread that runs its target on start()."""

    def __init__(self, target=None, args=(), kwargs=None, **_ignored) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


@unittest.skipUnless(HAS_FLET, "flet is not installed")
class TestVaultAppBackendGating(unittest.TestCase):
    """VaultApp treats an unset backend as not configured and never contacts it."""

    vault_app: types.ModuleType

    @classmethod
    def setUpClass(cls) -> None:
        from advanced_vault.gui import vault_app

        cls.vault_app = vault_app

    def _bare_app(self, backend_url: str, vault_path: str | None = None):
        """A VaultApp with only the state the backend helpers read (no __init__)."""
        import flet as ft

        app = self.vault_app.VaultApp.__new__(self.vault_app.VaultApp)
        app.page = _FakePage()
        app.backend_url = backend_url
        app.backend_status = "unknown"
        app.last_check = None
        app.training_manager = None
        app.vault_path = Path(vault_path) if vault_path else None
        app.compute_pipeline_icon = ft.IconButton(
            icon=ft.Icons.SCIENCE_ROUNDED,
            tooltip="Compute Pipeline: Checking...",
        )
        return app

    def _construct_app(self):
        with patch.dict(os.environ, {"ENCLAVE_LOCAL_FIRST": "1", "ENCLAVE_REQUIRE_AUTH": "0"}):
            with patch.object(self.vault_app.VaultApp, "check_authentication", autospec=True):
                return self.vault_app.VaultApp(_FakePage())

    def test_startup_with_nothing_configured_leaves_backend_unset(self) -> None:
        with _isolated_home():
            # vault_app runs apply_config() at import; repeat it with this HOME.
            self.vault_app.apply_config()
            self.assertIsNone(os.environ.get(BACKEND_KEY))
            with _network_forbidden(self):
                app = self._construct_app()
        self.assertEqual(app.backend_url, "")

    def test_startup_uses_configured_backend(self) -> None:
        with _isolated_home(config_env=f"{BACKEND_KEY}={EXAMPLE_URL}/\n"):
            self.vault_app.apply_config()
            app = self._construct_app()
        self.assertEqual(app.backend_url, EXAMPLE_URL)

    def test_health_check_without_backend_makes_no_request(self) -> None:
        app = self._bare_app(backend_url="")
        with patch.object(self.vault_app, "threading", types.SimpleNamespace(Thread=_InlineThread)):
            with _network_forbidden(self):
                app.check_backend_connectivity()

        self.assertEqual(app.backend_status, "not_configured")
        self.assertEqual(app.compute_pipeline_icon.tooltip, NOT_CONFIGURED_LABEL)
        self.assertEqual(app.compute_pipeline_icon.icon_color, self.vault_app.LightTheme.TEXT_MUTED)

    def test_health_check_uses_configured_backend(self) -> None:
        app = self._bare_app(backend_url=EXAMPLE_URL)
        ok = MagicMock(status_code=200)
        with patch.object(self.vault_app, "threading", types.SimpleNamespace(Thread=_InlineThread)):
            with patch.object(self.vault_app.requests, "get", return_value=ok) as get:
                app.check_backend_connectivity()

        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], f"{EXAMPLE_URL}/health")
        self.assertEqual(app.backend_status, "connected")

    def test_advanced_screens_without_backend_make_no_request(self) -> None:
        # Settings -> Advanced (System Setup, Training Queue, Activity Log)
        # rebuilds this UI, which used to request the default backend's /health.
        with _isolated_home():
            app = self._construct_app()
            with patch.object(self.vault_app.VaultApp, "load_secrets", autospec=True):
                with patch.object(
                    self.vault_app, "threading", types.SimpleNamespace(Thread=_InlineThread)
                ):
                    with _network_forbidden(self):
                        app.build_ui()

        self.assertEqual(app.backend_status, "not_configured")
        self.assertEqual(app.compute_pipeline_icon.tooltip, NOT_CONFIGURED_LABEL)

    def _initialize_signed_in_vault(self, config_env: str | None = None):
        """Run initialize_vault for a cloud-signed-in user, with heavy services mocked."""
        with _isolated_home(config_env=config_env):
            app = self._construct_app()
            app.session_data = {"access_token": "token", "user": {"id": "user-1"}}
            with (
                patch.multiple(
                    self.vault_app,
                    HybridVault=MagicMock(),
                    FolderManager=MagicMock(),
                    QAGenerator=MagicMock(),
                    TrainingQueue=MagicMock(),
                    CloudSyncService=MagicMock(),
                    TrainingManager=MagicMock(),
                ),
                patch.object(app, "_ensure_private_model_profile"),
                patch.object(app, "_prewarm_private_model_session"),
                _network_forbidden(self),
            ):
                app.initialize_vault()
                return app, self.vault_app.CloudSyncService, self.vault_app.TrainingManager

    def test_signed_in_without_backend_creates_no_cloud_clients(self) -> None:
        app, cloud_sync_cls, training_manager_cls = self._initialize_signed_in_vault()

        cloud_sync_cls.assert_not_called()
        training_manager_cls.assert_not_called()
        self.assertIsNone(app.cloud_sync)
        self.assertIsNone(app.training_manager)

    def test_signed_in_with_backend_creates_cloud_clients(self) -> None:
        app, cloud_sync_cls, training_manager_cls = self._initialize_signed_in_vault(
            config_env=f"{BACKEND_KEY}={EXAMPLE_URL}\n"
        )

        self.assertEqual(cloud_sync_cls.call_args.kwargs["backend_url"], EXAMPLE_URL)
        self.assertEqual(training_manager_cls.call_args.kwargs["backend_url"], EXAMPLE_URL)
        self.assertIsNotNone(app.cloud_sync)
        self.assertIsNotNone(app.training_manager)

    def test_policies_view_without_backend_makes_no_request(self) -> None:
        import flet as ft

        app = self._bare_app(backend_url="")
        app.session_data = {"access_token": "token"}
        app.cloud_sync = None
        app.secrets_list = ft.Column()
        with _network_forbidden(self):
            app.show_langchain_policies()

        texts = [
            control.value
            for container in app.secrets_list.controls
            for control in container.content.controls
        ]
        self.assertIn(NOT_CONFIGURED_LABEL, texts)

    def test_adapter_download_without_backend_makes_no_request(self) -> None:
        with tempfile.TemporaryDirectory() as vault_path:
            app = self._bare_app(backend_url="", vault_path=vault_path)
            with _network_forbidden(self):
                self.assertIsNone(app._download_adapter_for_local("adapter-123"))


if __name__ == "__main__":
    unittest.main()
