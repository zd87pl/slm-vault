"""Data models for the mock-only Enclave wallet module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

UTC = timezone.utc  # datetime.UTC alias needs 3.11+; project supports 3.10


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class WalletState(str, Enum):
    """State for wallet-level and request-level flows."""

    ACTIVE = "active"
    FROZEN = "frozen"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CAPTURED = "captured"


@dataclass
class Envelope:
    """A budget envelope controlled by Enclave policy."""

    name: str
    budget: float
    envelope_id: str = field(default_factory=lambda: str(uuid4()))
    period: str = "monthly"
    currency: str = "USD"
    provider: str = "mock"
    spent: float = 0.0
    pending: float = 0.0
    max_per_transaction: Optional[float] = None
    requires_approval_above: Optional[float] = None
    daily_limit: Optional[float] = None
    merchant_allowlist: List[str] = field(default_factory=list)
    merchant_blocklist: List[str] = field(default_factory=list)
    status: WalletState = WalletState.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()

    @property
    def available(self) -> float:
        return round(self.budget - self.spent - self.pending, 2)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Envelope":
        return cls(
            envelope_id=payload.get("envelope_id") or payload["name"],
            name=payload["name"],
            budget=float(payload["budget"]),
            period=payload.get("period", "monthly"),
            currency=payload.get("currency", "USD"),
            provider=payload.get("provider", "mock"),
            spent=float(payload.get("spent", 0.0)),
            pending=float(payload.get("pending", 0.0)),
            max_per_transaction=payload.get("max_per_transaction"),
            requires_approval_above=payload.get("requires_approval_above"),
            daily_limit=payload.get("daily_limit"),
            merchant_allowlist=list(payload.get("merchant_allowlist", [])),
            merchant_blocklist=list(payload.get("merchant_blocklist", [])),
            status=WalletState(payload.get("status", WalletState.ACTIVE.value)),
            metadata=dict(payload.get("metadata", {})),
            created_at=payload.get("created_at", _utcnow()),
            updated_at=payload.get("updated_at", _utcnow()),
        )


@dataclass
class PurchaseRequest:
    """A request made by an agent to spend from an envelope."""

    envelope_id: str
    merchant: str
    amount: float
    request_id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str = "user"
    currency: str = "USD"
    memo: str = ""
    provider: str = "mock"
    status: WalletState = WalletState.PENDING
    reason: str = ""
    provider_authorization_id: Optional[str] = None
    transaction_id: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PurchaseRequest":
        return cls(
            request_id=payload.get("request_id") or str(uuid4()),
            envelope_id=payload["envelope_id"],
            agent_id=payload.get("agent_id", "user"),
            merchant=payload["merchant"],
            amount=float(payload["amount"]),
            currency=payload.get("currency", "USD"),
            memo=payload.get("memo", ""),
            provider=payload.get("provider", "mock"),
            status=WalletState(payload.get("status", WalletState.PENDING.value)),
            reason=payload.get("reason", ""),
            provider_authorization_id=payload.get("provider_authorization_id"),
            transaction_id=payload.get("transaction_id"),
            decided_by=payload.get("decided_by"),
            decided_at=payload.get("decided_at"),
            metadata=dict(payload.get("metadata", {})),
            created_at=payload.get("created_at", _utcnow()),
            updated_at=payload.get("updated_at", _utcnow()),
        )


@dataclass
class Transaction:
    """A ledger entry created after a purchase is captured."""

    request_id: str
    envelope_id: str
    merchant: str
    amount: float
    transaction_id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str = "user"
    currency: str = "USD"
    provider: str = "mock"
    provider_reference: str = ""
    status: WalletState = WalletState.CAPTURED
    memo: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Transaction":
        return cls(
            transaction_id=payload.get("transaction_id") or str(uuid4()),
            request_id=payload["request_id"],
            envelope_id=payload["envelope_id"],
            agent_id=payload.get("agent_id", "user"),
            merchant=payload["merchant"],
            amount=float(payload["amount"]),
            currency=payload.get("currency", "USD"),
            provider=payload.get("provider", "mock"),
            provider_reference=payload.get("provider_reference", ""),
            status=WalletState(payload.get("status", WalletState.CAPTURED.value)),
            memo=payload.get("memo", ""),
            metadata=dict(payload.get("metadata", {})),
            created_at=payload.get("created_at", _utcnow()),
            updated_at=payload.get("updated_at", _utcnow()),
        )


@dataclass
class ApprovalDecision:
    """Outcome returned by request/approval flows."""

    request_id: str
    envelope_id: str
    decision: WalletState
    reason: str = ""
    agent_id: str = "user"
    merchant: str = ""
    amount: float = 0.0
    currency: str = "USD"
    requires_human_approval: bool = False
    transaction_id: Optional[str] = None
    provider_reference: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: str = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_approved(self) -> bool:
        return self.decision in {WalletState.APPROVED, WalletState.CAPTURED}

    def is_pending(self) -> bool:
        return self.decision == WalletState.PENDING

    def is_denied(self) -> bool:
        return self.decision == WalletState.DENIED

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
