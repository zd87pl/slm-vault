"""
MCP Server Setup Utilities.

Provides one-click setup for local MCP clients (Claude, Cursor) and
exposes readiness/status metadata for GUI wizard flows.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


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

    def _merge_mcp_servers(self, existing: Dict[str, Any], new_config: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(existing) if isinstance(existing, dict) else {}
        servers = merged.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
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
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
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
            config = self.generate_mcp_config()
            merged = self.merge_config(config, target=target)
            path = self._resolve_config_path(target)
            if self.write_config(merged, config_path=path, target=target):
                return {
                    "success": True,
                    "target": target,
                    "config_path": str(path) if path else None,
                    "message": f"{target.capitalize()} configured successfully.",
                }
            return {"success": False, "target": target, "error": "Failed to write MCP config file."}
        except Exception as e:
            logger.error(f"Auto-configure failed for {target}: {e}")
            return {"success": False, "target": target, "error": str(e)}

    def auto_configure_all_clients(self) -> Dict[str, Any]:
        results: Dict[str, Dict[str, Any]] = {}
        configured = 0

        if self.detect_claude_desktop():
            res = self.auto_configure(target="claude")
            results["claude"] = res
            if res.get("success"):
                configured += 1
        else:
            results["claude"] = {"success": False, "target": "claude", "error": "not_detected"}

        if self.detect_cursor():
            res = self.auto_configure(target="cursor")
            results["cursor"] = res
            if res.get("success"):
                configured += 1
        else:
            results["cursor"] = {"success": False, "target": "cursor", "error": "not_detected"}

        # Explicitly surfaced to avoid false promise in UX.
        results["chatgpt"] = {
            "success": False,
            "target": "chatgpt",
            "error": "unsupported_local_mcp",
        }

        return {
            "success": configured > 0,
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
