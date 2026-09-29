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

Lower priority: the experimental parts of the desktop app that are not part of
the local-only story (cloud sync, RunPod Q&A, the backend status check, and the
MCP server's `langchain_*` tools); the fix may be to remove them. The legacy
cloud-training stack, sync backend, browser extension, LangChain package and
OpenClaw plugin are no longer on `main` (they are kept, unmaintained, on the
`legacy-archive-2026-09-29` branch) and are out of scope.

The weaknesses listed below and in the README's
[Known Limitations](README.md#known-limitations) are already known; please
report them only if you find they are worse than described.

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
  and an app you opt in to the `vault_*` tools gets stored secrets from
  `vault_recall`. "Always Allow" does not expire.
- **Apps are not reliably told apart.** App identity is inferred from
  environment variables or, if the optional `psutil` package is installed,
  the parent process name. `psutil` is not an Enclave dependency, so on a
  default install every MCP client — Claude Desktop and Cursor included — is
  `unknown`: all of them get the `default` policy and share one consent
  decision, so "Always Allow" for one approves all of them. The shipped
  `default` policy allows the document tools but none of the `vault_*`
  secrets tools. Earlier versions put `vault_*` in `default`; Enclave replaces
  such a file if it was never edited (keeping a backup), and `enclave doctor`
  warns when an edited one still gives `vault_*` to unidentified apps.
- **Opting an app in to the secrets tools trusts a label.** The documented
  opt-in ([Letting one app use the secrets tools](README.md#letting-one-app-use-the-secrets-tools))
  sets `MCP_CLIENT` in that app's MCP config and adds `vault_*` tools to its
  entry in `policies.toml`. Any program that starts the MCP server with the same
  label gets that entry, as does, with `psutil` installed, any parent process
  whose name matches. This keeps your secrets from apps and agents you have
  not opted in; it does not stop software already running as you, which can
  read the vault directly (see above).
- **Consent and policy changes need a restart.** The MCP server reads
  `~/.vault/permissions.json` and `~/.enclave/policies.toml` only when it
  starts, so revoking access means editing those files and restarting the AI
  app; the desktop app's kill switch likewise reaches a running server only
  after that restart. The desktop app's permission toggles and Revoke button
  are not enforced.
- **Documents can inject instructions.** Retrieved text goes into the local
  model's prompt as-is, so a malicious document can influence the answer an
  agent receives.
- **Downloaded models and packages are trusted.** Models come from Hugging
  Face; some features download packages from npm or PyPI at runtime
  (see the README's [Network access](README.md#network-access)).
