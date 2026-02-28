"""Core models for the local Data Sheriff subsystem."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class FileRiskLabel(str, Enum):
    """Risk label assigned to a file/resource."""

    CRITICAL = "CRITICAL"
    SENSITIVE = "SENSITIVE"
    NORMAL = "NORMAL"


class AccessDecision(str, Enum):
    """Decision emitted by policy/access engine."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    PROMPT = "PROMPT"
    ALLOW_WITH_LEASE = "ALLOW_WITH_LEASE"


class ConsentLease(BaseModel):
    """Time-bound access lease."""

    lease_id: str = Field(default_factory=lambda: str(uuid4()))
    subject_app: str
    resource_scope: str
    purpose: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True

    def is_expired(self) -> bool:
        """Return true when the lease is no longer valid."""
        return datetime.utcnow() >= self.expires_at


class PolicyRule(BaseModel):
    """A single policy rule for path/risk/subject matching."""

    rule_id: str = Field(default_factory=lambda: str(uuid4()))
    path_scope: str = "*"
    label_scope: List[FileRiskLabel] = Field(default_factory=lambda: [FileRiskLabel.CRITICAL])
    subject_scope: List[str] = Field(default_factory=lambda: ["*"])
    decision: AccessDecision = AccessDecision.PROMPT
    conditions: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEvent(BaseModel):
    """Audit trail entry for access attempts and admin actions."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    subject: str
    resource: str
    action: str
    decision: AccessDecision
    reason: str = ""
    lease_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskFinding(BaseModel):
    """Single risk finding produced by scanner."""

    path: str
    label: FileRiskLabel
    score: float
    reasons: List[str] = Field(default_factory=list)
    recommendation: str
    detected_secrets: List[str] = Field(default_factory=list)


class RiskSummary(BaseModel):
    """Summary payload for UI/API."""

    scanned_at: datetime = Field(default_factory=datetime.utcnow)
    total_files: int
    critical_count: int
    sensitive_count: int
    normal_count: int
    findings: List[RiskFinding] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class AccessRequestResult(BaseModel):
    """Result of sheriff.request_access style call."""

    decision: AccessDecision
    reason: str
    label: FileRiskLabel
    lease: Optional[ConsentLease] = None
