# OpenClaw Enclave Plugin

This package turns Enclave into a local-first privacy layer for OpenClaw.

The design goal is simple: OpenClaw can ask questions and request actions, but the actual private context stays inside the local Enclave broker. Raw files, leases, and adapter state remain on the machine unless the user explicitly chooses otherwise.

## What It Does

- Ingests local files into the encrypted context index.
- Chats over local files through the existing Enclave runtime.
- Uses Sheriff for consent, lease-based reads, and path protection.
- Reports local WDVA adapter readiness so private-model workflows can grow from RAG into personalization.

## What It Does Not Do

- It does not use the cloud backend by default.
- It does not expose raw vault contents directly to OpenClaw.
- It does not treat ACP as the privacy boundary.

## Files

- `package.json`: Node package metadata and OpenClaw extension hook.
- `openclaw.plugin.json`: Plugin manifest and config schema.
- `src/index.js`: OpenClaw tool registration and bridge client.
- `scripts/enclave_bridge.py`: Local Python runtime bridge for ingest/chat/sheriff/adapter tasks.

## Local Setup

You need:

- Node 18+
- Python 3.10+
- This repository checked out locally

Install nothing else for the plugin skeleton itself. The bridge uses the repo's Python modules directly.

## Registering In OpenClaw

Point OpenClaw at this directory as a native plugin package. The plugin entry is `src/index.js` and the manifest is `openclaw.plugin.json`.

If your OpenClaw build expects a `definePluginEntry(...)` wrapper, keep `registerWithApi(api, config)` as the core integration point and wire that wrapper around it.

Important config fields:

- `vaultPath`: local vault root used by Enclave
- `profileName`: default Private Language Model profile for OpenClaw
- `pythonBin`: Python interpreter used for the bridge

## Suggested First Workflow

1. Ingest a folder of private docs.
2. Ask `enclave.chat` about those docs.
3. Run `enclave.scan` before exposing sensitive paths.
4. Use `enclave.protect` on directories that should always require consent.
5. Check `enclave.adapters` to see whether a local WDVA personalization pass makes sense.

## WDVA And The Private Language Model Concept

The Private Language Model concept here is not "fine-tune everything first." It is:

- Encrypted local retrieval for immediate context.
- WDVA adapters for learned behavior, style, and domain knowledge.
- Sheriff policies for consent and revocation.

That gives you a useful progression:

1. Add files and chat locally.
2. Learn which files and domains matter.
3. Turn approved interactions into adapter training data.
4. Fine-tune a small local MLX model on the Mac only when the pattern is stable enough.

## Bridge Commands

The bridge can also be run directly for smoke testing:

```bash
python3 scripts/enclave_bridge.py status --vault-path ~/.vault --profile-name openclaw
python3 scripts/enclave_bridge.py ingest --vault-path ~/.vault --profile-name openclaw ~/Documents/private-notes
python3 scripts/enclave_bridge.py chat --vault-path ~/.vault --profile-name openclaw "What are the main themes?"
python3 scripts/enclave_bridge.py scan --vault-path ~/.vault --paths ~/Documents
```

## Notes

- The plugin is intentionally dependency-light.
- The OpenClaw-facing surface should stay narrow.
- If you add new tools later, prefer local bridge operations over cloud calls.
