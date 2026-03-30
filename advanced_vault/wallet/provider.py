"""Wallet provider abstractions for mock-only Enclave wallet execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import uuid4

from .models import Envelope, PurchaseRequest


@dataclass
class ProviderAction:
    """Simple provider action record for debugging and tests."""

    action: str
    request_id: str
    provider_reference: str
    metadata: dict = field(default_factory=dict)


class WalletProvider(ABC):
    """Abstract spend provider."""

    name: str

    @abstractmethod
    def authorize(self, request: PurchaseRequest, envelope: Envelope) -> str:
        """Reserve funds for a purchase request and return an authorization reference."""

    @abstractmethod
    def capture(self, request: PurchaseRequest, authorization_id: str) -> str:
        """Capture a previously authorized purchase and return a capture reference."""

    @abstractmethod
    def void(self, authorization_id: str) -> None:
        """Void a previously authorized purchase."""


class MockWalletProvider(WalletProvider):
    """Local in-memory provider used for v1 and tests."""

    name = "mock"

    def __init__(self) -> None:
        self.authorizations: dict[str, ProviderAction] = {}
        self.captures: dict[str, ProviderAction] = {}
        self.voided: set[str] = set()

    def authorize(self, request: PurchaseRequest, envelope: Envelope) -> str:
        provider_reference = f"mock-auth-{uuid4().hex[:12]}"
        self.authorizations[provider_reference] = ProviderAction(
            action="authorize",
            request_id=request.request_id,
            provider_reference=provider_reference,
            metadata={
                "envelope_id": envelope.envelope_id,
                "merchant": request.merchant,
                "amount": request.amount,
            },
        )
        return provider_reference

    def capture(self, request: PurchaseRequest, authorization_id: str) -> str:
        provider_reference = f"mock-tx-{uuid4().hex[:12]}"
        self.captures[provider_reference] = ProviderAction(
            action="capture",
            request_id=request.request_id,
            provider_reference=provider_reference,
            metadata={"authorization_id": authorization_id},
        )
        return provider_reference

    def void(self, authorization_id: str) -> None:
        self.voided.add(authorization_id)
