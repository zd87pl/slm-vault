## Private Language Models

Enclave's Private Language Model concept turns local AI from a single model into a privacy-first runtime:

- encrypted local context from your files
- WDVA adapters for learned behavior, style, and domain focus
- Sheriff controls for consent, leases, audits, and path protection
- optional OpenClaw and LangChain integrations that use the same local profile

### Core Idea

The product is not "fine-tune first." The progression is:

1. Ingest local files into an encrypted profile.
2. Chat over those files locally with MLX-backed inference.
3. Observe recurring tasks, tone, and domain patterns.
4. Train or attach WDVA adapters when personalization is stable enough.
5. Keep policy, auditability, and revocation in the loop the whole time.

That makes RAG the immediate utility layer and WDVA the durable personalization layer.

### Local Quick Start

```bash
python -m advanced_vault.cli --vault-path ~/.vault model create work \
  --description "Private work assistant" \
  --model-name mlx-community/Qwen2.5-1.5B-Instruct-4bit

python -m advanced_vault.cli --vault-path ~/.vault model ingest work ~/Documents/private-notes

python -m advanced_vault.cli --vault-path ~/.vault model chat work \
  "Summarize the important themes across these files."
```

Useful follow-ups:

```bash
python -m advanced_vault.cli --vault-path ~/.vault model info work
python -m advanced_vault.cli --vault-path ~/.vault model repl work
python -m advanced_vault.cli --vault-path ~/.vault model list
```

If you want to validate the full local demo path before a meeting, run:

```bash
./.venv/bin/python scripts/verify_local_demo.py
```

### WDVA Adapters

WDVA adapters are the personalization layer for a Private Language Model.

Use them when you want the model to learn:

- how you write
- how your team classifies or drafts things
- how to behave for a repeated domain workflow

Keep using encrypted RAG for raw file access. Use WDVA for behavior and specialization.

#### Package An Existing Adapter

```bash
python -m advanced_vault.cli --vault-path ~/.vault model package-adapter \
  /path/to/adapter.safetensors \
  ~/.vault/private_models/work/wdva_packages/style.enc.json \
  ~/.vault/private_models/work/keys/style.key
```

#### Attach It To A Profile

```bash
python -m advanced_vault.cli --vault-path ~/.vault model attach-adapter \
  work style \
  ~/.vault/private_models/work/wdva_packages/style.enc.json \
  ~/.vault/private_models/work/keys/style.key \
  --weight 1.0
```

#### Train A Local WDVA Adapter

Prepare a JSONL dataset using either chat `messages` or `question` / `answer` records, then run:

```bash
python -m advanced_vault.cli --vault-path ~/.vault model train-adapter \
  work work-style /path/to/dataset.jsonl \
  --epochs 3 \
  --batch-size 2 \
  --learning-rate 1e-4
```

This trains locally with MLX, packages the resulting adapter into an encrypted WDVA artifact, and attaches it to the profile.

### OpenClaw Integration

The OpenClaw plugin lives in [`integrations/openclaw-enclave/`](../integrations/openclaw-enclave/).

It uses a named Private Language Model profile as the local trust boundary. The plugin:

- ingests local files into an encrypted profile
- chats against that profile locally
- reports WDVA adapter readiness for the active profile
- uses Sheriff for risk scanning, protection rules, and lease-based reads

The plugin config supports `profileName` so OpenClaw can target a dedicated local profile such as `openclaw`.

### LangChain Integration

The LangChain package lives in [`langchain-enclave/`](../langchain-enclave/).

The local client can now use the same Private Language Model runtime:

```python
from langchain_enclave import LocalEnclaveClient

client = LocalEnclaveClient(vault_path="~/.vault", profile_name="research")
client.ingest_directory("/path/to/files")
result = client.chat("What are the important themes here?")
print(result["answer"])
```

That means the CLI, OpenClaw, and LangChain can all converge on the same local profile instead of fragmenting context across separate stores.

### Recommended Mac Workflow

For MacBook M4 class devices:

- start with 3B or smaller 4-bit MLX models for responsive local chat
- use encrypted RAG first for file access
- add WDVA adapters for tone, extraction, drafting, and domain specialization
- only move to bigger models when your context window or quality needs clearly justify it

### Product Positioning

If you want to present this as a category, the clearest framing is:

`Private Language Model = encrypted local context + local reasoning + WDVA personalization + privacy controls`

That is meaningfully different from both:

- plain local model wrappers, which often ignore policy and audit
- cloud copilots, which often ignore local trust boundaries
