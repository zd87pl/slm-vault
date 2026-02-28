"""Audit logging for Sheriff decisions and access events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import AccessDecision, AuditEvent


class SheriffAuditLog:
    """Append-only JSONL audit log."""

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: AuditEvent) -> None:
        """Append one event to log."""
        with open(self.log_path, "a") as f:
            f.write(event.model_dump_json())
            f.write("\n")

    def list(
        self,
        *,
        limit: int = 100,
        subject: Optional[str] = None,
        resource: Optional[str] = None,
        decision: Optional[AccessDecision] = None,
    ) -> List[Dict]:
        """List recent events with optional filters."""
        if not self.log_path.exists():
            return []

        results: List[Dict] = []
        with open(self.log_path, "r") as f:
            lines = f.readlines()

        for line in reversed(lines):
            try:
                row = json.loads(line.strip())
            except Exception:
                continue

            if subject and row.get("subject") != subject:
                continue
            if resource and resource not in row.get("resource", ""):
                continue
            if decision and row.get("decision") != decision.value:
                continue

            results.append(row)
            if len(results) >= limit:
                break

        return results
