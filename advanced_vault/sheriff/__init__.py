"""Data Sheriff package."""

from .core import SheriffCore
from .enforcement import EnforcementStatus
from .models import (
    AccessDecision,
    AccessRequestResult,
    AuditEvent,
    ConsentLease,
    FileRiskLabel,
    PolicyRule,
    RiskFinding,
    RiskSummary,
)

try:
    from .local_api import create_local_sheriff_app
except Exception:  # pragma: no cover - optional FastAPI surface
    create_local_sheriff_app = None

__all__ = [
    "SheriffCore",
    "EnforcementStatus",
    "FileRiskLabel",
    "AccessDecision",
    "ConsentLease",
    "PolicyRule",
    "AuditEvent",
    "RiskFinding",
    "RiskSummary",
    "AccessRequestResult",
]

if create_local_sheriff_app is not None:
    __all__.append("create_local_sheriff_app")
