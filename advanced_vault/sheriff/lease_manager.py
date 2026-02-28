"""Consent lease management."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

from .models import ConsentLease
from .storage import JSONFileStore


def _resource_matches_scope(resource_path: str, scope: str) -> bool:
    """Return true when a resource path is covered by the lease scope."""
    if scope == "*":
        return True

    resource = str(Path(resource_path).expanduser().resolve())
    scoped = str(Path(scope).expanduser().resolve())
    if resource == scoped:
        return True

    # Directory scope case.
    return resource.startswith(scoped.rstrip("/") + "/")


class LeaseManager:
    """Persistent manager for short-lived consent leases."""

    def __init__(self, store_path: Path):
        self.store = JSONFileStore(Path(store_path))
        self._leases: Dict[str, ConsentLease] = {}
        self._load()

    def _load(self) -> None:
        raw = self.store.load(default={})
        leases: Dict[str, ConsentLease] = {}
        for lease_id, data in raw.items():
            try:
                lease = ConsentLease.model_validate(data)
                leases[lease_id] = lease
            except Exception:
                continue
        self._leases = leases

    def _flush(self) -> None:
        payload = {k: v.model_dump(mode="json") for k, v in self._leases.items()}
        self.store.save(payload)

    def issue(
        self,
        *,
        subject_app: str,
        resource_scope: str,
        purpose: str,
        ttl_seconds: int = 900,
    ) -> ConsentLease:
        """Issue a new lease."""
        lease = ConsentLease(
            subject_app=subject_app,
            resource_scope=resource_scope,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(seconds=max(1, ttl_seconds)),
        )
        self._leases[lease.lease_id] = lease
        self._flush()
        return lease

    def revoke(self, lease_id: str) -> bool:
        """Revoke a lease by id."""
        lease = self._leases.get(lease_id)
        if not lease:
            return False
        lease.active = False
        self._flush()
        return True

    def list_active(self) -> Dict[str, ConsentLease]:
        """Return currently active and non-expired leases."""
        active: Dict[str, ConsentLease] = {}
        changed = False
        for lease_id, lease in self._leases.items():
            if lease.is_expired() and lease.active:
                lease.active = False
                changed = True
            if lease.active and not lease.is_expired():
                active[lease_id] = lease

        if changed:
            self._flush()
        return active

    def validate(
        self,
        *,
        lease_id: str,
        subject_app: str,
        resource_path: str,
    ) -> Tuple[bool, str, Optional[ConsentLease]]:
        """Validate lease against subject and resource constraints."""
        lease = self._leases.get(lease_id)
        if not lease:
            return False, "Lease not found", None
        if not lease.active:
            return False, "Lease revoked", lease
        if lease.is_expired():
            lease.active = False
            self._flush()
            return False, "Lease expired", lease
        if lease.subject_app != subject_app:
            return False, "Lease subject mismatch", lease
        if not _resource_matches_scope(resource_path, lease.resource_scope):
            return False, "Lease scope mismatch", lease
        return True, "Lease valid", lease
