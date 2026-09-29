# Shrink Enclave Before You Launch It

Enclave can't launch as it stands. There is a credible product inside it, but only after roughly half the repository is cut away. The README's lead promise is "drop a document in the app, then ask Claude about it", and it fails in two separate ways. First, a fresh install pulls in MCP SDK 2.2.0, and on that version `enclave-mcp` crashes at startup. Second, even on SDK 1.x the MCP server reads an index that the GUI and CLI never write to. The two code audits also reproduced five more problems:

- a shell injection in the Linux consent dialog that runs before the user decides anything;
- a GUI chat that can never send a message on machines without Apple Silicon;
- an onboarding crash that falls back to a screen with an "Open Investor Demo" button;
- filenames, embeddings and chat history stored in plaintext, although the README says "all data encrypted";
- a torch/CUDA install of about 5 GB, and zero releases.

The plan has five phases:

1. Hotfix and correct the README, in days.
2. Cut down to a core of about 3–4k lines with one data root, one key, one index and one answer pipeline, shared by the GUI, CLI and MCP.
3. Rebuild a Mac-first consumer app on a 2026 stack: Qwen3.5 models sized to the machine's RAM; hybrid search that combines keyword ranking (BM25) with vector similarity, plus a reranker; page citations the software checks automatically; a SQLCipher-encrypted database unlocked by a passphrase (Argon2id) or the OS keychain; and an MCP server on the 2026-07-28 spec with five read-only tools.
4. Launch publicly under a new name. A same-category app called "Enclave AI" already ships on the App Store, and the Homebrew and PyPI names are taken.
5. Add differentiators: structured life data and reminders, then household sharing, sync and mobile.

Position the product in the one gap the competitor scan found: an OSI-licensed desktop vault for life documents, encrypted by default, that gives external agents cited, policy-filtered answers instead of files. Expect a strong Show HN to bring about 2,000–2,500 stars in week one and then fade within ten days. Growth therefore depends on planning three or four more launch moments, not one.

## Enclave today is a Mac demo whose flagship integration is broken

The two internal audits read the code, ran the tests and ran the product end to end on Linux x86_64 with Python 3.11 at commit `40b6d50`. Repository citations below are `path:line` at that commit.

**What works.** A small engine is buried under several stacked product pivots, and parts of it hold up:

- Profiles can be created, and txt, md and PDF files can be ingested into a per-profile SQLite index.
- Chunk text in that index is encrypted correctly: ChaCha20-Poly1305 with random 96-bit nonces, with the row ID bound in as associated data (`advanced_vault/training/rag_index.py:212-251`).
- Dense retrieval with e5-small found the right document in live runs (scores of 0.86 and 0.933).
- The `enclave_control` per-client allow-list is real, and today it is the only effective gate on MCP tools (`advanced_vault/enclave_control/runtime.py:92-109`).
- The MCP test suite passes 49/49 on SDK 1.30.

