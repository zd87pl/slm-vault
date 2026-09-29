"""
MCP Server Setup Utilities.

Provides one-click setup for local MCP clients (Claude, Cursor) and
exposes readiness/status metadata for GUI wizard flows.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class MCPConfigError(Exception):
    """An existing MCP client config cannot be safely updated."""


class MCPSetupHelper:
    """Helper for setting up local MCP server integration."""

    SERVER_NAME = "enclave"
    LEGACY_SERVER_NAMES = ("sheriff", "personal-vault")

    def __init__(self, vault_path: str = "~/.vault"):
        self.vault_path = Path(vault_path).expanduser()
        self.system = platform.system()
        self._test_cache: Optional[Tuple[bool, str]] = None
        self._test_cache_time: Optional[float] = None

    # ---------- Paths & Detection ----------

    def get_claude_desktop_config_path(self) -> Optional[Path]:
        if self.system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if self.system == "Windows":
            appdata = os.getenv("APPDATA")
            return Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
        if self.system == "Linux":
            return Path.home() / ".config" / "claude" / "claude_desktop_config.json"
        return None

    def get_cursor_config_path(self) -> Optional[Path]:
        if self.system in {"Darwin", "Linux"}:
            return Path.home() / ".cursor" / "mcp.json"
        if self.system == "Windows":
            user_profile = os.getenv("USERPROFILE")
            return Path(user_profile) / ".cursor" / "mcp.json" if user_profile else None
        return None

    def _claude_app_exists(self) -> bool:
        if self.system == "Darwin":
            return Path("/Applications/Claude.app").exists()
        if self.system == "Windows":
            local_app_data = os.getenv("LOCALAPPDATA")
            if not local_app_data:
                return False
            candidates = [
                Path(local_app_data) / "Claude" / "Claude.exe",
                Path(local_app_data) / "Programs" / "Claude" / "Claude.exe",
            ]
            return any(path.exists() for path in candidates)
        return False

    def _cursor_app_exists(self) -> bool:
        if self.system == "Darwin":
            return Path("/Applications/Cursor.app").exists()
        if self.system == "Windows":
            local_app_data = os.getenv("LOCALAPPDATA")
            if not local_app_data:
                return False
            candidates = [
                Path(local_app_data) / "Programs" / "Cursor" / "Cursor.exe",
                Path(local_app_data) / "Cursor" / "Cursor.exe",
            ]
            return any(path.exists() for path in candidates)
        if self.system == "Linux":
            try:
                result = subprocess.run(
                    ["which", "cursor"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return result.returncode == 0 and bool(result.stdout.strip())
            except Exception:
                return False
        return False

    def detect_claude_desktop(self) -> bool:
        path = self.get_claude_desktop_config_path()
        return bool((path and path.exists()) or self._claude_app_exists())

    def detect_cursor(self) -> bool:
        path = self.get_cursor_config_path()
        return bool((path and path.exists()) or self._cursor_app_exists())

    def detect_chatgpt_desktop(self) -> bool:
        # Detection only. Local MCP setup for ChatGPT desktop is currently unsupported.
        if self.system == "Darwin":
            return Path("/Applications/ChatGPT.app").exists()
        if self.system == "Windows":
            local_app_data = os.getenv("LOCALAPPDATA")
            if not local_app_data:
                return False
            candidates = [
                Path(local_app_data) / "Programs" / "ChatGPT" / "ChatGPT.exe",
                Path(local_app_data) / "ChatGPT" / "ChatGPT.exe",
            ]
            return any(path.exists() for path in candidates)
        return False

    # ---------- Config Generation ----------

    def get_python_path(self) -> str:
        import sys

        # Prefer the interpreter we are running in — it is the one that has
        # advanced_vault and its dependencies installed (typically the venv
        # created by setup.sh). A frozen app bundle can't be used this way,
        # so fall back to system pythons in that case.
        if not getattr(sys, "frozen", False) and sys.executable:
            return sys.executable

        homebrew_python = "/opt/homebrew/bin/python3"
        if Path(homebrew_python).exists():
            return homebrew_python

        homebrew_intel = "/usr/local/bin/python3"
        if Path(homebrew_intel).exists():
            return homebrew_intel

        for exe in ("python3", "python"):
            try:
                result = subprocess.run(
                    ["which", exe],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    python_path = result.stdout.strip()
                    lowered = python_path.lower()
                    if "miniconda" not in lowered and "conda" not in lowered:
                        return python_path
            except Exception:
                pass

        return "python3"

    def get_project_root(self) -> Path:
        current = Path(__file__).resolve()
        while current != current.parent:
            if (current / "advanced_vault" / "mcp_server").exists():
                return current
            current = current.parent

        try:
            import sys

            for path in sys.path:
                p = Path(path)
                if (p / "advanced_vault" / "mcp_server").exists():
                    return p
        except Exception:
            pass

        return Path.cwd()

    def generate_mcp_server_entry(self) -> Dict[str, Any]:
        return {
            "command": self.get_python_path(),
            "args": ["-m", "advanced_vault.mcp_server"],
            "env": {
                "VAULT_PATH": str(self.vault_path),
                "PYTHONPATH": str(self.get_project_root()),
            },
        }

    def generate_mcp_config(self) -> Dict[str, Any]:
        return {"mcpServers": {self.SERVER_NAME: self.generate_mcp_server_entry()}}

    # ---------- Config I/O ----------

    def _resolve_config_path(self, target: str = "claude") -> Optional[Path]:
        if target == "claude":
            return self.get_claude_desktop_config_path()
        if target == "cursor":
            return self.get_cursor_config_path()
        return None

    def _load_config_at_path(self, config_path: Optional[Path]) -> Optional[Dict[str, Any]]:
        if not config_path or not config_path.exists():
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config at {config_path}: {e}")
            return None

    @staticmethod
    def _config_error(config_path: Path, problem: str) -> MCPConfigError:
        return MCPConfigError(
            f"Refusing to modify {config_path}: {problem}. Nothing was written. "
            "Fix or move that file, then try again."
        )

    def _read_config_for_update(self, config_path: Path) -> Optional[Dict[str, Any]]:
        """Strictly load a config that is about to be modified.

        Returns None if the file does not exist. Raises MCPConfigError if it
        exists but is unreadable or not a JSON object, so a config we cannot
        fully understand is never replaced.
        """
        try:
            raw = config_path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as e:
            raise self._config_error(config_path, f"it could not be read ({e})") from e
        try:
            config = json.loads(raw.decode("utf-8-sig"))
        except ValueError as e:
            raise self._config_error(config_path, f"it is not valid JSON ({e})") from e
        if not isinstance(config, dict):
            raise self._config_error(config_path, "its top level is not a JSON object")
        servers = config.get("mcpServers")
        if servers is not None and not isinstance(servers, dict):
            raise self._config_error(config_path, '"mcpServers" is not a JSON object')
        return config

    @staticmethod
    def _backup_config_file(config_path: Path) -> Path:
        """Copy config_path to a timestamped sibling and return its path."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = config_path.with_name(f"{config_path.name}.bak-{stamp}")
        counter = 1
        while backup.exists():
            backup = config_path.with_name(f"{config_path.name}.bak-{stamp}-{counter}")
            counter += 1
        shutil.copy2(config_path, backup)
        return backup

    def _replace_config_file(self, config_path: Path, config: Dict[str, Any]) -> Optional[Path]:
        """Back up config_path (if present), then atomically replace it.

        The new file is written to a temp file in the same directory and moved
        into place with os.replace, keeping the original file mode. Returns the
        backup path, or None if there was no previous file.
        """
        payload = (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.is_symlink():
            # Update the file a (dotfiles-style) symlink points at, not the link.
            config_path = Path(os.path.realpath(config_path))

        backup = None
        mode = None
        if config_path.exists():
            # os.replace would bypass a read-only file's permissions; honour them.
            if not os.access(config_path, os.W_OK):
                raise self._config_error(config_path, "it is not writable")
            mode = stat.S_IMODE(config_path.stat().st_mode)
            backup = self._backup_config_file(config_path)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{config_path.name}.", suffix=".tmp", dir=str(config_path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            if mode is not None:
                os.chmod(tmp_name, mode)
            os.replace(tmp_name, config_path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
        return backup

    def _install_into_config(self, config_path: Path) -> Dict[str, Any]:
        """Add or update Enclave's server entry in the client config at config_path.

        All other top-level keys and servers are preserved. Nothing is written
        when the entry is already up to date. Raises MCPConfigError, without
        touching the file, if the existing config cannot be parsed or is not
        writable.
        """
        existing = self._read_config_for_update(config_path)
        merged = self._merge_mcp_servers(existing or {}, self.generate_mcp_config())
        if merged == existing:
            return {"changed": False, "backup_path": None}
        backup = self._replace_config_file(config_path, merged)
        logger.info(f"Wrote MCP config to {config_path}")
        return {"changed": True, "backup_path": str(backup) if backup else None}

    def _merge_mcp_servers(self, existing: Dict[str, Any], new_config: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(existing) if isinstance(existing, dict) else {}
        servers = merged.get("mcpServers")
        # Copy so the caller's config is not mutated (and can be compared).
        servers = dict(servers) if isinstance(servers, dict) else {}
        merged["mcpServers"] = servers

        for legacy_name in self.LEGACY_SERVER_NAMES:
            if legacy_name in servers:
                servers.pop(legacy_name, None)

        servers[self.SERVER_NAME] = new_config["mcpServers"][self.SERVER_NAME]
        return merged

    # Backward-compatible methods (default target=claude)
    def load_existing_config(self, target: str = "claude") -> Optional[Dict[str, Any]]:
        return self._load_config_at_path(self._resolve_config_path(target))

    def merge_config(self, new_config: Dict[str, Any], target: str = "claude") -> Dict[str, Any]:
        existing = self.load_existing_config(target=target)
        if existing is None:
            return new_config
        return self._merge_mcp_servers(existing, new_config)

    def write_config(
        self,
        config: Dict[str, Any],
        config_path: Optional[Path] = None,
        target: str = "claude",
    ) -> bool:
        path = config_path or self._resolve_config_path(target)
        if not path:
            return False
        try:
            backup = self._replace_config_file(path, config)
            if backup:
                logger.info(f"Backed up previous MCP config to {backup}")
            logger.info(f"Wrote MCP config to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write config to {path}: {e}")
            return False

    # ---------- Configuration Actions ----------

    def auto_configure(self, target: str = "claude") -> Dict[str, Any]:
        if target == "chatgpt":
            return {
                "success": False,
                "target": "chatgpt",
                "error": "Local MCP setup for ChatGPT is not supported.",
            }

        if target == "claude" and not self.detect_claude_desktop():
            return {"success": False, "target": "claude", "error": "Claude Desktop not detected."}

        if target == "cursor" and not self.detect_cursor():
            return {"success": False, "target": "cursor", "error": "Cursor not detected."}

        try:
            path = self._resolve_config_path(target)
            if not path:
                return {"success": False, "target": target, "error": "Failed to write MCP config file."}
            outcome = self._install_into_config(path)
            return {
                "success": True,
                "target": target,
                "config_path": str(path),
                "backup_path": outcome["backup_path"],
                "changed": outcome["changed"],
                "message": (
                    f"{target.capitalize()} configured successfully."
                    if outcome["changed"]
                    else f"{target.capitalize()} was already configured; nothing changed."
                ),
            }
        except MCPConfigError as e:
            # The caller shows this message to the user; don't print it twice.
            logger.info(str(e))
            return {"success": False, "target": target, "error": str(e)}
        except Exception as e:
            logger.error(f"Auto-configure failed for {target}: {e}")
            return {"success": False, "target": target, "error": f"Failed to write MCP config file: {e}"}

    def auto_configure_all_clients(self) -> Dict[str, Any]:
        results: Dict[str, Dict[str, Any]] = {}
        configured = 0
        failed = 0

        if self.detect_claude_desktop():
            res = self.auto_configure(target="claude")
            results["claude"] = res
            if res.get("success"):
                configured += 1
            else:
                failed += 1
        else:
            results["claude"] = {"success": False, "target": "claude", "error": "not_detected"}

        if self.detect_cursor():
            res = self.auto_configure(target="cursor")
            results["cursor"] = res
            if res.get("success"):
                configured += 1
            else:
                failed += 1
        else:
            results["cursor"] = {"success": False, "target": "cursor", "error": "not_detected"}

        # Explicitly surfaced to avoid false promise in UX.
        results["chatgpt"] = {
            "success": False,
            "target": "chatgpt",
            "error": "unsupported_local_mcp",
        }

        return {
            # A detected client we could not configure (e.g. its config was
            # refused as unparseable) is a failure the user must act on.
            "success": configured > 0 and failed == 0,
            "configured_count": configured,
            "results": results,
        }

    # ---------- Status ----------

    def _is_target_configured(self, target: str) -> bool:
        cfg = self.load_existing_config(target=target)
        if not cfg or "mcpServers" not in cfg or not isinstance(cfg["mcpServers"], dict):
            return False
        servers = cfg["mcpServers"]
        return bool(
            self.SERVER_NAME in servers
            or any(legacy in servers for legacy in self.LEGACY_SERVER_NAMES)
        )

    def test_mcp_server(self, use_cache: bool = True) -> Tuple[bool, str]:
        if use_cache and self._test_cache is not None and self._test_cache_time is not None:
            if time.time() - self._test_cache_time < 30:
                return self._test_cache

        try:
            import sys

            project_root = self.get_project_root()
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from advanced_vault.mcp_server import create_vault_server

            server = create_vault_server(str(self.vault_path))
            result = (
                (True, "MCP server initialized successfully")
                if hasattr(server, "server")
                else (False, "MCP server missing server attribute")
            )
        except ImportError as e:
            result = (False, f"Import error: {e}")
        except Exception as e:
            result = (False, f"Error: {e}")

        self._test_cache = result
        self._test_cache_time = time.time()
        return result

    def get_setup_status(self) -> Dict[str, Any]:
        claude_installed = self.detect_claude_desktop()
        cursor_installed = self.detect_cursor()
        chatgpt_installed = self.detect_chatgpt_desktop()

        claude_path = self.get_claude_desktop_config_path()
        cursor_path = self.get_cursor_config_path()
        claude_configured = self._is_target_configured("claude")
        cursor_configured = self._is_target_configured("cursor")

        test_success, test_message = self.test_mcp_server(use_cache=True)
        any_configured = claude_configured or cursor_configured

        return {
            # Backward-compatible fields.
            "claude_installed": claude_installed,
            "config_path": str(claude_path) if claude_path else None,
            "config_exists": bool(claude_path and claude_path.exists()),
            "mcp_configured": any_configured,
            # Extended fields.
            "cursor_installed": cursor_installed,
            "chatgpt_installed": chatgpt_installed,
            "claude_mcp_configured": claude_configured,
            "cursor_mcp_configured": cursor_configured,
            "chatgpt_mcp_configured": False,
            "chatgpt_local_mcp_supported": False,
            "chatgpt_support_message": "Local MCP setup for ChatGPT is not supported.",
            "clients": {
                "claude": {
                    "installed": claude_installed,
                    "configured": claude_configured,
                    "config_path": str(claude_path) if claude_path else None,
                },
                "cursor": {
                    "installed": cursor_installed,
                    "configured": cursor_configured,
                    "config_path": str(cursor_path) if cursor_path else None,
                },
                "chatgpt": {
                    "installed": chatgpt_installed,
                    "configured": False,
                    "config_path": None,
                    "supported_local_mcp": False,
                },
            },
            "test_success": test_success,
            "test_message": test_message,
            "vault_path": str(self.vault_path),
            "python_path": self.get_python_path(),
        }

    def get_config_json(self) -> str:
        return json.dumps(self.generate_mcp_config(), indent=2)

    def get_merged_config_json(self, target: str = "claude") -> str:
        new_config = self.generate_mcp_config()
        merged = self.merge_config(new_config, target=target)
        return json.dumps(merged, indent=2)
