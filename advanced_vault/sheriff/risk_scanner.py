"""Risk scanner for local file system resources."""

from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from typing import List, Tuple

from .models import FileRiskLabel, RiskFinding, RiskSummary

_PATH_CRITICAL_KEYWORDS = {
    "passport",
    "dowod",
    "id_card",
    "ssn",
    "pesel",
    "tax",
    "pit",
    "irs",
    "w2",
    "medical",
    "health",
    "clinic",
    "bank",
    "statement",
    "invoice",
    "contract",
}

_PATH_SENSITIVE_KEYWORDS = {
    "resume",
    "cv",
    "salary",
    "personal",
    "private",
    "confidential",
}

_SECRET_PATTERNS = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_password", re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_\.=]{20,}")),
]


def _is_probably_text(path: Path) -> bool:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("text/"):
        return True
    return path.suffix.lower() in {".txt", ".md", ".json", ".yaml", ".yml", ".env", ".log", ".cfg", ".ini", ".py", ".js"}


class RiskScanner:
    """Filesystem scanner that classifies resources and recommends protection."""

    def __init__(self, max_file_bytes: int = 128 * 1024):
        self.max_file_bytes = max_file_bytes

    def classify_path(self, path: str) -> Tuple[FileRiskLabel, float, List[str], List[str]]:
        """Classify single path and return (label, score, reasons, detected_secrets)."""
        p = Path(path).expanduser()
        norm = str(p).lower()
        reasons: List[str] = []
        detected_secrets: List[str] = []
        score = 0.0

        for keyword in _PATH_CRITICAL_KEYWORDS:
            if keyword in norm:
                score += 0.45
                reasons.append(f"Path contains critical keyword: {keyword}")
        for keyword in _PATH_SENSITIVE_KEYWORDS:
            if keyword in norm:
                score += 0.2
                reasons.append(f"Path contains sensitive keyword: {keyword}")

        if p.suffix.lower() in {".pem", ".key", ".p12", ".kdbx"}:
            score += 0.7
            reasons.append(f"Potential credential/key file extension: {p.suffix.lower()}")

        if p.exists() and p.is_file() and _is_probably_text(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read(self.max_file_bytes)
                for secret_name, pattern in _SECRET_PATTERNS:
                    if pattern.search(text):
                        detected_secrets.append(secret_name)
                        score += 0.35
                        reasons.append(f"Detected secret pattern: {secret_name}")
            except Exception:
                pass

        score = min(score, 1.0)
        if score >= 0.65:
            label = FileRiskLabel.CRITICAL
        elif score >= 0.30:
            label = FileRiskLabel.SENSITIVE
        else:
            label = FileRiskLabel.NORMAL
            reasons.append("No high-risk indicators detected")
        return label, score, reasons, detected_secrets

    def scan_paths(self, paths: List[str], max_files: int = 2000) -> RiskSummary:
        """Scan paths recursively and return summary."""
        findings: List[RiskFinding] = []
        file_count = 0
        critical = 0
        sensitive = 0
        normal = 0

        for root in paths:
            root_path = Path(root).expanduser()
            if not root_path.exists():
                continue

            iterator = [root_path] if root_path.is_file() else root_path.rglob("*")
            for candidate in iterator:
                if file_count >= max_files:
                    break
                if not candidate.exists() or not candidate.is_file():
                    continue
                file_count += 1

                label, score, reasons, detected = self.classify_path(str(candidate))
                if detected:
                    recommendation = "Extract & encrypt secret"
                elif label in {FileRiskLabel.CRITICAL, FileRiskLabel.SENSITIVE}:
                    recommendation = "Protect with consent barrier"
                else:
                    recommendation = "Ignore"

                findings.append(
                    RiskFinding(
                        path=str(candidate),
                        label=label,
                        score=round(score, 3),
                        reasons=reasons,
                        recommendation=recommendation,
                        detected_secrets=detected,
                    )
                )

                if label == FileRiskLabel.CRITICAL:
                    critical += 1
                elif label == FileRiskLabel.SENSITIVE:
                    sensitive += 1
                else:
                    normal += 1

        findings.sort(key=lambda f: f.score, reverse=True)
        recommendations = self._build_recommendations(findings)
        return RiskSummary(
            total_files=file_count,
            critical_count=critical,
            sensitive_count=sensitive,
            normal_count=normal,
            findings=findings,
            recommendations=recommendations,
        )

    def _build_recommendations(self, findings: List[RiskFinding]) -> List[str]:
        """Build concise recommendation list."""
        if not findings:
            return ["No files scanned yet."]

        top_critical = [f for f in findings if f.label == FileRiskLabel.CRITICAL][:5]
        top_sensitive = [f for f in findings if f.label == FileRiskLabel.SENSITIVE][:5]
        recs: List[str] = []
        if top_critical:
            recs.append(f"Protect {len(top_critical)} highest-risk files with consent barrier immediately.")
        if any(f.detected_secrets for f in findings):
            recs.append("Extract detected secrets (.env, keys, tokens) into encrypted local secrets vault.")
        if top_sensitive:
            recs.append("Apply time-limited leases for sensitive document access to reduce prompt fatigue.")
        if not recs:
            recs.append("Current scan indicates low risk. Keep deny-by-default for unknown apps.")
        return recs