The auditors put this usable core at **roughly 3–4k lines**. The whole package is **about 57k Python lines in `advanced_vault/`, of which 31k are GUI code and 16,145 sit in one `VaultApp` class** ([GitHub repo](https://github.com/zd87pl/slm-vault)).

**What is broken or overclaimed.** Almost everything the README leads with fails or overclaims. The table lists the blockers the audits reproduced or verified in code.

| Launch blocker | Evidence | Fix | Phase |
|---|---|---|---|
| MCP server crashes on a fresh install | `pyproject.toml:50` requires only `mcp>=1.0.0`. pip resolves 2.2.0 ([PyPI mcp](https://pypi.org/pypi/mcp/json); 2.0.0 shipped 2026-07-28). `Server.list_tools` no longer exists, so the server raises `AttributeError` at `advanced_vault/mcp_server/server.py:130`. The test run shows 2 failures and 15 errors. `enclave doctor` still prints "Ready to go". | Pin `mcp<2` now. Migrate to SDK 2.x in Phase 1. | 0 → 1 |
| MCP reads a different index than the GUI and CLI | `LocalAgent` opens `$VAULT_PATH/rag.db` (`mcp_server/agent.py:92-125`), but ingest writes to `private_models/<profile>/vault/rag.db` (`private_models/manager.py:301-319`). Reproduced: `list_documents()` returned `[]` and the query returned a made-up answer with `sources: []`. | Point MCP at the profile index now. Move to a single store in Phase 1. | 0 → 1 |
| Shell injection in the Linux consent dialog, before consent | The preview strips `"` and `\` but not `$(…)` or backticks, then runs `bash -c` (`mcp_server/consent.py:255-262, 301-316`). The preview `$(touch PWNED)` created a file and the decision still came back DENY. Reachable through `agent_query` and `vault_recall` arguments, which the LLM writes. Independently confirmed by the owner's coordinator. | Remove the shell path entirely. | 0 |
| Chat never sends without Apple Silicon | `is_model_available()` returns False without MLX (`gui/local_inference.py:181-185`). Send then reopens the download dialog (`gui/vault_app.py:6326-6334`). The CLI fallback, TinyLlama-1.1B, answered "What was Q3 revenue?" by paraphrasing its own system prompt. | Declare Apple Silicon only now. Add a llama.cpp backend in Phase 1. | 0 → 1 |
| Onboarding crashes | `OnboardingFlow` calls `update()` before the control is mounted (`gui/prosumer_components.py:215, 217-231`). The fallback screen reads "Open Investor Demo" and "Runs on this Mac" even on Linux (`gui/localization.py:16-26`). | Remove the investor copy now. New onboarding in Phase 2. | 0 → 2 |
| Plaintext contradicts "all data encrypted" | Stored in clear: names, absolute paths, unsalted content hashes, embeddings, the global embedding cache (which survives deletion), chat history JSON, query logs, and the full arguments of denied calls, including secrets (`rag_index.py:327-339`; `vault_app.py:429-436`; `mcp_server/server.py:653-662`). | Correct the README now. SQLCipher plus a key redesign in Phase 1. | 0 → 1 |
| No user secret; key stored next to the data | Five duplicate writers put a random `master.key` beside `rag.db` (`cli/main.py:35-47`, `mcp_server/server.py:100-113`, `mcp_server/agent.py:92-110`, `private_models/manager.py:304-314`, `gui/vault_app.py:6904-6914`). No KDF, no keychain. | Argon2id + keychain + a wrapped data key. | 1 |
| Install of 4–6 GB | `sentence-transformers` is a core dependency (`pyproject.toml:60`) and pulls torch plus the CUDA stack: 3.1 GB of wheels and a 5.9 GB venv on Linux. | ONNX or llama.cpp embeddings, plus a uv lockfile. | 1 |
| No path for non-developers | 0 releases, 0 tags, PyPI 404. Three overlapping build pipelines, none signed. Install docs tell users to right-click → Open, which macOS Sequoia no longer honours ([Apple Developer News](https://developer.apple.com/news/?id=saqachfa)). | Signed, notarized DMG plus a Homebrew cask. | 2–3 |
| `enclave mcp install` can wipe the user's config | If the existing Claude config fails to parse, it is overwritten with no backup (`gui/mcp_setup.py:195-245`). The README says "merges, never overwrites". | Back up the file and refuse when parsing fails. | 0 |

**The security posture is weaker than the name implies.** Five findings stand out:

- **`vault_recall` leaks secrets.** It returns raw secrets on loose keyword overlap. After consent, an "unknown" client asked "tell me about stripe" and got back `sk_live_REALSECRET123` (`core/hybrid_vault.py:334-356`).
- **Consent is coarse and never expires.** "Always Allow" grants every tool to that app with no expiry (`consent.py:373-378`). The granular `AgentPermission` model, with scopes, expiry and hourly quotas, is never called, so the time-limited access shown in the GUI never expires.
- **Windows consent always returns DENY** (`consent.py:330-345`).
- **Documents can inject prompts.** Retrieved chunks are pasted into the local prompt with no delimiting, and the output goes straight back to the external agent.
- **Code and data are fetched at runtime.** The PDF fallback runs `npx -y @llamaindex/liteparse`, which downloads and executes npm code at parse time. The GUI pip-installs packages at runtime. Each model load makes about 30 Hugging Face Hub requests.

`docs/architecture/CRYPTOGRAPHIC_SPECS.md` describes XChaCha20, HSMs, SGX, zero-knowledge proofs and homomorphic encryption, none of which exists in the code. The README's "key zeroing" cannot work in Python, because immutable `bytes` copies of the key stay alive in several objects.

**Code health confirms the sprawl.** The numbers:

- Tests: 29% line coverage. The "end-to-end" tests mock both the retrieval index and the LLM.
- Lint: 4,252 findings, 87% of them auto-fixable.
- CI: Ubuntu and Python 3.11 only, with no macOS runner, even though MLX is the flagship path.
- GUI: about a quarter of `vault_app.py` (~4,060 lines) cannot be reached, and it contains 187 `except Exception` blocks.
- MCP: the server advertises 28 tools across four unrelated domains (secrets, documents, a file "Sheriff" and a mock wallet).
- Docs: 24 broken links, 28 files that mention RunPod, and a `STATUS.md` claiming "Alpha Release Ready" as of January 2025.
- Licensing: some headers say "All rights reserved" (`prosumer/__init__.py`), which contradicts the Apache-2.0 LICENSE.

The repository has 2 stars and 0 forks ([GitHub repo](https://github.com/zd87pl/slm-vault)). The disposition below removes roughly 25–30k lines and most of the 67 Markdown docs, leaving something contributors can understand.

| Disposition | Components | Why |
|---|---|---|
| Keep and refactor into the core | Parsing; `RAGIndex`, `EmbeddingEngine`, `VectorIndex`; `PrivateModelSession` ingest/ask; a trimmed MCP server and agent; a slimmed `enclave_control` (per-client allow-list and audit); the CLI `model`/`mcp`/`doctor` commands; `MCPSetupHelper`; prosumer categories (without the adapter presets) | This is the path that works |
| Quarantine as an optional "lab" extra | MLX fine-tuning, DPO/GRPO/QAT, both adapter packagers (one derives keys from passwords with a single unsalted SHA-256), the GUI adapter engines; the secrets KV (`encrypted_kv`, `hybrid_vault`, `smart_router`), with no MCP tool that returns raw values | MLX-only and trained on synthetic data; no evaluation shows adapters beat retrieval; adapters can memorize documents |
| Move to archived repos | `backend/` (FastAPI, Supabase, RunPod), `src/` (10.7k lines including genomics), `langchain-enclave/`, `browser-extension/` (calls a hard-coded Railway backend and injects on `<all_urls>`), `integrations/openclaw-enclave/`, `sheriff/`, `wallet/` (mock only) | They contradict the local-only story |
| Delete | The four empty packages (`federated`, `homomorphic`, `threshold_crypto`, `speculative`); `late_chunking.py` (which includes an unused path that sends text to Jina's cloud API); `kv_cache.py`; `FastEmbeddingEngine`; `macos_app/`; `core/runpod_client.py`; the dead consent methods; the stale ROADMAP/STATUS/BASELINE/CRYPTOGRAPHIC_SPECS docs | Dead code and misleading claims |

## The open lane is an encrypted life-document vault that answers agents instead of handing over files

### Generalist chat apps won; nobody owns sensitive paperwork

Growth from 2025 to 2026 went to two kinds of project:

- **General AI workspaces**: Open WebUI (153.5k stars), RAGFlow (91.5k), AnythingLLM (66.6k) and Cherry Studio (52.2k).
- **NotebookLM clones**: by a rough proxy, Open Notebook grew about **12× in twelve months, to 39.6k** ([Open Notebook](https://github.com/lfnovo/open-notebook); [OSS Insight](https://api.ossinsight.io/v1/repos/lfnovo/open-notebook/stargazers/history/?per=month)).

Single-purpose "chat with local docs" apps stalled or died:

- GPT4All has shipped no release since February 2025 ([releases](https://github.com/nomic-ai/gpt4all/releases)).
- Reor is archived ([repo](https://github.com/reorproject/reor)), and so is h2oGPT.
- Rewind was bought by Meta ([9to5Mac](https://9to5mac.com/2025/12/05/rewind-limitless-meta-acquisition/)), and Nexa's Hyperlink was absorbed into Qualcomm ([nexa.ai](https://nexa.ai/)).

That record is the strongest argument against building another generic doc-chat app.

The counter-signal is just as clear:

- **Paperless-ngx** is the household-paperwork document manager. It grew **about 60% in twelve months to 46k stars** and added AI suggestions and document chat in v3 ([repo](https://github.com/paperless-ngx/paperless-ngx); [changelog](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/dev/docs/changelog.md)).
- **OpenAI** built a sandboxed health space, citing **300M+ health questions a week** ([OpenAI](https://openai.com/index/health-in-chatgpt/)). It drew a 310-point HN backlash, "guess who is the product" ([HN 46541533](https://news.ycombinator.com/item?id=46541533)).

So demand for AI over personal paperwork is real. People who want it private are served mainly by a Docker server whose README warns it "should never be run on an untrusted host".

Two structural gaps make the lane open:

- **Every popular local chat app consumes MCP; none serves documents over it.** AnythingLLM, LM Studio and Jan are MCP clients ([AnythingLLM MCP docs](https://docs.anythingllm.com/mcp-compatibility/overview); [LM Studio MCP docs](https://lmstudio.ai/docs/app/mcp)). The personal MCP servers that do exist (Screenpipe, basic-memory, OpenKnowledge, mcpvault) hand over raw notes or screen captures. Screenpipe is source-available rather than open source ([README](https://raw.githubusercontent.com/screenpipe/screenpipe/HEAD/README.md)).
- **Encryption at rest is rare and optional.** Open WebUI still has open issues about it ([#20051](https://github.com/open-webui/open-webui/issues/20051)). Open Notebook's key encrypts only API keys ([README](https://raw.githubusercontent.com/lfnovo/open-notebook/HEAD/README.md)). Local Deep Research is the clean precedent, using SQLCipher with a password-derived key, but it is a research tool ([README](https://raw.githubusercontent.com/LearningCircuit/local-deep-research/HEAD/README.md)).

The table shows what each adjacent product lacks.

| Adjacent product | Has | Missing for this wedge |
|---|---|---|
| Paperless-ngx v3 (GPL-3.0) | Life-document model, OCR, AI suggestions and chat | Desktop install, encryption, MCP server |
| AnythingLLM, Jan, LM Studio, Msty | One-click desktop app, local models, citations | Document schema, default encryption, MCP-server role; users report RAG "unusable" ([#2087](https://github.com/Mintplex-Labs/anything-llm/issues/2087)) |
| Local Deep Research | Password-derived SQLCipher | Wrong domain |
| Screenpipe, basic-memory, OpenKnowledge | MCP server for personal context | Pass raw content through; licensing drift |
| ChatGPT Health, Gemini Notebook | Best health-record and cited-Q&A experience | Cloud only |

**Recommended wedge:** *the private vault for the paperwork that runs your life. Ask about your tax, medical, legal, ID and insurance documents and get page-level citations; get reminded before things expire; and let Claude, Cursor or OpenClaw use your documents without ever handing them the files.*

- **Primary user:** a privacy-conscious person on a 16 GB Apple Silicon Mac who manages a household's paperwork and already uses an AI agent.
- **Secondary user:** the less technical household member, reached later through sharing.
- **What it is not:** a general AI workspace, an agent platform, a secrets manager, a wallet or a fine-tuning lab.

Timing favours the agent angle:

- OpenClaw stores secrets unencrypted and has no default sandbox ([Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)).
- About **26% of 31,000 ClawHub skills** contained vulnerabilities ([All Things Open](https://allthingsopen.org/articles/openclaw-viral-open-source-ai-agent-architecture)).

That makes "the safe way to give your agent your tax documents" a credible pitch.

**The strongest objections, and the answers:**

- *Generalists could add encryption and an MCP-server mode quickly.* The defence is depth in the life-document schema, checked citations and household features, not the feature checkbox.
- *Cloud incumbents will keep improving.* True. But the "answers, not files" MCP design lets users keep a frontier model for reasoning while the data stays local.
- *Local models are weaker.* That also answers the HN question "Why go local unless there's private data involved?" ([HN 44379792](https://news.ycombinator.com/item?id=44379792)): this product exists precisely for private data.

**Keep Apache-2.0.** An OSI license is itself a differentiator here. Open WebUI's branding clause ([license docs](https://docs.openwebui.com/license/)) and Screenpipe's move from MIT to source-available ("FOSS hackers like me feel betrayed", [HN 49024620](https://news.ycombinator.com/item?id=49024620)) both drew backlash.

### Rename before launch, while it still costs nothing

"Enclave" collides on every surface that matters:

- **A direct competitor.** **"Enclave AI" is a private, offline local-LLM assistant with document chat on Mac and iPhone.** It is on the App Store (id 6476614556), runs a Discord and keeps an active blog ([enclaveai.app](https://enclaveai.app/); [App Store](https://apps.apple.com/us/app/enclave-local-ai-assistant/id6476614556)).
- **Package names.** The Homebrew cask `enclave` belongs to Enclave Networks' zero-trust networking app ([cask JSON](https://formulae.brew.sh/api/cask/enclave.json)). PyPI `enclave` is taken ([PyPI](https://pypi.org/project/enclave/)).
- **GitHub.** 1,914 repositories have "enclave" in their name, including an AI companion app called Enclave ([GitHub search](https://github.com/search?q=enclave+in%3Aname&type=repositories)).
- **Meaning.** In security vocabulary "enclave" means a hardware trusted execution environment (TEE), such as Apple Secure Enclave, SGX or Nitro. That invites skepticism about a product that uses none.
- **Inconsistent use inside the repo.** The repo is `slm-vault`, the CLI calls itself "Personal Vault", and the two bundle IDs conflict (`ai.enclave.vault` vs `com.enclave.vault`).

**Precedents favour renaming early.** Ollama WebUI became Open WebUI by community vote ([Discussion #602](https://github.com/open-webui/open-webui/discussions/602)). Clawdbot became Moltbot after an Anthropic trademark complaint and then OpenClaw within a week, and the rename post itself drew 667 HN points ([HN](https://news.ycombinator.com/item?id=46820783)). At 2 stars, a rename costs nothing today. After launch it costs links, SEO and stars.

**Criteria for the new name:**

1. Unique on Google, GitHub, PyPI, npm, Homebrew and the App Store.
2. Clear in a USPTO/EUIPO search of software classes 9 and 42.
3. A matching .com, .app or .ai domain.
4. No implied security property the product lacks (no TEE words).
5. No derivation from Apple, Anthropic or OpenAI marks (the OpenClaw lesson).
6. One string used for the repo, app, bundle ID, cask token and PyPI package.
7. The category keywords ("offline", "private", "your documents") go in the tagline, not the name.

Candidates such as *Paperkeep*, *Hearthfile* or *Keepfolio* only illustrate the direction: household-paperwork connotation, nothing about hardware security. **None has been checked for trademark, domain or package availability.**

If the owner insists on keeping the brand, the fallback is a qualified "Enclave Vault" with `enclave-vault` as the package and cask token. That PyPI name was free on 2026-09-29 ([PyPI](https://pypi.org/project/enclave/)). A trademark search should come first, and the same-category conflict would remain.

## Three magic moments define v1; everything else waits

The target experience combines what the best 2026 apps do with what only a local vault can truthfully claim. There are three moments.

**Moment one: a cited answer inside the first minute.** Jan v0.8.0 shows a "Fits / May be slow / Won't fit" hardware badge before any download ([Jan changelog](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)). Enclave should copy that, then:

1. Download the right model in the background, showing size, ETA and a cancel button. Today's dialog shows none of these (`gui/vault_app.py:584-655`).
2. Meanwhile, open a pre-indexed sample vault: a fictional family's passport, lease, insurance and tax PDFs. The user asks a suggested question before the model even finishes downloading.
3. Lead onboarding copy with outcomes, not "AI". NN/g's State of UX 2026 reports that "the shine is fading fast" on AI features ([NN/g](https://www.nngroup.com/articles/state-of-ux-2026/)).
4. Ask for OS permissions only when a feature needs them, one line of reason each, following Claude Desktop Quick Entry ([Claude Help Center](https://support.claude.com/en/articles/12626668-use-quick-entry-with-claude-desktop-on-mac)).

**Moment two: the vault knows your paperwork.**

- Ask "when does my passport expire?" and get the date with a numbered citation. Clicking it opens the scan at the right page with the line highlighted. NotebookLM set that bar ([Wikipedia: NotebookLM](https://en.wikipedia.org/wiki/NotebookLM)); Kotaemon matches it in open source ([README](https://raw.githubusercontent.com/Cinnamon/kotaemon/HEAD/README.md)).
- Drop a 40-page lease on the window and get a one-card summary (rent, term, notice period, penalties), with every field cited.
- When the vault finds a date, it asks: "We found an expiry date: 12 Mar 2027 — add reminder?"

Consumer expiry trackers show people pay for exactly this job: Expiro and Remindax extract dates from IDs and policies ([Expiro](https://mwm.ai/apps/expiro-app/6758278098); [Remindax](https://www.remindax.com/expiration-reminder)). The confirm-first framing matters. CHI 2026 research found that proactive assistants raise "uncertainty about system use of personal context" ([ACM](https://dl.acm.org/doi/10.1145/3772363.3798894)). Asking the user to confirm turns a potentially creepy moment into a helpful one, and it catches extraction errors too.

**Moment three: Claude asks, the vault answers, the files never leave.** In Claude Desktop the user asks, "What's my notice period on the lease?" Claude receives a cited answer, not the PDF. Inside the vault app, an inline card shows exactly what Claude asked and offers a scoped grant.

The consent design must be scoped rather than all-or-nothing. In the ConLeash study, **81% of users clicked "Always Allow" just to dismiss prompts**. Grants scoped by input, output destination, sensitivity and effect raised use of reusable grants from 13.3% to 46.3%, auto-permitted 98.3% of harmless calls, and caught 99.4% of escalations ([arXiv 2605.11360](https://arxiv.org/html/2605.11360v1)). Jan already renders tool calls as inline cards showing "the exact arguments" ([Jan changelog](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)).

**Trust surfaces make "nothing leaves" checkable rather than claimed.** Four are needed:

- **A "Local only" status pill.** It opens a live network log.
- **A "What the AI saw" drawer** on every answer, listing the exact passages and pages used.
- **An exportable activity log** of agent calls, modelled on Apple's Intelligence Report JSON ([Apple Support](https://support.apple.com/guide/mac-help/apple-intelligence-and-privacy-mchlfc0d4779/mac)).
- **Local vs. Remote labels** on any optional cloud model, which Apple's WWDC26 guidance says users "deserve to know" ([WWDC26 session 339](https://developer.apple.com/videos/play/wwdc2026/339/)).

**Speed is judged during the wait, so the latency budget is staged:**

| Stage | Target |
|---|---|
| Search-as-you-type from the keyword index | Under 100 ms |
| "Found 6 passages in 3 documents" | About 300 ms |
| First generated token | Under 1.5 s |
| Generation speed | 15 tokens/s or more |

These targets follow Nielsen's 0.1 s / 1 s / 10 s limits ([NN/g](https://www.nngroup.com/articles/response-times-3-important-limits/)). Source chips should appear before the answer streams, and the app should be queryable while indexing is still running.

| Capability | Priority | Grounding |
|---|---|---|
| Hardware fit check; background model download with size, ETA and cancel; pre-indexed sample vault | Launch | Jan v0.8.0; empty-state dead zone in today's app |
| Drag-and-drop anywhere, watch folders, progressive indexing ("you can ask now") | Launch | GPT4All indexing complaints ([#2579](https://github.com/nomic-ai/gpt4all/issues/2579)); Flet 0.28 has no OS drop API |
| Streaming answers with stage labels; Markdown rendering | Launch | Today: spinner, plain text, no stop button |
| Numbered inline citations opening a split-view reader at the highlighted page | Launch | Today: three non-clickable "name (score%)" rows |
| Honest "couldn't find that" and "your documents conflict" answers | Launch | Misleading-context results (see architecture) |
| Local-only pill, "What the AI saw" drawer, exportable activity log, answers labelled as AI-generated | Launch | Apple, Jan; EU AI Act Art. 50 ([Council](https://www.consilium.europa.eu/en/press/press-releases/2026/06/29/artificial-intelligence-council-gives-final-green-light-to-simplify-and-streamline-rules/)) |
| One-click "Connect to Claude" (signed .mcpb) with inline scoped consent | Launch | ConLeash; .mcpb ([repo](https://github.com/modelcontextprotocol/mcpb)) |
| Touch ID or passphrase unlock, dark mode, full keyboard control, screen-reader labels | Launch | Today: hard-coded light theme, zero semantics labels |
| OCR for scans and phone photos | Launch (Mac) | Top unmet want in the competitor survey |
| Extracted-field cards (lease, policy, lab result) and confirm-to-remind | Differentiator, v1.1 | Expiry apps; CHI 2026 |
| Generated tables ("all my insurance policies" with renewal dates) | Differentiator | MCP Apps ([blog](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)) |
| Global hotkey quick-ask, Finder "Ask about this file", Spotlight App Intents | Differentiator | Claude Quick Entry; macOS Tahoe ([MacStories](https://www.macstories.net/news/macos-tahoe-the-macstories-overview/)) |
| Local voice questions; MCP Apps citation viewer inside Claude, ChatGPT and Cursor | Differentiator | Whisper/Parakeet; MCP Apps hosts |
| Weekly Vault Digest; opt-in anomaly insights; life timeline; local audio briefing | Later | ChatGPT Pulse steering lesson ([OpenAI](https://openai.com/index/introducing-chatgpt-pulse/)) |
| Household vault, emergency access, recovery kit, end-to-end-encrypted sync, mobile scan-to-vault | Later (Phase 5) | Bitwarden ([Emergency Access](https://bitwarden.com/help/emergency-access/)), Obsidian Sync ([security](https://obsidian.md/help/sync/security)) |
| Fine-tuned adapters | Lab only | No evaluation shows a gain over retrieval |

## Keep the Python engine, but replace nearly every component around it

### One engine process should own the key, the index and consent

Three of the worst defects share one root cause: no single process owns the vault.

- **The index split.** The MCP server and the GUI each open their own database and key (see the blocker table).
- **The shell-built consent dialog.** Consent is handled by a subprocess the server spawns (`consent.py:301-316`).
- **The packaged app can't serve MCP.** When the app is frozen into a bundle, it points Claude Desktop at the user's system Python with a `PYTHONPATH` hack (`gui/mcp_setup.py:118-181`).

**The fix is architectural.** A headless Python engine becomes the only holder of the unwrapped data key, and the only reader and writer of the encrypted store. The GUI talks to it over authenticated local IPC: a Unix socket, or loopback plus a random bearer token, following MCP's local-server guidance ([MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)). The CLI is another client. The MCP server becomes a thin stdio process, shipped inside the app bundle and as a signed .mcpb, that forwards to the engine.

This gives three properties:

- **A locked vault stays closed.** If the vault is locked, an agent gets "open the app to unlock your vault", never data.
- **Consent is decided in the vault app, not by the calling agent.** Prompts render in the vault's own UI and are never built as shell strings. The MCP research recommends keeping the real consent gate out of band like this, because the calling agent's UI may auto-approve or be compromised. The spec's Multi Round-Trip Requests can still carry an in-call confirmation step ([MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)).
- **One answer pipeline.** GUI, CLI and MCP all get the same answers with the same citations, by construction.

| Layer | Recommendation | Alternative considered | Deciding trade-off |
|---|---|---|---|
| App shell | Tauri 2 with a web UI; Python engine as a signed sidecar (onedir or Nuitka, not PyInstaller `--onefile`) | Flet 1.0 declarative rewrite | Web-grade citation viewer, drag-and-drop, updater and tray, versus one language |
| LLM runtime | MLX on Mac; llama.cpp `llama-server` on Windows/Linux; both behind an OpenAI-compatible interface; bring-your-own endpoint optional | Ollama as a hard dependency | Ollama added sign-in and cloud routing in 2026 |
| Answer model | Qwen3.5 in non-thinking mode, sized to RAM | Gemma 4, Granite 4.1 | All Apache-2.0; own evaluation decides |
| Embeddings | Qwen3-Embedding-0.6B, shortened to 256–512 dimensions, via ONNX or llama.cpp | EmbeddingGemma-300M | Drops torch from the core install |
| Reranker | Qwen3-Reranker-0.6B or bge-reranker-v2-m3 on the top 30–50 candidates | jina-reranker-v3 | Jina is non-commercial |
| Ingestion | Docling container: text layer, then OS OCR, then a small document model on hard pages | Marker, Surya, Chandra | GPL and revenue-capped licenses |
| Store | One SQLCipher file holding documents, chunks, FTS5 keyword index, sqlite-vec vectors, extracted entities, citation anchors and the audit log | DuckDB 1.4 with AES-GCM | LanceDB open source lacks encryption at rest |
| Retrieval | Keyword + vector search merged by reciprocal rank fusion, then rerank; contextual headers; at most two loops | GraphRAG | Graphs lose on fact lookup and cost ~12× more to build |
| Citations | Sentence and block IDs, an automated verifier, exact matching for numbers, abstention and conflict answers | Prompt-only | Prompt-only abstention fails |
| Keys | Random data key, wrapped by an Argon2id passphrase key and an OS-keychain key; recovery kit | Keychain only | The key must never sit next to the data |
| MCP | SDK 2.x on spec 2026-07-28, stdio, five read-only tools, signed .mcpb | Today's 28 tools on SDK 1.x | Tool caps and attack surface |

### A Tauri shell over a Python sidecar narrowly beats a Flet 1.0 rewrite

**The UI gets rewritten either way.** About 25% of `vault_app.py` is dead code. Flet reached 1.0 on 14 September 2026 ([PyPI flet](https://pypi.org/pypi/flet/json)), and its own announcement says it is "not a drop-in replacement". It also changes the threading model: event handlers now run on the app's event loop instead of each on its own thread ([Flet blog](https://flet.dev/blog/flet-1-0)). Today's code relies on blocking handlers, such as a 120-second AppleScript file picker and synchronous SQLite reads on every render, so those would freeze the UI under 1.0. The v1 surface is only four screens: Chat, Library, Models/Settings and Connect. The UX audit sized it at "a few thousand lines of UI code and weeks rather than months for one experienced developer".

**Why Tauri 2:**

- It is the proven local-AI pattern. Jan moved to it because Electron's size "has become really big" and Tauri offers "lower memory & CPU usage" and a mobile path ([Jan issue #4485](https://github.com/janhq/jan/issues/4485)).
- It has first-party global-shortcut, updater and tray plugins ([Tauri global shortcut](https://v2.tauri.app/plugin/global-shortcut/)).
- A native Quick Look or Finder extension can sit in `Contents/PlugIns/`.
- The launch features — streaming Markdown, a PDF.js reader with highlight, OS drag-and-drop — are commodity web components.

**Why Flet 1.0 falls short on today's evidence:**

- It bundles CPython and targets six platforms, which is attractive.
- But its `MenuBar` is drawn by Flet, not the native macOS menu ([Flet docs](https://flet.dev/docs/controls/menubar/)).
- The underlying Flutter menu bar replaces the system menus, and multi-window support is still experimental ([flutter #162566](https://github.com/flutter/flutter/issues/162566)).
- OS drag-and-drop, notarization support and screen-reader behaviour in 1.0 were not verified.

**Costs of Tauri, stated plainly:**

- **A second language.** The UI is TypeScript while the engine stays Python.
- **macOS sidecar signing.** A PyInstaller `--onefile` sidecar carries an ad-hoc-signed Python framework that the hardened runtime refuses to load after re-signing. Every embedded binary must be signed with the same Team ID ([ResumeCompiler PR #63](https://github.com/raphaellith/ResumeCompiler/pull/63)). A reference repo shows a Tauri v2 Python sidecar with supervised restart, authenticated transport, Nuitka packaging and signing ([tauri-python-sidecar](https://github.com/matshoppenbrouwers/tauri-python-sidecar)).
- **No true native look.** Neither stack gets Liquid Glass natively, and Liquid Glass becomes mandatory for Xcode 27 builds ([Michael Tsai](https://mjtsai.com/blog/2026/03/23/liquid-glass-is-permanent/)). Native feel should come from correct menus, shortcuts and small Swift extensions, not pixel-matching.

**Choose Flet 1.0 only if the owner will not write TypeScript.** In that case, gate the choice on a short spike that proves OS drag-and-drop, a notarized build and screen-reader labels work in 1.0. SwiftUI-native is the highest-polish option but gives up Windows, Linux and the Python engine, and roughly doubles UI effort.

### RAM-tiered Qwen3.5 models replace 2024-era defaults

**Every model the app ships today is from 2024 or earlier.** The torch fallback, TinyLlama, is unusable.

**Qwen3.5 small models are the default.** They come in 0.8B, 2B, 4B and 9B sizes, are Apache-2.0, and handle images natively with 262K context. On the Artificial Analysis Intelligence Index they score **9B = 32, 4B = 27 and 2B = 16**, against about 13 for the older Qwen3 1.7B ([Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models)). Gemma 4 (Apache-2.0, April 2026; [model card](https://ai.google.dev/gemma/docs/core/model_card_4)) and Granite 4.1 (Apache-2.0, dense 3B/8B/30B; [IBM Research](https://research.ibm.com/blog/granite-4-1-ai-foundation-models)) are the alternates.

**Run them in non-thinking mode with capped output length, and only ever answer from sources.** Artificial Analysis measured **80–82% hallucination for the Qwen3.5 4B and 9B on a closed-book test**, meaning the models were answering from their own knowledge without documents. Grounded summarization is much better: Vectara's leaderboard shows **Qwen3-4B at 5.7% and Gemma-3-4B at 6.4%** hallucination ([Vectara](https://github.com/vectara/hallucination-leaderboard)). The same Vectara team found thinking models exceed 10% on their harder dataset ([Vectara blog](https://www.vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard)).

**Hardware reality: 16 GB is the modal machine.** Steam's August 2026 survey shows 41.07% at 16 GB, 38.47% at 32 GB and 7.00% at 8 GB ([Steam](https://store.steampowered.com/hwsurvey/Steam-Hardware-Software-Survey-Welcome-to-Steam?platform=pc)). Steam skews toward high-end gaming PCs, so the real consumer base likely has more 8–16 GB machines.

| RAM tier | Default answer model (4-bit memory) | Alternates | Embedder | Reranker |
|---|---|---|---|---|
| 8 GB | Qwen3.5-2B (~3.5 GB) | Gemma 4 E2B | EmbeddingGemma-300M (license check) or Granite Embedding R2 97M | None, or 0.6B on the top 20 |
| 16 GB (modal) | **Qwen3.5-4B (~5.5 GB)** | Gemma 4 E4B (audio input), Granite 4.1 3B, Qwen3.5-9B quality mode (~6.5 GB) | **Qwen3-Embedding-0.6B** | Qwen3-Reranker-0.6B |
| 24–32 GB | Qwen3.5-9B or Gemma 4 12B | Granite 4.1 8B, gpt-oss-20b (reasoning) | Qwen3-Embedding-0.6B/4B | Qwen3-Reranker-4B |
| 36 GB+ | Qwen3.6-27B / Qwen3.8-27B (~17 GB) | Gemma 4 26B-A4B, Muse Glimmer 30B | Qwen3-Embedding-4B | Qwen3-Reranker-4B |

Memory figures come from Unsloth ([Qwen3.5 docs](https://unsloth.ai/docs/models/qwen3.5)). The embedding and reranking choices come from the Qwen3-Embedding release: Apache-2.0, 32K context, and output that can be shortened to fewer dimensions ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)). Jina's stronger small embedder and reranker are licensed **CC-BY-NC**, so they cannot ship commercially without a separate license ([jina-reranker-v3](https://huggingface.co/jinaai/jina-reranker-v3)).

**Runtimes:**

- **Mac:** keep MLX. On M5 chips it uses the GPU Neural Accelerators, with 3.3–4.1× faster time-to-first-token than M4 ([Apple ML Research](https://machinelearning.apple.com/research/exploring-llms-mlx-m5)).
- **Windows and Linux:** add llama.cpp. It ships CUDA, Vulkan, ROCm and CPU builds for every OS ([llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)).
- **Don't depend on Ollama.** Since 2026 it has added first-run sign-in, cloud routing behind an identical API, and per-token pricing ([Ollama releases](https://github.com/ollama/ollama/releases); [Ollama blog](https://ollama.com/blog)). Offer it only as an optional bring-your-own endpoint with a clear local/cloud badge.
- **Copilot+ PCs:** Microsoft Foundry Local, a ~20 MB OpenAI-compatible runtime for Windows, macOS and Linux, is the optional NPU path ([MS Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/what-is-foundry-local)).
- **macOS 27:** Apple's Foundation Models can do titles and short extractions without any download ([WWDC26 guide](https://developer.apple.com/wwdc26/guides/apple-intelligence/)). Its small context window rules it out as the main answering model.

**Swapping sentence-transformers for ONNX or llama.cpp embeddings removes torch from the core install.** That cuts the install from gigabytes to roughly 100–200 MB before models, per the core audit's estimate.

### Hybrid retrieval with machine-checked citations is where answer quality is won

**Ingestion should cascade from cheap to expensive:**

1. Parse the text layer directly for born-digital PDF, DOCX, XLSX and email, using Docling as the container. It covers DOCX, PPTX, XLSX, EPUB, Pages, EML/MSG and audio ([Docling formats](https://docling-project.github.io/docling/usage/supported_formats/)).
2. Use OS OCR for scans. Apple Vision's `RecognizeDocumentsRequest` returns tables plus detected dates, amounts and addresses, entirely on-device ([WWDC25 session 272](https://developer.apple.com/videos/play/wwdc2025/272/)). Windows' `TextRecognizer` runs only on Copilot+ NPUs ([MS Learn](https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition)).
3. Escalate hard pages to a small document model:
   - **Granite-Docling-258M**: Apache-2.0, 200–300 tokens/s on MLX ([HF](https://huggingface.co/ibm-granite/granite-docling-258M-mlx)).
   - **GLM-OCR**: 0.9B, MIT weights, 95.22 on OmniDocBench v1.6 ([OmniDocBench](https://github.com/opendatalab/OmniDocBench)).
   - Avoid Chandra 2 (revenue cap), Surya/Marker (GPL) and the MinerU2.5 AGPL weights.

**Expect errors on phone photos.** PureDocBench found that every parser loses **11.61 points on real phone photos and shared captures** compared with clean pages ([arXiv 2605.07492](https://arxiv.org/abs/2605.07492)). So a low-confidence field should show its image crop rather than trusted text.

**Index in stages so the vault is useful immediately:**

- **Seconds:** text layer and keyword index, searchable at once.
- **Minutes:** embeddings.
- **Hours:** OCR on hard pages, contextual headers and extraction. Run these on AC power when the machine is idle.

**Retrieval evidence points one way:**

- **Keyword search plus reranking cuts failures by two-thirds.** In Anthropic's contextual-retrieval work, top-20 failures fell **35% with contextual embeddings, 49% after adding BM25 and 67% after adding reranking** ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)).
- **Keyword search wins at scale.** A July 2026 scaling study found BM25 overtakes a file-system agent at about 10M corpus tokens and calls it "the strongest scalable default" ([arXiv 2607.26497](https://arxiv.org/abs/2607.26497)).
- **A short loop captures nearly all the agentic gain.** With a local 7B model, **two retrieval iterations captured 95% of the gains of five**, and fixed hybrid retrieval beat adaptive routing ([arXiv 2606.21553](https://arxiv.org/abs/2606.21553)).
- **Plain chunking beats "semantic" chunking.** Recursive 512-token splitting reached 69% end-to-end accuracy against 54% for semantic chunking in a 2026 benchmark ([PremAI summary](https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/)).

**The design that follows:**

- **Chunking:** chunk by document structure, and keep each table as one chunk. Prepend a deterministic header (file name, document type, issuer, date, section, page) to get much of the contextual-retrieval benefit without spending LLM time.
- **Search and ranking:** merge keyword and vector results with reciprocal rank fusion (RRF), rerank the top 30–50, and pass 10–20 chunks to the model.
- **Loop limit:** cap the retrieve-and-answer loop at two passes.
- **Storage:** everything lives in one SQLCipher file. sqlite-vec brute-force search takes 5–15 ms per 100k vectors ([llms.blog](https://www.llms.blog/posts/embedded-vector-databases-in-production-comparing-lancedb-sqlite-vec-duckdb-vss-and-chroma)). Its approximate-search index is only in alpha ([releases](https://github.com/asg017/sqlite-vec/releases)), and brute force is adequate at vault scale anyway.
- **Drop graph-based RAG.** GraphRAG-Bench found it "frequently underperforms vanilla RAG on many real-world tasks" ([arXiv 2506.05690](https://arxiv.org/abs/2506.05690)). Structured personal data should come from an extraction layer instead. NuExtract3 (4B, Apache-2.0; [HF](https://huggingface.co/numind/NuExtract3)) fills per-document-type JSON templates. LangExtract-style grounding maps each extracted value to its exact source location ([LangExtract](https://github.com/google/langextract)). The results go into typed tables that record when each fact became valid and what superseded it, so "current policy number" never returns a stale value.

**Citations must be checked by code, not trusted from the model.** This follows the pattern of Claude's Citations API, which returns character, page or block locations with each cited span ([Claude docs](https://platform.claude.com/docs/en/build-with-claude/citations)):

1. Every chunk stores its document, page, region and sentence IDs.
2. The model cites IDs.
3. A deterministic verifier drops or flags any claim whose cited span isn't in the context.
4. Any amount, date or lab value must appear exactly in its cited span.

Abstention also needs code. Three small models with explicit abstention instructions **still answered 41.6% of misleading questions, and 63% of those answers repeated the planted wrong entity** ([arXiv 2608.22228](https://arxiv.org/abs/2608.22228)). So the app should combine a retrieval threshold, a "no supporting span" rule and cross-document conflict detection. "Your documents disagree" becomes a first-class answer. Track the answer rate as well: Gemma-3-4B's low hallucination rate comes partly from answering only 67.3% of questions ([Vectara](https://github.com/vectara/hallucination-leaderboard)).

### A user secret, five MCP tools and an assume-breach agent model

**Key management:**

- A random 256-bit data key encrypts the whole SQLCipher database, including the keyword index, the vectors and the audit log.
- That key is wrapped by an Argon2id passphrase key. OWASP's floor is 19 MiB memory with t=2 ([OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)); for a desktop vault, tune well above it to about 0.5–1 s.
- It is also wrapped by an OS-keychain key for convenient unlock.
- An optional passkey-derived key can be added: Apple Passwords and Google Password Manager passed 100% of the PRF tests in August 2026 ([Corbado](https://www.corbado.com/blog/passkeys-prf-webauthn)).
- Users print a recovery kit, as 1Password does ([Emergency Kit](https://support.1password.com/emergency-kit/)).
- Content hashes use a keyed HMAC.
- Chat history is encrypted.
- Deletion is crypto-erase: destroying the keys makes the data unreadable.

The threat-model document that replaces `CRYPTOGRAPHIC_SPECS.md` should say plainly that Python cannot reliably zero out `bytes` ([pyca/cryptography](https://cryptography.io/en/latest/limitations/)). It should also say that an unlocked vault is exposed to anything running as the same user.

**MCP should target the 2026-07-28 spec.** That revision:

- removes the stateful `initialize` handshake;
- replaces server-initiated prompts with Multi Round-Trip Requests (`input_required`) for in-call confirmation;
- deprecates Sampling, Roots, Logging and the HTTP+SSE transport, with a minimum 12-month window;
- has updated Python and TypeScript SDKs ([MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)).

Keep 2025-11-25 compatibility, because clients will lag. Following Anthropic's tool-design guidance ([Anthropic Engineering](https://www.anthropic.com/engineering/writing-tools-for-agents)) and Cursor's historical 40-tool cap ([Cursor forum](https://forum.cursor.com/t/tools-limited-to-40-total/67976)), expose five namespaced read-only tools:

- `ask` returns an answer plus citation handles.
- `search` returns titles, snippets and resource links, under policy.
- `open_citation` returns a redacted excerpt and requires consent.
- `list_collections`.
- `status`.

Mark them read-only with tool annotations and return structured output. Never put document-derived text in tool descriptions, because that is the tool-poisoning vector ([Invariant Labs](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)). Ship a signed .mcpb for one-click Claude Desktop install ([mcpb](https://github.com/modelcontextprotocol/mcpb)). ChatGPT accepts only remote HTTPS servers ([OpenAI Help](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)), so a tunnel for it stays an off-by-default advanced option.

**The agent security model starts from the lethal trifecta.** The vault holds private data. Its documents can carry injected instructions. The calling agent usually has a way to send data out ([Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)). Automated attacks such as RAG-Thief can extract large parts of a corpus through repeated synthesized answers ([arXiv 2411.14110](https://arxiv.org/html/2411.14110v1)).

The defences are layered:

- **Per-agent limits.** Scopes by collection, rate limits and daily quotas.
- **Extraction detection.** A detector for single-record, verbatim-style queries (RAG-CT; [arXiv 2609.16095](https://arxiv.org/pdf/2609.16095)), plus caps on how much of an answer can repeat source text word for word.
- **Redaction.** PII redaction by default with Presidio and GLiNER ([Presidio](https://presidio.dataprivacystack.org/samples/python/gliner/)).
- **Human approval for sensitive collections**, given in the vault's own UI.
- **A sealed synthesis model.** The vault's own LLM has no tools and no network access.
- **Clean outputs.** Strip links and images from answers before returning them.
- **No dynamic execution.** No shell calls and no runtime `npx` or pip.

The ecosystem shows why this matters:

- A zero-click remote-code-execution chain through unsandboxed Claude Desktop extensions ([LayerX](https://layerxsecurity.com/blog/claude-desktop-extensions-rce/)).
- A systemic stdio command-injection pattern across SDKs and products, with 10 CVEs ([OX Security](https://www.ox.security/blog/the-mother-of-all-ai-supply-chains-critical-systemic-vulnerability-at-the-core-of-the-mcp/)).
- The first malicious MCP server, which BCC'd every email to its author ([Snyk](https://snyk.io/blog/malicious-mcp-server-on-npm-postmark-mcp-harvests-emails/)).

The README should also say, honestly, that "answers, not documents" cuts bulk exfiltration but cannot stop an authorized agent from learning the facts it asks about. Consent and the audit log are the real controls.

## Five phases take Enclave from hotfix to household vault

The audits support two effort figures directly: Phase 0 in days, and the UI rebuild in weeks rather than months for one experienced developer. The other timeboxes below are my estimates for one full-time experienced developer. The calendar dates assume work starts on 1 October 2026.

| Phase | Timebox | Deliverables | Exit criteria |
|---|---|---|---|
| **0. Hotfix and honesty pass** | Days to 2 weeks (Oct 2026) | Pin `mcp<2`. Delete the `bash -c` consent path (argv-only zenity or in-app prompt) and publish a GitHub security advisory. Point MCP at the profile index. Make `doctor` actually start the MCP server. Fix the double chat template and the `model_used` misreport. Back up the config in `mcp install`. Set offline model loading after the first download. Rewrite the README: Apple Silicon only; say exactly what is and isn't encrypted; remove "key zeroing", the Windows/Linux claims, the training claims and the unsourced 79% statistic. Remove investor-demo copy. Fix the "All rights reserved" headers. Add SECURITY.md. Require Python 3.11+ or declare `tomli`. Add a macOS CI runner. | On a clean Apple Silicon Mac, a document ingested through the GUI is answered correctly by Claude Desktop. CI is green on both SDK versions. No shell interpolation remains (grep gate). |
| **1. Cut and unify the core** | ~6–8 weeks (Oct–Dec 2026) | Archive and quarantine per the cut table. Build the engine as a service: one data root, key, index and `ask()` pipeline, with inference moved out of `gui/`. Argon2id + keychain + SQLCipher. Docling ingestion with Apple Vision OCR. FTS5 + sqlite-vec hybrid search with a reranker. Verified citations. Qwen3.5 and Qwen3 retrievers via MLX, plus a llama.cpp backend. ONNX embeddings; torch leaves the core. MCP SDK 2.x with five tools. A golden evaluation set of 200–500 questions across document types (lookup, aggregation, temporal, multi-document, unanswerable, misleading), with gold page and span labels. An integration test from GUI ingest to MCP query. uv lockfile, `ruff --fix`, and the new name chosen. | Core install under ~200 MB without models. Nothing on disk in plaintext except documented metadata. Evaluation baselines recorded and beaten. Codebase roughly halved. |
| **2. Consumer v1 (Mac first)** | ~8–10 weeks (Dec 2026–Feb 2027) | Tauri shell covering every "Launch" row in the capability table. Signed, notarized DMG pipeline with the Sparkle 2 or Tauri updater ([Sparkle](https://sparkle-project.org/documentation/)). Private beta of 50–100 users recruited from r/LocalLLaMA feedback threads and personal networks. | A non-developer on a 16 GB Mac gets a first cited answer from the sample vault within about 60 s of launch, and from their own documents within minutes. Zero unlisted outbound connections. Crash-free beta week. |
| **3. Public launch** | 2–3 weeks prep + launch (~Mar 2027) | Rename live across every surface. README with GIF and download buttons. Homebrew cask. Sigstore-signed releases with SLSA provenance and SBOM. OpenSSF Scorecard badge. Published threat model. Egress domain list. Signed .mcpb and tool-manifest hashes. Discord and Discussions. Show HN and the channel plan below. | Launch-week star, download and activation numbers recorded against the targets in the metrics table. |
| **4. Differentiators** | Q2–Q3 2027 | Extraction cards and confirm-to-remind. Generated tables. Global hotkey. Local voice. MCP Apps citation viewer. Windows build on llama.cpp. Connectors: Obsidian, email, FHIR patient access via CMS Aligned Networks ([Wilson Sonsini](https://www.wsgr.com/en/insights/cms-announces-creation-of-health-tech-ecosystem-for-improving-access-to-patient-data.html)), OFX/CSV statements. OpenClaw/Hermes skill. Third-party security audit budgeted. | Each release doubles as a launch moment. Audit report published. |
| **5. Household, sync, mobile** | H2 2027+ | Household vault, emergency access with a waiting period, recovery kit. End-to-end-encrypted sync of source documents only, with each device re-embedding locally, over the user's own cloud folder or a blind relay. Mobile scan-to-vault companion. Paid convenience tier. | Sync design reviewed against FTC Health Breach Notification Rule exposure ([FTC](https://www.ftc.gov/business-guidance/resources/complying-ftcs-health-breach-notification-rule-0)) before any hosted component ships. |

**Sequencing logic.** Phase 0 exists because the repository is already public and its flagship integration is broken; every day it stays up with a known RCE path and false encryption claims costs credibility. Phase 1 comes before any UI work because the index split, the key layout and the model swap all force a re-index and a data migration. Doing them under a new UI would mean migrating twice. Phase 2 stays Mac-only because MLX is the only answering path that works today. Declaring Windows and Linux "later" is more honest than shipping the current loop that never sends.

**Phase 5 should not start before the product has users.** Sync widens the threat model. The security research recommends keeping it out of the public launch ([Obsidian audits](https://obsidian.md/blog/cure53-tob-sync-audits/) show that even a mature implementation leaves path metadata visible and uses deterministic encryption).

## One launch buys about two thousand stars, so plan four

**What a launch buys.** The best-measured channel is Hacker News:

- Across 138 AI-tool launches, the average was **+121 stars at 24 h, +189 at 48 h and +289 at 7 days**.
- Posting between 12:00 and 17:00 UTC was worth about +200 stars.
- The "Show HN" tag and the day of week made no significant difference ([arXiv 2511.04453](https://arxiv.org/html/2511.04453v1)).
- The median Show HN scores 2 points. **250+ points is the top 1%**, and a front-page post brings 5k–30k visitors, 92% of them within 48 hours ([daily.dev](https://business.daily.dev/resources/hacker-news-marketing-developer-tools-show-hn-launch-day-sustained-coverage/)).

**Local-AI desktop apps do much better than the average**, at roughly 3–6 stars per HN point:

- Reor: 411 points, about 2,457 stars in six days ([HN](https://news.ycombinator.com/item?id=39372159)).
- AnythingLLM: 368 points, about 2,160 stars in six days ([HN](https://news.ycombinator.com/item?id=41457633)).
- Khoj: 565 points, 1,676 stars in four days ([HN](https://news.ycombinator.com/item?id=36933452)).

Star data from [OSS Insight](https://api.ossinsight.io/v1/repos/reorproject/reor/stargazers/history?per=day).

**The spike fades.** Reor's velocity returned to 30–60 stars a day within ten days. It peaked at about 8.5k stars and was archived in 2026. It is the closest analog to Enclave, and the warning is that one spike without a distribution moat does not sustain a project.

**The biggest spikes came from timing and channels, not polish.**

- **Model-release moments lifted everything.** In February 2025, the month after DeepSeek-R1, Ollama, Open WebUI and AnythingLLM all had their record months ([OSS Insight Ollama](https://api.ossinsight.io/v1/repos/ollama/ollama/stargazers/history?per=month)).
- **Discord and one-line installs drove OpenClaw.** It gained about 40k stars in one week. The multipliers were a public Discord where users posted screenshots the same evening, and a one-line install: "Virality dies at configuration friction" ([Developers Digest](https://www.developersdigest.tech/blog/openclaw-github-star-chart-vertical-line)).
- **Coordinated channels.** AFFiNE's self-reported playbook: seed 100–300 genuine stars first, concentrate every channel into 48 hours, and expect 50–300 stars per good Reddit post and 200–600 from Product Hunt ([Gingiris/AFFiNE](https://gingiris.github.io/growth-tools/blog/2026/03/25/how-to-get-more-github-stars-the-definitive-guide-33k-stars-case-study/)).

| When | Action | Expected effect |
|---|---|---|
| T−6 to T−1 weeks | Private beta; seed 100–300 genuine stars; open Discord and Discussions; README with a 10–20 s GIF (drop a PDF, Wi-Fi visibly off, cited answer), download buttons, a trust box, a comparison table against AnythingLLM/Jan/NotebookLM; zh-CN and ja README translations | Enough base velocity for GitHub Trending (practitioner heuristic: 50–100 stars/day for a language list, 200+ for all languages; [GitHub discussion](https://github.com/orgs/community/discussions/163970)) |
| T0, weekday 12:00–17:00 UTC | Show HN linking the repo, titled like "Show HN: *Name* – Ask your tax, medical and legal documents, 100% offline (open source)", with a first comment covering privacy architecture and business model ([Markepear](https://www.markepear.dev/blog/dev-tool-hacker-news-launch)); same-day X video; r/LocalLLaMA, r/selfhosted, r/privacy, r/macapps | About 2,000–2,500 stars in week one if the post reaches 350–650 points |
| T+1–2 weeks | Product Hunt for the badge; outreach to local-AI YouTubers with a "fully offline document chat in 5 minutes" script; Homebrew cask submission | 200–600 stars from Product Hunt (self-reported range) |
| Within 24–48 h of the next major open-weight model | A pre-written "now runs *model* offline" release | Rides the category-wide wave |
| Months 2–9 | Agent-integration moments (OpenClaw/Hermes skill, MCP Registry listing, LM Studio "Add" deeplink), the structured-life-data release, the Windows release, the published security audit | Each one re-ignites a fading curve |

**Distribution must be signed from day one.**

- **Homebrew.** Since 1 September 2026, Homebrew disables every cask that fails Gatekeeper, and it has removed `--no-quarantine`; about 387 of 7,624 casks had been deprecated ([Homebrew #6482](https://github.com/orgs/Homebrew/discussions/6482)). Self-submitted casks also face notability thresholds, reported as 225 stars / 90 forks / 90 watchers ([Acceptable Casks](https://docs.brew.sh/Acceptable-Casks)). The `enclave` token is taken.
- **Installer.** Keep the installer small and download models after install with the hardware-fit UI.
- **Channels by audience.** Offer `pipx`/`uvx` for developers only. Avoid `curl | sh` for consumers, because it undercuts a trust brand. Defer the Mac App Store, because its sandbox complicates watch folders and helper processes.
- **Trust checklist.** SECURITY.md, Sigstore-signed releases ([OpenSSF Sigstore](https://openssf.org/projects/sigstore/); OpenSSF Scorecard's Signed-Releases check ignores plain checksums, [Scorecard example](https://github.com/jeedo/oneshot/issues/71)), an SBOM, telemetry off by default, and a published list of every domain the app can contact.
- **Audit.** Budget a Cure53 or Trail of Bits review after the beta and publish it in full, following Obsidian's precedent.

**Community and business model.** Use Discord for launch-day energy and GitHub Discussions for durable Q&A and roadmap votes. Write a CONTRIBUTING.md with an AI-generated-PR policy from day one. OpenClaw's maintainers reported that "pull requests became prompt requests" ([GitHub Blog](https://github.blog/open-source/maintainers/openclaw-went-viral-meet-the-maintainers-building-and-securing-it/)). Connectors are both extension points and distribution channels into other communities. Any shared skill or plugin registry must be signed and reviewed.

The proven model is "local app free forever, pay for convenience". Obsidian charges $4–5 a month for end-to-end-encrypted sync ([Obsidian pricing](https://obsidian.md/pricing)). Ollama monetizes cloud tiers and has raised $88M ([Yahoo Finance](https://finance.yahoo.com/technology/ai/articles/popular-open-source-ai-developer-130000699.html)). Protect the brand with a trademark policy rather than a license change. Draw any open-core line at launch, because changing a license after traction costs goodwill.

**Never buy stars.** StarScout found about 4.5–6M suspected fake stars. It concluded they help for "less than two months" and then become "a liability" ([arXiv 2412.13459](https://arxiv.org/abs/2412.13459)). For a privacy product, an authenticity scandal would be fatal.

## Measure cited answers and verified silence, then stars

Stars measure intent, not use. Ollama has about 50 monthly developers per star ([Yahoo Finance](https://finance.yahoo.com/technology/ai/articles/popular-open-source-ai-developer-130000699.html)). OpenClaw's pace fell from about 50,000 stars a week to about 1,400 once the curious had starred ([Developers Digest](https://www.developersdigest.tech/blog/openclaw-github-star-chart-vertical-line)).

The gates below are proposed targets. They are anchored in the research where noted, and are otherwise the author's judgment.

| Dimension | Metric | Proposed gate |
|---|---|---|
| Activation | Time from first launch to a first cited answer (sample vault / own documents) | ≤60 s / a few minutes after the model download, on a 16 GB Mac |
| Retrieval | Recall@10 and citation precision on the golden set | Baseline set in Phase 1; each default change must beat it. CUBO reports laptop Recall@10 of 0.48–0.97 by domain ([arXiv 2602.03731](https://arxiv.org/abs/2602.03731)) |
| Faithfulness | Numbers and dates shown without an exact-match source span | Zero |
| Abstention | Answer rate on misleading and unanswerable questions | Far below the 41.6% baseline, while tracking the overall answer rate |
| Speed | Search / retrieval stage / first token / decode | <100 ms / ~300 ms / <1.5 s / ≥15 tokens/s |
| Privacy | Outbound domains beyond the published list | Zero |
| Footprint | Core install excluding models | <~200 MB |
| Growth | Week-one stars; release downloads; cask installs; opt-in update pings as a proxy for weekly active users; 4-week retention | ~2k week-one stars if HN front page; retention tracked from the beta |

| Risk | Why it is real | Mitigation |
|---|---|---|
| A generalist adds encryption and an MCP-server mode | Competitor scan | Out-execute on the life-document schema, checked citations and reminders; keep the OSI license |
| Cloud incumbents and Apple's Siri AI raise the bar | Siri AI shipped personal context over messages, email and photos on 14 Sept 2026, not yet in the EU ([Apple Newsroom](https://www.apple.com/newsroom/2026/09/siri-ai-a-profoundly-more-capable-and-personal-assistant-is-here/)) | Verifiable local-only; work with any agent; cover the documents Siri doesn't |
| Local answer quality disappoints | Closed-book hallucination; weak small models | Retrieval-only answering, verifier, abstention; optional explicit cloud escalation that shows the payload |
| Launch spike, then decay | Reor archived at 8.5k | Four planned moments; paid convenience tier |
| Security incident via MCP | CVE wave; DXT RCE | Five read-only tools, no shell, signed bundles, audit log, published review |
| Extraction through answers | RAG-Thief | Quotas, detection, redaction, honest disclosure |
| Trademark dispute | Same-category Enclave AI | Rename before Phase 3 |
| Model license drift | Jina CC-BY-NC, Chandra revenue cap, LFM license unclear | Apache/MIT defaults only; license check in CI |
| Sidecar signing or bundling failure | Team-ID mismatch; torch size | onedir/Nuitka; drop torch; macOS CI build from Phase 1 |
| sqlite-vec inside SQLCipher untested across platforms | Not officially documented | Phase 1 spike; fallback to encrypted DuckDB or per-row encrypted vectors |
| Maintainer overload | AI-generated PR floods | Contribution policy; strict scope |

## Eight decisions the owner should make this month

| Decision | Recommendation | Needed by |
|---|---|---|
| Name | Rename; pick using the criteria above after trademark, domain and package checks | End of Phase 1 |
| Platform scope | macOS Apple Silicon first; Windows via llama.cpp in Phase 4; Linux experimental | Now (drives the Phase 0 README) |
| UI stack | Tauri 2 + Python sidecar; Flet 1.0 only if TypeScript is ruled out, and only after a spike passes | Start of Phase 1 |
| Fine-tuning and adapters | Quarantine into an optional lab extra; revisit only after the evaluation shows retrieval is solid | Now |
| Secrets KV, wallet, Sheriff, browser extension | Remove from the product and archive; secrets become an optional plugin with no raw-returning MCP tool, if kept at all | Now |
| Cloud escalation | Off by default; per-request, showing exactly what is sent; later Apple Private Cloud Compute or zero-data-retention BYOK ([OpenRouter ZDR](https://openrouter.ai/docs/features/zdr)) | Phase 2 |
| Telemetry | None by default; any opt-in update ping disclosed verbatim | Phase 2 |
| License, business model, funding | Apache-2.0 plus a trademark policy; paid encrypted sync and household later; decide on company or VC before any hosted component | Phase 3 (license line); Phase 5 (company) |

## Where the evidence is thin or contradictory

**The research had gaps.** Several researchers ran out of web-search budget partway through. Reddit was blocked (HTTP 403), so community sentiment comes from HN and GitHub issues only. The audits ran on Linux without Apple Silicon, so MLX answer quality, Mac install size and Mac timings are **unverified**. Windows was not tested at all. No trademark search or domain check was done for any name.

**Some tools and designs were not checked.** Flet 1.0's drag-and-drop, notarization and accessibility behaviour were not verified. The Tauri-vs-Electron size and RAM figures are from secondary sources. No source confirmed that sqlite-vec loads cleanly into SQLCipher builds on every platform.

**Star data conflicts.** OSS Insight undercounts 2026 stars badly, for example 109,834 vs 390,778 live for OpenClaw. Only relative timing from it is reliable.

**Several sources conflict, so decide with your own evaluation rather than any one leaderboard.**

- **Qwen3.5 details.** Release dates differ by a few days. Unsloth says thinking mode is off by default for the small models, while the HF card summary says it is on.
- **Qwen3.5 hallucination.** Its 80–82% hallucination rate is closed-book, and no source ranks Qwen3.5, Gemma 4 or Granite 4.1 on cited retrieval-based QA.
- **Model and license details.** EmbeddingGemma's license is reported both as Gemma Terms of Use and as Apache-2.0; verify it before shipping. Jina's paper puts Qwen3-Reranker-0.6B below bge-reranker-v2-m3, while secondary guides recommend Qwen3-Reranker. Apple's on-device Foundation Model context is reported as both 4,096 and 8,192 tokens, both from secondary sources.
- **Benchmark methods.** OmniDocBench scores shift between v1.5 and v1.6. Chunking studies rank strategies in opposite orders depending on whether they measure retrieval recall or end-to-end accuracy. Memory-layer benchmarks range from about 49% to 95% for the same systems.

**Growth and ecosystem figures are disputed or dated.** HN timing folklore (Tuesday–Thursday mornings ET) conflicts with the academic finding that the day of week doesn't matter. MCP CVE tallies for early 2026 range from 14 to "40+". Cursor's 40-tool cap dates from 2025. Homebrew's notability numbers come from a search summary of an older docs page. Product Hunt, Reddit and README-conversion figures are practitioner self-reports.

**No dataset exists for personal-document retrieval, and none quantifies consumer demand for a local vault or willingness to pay.** The golden set and the beta are therefore the first real evidence the project will have.

## Conclusion

The defects that look like unrelated bugs are really one architectural gap. The MCP index split, the shell-built consent dialog, the "frozen app can't serve MCP" problem and the key stored next to its data all come from having no single process that owns the vault. Making one unlocked engine the sole key-holder and consent authority, with the GUI, CLI and MCP as thin clients, fixes correctness, security and UX in one move. It also turns "your agent can't read your files unless the vault is unlocked and you said yes" into a demonstrable property rather than a promise.

The moat is not local inference, which Ollama, LM Studio and Jan have commoditized. It is being the trustworthy intermediary between sensitive paperwork and whichever agent the user prefers. The strategy therefore deliberately uses frontier cloud agents instead of competing with them: let Claude or OpenClaw do the reasoning and keep the documents here. Stars in this category follow model and agent moments more than polish. The owner's scarcest resource after launch will be the capacity to ship a credible release within 48 hours of the next moment, so keeping scope small now is what makes that possible later.
