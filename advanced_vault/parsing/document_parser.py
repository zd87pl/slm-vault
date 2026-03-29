"""Shared PDF parsing helpers with optional LiteParse support."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - compatibility for GUI envs
    try:
        from PyPDF2 import PdfReader  # type: ignore[assignment]
    except ImportError:  # pragma: no cover - optional dependency
        PdfReader = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "auto"
SUPPORTED_BACKENDS = {"auto", "pypdf", "liteparse"}


@dataclass
class ParsedDocument:
    """Normalized PDF parsing result."""

    text: str
    backend: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def get_parser_backend() -> str:
    """Return the preferred parser backend from environment configuration."""
    backend = os.getenv("ENCLAVE_PARSER_BACKEND", DEFAULT_BACKEND).strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        logger.warning("Unknown ENCLAVE_PARSER_BACKEND=%s. Falling back to auto.", backend)
        return DEFAULT_BACKEND
    return backend


def has_liteparse_backend(
    allow_npx: Optional[bool] = None,
    cli_path: Optional[str] = None,
) -> bool:
    """Return whether a LiteParse CLI is reachable in the current environment."""
    return _resolve_liteparse_command(allow_npx=allow_npx, cli_path=cli_path) is not None


def is_text_quality_good(text: str) -> bool:
    """Heuristic check for whether extracted text is likely usable."""
    if not text or len(text.strip()) < 50:
        return False

    special_chars = "!\"#$%&*()+=[]{}|;:,.<>?/@\\^_`~"
    if len(text) > 100:
        sample = text[:500] if len(text) > 500 else text
        special_char_ratio = sum(1 for char in sample if char in special_chars) / len(sample)
        if special_char_ratio > 0.15:
            return False

    return len(text.split()) >= 10


def extract_pdf_text(
    pdf_path: str | Path,
    backend: Optional[str] = None,
    ocr_language: Optional[str] = None,
    ocr_server_url: Optional[str] = None,
    allow_npx: Optional[bool] = None,
    cli_path: Optional[str] = None,
    quiet: bool = True,
) -> ParsedDocument:
    """Extract PDF text using PyPDF/PyPDF2, LiteParse, or both."""
    path = Path(pdf_path).expanduser()
    backend_name = (backend or get_parser_backend()).strip().lower()
    if backend_name not in SUPPORTED_BACKENDS:
        backend_name = DEFAULT_BACKEND

    if backend_name == "pypdf":
        return _extract_with_pypdf(path)

    if backend_name == "liteparse":
        try:
            return _extract_with_liteparse(
                path,
                ocr_language=ocr_language,
                ocr_server_url=ocr_server_url,
                allow_npx=allow_npx,
                cli_path=cli_path,
                quiet=quiet,
            )
        except Exception as exc:
            logger.warning("LiteParse extraction failed for %s: %s", path, exc)
            fallback = _extract_with_pypdf(path)
            fallback.warnings.append(f"liteparse_failed: {exc}")
            return fallback

    pypdf_result: Optional[ParsedDocument] = None
    pypdf_error: Optional[Exception] = None
    try:
        pypdf_result = _extract_with_pypdf(path)
        if is_text_quality_good(pypdf_result.text):
            return pypdf_result
    except Exception as exc:
        pypdf_error = exc

    try:
        liteparse_result = _extract_with_liteparse(
            path,
            ocr_language=ocr_language,
            ocr_server_url=ocr_server_url,
            allow_npx=allow_npx,
            cli_path=cli_path,
            quiet=quiet,
        )
        if pypdf_result is None:
            if pypdf_error is not None:
                liteparse_result.warnings.append(f"pypdf_failed: {pypdf_error}")
            return liteparse_result

        if len(liteparse_result.text.strip()) > len(pypdf_result.text.strip()) * 1.15:
            liteparse_result.warnings.extend(pypdf_result.warnings)
            return liteparse_result

        pypdf_result.warnings.extend(liteparse_result.warnings)
        return pypdf_result
    except Exception as exc:
        if pypdf_result is not None:
            pypdf_result.warnings.append(f"liteparse_failed: {exc}")
            return pypdf_result
        raise RuntimeError(f"Could not parse PDF {path}: {exc}") from exc


def _extract_with_pypdf(path: Path) -> ParsedDocument:
    if PdfReader is None:
        raise RuntimeError("pypdf or PyPDF2 is required to parse PDF files")

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    sections: List[str] = []
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if not page_text:
            continue
        sections.append(f"--- Page {page_num} ---\n\n{page_text}")

    return ParsedDocument(
        text="\n\n".join(sections),
        backend="pypdf",
        metadata={"page_count": page_count},
    )


def _extract_with_liteparse(
    path: Path,
    ocr_language: Optional[str] = None,
    ocr_server_url: Optional[str] = None,
    allow_npx: Optional[bool] = None,
    cli_path: Optional[str] = None,
    quiet: bool = True,
) -> ParsedDocument:
    command = _resolve_liteparse_command(allow_npx=allow_npx, cli_path=cli_path)
    if command is None:
        raise RuntimeError("LiteParse CLI is not available")

    cli_command = list(command)
    cli_command.extend(
        [
            "parse",
            str(path),
            "--format",
            "json",
            "--ocr-language",
            ocr_language or os.getenv("ENCLAVE_PARSER_OCR_LANGUAGE", "en"),
        ]
    )

    ocr_server = ocr_server_url or os.getenv("ENCLAVE_LITEPARSE_OCR_SERVER_URL")
    if ocr_server:
        cli_command.extend(["--ocr-server-url", ocr_server])

    if os.getenv("ENCLAVE_LITEPARSE_NO_OCR", "false").lower() == "true":
        cli_command.append("--no-ocr")

    max_pages = os.getenv("ENCLAVE_LITEPARSE_MAX_PAGES")
    if max_pages:
        cli_command.extend(["--max-pages", max_pages])

    dpi = os.getenv("ENCLAVE_LITEPARSE_DPI")
    if dpi:
        cli_command.extend(["--dpi", dpi])

    if quiet:
        cli_command.append("-q")

    timeout_seconds = int(os.getenv("ENCLAVE_LITEPARSE_TIMEOUT_SECONDS", "180"))
    completed = subprocess.run(
        cli_command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        stderr_tail = completed.stderr.strip().splitlines()
        message = stderr_tail[-1] if stderr_tail else completed.stdout.strip() or "unknown error"
        raise RuntimeError(message)

    payload = json.loads(completed.stdout or "{}")
    pages = payload.get("pages") or []
    sections: List[str] = []
    for page in pages:
        page_number = page.get("page") or len(sections) + 1
        page_text = (page.get("text") or "").strip()
        if not page_text:
            items = page.get("textItems") or []
            page_text = "\n".join(
                item.get("text", "").strip()
                for item in items
                if item.get("text", "").strip()
            )
        if page_text:
            sections.append(f"--- Page {page_number} ---\n\n{page_text}")

    return ParsedDocument(
        text="\n\n".join(sections),
        backend="liteparse",
        metadata={"page_count": len(pages)},
    )


def _resolve_liteparse_command(
    allow_npx: Optional[bool] = None,
    cli_path: Optional[str] = None,
) -> Optional[List[str]]:
    explicit_cli_path = cli_path or os.getenv("ENCLAVE_LITEPARSE_CLI_PATH")
    if explicit_cli_path:
        explicit_path = Path(explicit_cli_path).expanduser()
        if explicit_path.exists():
            return [str(explicit_path)]

    for candidate in ("liteparse", "lit"):
        if shutil.which(candidate):
            return [candidate]

    use_npx = allow_npx
    if use_npx is None:
        use_npx = os.getenv("ENCLAVE_LITEPARSE_ALLOW_NPX", "true").lower() == "true"

    if use_npx and shutil.which("npx"):
        return ["npx", "-y", "@llamaindex/liteparse"]
    return None
