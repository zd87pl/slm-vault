"""Tests for Data Sheriff core behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from advanced_vault.sheriff.core import SheriffCore
from advanced_vault.sheriff.models import AccessDecision, FileRiskLabel


# Sheriff re-checks the shared policy (~/.enclave/policies.toml); the shipped
# one lets the operator identities (vault-cli, local-ui) use it, not unknown apps.
SUBJECT = "vault-cli"


@pytest.fixture
def sheriff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SheriffCore:
    """Create sheriff core with temporary vault path and shared policy."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return SheriffCore(vault_path=str(tmp_path))


def test_request_access_allows_normal_with_lease(sheriff: SheriffCore, tmp_path: Path) -> None:
    """Normal files should be allowed and receive time-limited lease."""
    resource = tmp_path / "notes.txt"
    resource.write_text("meeting notes")

    result = sheriff.request_access(
        subject_app=SUBJECT,
        resource=str(resource),
        purpose="answer question",
    )

    assert result.decision == AccessDecision.ALLOW_WITH_LEASE
    assert result.label == FileRiskLabel.NORMAL
    assert result.lease is not None


def test_request_access_prompt_then_consent_for_critical(sheriff: SheriffCore, tmp_path: Path) -> None:
    """Critical resource should require explicit consent before lease issue."""
    resource = tmp_path / "tax_records_2025.pem"
    resource.write_text("dummy-key")

    prompt_result = sheriff.request_access(
        subject_app=SUBJECT,
        resource=str(resource),
        purpose="summarize",
    )
    assert prompt_result.decision == AccessDecision.PROMPT
    assert prompt_result.label == FileRiskLabel.CRITICAL
    assert prompt_result.lease is None

    granted_result = sheriff.consent_decide(
        subject_app=SUBJECT,
        resource=str(resource),
        purpose="summarize",
        allow=True,
        ttl_seconds=60,
    )
    assert granted_result.decision == AccessDecision.ALLOW_WITH_LEASE
    assert granted_result.lease is not None


def test_read_with_lease_redacts_then_blocks_after_revoke(sheriff: SheriffCore, tmp_path: Path) -> None:
    """Read should work with active lease and fail after revoke."""
    resource = tmp_path / "secrets.env"
    resource.write_text("password=mysecret\ntoken=abc")

    lease = sheriff.issue_lease(
        subject_app=SUBJECT,
        resource_scope=str(resource),
        purpose="inspect",
        ttl_seconds=60,
    )
    content = sheriff.read_with_lease(
        subject_app=SUBJECT,
        resource=str(resource),
        lease_id=lease.lease_id,
        redact=True,
    )
    assert "[REDACTED]" in content

    assert sheriff.revoke_lease(lease.lease_id) is True
    with pytest.raises(PermissionError):
        sheriff.read_with_lease(
            subject_app=SUBJECT,
            resource=str(resource),
            lease_id=lease.lease_id,
            redact=True,
        )


def test_unidentified_subject_gets_no_lease_or_file_content(sheriff: SheriffCore, tmp_path: Path) -> None:
    """The shared policy's default entry no longer allows sheriff.* for unknown apps."""
    resource = tmp_path / "notes.txt"
    resource.write_text("meeting notes")

    result = sheriff.request_access(subject_app="unknown", resource=str(resource), purpose="read")

    assert result.decision == AccessDecision.DENY
    assert result.lease is None
    lease = sheriff.issue_lease(
        subject_app="unknown", resource_scope=str(resource), purpose="read", ttl_seconds=60,
    )
    with pytest.raises(PermissionError, match="sheriff.read"):
        sheriff.read_with_lease(subject_app="unknown", resource=str(resource), lease_id=lease.lease_id)


def test_scan_risk_detects_secret_recommendation(sheriff: SheriffCore, tmp_path: Path) -> None:
    """Scanner should flag secret-like content and recommend extraction."""
    env_file = tmp_path / "test.env"
    env_file.write_text("OPENAI_API_KEY=sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n")

    summary = sheriff.scan_risk(paths=[str(tmp_path)], max_files=10)

    assert summary.total_files >= 1
    assert any("Extract detected secrets" in r for r in summary.recommendations)
    assert any("openai_key" in finding.detected_secrets for finding in summary.findings)
