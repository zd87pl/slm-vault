"""Tests for the shared Enclave runtime control plane."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from advanced_vault.enclave_control import EnclaveRuntime


class TestEnclaveRuntime(unittest.TestCase):
    """Validate shared policy, kill switch, and event logging behavior."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.tmpdir.name) / "vault"
        self.config_path = Path(self.tmpdir.name) / ".enclave" / "policies.toml"
        self.runtime = EnclaveRuntime(
            vault_path=str(self.vault_path),
            config_path=str(self.config_path),
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_default_policy_denies_wallet_for_unknown_agent(self) -> None:
        decision, reason = self.runtime.evaluate_action(
            agent_id="unknown-agent",
            module="wallet",
            tool="request_purchase",
            amount=5.0,
        )
        self.assertEqual(decision, "deny")
        self.assertIn("not allowed", reason)

    def test_local_ui_policy_allows_wallet_actions(self) -> None:
        decision, reason = self.runtime.evaluate_action(
            agent_id="local-ui",
            module="wallet",
            tool="create_envelope",
        )
        self.assertEqual(decision, "allow")
        self.assertIn("allows", reason)

    def test_kill_switch_blocks_vault_and_wallet(self) -> None:
        self.runtime.set_kill_switch(True, reason="demo freeze", actor="test")
        decision, reason = self.runtime.evaluate_action(
            agent_id="local-ui",
            module="vault",
            tool="agent_query",
        )
        self.assertEqual(decision, "deny")
        self.assertIn("demo freeze", reason)

    def test_event_logging_and_module_status(self) -> None:
        self.runtime.log_event(
            subject="local-ui",
            module="wallet",
            tool="request_purchase",
            decision="PENDING",
            resource="demo-ops:openai.com",
            summary="Pending approval",
            metadata={"amount": 85.0},
        )
        events = self.runtime.list_events(limit=5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["tool"], "request_purchase")

        snapshot = self.runtime.update_module_status(
            "wallet",
            status="ready",
            headline="Wallet ready",
            details={"envelope_count": 1},
        )
        self.assertEqual(snapshot["module"], "wallet")
        stored = self.runtime.get_module_status("wallet")
        self.assertEqual(stored["details"]["envelope_count"], 1)


if __name__ == "__main__":
    unittest.main()
