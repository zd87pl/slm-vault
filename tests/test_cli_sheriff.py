"""Tests for sheriff commands in CLI."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from advanced_vault.cli.main import cli


def test_sheriff_scan_and_protect(tmp_path: Path) -> None:
    """CLI should scan risk and create protect rules."""
    runner = CliRunner()
    scan_root = tmp_path / "scan"
    scan_root.mkdir(parents=True, exist_ok=True)
    (scan_root / "medical_report.txt").write_text("basic medical info")

    scan = runner.invoke(
        cli,
        [
            "--vault-path",
            str(tmp_path),
            "sheriff",
            "scan",
            str(scan_root),
            "--max-files",
            "100",
            "--json",
        ],
    )
    assert scan.exit_code == 0
    payload = json.loads(scan.output)
    assert payload["total_files"] >= 1
    assert "recommendations" in payload

    protect = runner.invoke(
        cli,
        [
            "--vault-path",
            str(tmp_path),
            "sheriff",
            "protect",
            str(scan_root),
            "--json",
        ],
    )
    assert protect.exit_code == 0
    protect_payload = json.loads(protect.output)
    assert protect_payload["count"] == 1
    assert len(protect_payload["rules"]) == 1


def test_sheriff_access_read_revoke_flow(tmp_path: Path) -> None:
    """CLI should issue lease, read with lease, then deny after revoke."""
    runner = CliRunner()
    resource = tmp_path / "notes.txt"
    resource.write_text("hello world")

    access = runner.invoke(
        cli,
        [
            "--vault-path",
            str(tmp_path),
            "sheriff",
            "access",
            str(resource),
            "test-purpose",
            "--json",
        ],
    )
    assert access.exit_code == 0
    access_payload = json.loads(access.output)
    assert access_payload["decision"] == "ALLOW_WITH_LEASE"
    lease_id = access_payload["lease"]["lease_id"]

    read = runner.invoke(
        cli,
        [
            "--vault-path",
            str(tmp_path),
            "sheriff",
            "read",
            str(resource),
            lease_id,
        ],
    )
    assert read.exit_code == 0
    assert "hello world" in read.output

    revoke = runner.invoke(
        cli,
        [
            "--vault-path",
            str(tmp_path),
            "sheriff",
            "revoke",
            lease_id,
        ],
    )
    assert revoke.exit_code == 0

    denied = runner.invoke(
        cli,
        [
            "--vault-path",
            str(tmp_path),
            "sheriff",
            "read",
            str(resource),
            lease_id,
        ],
    )
    assert denied.exit_code == 1
    assert "Access denied" in denied.output
