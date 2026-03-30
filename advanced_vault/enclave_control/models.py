"""Shared data models for Enclave runtime control-plane services."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from typing import Any, Dict, List, Optional


def utcnow_iso() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC).isoformat()


@dataclass
class KillSwitchState:
    """Global kill switch state shared across Vault and Wallet."""

    enabled: bool = False
    reason: str = ""
    updated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentPolicy:
    """Operator-editable policy envelope for an external or local agent."""

    agent_id: str
    trust_level: str = "standard"
    allowed_modules: List[str] = field(default_factory=lambda: ["vault"])
    allowed_tools: List[str] = field(default_factory=lambda: ["*"])
    vault_scopes: List[str] = field(default_factory=lambda: ["*"])
    wallet_scopes: List[str] = field(default_factory=lambda: ["*"])
    wallet_auto_approve_below: float = 25.0
    wallet_prompt_above: float = 100.0
    start_hour: int = 0
    end_hour: int = 23
    metadata: Dict[str, Any] = field(default_factory=dict)

    def allows_module(self, module: str) -> bool:
        """Return whether the module is permitted for this agent."""
        if "*" in self.allowed_modules:
            return True
        return module in self.allowed_modules

    def allows_tool(self, tool: str) -> bool:
        """Return whether a specific tool pattern is permitted."""
        for pattern in self.allowed_tools:
            if pattern == "*" or fnmatch(tool, pattern):
                return True
        return False

    def is_active_hour(self, hour: int) -> bool:
        """Return whether the policy is active at the given local hour."""
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour <= self.end_hour
        return hour >= self.start_hour or hour <= self.end_hour

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEventRecord:
    """Normalized event stored in the shared audit/event SQLite store."""

    subject: str
    module: str
    tool: str
    decision: str
    resource: str = ""
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utcnow_iso)
    source: str = "runtime"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleStatus:
    """Snapshot used by GUI and integrations to render module health."""

    module: str
    status: str = "ready"
    headline: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
