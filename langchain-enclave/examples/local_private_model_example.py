"""
Example: Local-first private model workflow with LangChain Enclave.

This example shows how to:
1. Ingest local files into the encrypted private RAG index
2. Chat over the files locally
3. Use the same vault for secrets and knowledge

If ENCLAVE_CONTEXT_DIR is not set, the script creates a few sample files in a
temporary directory so you can run it immediately.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from langchain_enclave import (
    LocalEnclaveClient,
    LocalEnclaveKnowledgeRetriever,
    LocalEnclaveSecretProvider,
)


def _prepare_context_dir() -> Tuple[Path, Optional[object]]:
    context_dir = os.getenv("ENCLAVE_CONTEXT_DIR")
    if context_dir:
        path = Path(context_dir).expanduser()
        if path.exists():
            return path, None

    temp_dir = tempfile.TemporaryDirectory()
    base = Path(temp_dir.name)
    base.joinpath("project_notes.md").write_text(
        "# Project Notes\n\n"
        "We chose Stripe for webhook reliability and developer experience.\n"
        "The launch checklist includes docs, security review, and customer support.\n",
        encoding="utf-8",
    )
    base.joinpath("roadmap.txt").write_text(
        "Q2 focus: private file chat, local policies, and OpenClaw integration.\n"
        "Q3 focus: adapter tuning and team sharing.\n",
        encoding="utf-8",
    )
    return base, temp_dir


def main() -> None:
    vault_path = os.getenv("ENCLAVE_VAULT_PATH", "~/.vault")
    context_dir, temp_dir = _prepare_context_dir()

    print("Initializing local Enclave runtime...")
    client = LocalEnclaveClient(vault_path=vault_path)

    print(f"Ingesting private files from: {context_dir}")
    ingest_result = client.ingest_directory(str(context_dir))
    print(f"Ingested: {ingest_result['ingested_count']} files")

    try:
        model_status = client.load_model()
        print(f"Local model loaded: {model_status['model_loaded']}")
        print(f"Backend: {model_status['backend']}")
        if model_status.get("model_name"):
            print(f"Model: {model_status['model_name']}")
    except Exception as exc:
        print(f"Local model unavailable, using extractive fallback: {exc}")

    # Store and retrieve a secret locally
    secret_tool = LocalEnclaveSecretProvider(vault_path=vault_path, client=client)
    client.store_secret(
        service="stripe",
        content="sk_live_example_local_secret",
        tags=["payment", "local-demo"],
        description="Local demo secret",
    )
    print(f"Secret lookup: {secret_tool._run(service='stripe')[:8]}...")

    # Query the private files
    answer = client.chat("Why did we choose Stripe and what is the launch plan?")
    print("\nPrivate file answer:")
    print(answer["answer"])

    retriever = LocalEnclaveKnowledgeRetriever(vault_path=vault_path, client=client)
    docs = retriever.get_relevant_documents("Summarize the roadmap")
    print("\nRetriever output:")
    print(docs[0].page_content)

    if temp_dir is not None:
        temp_dir.cleanup()


if __name__ == "__main__":
    main()
