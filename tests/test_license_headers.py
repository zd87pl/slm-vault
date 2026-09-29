"""The repository is Apache-2.0; no file header may say "All rights reserved"."""

import re
from pathlib import Path

import advanced_vault.prosumer as prosumer

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("advanced_vault", "tests", "docs", "examples", "scripts")
SCANNED_SUFFIXES = {".py", ".md", ".txt", ".toml", ".sh"}
SKIPPED_PARTS = {".venv", "node_modules", "__pycache__", ".git"}

# A copyright line that goes on to reserve all rights.
ALL_RIGHTS_RESERVED = re.compile(r"^\W*Copyright\b.*\bAll rights reserved\b", re.MULTILINE)


def _candidate_files():
    for path in REPO_ROOT.iterdir():
        if path.is_file() and path.suffix in SCANNED_SUFFIXES:
            yield path
    for name in SCANNED_DIRS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix in SCANNED_SUFFIXES and path.is_file() and not SKIPPED_PARTS.intersection(path.parts):
                yield path


def test_no_all_rights_reserved_headers():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _candidate_files()
        if ALL_RIGHTS_RESERVED.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []


def test_prosumer_header_points_at_apache_license():
    assert "Apache License 2.0" in prosumer.__doc__
    assert "All rights reserved" not in prosumer.__doc__
