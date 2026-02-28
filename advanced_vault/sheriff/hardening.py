"""Configuration hardening checks for AI agent integrations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


KNOWN_CONFIG_PATHS = [
    Path("~/Library/Application Support/Claude/claude_desktop_config.json").expanduser(),
    Path("~/.cursor/mcp.json").expanduser(),
    Path("~/.config/claude/claude_desktop_config.json").expanduser(),
]


class HardeningInspector:
    """Scans agent configuration files for direct filesystem access risks."""

    def inspect(self) -> List[Dict]:
        alerts: List[Dict] = []
        found_any = False

        for cfg_path in KNOWN_CONFIG_PATHS:
            if not cfg_path.exists():
                continue
            found_any = True
            try:
                payload = json.loads(cfg_path.read_text())
            except Exception:
                alerts.append(
                    {
                        "severity": "warning",
                        "path": str(cfg_path),
                        "message": "Configuration file exists but cannot be parsed as JSON.",
                    }
                )
                continue

            servers = payload.get("mcpServers", {})
            if "sheriff" not in servers:
                alerts.append(
                    {
                        "severity": "high",
                        "path": str(cfg_path),
                        "message": "No 'sheriff' MCP gateway found. Add sheriff server as mandatory broker.",
                    }
                )

            for name, server_cfg in servers.items():
                args = [str(a).lower() for a in server_cfg.get("args", [])]
                cmd = str(server_cfg.get("command", "")).lower()

                if "filesystem" in name.lower() or any("filesystem" in a for a in args):
                    alerts.append(
                        {
                            "severity": "critical",
                            "path": str(cfg_path),
                            "message": f"MCP server '{name}' appears to provide direct filesystem access.",
                        }
                    )

                if "advanced_vault.mcp_server" in " ".join(args) and "sheriff" not in name.lower():
                    alerts.append(
                        {
                            "severity": "warning",
                            "path": str(cfg_path),
                            "message": f"MCP server '{name}' uses legacy enclave server without explicit sheriff naming/hardening.",
                        }
                    )

                if cmd in {"python", "python3"} and any("os.system" in a for a in args):
                    alerts.append(
                        {
                            "severity": "high",
                            "path": str(cfg_path),
                            "message": f"MCP server '{name}' contains suspicious command arguments.",
                        }
                    )

        if not found_any:
            alerts.append(
                {
                    "severity": "info",
                    "path": "",
                    "message": "No known MCP config files found; hardening checks skipped.",
                }
            )

        return alerts
