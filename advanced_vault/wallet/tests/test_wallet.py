"""Tests for the mock-only Enclave wallet module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from advanced_vault.wallet import WalletService
from advanced_vault.wallet.models import WalletState


class TestWalletService(unittest.TestCase):
    """End-to-end tests for the wallet facade."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault_path = self.tmpdir.name
        self.service = WalletService(vault_path=self.vault_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_create_list_and_check_budget(self) -> None:
        envelope = self.service.create_envelope(
            "shopping",
            budget=100.0,
            requires_approval_above=25.0,
            max_per_transaction=50.0,
            daily_limit=75.0,
        )

        envelopes = self.service.list_envelopes()
        self.assertEqual(len(envelopes), 1)
        self.assertEqual(envelopes[0].name, "shopping")

        snapshot = self.service.check_budget(envelope.envelope_id)
        self.assertEqual(snapshot["budget"], 100.0)
        self.assertEqual(snapshot["available"], 100.0)
        self.assertFalse(snapshot["frozen"])
        self.assertTrue(snapshot["can_spend"])

    def test_auto_approve_under_threshold(self) -> None:
        envelope = self.service.create_envelope(
            "tools",
            budget=200.0,
            requires_approval_above=25.0,
        )

        decision = self.service.request_purchase(
            envelope.envelope_id,
            amount=19.99,
            merchant="github.com",
            agent_id="claude",
            memo="API key rotation subscription",
        )

        self.assertEqual(decision.decision, WalletState.APPROVED)
        self.assertFalse(decision.requires_human_approval)
        self.assertIsNotNone(decision.transaction_id)

        refreshed = self.service.check_budget(envelope.envelope_id)
        self.assertEqual(refreshed["spent"], 19.99)
        self.assertEqual(refreshed["available"], 180.01)
        transactions = self.service.get_transactions(envelope.envelope_id)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].merchant, "github.com")

    def test_pending_then_approve(self) -> None:
        envelope = self.service.create_envelope(
            "travel",
            budget=300.0,
            requires_approval_above=50.0,
        )

        decision = self.service.request_purchase(
            envelope.name,
            amount=120.0,
            merchant="airline.example",
            agent_id="openclaw",
        )
        self.assertEqual(decision.decision, WalletState.PENDING)
        self.assertTrue(decision.requires_human_approval)
        self.assertIsNone(decision.transaction_id)

        pending = self.service.list_pending_requests(envelope.name)
        self.assertEqual(len(pending), 1)

        approval = self.service.approve_purchase(pending[0].request_id, approver="user")
        self.assertEqual(approval.decision, WalletState.APPROVED)
        self.assertIsNotNone(approval.transaction_id)

        refreshed = self.service.check_budget(envelope.name)
        self.assertEqual(refreshed["spent"], 120.0)
        self.assertEqual(refreshed["pending"], 0.0)
        self.assertEqual(len(self.service.get_transactions(envelope.name)), 1)

    def test_freeze_blocks_requests(self) -> None:
        envelope = self.service.create_envelope(
            "api-costs",
            budget=50.0,
            requires_approval_above=10.0,
        )

        state = self.service.freeze_all(reason="kill switch")
        self.assertTrue(state["frozen"])

        with self.assertRaises(PermissionError):
            self.service.request_purchase(
                envelope.envelope_id,
                amount=1.0,
                merchant="openai.com",
            )

    def test_persistence_across_restart(self) -> None:
        envelope = self.service.create_envelope(
            "ops",
            budget=500.0,
            requires_approval_above=100.0,
        )
        self.service.request_purchase(
            envelope.envelope_id,
            amount=25.0,
            merchant="gitlab.com",
        )

        reopened = WalletService(vault_path=self.vault_path)
        loaded = reopened.list_envelopes()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].spent, 25.0)
        self.assertEqual(len(reopened.get_transactions(loaded[0].envelope_id)), 1)


if __name__ == "__main__":
    unittest.main()
