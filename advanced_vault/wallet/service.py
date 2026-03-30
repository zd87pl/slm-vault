"""High-level facade for the mock-only Enclave wallet module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .budget import BudgetEngine, BudgetEvaluation
from .models import ApprovalDecision, Envelope, PurchaseRequest, Transaction, WalletState
from .provider import MockWalletProvider, WalletProvider
from .store import WalletStore


@dataclass
class WalletSnapshot:
    """Summary object returned by ``check_budget``."""

    envelope_id: str
    name: str
    budget: float
    spent: float
    pending: float
    available: float
    currency: str
    status: str
    provider: str
    frozen: bool
    daily_spent: float
    transaction_count: int
    pending_request_count: int
    can_spend: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "name": self.name,
            "budget": self.budget,
            "spent": self.spent,
            "pending": self.pending,
            "available": self.available,
            "currency": self.currency,
            "status": self.status,
            "provider": self.provider,
            "frozen": self.frozen,
            "daily_spent": self.daily_spent,
            "transaction_count": self.transaction_count,
            "pending_request_count": self.pending_request_count,
            "can_spend": self.can_spend,
            "reason": self.reason,
        }


class WalletService:
    """Facade for envelopes, requests, transactions, and freeze control."""

    def __init__(
        self,
        vault_path: str = "~/.vault",
        *,
        store: Optional[WalletStore] = None,
        provider_registry: Optional[Dict[str, WalletProvider]] = None,
        default_provider: str = "mock",
    ):
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.wallet_dir = self.vault_path / "wallet"
        self.wallet_dir.mkdir(parents=True, exist_ok=True)

        self.store = store or WalletStore(str(self.wallet_dir / "wallet.db"))
        self.budget_engine = BudgetEngine()
        self.providers = provider_registry or {"mock": MockWalletProvider()}
        self.default_provider = default_provider

        if self.default_provider not in self.providers:
            raise ValueError(f"Unknown default provider: {self.default_provider}")

    def create_envelope(
        self,
        name: str,
        *,
        budget: float,
        period: str = "monthly",
        currency: str = "USD",
        provider: Optional[str] = None,
        max_per_transaction: Optional[float] = None,
        requires_approval_above: Optional[float] = None,
        daily_limit: Optional[float] = None,
        merchant_allowlist: Optional[Iterable[str]] = None,
        merchant_blocklist: Optional[Iterable[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Envelope:
        self._ensure_not_frozen()
        if self.store.get_envelope_by_name(name) is not None:
            raise ValueError(f"Envelope already exists: {name}")

        provider_name = provider or self.default_provider
        self._resolve_provider(provider_name)

        envelope = Envelope(
            name=name,
            budget=float(budget),
            period=period,
            currency=currency,
            provider=provider_name,
            max_per_transaction=max_per_transaction,
            requires_approval_above=requires_approval_above,
            daily_limit=daily_limit,
            merchant_allowlist=list(merchant_allowlist or []),
            merchant_blocklist=list(merchant_blocklist or []),
            metadata=dict(metadata or {}),
        )
        return self.store.upsert_envelope(envelope)

    def list_envelopes(self) -> List[Envelope]:
        return self.store.list_envelopes()

    def check_budget(self, envelope_ref: str) -> Dict[str, Any]:
        envelope = self._resolve_envelope(envelope_ref)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_ref}")

        frozen = self.store.is_frozen()
        daily_spent = self._daily_spent(envelope.envelope_id)
        transaction_count = len(self.store.list_transactions(envelope.envelope_id))
        pending_requests = self.store.list_purchase_requests(
            envelope_id=envelope.envelope_id,
            status=WalletState.PENDING,
        )

        can_spend = not frozen and envelope.status == WalletState.ACTIVE and envelope.available > 0
        reason = "Wallet is frozen" if frozen else "Budget available"
        if envelope.status != WalletState.ACTIVE:
            reason = f"Envelope is {envelope.status.value}"

        snapshot = WalletSnapshot(
            envelope_id=envelope.envelope_id,
            name=envelope.name,
            budget=envelope.budget,
            spent=envelope.spent,
            pending=envelope.pending,
            available=envelope.available,
            currency=envelope.currency,
            status=envelope.status.value,
            provider=envelope.provider,
            frozen=frozen,
            daily_spent=daily_spent,
            transaction_count=transaction_count,
            pending_request_count=len(pending_requests),
            can_spend=can_spend,
            reason=reason,
        )
        return snapshot.to_dict()

    def request_purchase(
        self,
        envelope_ref: str,
        *,
        amount: float,
        merchant: str,
        agent_id: str = "user",
        currency: str = "USD",
        memo: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalDecision:
        self._ensure_not_frozen()
        envelope = self._resolve_envelope(envelope_ref)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_ref}")

        request = PurchaseRequest(
            envelope_id=envelope.envelope_id,
            agent_id=agent_id,
            merchant=merchant,
            amount=float(amount),
            currency=currency,
            memo=memo,
            provider=envelope.provider,
            metadata=dict(metadata or {}),
        )

        evaluation = self.budget_engine.evaluate(
            envelope,
            merchant=merchant,
            amount=request.amount,
            daily_spent=self._daily_spent(envelope.envelope_id),
            global_frozen=self.store.is_frozen(),
        )

        if evaluation.decision == WalletState.DENIED:
            request.status = WalletState.DENIED
            request.reason = evaluation.reason
            self.store.upsert_purchase_request(request)
            return self._decision_from_request(
                request,
                decision=WalletState.DENIED,
                reason=evaluation.reason,
                requires_human_approval=False,
            )

        if evaluation.decision == WalletState.PENDING:
            request.status = WalletState.PENDING
            request.reason = evaluation.reason
            self.store.upsert_purchase_request(request)
            self.store.adjust_envelope_balances(
                envelope.envelope_id,
                pending_delta=request.amount,
            )
            return self._decision_from_request(
                request,
                decision=WalletState.PENDING,
                reason=evaluation.reason,
                requires_human_approval=True,
            )

        return self._capture_request(
            request=request,
            envelope=envelope,
            reason=evaluation.reason,
        )

    def approve_purchase(
        self,
        request_id: str,
        *,
        approver: str = "user",
    ) -> ApprovalDecision:
        self._ensure_not_frozen()
        request = self.store.get_purchase_request(request_id)
        if request is None:
            raise KeyError(f"Purchase request not found: {request_id}")
        if request.status != WalletState.PENDING:
            raise ValueError(f"Purchase request is not pending: {request.status.value}")

        envelope = self._resolve_envelope(request.envelope_id)
        if envelope is None:
            raise KeyError(f"Envelope not found: {request.envelope_id}")

        evaluation = self.budget_engine.evaluate(
            envelope,
            merchant=request.merchant,
            amount=request.amount,
            daily_spent=self._daily_spent(envelope.envelope_id),
            global_frozen=self.store.is_frozen(),
            approval_override=True,
        )
        if evaluation.decision == WalletState.DENIED:
            request.status = WalletState.DENIED
            request.reason = evaluation.reason
            request.decided_by = approver
            request.decided_at = _utcnow()
            self.store.adjust_envelope_balances(
                envelope.envelope_id,
                pending_delta=-request.amount,
            )
            self.store.upsert_purchase_request(request)
            return self._decision_from_request(
                request,
                decision=WalletState.DENIED,
                reason=evaluation.reason,
                requires_human_approval=False,
                decided_by=approver,
            )

        capture = self._capture_request(
            request=request,
            envelope=envelope,
            reason="Human approval granted",
            decided_by=approver,
            release_pending=True,
        )
        return capture

    def get_transactions(self, envelope_ref: Optional[str] = None) -> List[Transaction]:
        if envelope_ref is None:
            return self.store.list_transactions()
        envelope = self._resolve_envelope(envelope_ref)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_ref}")
        return self.store.list_transactions(envelope.envelope_id)

    def list_pending_requests(self, envelope_ref: Optional[str] = None) -> List[PurchaseRequest]:
        if envelope_ref is None:
            return self.store.list_purchase_requests(status=WalletState.PENDING)
        envelope = self._resolve_envelope(envelope_ref)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_ref}")
        return self.store.list_purchase_requests(
            envelope_id=envelope.envelope_id,
            status=WalletState.PENDING,
        )

    def freeze_all(self, reason: str = "user requested freeze") -> Dict[str, Any]:
        return self.store.update_global_freeze(reason=reason)

    def unfreeze_all(self, reason: str = "user requested unfreeze") -> Dict[str, Any]:
        return self.store.clear_global_freeze(reason=reason)

    def _capture_request(
        self,
        *,
        request: PurchaseRequest,
        envelope: Envelope,
        reason: str,
        decided_by: Optional[str] = None,
        release_pending: bool = False,
    ) -> ApprovalDecision:
        provider = self._resolve_provider(envelope.provider)
        authorization_id = provider.authorize(request, envelope)
        provider_reference = provider.capture(request, authorization_id)

        transaction = Transaction(
            request_id=request.request_id,
            envelope_id=envelope.envelope_id,
            agent_id=request.agent_id,
            merchant=request.merchant,
            amount=request.amount,
            currency=request.currency,
            provider=envelope.provider,
            provider_reference=provider_reference,
            memo=request.memo,
            metadata=dict(request.metadata),
        )

        request.status = WalletState.CAPTURED
        request.reason = reason
        request.provider_authorization_id = authorization_id
        request.provider = envelope.provider
        request.transaction_id = transaction.transaction_id
        request.decided_by = decided_by or request.agent_id
        request.decided_at = _utcnow()
        self.store.upsert_purchase_request(request)
        self.store.upsert_transaction(transaction)

        if release_pending:
            self.store.adjust_envelope_balances(
                envelope.envelope_id,
                pending_delta=-request.amount,
                spent_delta=request.amount,
            )
        else:
            self.store.adjust_envelope_balances(
                envelope.envelope_id,
                spent_delta=request.amount,
            )

        return self._decision_from_request(
            request,
            decision=WalletState.APPROVED,
            reason=reason,
            requires_human_approval=False,
            transaction_id=transaction.transaction_id,
            provider_reference=provider_reference,
            decided_by=decided_by or request.agent_id,
        )

    def _decision_from_request(
        self,
        request: PurchaseRequest,
        *,
        decision: WalletState,
        reason: str,
        requires_human_approval: bool,
        transaction_id: Optional[str] = None,
        provider_reference: Optional[str] = None,
        decided_by: Optional[str] = None,
    ) -> ApprovalDecision:
        return ApprovalDecision(
            request_id=request.request_id,
            envelope_id=request.envelope_id,
            decision=decision,
            reason=reason,
            agent_id=request.agent_id,
            merchant=request.merchant,
            amount=request.amount,
            currency=request.currency,
            requires_human_approval=requires_human_approval,
            transaction_id=transaction_id or request.transaction_id,
            provider_reference=provider_reference or request.provider_authorization_id,
            decided_by=decided_by or request.decided_by,
            metadata=dict(request.metadata),
        )

    def _resolve_provider(self, provider_name: str) -> WalletProvider:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Unknown wallet provider: {provider_name}")
        return provider

    def _resolve_envelope(self, envelope_ref: str) -> Optional[Envelope]:
        envelope = self.store.get_envelope(envelope_ref)
        if envelope is not None:
            return envelope
        return self.store.get_envelope_by_name(envelope_ref)

    def _daily_spent(self, envelope_id: str) -> float:
        today = datetime.now(UTC).date()
        total = 0.0
        for transaction in self.store.list_transactions(envelope_id):
            created_at = datetime.fromisoformat(transaction.created_at)
            if created_at.date() == today:
                total += float(transaction.amount)
        return round(total, 2)

    def _ensure_not_frozen(self) -> None:
        if self.store.is_frozen():
            raise PermissionError("Wallet is frozen")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
