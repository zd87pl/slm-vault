# ADR 0001: One vault engine that owns the key, the index and consent

| | |
|---|---|
| Status | Proposed (Phase 1 foundation). Revision 2, after review round 1 |
| Date | 2026-09-29 |
| Base commit | `2ec68a7` (all `path:line` references are at this commit) |
| Decides | Engine process model, IPC, data root and storage format, vector search path, key hierarchy, consent/audit model, MCP shim, sidecar packaging, migration from today's layout, Phase 1 PR plan |
| Evidence | [ROADMAP.md](../launch-plan/ROADMAP.md) · [research notes](../launch-plan/research/) · [SQLCipher/sqlite-vec spike](../../spikes/sqlcipher-vec/README.md) |

**Names.** The product rename is pending ([ROADMAP.md](../launch-plan/ROADMAP.md), "Rename before launch").

- User-visible names are written `<App>` (display name), `<app>` (slug for directories, socket and CLI) and `<bundle-id>`.
  Code defines them once (`APP_ID`, `APP_NAME`).
- Cryptographic and wire identifiers (HKDF labels, AAD fields, file magics, the IPC protocol name) are **frozen constants
  that do not follow the rename** (§5.1). Renaming the app must not change a key or a file format.

---

## 1. Context, goals and non-goals

### 1.1 The root cause

The roadmap traces four defects to one missing owner. The section "One engine process should own the key, the
index and consent" lists them:

- **The index split.** MCP read `$VAULT_PATH/rag.db` while the GUI and CLI wrote `private_models/<profile>/vault/rag.db`.
  Phase 0 (#23) repointed MCP at the profile index. It still reopens that index in a second process, with its own key read
  (`advanced_vault/mcp_server/agent.py:1-28`).
- **Shell-built consent.** The consent dialog is a subprocess the MCP server spawns (`advanced_vault/mcp_server/consent.py:195-254`;
  argv-only since #18). Consent is therefore decided by whichever process an agent happened to launch.
- **A frozen app cannot serve MCP.** The app points Claude Desktop at a system Python with a `PYTHONPATH` hack
  (`advanced_vault/gui/mcp_setup.py:129-192`).
- **The key sits next to the data.** Five code paths write a random `master.key` beside the database it protects:
  `cli/main.py:26-56`, `mcp_server/server.py:96-125`, `private_models/manager.py:402-412`, `gui/vault_app.py:6898-6908`, and
  the MCP agent through the manager (`mcp_server/agent.py:195-196`). A sixth, `macos_app/vault_app.py:35-45`, goes with the
  legacy cut. No user secret, KDF or keychain is involved ([codebase_audit_core.md](../launch-plan/research/codebase_audit_core.md) Q5).

The audit also found plaintext names, absolute paths, unsalted content hashes, embeddings (in `rag.db`,
`rag.hnsw`/`rag.brute.json` and `~/.enclave/embedding_cache.db`), chat history, activity logs and consent state (Q5). The
README now says so (#22). Phase 1 has to make that untrue.

### 1.2 Goals and non-goals

Goals:

1. **One engine process.** It alone holds the unwrapped data key, reads and writes the encrypted store, runs ingestion,
   retrieval and generation, decides consent and writes the audit log.
2. **Thin clients.** The Tauri UI, the `<app>` CLI and the MCP stdio shim are clients. They get identical answers and
   citations by construction.
3. **Nothing sensitive in plaintext on disk that we control.** That covers the data root, `$HOME` and `$TMPDIR`. The exceptions are listed
   in §4.7 and none is document-derived. This is the Phase 1 exit criterion "Nothing on disk in plaintext except documented metadata".
4. **A user secret.** A random data key is wrapped by an Argon2id passphrase key, an optional OS-keystore key and a
   recovery key. Changing the passphrase does not re-encrypt data.
5. **A locked or stopped vault is closed.** Agents get "open <App> to unlock your vault", never data.
6. **Consent is decided in the vault's own UI.** It is scoped, expiring, quota-limited and audited, and never runs as a shell command.
7. **Safe migration of today's data.** One-shot, resumable, verifiable, and read-only on legacy files until the user confirms removal.

Non-goals for Phase 1:

- **The Tauri UI itself** (Phase 2). Phase 1 fixes the IPC and UI-isolation rules it must follow (§3.5).
- **Retrieval-quality work:** Docling, OCR, reranker, verified citations, Qwen3.5, llama.cpp, ONNX embeddings. These are
  Phase 1 items too, and they plug into the interfaces defined here.
- **Sync, household sharing and mobile** (Phase 5). The per-vault layout and blobs kept outside the index are chosen not to block them.
- **Protecting an unlocked vault from malware running as the same user.** That is not achievable (§10).
- **Secrets management.** `encrypted_kv` is quarantined. §9 only carries its data over.

### 1.3 Amendments to the roadmap

This ADR changes three things the [roadmap](../launch-plan/ROADMAP.md) states:

- **Components kept.** The roadmap's disposition table keeps and refactors `RAGIndex`, `VectorIndex` and a slimmed `enclave_control`.
  This ADR instead *replaces* their storage and runtime with the engine store, an in-engine vector matrix and the consent/audit
  service. It reuses the parsers, the chunker and `EmbeddingEngine`, without its disk cache.
- **Vector search.** The layer table puts "sqlite-vec vectors" in the SQLCipher file and quotes brute force at "5–15 ms per 100k".
  Instead, vectors persist in SQLCipher as BLOB rows and are queried from memory (§4.4). sqlite-vec works inside SQLCipher but is
  not used in Phase 1 (spike §2, §9). That also closes the risk-table item "sqlite-vec inside SQLCipher untested".
- **Recovery kit.** It moves from Phase 5 (capability table) to Phase 1 (§5.5).

---

## 2. Process architecture

```
 ┌──────────────── <App>.app (signed, notarized) ────────────────┐
 │  Tauri shell (Rust)            WebView: library + trust windows│
 │   • spawns + supervises engine  ◄──── per-window capabilities │
 │   • holds owner token (memory)                                │
 │   • OS events: sleep/lock/power                               │
 │        │ owner connection (peer = its own child, verified)    │
 │        ▼                                                      │
 │  <app>-engine (Python, PyInstaller onedir, same Team ID)      │
 │   key custody · store · vector matrix · ingest · generation   │
 │   consent/policy · audit · migrations                         │
 └────────▲──────────────────────────▲───────────────────────────┘
          │ owner (passphrase)        │ agent role (token file)
     `<app>` CLI                 `<app>-mcp` stdio shim  ◄── stdio ── Claude Desktop / Cursor / LM Studio …
```

The engine is a headless asyncio process with these parts:

- **IPC server** (§3), on the event loop.
- **A single writer and a small reader pool.** Every write goes through one writer task and connection, because the engine
  is the only writer. A few reader connections serve FTS5 and metadata. SQLite work runs in a thread pool, which releases the GIL.
- **The vector matrix** (§4.4), held in memory and owned by the writer.
- **One generation worker thread** that owns the LLM runtime.
- **An ingestion scheduler** that runs staged jobs at low priority. Interactive queries preempt it.
- **Key custody** (§5).

**Who starts it**

| Situation | Starter | Lifetime |
|---|---|---|
| Consumer app | The Tauri shell spawns the sidecar (§8.2) | Until the app quits. Closing the window keeps the tray and the engine |
| CLI while the app runs | Nobody: the CLI connects | n/a |
| CLI or dev without the app | `<app> engine start [--foreground]` | Until `<app> engine stop`. Without a UI, consent comes from `<app> consent watch` (§6.2) or existing grants |
| The app starts while a CLI-started engine runs | The shell sees exit code 3, verifies the running engine binary (§3.2), asks the user, SIGTERMs it and spawns its own. It never loops | n/a |
| Flet GUI (PR 11 until Phase 2) | Flet spawns `<app>-engine serve` without an owner token and sends the passphrase from its unlock dialog only to that child (§3.2). If the child exits with code 3, Flet does not connect to the running engine; it asks the user to stop it | Until Flet quits |
| MCP client launches the shim | The shim never starts an engine (§7.4) | n/a |

**Single instance.** An exclusive, non-blocking lock on `<data_root>/engine.lock` (`fcntl.flock`, or `LockFileEx` on Windows) is
held for the engine's lifetime, and `engine.pid` is written next to it. A second engine exits with code 3. Stale sockets are
removed only while holding the lock.

**Locked state.** The engine runs with no DEK.

- Unauthenticated connections get `hello` and `vault.status` only.
- `auth.passphrase` and `auth.recovery` authenticate *and* unlock. `vault.unlock` is owner-only; the shell uses it for passphrase and keystore unlock.
- Data methods return `VAULT_LOCKED`. Agent methods return the "open <App> to unlock" error (§7.4).
- Events that occur while locked (failed auth, agent calls) are buffered in memory, up to 1,000, and written to the audit log at
  the next unlock. They are lost if the engine exits while locked.
- Folder watchers record nothing while locked. A reconciliation scan at unlock catches up, so paths never sit in a plaintext queue.

**Crash and restart**

- **Recovery.** SQLite WAL recovery is automatic. Jobs are rows in the encrypted `jobs` table and resume after unlock; three
  failures park a job as `failed`.
- **Restart policy.** The shell restarts the engine with backoff (1–30 s) and gives up after 5 crashes in 2 minutes, showing
  recent log lines, which never hold content (§4.7).
- **After a restart the vault is locked, and keystore unlock is never automatic.** It needs an explicit click, plus Touch ID or
  the login password in Phase 2 on macOS (§5.4). Otherwise killing the engine would turn an idle lock back into an unlocked vault.
- **Orphan protection.** The engine exits when stdin reaches EOF, which happens when the shell dies. Headless engines are the
  explicit exception.

**Indexing** runs only while unlocked, in stages ([document_rag_sota.md](../launch-plan/research/document_rag_sota.md) §10):

1. Text layer and FTS5, in seconds. The document is searchable at once.
2. Embeddings, in minutes.
3. OCR of hard pages, contextual headers and extraction, in hours, and only on AC power.

**Idle lock versus indexing (decided).**

- **The idle timer** (§5.8) is extended while ingestion jobs are pending on AC power, by at most **2 hours after the last owner
  activity**. The tray shows "Unlocked while indexing N files · Lock now".
- **Immediate lock.** Sleep, screen lock, quit and manual lock always lock at once. Jobs pause and resume at the next unlock.
- **Accepted consequence.** Stage 3 runs while the user is around or within that window, so a large backlog takes several
  sessions. The Library shows what is waiting.
- **Rejected alternative.** Keeping the vault unlocked until indexing finishes would leave it open overnight.

---

## 3. IPC

### 3.1 Transport

| OS | Transport | Location | Access control |
|---|---|---|---|
| macOS | Unix domain socket | `<runtime_dir>/engine.sock`, where `<runtime_dir>` = the per-user Darwin temp dir (`confstr(_CS_DARWIN_USER_TEMP_DIR)`, what `$TMPDIR` points to) + `<app>/`. Not `~/Library/Caches/TemporaryItems`, which cleaners purge | Directory `0700`. The engine refuses a symlinked or foreign-owned directory. Socket `0600`; peer uid via `getpeereid()`, peer pid via `LOCAL_PEERPID` |
| Linux | Unix domain socket | `$XDG_RUNTIME_DIR/<app>/`, fallback `/tmp/<app>-<uid>/` with the same checks | Same; `SO_PEERCRED` |
| Windows (Phase 4) | Named pipe | `\\.\pipe\<app>-engine-<user SID>` | DACL for the user SID only, `FILE_FLAG_FIRST_PIPE_INSTANCE`, `PIPE_REJECT_REMOTE_CLIENTS` |

- **No loopback HTTP** (§12). The MCP security guidance prefers stdio or restricted IPC for local servers
  ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §4).
- **Path overrides.** Signed builds ignore `<APP>_DATA_DIR`, `<APP>_RUNTIME_DIR` and `PYTHON*` variables, which a
  `launchctl setenv` could inject. Only dev builds honour them.

### 3.2 Authentication and roles

Every connection starts with `hello`, then authenticates.

| Role | Can | Credential |
|---|---|---|
| `owner` | Everything: unlock/lock, ingest/delete, settings, consent decisions, grants, audit, raw documents for the viewer, export | (a) The **owner token**: 32 random bytes the shell writes to the engine's stdin at spawn. It is never on disk, and it is accepted only if the engine's parent passes a code-signature check (§8.2). (b) Or `auth.passphrase` / `auth.recovery`, which verify by unwrapping a header slot and also unlock. The CLI and Flet use (b) |
| `agent` | Only `agent.*` (§3.4), always through policy and consent | The **agent token**: 32 random bytes in `<runtime_dir>/engine.token` (`0600`), new on every engine start |

**Clients authenticate the engine before sending anything.** Same-user code could otherwise kill the engine, take the lock, bind
the socket and capture a passphrase.

- **Spawning clients: the shell and Flet.** They send the owner token or a passphrase only after checking that the socket's
  peer pid (`LOCAL_PEERPID`, `SO_PEERCRED`, `GetNamedPipeServerProcessId`) is the child they spawned. This works for
  interpreter-run engines too.
- **Connecting clients: the CLI and the shim.** They resolve the peer pid to an executable (`proc_pidpath`, `/proc/<pid>/exe`,
  `QueryFullProcessImageNameW`), and require the installed engine binary with a valid signature for our Team ID or certificate.
- **Scope of that check.** It is meaningful only for **signed frozen builds on macOS and Windows**. An interpreter-run engine
  resolves to `python3.x`, which any same-user script also is. That covers all of Phase 1: pip/venv installs, the CLI, and Flet's
  child. On Linux the check is path-only. In those cases same-user code can impersonate the engine and capture a passphrase typed
  into the CLI. Flet and the shell are protected by the child-pid check, and the CLI warns when it cannot verify.

**Rules**

- `vault.unlock` is owner-only.
- `auth.passphrase` and `auth.recovery` back off exponentially after 5 failures. While unlocked, they verify against
  `meta.header_json` (§5.3), never the file on disk.
- **Serialized derives.** Argon2id derives (up to 1 GiB each) run one at a time from a short queue; excess attempts get `RATE_LIMITED`.
- **`vault.create`** is accepted only while the vault is uninitialized, and never over the agent token. The engine cannot tell
  which client verified it, so any same-user process can call it first. That first-run pre-emption causes denial or confusion,
  not exposure: the vault is empty, and the user cannot unlock a passphrase they never set. Setup shows the creation time, and
  `<app> vault reset` deletes, after confirmation, a vault that has no blobs. Any same-user process could delete those files anyway.
- Tokens are compared with `hmac.compare_digest`.

**Limits.**

- **Agent role.** Anything running as the user can read `engine.token`, so it can reach the agent role. It still gets nothing
  without a grant, and `sensitive` collections always need a fresh click in the trust window (§6).
- **Owner role.** Owner access needs the passphrase or the verified shell. What same-user code can still do is listed in §10.

### 3.3 Protocol

- **Framing.** JSON-RPC 2.0, one message per line (NDJSON), UTF-8, at most 1 MiB per line. Protocol name `"vault-ipc"`, which is frozen.
- **Streaming.** A streaming request (`ask`, `ingest.add`, `docs.read_original`, `events.subscribe`) receives `stream.event`
  notifications `{"id":<request id>,"seq":n,"event":{…}}`, then the normal response with the final result.
- **Cancellation.** `rpc.cancel {"id"}` stops the request at the next checkpoint and returns error `CANCELLED`.
- **Server events.** `events.subscribe` delivers `vault.state`, `consent.requested`, `index.progress`, `jobs` and `unlock.requested`.
- **Errors** carry stable `data.code` values: `VAULT_LOCKED`, `NOT_INITIALIZED`, `AUTH_REQUIRED`, `FORBIDDEN`, `CONSENT_PENDING`,
  `CONSENT_DENIED`, `RATE_LIMITED`, `QUOTA_EXCEEDED`, `KEYSTORE_UNAVAILABLE`, `NOT_FOUND`, `CANCELLED`, `BAD_REQUEST`, `INTERNAL`.
- **Versioning.** `hello {"protocol":"vault-ipc","versions":[1],"client":{kind,name,version}}` returns the chosen version, the
  engine version, capabilities and the vault state.
  - Additive changes do not bump the version, and clients ignore unknown fields and events.
  - Breaking changes bump the major version, and the engine serves N and N-1 for one release.
  - The shim and CLI run from the app bundle (§7.3), so skew is rare.

### 3.4 API surface (v1)

Owner-only unless marked. Parameters and results are abbreviated.

| Method | Params | Result / stream events |
|---|---|---|
| `hello` (any) | `versions, client` | `version, engine, capabilities, vault_state` |
| `auth` | `token` | `role` |
| `auth.passphrase` / `auth.recovery` | `secret` | `role: owner`; unlocks if locked |
| `vault.status` (any) | none | `state`, `vault_id`, `unlock_methods`, `idle_lock_s`, `matrix_ready` |
| `vault.create` (§3.2 rules) | `passphrase` | `vault_id`, `recovery_key` (shown once; must be typed back) |
| `vault.unlock` | `method: keystore/passphrase/recovery, secret?` | `state` |
| `vault.lock` | none | `state` |
| `vault.change_passphrase` | `old, new` | ok |
| `vault.keystore.enable` / `.disable` | `passphrase` | ok |
| `vault.recovery.regenerate` | `passphrase` | `recovery_key` |
| `vault.rotate_data_key` | `passphrase` | new `recovery_key` (type-back), then a job (§5.6) |
| `vault.export_backup` | `path` | job (§4.8) |
| `collections.list/create/update/delete` | `name, sensitivity: normal/sensitive/private` | collections; delete = crypto-erase of every document |
| `docs.list` / `docs.get` / `docs.delete` | `collection?, cursor` / `id` / `id` | metadata; delete per §4.6 |
| `docs.read_original` (stream) | `id, range?` | base64 `chunk` events for the viewer, delivered through a Tauri channel (§3.5) |
| `ingest.add` (stream) / `ingest.cancel` / `ingest.jobs` | `paths[], collection` / `job` / none | job id, `progress{file, stage, n, total}` |
| `watch.add/list/remove` | `path, collection` | watch folders |
| `search` | `query, collections?, k, mode: hybrid/keyword/vector` | hits `{citation, doc, page, snippet, score}`; `keyword_only: true` until the matrix is loaded |
| `ask` (stream) | `question, collections?, conversation?` | `stage` → `sources` (handles before tokens) → `token`… → `verdict` → `{answer, citations[], abstained, conflict}` |
| `citation.open` | `handle` | `{doc, page, char_span, bbox, excerpt}` |
| `conversations.list/get/delete` | `id?` | chat history |
| `agent.ask` / `agent.search` (agent) | `question` / `query, k≤20`, `collections?` | final result only, after policy and consent (§6) |
| `agent.open_citation` (agent) | `handle` | redacted excerpt ≤ 500 chars; always needs consent |
| `agent.list_collections` / `agent.status` (agent) | none | granted collections only / `{state, app_version}` |
| `consent.pending` / `consent.decide` | `request_id, decision, scope?` | requests / ok |
| `grants.list/add/revoke` | `client?, collection, tools, expiry, quota` | grants |
| `audit.query/export/verify` | filters / `format` / none | events / file / chain status (§6.5) |
| `settings.get/set`, `settings.set_runtime` | keys; power and sleep hints from the shell | values |
| `events.subscribe` (stream) | `topics` | events |
| `engine.shutdown` | none | ok |

### 3.5 UI isolation (Phase 2, binding on the Tauri UI)

Document-derived content (PDF.js, Markdown answers) and agent-supplied text are untrusted inside the webview.

- **Two window types with separate Tauri 2 capabilities**, enforced by window label in the Rust command layer:
  - The **library** window renders documents and answers. It may call only `search`, `ask`, `docs.list/get/read_original`,
    `citation.open`, `conversations.list/get`, `ingest.*`, `watch.*` and `collections.list`.
  - The **trust** window renders no document content. It is the only window allowed `vault.*`, `consent.*`, `grants.*`,
    `audit.export`, `vault.export_backup`, `settings.*`, `collections.create/update/delete` (turning a `private` collection
    `normal` exposes it to agents), and every delete (`docs.delete`, `conversations.delete`).
  - Agent-supplied text on consent cards is set with `textContent`, never as HTML or Markdown.
  - The webview never sees the owner token.
- **Markdown.** Rendered with raw HTML disabled and the output sanitized. Links are shown as text and images never load.
- **PDF.js.** `enableScripting: false`, `isEvalSupported: false`, no XFA, loaded from an in-memory `ArrayBuffer`.
- **CSP, with no remote origins:** `default-src 'self'; script-src 'self'; img-src 'self' blob: data:; connect-src ipc:
  http://ipc.localhost; object-src 'none'; frame-src 'none'; base-uri 'none'`.
- **No cacheable URLs.** Document bytes reach the webview only through Tauri channels, never through a URL scheme that WebKit
  could cache on disk.

---

## 4. Data root and storage

### 4.1 Platform directories

| | macOS | Windows | Linux |
|---|---|---|---|
| Data root | `~/Library/Application Support/<App>` | `%LOCALAPPDATA%\<App>` (a multi-GB database must stay out of roaming sync) | `$XDG_DATA_HOME/<app>` |
| Runtime (socket, token) | §3.1 | named pipe; token in `%LOCALAPPDATA%\<App>\run`, user-only ACL | `$XDG_RUNTIME_DIR/<app>` |
| Logs | `~/Library/Logs/<App>` | `%LOCALAPPDATA%\<App>\Logs` | `$XDG_STATE_HOME/<app>/log` |

### 4.2 Layout

```
<data_root>/                        0700
  engine.lock, engine.pid           single instance (§2)
  vaults/<vault_id>/                0700, one vault in v1; per-vault so household vaults need no new layout
    vault.json                      key header, the only plaintext of the vault (§5.3)
    vault.db (+ -wal, -shm)         SQLCipher 4 database
    blobs/<2 hex>/<blob_id>         original files, per-file-key AEAD (§4.5)
    blobs/.tmp/                     ciphertext staging, cleaned at engine start
    parse-tmp/                      plaintext parser scratch, 0700, cleaned at engine start and after every job (§4.7)
  models/                           public model weights
```

Today's per-profile indexes become **collections** in one vault.

### 4.3 The database: one SQLCipher file per vault

The binding is `sqlcipher3` (SQLCipher 4.12, SQLite 3.51, static OpenSSL, wheels for every target). The spike verified that the
file is opaque without the key and that backups stay encrypted. It also verified that `apsw-sqlite3mc` reads and writes the
same format, as a fallback ([spike](../../spikes/sqlcipher-vec/README.md) §1–4).

Connection setup:

```text
PRAGMA cipher_log_level = NONE;       -- first: a wrong key must not log to stderr
PRAGMA key = "x'<hex of K_db>'";      -- K_db = HKDF(DEK) (§5.1); SQLCipher's PBKDF2 is skipped
SELECT count(*) FROM sqlite_schema;   -- fail fast on a wrong key
PRAGMA journal_mode = WAL;  PRAGMA secure_delete = ON;  PRAGMA foreign_keys = ON;
PRAGMA cache_size = -65536;           -- 64 MiB; vectors are not queried through SQLite (§4.4)
```

Extension loading is never enabled.

Schema v1, abridged. Migrations are numbered SQL files, applied at unlock after a `VACUUM INTO` snapshot, which is deleted
after the next successful unlock.

```sql
meta(key PRIMARY KEY, value)   -- schema_version, vault_id, meta_secret, header_json, next_header_hash, embedder id + dim
collections(id, uuid, name, sensitivity CHECK IN ('normal','sensitive','private'), settings_json, created_at)
documents(id, uuid, collection_id, title, source_path, mime, size_bytes, content_mac, blob_id, file_key, key_epoch,
          page_count, status, pipeline_version, created_at, updated_at)
pages(doc_id, page_no, width, height, text_source)          chunks(id, doc_id, ord, page_start, page_end, header, text, char_start, char_end)
chunks_fts = fts5(header, text, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2') + secure-delete=1, synced by triggers
chunk_vectors(chunk_id PRIMARY KEY REFERENCES chunks ON DELETE CASCADE, model_id, vec BLOB)   -- persistence only (§4.4)
anchors(id, chunk_id, doc_id, page_no, kind, char_start, char_end, bbox_json)
entities(id, doc_id, type, value_json, anchor_id, valid_from, valid_to, superseded_by, confirmed_at)
conversations(…) ; messages(…) ; citation_handles(handle PRIMARY KEY, client_key, anchor_id, expires_at)
clients(client_key PRIMARY KEY, claimed_name, install_id, kind, first_seen, last_seen)
grants(id, client_key, collection_id, tools, expires_at, daily_quota, hourly_rate, verbatim_cap, created_via, revoked_at)
consent_requests(id, client_key, method, args_json, collections_json, status, decision, grant_id, created_at, decided_at)
audit_events(seq PRIMARY KEY, ts, kind, actor, client_key, method, collections_json, decision, grant_id,
             request_json, result_json, prev_mac, mac)          -- kind 'checkpoint' after pruning (§6.5)
jobs(…) ; watch_folders(…) ; settings(key PRIMARY KEY, value_json) ; migration_items(…)   -- §9
```

**Settings the spike forced:**

- **FTS5 `secure-delete = 1`.** Without it, a deleted document's tokens survive in the FTS5 index even after `VACUUM`. With it,
  and with `secure_delete = ON`, a delete leaves no row text or tokens in the decrypted pages (spike §4). For `chunk_vectors` BLOB
  rows at 384, 512 and 1024 dims, including rows that overflow a page, the round-2 review found no marker bytes after delete.
  I reproduced that (`check_blob_residue.py`, spike §4).
- **A modest page cache.** Any other connection's commit resets a reader's cache anyway (§4.4). FTS5 tolerates that: at 10k chunks
  a common-term query takes 21–23 ms after an invalidation, against 10–11 ms warm (spike §9).
- **FTS5 at scale.** Common-term and prefix queries grow about linearly with the corpus. The round-2 review measured, at 50k
  chunks, a common term at 53 ms warm and 73 ms after invalidation, and a prefix at 45 and 50 ms. That extrapolates to 100–150 ms
  at 100k, which is over the 100 ms search-as-you-type budget. Search-as-you-type therefore debounces, needs at least 3 characters
  for a prefix, and returns an unranked first page before the ranked one (PR 7).

### 4.4 Vector search: an in-engine matrix, SQLCipher for persistence

**Why not query vectors in SQLite.** In WAL mode, a commit by another connection empties every reader connection's page cache.
An encrypted sqlite-vec scan over 100k × 384 then takes 534–549 ms instead of 41 ms, and the engine commits on nearly every
request (audit rows, `last_seen`, jobs). Measured in spike §9, reproducing the reviewer's experiment. The engine is the only
writer, so the live embeddings stay in its memory.

| | Design | Measured (spike §9, shared 4-vCPU x86) |
|---|---|---|
| Query | numpy float32 matrix (≤ 512 dims) with id and liveness arrays. Top-k is one matrix-vector product plus `argpartition`; collection filters are boolean masks | Top-50: **1.9 ms** at 100k × 384 and **9.6–19.8 ms** at 100k × 1024. Exact results. 30% mask: about the same |
| Persistence | `chunk_vectors` BLOB rows, written by the writer in the chunk's transaction. The matrix is updated after commit: append in place into spare capacity; delete zeroes the row and clears its liveness bit; compaction at lock | One 20-chunk document persists in 0.6–1.1 ms; the in-memory append takes < 0.05 ms; one delete 0.2–0.5 ms |
| Unlock | Loaded in the background after unlock. Until ready, `search` is keyword-only, and says so | 1.2–1.6 s at 100k × 384; 2.9–3.9 s at 100k × 1024 (decryption-bound; 1024-d rows overflow a 4 KiB page) |
| Hybrid | FTS5 top-50 in SQLCipher, matrix top-50, RRF in Python | 1.2–11 ms p50 with a commit before *every* query (10k chunks) |
| Concurrency | Queries hold a shared lock for the product and read rows up to the published count. The writer appends beyond it into spare capacity, and deletes zero rows in place and clear liveness. Growth and compaction take the lock exclusively, copy into a new array, then **zero the old one** before releasing it. Queries drop deleted or `-inf` results when fewer than k rows are valid. BLAS threads are capped so a query cannot starve generation | 1 thread: 6.6–7.5 ms at 100k × 384 |
| Memory | n × dim × 4 bytes of plaintext embeddings while unlocked, e.g. about 200 MiB at 100k × 512. Embeddings can be inverted to approximate text, so they count as content (§5.7). Above 1 GiB (about 500k chunks at 512-d): int8 matrix plus float rescore (unmeasured) | 146 MiB at 100k × 384; 391 MiB at 100k × 1024 |

A changed embedder writes `chunk_vectors` rows with a new `model_id` in the background, then swaps the matrix. Alternatives are in §12.

### 4.5 Original files: per-file AEAD blobs

**Decision.** Originals are stored outside the database. Each blob has its own random 256-bit key, held in `documents.file_key`.
Compared with storing blobs in SQLCipher:

- `vault.db` stays index-sized, so rekey, `VACUUM`, backup and migration do not scale with scans. Rekey takes 2.2 s per 235 MiB (spike §10).
- One document is crypto-erased by deleting its key row and unlinking its blob.
- Blobs can later sync individually while each device rebuilds its own index ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §7).
- **Cost:** blob count, 64 KiB-granular sizes and timestamps are visible, and writes are two-phase.

**Format `vault-blob/1`** (frozen):

- **Header:** magic `AVB1` ‖ version (1 byte) ‖ `blob_id` (16) ‖ segment size (u32, 65,536) ‖ plaintext length (u64).
- **Segments:** AES-256-GCM. Nonce = **11-byte big-endian segment index ‖ 1 flag byte** (`0x00`, or `0x01` on the final
  segment). AAD = the header bytes.
- **Padding.** The final segment is zero-padded to full size. Readers check the authenticated length and that the padding is zero.
- **Properties.** Keys are single-use per file version, so nonces never repeat. Truncation, reordering and swapping segments
  between blobs are all detected.

**Write path.** Encrypt into `blobs/.tmp/<id>`, `fsync`, `rename`, then commit the row. At engine start, `.tmp` and `parse-tmp` are
emptied. At unlock, blobs no row references are deleted, and rows whose blob is missing are marked `damaged`.

### 4.6 Content MACs and deletion

- **Content MAC.** `content_mac = HMAC-SHA256(K_hash, file bytes)` is used for dedupe and change detection. `K_hash` derives
  from `meta_secret`, not from the DEK, so DEK rotation leaves MACs valid (§5.1). Today's unsalted SHA-256
  (`training/rag_index.py:548`) allows "is file X in this vault?" confirmation attacks.
- **Document delete, in one transaction:**
  1. Chunks (the FTS5 delete triggers run with `secure-delete`).
  2. `chunk_vectors`, `anchors`, `entities` and `citation_handles` rows.
  3. The document row, which removes `file_key`; `secure_delete` overwrites it.
  4. Commit, then zero the matrix rows, `PRAGMA wal_checkpoint(PASSIVE)` and unlink the blob. `TRUNCATE` waits for readers,
     so it runs at lock.

  Text the document contributed to `messages`, `audit_events` and `consent_requests` stays. The delete dialog offers to delete
  conversations that cite the document too. Audit rows age out (§6.5).
- **Scope, stated precisely.** Deletion is final **for the live vault**. Copies made before it still contain the document and
  open with any credential valid for that copy: Time Machine or File History backups, APFS local snapshots, explicit exports,
  and a schema-migration snapshot (§4.3) until it is deleted. The delete dialog says so and offers backup exclusion (§4.8). Vault delete removes
  `vault.json` and the keystore item, which crypto-erases the live copy only.

### 4.7 Plaintext on disk and outside our control

| Where | What | Why / control |
|---|---|---|
| `vault.json` | Format, vault id, generation, KDF parameters and salts, wrapped keys, keystore item reference | Needed before any key exists |
| Blob files | Count, sizes rounded to 64 KiB, timestamps | Filesystem metadata |
| `parse-tmp/` | Plaintext from a parser that insists on a file path | Short-lived, emptied at start and after each job. A known gap |
| `engine.lock/.pid/.token`, socket | Coordination; the token is new every start | n/a |
| Logs | Event names, timings, error classes, ids | Filtered by pattern (paths, quoted strings) and tested by pushing marker strings through parser and error paths. Field-name filtering alone is not enough |
| `models/` | Public weights | Not user data |
| MCP client configs | Shim path, `<APP>_CLIENT_ID` | Third-party files |
| **MCP client logs** (e.g. Claude Desktop's MCP logs) | The client may log tool results (answers, snippets, citation excerpts) and the shim's stderr | **Outside our control.** The shim writes no content to stderr. The "Connect" screen tells the user that the client keeps its own logs |
| **The agent's conversation** | Whatever an agent receives, often stored in its cloud history | Outside our control. This is the point of consent (§6) |
| **Legacy `~/.vault`, `~/.enclave`** | Until removal (§9) | The import report lists them |

### 4.8 Backups, and what they keep

- **Explicit export.** `vault.export_backup` writes a `VACUUM INTO` copy of `vault.db` (the spike showed it stays encrypted),
  plus the blobs and `vault.json`. It restores with the credentials valid at export time. `sqlcipher_export` can produce a copy
  under a different key.
- **OS backups** copy only ciphertext. The engine checkpoints the WAL at lock and when idle, so the main file is usually
  self-consistent. The last explicit export is the fallback.
- **What credentials and deletions do not reach.** A backup keeps the `vault.json` it was taken with, so it keeps opening with
  the passphrase, recovery kit or keystore item that was valid then, for the data it holds.
  - Passphrase changes, kit regeneration and document deletion act on the live vault only.
  - Only DEK rotation (§5.6) stops old credentials from opening data written *after* the rotation.
- **Opt-in "Exclude this vault from OS backups".** macOS `NSURLIsExcludedFromBackupKey` on the vault directory, the Windows
  File History exclusion. It is offered at setup and when deleting from a `sensitive` collection. Default off, because losing
  the only copy of life documents is the likelier harm (§12 Q9).

---

## 5. Key hierarchy

### 5.1 Keys and frozen identifiers

```
DEK            32 random bytes, wrapped in each slot of vault.json (§5.3)
 └ K_db      = HKDF-SHA256(DEK, salt=vault_id, info="vault/v1/sqlcipher-key")        SQLCipher raw key
meta_secret    32 random bytes in meta (inside the DB), created with the vault, never rotated
 ├ K_hash    = HKDF-SHA256(meta_secret, info="vault/v1/content-mac")                 content MACs
 └ K_audit   = HKDF-SHA256(meta_secret, info="vault/v1/audit-chain")                 audit chain
file keys      32 random bytes per blob version, in documents.file_key
KEK_pass     = Argon2id(NFKC(passphrase), salt, m, t, p)                             §5.2
KEK_keystore = 32 random bytes held by the OS keystore                               §5.4
KEK_recovery = HKDF-SHA256(recovery secret, salt, info="vault/v1/recovery-kek")      §5.5
```

- **Why.** The DEK is only ever HKDF input. `K_hash` and `K_audit` do not depend on it, so a DEK rotation leaves content MACs and
  the audit chain intact (§5.6).
- **Frozen identifiers.** These live in `engine/constants.py` and never derive from `APP_ID`: the HKDF labels above, `vault-header/1`,
  `vault-blob/1`/`AVB1`, `vault-ipc`, `vault/v1/recovery-check`, and the slot-wrap AAD field names.

### 5.2 Passphrase KDF

**Algorithm.** Argon2id (RFC 9106, v1.3) via `argon2-cffi`, with a 16-byte salt and a 32-byte output. Passphrases are NFKC UTF-8,
at least 10 characters, with a strength meter.

**Calibration**, at vault creation and passphrase change, target 0.5–1.0 s. This is `bench_argon2.py:calibrate`:

1. Set p = min(4, logical CPUs), and start at m = 256 MiB, t = 2.
2. Double m while the derive stays ≤ 1.0 s. The cap is 1 GiB when the OS reports ≥ 15 GiB RAM, 512 MiB at ≥ 7 GiB, and 256 MiB
   otherwise. A "16 GB" machine reports about 15.x GiB.
3. Then raise t until the derive takes ≥ 0.5 s.
4. A machine too slow for 256 MiB at t = 2 within 1.0 s halves m, down to a floor of 64 MiB, and uses t ≥ 3. That is RFC 9106's
   second recommended option.

**Measured.** 1 GiB, t = 2, p = 4 took 0.82 s on the spike box. Under load, the same code picked 512 MiB/t=2 and 256 MiB/t=3
(spike §7). OWASP's 19 MiB floor costs 28 ms, which is far too cheap for an offline-attackable header.

**Rules.**

- **Never lower.** On passphrase change, each parameter becomes max(old, recalibrated). Lowering is an explicit action ("faster
  unlock on this slower machine").
- **Wrapping.** AES-256-GCM with a random 96-bit nonce. AAD is the canonical JSON of `{format, vault_id, slot_type, slot_id,
  dek_id, kdf}`, so editing `vault.json` cannot downgrade parameters or move a slot.
- **CI** tests the calibration logic with a fake clock.

### 5.3 `vault.json`: pending slots and header integrity

```json
{
  "format": "vault-header/1", "vault_id": "3b0d…", "generation": 7,
  "db": {"cipher": "sqlcipher4", "key": "hkdf-raw256"}, "blobs": {"format": "vault-blob/1"},
  "slots": [
    {"id": "p1", "type": "passphrase", "dek_id": "a1…",
     "kdf": {"alg": "argon2id", "v": 19, "m_kib": 1048576, "t": 2, "p": 4, "salt": "b64…"},
     "wrap": {"alg": "aes256gcm", "nonce": "b64…", "ct": "b64…"}},
    {"id": "r1", "type": "recovery", "dek_id": "a1…", "kdf": {"alg": "hkdf-sha256", "salt": "b64…"}, "wrap": {"…": "…"}}
  ],
  "pending": null
}
```

**Writes.** `generation` is informational and unauthenticated; integrity comes from hashes kept inside the encrypted DB.

1. Commit `meta.next_header_hash = SHA-256(new header bytes)`.
2. Write a temp file, `fsync`, `rename`, `fsync` the directory.
3. Commit `meta.header_json` = the exact new header bytes, and clear `next_header_hash`.

**Integrity check at unlock.** Once the DB opens, the file is accepted only if its hash equals SHA-256(`meta.header_json`) or
`meta.next_header_hash`. A match on the latter is a crash between steps 2 and 3, so step 3 is finished.

- **Anything else is tampering**, for example a slot copied from a backup or a replayed old header. The engine warns the owner,
  audits the event and rewrites `vault.json` from `meta.header_json`.
- **Planted slot.** If the slot that unlocked is not in `meta.header_json`, the engine locks again and refuses the session.
- **While unlocked,** `auth.passphrase` and `auth.recovery` verify against `meta.header_json` (§3.2), so a slot planted in the file
  grants nothing over IPC.

**Scope.** Offline use of an old header copy together with the live `vault.db` is undetectable, because both use the same DEK.
After a suspected passphrase or kit compromise, the UI therefore offers DEK rotation (§5.6), not just a passphrase change.
Superseded headers are never kept in the live directory; backups are covered in §4.8.

### 5.4 OS keystore (convenience unlock)

| OS | Phase 1 (`keyring`) | Phase 2 |
|---|---|---|
| macOS | The Keychain item's ACL trusts our signed engine binary, **which any same-user process can execute**, so the slot is a keychain oracle. **Off by default**, labelled "Convenience: apps running as you can unlock this vault" | The shell creates a data-protection keychain item with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` and `SecAccessControl .userPresence`. Every use needs Touch ID or the login password. Offered as "Unlock with Touch ID". The shell passes `KEK_keystore` over the owner connection and never holds the DEK |
| Windows | Credential Manager (DPAPI): no per-app ACL. **Off by default**, same label | Windows Hello gate (`KeyCredentialManager`), Phase 4 |
| Linux | Secret Service: no per-app ACL. **Off by default**, same label | unchanged |

Rules:

- **Explicit use only.** Keystore unlock is owner-only and never automatic, including after an engine restart (§2).
- **No keystore available.** `keyring.backends.fail.Keyring` (what the spike got in a container), an empty chainer, or any
  `keyrings.alt` backend means "no keystore". Unlock is then by passphrase or recovery key only, never through a plaintext keyring.
- **Item gone.** A vanished keystore item returns `KEYSTORE_UNAVAILABLE`. The slot is removed at the next passphrase unlock.

### 5.5 Recovery kit (moved to Phase 1)

- **Secret.** 160 random bits, shown as 32 Crockford-base32 characters in 8 groups of 4.
- **Check group.** A 9th group holds the first 4 Crockford characters of base32(SHA-256(`"vault/v1/recovery-check"` ‖ secret)),
  which catches typos before a derive.
- **Setup.** Printed and not saved by default. Setup requires typing back the last group; Phase 1's CLI does the same.
- **Regeneration** replaces the slot in the live header. Older copies are covered in §4.8.
- **Passkey PRF** can be added later as another slot type (§12).

### 5.6 Changing and rotating

**Passphrase change** needs the old passphrase. It rewraps with never-lowered parameters and increments `generation`. The old
passphrase stops working for the live header only (§4.8).

**Keystore enable/disable and kit regeneration** change slots only.

**DEK rotation** (`vault.rotate_data_key{passphrase}`) runs in two phases:

1. **Prepare.** Generate DEK′ and a **new recovery secret**. The engine never holds the old secret, so the old kit cannot be
   rewrapped. Show the new kit and require type-back.
2. **Pending header.** Write header g+1 with `pending` = DEK′ wrapped under `KEK_pass`, `KEK_keystore` (if the slot exists, with
   user presence on Phase 2 macOS) and the new `KEK_recovery`. Current slots are unchanged.
3. **Rekey.** Quiesce first: close the reader connections, pause the matrix loader and jobs. Then run `PRAGMA rekey` to `K_db(DEK′)`
   on the writer connection. It is one transaction: killed at 15%, 40% and 70%, the file reopened intact under the old key every
   time (spike §10, which had no concurrent readers). After commit, readers reopen under the new key.
4. **Promote.** Write header g+2 with `slots` = the pending slots and `pending` removed, and update `meta`.
5. **Blobs, in the background.** Re-encrypt every blob under a new file key, because the old DEK may have exposed the old keys.
   A per-document `key_epoch` makes this resumable.

**Unlock during a rotation.** The credential unwraps every slot it can, current and pending, and the engine opens the DB with
whichever DEK it accepts. If that is DEK′, it finishes step 4.

- The passphrase works in every crash window, because it has both a current and a pending slot.
- The old kit works until the rekey commits; the new kit works from then on.
- `K_hash` and `K_audit` are unaffected.

**What rotation revokes.** Old credentials can no longer open data written after the rotation. Copies made before it still open
with them (§4.8).

### 5.7 Memory

| Secret | Where | Dropped |
|---|---|---|
| Passphrase / recovery secret | IPC JSON → `bytearray` → KDF | After the KDF. JSON decoding left an immutable `str` that Python cannot wipe |
| KEKs, file keys | `bytearray` | Right after use |
| DEK | One `bytearray`. `K_db` hex exists briefly as a `str` for `PRAGMA key` | On lock or exit; the `str` copies cannot be wiped |
| Vector matrix | numpy arrays (mutable) | `fill(0)` and release on lock |
| Embedder cache | In memory only; **no disk cache** (`use_persistent_cache=False`) | Cleared on lock |
| SQLCipher key and page cache | C heap | On close. `cipher_memory_security = ON` (off by default) wipes, and may `mlock`. If `RLIMIT_MEMLOCK` (8 MiB default on Linux) blocks it, wiping continues without locking (measured in PR 3) |
| Chunks, answers, LLM KV cache | Python objects, model runtime | On lock: finish or cancel jobs, close connections, reset generation state, drop caches, `gc.collect()` |

Python cannot reliably zeroise `bytes` or `str` ([pyca/cryptography](https://cryptography.io/en/latest/limitations/)). The README
must not claim "key zeroing".

**Hardening:** `RLIMIT_CORE = 0`; `prctl(PR_SET_DUMPABLE, 0)` on Linux, also in the Tauri shell, which holds the owner token; on
macOS, the hardened runtime without `get-task-allow`.
FileVault, BitLocker or LUKS is recommended because swap can hold pages.

### 5.8 Lock triggers

- **Idle timeout.** 15 minutes without *owner* activity. Agent calls do not reset it. It is extended while indexing on AC power
  by at most 2 hours (§2).
- **Immediate.** Sleep, screen lock, quit and manual lock. The shell observes the OS events and sends `vault.lock`.
- **Headless engines** use the idle timeout only.

---

## 6. Consent and policy

### 6.1 Model

**Grants.** Every `agent.*` call except `agent.status` needs a grant. A grant is
`(client_key, collection or *, tools ⊆ {ask, search, open_citation, list_collections}, expires_at, hourly_rate, daily_quota,
verbatim_cap)`. There are no "all tools forever" grants: that is what users click just to dismiss prompts
([ROADMAP.md](../launch-plan/ROADMAP.md), moment three), and it is what `consent.py:478-482` does today.

| Sensitivity | Agent access |
|---|---|
| `normal` | Grants of up to 30 days |
| `sensitive` (IDs, medical; suggested at creation) | Grants last **until the next lock**. `open_citation` always prompts |
| `private` | Invisible to agents |

**Global limits** apply across all claimed identities, because renaming a client resets per-client limits. Defaults: 60 agent calls
a minute, 10 open consent prompts, and at most one `unlock.requested` notification a minute.

### 6.2 Prompts

1. **Request.** A call without a covering grant creates a `consent_requests` row and a `consent.requested` event. The event
   carries the claimed client, the method, the exact arguments, the collections, and what would be returned.
2. **Coalescing.** Requests with the same (client, method, collection) attach to the open card as "+N more".
3. **The card**, in the trust window (§3.5): Allow once · Allow for 1 h / 1 day / 30 days (or "until lock" for `sensitive`) · Deny · Always deny.
4. **Waiting.** The call waits up to 55 s, then returns `CONSENT_PENDING` ("The user has been asked in <App>; retry after they respond").
5. **No approver.** Without a UI, **`<app> consent watch`** (owner, in a terminal) approves or denies requests, and `<app> grants
   add/list/revoke` manages grants (PR 8). With no owner client subscribed at all, the call returns `CONSENT_DENIED`.
6. **MRTR.** On spec 2026-07-28 the shim may add an MRTR `input_required` ("Approve in <App>, then continue"). That is a courtesy
   only: the calling agent's UI may auto-approve ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §1).

### 6.3 Client identity is claimed, not proven

A stdio server sees only a self-asserted `clientInfo` (in `initialize` on 2025-11-25, or in `_meta` on 2026-07-28), a spoofable
parent process and its launch config. Today's heuristics (`consent.py:309-358`) collapse to `"unknown"`.

- **Client key.** `client_key = hash(claimed name, install_id)`.
  - `<app> mcp install` writes a random `install_id` into the client config as `<APP>_CLIENT_ID`. That tells installs apart and
    allows revoking one. It does not stop another local process from reusing it.
  - A `.mcpb` bundle is static, so it cannot carry a per-install id. Those installs appear as `<client> (extension)` and share one key per client name.
- **Display.** The UI and audit log show identities as *claimed*.
- **"Always deny"** is a convenience that renaming bypasses. The controls are narrow grants, expiry, global limits, `sensitive`
  prompts and the audit log.

### 6.4 Extraction resistance: hooks now, detectors later

| Hook | Phase 1 | Later |
|---|---|---|
| `pre_retrieval` | Per-client and global rate limits; grant quotas | RAG-CT single-record detection ([mcp_security_trust.md](../launch-plan/research/mcp_security_trust.md) §5) |
| `post_retrieval` | Drop hits outside the grant or in `private`; at most 10 chunks of agent context | Anomaly scoring |
| `post_generation` | Verbatim cap: if more than 40% of the answer's 8-grams appear in the retrieved chunks, truncate and flag. Strip links and images | Presidio + GLiNER redaction |
| `open_citation` | Random handles bound to `client_key`, 24 h expiry, ≤ 500 chars, 20 a day | Redaction |

### 6.5 Audit log

- **Where.** `audit_events` in the encrypted database, replacing today's plaintext JSONL (`activity_logger.py:152,196`).
- **What.** Agent calls (with the full question), consent decisions, grant changes, unlocks and locks, exports, settings changes,
  and buffered pre-unlock events (§2).
- **Retention.** 180 days. Pruning inserts a `checkpoint` row that carries the seq and mac of the last pruned row, and
  verification starts from the newest checkpoint. An "export activity log" follows Apple's Intelligence Report model.
- **What the chain proves**, where `mac = HMAC-SHA256(K_audit, prev_mac ‖ canonical(row))`:
  - **It detects** insertion, modification or reordering of rows in the middle of the log, by code that can write the database but
    lacks `K_audit`. In practice that means bugs.
  - **It does not detect** truncation of the tail, a deleted un-checkpointed WAL, or a restored older `vault.db`.
  - **It gives nothing** against a holder of the DEK, including the engine itself.
  - SQLCipher's per-page HMAC already detects edits by anyone without the key.
  - Anchoring the head `(seq, mac)` outside the data directory at each lock would detect rollback. That is deferred.
- **Kill switch.** `agents.enabled = false` (today's `enclave_control` kill switch) returns `FORBIDDEN` to every agent call, audited.

---

## 7. The MCP shim

### 7.1 Shape

- **A translator.** `<app>-mcp` is a stdio MCP server with no crypto, storage or model; it only turns tool calls into `agent.*` IPC.
- **SDK and spec.** Python MCP SDK 2.x (`MCPServer`; [codebase_audit_core.md](../launch-plan/research/codebase_audit_core.md) Q6), pinned
  `>=2.2,<3`. It targets spec **2026-07-28** and keeps **2025-11-25** compatible ([ROADMAP.md](../launch-plan/ROADMAP.md)). PR 9 tests
  both with an SDK 1.x client and a 2026-07-28 client; if one server cannot serve both, the shim branches on the protocol version.
- **Lightweight.** Every client window starts its own shim, so the shim imports only the IPC client.
- **Connections.** It connects lazily per call, re-reading `engine.token` on each (re)connect because the token changes every engine
  start, and it verifies the engine executable first (§3.2).

### 7.2 Tools (static, read-only)

| Tool | Input | Structured output |
|---|---|---|
| `<app>_ask` | `question`, `collections?`, `response_format` | `{answer, citations: [{handle, document, page}], abstained, conflict, generated_by: "local model"}` |
| `<app>_search` | `query`, `collections?`, `limit ≤ 20` | `{results: [{handle, document, page, snippet}]}` |
| `<app>_open_citation` | `handle` | `{document, page, excerpt}` (redacted, ≤ 500 chars) |
| `<app>_list_collections` | none | `{collections: [{name, document_count}]}` (granted only) |
| `<app>_status` | none | `{state, app_version, setup_hint?}` |

- **Annotations.** All tools carry `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true` and `openWorldHint: false`,
  and return an `outputSchema` plus text.
- **Static text.** Descriptions and server `instructions` are fixed at build time. A test compares them byte for byte with the
  checked-in manifest, which blocks tool poisoning. Release manifest hashes are published in Phase 3.

### 7.3 Packaging, entry points and discovery

- **Binary.** The shim is the engine's PyInstaller build in shim mode, launched as `Contents/MacOS/<app>-mcp`.
- **Entry points.**
  - PR 9 adds a **new** entry point, `<app>-mcp`.
  - **`enclave-mcp` keeps serving the legacy server until PR 11**, when the GUI writes through the engine. From then on it is an
    alias of the shim. Flipping it earlier would make MCP read different data than the GUI writes, recreating the defect #23 fixed.
- **Registration.**
  - Claude Desktop gets a signed `.mcpb`. PR 9 verifies whether its manifest can reference the installed shim or must embed a launcher.
  - Other clients get `<app> mcp install --target …`, which keeps #17's backup and refuse-on-parse-error behaviour.
  - Legacy entries are matched by key `enclave` or by a command running `enclave-mcp` or `advanced_vault.mcp_server`, and replaced only
    after migration.

### 7.4 Error semantics

The shim never returns data from anywhere but the engine, never caches it and never writes content to stderr.

| Situation | Tool result |
|---|---|
| No engine | `isError`: "<App> isn't running. Ask the user to open <App>." |
| `VAULT_LOCKED` | `isError`: "The <App> vault is locked. Ask the user to unlock it in <App>." The engine emits a rate-limited `unlock.requested` |
| `CONSENT_PENDING` / `CONSENT_DENIED` | "Waiting for the user to approve this in <App>" / "The user has not allowed this" |
| `RATE_LIMITED` / `QUOTA_EXCEEDED` | Retry-after |
| Incompatible engine or failed engine check | "Update <App>" / "Could not verify the <App> engine" |
| `<app>_status` | Always answers: `not_running`, `locked` or `unlocked` |

The shim launching the app (`open -g -b <bundle-id>`) is off by default (§12).

---

## 8. Packaging with Tauri

### 8.1 Engine build

- **Build.** PyInstaller **onedir**, never onefile: onefile unpacks an ad-hoc-signed framework that the hardened runtime rejects
  after re-signing ([consumer_ux_patterns.md](../launch-plan/research/consumer_ux_patterns.md) Q9–Q10). Nuitka is evaluated in PR 13.
- **Placement.** The tree goes under `Contents/Frameworks/<app>-engine/`, with launchers in `Contents/MacOS/`, verified by PR 13.
- **Signing.** Sign inside-out: every Mach-O with the same Developer ID Team ID, `--options runtime` and `--timestamp`. Wheel binaries
  arrive linker-signed ad hoc with no Team ID, so re-signing is mandatory. They link only `libSystem`; OpenSSL is static (spike §1).
- **Entitlements.** None to start with. `allow-unsigned-executable-memory` is added only if PR 13 proves cffi needs it. Never
  `disable-library-validation` or `allow-dyld-environment-variables`.
- **Environment.** Signed builds ignore `<APP>_*` overrides and `PYTHON*` environment variables (§3.1), verified in PR 13.
- **Size.** Under about 200 MB without models; `sqlcipher3` adds 6.6 MB. sqlite-vec is not bundled.

### 8.2 Supervision

1. **Spawn.** The shell runs `<app>-engine serve --owner-token-stdin` and writes the token to stdin, keeping stdin open.
2. **The engine verifies its parent** before accepting the token:
   - **macOS:** `SecCodeCopyGuestWithAttributes` for `getppid()`, then `SecCodeCheckValidity` against
     `anchor apple generic and certificate leaf[subject.OU] = "<TEAMID>" and identifier "<bundle-id>"`, then a re-check that
     `getppid()` is unchanged.
   - **Windows:** the parent image must be inside the install directory and Authenticode-signed with our certificate.
   - **Linux:** the parent's `/proc/<ppid>/exe` must be the installed shell binary (path only).

   On failure, the token is refused and owner access needs the passphrase. A same-user process that runs our signed engine therefore
   cannot become owner and use the keystore slot.
3. **Ready line.** The engine prints `{"ready":true,"socket":…,"protocol":1,"pid":…}` on stdout **before** importing the ML stack,
   which loads lazily, so first launches beat the 20 s timeout. Logs go to files, never stdout.
4. **Shell check.** The shell verifies that the socket's peer pid is its child (§3.2) and only then authenticates.
5. **Restart and exit.** Backoff restarts, and the exit-code-3 handling (§2). On quit: `engine.shutdown`, wait 5 s, then
   SIGTERM or `TerminateProcess`. Closing stdin also stops the engine.
6. **System events.** The shell forwards sleep, screen-lock and power events (§5.8).

### 8.3 Updates

The engine updates atomically with the signed app, through the Tauri updater or Sparkle 2
([consumer_ux_patterns.md](../launch-plan/research/consumer_ux_patterns.md) Q10). Schema migrations run as described in §4.3.

---

## 9. Migration from today's layout

### 9.1 What exists today (at `2ec68a7`)

The root is `~/.vault`. The CLI has `--vault-path` and MCP reads `$VAULT_PATH`; the GUI hard-codes `~/.vault` (`gui/vault_app.py:234`).
Items marked *(secret)* hold credentials or keys; **plaintext** means readable without any key.

| Path | Written by | Contents |
|---|---|---|
| `private_models/<p>/profile.json` | GUI, `model create` | **Plaintext**: name, description, system prompt, keywords, model, adapter paths and adapter key paths |
| `private_models/<p>/vault/master.key` *(secret)* | `manager.py:402-412` | **Plaintext** 32 bytes, `chmod 0600` after write |
| `private_models/<p>/vault/rag.db` | `training/rag_index.py:327-366` | `documents`: **plaintext** name, absolute `source_path`, unsalted SHA-256, `{"folder"}` metadata and timestamps; `content` = ChaCha20-Poly1305(text, AAD = doc id). `chunks`: text sealed (AAD = chunk id), **plaintext** float32 embedding (`:627`). Original bytes are not stored |
| `…/vault/rag.hnsw` + `rag.meta.json`, or `rag.brute.json` | `vector_index.py:234-262, 362-376` | **Plaintext** vectors and id maps |
| `private_models/<p>/{models, trained_adapters, wdva_packages, keys}` (`keys/` is *secret*) | GUI, `train-adapter` | Model cache; adapters; adapter keys (**plaintext**) |
| `.active_private_profile`, `.language_pref`, `.onboarding_v1_complete` | GUI | UI state |
| `activity_export.{csv,json}` | GUI activity export (`gui/vault_app.py:10529`) | **Plaintext** agent query previews. A user file: listed in the report, never deleted automatically |
| `master.key` (root) *(secret)* | `cli/main.py:26-56`, `server.py:96-125`, `vault_app.py:6898-6908` | Key for `vault.db` and older builds' root `rag.db` |
| `vault.db` | `encrypted_kv/storage.py:72-120` | **Plaintext** `service`, `entry_type`, `tags`, `description`, `folder` and timestamps; `encrypted_data` = hex ChaCha20-Poly1305 (AAD = service). `FOLDER` entries are folder-password hashes, not secrets (`encrypted_kv/models.py:22`) |
| `rag.db` + index files (root) | pre-#23 `LocalAgent` | Profile-index format under the root key; only counted today (`agent.py:288-306`) |
| `chat_history_<p>.json`, `question_history.json` | `vault_app.py:244, 426-433` | **Plaintext** chats and questions |
| `activity.jsonl` | `activity_logger.py:152, 196` | **Plaintext** agent query previews. Every line is also written to `events.db` (`activity_logger.py:199-212`) |
| `control_plane/events.db` | `enclave_control/runtime.py:29` | **Plaintext** events. It bulk-imports existing `activity.jsonl` and `sheriff/audit.jsonl` at first start (`runtime.py:175-186`) |
| `permissions.json` | `consent.py:279` | **Plaintext** per-app `auto_approve` / `deny_always` |
| `session.json` *(secret)* | `gui/auth_screen.py:416-427, 497-505` | **Plaintext Supabase access and refresh tokens** |
| `models/` | `LocalAgent` (`agent.py:312`) | Model cache |
| `backups/`, `adapters/*.wdva` | `prosumer/adapter_backup.py:101, 267` | Adapter backups (lab) |
| `sheriff/`, `wallet/`, `local_adapters/`, `local_datasets/`, `training_queue/`, `datasets/` | Sheriff, wallet, training | Handled by the Phase 1 cut PRs; the importer leaves them in place |
| `~/.enclave/policies.toml` | `enclave_control/config.py` | **Plaintext** kill switch and allow-lists |
| `~/.enclave/embedding_cache.db` | `training/embeddings.py:72, 348` | **Plaintext** embeddings keyed by a 16-hex text hash; survives document deletion |
| `~/.enclave/query_cache.db`, `~/.enclave/kv_cache/` | `training/kv_cache.py:61, 250` | **Plaintext** queries and responses, if that dead code ever ran |
| `~/.enclave/adapters/` | `mlx_trainer.py:132`, `mlx_lora_backend.py:207` | Trained adapters (lab) |
| `~/.enclave/config.env` *(secret)* | `gui/config_loader.py:18-24` | May hold `RUNPOD_API_KEY`, `RUNPOD_QA_API_KEY`, `SUPABASE_ANON_KEY` |
| Model caches | `$HF_HOME`; `~/Library/Application Support/Enclave/models` or `~/.cache/enclave/models` (`local_inference.py:51-58`); `~/.cache/enclave` (`local_inference.py:261`) | Public weights |
| Client configs | `gui/mcp_setup.py:184-192` | `{command: <python>, args: [-m, advanced_vault.mcp_server], env: {VAULT_PATH, PYTHONPATH}}` |

### 9.2 The importer

`<app> migrate [--from DIR] [--dry-run] [--resume] [--verify] [--remove-legacy]`, also offered at first run. It finds legacy roots
from `--from`, `~/.vault`, and the `VAULT_PATH` in existing client configs.

**Read-only by construction.**

- **Readers.** Small raw readers open legacy databases with `sqlite3.connect("file:…?mode=ro", uri=True)`. If a hot journal or WAL
  exists, they read a copy placed in `parse-tmp/`.
- **Decryption.** They decrypt directly with ChaCha20-Poly1305: AAD is the doc id, chunk id or service, and KV fields are hex.
- **Never the legacy classes.** They never instantiate `RAGIndex`, `EncryptedKVStore` or `EmbeddingEngine`, which create files,
  alter schemas (`rag_index.py:314-325` drops tables on old schemas), rewrite `rag.hnsw` and create `embedding_cache.db`.
- **Test.** A test hashes every file under the legacy roots before and after an import.

**Steps**

1. **Inventory (dry run).** Every row of §9.1 with counts and sizes, missing sources, and a free-space check of 1.5 × (originals +
   legacy databases). The report says what will be imported, left in place or dropped, and why.
2. **Create the new vault first**, with passphrase, recovery kit and optional keystore.
3. **Documents.** Profiles become collections. For each legacy document:
   - If `source_path` exists, **re-ingest from source** (`imported_from_source`). If the file's mtime is newer than the legacy
     `updated_at`, it is also marked "changed since it was indexed".
   - Otherwise store the decrypted text as a **text-only** document (`imported_text_only`).
   - The onboarding sample documents (`gui/vault_app.py:2318-2362`) are skipped.
   - Legacy embeddings and index files are never read.
4. **Chats.** Chat and question history JSON become `conversations`.
5. **Settings.** `.language_pref` carries over.
6. **Secrets KV.** Non-`FOLDER` entries go to a `legacy_secrets` table that no agent method reaches; the owner can list and export them.
   `FOLDER` entries (password hashes for a removed feature) are dropped and listed.
7. **Consent.**
   - "Always allow" entries are **not** carried over: all tools, no expiry, heuristic identity.
   - `deny_always` for a legacy id (`claude-desktop`, `cursor`, `vscode`) becomes a deny rule only for the exact `clientInfo`
     names on a list maintained with the shim. Substrings are never used: "code" would also match Claude Code, Codex and OpenCode.
     Unmapped ids are listed in the report and not carried over.
   - From `policies.toml`, only the kill switch carries over.
8. **Activity.** Import `control_plane/events.db`, deduplicated by `event_key`. Read `activity.jsonl` only if `events.db` is
   missing, because every jsonl line is already in `events.db`. Rows get `actor = legacy`, after an `import` marker that starts the chain.
9. **Lab data, left in place.** Adapter packages, adapter keys, `trained_adapters/`, `~/.enclave/adapters/`, `~/.vault/backups/`,
   `adapters/*.wdva` and training data are never moved or deleted. The importer never deletes a key without its package. An
   optional export writes package plus key together.
10. **Credentials.**
    - `session.json` is deleted at removal. The report says its tokens stay valid at Supabase until they expire.
    - `config.env` is never deleted automatically. The report names the keys that are set (names only) and recommends rotating them.
11. **Client configs.** Back up each client config and replace legacy entries with the shim (§7.3).

**Resumable.** Every unit is a `migration_items` row inside the new vault, processed in its own transaction, so `--resume` skips
finished units.

**Verifiable** (`--verify`, which also runs at the end):

- Each legacy document id maps to exactly one outcome (`imported_from_source`, `imported_text_only` or `failed(reason)`), and counts
  match per profile.
- For text-only imports, `HMAC(K_hash, stored text) == HMAC(K_hash, legacy text)`.
- Each KV entry round-trips.

**Removal**, only after verification *and* the user's confirmation:

- **Removed:** the listed index, cache and log files. That is each profile's `vault/rag.db`, `rag.hnsw`/`.meta.json`/`.brute.json`
  and `vault/master.key` (the index key only, never adapter keys); `profile.json`, unless it references adapters; the root `rag.db` and its index files; `vault.db`
  and the root `master.key`, once both of its users are verified; the chat JSON; `activity.jsonl`; `control_plane/`;
  `permissions.json`; `session.json`; and `~/.enclave/{embedding_cache.db, query_cache.db, kv_cache/, policies.toml}`.
- **Never removed:** lab data (step 9), `config.env`, `activity_export.*`, model caches and `~/.vault` itself.
- **"Keep a copy for 30 days"** moves only those files to `~/.vault/.migrated-<date>/`.
- **Model cache.** If the product keeps the name "Enclave", the legacy macOS model cache *is* `<data_root>/models`; the importer detects
  this and leaves it alone.
- **No secure-erase claim.** On APFS, SSDs and in backups, old copies may persist, and the UI links to deleting local snapshots.

**Failures.** A missing key or a corrupt database marks that profile's items `failed` and the import continues. Bad tags are reported
per item. A full disk stops cleanly and can resume. If vault creation fails, nothing was written. The Flet GUI runs only as an
engine client after migration (PR 11).

---

## 10. Threat model summary

| Adversary / situation | Protected? | How / why not |
|---|---|---|
| Offline disk theft or a copied data dir, vault locked | **Yes**, subject to passphrase strength | Everything is SQLCipher or per-file AEAD. `vault.json` and blob metadata are visible. One guess costs one Argon2id derive (about 1 GiB, 0.8 s here) |
| Backups, snapshots and exports | **Partly** | Encrypted, but they open with the credentials valid when taken, and hold deleted documents (§4.8). Only DEK rotation protects data written afterwards. Backup exclusion is opt-in |
| Another local non-admin user | **Yes** | `0700`/`0600` modes, peer-uid checks, user-only pipe DACL |
| Admin or root | **No** | Memory access, keyloggers |
| Same-user malware, vault **locked** | **Partly** | It can keylog the passphrase. **Signed frozen builds on macOS and Windows:** it cannot become owner through our binaries, because a parent-signature check guards the owner token (§8.2) and clients verify the engine before sending secrets (§3.2). **Interpreter-run engines (all of Phase 1) and Linux:** it can impersonate the engine and capture a passphrase typed into the CLI; the shell and Flet are protected by their child-pid check. Phase 1 keystore slots (off by default) are readable by same-user code on every OS; on Phase 2 macOS the keystore needs Touch ID or the password on every use. A slot planted in `vault.json` is rejected (§5.3) |
| Same-user malware, vault **unlocked** | **No** | It reaches the agent role; consent still applies. It can read engine memory where the OS allows (Windows; Linux blocks it with `PR_SET_DUMPABLE=0`, macOS with the hardened runtime). It can drive the UI where accessibility access has been granted (TCC on macOS) |
| Hijacked agent via MCP | **Partly** | Read-only tools, answers rather than files, default deny, scoped and expiring grants, global and per-client limits, verbatim cap, `sensitive` prompts, `private` invisibility, audit. **It cannot stop an authorised agent from learning what it asks about** |
| Prompt injection from documents | **Partly** | The synthesis model has no tools or network. Documents are delimited as data, links and images are stripped, and tool text is static. Misleading answers remain possible; citations make them visible |
| Script injection in the webview (malicious PDF or answer) | **Mostly** | Library-window script cannot call consent, grant, export, unlock or delete commands (§3.5). It can read what that window can show |
| Plaintext outside our control (MCP client logs, agent history) | **No** | Disclosed at "Connect". This is what consent governs |
| Forensic recovery of deleted documents, live vault | **Mostly** | Per-file keys, FTS5 `secure-delete`, `secure_delete`, zeroed matrix rows. Old encrypted pages may survive on SSD, useless without the DEK |
| Tampering with the audit log | **Weak** | Detects mid-log edits by non-key-holders only. Not truncation, rollback, or anyone holding the DEK (§6.5) |
| Supply chain | **Partly** | Lockfile, no runtime `pip`/`npx`, signed builds; SBOM and Sigstore in Phase 3 |

This seeds `docs/THREAT_MODEL.md`, which replaces `docs/architecture/CRYPTOGRAPHIC_SPECS.md` in Phase 3.

---

## 11. Implementation plan (Phase 1)

New code lives in `advanced_vault/engine/`, and moves wholesale at the rename. It never imports `advanced_vault.gui`. New
dependencies are `sqlcipher3`, `argon2-cffi`, `keyring` and `platformdirs`, plus `pywin32` in Phase 4, each pinned in the uv lockfile by
the PR that first needs it. "Marker scan" means the test that pushes marker strings through a flow and then searches every file
under a **sandboxed `$HOME`, `$TMPDIR` and data root**.

| # | PR | Needs | Reuses / replaces | Tests beyond unit | Exit |
|---|---|---|---|---|---|
| 1 | **Paths, lock, logging**: platformdirs, runtime-dir checks, single-instance lock and pid, pattern log filter, overrides ignored in signed builds | none | New | Lock contention; hostile runtime dir; markers pushed through error paths never reach logs | `<app> engine paths` |
| 2 | **Keys**: frozen constants, `vault.json` (slots, pending), Argon2id slot (calibration, never-lower), recovery slot and check group, keystore slot (off by default) + null store, passphrase change | 1 | Replaces the `master.key` writers (removed in PR 12) | Tampered AAD, downgrade, slot swap; fake-clock calibration; `fail.Keyring` → no slot; header fuzzing | 100% branch coverage of `keys/` |
| 3 | **Store v1**: SQLCipher factory (`K_db`, pragma order, no extensions), schema v1 with `meta_secret` and `chunk_vectors`, migration runner, blob store (§4.5), crypto-erase delete, content MACs, header integrity check, two-phase DEK rotation | 2 | Replaces `RAGIndex` storage (`rag_index.py:314-366`), `vector_index.py` | Spike crypto and residue checks; blob tamper, truncation, reorder; rotation killed at every step with concurrent readers (quiesce and reopen); header tampering and planted slots rejected | Marker scan clean |
| 4 | **IPC**: UDS server, NDJSON JSON-RPC, roles, streaming and cancel, peer checks, **client-side engine verification**, `vault.create` rules, auth backoff; client library | 3 | New | Impersonating engine refused by the CLI and shim; wrong-uid peer; frame limits; cancel; 20 clients | `<app> status` over IPC |
| 5 | **Lifecycle and vault API**: `serve` with parent-signature check and early ready line, `vault.*`, idle lock with the indexing extension, pre-unlock event buffer, `events.subscribe`, explicit-only keystore unlock | 4 | Replaces `VaultCLI` key handling | Owner token refused from an unsigned parent; restart comes back locked; agent calls do not reset idle | `<app> engine start/unlock/lock/status` |
| 6 | **Ingestion**: staged jobs, watch folders with reconciliation, `docs.*`, collections, `parse-tmp`; embedder interface with `use_persistent_cache=False` forced and memory cache cleared on lock | 5 | Reuses `parsing/`, the chunker (`rag_index.py:368-519`), `EmbeddingEngine` (ONNX later) | Round trip; kill mid-ingest then resume; delete leaves no residue; nothing recorded while locked | Marker scan clean, including `~/.enclave` |
| 7 | **Retrieval and `ask()`**: vector matrix (background load, writer-updated), hybrid FTS5 + matrix RRF, streamed `ask`, citation handles; inference moved to `engine/llm/` | 6 | Replaces `PrivateModelSession.ask` (`manager.py:555-627`), `LocalAgent.query` | Parity across UI, CLI and agent paths; matrix equals the DB after crash and restart; keyword-only until loaded; fewer than k valid rows; FTS5 at 50k–100k chunks with debounce, minimum prefix and unranked-first (§4.3) | No `advanced_vault.gui` imports under `engine/` |
| 8 | **Consent, policy, audit**: grants, requests and coalescing, global and per-client limits, sensitivity, extraction hooks, audit chain with checkpoints, kill switch, **`<app> grants add/list/revoke` and `<app> consent watch`** | 5, 7 | Replaces `consent.py`, `activity_logger.py`, `enclave_control` for the new path | Default deny; expiry; quotas; `sensitive` until lock; `private` invisible; chain checks as scoped in §6.5 | Every agent call audited |
| 9 | **MCP shim** on SDK 2.x as a **new `<app>-mcp` entry point**; `enclave-mcp` untouched; `.mcpb` manifest (unsigned) | 4, 6, 7, 8 | New | Contract tests on 2026-07-28 and 2025-11-25; locked and not-running; manifest byte match; token re-read after an engine restart | Claude Desktop cites a document, approved via `consent watch` |
| 10 | **Importer** with raw read-only legacy readers (§9.2) | 3, 6 | New; legacy classes never instantiated | Fixture generated by today's code (2 profiles, KV with `FOLDER`, `events.db` + jsonl, adapters, `session.json`, missing sources); legacy tree hashes unchanged; kill → `--resume`; injected mismatch caught | Dry-run, import, verify and remove on the fixture |
| 11 | **Flet GUI as an engine client**: spawns the engine and unlocks with the passphrase; adapter covering `ingest_paths`, `add_document`, delete, `list_documents`, `search`, `ask`, `get_status`, `ensure_model_ready`, profiles → collections; migration prompt; **`enclave-mcp` becomes an alias of the shim, and `mcp install` writes shim entries** | 9, 10 | Keeps Flet usable until Phase 2 | **Roadmap exit test**: GUI ingest → shim answers with a citation | The GUI opens no database or key itself |
| 12 | **Delete legacy data paths** (key writers, `private_models` storage, `RAGIndex` storage, `vector_index.py`, embedding and query caches, legacy consent, activity and `enclave_control`) | 11 | Removal | CI grep gates: no `master.key`, no `sqlite3.connect` outside `engine/store` and `engine/migrate/legacy`, no `bash -c`, no `use_persistent_cache=True` | Legacy code only in the importer |
| 13 | **Frozen-build CI, macOS arm64**: onedir engine and shim, re-sign every Mach-O, hardened runtime, overrides ignored; smoke test | 3 (store smoke); 9 (full smoke) | Replaces `enclave.spec` | Frozen build: create, ingest, query via the shim | De-risks §8 before Phase 2 |

**Order.**

- The critical path runs 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 11 → 12.
- PR 10 runs in parallel after 6.
- PR 13 starts after 3 and extends after 9.
- PR 8's policy tables and CLI can begin after 5; its generation hooks need 7.
- The retrieval-quality track (ONNX embeddings, reranker, Docling and OCR, verified citations, Qwen3.5 and llama.cpp, the golden
  evaluation set) plugs into PR 6 and PR 7 interfaces.

**Flet GUI during the transition.** Through PR 10, Flet and `enclave-mcp` stay on the legacy path, and the importer is CLI-only behind a
flag. PR 11 switches both at once. After that there is one data path, and Tauri replaces Flet in Phase 2 on the same IPC.

---

## 12. Alternatives considered and open questions

### Alternatives considered

| Option | Verdict | Reason |
|---|---|---|
| Today's per-row ChaCha20-Poly1305 with plaintext metadata and vectors | Rejected | Leaks names, paths, hashes and embeddings; FTS5 cannot index ciphertext |
| sqlite-vec (vec0) as the query path | Rejected for Phase 1 | Page-cache invalidation by any other connection's commit: 534–549 ms instead of 41 ms at 100k × 384 (spike §9). It works inside SQLCipher (spike §2); a candidate for on-disk ANN if vaults outgrow RAM |
| Separate `vectors.db` with batched commits | Not chosen | Would narrow invalidation but not remove it, and is unmeasured. The matrix is faster and simpler |
| Owner-connection-only vector queries on the writer connection | Rejected | Serialises reads behind writes, and the cache still has to hold the whole table |
| DuckDB 1.4 with AES-GCM | Rejected for the store | No incremental BM25 comparable to FTS5; a second engine to secure ([document_rag_sota.md](../launch-plan/research/document_rag_sota.md) §4) |
| LanceDB | Rejected | Encryption at rest is Enterprise-only |
| `apsw-sqlite3mc` | Fallback | Same file format in both directions (spike §1); `sqlcipher3` is DB-API compatible |
| Blobs inside SQLCipher | Rejected | §4.5 |
| `K_hash`/`K_audit` from the DEK with key epochs in the chain | Rejected | Every rotation would recompute MACs and complicate verification; a random `meta_secret` avoids both |
| DEK rotation keeping the old recovery kit | Impossible | The engine never holds the recovery secret; rotation issues a new kit (§5.6) |
| Separate SQLCipher files per sensitivity tier | Deferred | Separately lockable `sensitive` collections, at the cost of cross-database queries |
| gRPC | Rejected | Toolchains and HTTP/2 on both sides; JSON-RPC matches MCP and debugs with `socat` |
| Loopback HTTP with a token | Rejected | Reachable by every local user; DNS rebinding |
| Key custody in the Rust shell | Rejected for Phase 1 | Contradicts one owner. The keystore/Touch ID part does move to Rust (§5.4) |
| Keystore-only unlock | Rejected | "The key must never sit next to the data"; no recovery path |
| Keeping the vault unlocked until indexing finishes | Rejected | It would stay open overnight; bounded 2-hour extension instead (§2) |

### Open questions for the owner

1. **Name, bundle id and CLI name.** PR 1 can land with placeholders, but real values are needed before PR 11 writes the new layout
   for users. Directory names, the keychain service and the socket path derive from them, and changing them later means another
   migration. The frozen crypto identifiers (§5.1) are unaffected.
2. **Windows data root.** `%LOCALAPPDATA%` rather than `%APPDATA%`?
3. **Secrets KV.** Keep a non-agent `legacy_secrets` table with export, or export only and drop the feature?
4. **Engine lifetime and shim launching.** Should the engine keep running in the tray with the window closed (proposed: yes, with idle
   lock)? May the shim launch the app (proposed: no)?
5. **Locking defaults.** Idle lock 15 minutes, the indexing extension capped at 2 hours on AC, lock on screen lock and sleep. Acceptable?
6. **Touch ID in v1.** Phase 2's keychain item needs the keychain-access-groups entitlement and a provisioning profile. Should v1 ship
   with it, or with passphrase unlock only (keystore off, as in Phase 1)?
7. **Recovery kit mandatory** at setup (type-back), or skippable with a persistent warning?
8. **Passkey (PRF) unlock.** It needs native `AuthenticationServices` on macOS 15+. Schedule it before sync?
9. **OS backup exclusion.** Offered opt-in, default off (§4.8). Should the default be on for `sensitive` collections? That would need
   a separate vault per tier, which is also deferred.
10. **Flet GUI.** Adopt PR 11, or freeze Flet and ship Phase 1 as CLI plus MCP only?
11. **Legacy credentials.** Delete `session.json` at removal and never touch `config.env` (proposed)?
