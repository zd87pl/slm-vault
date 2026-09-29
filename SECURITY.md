# Security Policy

## Supported versions

Enclave has no releases yet. Security fixes land on the `main` branch only,
so please check that an issue still reproduces on the latest `main` before
reporting it.

## Reporting a vulnerability

Please **do not** open a public issue, pull request or discussion for a
security problem. Report it privately through GitHub's private vulnerability
reporting:

**https://github.com/zd87pl/slm-vault/security/advisories/new**

A useful report includes the commit you tested, your OS and hardware, steps
to reproduce (a proof of concept if you have one), and what an attacker
gains.

## Scope

In scope:

- **The local vault**: the encrypted RAG index, the secrets store, key
  handling, and anything Enclave writes under `~/.vault` and `~/.enclave`.
- **The MCP server** (`enclave-mcp`) and its tools, including ways to make it
  return data an agent was not allowed to get, or to run commands.
- **Consent and policy enforcement**: consent prompts, `permissions.json`,
  `~/.enclave/policies.toml`, and the activity and audit logs.
- **Cryptography**: ChaCha20-Poly1305 usage, nonces, key generation and
  storage, and adapter package encryption.
- The CLI, desktop app and setup scripts where they touch any of the above.

Lower priority: the experimental and legacy components that are not part of
the local app (`src/`, `advanced_vault/backend/`, `browser-extension/`,
`langchain-enclave/`, `integrations/`). Reports are still welcome, but the fix
may be to archive the component. The weaknesses listed below and in the
README's [Known Limitations](README.md#known-limitations) are already known;
please report them only if you find they are worse than described.

## What to expect

Enclave is a small project maintained on a best-effort basis. There is no
guaranteed response time: we acknowledge reports as soon as we can and keep
you updated in the private advisory. Once a fix is on `main` we aim to
publish a GitHub security advisory crediting you, unless you prefer not to be
named. Please give us a reasonable amount of time to fix the issue before
disclosing it publicly.

## Threat model (current state)

What the code protects against today, and what it doesn't:

- **At-rest encryption covers document text and secret values only.** File
  names, paths, content hashes, embeddings, the embedding cache, chat history
  and logs are stored in plaintext (see
  [What is and isn't encrypted](README.md#what-is-and-isnt-encrypted)).
- **The key is stored next to the data.** Each encrypted database's key is a
  random 32-byte key in a `master.key` file beside it, with no passphrase, key
  derivation or OS keychain. The encryption therefore only helps when a
  database file is copied without its key file.
- **Anyone running code as the same OS user can read an unlocked vault** —
  and today the vault is never locked. The same goes for anyone with a backup
  or sync of the whole folder, or with physical access to an unlocked or
  unencrypted disk. Use full-disk encryption.
- **Keys are not reliably wiped from memory.** Python keeps copies of key
  bytes that cannot be zeroed.
- **An agent you allow can learn what it asks about.** MCP agents get answers
  generated locally instead of files, but answers can quote your documents,
  and `vault_recall` returns stored secrets. Consent is per app and "Always
  Allow" does not expire; app identity is inferred from the calling process
  and can fall back to `unknown`.
- **Documents can inject instructions.** Retrieved text goes into the local
  model's prompt as-is, so a malicious document can influence the answer an
  agent receives.
- **Downloaded models and packages are trusted.** Models come from Hugging
  Face; some features download packages from npm or PyPI at runtime
  (see the README's [Network access](README.md#network-access)).
