"""Shared runtime facade for policy, audit, agent identity, and module status."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .audit_store import AuditEventStore
from .config import EnclavePolicyConfig
from .models import AgentPolicy, AuditEventRecord, KillSwitchState, ModuleStatus, utcnow_iso


class EnclaveRuntime:
    """Shared control-plane facade used by GUI, CLI, Sheriff, MCP, and Wallet."""

    def __init__(
        self,
        vault_path: str = "~/.vault",
        *,
        config_path: str = "~/.enclave/policies.toml",
        store_path: Optional[str] = None,
    ):
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self.config = EnclavePolicyConfig(config_path)
        store_root = Path(store_path).expanduser() if store_path else (self.vault_path / "control_plane" / "events.db")
        self.audit_store = AuditEventStore(str(store_root))

        self._document = self.config.load()
        self._registered_modules = {"vault", "wallet", "security"}
        self._import_legacy_events()

    def reload(self) -> None:
        """Reload TOML policy config from disk."""
        self._document = self.config.load()

    def register_module(self, module: str) -> None:
        """Register a module name for future status snapshots."""
        self._registered_modules.add(module)

    def get_kill_switch(self) -> KillSwitchState:
        """Return current kill-switch state from config."""
        return self._document.kill_switch

    def set_kill_switch(self, enabled: bool, reason: str = "", actor: str = "local-ui") -> KillSwitchState:
        """Persist kill-switch state and emit a shared runtime event."""
        state = KillSwitchState(enabled=enabled, reason=reason, updated_at=utcnow_iso())
        self._document.kill_switch = state
        self.config.save_kill_switch(state)
        self.log_event(
            subject=actor,
            module="security",
            tool="runtime.kill_switch",
            decision="ALLOW" if enabled else "INFO",
            resource="global",
            summary=("Kill switch enabled" if enabled else "Kill switch disabled") + (f": {reason}" if reason else ""),
            metadata=state.to_dict(),
            source="runtime",
        )
        return state

    def get_agent_policy(self, agent_id: str) -> AgentPolicy:
        """Resolve a concrete agent policy, falling back to `default`."""
        if agent_id in self._document.agents:
            return self._document.agents[agent_id]

        # Match common normalized aliases before defaulting.
        normalized = (agent_id or "default").strip().lower()
        if normalized in self._document.agents:
            return self._document.agents[normalized]

        if "claude" in normalized and "claude-desktop" in self._document.agents:
            return self._document.agents["claude-desktop"]
        if "cursor" in normalized and "cursor" in self._document.agents:
            return self._document.agents["cursor"]
        if "openclaw" in normalized and "openclaw" in self._document.agents:
            return self._document.agents["openclaw"]
        return self._document.agents["default"]

    def evaluate_action(
        self,
        *,
        agent_id: str,
        module: str,
        tool: str,
        resource: str = "",
        amount: Optional[float] = None,
    ) -> Tuple[str, str]:
        """Evaluate one action against kill-switch and agent policy."""
        if self._document.kill_switch.enabled and module in {"vault", "wallet"}:
            return "deny", self._document.kill_switch.reason or "Global kill switch is enabled"

        policy = self.get_agent_policy(agent_id)
        if not policy.allows_module(module):
            return "deny", f"Agent '{agent_id}' is not allowed to use module '{module}'"
        if not policy.allows_tool(tool):
            return "deny", f"Agent '{agent_id}' is not allowed to call '{tool}'"

        local_hour = datetime.now().hour
        if not policy.is_active_hour(local_hour):
            return "deny", f"Agent '{agent_id}' is outside its allowed operating window"

        if module == "wallet" and amount is not None and policy.wallet_prompt_above > 0 and amount > policy.wallet_prompt_above:
            return "prompt", "Shared wallet policy requires human approval"

        return "allow", "Shared policy allows action"

    def log_event(
        self,
        *,
        subject: str,
        module: str,
        tool: str,
        decision: str,
        resource: str = "",
        summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "runtime",
    ) -> None:
        """Append one normalized event to the shared store."""
        self.audit_store.append(
            AuditEventRecord(
                subject=subject,
                module=module,
                tool=tool,
                decision=decision,
                resource=resource,
                summary=summary,
                metadata=dict(metadata or {}),
                source=source,
            )
        )

    def list_events(
        self,
        *,
        limit: int = 50,
        subject: Optional[str] = None,
        module: Optional[str] = None,
        decision: Optional[str] = None,
    ):
        """Expose recent shared events."""
        return self.audit_store.list_events(limit=limit, subject=subject, module=module, decision=decision)

    def update_module_status(
        self,
        module: str,
        *,
        status: str = "ready",
        headline: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a module snapshot for the GUI and future shells."""
        snapshot = ModuleStatus(
            module=module,
            status=status,
            headline=headline,
            details=dict(details or {}),
            updated_at=utcnow_iso(),
        )
        self.audit_store.upsert_module_status(snapshot)
        return snapshot.to_dict()

    def get_module_status(self, module: str) -> Optional[Dict[str, Any]]:
        """Return the latest stored status for a module."""
        return self.audit_store.get_module_status(module)

    def list_module_statuses(self):
        """Return all current module snapshots."""
        return self.audit_store.list_module_statuses()

    def _import_legacy_events(self) -> None:
        """Import legacy JSONL activity/audit logs into the shared store."""
        if self.audit_store.has_events():
            return

        activity_log = self.vault_path / "activity.jsonl"
        sheriff_log = self.vault_path / "sheriff" / "audit.jsonl"
        if activity_log.exists():
            self._import_activity_log(activity_log)
        if sheriff_log.exists():
            self._import_sheriff_log(sheriff_log)

    def _import_activity_log(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            tool_name = str(entry.get("tool_name", "unknown"))
            self.audit_store.append(
                AuditEventRecord(
                    timestamp=str(entry.get("timestamp") or utcnow_iso()),
                    subject=str(entry.get("app_identifier") or "unknown"),
                    module=self._module_for_tool(tool_name),
                    tool=tool_name,
                    decision="ALLOW" if entry.get("granted", True) else "DENY",
                    resource=str(entry.get("query_preview", "")),
                    summary=str(entry.get("result_summary", "")),
                    metadata=dict(entry.get("metadata", {})),
                    source="activity_jsonl",
                )
            )

    def _import_sheriff_log(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.audit_store.append(
                AuditEventRecord(
                    timestamp=str(entry.get("timestamp") or utcnow_iso()),
                    subject=str(entry.get("subject") or "unknown"),
                    module="security",
                    tool=str(entry.get("action") or "sheriff"),
                    decision=str(entry.get("decision") or "INFO"),
                    resource=str(entry.get("resource") or ""),
                    summary=str(entry.get("reason") or ""),
                    metadata=dict(entry.get("metadata", {})),
                    source="sheriff_jsonl",
                )
            )

    def _module_for_tool(self, tool_name: str) -> str:
        if tool_name.startswith(("sheriff_", "sheriff.")):
            return "security"
        if tool_name in {
            "check_budget",
            "list_envelopes",
            "request_purchase",
            "approve_purchase",
            "get_transactions",
            "create_envelope",
            "freeze_all",
            "unfreeze_all",
        }:
            return "wallet"
        return "vault"
