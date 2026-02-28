"""Core orchestration layer for the local Data Sheriff."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

from .audit_log import SheriffAuditLog
from .enforcement import EnforcementLayer
from .hardening import HardeningInspector
from .lease_manager import LeaseManager
from .models import (
    AccessDecision,
    AccessRequestResult,
    AuditEvent,
    FileRiskLabel,
    PolicyRule,
    RiskSummary,
)
from .policy_engine import PolicyEngine
from .risk_scanner import RiskScanner
from .secrets_vault import SecretsVault


_REDACTION_PATTERNS = [
    re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*([^\s]+)"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


class SheriffCore:
    """Main product facade for risk scan + access control + audit."""

    def __init__(self, vault_path: str = "~/.vault"):
        self.base_path = Path(vault_path).expanduser() / "sheriff"
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.policy = PolicyEngine(self.base_path / "policy_rules.json")
        self.leases = LeaseManager(self.base_path / "leases.json")
        self.audit = SheriffAuditLog(self.base_path / "audit.jsonl")
        self.scanner = RiskScanner()
        self.secrets = SecretsVault(self.base_path / "secrets")
        self.hardening = HardeningInspector()
        self.enforcement = EnforcementLayer()

    def request_access(
        self,
        *,
        subject_app: str,
        resource: str,
        purpose: str,
        consent_granted: bool = False,
        ttl_seconds: int = 900,
    ) -> AccessRequestResult:
        """
        Evaluate access and optionally issue lease.

        Default posture is deny-by-default for critical/sensitive labels.
        """
        label, _, _, _ = self.scanner.classify_path(resource)
        decision, reason = self.policy.evaluate(subject_app=subject_app, resource=resource, label=label)

        if decision == AccessDecision.ALLOW:
            lease = self.leases.issue(
                subject_app=subject_app,
                resource_scope=resource,
                purpose=purpose,
                ttl_seconds=ttl_seconds,
            )
            result = AccessRequestResult(
                decision=AccessDecision.ALLOW_WITH_LEASE,
                reason=f"{reason}; lease issued",
                label=label,
                lease=lease,
            )
            self._log(subject_app, resource, "request_access", result.decision, result.reason, lease.lease_id)
            return result

        if decision == AccessDecision.PROMPT and consent_granted:
            lease = self.leases.issue(
                subject_app=subject_app,
                resource_scope=resource,
                purpose=purpose,
                ttl_seconds=ttl_seconds,
            )
            result = AccessRequestResult(
                decision=AccessDecision.ALLOW_WITH_LEASE,
                reason="Explicit consent granted; lease issued",
                label=label,
                lease=lease,
            )
            self._log(subject_app, resource, "request_access", result.decision, result.reason, lease.lease_id)
            return result

        result = AccessRequestResult(decision=decision, reason=reason, label=label)
        self._log(subject_app, resource, "request_access", decision, reason, None)
        return result

    def consent_decide(
        self,
        *,
        subject_app: str,
        resource: str,
        purpose: str,
        allow: bool,
        ttl_seconds: int = 900,
    ) -> AccessRequestResult:
        """Resolve consent prompt into allow/deny result."""
        return self.request_access(
            subject_app=subject_app,
            resource=resource,
            purpose=purpose,
            consent_granted=allow,
            ttl_seconds=ttl_seconds,
        )

    def issue_lease(
        self,
        *,
        subject_app: str,
        resource_scope: str,
        purpose: str,
        ttl_seconds: int = 900,
    ):
        """Issue lease directly (admin/internal)."""
        lease = self.leases.issue(
            subject_app=subject_app,
            resource_scope=resource_scope,
            purpose=purpose,
            ttl_seconds=ttl_seconds,
        )
        self._log(subject_app, resource_scope, "issue_lease", AccessDecision.ALLOW_WITH_LEASE, "Direct lease issue", lease.lease_id)
        return lease

    def revoke_lease(self, lease_id: str, actor: str = "user") -> bool:
        """Revoke lease and audit event."""
        ok = self.leases.revoke(lease_id)
        decision = AccessDecision.ALLOW if ok else AccessDecision.DENY
        reason = "Lease revoked" if ok else "Lease not found"
        self._log(actor, lease_id, "revoke_lease", decision, reason, lease_id if ok else None)
        return ok

    def read_with_lease(
        self,
        *,
        subject_app: str,
        resource: str,
        lease_id: str,
        redact: bool = True,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> str:
        """Read resource only when lease is valid."""
        valid, reason, _ = self.leases.validate(
            lease_id=lease_id,
            subject_app=subject_app,
            resource_path=resource,
        )
        if not valid:
            self._log(subject_app, resource, "read", AccessDecision.DENY, reason, lease_id)
            raise PermissionError(reason)

        path = Path(resource).expanduser()
        if not path.exists() or not path.is_file():
            self._log(subject_app, resource, "read", AccessDecision.DENY, "Resource not found", lease_id)
            raise FileNotFoundError(resource)

        with open(path, "rb") as f:
            data = f.read(max_bytes)
        text = data.decode("utf-8", errors="ignore")
        if redact:
            text = self._redact(text)

        self._log(subject_app, resource, "read", AccessDecision.ALLOW_WITH_LEASE, "Read allowed by lease", lease_id)
        return text

    def scan_risk(self, *, paths: Optional[List[str]] = None, max_files: int = 2000) -> RiskSummary:
        """Run filesystem scan and return summary."""
        if not paths:
            paths = [str(Path.home() / "Documents")]
        return self.scanner.scan_paths(paths=paths, max_files=max_files)

    def protect_now(self, paths: List[str]) -> List[PolicyRule]:
        """Create prompt-based protection rules for selected paths."""
        rules = self.policy.protect_paths(paths=paths, label=FileRiskLabel.CRITICAL)
        for rule in rules:
            self._log("user", rule.path_scope, "protect_now", AccessDecision.PROMPT, "Protection rule enabled", None)
        return rules

    def hardening_report(self):
        """Return config hardening alerts."""
        return self.hardening.inspect()

    def audit_events(self, *, limit: int = 100, subject: Optional[str] = None, resource: Optional[str] = None, decision: Optional[AccessDecision] = None):
        """List recent audit events."""
        return self.audit.list(limit=limit, subject=subject, resource=resource, decision=decision)

    def enforcement_status(self) -> dict:
        """Return system enforcement backend status."""
        status = self.enforcement.status()
        return {
            "backend": status.backend,
            "enabled": status.enabled,
            "mode": status.mode,
            "message": status.message,
        }

    def _redact(self, text: str) -> str:
        """Best-effort local redaction for potentially sensitive tokens."""
        redacted = text
        for pattern in _REDACTION_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    def _log(
        self,
        subject: str,
        resource: str,
        action: str,
        decision: AccessDecision,
        reason: str,
        lease_id: Optional[str],
    ) -> None:
        self.audit.append(
            AuditEvent(
                subject=subject,
                resource=resource,
                action=action,
                decision=decision,
                reason=reason,
                lease_id=lease_id,
                metadata={"pid": os.getpid()},
            )
        )
