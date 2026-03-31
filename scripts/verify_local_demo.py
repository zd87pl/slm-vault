#!/usr/bin/env python3
"""Verify the local investor-demo path end to end."""

from __future__ import annotations

import platform
import sys
import tempfile
from pathlib import Path


DEFAULT_MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    print("== Enclave Local Demo Verification ==")
    print(f"Python: {platform.python_version()} ({platform.platform()})")
    version = sys.version_info
    _require((version.major, version.minor) >= (3, 10), "Python 3.10+ is required")

    import flet  # noqa: F401
    import flet_desktop  # noqa: F401

    from advanced_vault.gui.local_inference import LocalInferenceEngine
    from advanced_vault.gui.vault_app import VaultApp  # noqa: F401
    from advanced_vault.private_models import PrivateModelManager
    from advanced_vault.wallet import WalletService

    print("GUI imports: OK")

    engine = LocalInferenceEngine(cache_dir=".demo_model_cache")
    print(f"Local backend: {engine.backend}")
    _require(engine.backend == "mlx", "Expected MLX backend for the local demo path")
    _require(
        engine.load_model(progress_callback=lambda message: print(f"[model] {message}")),
        "Local MLX model failed to load",
    )
    print(f"Active model: {engine.MLX_MODEL_NAME}")
    _require(
        engine.MLX_MODEL_NAME == DEFAULT_MODEL,
        f"Expected default model {DEFAULT_MODEL}, got {engine.MLX_MODEL_NAME}",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        manager = PrivateModelManager(root_path=str(root / "private_models"))
        profile = manager.create_profile(
            name="investor-demo",
            description="Local investor demo profile",
            model_name=DEFAULT_MODEL,
        )
        session = manager.open_session(profile.name)
        try:
            session.add_document(
                name="pitch_overview.txt",
                content=(
                    "Enclave keeps sensitive files local, encrypted, and auditable. "
                    "External agents interact through MCP and receive synthesized answers "
                    "instead of raw documents."
                ),
                source_path=str(root / "pitch_overview.txt"),
            )
            session.add_document(
                name="wallet_controls.txt",
                content=(
                    "The escrow wallet blocks autonomous spending above 75 dollars unless "
                    "the user approves it. Funds must be preloaded into the envelope, and "
                    "the global kill switch freezes both privileged data access and spending."
                ),
                source_path=str(root / "wallet_controls.txt"),
            )

            result = session.ask(
                "What blocks autonomous spending above 75 dollars?",
                max_tokens=128,
                temperature=0.1,
            )
        finally:
            session.close()

        answer = result.get("answer", "").strip()
        sources = result.get("sources", [])
        print(f"[qa] {answer}")
        _require(answer, "Local Q&A returned an empty answer")
        normalized_answer = answer.lower()
        _require(
            "75" in answer and ("approve" in normalized_answer or "block" in normalized_answer),
            "Local Q&A answer was not grounded",
        )
        _require(bool(sources), "Local Q&A returned no source citations")

        wallet = WalletService(vault_path=tmpdir)
        wallet.create_envelope(
            "demo-wallet",
            budget=500.0,
            max_per_transaction=150.0,
            requires_approval_above=75.0,
            merchant_allowlist=["github.com", "openai.com"],
            metadata={"purpose": "investor-demo"},
        )

        auto_approved = wallet.request_purchase(
            "demo-wallet",
            amount=19.0,
            merchant="github.com",
            agent_id="agent-demo",
            memo="Auto-approved demo spend",
        )
        pending = wallet.request_purchase(
            "demo-wallet",
            amount=85.0,
            merchant="openai.com",
            agent_id="agent-demo",
            memo="Pending approval demo spend",
        )
        approved = wallet.approve_purchase(pending.request_id, approver="user")
        snapshot = wallet.check_budget("demo-wallet")
        wallet.freeze_all(reason="demo stop")

        print(
            "[wallet]",
            f"small={auto_approved.decision.value}",
            f"large={pending.decision.value}",
            f"approved={approved.decision.value}",
            f"available={snapshot['available']}",
        )
        _require(auto_approved.decision.value == "approved", "Small wallet spend should auto-approve")
        _require(pending.decision.value == "pending", "Large wallet spend should queue for approval")
        _require(approved.decision.value == "approved", "Pending wallet spend should approve")
        _require(snapshot["frozen"] is False, "Wallet snapshot should be active before freeze")

    print("Local investor demo verification: PASS")
    print("Launch the GUI with: ./.venv/bin/python -m advanced_vault.gui.vault_app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
