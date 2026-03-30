"""Human-editable TOML config loader for the shared Enclave policy plane."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore

from .models import AgentPolicy, KillSwitchState, utcnow_iso


DEFAULT_POLICY_TOML = """# Enclave control-plane policy configuration
# This file is human-editable and acts as the source of truth for shared Vault + Wallet policy.

[kill_switch]
enabled = false
reason = ""
updated_at = ""

[[agents]]
agent_id = "default"
trust_level = "standard"
allowed_modules = ["vault"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "vault_*", "sheriff.*"]
vault_scopes = ["*"]
wallet_scopes = []
wallet_auto_approve_below = 0.0
wallet_prompt_above = 0.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "local-ui"
trust_level = "operator"
allowed_modules = ["vault", "wallet", "security"]
allowed_tools = ["*"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 100.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "vault-cli"
trust_level = "operator"
allowed_modules = ["vault", "wallet", "security"]
allowed_tools = ["*"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 100.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "claude-desktop"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "cursor"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "openclaw"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23
"""


@dataclass
class EnclavePolicyDocument:
    """Parsed policy document from the operator-facing TOML config."""

    kill_switch: KillSwitchState
    agents: Dict[str, AgentPolicy]


class EnclavePolicyConfig:
    """Load and persist `~/.enclave/policies.toml`."""

    def __init__(self, path: str = "~/.enclave/policies.toml"):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_exists()

    def ensure_exists(self) -> None:
        """Create a sensible default policy file when missing."""
        if self.path.exists():
            return
        self.path.write_text(DEFAULT_POLICY_TOML, encoding="utf-8")

    def load(self) -> EnclavePolicyDocument:
        """Parse the TOML file into strongly-typed runtime structures."""
        payload = tomllib.loads(self.path.read_text(encoding="utf-8"))
        kill_switch_payload = dict(payload.get("kill_switch", {}))
        kill_switch = KillSwitchState(
            enabled=bool(kill_switch_payload.get("enabled", False)),
            reason=str(kill_switch_payload.get("reason", "")),
            updated_at=str(kill_switch_payload.get("updated_at") or utcnow_iso()),
        )

        agents: Dict[str, AgentPolicy] = {}
        for raw_agent in payload.get("agents", []):
            policy = AgentPolicy(
                agent_id=str(raw_agent.get("agent_id", "default")),
                trust_level=str(raw_agent.get("trust_level", "standard")),
                allowed_modules=list(raw_agent.get("allowed_modules", ["vault"])),
                allowed_tools=list(raw_agent.get("allowed_tools", ["*"])),
                vault_scopes=list(raw_agent.get("vault_scopes", ["*"])),
                wallet_scopes=list(raw_agent.get("wallet_scopes", ["*"])),
                wallet_auto_approve_below=float(raw_agent.get("wallet_auto_approve_below", 25.0)),
                wallet_prompt_above=float(raw_agent.get("wallet_prompt_above", 100.0)),
                start_hour=int(raw_agent.get("start_hour", 0)),
                end_hour=int(raw_agent.get("end_hour", 23)),
                metadata=dict(raw_agent.get("metadata", {})),
            )
            agents[policy.agent_id] = policy

        if "default" not in agents:
            agents["default"] = AgentPolicy(agent_id="default")
        return EnclavePolicyDocument(kill_switch=kill_switch, agents=agents)

    def save_kill_switch(self, state: KillSwitchState) -> None:
        """Persist kill-switch state while leaving the rest of the file intact."""
        document = self.path.read_text(encoding="utf-8")
        lines = document.splitlines()
        new_lines = []
        in_block = False
        replaced_enabled = False
        replaced_reason = False
        replaced_updated_at = False
        reason_value = json.dumps(state.reason)
        updated_value = json.dumps(state.updated_at)

        for line in lines:
            stripped = line.strip()
            if stripped == "[kill_switch]":
                in_block = True
                new_lines.append(line)
                continue
            if in_block and stripped.startswith("[") and stripped != "[kill_switch]":
                if not replaced_enabled:
                    new_lines.append(f"enabled = {'true' if state.enabled else 'false'}")
                    replaced_enabled = True
                if not replaced_reason:
                    new_lines.append(f"reason = {reason_value}")
                    replaced_reason = True
                if not replaced_updated_at:
                    new_lines.append(f"updated_at = {updated_value}")
                    replaced_updated_at = True
                in_block = False

            if in_block and stripped.startswith("enabled ="):
                new_lines.append(f"enabled = {'true' if state.enabled else 'false'}")
                replaced_enabled = True
                continue
            if in_block and stripped.startswith("reason ="):
                new_lines.append(f"reason = {reason_value}")
                replaced_reason = True
                continue
            if in_block and stripped.startswith("updated_at ="):
                new_lines.append(f"updated_at = {updated_value}")
                replaced_updated_at = True
                continue

            new_lines.append(line)

        if in_block:
            if not replaced_enabled:
                new_lines.append(f"enabled = {'true' if state.enabled else 'false'}")
            if not replaced_reason:
                new_lines.append(f"reason = {reason_value}")
            if not replaced_updated_at:
                new_lines.append(f"updated_at = {updated_value}")

        self.path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
