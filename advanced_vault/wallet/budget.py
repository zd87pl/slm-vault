"""Budget evaluation helpers for the Enclave wallet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Iterable, Optional

from .models import Envelope, WalletState

UTC = timezone.utc  # datetime.UTC alias needs 3.11+; project supports 3.10


@dataclass
class BudgetEvaluation:
    """Internal result of budget-policy evaluation."""

    decision: WalletState
    reason: str
    requires_human_approval: bool = False
    blocked: bool = False


class BudgetEngine:
    """Evaluate wallet requests against envelope rules."""

    def evaluate(
        self,
        envelope: Envelope,
        *,
        merchant: str,
        amount: float,
        daily_spent: float = 0.0,
        global_frozen: bool = False,
        approval_override: bool = False,
        now: Optional[datetime] = None,
    ) -> BudgetEvaluation:
        """Return the policy outcome for a spend request."""
        current_time = now or datetime.now(UTC)
        _ = current_time

        if global_frozen:
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason="Wallet is frozen",
                blocked=True,
            )

        if envelope.status != WalletState.ACTIVE:
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason=f"Envelope is {envelope.status.value}",
                blocked=True,
            )

        if amount <= 0:
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason="Amount must be greater than zero",
                blocked=True,
            )

        if envelope.merchant_blocklist and _matches_any(merchant, envelope.merchant_blocklist):
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason=f"Merchant '{merchant}' is blocked",
                blocked=True,
            )

        if envelope.merchant_allowlist and not _matches_any(merchant, envelope.merchant_allowlist):
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason=f"Merchant '{merchant}' is not on the allowlist",
                blocked=True,
            )

        if envelope.max_per_transaction is not None and amount > envelope.max_per_transaction:
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason="Amount exceeds the maximum per transaction",
                blocked=True,
            )

        if amount > envelope.available:
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason="Insufficient envelope budget",
                blocked=True,
            )

        if envelope.daily_limit is not None and (daily_spent + amount) > envelope.daily_limit:
            return BudgetEvaluation(
                decision=WalletState.DENIED,
                reason="Daily budget limit exceeded",
                blocked=True,
            )

        approval_threshold = envelope.requires_approval_above
        if approval_override:
            approval_threshold = None

        if approval_threshold is not None and amount > approval_threshold:
            return BudgetEvaluation(
                decision=WalletState.PENDING,
                reason="Purchase requires human approval",
                requires_human_approval=True,
            )

        return BudgetEvaluation(
            decision=WalletState.APPROVED,
            reason="Purchase is within budget policy",
        )


def _matches_any(value: str, patterns: Iterable[str]) -> bool:
    value_lower = value.lower()
    for pattern in patterns:
        if fnmatch(value_lower, pattern.lower()):
            return True
    return False
