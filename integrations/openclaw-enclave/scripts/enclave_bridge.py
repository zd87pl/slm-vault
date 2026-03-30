#!/usr/bin/env python3
"""
Local Enclave bridge for OpenClaw.

This bridge stays local-first:
- Ingests files into the encrypted RAG index
- Chats against local context
- Uses Sheriff for consent/lease-based file reads
- Reports WDVA adapter readiness

The script prints JSON to stdout so a plugin host can consume it safely.
"""

from __future__ import annotations

import argparse
import os
import sys
import json
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def add_repo_to_path() -> None:
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def load_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(errors="ignore")


def collect_files(paths: list[str], max_files: int) -> list[Path]:
    allowed_suffixes = {
        ".txt",
        ".md",
        ".rst",
        ".py",
        ".json",
        ".yaml",
        ".yml",
        ".csv",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".pdf",
    }

    files: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in allowed_suffixes and path not in seen:
                files.append(path)
                seen.add(path)
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if len(files) >= max_files:
                    return files
                if candidate.is_file() and candidate.suffix.lower() in allowed_suffixes and candidate not in seen:
                    files.append(candidate)
                    seen.add(candidate)
    return files


def json_out(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def build_sheriff(vault_path: str):
    add_repo_to_path()
    from advanced_vault.sheriff.core import SheriffCore

    return SheriffCore(vault_path=vault_path)


def build_private_model_manager(vault_path: str):
    add_repo_to_path()
    from advanced_vault.private_models import PrivateModelManager

    return PrivateModelManager(root_path=str(Path(vault_path).expanduser() / "private_models"))


def open_private_model_session(vault_path: str, profile_name: str, create: bool = False):
    manager = build_private_model_manager(vault_path)
    try:
        manager.get_profile(profile_name)
    except FileNotFoundError:
        if not create:
            return manager, None
        manager.create_profile(
            name=profile_name,
            description="OpenClaw local private profile",
        )
    return manager, manager.open_session(profile_name)


def cmd_status(args: argparse.Namespace) -> int:
    private_model = {
        "mlx_available": False,
        "recommended_model": None,
        "local_adapters": [],
        "profile_name": args.profile_name,
        "profile_exists": False,
    }

    try:
        add_repo_to_path()
        from advanced_vault.training import check_mlx_available, get_recommended_model
        from advanced_vault.training import MLXTrainer

        private_model["mlx_available"] = check_mlx_available()
        private_model["recommended_model"] = get_recommended_model(args.memory_gb)

        try:
            trainer = MLXTrainer(output_dir=str(Path(args.vault_path).expanduser() / "adapters"))
            private_model["local_adapters"] = trainer.list_adapters()
        except Exception:
            private_model["local_adapters"] = []
    except Exception:
        pass

    manager, session = open_private_model_session(
        args.vault_path,
        args.profile_name,
        create=False,
    )
    if session is not None:
        try:
            status = session.get_status()
            profile = manager.get_profile(args.profile_name)
            private_model["profile_exists"] = True
            private_model["attached_wdva_adapters"] = [
                adapter.to_dict() for adapter in profile.wdva_adapters
            ]
        finally:
            session.close()
    else:
        status = {
            "profile": {
                "name": args.profile_name,
                "description": "",
                "model_name": None,
                "wdva_adapters": [],
            },
            "document_count": 0,
            "chunk_count": 0,
            "active_adapters": [],
        }
        private_model["attached_wdva_adapters"] = []

    status["private_model"] = private_model
    status["vault_path"] = str(Path(args.vault_path).expanduser())
    json_out(status)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    _manager, session = open_private_model_session(
        args.vault_path,
        args.profile_name,
        create=True,
    )
    assert session is not None
    files = collect_files(args.paths, args.max_files)
    ingested = []

    try:
        for file_path in files:
            try:
                text = load_text(file_path)
            except Exception as exc:
                ingested.append({"path": str(file_path), "success": False, "error": str(exc)})
                continue

            if not text.strip():
                ingested.append({"path": str(file_path), "success": False, "error": "empty content"})
                continue

            doc = session.add_document(
                name=file_path.name,
                content=text,
                source_path=str(file_path),
                metadata={
                    "source_path": str(file_path),
                    "tags": args.tags,
                },
            )
            ingested.append(
                {
                    "success": True,
                    "id": doc.id,
                    "name": doc.name,
                    "chunks": len(doc.chunks),
                    "path": str(file_path),
                }
            )
    finally:
        session.close()

    json_out(
        {
            "success": True,
            "count": len([item for item in ingested if item.get("success")]),
            "files": ingested,
            "profile_name": args.profile_name,
        }
    )
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    _manager, session = open_private_model_session(
        args.vault_path,
        args.profile_name,
        create=True,
    )
    assert session is not None
    try:
        result = session.ask(
            question=args.question,
            top_k=args.top_k,
            max_tokens=args.max_response_tokens,
            temperature=args.temperature,
        )
    finally:
        session.close()

    if result.get("warning") in {"engine_start_failed", "model_unavailable"}:
        json_out(
            {
                "success": False,
                "error": result.get("answer"),
                "warning": result.get("warning"),
                "profile_name": args.profile_name,
                "sources": result.get("sources", []),
            }
        )
        return 1
    json_out({"success": True, "profile_name": args.profile_name, **result})
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    sheriff = build_sheriff(args.vault_path)
    summary = sheriff.scan_risk(paths=args.paths or None, max_files=args.max_files)
    json_out(summary.model_dump(mode="json"))
    return 0


def cmd_protect(args: argparse.Namespace) -> int:
    sheriff = build_sheriff(args.vault_path)
    rules = sheriff.protect_now(args.paths)
    json_out({"count": len(rules), "rules": [rule.model_dump(mode="json") for rule in rules]})
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    sheriff = build_sheriff(args.vault_path)
    content = sheriff.read_with_lease(
        subject_app="openclaw-enclave",
        resource=args.resource,
        lease_id=args.lease_id,
        redact=args.redact,
    )
    json_out({"success": True, "resource": args.resource, "content": content})
    return 0


def cmd_adapters(args: argparse.Namespace) -> int:
    add_repo_to_path()
    output_dir = Path(args.vault_path).expanduser() / "adapters"
    manager, session = open_private_model_session(
        args.vault_path,
        args.profile_name,
        create=False,
    )
    profile_adapters = []
    if session is not None:
        try:
            profile = manager.get_profile(args.profile_name)
            profile_adapters = [adapter.to_dict() for adapter in profile.wdva_adapters]
        finally:
            session.close()
    try:
        from advanced_vault.training import check_mlx_available, get_recommended_model, MLXTrainer

        trainer = MLXTrainer(output_dir=str(output_dir))
        adapters = trainer.list_adapters()
    except Exception as exc:
        json_out(
            {
                "success": False,
                "error": str(exc),
                "mlx_available": check_mlx_available(),
                "recommended_model": get_recommended_model(args.memory_gb),
                "adapters": [],
                "profile_adapters": profile_adapters,
                "profile_name": args.profile_name,
                "output_dir": str(output_dir),
            }
        )
        return 1
    json_out(
        {
            "success": True,
            "mlx_available": check_mlx_available(),
            "recommended_model": get_recommended_model(args.memory_gb),
            "adapters": adapters,
            "profile_adapters": profile_adapters,
            "profile_name": args.profile_name,
            "output_dir": str(output_dir),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    def add_common_options(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--vault-path", default=os.environ.get("ENCLAVE_VAULT_PATH", "~/.vault"))
        parser.add_argument(
            "--profile-name",
            default=os.environ.get("ENCLAVE_PROFILE_NAME", "openclaw"),
        )
        parser.add_argument("--memory-gb", type=int, default=24)

    parser = argparse.ArgumentParser(description="Local Enclave bridge for OpenClaw")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status")
    add_common_options(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("ingest")
    add_common_options(p)
    p.add_argument("paths", nargs="+")
    p.add_argument("--tags", nargs="*", default=[])
    p.add_argument("--max-files", type=int, default=2000)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("chat")
    add_common_options(p)
    p.add_argument("question")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--max-context-tokens", type=int, default=1500)
    p.add_argument("--max-response-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.7)
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("scan")
    add_common_options(p)
    p.add_argument("--paths", nargs="*", default=[])
    p.add_argument("--max-files", type=int, default=2000)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("protect")
    add_common_options(p)
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_protect)

    p = sub.add_parser("read")
    add_common_options(p)
    p.add_argument("resource")
    p.add_argument("lease_id")
    p.add_argument("--redact", action=argparse.BooleanOptionalAction, default=True)
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("adapters")
    add_common_options(p)
    p.set_defaults(func=cmd_adapters)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.vault_path = str(Path(args.vault_path).expanduser())
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
