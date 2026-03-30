"""SQLite-backed shared event store for Enclave Vault + Wallet activity."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AuditEventRecord, ModuleStatus


class AuditEventStore:
    """Persist normalized runtime events and module status snapshots."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    module TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    source TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS module_status (
                    module TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def append(self, event: AuditEventRecord) -> None:
        """Insert one event if it has not already been imported."""
        payload = event.to_dict()
        event_key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO events(
                    event_key, timestamp, subject, module, tool, decision,
                    resource, summary, metadata, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_key,
                    event.timestamp,
                    event.subject,
                    event.module,
                    event.tool,
                    event.decision,
                    event.resource,
                    event.summary,
                    json.dumps(event.metadata, sort_keys=True),
                    event.source,
                ),
            )
            conn.commit()

    def list_events(
        self,
        *,
        limit: int = 50,
        subject: Optional[str] = None,
        module: Optional[str] = None,
        decision: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent events ordered from newest to oldest."""
        query = "SELECT * FROM events"
        clauses = []
        params: List[Any] = []
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if module:
            clauses.append("module = ?")
            params.append(module)
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_dict(row) for row in rows]

    def upsert_module_status(self, status: ModuleStatus) -> None:
        """Persist a module status snapshot."""
        payload = status.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO module_status(module, status, payload, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    status.module,
                    status.status,
                    json.dumps(payload, sort_keys=True),
                    status.updated_at,
                ),
            )
            conn.commit()

    def get_module_status(self, module: str) -> Optional[Dict[str, Any]]:
        """Return one module status if present."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM module_status WHERE module = ?",
                (module,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def list_module_statuses(self) -> List[Dict[str, Any]]:
        """Return all module statuses."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM module_status ORDER BY module ASC"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def has_events(self) -> bool:
        """Return whether the shared store already contains events."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return bool(row and row["count"])

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "timestamp": row["timestamp"],
            "subject": row["subject"],
            "module": row["module"],
            "tool": row["tool"],
            "decision": row["decision"],
            "resource": row["resource"],
            "summary": row["summary"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "source": row["source"],
        }
