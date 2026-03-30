"""SQLite-backed persistence for the Enclave wallet."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import ApprovalDecision, Envelope, PurchaseRequest, Transaction, WalletState


class WalletStore:
    """Small SQLite store for envelopes, requests, transactions, and state."""

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
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS envelopes (
                    envelope_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_requests (
                    request_id TEXT PRIMARY KEY,
                    envelope_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    envelope_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def set_global_state(self, state: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                ("wallet_state", json.dumps(state, sort_keys=True)),
            )
            conn.commit()

    def get_global_state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM metadata WHERE key = ?", ("wallet_state",)).fetchone()
            if row is None:
                return {"frozen": False}
            return json.loads(row["value"])

    def is_frozen(self) -> bool:
        return bool(self.get_global_state().get("frozen", False))

    def upsert_envelope(self, envelope: Envelope) -> Envelope:
        envelope.touch()
        payload = envelope.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO envelopes(envelope_id, name, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    envelope.envelope_id,
                    envelope.name,
                    json.dumps(payload, sort_keys=True),
                    envelope.created_at,
                    envelope.updated_at,
                ),
            )
            conn.commit()
        return envelope

    def get_envelope(self, envelope_id: str) -> Optional[Envelope]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM envelopes WHERE envelope_id = ?",
                (envelope_id,),
            ).fetchone()
            if row is None:
                return None
            return Envelope.from_dict(json.loads(row["payload"]))

    def get_envelope_by_name(self, name: str) -> Optional[Envelope]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM envelopes WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                return None
            return Envelope.from_dict(json.loads(row["payload"]))

    def list_envelopes(self) -> List[Envelope]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM envelopes ORDER BY created_at ASC").fetchall()
            return [Envelope.from_dict(json.loads(row["payload"])) for row in rows]

    def update_envelope(self, envelope: Envelope) -> Envelope:
        return self.upsert_envelope(envelope)

    def upsert_purchase_request(self, request: PurchaseRequest) -> PurchaseRequest:
        request.touch()
        payload = request.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO purchase_requests(
                    request_id, envelope_id, status, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.envelope_id,
                    request.status.value,
                    json.dumps(payload, sort_keys=True),
                    request.created_at,
                    request.updated_at,
                ),
            )
            conn.commit()
        return request

    def get_purchase_request(self, request_id: str) -> Optional[PurchaseRequest]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM purchase_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            return PurchaseRequest.from_dict(json.loads(row["payload"]))

    def list_purchase_requests(
        self,
        *,
        envelope_id: Optional[str] = None,
        status: Optional[WalletState] = None,
    ) -> List[PurchaseRequest]:
        query = "SELECT payload FROM purchase_requests"
        clauses: List[str] = []
        params: List[Any] = []
        if envelope_id is not None:
            clauses.append("envelope_id = ?")
            params.append(envelope_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [PurchaseRequest.from_dict(json.loads(row["payload"])) for row in rows]

    def upsert_transaction(self, transaction: Transaction) -> Transaction:
        transaction.touch()
        payload = transaction.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transactions(
                    transaction_id, envelope_id, request_id, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction.transaction_id,
                    transaction.envelope_id,
                    transaction.request_id,
                    json.dumps(payload, sort_keys=True),
                    transaction.created_at,
                    transaction.updated_at,
                ),
            )
            conn.commit()
        return transaction

    def list_transactions(self, envelope_id: Optional[str] = None) -> List[Transaction]:
        query = "SELECT payload FROM transactions"
        params: List[Any] = []
        if envelope_id is not None:
            query += " WHERE envelope_id = ?"
            params.append(envelope_id)
        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Transaction.from_dict(json.loads(row["payload"])) for row in rows]

    def update_global_freeze(self, reason: str = "") -> Dict[str, Any]:
        state = {
            "frozen": True,
            "reason": reason,
        }
        self.set_global_state(state)
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM envelopes").fetchall()
            for row in rows:
                envelope = Envelope.from_dict(json.loads(row["payload"]))
                envelope.status = WalletState.FROZEN
                envelope.touch()
                conn.execute(
                    "UPDATE envelopes SET payload = ?, updated_at = ? WHERE envelope_id = ?",
                    (
                        json.dumps(envelope.to_dict(), sort_keys=True),
                        envelope.updated_at,
                        envelope.envelope_id,
                    ),
                )
            conn.commit()
        return state

    def clear_global_freeze(self, reason: str = "") -> Dict[str, Any]:
        state = {
            "frozen": False,
            "reason": reason,
        }
        self.set_global_state(state)
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM envelopes").fetchall()
            for row in rows:
                envelope = Envelope.from_dict(json.loads(row["payload"]))
                envelope.status = WalletState.ACTIVE
                envelope.touch()
                conn.execute(
                    "UPDATE envelopes SET payload = ?, updated_at = ? WHERE envelope_id = ?",
                    (
                        json.dumps(envelope.to_dict(), sort_keys=True),
                        envelope.updated_at,
                        envelope.envelope_id,
                    ),
                )
            conn.commit()
        return state

    def adjust_envelope_balances(
        self,
        envelope_id: str,
        *,
        spent_delta: float = 0.0,
        pending_delta: float = 0.0,
    ) -> Envelope:
        envelope = self.get_envelope(envelope_id)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_id}")
        envelope.spent = round(envelope.spent + spent_delta, 2)
        envelope.pending = round(envelope.pending + pending_delta, 2)
        envelope.touch()
        return self.update_envelope(envelope)
