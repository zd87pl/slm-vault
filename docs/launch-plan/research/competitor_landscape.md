# Competitive Landscape: Local/Private AI Document Assistants & Personal Knowledge Vaults (as of 2026-09-29)

**Method and caveats (read first)**
- Live GitHub star counts, archived status and repo descriptions were pulled on **2026-09-29** through the GitHub search API (via the GitHub MCP tool). Licenses come from each repo's LICENSE file (raw.githubusercontent.com, HEAD). Latest releases and last-push dates come from ungh.cc, a GitHub mirror API.
- Star *history* comes from the OSS Insight API (`api.ossinsight.io/v1/repos/{repo}/stargazers/history/?per=month`). **Caveat:** OSS Insight's 2026 figures run well below live GitHub counts for every repo, including dormant ones. For example, GPT4All shows 73,393 on OSS Insight for 2026-09 vs 77,388 live, and AnythingLLM shows 49,591 vs 66,599. I use OSS Insight mainly for the **Jan→Sep 2025** growth window. "Live minus OSS Insight Sep-2025" serves only as a rough upper-bound proxy for 12-month gains.
- Reddit was unreachable (the proxy returned 403 for reddit.com) and this session's web-search budget ran out partway through. User-complaint evidence therefore comes mainly from **Hacker News threads (via the HN Algolia API)** and **GitHub issues**. Treat Reddit sentiment as a gap.
- Anything not confirmed from a 2026 source is marked **[unverified 2026]**.

---

## Q1. Who are the competitors, and what does each one offer? (per-player profile)

### Takeaway
The field splits into five clusters:
1. **General local-LLM chat apps with bolt-on document chat:** AnythingLLM, Open WebUI, Jan, LM Studio, Msty, GPT4All, Cherry Studio, LobeHub.
2. **Heavier self-hosted RAG servers:** RAGFlow, Kotaemon, PrivateGPT/Zylon, Onyx, DocsGPT, SurfSense, Open Notebook.
3. **Notes/PKM tools with AI layers:** Obsidian plugins, Logseq, SiYuan, AFFiNE, Anytype, Reor (dead), Khoj.
4. **Document-management systems adding AI:** Paperless-ngx v3 with paperless-gpt and paperless-ai.
5. **Platform and cloud incumbents:** ChatGPT Health, Claude memory and healthcare, Gemini Notebook (formerly NotebookLM), Apple, Microsoft Recall.

None of them combines three things: encrypted-at-rest storage by default, a personal-life-document schema, and an MCP *server* that exposes answers without exposing raw documents.

### Cited Findings

#### Master table: open-source players (live stats 2026-09-29)
| Project | Stars (live) | License | Latest release / activity | Notes | Sources |
|---|---|---|---|---|---|
| Open WebUI | 153,529 | Custom "Open WebUI License" (BSD-3 plus a branding clause from v0.6.6, Apr 2025) | v0.11.4, 2026-09-21 | README mentions MCP, OCR, encryption | [repo](https://github.com/open-webui/open-webui), [LICENSE](https://raw.githubusercontent.com/open-webui/open-webui/HEAD/LICENSE), [license docs](https://docs.openwebui.com/license/) |
| RAGFlow (infiniflow) | 91,495 | Apache-2.0 | v1.0.0-rc1, 2026-09-29 | Now positioned as a "context engine"; OCR, tables, citations, MCP in README | [repo](https://github.com/infiniflow/ragflow), [releases](https://github.com/infiniflow/ragflow/releases) |
| LobeHub (formerly LobeChat) | 82,899 | "LobeHub Community License" (not OSI) | v2.2.19-canary, 2026-09-29 | Rebranded as "Chief Agent Operator"; knowledge-base and MCP topics | [repo](https://github.com/lobehub/lobehub), [LICENSE](https://raw.githubusercontent.com/lobehub/lobehub/HEAD/LICENSE) |
| GPT4All (Nomic) | 77,388 | MIT | **v3.10.0, 2025-02-25; last push 2025-05-27** | LocalDocs; effectively dormant | [repo](https://github.com/nomic-ai/gpt4all), [releases](https://github.com/nomic-ai/gpt4all/releases) |
| AFFiNE | 73,092 | MIT, plus an EE-licensed portion | canary builds, 2026-09-26 | Notion/Miro alternative; "privacy first" | [repo](https://github.com/toeverything/AFFiNE) |
| AnythingLLM (Mintplex) | 66,599 | MIT | v1.16.2, 2026-09-22 | Desktop (Mac/Win/Linux) plus Android; acts as an MCP client; citations; anonymous telemetry | [repo](https://github.com/Mintplex-Labs/anything-llm), [site](https://anythingllm.com/) |
| PrivateGPT (Zylon) | 57,551 | Apache-2.0 | v1.0.0, 2026-06-03; v1.0.1, 2026-06-18 | Repositioned as an "API layer" | [repo](https://github.com/zylon-ai/private-gpt) |
| Cherry Studio | 52,236 | AGPL-3.0 | active daily, 2026-09-29 | MCP, OCR, knowledge base; README mentions iOS/Android | [repo](https://github.com/CherryHQ/cherry-studio) |
| SiYuan | 46,558 | AGPL-3.0 (some features paid) | v3.8.6, 2026-09-29 | AI via OpenAI API; MCP topic | [repo](https://github.com/siyuan-note/siyuan), [README](https://raw.githubusercontent.com/siyuan-note/siyuan/HEAD/README.md) |
| Paperless-ngx | 46,154 | GPL-3.0 | v3.2.1, 2026-09-20 | v3 ships built-in AI suggestions, document chat, remote OCR | [repo](https://github.com/paperless-ngx/paperless-ngx), [changelog](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/dev/docs/changelog.md) |
| Logseq | 45,084 | AGPL-3.0 | 2.0.1 (DB version), 2026-07-13 | No native AI found in README | [repo](https://github.com/logseq/logseq), [releases](https://github.com/logseq/logseq/releases) |
| Jan (Menlo Research) | 44,706 | Apache-2.0 | v0.8.4, 2026-07-23 | MCP connectors; "cowork-style" desktop app | [repo](https://github.com/janhq/jan), [changelog](https://jan.ai/changelog) |
| Open Notebook (lfnovo) | 39,624 | MIT | v1.14.0, 2026-07-21 | "100% local" NotebookLM alternative | [repo](https://github.com/lfnovo/open-notebook) |
| Quivr | 39,562 | Apache-2.0 | last core release 2025-02-04 | Appears stalled | [repo](https://github.com/QuivrHQ/quivr) |
| Khoj | 37,536 | AGPL-3.0 | 2.0.0-beta.28, 2026-03-26 | Self-host, cloud and enterprise; company now foregrounds "Pipali" | [repo](https://github.com/khoj-ai/khoj), [site](https://khoj.dev/) |
| Vane (formerly Perplexica) | 36,934 | MIT | v1.12.2, 2026-04-10 | Web answer engine, not a document vault | [repo](https://github.com/ItzCrazyKns/Vane) |
| Onyx (formerly Danswer) | 32,286 | MIT, plus EE-licensed `ee/` directories | Helm charts, 2026-09-28 | Enterprise search; YC W24 | [repo](https://github.com/onyx-dot-app/onyx) |
| Kotaemon (Cinnamon) | 25,787 | Apache-2.0 | v0.12.0, 2026-05-31 | Best-in-class citation UX; Docker-first | [repo](https://github.com/Cinnamon/kotaemon) |
| Screenpipe | 21,776 | **Screenpipe Commercial License** (source-available; was MIT) | app-v2.7.76, 2026-09-26 | YC S26; MCP server | [repo](https://github.com/screenpipe/screenpipe), [README](https://raw.githubusercontent.com/screenpipe/screenpipe/HEAD/README.md) |
| localGPT (PromtEngineer) | 22,199 | – | low growth | – | [repo](https://github.com/PromtEngineer/localGPT) |
| DocsGPT (arc53) | 18,295 | MIT | 0.21.0, 2026-09-16 | Enterprise/agent-builder focus | [repo](https://github.com/arc53/DocsGPT) |
| Rowboat | 17,985 | – | active, 2026-09-29 | "Open-source, local-first alternative to Claude Desktop" | [repo](https://github.com/rowboatlabs/rowboat), [HN](https://news.ycombinator.com/item?id=48819808) |
| SurfSense | 16,294 | Mixed (`proprietary/` directory) | v2.0.3, 2026-09-26 | Hosted app being retired; moving to a desktop app | [repo](https://github.com/MODSetter/SurfSense) |
| EverOS (EverMind) | 13,287 | Apache-2.0 | v1.4.1, 2026-09-24 | Portable Markdown memory layer; MCP | [repo](https://github.com/EverMind-AI/EverOS) |
| h2oGPT | 11,959 | Apache-2.0 | **archived**; last push 2025-10-09 | – | [repo](https://github.com/h2oai/h2ogpt) |
| Local Deep Research | 9,142 | MIT | v1.10.7, 2026-08-28 | SQLCipher-encrypted per-user DB | [repo](https://github.com/LearningCircuit/local-deep-research) |
| Morphic | 9,149 | – | 2026-09 | Web search engine UI | [repo](https://github.com/miurla/morphic) |
| Anytype (anytype-ts) | 8,866 | "Any Source Available License 1.0" | v0.57.1-beta, 2026-09-22 | Zero-knowledge E2EE, P2P; no AI found in README | [repo](https://github.com/anyproto/anytype-ts) |
| Reor | 8,549 | AGPL-3.0 | **archived**; last release 2025-04-05; last push 2025-05-13 | – | [repo](https://github.com/reorproject/reor) |
| Nexa SDK, now "GenieX" | 8,406 | BSD-3, © Qualcomm | v0.7.1, 2026-09-28 | Snapdragon-only | [repo](https://github.com/NexaAI/nexa-sdk) |
| Obsidian Copilot | 7,769 | AGPL-3.0 | 4.0.12, 2026-09-29 | Free plugin plus paid license | [repo](https://github.com/logancyang/obsidian-copilot), [site](https://www.obsidiancopilot.com/en) |
| Enchanted | 6,006 | Apache-2.0 | v1.8.2, 2026-06-15 (previous release 2024-05) | iOS/macOS Ollama client | [repo](https://github.com/gluonfield/enchanted) |
| paperless-ai | 5,954 | MIT | v3.0.9, 2025-11-04 | Slowing | [repo](https://github.com/clusterzx/paperless-ai) |
| Smart Connections | 5,473 | "Smart Plugins License" (Jobsi, Inc.) | 4.7.2, 2026-08-06 | 496 open issues | [repo](https://github.com/brianpetro/obsidian-smart-connections) |
| OpenKnowledge (inkeep) | 4,346 | – | created 2026-06 | MCP server plus skills; macOS app | [repo](https://github.com/inkeep/open-knowledge), [HN](https://news.ycombinator.com/item?id=48675435) |
| basic-memory | 4,063 | AGPL-3.0 | v0.23.2, 2026-08-25 | MCP-native; $15/mo cloud | [repo](https://github.com/basicmachines-co/basic-memory) |
| Deta Surf | 3,585 | – | 2026-08 | Local-first AI notebook | [repo](https://github.com/deta/surf) |
| Sidekick (macOS) | 3,315 | MIT | 1.0.0-rc.18, 2026-04-02; last push 2026-05-24 | – | [repo](https://github.com/johnbean393/Sidekick) |
| paperless-gpt | 2,719 | MIT | v0.28.0, 2026-09-18 | LLM-vision OCR | [repo](https://github.com/icereed/paperless-gpt) |
| mcpvault (Obsidian MCP) | 1,675 | – | 2026-09 | Safe Obsidian vault access over MCP | [repo](https://github.com/bitbonsai/mcpvault) |

Infrastructure context (not direct competitors, but they set expectations):
- Ollama: 181,919 stars — [repo](https://github.com/ollama/ollama)
- microsoft/markitdown: 187,586 stars — [repo](https://github.com/microsoft/markitdown)
- Docling: 68,176 stars — [repo](https://github.com/docling-project/docling)
- mem0: 66,310 stars — [repo](https://github.com/mem0ai/mem0)
- LocalAI: 49,319 stars — [repo](https://github.com/mudler/LocalAI)
- LightRAG: 39,920 stars — [repo](https://github.com/HKUDS/LightRAG)
- Graphiti: 31,305 stars — [repo](https://github.com/getzep/graphiti)
- Cognee: 31,210 stars — [repo](https://github.com/topoteretes/cognee)

#### Per-player detail: general local-LLM chat apps with document chat

**AnythingLLM** (Mintplex Labs; MIT)
- Desktop app for Mac, Windows and Linux, plus an open-source Android app. Mobile "runs small models fully on-device … Pair it with your desktop to reach larger models and your full workspaces from anywhere." — [anythingllm.com](https://anythingllm.com/), [README](https://raw.githubusercontent.com/Mintplex-Labs/anything-llm/HEAD/README.md)
- Features: drag-and-drop uploads with source citations; a local meeting assistant (no bot joins the call); Microsoft Foundry Local on Windows CPU/GPU/NPU from v1.16.1; You.com web search on by default. — [anythingllm.com](https://anythingllm.com/)
- MCP: AnythingLLM is an MCP **client/host**. MCP servers are added through a config file and managed in the UI. — [AnythingLLM MCP docs](https://docs.anythingllm.com/mcp-compatibility/overview)
- Telemetry: "contains a telemetry feature that collects anonymous usage information." — [README](https://raw.githubusercontent.com/Mintplex-Labs/anything-llm/HEAD/README.md)
- Business model: the desktop app is free, Docker self-hosting is free, and paid hosted multi-user plans offer white-labeling. — [pricing](https://anythingllm.com/pricing)
- Repo topics have shifted toward "agent-harness", "computer-use" and "hermes-agent". — [repo](https://github.com/Mintplex-Labs/anything-llm)
- Complaints (GitHub):
  - "Search in documents (RAG) dont work, is unusable in all versions" — [#2087](https://github.com/Mintplex-Labs/anything-llm/issues/2087)
  - "Bad result from RAG" — [#1406](https://github.com/Mintplex-Labs/anything-llm/issues/1406)
  - Feature request: OCR for scanned PDFs — [#2626](https://github.com/Mintplex-Labs/anything-llm/issues/2626)
  - Document-window UI "needs improvements for large corpus of files" (Dec 2025) — [#4776](https://github.com/Mintplex-Labs/anything-llm/issues/4776)
  - Most-reacted RAG request: metadata-based filtering of documents — [#1858](https://github.com/Mintplex-Labs/anything-llm/issues/1858)
- Praise: an HN commenter recommends AnythingLLM for "minimal effort … Pretty much plug and play" local RAG. — [HN 46080364](https://news.ycombinator.com/item?id=46080364)

**Open WebUI** (153.5k stars)
- The most popular self-hosted UI. README covers RAG, MCP, OCR and "encrypt". — [repo](https://github.com/open-webui/open-webui)
- License: changed in v0.6.6 (Apr 2025) to add a branding-protection clause that applies to deployments of 50+ users. — [Open WebUI license docs](https://docs.openwebui.com/license/)
  - HN debate over the change (73 points): claims of a "rugpull" and doubt about whether it meets the Open Source Definition. — [HN 43901575](https://news.ycombinator.com/item?id=43901575)
- Encryption at rest is a recurring gap:
  - Feature request for `sqlite+sqlcipher://` — [#16112](https://github.com/open-webui/open-webui/issues/16112)
  - "at rest encryption not working" (Dec 2025) — [#20051](https://github.com/open-webui/open-webui/issues/20051)
  - Request to "activate or retire AES-GCM envelope encryption (KEK/DEK) for chat messages" (Jul 2026) — [#26895](https://github.com/open-webui/open-webui/issues/26895)
- It is a server/Docker web app, not a turnkey desktop vault. This is an inference from its deployment model.

**Jan** (Menlo Research; Apache-2.0)
- Describes itself as a "cowork-style desktop app — chat, models, MCP connectors, and local API server". — [jan.ai/docs](https://jan.ai/docs)
- Recent changelog items — [jan.ai/changelog](https://jan.ai/changelog):
  - v0.8.0: inline MCP tool approval with citation cards, llama.cpp router mode.
  - v0.7.9: "caps context length to avoid high RAM usage."
  - v0.7.8: OpenClaw integration.
  - v0.8.4 (Jul 2026): native web search.
- RAG maturity is limited. An open request asks to "Dynamically update RAG files attached to projects" (May 2026) — [#8117](https://github.com/janhq/jan/issues/8117). Also "RAG doesn't work as expected" — [#4858](https://github.com/janhq/jan/issues/4858).
- System guidance: macOS 8 GB RAM for 3B models and 16 GB for 7B. — [README](https://raw.githubusercontent.com/janhq/jan/HEAD/README.md)

**LM Studio** (closed-source app; license and pricing **[unverified 2026]**)
- Document chat attaches .docx/.pdf/.txt files. If a document fits in context it is inserted in full; otherwise RAG is used. The docs tell users to "mention terms … you expect to be in the relevant source material", which points to naive retrieval. — [LM Studio RAG docs](https://lmstudio.ai/docs/app/basics/rag)
- MCP **host** since 0.3.17, supporting local and remote servers configured via an `mcp.json` file in Cursor's format. The docs warn: "Never install MCPs from untrusted sources." — [LM Studio MCP docs](https://lmstudio.ai/docs/app/mcp)
- The homepage now promotes "Bionic" agent document editing and local voice. — [lmstudio.ai](https://lmstudio.ai/)
- HN "MCP in LM Studio" (240 points, June 2025) — [HN 44379792](https://news.ycombinator.com/item?id=44379792):
  - Called "the best way to run local LLMs on an Apple Silicon Mac" thanks to MLX support.
  - A user on an 8 GB M1 reports "the laptop gets hot and slow" and resents Electron's memory overhead.
  - Another user asks: "Why go local unless there's private data involved?"

**Msty** (closed-source)
- Knowledge Stacks is Msty's RAG feature. — [Msty docs](https://docs.msty.studio/features/knowledge-stacks/overview)
- Free tier includes chat and Knowledge Stacks. Aurum costs $149/user/year or $349 one-time; Enterprise starts at $300/seat/year with a 5-seat minimum. Pricing comes from search-result summaries of the pricing page; the page fetched on 2026-09-29 did not render the numbers, so treat them as **[partially verified]**. — [msty.ai/pricing](https://msty.ai/pricing/), [Toolradar](https://toolradar.com/tools/msty), [Msty Enterprise blog](https://msty.ai/resources/blog/msty-studio-enterprise-plan-announcement/)
- Msty is expanding into "Go" (agents, formerly "Claw"), "Nexus", and an **upcoming "Msty Stack"**. Stack is described as an "API-first knowledge control plane" that serves versioned Knowledge Stacks to "authenticated clients" and "approved AI apps". This is the closest commercial analog to a "context provider for external agents", but it targets teams and is not shipped yet (waitlist). — [msty.ai](https://msty.ai/), [msty.ai/stack](https://msty.ai/stack/)

**GPT4All** (Nomic; MIT)
- Last release v3.10.0 on 2025-02-25; last push 2025-05-27. — [releases](https://github.com/nomic-ai/gpt4all/releases)
- Nomic's site now sells AEC (architecture/engineering/construction) enterprise agents, "Self Service Starts At $20/Month". GPT4All/LocalDocs remains listed. — [nomic.ai/gpt4all](https://www.nomic.ai/gpt4all)
- LocalDocs complaints, all still open:
  - Slow indexing that doesn't use the hardware — [#1736](https://github.com/nomic-ai/gpt4all/issues/1736)
  - No way to ignore folders — [#2549](https://github.com/nomic-ai/gpt4all/issues/2549)
  - No progress indicator on large collections — [#2579](https://github.com/nomic-ai/gpt4all/issues/2579)
  - Indexing 10 small PDFs produced 500 MB/s of writes for 30 minutes — [#1815](https://github.com/nomic-ai/gpt4all/issues/1815)

**Cherry Studio** (AGPL-3.0; 52k stars)
- Multi-provider AI desktop "studio" with MCP, OCR and knowledge base. Recently repositioned around agents and coding ("claude-code", "codex", "vibe-coding" topics). — [repo](https://github.com/CherryHQ/cherry-studio)

**LobeHub** (formerly LobeChat)
- Now "Chief Agent Operator"; community license. — [repo](https://github.com/lobehub/lobehub)

**Ollama** (runtime, but now also a consumer app)
- The new macOS/Windows app (Jul 2025) supports file drag-and-drop for PDFs. Large documents require raising the context length ("will require more memory"). — [Ollama blog](https://ollama.com/blog/new-app)
- MLX backend on Apple Silicon in preview (Mar 2026; HN 648 points). — [Ollama MLX blog](https://ollama.com/blog/mlx)

#### Per-player detail: self-hosted RAG servers / NotebookLM clones

**RAGFlow**
- Apache-2.0, 91.5k stars; v1.0.0-rc1 released 2026-09-29.
- Deep document understanding (OCR, tables), citations, MCP.
- Rebranded as a "context engine / agent harness". It is a heavy Docker stack aimed at developers and enterprises. — [repo](https://github.com/infiniflow/ragflow)

**Kotaemon**
- Apache-2.0.
- Strong citations: "Advanced citations with document preview … View your citations (incl. relevant score) directly in the in-browser PDF viewer."
- Multimodal QA with figures and tables.
- Local PaddleOCR option.
- Docker "lite/full" images for linux/amd64 and arm64. — [README](https://raw.githubusercontent.com/Cinnamon/kotaemon/HEAD/README.md)
- HN front page in Jan 2025 (191 points). — [HN 42571272](https://news.ycombinator.com/item?id=42571272)

**PrivateGPT (Zylon)**
- v1.0 (June 2026) rebuilt it as an "open-source API layer following the Claude API model".
- Features: retrieval with citations, agentic RAG, custom tools, MCP connectors, remote MCP servers, text-to-SQL, air-gapped operation.
- The history section says it "went viral … crossed 50K stars". — [README](https://raw.githubusercontent.com/zylon-ai/private-gpt/HEAD/README.md)
- It is developer infrastructure, not a consumer app (inference from the README).

**Open Notebook**
- MIT. Describes itself as "a private, multi-model, 100% local, full-featured alternative to Notebook LM" with 18+ providers including Ollama and LM Studio, and 1–4-speaker podcasts.
- Its own comparison table rates its citations as "Basic references (will improve)" vs NotebookLM's "Comprehensive".
- Deployed with Docker plus SurrealDB. Default credentials are root:root "for a zero-config local setup".
- Its encryption key only "encrypts your API keys in the database", not the documents. — [README](https://raw.githubusercontent.com/lfnovo/open-notebook/HEAD/README.md)

**SurfSense**
- Billed as an "Air gapped, privacy focused open source NotebookLM alternative". — [repo](https://github.com/MODSetter/SurfSense)
- **Retiring the hosted web app** and moving users to desktop installers (Windows, macOS arm64, Linux AppImage/deb) with an export/import path.
- "Every role can run locally": the document parser, retrieval model and podcast voice ship inside the installer.
- Generates .pptx/.docx/.xlsx files and podcasts. — [README](https://raw.githubusercontent.com/MODSetter/SurfSense/HEAD/README.md)

**Onyx**
- Enterprise search/chat; MIT core with a proprietary `ee/` directory. — [LICENSE](https://raw.githubusercontent.com/onyx-dot-app/onyx/HEAD/LICENSE)
- Launch HN, Nov 2025 (254 points). — [HN 46045987](https://news.ycombinator.com/item?id=46045987)

**Local Deep Research**
- "Each user gets their own isolated SQLCipher database encrypted with AES-256, with the key derived from your password. Your password is never stored."
- Hardened Docker setup (`cap_drop: ALL`, non-root).
- An "encrypted library" of downloaded sources is indexed and searchable. — [README](https://raw.githubusercontent.com/LearningCircuit/local-deep-research/HEAD/README.md)
- This is the clearest example in the space of **password-derived encryption at rest**, but the product is a research tool, not a personal-document vault.

**DocsGPT, Quivr, localGPT, h2oGPT**
- DocsGPT has moved to enterprise agents. — [repo](https://github.com/arc53/DocsGPT)
- Quivr's last core release was Feb 2025. — [repo](https://github.com/QuivrHQ/quivr)
- h2oGPT is archived. — [repo](https://github.com/h2oai/h2ogpt)

#### Per-player detail: PKM / notes with AI

**Obsidian Copilot** (AGPL)
- The free plugin works with the user's own ChatGPT/Claude subscription or API keys.
- A paid license adds managed models, search, PDF parsing ("tables and layout included, ready to cite") and skills.
- Can now run agents inside Obsidian (OpenCode, Codex, Claude Code). — [obsidiancopilot.com](https://www.obsidiancopilot.com/en), [repo](https://github.com/logancyang/obsidian-copilot)

**Smart Connections**
- "A local embedding model powers semantic search. Zero setup. No API key." — [repo](https://github.com/brianpetro/obsidian-smart-connections)
- Free core plus a Pro tier (e.g., "Smart Graph · Pro"). — [smartconnections.app](https://smartconnections.app/)
- Licensed under a custom "Smart Plugins License Agreement". — [LICENSE](https://raw.githubusercontent.com/brianpetro/obsidian-smart-connections/HEAD/LICENSE)

**Khoj**
- AGPL. Supports images, PDF, Markdown, org-mode, Word and Notion files; runs on-device, in the cloud, or on-prem for enterprise. — [README](https://raw.githubusercontent.com/khoj-ai/khoj/HEAD/README.md)
- The khoj.dev homepage now leads with "Pipali — Our desktop AI co-worker" and a research workbench. — [khoj.dev](https://khoj.dev/)
- No release since 2026-03-26. — [releases](https://github.com/khoj-ai/khoj/releases)

**Reor**
- AGPL. Was a "Private & local AI personal knowledge management app" built on Ollama, Transformers.js and LanceDB. — [README](https://raw.githubusercontent.com/reorproject/reor/HEAD/README.md)
- **Archived**; last release 2025-04-05. — [repo](https://github.com/reorproject/reor)

**Anytype**
- "Local‑first, peer‑to‑peer & end‑to‑end‑encrypted knowledge OS", with "Zero‑knowledge encryption powered by any‑sync". — [README](https://raw.githubusercontent.com/anyproto/anytype-ts/HEAD/README.md)
- License is source-available, not OSI.
- No AI/RAG features appear in the README **[AI status unverified 2026]**.

**SiYuan**
- "AI writing and Q/A chat via OpenAI API"; "Some features are only available to paid members". — [README](https://raw.githubusercontent.com/siyuan-note/siyuan/HEAD/README.md)
- Repo description: "knowledge workspace where humans and AI agents work together"; MCP topic. — [repo](https://github.com/siyuan-note/siyuan)

**Logseq**
- 2.0 "DB version" shipped in July 2026 (2.0.1 on 2026-07-13). — [releases](https://github.com/logseq/logseq/releases), [HN 48896229](https://news.ycombinator.com/item?id=48896229)

**OpenKnowledge** (inkeep, June 2026)
- An "AI-native markdown IDE and LLM wiki" that "build[s] in skills and an MCP server into the app, and auto-install[s] those into e.g. Claude, Codex, and Cursor".
- macOS-only app; the CLI is cross-platform. — [HN 48675435](https://news.ycombinator.com/item?id=48675435)

**basic-memory**
- AGPL; "MCP-native. Works with every major AI client"; local Markdown.
- Optional cloud at "$15.00/mo" (beta pricing). — [README](https://raw.githubusercontent.com/basicmachines-co/basic-memory/HEAD/README.md)

#### Per-player detail: document-management systems + AI (closest to the "life documents" niche)

**Paperless-ngx v3.x** (GPL-3.0; 46k stars)
- Added built-in AI features. — [changelog](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/dev/docs/changelog.md)
  - "Apply AI suggestions" workflow action (v3.1.0).
  - AI suggestions that "prefer existing tags, types, correspondents, and storage paths" (v3.1.0).
  - Document chat backed by a vector store/LLM index (v3.0.x–3.1.3).
  - Selective remote OCR engines (v3.1.0).
  - Support for OpenAI-compatible servers (v3.1.1).
  - "Security: validate remote OCR endpoint" (v3.1.3).
- The README warns that Paperless-ngx "should never be run on an untrusted host" because of how scanned sensitive documents ("social insurance number, tax records, invoices") are stored. The truncated README line implies unencrypted storage; the exact wording was not fully captured. — [README](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/HEAD/README.md)
- It is a Docker/server deployment, not a desktop app (README: "The easiest way to deploy paperless is docker compose").

**paperless-gpt** (MIT)
- "Use LLMs and LLM Vision (OCR)"; v0.28.0 released 2026-09-18. — [repo](https://github.com/icereed/paperless-gpt)

**paperless-ai** (MIT)
- Auto-tagging/analysis with OpenAI, Ollama and others; last release 2025-11-04. — [repo](https://github.com/clusterzx/paperless-ai)

#### Per-player detail: screen memory / lifelogging

**Screenpipe**
- YC S26. Captures "full accessibility tree, OCR as fallback, transcription, speakers, keyboard inputs"; "optional encryption at rest".
- Ships an MCP server: `claude mcp add screenpipe -- npx -y screenpipe-mcp@latest`.
- Licensed under the "Screenpipe Commercial License (source-available; personal, non-commercial use permitted, commercial use requires a license)". — [README](https://raw.githubusercontent.com/screenpipe/screenpipe/HEAD/README.md)
- Launch HN (Jul 2026; 88 points / 67 comments) — [HN 49024620](https://news.ycombinator.com/item?id=49024620):
  - "privacy nightmare"
  - "zero chance im trusting any cloud or third party SaaS if this doesn't run fully local"
  - One user reports a suggested automation "pretty immediately started sending my local api keys to an endpoint".
  - A FOSS developer objects to the switch from MIT to source-available: "FOSS hackers like me feel betrayed".

**Rewind / Limitless**
- Meta acquired Limitless on 2025-12-05. Pendant sales stopped that day; Rewind's screen and audio capture was disabled on 2025-12-19; the service was no longer available in the EU/UK. — [9to5Mac](https://9to5mac.com/2025/12/05/rewind-limitless-meta-acquisition/), [WinBuzzer](https://winbuzzer.com/2025/12/05/meta-acquires-ai-wearables-startup-limitless-kills-pendant-sales-and-sunsets-rewind-app-xcxwbn/)

**Hyperlink by Nexa AI**
- A local "AI agent that finds your files", marketed as "Perplexity for your local files". The NVIDIA RTX build claimed "up to 3x faster indexing and 2x faster LLM inference" and cited answers. — [NVIDIA blog](https://blogs.nvidia.com/blog/rtx-ai-garage-nexa-hyperlink-local-agent/), [Product Hunt](https://www.producthunt.com/products/hyperlink-by-nexa-ai)
- **nexa.ai now states "Nexa AI Is Now Part of Qualcomm AI Hub"**; hyperlink.nexa.ai returned 404 on 2026-09-29. — [nexa.ai](https://nexa.ai/)
- The nexa-sdk repo is now "GenieX … runs only on Qualcomm Snapdragon", © Qualcomm. — [nexa-sdk README](https://raw.githubusercontent.com/NexaAI/nexa-sdk/HEAD/README.md)

#### Platform and cloud incumbents (UX / feature benchmarks)

**OpenAI — ChatGPT Health**
- Announced 2026-01-07; users link patient portals, Apple Health and wellness apps. — [OpenAI](https://openai.com/index/introducing-chatgpt-health/), [Fierce Healthcare](https://www.fiercehealthcare.com/ai-and-machine-learning/openai-launches-chatgpt-health-connect-data-health-apps-medical-records)
- Rolled out broadly to US users by late July 2026. — [gHacks, 2026-07-25](https://www.ghacks.net/2026/07/25/openai-launches-health-in-chatgpt-for-us-users-connecting-apple-health-and-medical-records/), [Fierce Healthcare](https://www.fiercehealthcare.com/ai-and-machine-learning/openai-makes-health-chatgpt-widely-available-moving-deeper-consumer-health)
- Privacy claims: health data sits in a "sandboxed environment separate from the rest of ChatGPT, with its own memory store", is "encrypted in transit and at rest", and is not used for training. OpenAI cites 300M+ health questions per week. — [OpenAI](https://openai.com/index/health-in-chatgpt/)
- HN backlash: "ChatGPT Health is a marketplace, guess who is the product?" (310 points). — [HN 46541533](https://news.ycombinator.com/item?id=46541533)
- A study reported by The Guardian found it "fails to recognise medical emergencies" (Feb 2026). — [Guardian](https://www.theguardian.com/technology/2026/feb/26/chatgpt-health-fails-recognise-medical-emergencies)

**Anthropic — Claude**
- Memory for Pro/Max (Oct 2025) is project-scoped: "each project has its own separate memory", with a view/edit summary and Incognito chats. — [Anthropic](https://www.anthropic.com/news/memory)
- Healthcare push: HIPAA-ready enterprise offerings and connectors (CMS coverage, ICD codes, NPI, PubMed), plus "tools to help individuals understand and navigate their personal health data". The page is undated in the fetch; it references Opus 4.5 and Dec 2025 benchmarks, so it is likely Jan 2026. — [Anthropic](https://www.anthropic.com/news/healthcare-life-sciences)
- Claude Desktop is the MCP host an MCP-exposing vault would plug into (inference).

**Google — Gemini Notebook (formerly NotebookLM)**
- Renamed Gemini Notebook on 2026-07-16. "Same standalone product" that now syncs across the Gemini app and Google Search.
- Adds a "secure cloud computer" for running code (Ultra users first) and "flexible usage limits". — [Google blog](https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/)
- This is the UX benchmark for source-grounded Q&A, citations and audio overviews, and it is cloud-only.

**Apple**
- Apple picked Gemini to power Siri (CNBC, 2026-01-12; HN 1,038 points). — [CNBC](https://www.cnbc.com/2026/01/12/apple-google-ai-siri-gemini.html), [HN 46589675](https://news.ycombinator.com/item?id=46589675)
- WWDC 2026 was held on 2026-06-08. — [Apple event](https://www.apple.com/apple-events/event-stream/)
- A commentary piece calls the new branding "Siri AI". — [Cupertino Lens](https://cupertinolens.com/2026/06/09/wwdc-2026-apple-is-folding/)
- Apple published Private Cloud Compute SOC 3 audit reports (Jul 2026). — [Apple support](https://support.apple.com/guide/certifications/apple-private-cloud-compute-soc-3-audit-apc95a31b9d8/web)
- An Ask HN thread on 2026-09-21 asks: "Is it impossible to disable Siri on macOS 27?" — [HN 49786609](https://news.ycombinator.com/item?id=49786609)
- On-device semantic Spotlight and personal-document Q&A details were **not verified** (see Gaps).

**Microsoft — Recall**
- Recall returned to Windows in April 2025 after its 2024 delay. — [Ars Technica](https://arstechnica.com/security/2025/04/microsoft-is-putting-privacy-endangering-recall-back-into-windows-11/)
- Signal blocked Recall from capturing its desktop app. — [Ars Technica](https://arstechnica.com/security/2025/05/signal-resorts-to-weird-trick-to-block-windows-recall-in-desktop-app/)
- Feb 2026, per Windows Central sources: "Microsoft believes that Recall, in its current implementation, has failed" and is exploring ways to "evolve the concept … possibly dropping the Recall name". Semantic Search and Windows AI APIs continue. — [Windows Central](https://www.windowscentral.com/microsoft/windows-11/microsoft-is-reevaluating-its-ai-efforts-on-windows-11-plans-to-reduce-copilot-integrations-and-evolve-recall), [HN 46854951](https://news.ycombinator.com/item?id=46854951)

**Notion AI**
- PromptArmor showed "Notion AI is susceptible to data exfiltration via indirect prompt injection" hidden in an uploaded resume PDF, because AI edits are saved before user approval (Jan 2026; HN 206 points). — [PromptArmor](https://www.promptarmor.com/resources/notion-ai-unpatched-data-exfiltration), [HN 46531565](https://news.ycombinator.com/item?id=46531565)
- An earlier exfiltration risk was reported in Notion 3.0 agents. — [CodeIntegrity](https://www.codeintegrity.ai/blog/notion)

### Inferences
- Every major open-source "chat with docs" app (AnythingLLM, Jan, LM Studio, Cherry, Open WebUI) is an MCP **client**: it consumes tools. Almost none exposes the user's indexed documents as an MCP **server** to Claude Desktop or Cursor. The exceptions are notes/memory tools (basic-memory, OpenKnowledge, EverOS, mcpvault) and Screenpipe. All of those expose raw notes or captures, not policy-filtered answers from sensitive documents.
- Encryption at rest is rare and usually optional:
  - Local Deep Research uses SQLCipher.
  - Anytype has E2EE but no AI.
  - Screenpipe's encryption is optional and "early".
  - Open WebUI has open issues about it.
  - Paperless-ngx warns against untrusted hosts.
- Licensing drift away from OSI licenses is widespread among the leaders: Open WebUI, LobeHub, Screenpipe, Anytype, Smart Connections, SurfSense's proprietary directory, and EE carve-outs in Onyx and AFFiNE. A genuinely OSI-licensed vault is a differentiator for the privacy crowd, who reacted angrily to the Screenpipe and Open WebUI changes.

### Gaps
- Msty, LM Studio, Hyperlink and Mem are closed-source, so no star or usage data is available. LM Studio's 2026 license and pricing could not be verified in-session (web-search budget exhausted).
- Perplexity Spaces, Mem, ChatGPT Projects/connectors and Notion AI feature and pricing specifics for 2026 were not fetched; no citable 2026 data was collected for them.
- Apple on-device features (semantic Spotlight, whether Siri answers from personal files, where the Gemini-powered Siri runs) are unconfirmed beyond the headlines above.
- Hyperlink's current status after the Qualcomm deal (discontinued, rebranded, or folded into Qualcomm AI Hub) was not confirmed; only the 404 and the nexa.ai banner were observed. The acquisition date is unknown.
- Download counts (for example AnythingLLM desktop installs) were not collected.

---

## Q2. Which players are growing fastest in 2025–2026, which have stalled or died, and why?

### Takeaway
Growth concentrated in four groups:
1. Agent-platform generalists (Open WebUI, RAGFlow, Cherry Studio, AnythingLLM).
2. NotebookLM-style clones (Open Notebook is the breakout, followed by SurfSense).
3. Document parsing infrastructure (Docling doubled).
4. Paperless-ngx, which added native AI.

Single-purpose local doc-chat and PKM apps stalled or died: GPT4All, Reor, h2oGPT, Quivr and localGPT. The consumer lifelogging and local-search startups were absorbed by big companies (Rewind by Meta, Nexa/Hyperlink by Qualcomm).

### Cited Findings

#### Star growth (OSS Insight monthly cumulative; live GitHub 2026-09-29)
| Repo | OSSI 2025-01 | OSSI 2025-09 | 2025 growth (Jan→Sep) | Live 2026-09-29 | Proxy 12-mo gain (live − OSSI Sep-25) |
|---|---|---|---|---|---|
| Open Notebook | 874 | 3,181 | +264% | 39,624 | +36.4k (~12×) |
| SurfSense | 912 | 6,061 | +565% | 16,294 | +10.2k (+169%) |
| Cherry Studio | 4,686 | 28,641 | +511% | 52,236 | +23.6k (+82%) |
| RAGFlow | 28,624 | 56,970 | +99% | 91,495 | +34.5k (+61%) |
| Docling | 17,970 | 33,454 | +86% | 68,176 | +34.7k (+104%) |
| Open WebUI | 59,958 | 98,387 | +64% | 153,529 | +55.1k (+56%) |
| Paperless-ngx | 23,002 | 28,779 | +25% | 46,154 | +17.4k (+60%) |
| AnythingLLM | 29,814 | 45,014 | +51% | 66,599 | +21.6k (+48%) |
| Screenpipe | 11,096 | 14,326 | +29% | 21,776 | +7.5k (+52%) |
| Vane (Perplexica) | 17,908 | 22,928 | +28% | 36,934 | +14.0k (+61%) |
| Jan | 26,046 | 33,367 | +28% | 44,706 | +11.3k (+34%) |
| Khoj | 24,113 | 29,250 | +21% | 37,536 | +8.3k (+28%) |
| LobeHub | 52,045 | 64,634 | +24% | 82,899 | +18.3k (+28%) |
| SiYuan | 28,425 | 36,603 | +29% | 46,558 | +10.0k (+27%) |
| AFFiNE | 45,105 | 53,749 | +19% | 73,092 | +19.3k (+36%) |
| Logseq | 35,237 | 38,765 | +10% | 45,084 | +6.3k (+16%) |
| Onyx* | 10,896 | 13,346 | +22% | 32,286 | +18.9k (*OSSI likely undercounts because of the Danswer→Onyx rename) |
| Obsidian Copilot | 3,492 | 4,826 | +38% | 7,769 | +2.9k |
| Smart Connections | 3,065 | 3,790 | +24% | 5,473 | +1.7k |
| paperless-ai | 1,639 | 3,501 | +114% | 5,954 | +2.5k |
| paperless-gpt | 398 | 1,144 | +187% | 2,719 | +1.6k |
| Local Deep Research | – | 2,856 | – | 9,142 | +6.3k |
| basic-memory | – | 1,293 | – | 4,063 | +2.8k |
| DocsGPT | 14,961 | 16,272 | +9% | 18,295 | +2.0k (+12%) |
| localGPT | 19,596 | 20,786 | +6% | 22,199 | +1.4k (+7%) |
| GPT4All | 68,927 | 72,722 | +5.5% | 77,388 | +4.7k (+6%) |
| PrivateGPT | 52,783 | 54,511 | +3% | 57,551 | +3.0k (+6%) |
| Reor | 7,153 | 7,755 | +8% | 8,549 (archived) | +0.8k |
| h2oGPT | 11,177 | 11,527 | +3% | 11,959 (archived) | +0.4k |
| Sidekick | 70 | 2,668 | (launch spike) | 3,315 | +0.6k |
| Enchanted | 4,286 | 5,195 | +21% | 6,006 | +0.8k |

Sources: OSS Insight API per repo, e.g. [AnythingLLM history](https://api.ossinsight.io/v1/repos/Mintplex-Labs/anything-llm/stargazers/history/?per=month) and [Open Notebook history](https://api.ossinsight.io/v1/repos/lfnovo/open-notebook/stargazers/history/?per=month); live counts from the GitHub repo pages listed in Q1. Kotaemon had no OSS Insight data; EverOS was created 2025-10 and Rowboat 2025-01.

#### New entrants created 2025–2026 with traction
- EverOS: created 2025-10-28, now 13,287 stars. — [repo](https://github.com/EverMind-AI/EverOS)
- Rowboat: 17,985 stars; two HN launches — Feb 2026 (205 points) and Jul 2026 as a "local-first alternative to Claude Desktop" (219 points). — [repo](https://github.com/rowboatlabs/rowboat), [HN 48819808](https://news.ycombinator.com/item?id=48819808)
- OpenKnowledge: created 2026-06, 4,346 stars; HN 381 points. — [HN 48675435](https://news.ycombinator.com/item?id=48675435)
- Deta Surf: 3,585 stars. — [repo](https://github.com/deta/surf)
- LocalGPT (Rust): HN 331 points, Feb 2026. — [HN 46930391](https://news.ycombinator.com/item?id=46930391)
- Atomic, a local-first AI knowledge base (Apr 2026). — [HN 47889110](https://news.ycombinator.com/item?id=47889110)
- The biggest 2026 MCP breakouts are **code** context providers, not personal-document ones:
  - Graphify: 122k stars, created 2026-04. — [repo](https://github.com/Graphify-Labs/graphify)
  - codebase-memory-mcp: 45k stars, created 2026-02. — [repo](https://github.com/DeusData/codebase-memory-mcp)
  - claude-context: 12.6k stars. — [repo](https://github.com/zilliztech/claude-context)
- Agent memory layers are also hot:
  - mem0: 66k stars — [repo](https://github.com/mem0ai/mem0)
  - Graphiti: 31k stars — [repo](https://github.com/getzep/graphiti)
  - Cognee: 31k stars — [repo](https://github.com/topoteretes/cognee)
  - Memori: 17k stars, created 2025-07 — [repo](https://github.com/MemoriLabs/Memori)
  - MemOS: 11.6k stars — [repo](https://github.com/MemTensor/MemOS)

#### Stalled, died, or acquired
- GPT4All: no release since 2025-02-25 and no push since 2025-05-27. Nomic now sells AEC enterprise agents. — [releases](https://github.com/nomic-ai/gpt4all/releases), [nomic.ai](https://www.nomic.ai/gpt4all)
- Reor: archived; last release 2025-04-05. — [repo](https://github.com/reorproject/reor)
- h2oGPT: archived; last push 2025-10-09. — [repo](https://github.com/h2oai/h2ogpt)
- Quivr: last core release 2025-02-04. — [repo](https://github.com/QuivrHQ/quivr)
- paperless-ai: last release 2025-11-04. — [repo](https://github.com/clusterzx/paperless-ai)
- Khoj: last release 2026-03-26; the company homepage now leads with other products (Pipali). — [khoj.dev](https://khoj.dev/)
- Rewind/Limitless: acquired by Meta on 2025-12-05; the app was killed on 2025-12-19. — [9to5Mac](https://9to5mac.com/2025/12/05/rewind-limitless-meta-acquisition/)
- Nexa AI (Hyperlink): now "Part of Qualcomm AI Hub"; the SDK is Snapdragon-only. — [nexa.ai](https://nexa.ai/), [nexa-sdk README](https://raw.githubusercontent.com/NexaAI/nexa-sdk/HEAD/README.md)
- Microsoft Recall: judged internally as having "failed" in its current form (Feb 2026 report). — [Windows Central](https://www.windowscentral.com/microsoft/windows-11/microsoft-is-reevaluating-its-ai-efforts-on-windows-11-plans-to-reduce-copilot-integrations-and-evolve-recall)
- SurfSense: retiring its hosted SaaS in favor of a local desktop app. — [README](https://raw.githubusercontent.com/MODSetter/SurfSense/HEAD/README.md)
- Pivots and repositioning:
  - PrivateGPT pivoted from a consumer script to an API layer (v1.0, June 2026). — [README](https://raw.githubusercontent.com/zylon-ai/private-gpt/HEAD/README.md)
  - LobeHub repositioned as an agent operator. — [repo](https://github.com/lobehub/lobehub)
  - Cherry Studio and AnythingLLM are re-tagging toward agents and computer use. — [Cherry repo](https://github.com/CherryHQ/cherry-studio), [AnythingLLM repo](https://github.com/Mintplex-Labs/anything-llm)

### Inferences
- **Why the winners grew:**
  - They became general "AI workspaces/agent harnesses" with MCP, multi-provider support and web search (Open WebUI, Cherry, AnythingLLM, RAGFlow's "context engine").
  - Or they cloned a beloved cloud UX (NotebookLM → Open Notebook, SurfSense).
  - Or they rode document-parsing demand (Docling, markitdown).
  - Paperless-ngx's surge (+60%) suggests that **"AI over my household paperwork" is a real pull**, even inside a Docker server product.
- **Why the losers stalled:**
  - A single-feature "chat with local docs" product is hard to monetize and quickly gets commoditized by the generalists (GPT4All's LocalDocs, Reor, localGPT, h2oGPT, Quivr).
  - Hardware and platform companies buy the teams: Meta bought Limitless, Qualcomm bought Nexa.
  - Platform-native memory (Recall) ran into trust backlash.
  - Pattern: the market rewards breadth plus agents; the personal-sensitive-document use case has no dedicated, healthy OSS leader.
- The 2026 attention wave for "context providers to agents" (Graphify, codebase-memory-mcp, memory layers) is almost entirely **developer/code-centric**. A consumer/personal-document equivalent has not broken out. That is either white space or a sign of weaker demand (see Q4).

### Gaps
- True 2026 month-by-month growth is uncertain because OSS Insight undercounts 2026 relative to live GitHub. star-history.com's SVG endpoint responded (HTTP 200) but was not parsed.
- No explicit statements were found on *why* Reor was archived or why Nomic de-prioritized GPT4All; the reasons above are inferred.
- Commercial-traction data (revenue, downloads) for Msty, LM Studio, AnythingLLM and Screenpipe is not public in the sources collected.

---

## Q3. What do users complain about, and what do they want but can't get?

### Takeaway
The recurring complaints are:
- Poor retrieval quality on real-world queries, and weak scanned-PDF/table handling.
- Slow, opaque indexing of large folders.
- RAM and heat on laptops.
- Docker/server-only installs.
- No encryption at rest.
- License rug-pulls.
- Fear that "memory" tools leak data (Recall, Screenpipe, Notion AI, ChatGPT Health).

Users want something that "just works" locally, cites sources precisely, stays private in a verifiable way, and plugs into the agents they already use.

### Cited Findings

#### Retrieval quality
- A builder reports ~90% recall on internal tests, but "when the first actual users tried it, it could barely answer anything (closer to 30%)", because testers relied on exact keywords they already knew. — [HN 46080364 (kgeist)](https://news.ycombinator.com/item?id=46080364)
- Simon Willison suggests full-text search/grep in an agentic loop can beat vector-DB-only setups; others argue for hybrid BM25 plus semantic ranking. — [HN 46080364](https://news.ycombinator.com/item?id=46080364)
- A commenter notes there is no standard eval dataset for local RAG. — [HN 46080364](https://news.ycombinator.com/item?id=46080364)
- AnythingLLM users report RAG "unusable in all versions" ([#2087](https://github.com/Mintplex-Labs/anything-llm/issues/2087)), "Bad result from RAG" ([#1406](https://github.com/Mintplex-Labs/anything-llm/issues/1406)), and "RAG feature returning incorrect count of records" ([#4275](https://github.com/Mintplex-Labs/anything-llm/issues/4275)).
- Jan: "RAG doesn't work as expected" — [#4858](https://github.com/janhq/jan/issues/4858)
- LM Studio's own docs push the burden onto the user: "Mention terms, ideas, and words you expect to be in the relevant source material". — [LM Studio docs](https://lmstudio.ai/docs/app/basics/rag)

#### Scanned PDFs, tables, OCR, citations
- AnythingLLM OCR request for scanned PDFs — [#2626](https://github.com/Mintplex-Labs/anything-llm/issues/2626)
- AnythingLLM request for a "RAG + OCR with Preprocessing" workflow — [#2059](https://github.com/Mintplex-Labs/anything-llm/issues/2059)
- Paperless-ngx v3 had to fix born-digital PDF detection and "don't skip OCR/archive for tagged PDFs with no actual text". — [changelog](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/dev/docs/changelog.md)
- Kotaemon differentiates on in-PDF citation preview with relevance scores. — [README](https://raw.githubusercontent.com/Cinnamon/kotaemon/HEAD/README.md)
- Open Notebook admits its citations are "Basic references (will improve)". — [README](https://raw.githubusercontent.com/lfnovo/open-notebook/HEAD/README.md)
- Obsidian Copilot sells PDF parsing with "tables and layout included, ready to cite" as a paid feature. — [obsidiancopilot.com](https://www.obsidiancopilot.com/en)

#### Indexing speed, scale, control
- GPT4All LocalDocs issues, all open:
  - Slow indexing — [#1736](https://github.com/nomic-ai/gpt4all/issues/1736)
  - Heavy disk writes — [#1815](https://github.com/nomic-ai/gpt4all/issues/1815)
  - No progress indicator — [#2579](https://github.com/nomic-ai/gpt4all/issues/2579)
  - Can't ignore folders — [#2549](https://github.com/nomic-ai/gpt4all/issues/2549)
  - Hangs — [#3071](https://github.com/nomic-ai/gpt4all/issues/3071)
- AnythingLLM's document UI struggles with large corpora — [#4776](https://github.com/Mintplex-Labs/anything-llm/issues/4776)
- Jan: "Dynamically update RAG files attached to projects" (no live folder sync) — [#8117](https://github.com/janhq/jan/issues/8117)
- Hyperlink marketed "a dense 1GB folder that would previously take almost 15 minutes to index" being made faster. Indexing time is a known pain point. — [NVIDIA blog](https://blogs.nvidia.com/blog/rtx-ai-garage-nexa-hyperlink-local-agent/)

#### RAM, heat, laptops
- An 8 GB M1 user running a 4B model: "the laptop gets hot and slow" and "waste a gig of memory on Electron". — [HN 44379792](https://news.ycombinator.com/item?id=44379792)
- Jan v0.7.9 "caps context length to avoid high RAM usage"; Jan's README guidance is 8 GB for 3B models and 16 GB for 7B. — [Jan changelog](https://jan.ai/changelog), [README](https://raw.githubusercontent.com/janhq/jan/HEAD/README.md)
- Ollama warns that increasing context for large documents "will require more memory". — [Ollama blog](https://ollama.com/blog/new-app)
- Cloud quality is the other reason people don't go local: "I'm spoiled by Claude 4 Opus; local LLMs are slower and lower quality"; "Why go local unless there's private data involved?" — [HN 44379792](https://news.ycombinator.com/item?id=44379792)

#### Install friction
- Many of the strongest RAG stacks are Docker-first: Kotaemon, RAGFlow, Open Notebook (Docker plus SurrealDB with root:root defaults), Paperless-ngx (docker compose), Open WebUI. — [Kotaemon README](https://raw.githubusercontent.com/Cinnamon/kotaemon/HEAD/README.md), [Open Notebook README](https://raw.githubusercontent.com/lfnovo/open-notebook/HEAD/README.md), [Paperless README](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/HEAD/README.md)
- Local Deep Research documents Docker pitfalls on Mac and Windows: `--network host` "silently fails". — [README](https://raw.githubusercontent.com/LearningCircuit/local-deep-research/HEAD/README.md)
- SurfSense moving from web to desktop installers shows the pull toward one-click desktop apps. — [README](https://raw.githubusercontent.com/MODSetter/SurfSense/HEAD/README.md)

#### Privacy, trust, encryption
- Open WebUI encryption-at-rest requests and bugs: [#16112](https://github.com/open-webui/open-webui/issues/16112), [#20051](https://github.com/open-webui/open-webui/issues/20051), [#26895](https://github.com/open-webui/open-webui/issues/26895)
- Screenpipe Launch HN: "privacy nightmare"; "zero chance im trusting any cloud … if this doesn't run fully local"; an automation "started sending my local api keys to an endpoint". — [HN 49024620](https://news.ycombinator.com/item?id=49024620)
- Recall backlash, including Signal blocking it. — [Ars Technica](https://arstechnica.com/security/2025/05/signal-resorts-to-weird-trick-to-block-windows-recall-in-desktop-app/)
- ChatGPT Health skepticism ("guess who is the product", 310 points). — [HN 46541533](https://news.ycombinator.com/item?id=46541533)
- Notion AI prompt-injection exfiltration via an uploaded PDF. — [PromptArmor](https://www.promptarmor.com/resources/notion-ai-unpatched-data-exfiltration)
- "Document poisoning in RAG systems" (HN 155 points, Mar 2026). — [HN 47350407](https://news.ycombinator.com/item?id=47350407)

#### Licensing and trust in openness
- Open WebUI license change (HN 43901575): "use a permissive/pushover license to get adoption, then rugpull". — [HN 43901575](https://news.ycombinator.com/item?id=43901575)
- Screenpipe's switch from MIT to source-available: "FOSS hackers like me feel betrayed". — [HN 49024620](https://news.ycombinator.com/item?id=49024620)
- On OpenKnowledge: "there genuinely ought to be consequences for using 'open source' in the context of something like this tied to proprietary AI services. Local models should be the first choice". — [HN 48675435](https://news.ycombinator.com/item?id=48675435)

#### Interoperability and agents
- On OpenKnowledge, one user wants knowledge that is "(1) versioned … (2) usable from any chat (a la MCP) (3) basic access controls". Another asks for migration from Obsidian/Notion. A third criticizes "Fully local, but can't integrate with any local LLM?" and wants Android. — [HN 48675435](https://news.ycombinator.com/item?id=48675435)

#### Mobile and cross-device
- AnythingLLM now pairs an Android app with desktop ("reach larger models and your full workspaces from anywhere"). — [anythingllm.com](https://anythingllm.com/)
- Gemini Notebook syncs across the Gemini app and Search. — [Google blog](https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/)
- The OpenKnowledge commenter wants Android. — [HN 48675435](https://news.ycombinator.com/item?id=48675435)

### Inferences
Ranked list of unmet wants for a personal-document vault:
1. One-click desktop install with no Docker, working on a 16 GB laptop.
2. Reliable ingestion of scanned PDFs, photos of receipts and IDs, and tables, with OCR on by default.
3. Precise, clickable citations down to page and region.
4. Fast incremental indexing of watched folders, with progress, exclusions and dedupe.
5. Hybrid lexical plus semantic retrieval that works with the vague, real-world phrasing users actually type.
6. Encryption at rest by default, with a password- or keychain-derived key.
7. Verifiable "nothing leaves the device": no telemetry by default, network kill-switch or audit log.
8. A durable OSI license with no future rug-pull.
9. Safe exposure to external agents (Claude/Cursor) without handing over raw files, with protection against prompt-injection exfiltration.
10. Mobile access or capture and family/household sharing.

Current products address 3–4 of these at most.

"Family sharing" and "household" multi-user needs are served only by server-style products (Paperless-ngx, Open WebUI and AnythingLLM multi-user). No desktop-first private vault offers household sharing (inference from the feature surveys above).

### Gaps
- Reddit (r/LocalLLaMA, r/selfhosted, r/privacy, r/ObsidianMD) was blocked (HTTP 403), so no Reddit quotes are included. Sentiment there should be sampled separately.
- GitHub reaction counts on RAG-quality issues are low (single to double digits). Complaint *volume* is therefore anecdotal, not quantified.
- No survey data was found quantifying demand for family sharing or mobile access.

---

## Q4. Where is the white space? (Personal life-documents vault, and private context provider for external agents via MCP)

### Takeaway
No actively maintained, OSI-licensed desktop product combines all of the following:
- Local LLM Q&A.
- Encryption at rest by default.
- A life-admin document model (medical, tax, legal, IDs, receipts, with OCR and structured fields).
- An MCP server that gives external agents *mediated* answers (redacted, cited, policy-scoped) instead of raw files.

The adjacent positions are each missing pieces:
- Paperless-ngx has the right document model, but it is a server with no encryption or MCP.
- Local Deep Research has the right encryption, but the wrong domain.
- Screenpipe, basic-memory and OpenKnowledge have the MCP-server pattern, but for screen captures and notes; Screenpipe is source-available.
- ChatGPT Health and Claude have the health-records UX, but in the cloud.

### Cited Findings

#### Demand signal for "life documents + AI" is strong, and incumbents are going cloud
- OpenAI built a dedicated, sandboxed Health space for medical records and Apple Health: "300 million people" ask health questions weekly, and it rolled out broadly in the US in Jul 2026. — [OpenAI](https://openai.com/index/health-in-chatgpt/), [gHacks](https://www.ghacks.net/2026/07/25/openai-launches-health-in-chatgpt-for-us-users-connecting-apple-health-and-medical-records/)
- Anthropic added "tools to help individuals understand and navigate their personal health data". — [Anthropic](https://www.anthropic.com/news/healthcare-life-sciences)
- The privacy backlash is visible (HN 310 points) — [HN 46541533](https://news.ycombinator.com/item?id=46541533) — as are safety failures. — [Guardian](https://www.theguardian.com/technology/2026/feb/26/chatgpt-health-fails-recognise-medical-emergencies)
- Paperless-ngx (the household-paperwork DMS) grew about 60% in 12 months to 46k stars. It added AI suggestions and chat in v3, and its ecosystem add-ons (paperless-gpt, paperless-ai) grew over 100% in 2025. — [repo](https://github.com/paperless-ngx/paperless-ngx), [paperless-gpt](https://github.com/icereed/paperless-gpt), [paperless-ai](https://github.com/clusterzx/paperless-ai)
- Paperless-ngx explicitly names sensitive scans ("social insurance number, tax records, invoices") and warns against untrusted hosts, but provides no built-in encryption story. — [README](https://raw.githubusercontent.com/paperless-ngx/paperless-ngx/HEAD/README.md)
- Platform players stepped back or went cloud:
  - Microsoft Recall "has failed" (Feb 2026 report). — [Windows Central](https://www.windowscentral.com/microsoft/windows-11/microsoft-is-reevaluating-its-ai-efforts-on-windows-11-plans-to-reduce-copilot-integrations-and-evolve-recall)
  - Apple chose Gemini to power Siri. — [CNBC](https://www.cnbc.com/2026/01/12/apple-google-ai-siri-gemini.html)
  - Rewind is gone. — [9to5Mac](https://9to5mac.com/2025/12/05/rewind-limitless-meta-acquisition/)
  - Hyperlink has been absorbed into Qualcomm. — [nexa.ai](https://nexa.ai/)

#### MCP context-provider niche: the pattern is validated for code and notes, not for sensitive documents
Existing MCP servers over personal data:
- Screenpipe (screen/audio history; source-available; optional encryption). — [README](https://raw.githubusercontent.com/screenpipe/screenpipe/HEAD/README.md)
- basic-memory (Markdown notes; AGPL; $15/mo cloud). — [README](https://raw.githubusercontent.com/basicmachines-co/basic-memory/HEAD/README.md)
- OpenKnowledge (Markdown wiki; auto-installs MCP/skills into Claude, Codex and Cursor; macOS). — [HN 48675435](https://news.ycombinator.com/item?id=48675435)
- mcpvault (safe Obsidian vault access; 1.7k stars). — [repo](https://github.com/bitbonsai/mcpvault)
- EverOS (portable memory; Apache-2.0). — [repo](https://github.com/EverMind-AI/EverOS)
- Small "vault" MCP servers — [vault-mcp](https://github.com/nikhgupta/vault-mcp), [memory-vault (64 stars)](https://github.com/MihaiBuilds/memory-vault), [VaultPDF MCP](https://glama.ai/mcp/servers/AlexeySamosadov/vaultpdf-mcp):
  - vault-mcp "turns a local folder … into a searchable knowledge base for AI assistants via MCP" and embeds "markdown, PDFs, images, audio, video".
  - VaultPDF lets MCP hosts "work with PDFs on the user's own machine — files are never uploaded".
  - The coverage is fragmented and hobby-scale.

Other relevant data points:
- The largest MCP projects of 2026 are code-context servers: Graphify (122k stars), codebase-memory-mcp (45k) and claude-context (12.6k), plus awesome-mcp-servers (95.7k). — [Graphify](https://github.com/Graphify-Labs/graphify), [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp), [claude-context](https://github.com/zilliztech/claude-context), [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- Enterprise players are building governed context layers:
  - Msty Stack, still upcoming, "serve[s] context only to clients with valid credentials". — [msty.ai/stack](https://msty.ai/stack/)
  - PrivateGPT v1.0 is an API layer with MCP. — [README](https://raw.githubusercontent.com/zylon-ai/private-gpt/HEAD/README.md)
  - PipesHub offers "permission-aware search with verified citations" for agents (3.8k stars). — [repo](https://github.com/pipeshub-ai/pipeshub-ai)
  - FutureVault launched MCP for enterprise document vaults. — [FutureVault](https://www.futurevault.com/futurevault-launches-mcp-and-ai-orchestration-layer/)
- The popular local chat apps (AnythingLLM, LM Studio, Jan) are MCP hosts/clients and warn about MCP risk ("Never install MCPs from untrusted sources"). None of them positions its document index as an MCP server for other agents. — [AnythingLLM MCP docs](https://docs.anythingllm.com/mcp-compatibility/overview), [LM Studio MCP docs](https://lmstudio.ai/docs/app/mcp), [Jan docs](https://jan.ai/docs)
- Security precedent for why "no raw documents" matters:
  - Notion AI exfiltration via a prompt injection in an uploaded PDF. — [PromptArmor](https://www.promptarmor.com/resources/notion-ai-unpatched-data-exfiltration)
  - A Screenpipe user saw API keys sent to an endpoint. — [HN 49024620](https://news.ycombinator.com/item?id=49024620)
  - RAG document-poisoning discussion. — [HN 47350407](https://news.ycombinator.com/item?id=47350407)

#### Encryption-at-rest precedents to emulate
- Local Deep Research: per-user SQLCipher AES-256 with a password-derived key that is never stored. — [README](https://raw.githubusercontent.com/LearningCircuit/local-deep-research/HEAD/README.md)
- Anytype: zero-knowledge E2EE with P2P sync. — [README](https://raw.githubusercontent.com/anyproto/anytype-ts/HEAD/README.md)
- ChatGPT Health, the cloud benchmark: "sandboxed … its own memory store … encrypted in transit and at rest". — [OpenAI](https://openai.com/index/health-in-chatgpt/)

### Inferences
**White space 1 — the "personal life-documents vault" (desktop, encrypted, local-LLM).**
- The closest OSS products are Paperless-ngx (DMS plus AI, but Docker/server, unencrypted, no MCP, no desktop UX) and AnythingLLM/Jan/Msty (desktop, but generic chat, no document schema, no default encryption).
- A product that ships the following would occupy an uncontested position:
  - A single-installer desktop app with auto-OCR for scans and photos.
  - Life-admin document types: medical records/labs, tax forms, contracts, IDs/passports with expiry dates, receipts/warranties, insurance.
  - Structured field extraction and reminders (e.g., "passport expires in 5 months").
  - Page-level citations.
  - An encrypted store and index.
- It would also inherit the demand that ChatGPT Health is proving, among users who refuse to upload medical records to the cloud.

**White space 2 — a "private context provider" MCP server with mediation.**
- Existing personal MCP servers pass through raw content: note files, screen captures, PDFs.
- The unclaimed design is an MCP server that:
  - returns answers, extracted fields and citations with redaction policies (e.g., mask SSNs/account numbers);
  - enforces per-agent, per-collection scopes and consent prompts;
  - logs every access to an audit log;
  - never streams raw documents unless explicitly allowed.
- In effect this is "Msty Stack / PipesHub-style governance" for individuals, fully local. It speaks to the exfiltration fears in the Notion and Screenpipe threads and lets users keep using Claude/Cursor for reasoning while the vault holds the data.
- The enterprise versions (Msty Stack, PrivateGPT API, PipesHub, FutureVault) confirm the concept; none targets individuals on a laptop.

**Combination nobody delivers:** OSI license, plus a one-click desktop install on a 16 GB laptop, plus encrypted-by-default storage, plus OCR/table-aware ingestion with page citations, plus a life-document schema and reminders, plus a mediated MCP server with audit and redaction, plus optional household sharing and a mobile companion.

**Risks and counter-signals:**
- Single-purpose local doc-chat apps have a poor survival record: GPT4All, Reor, h2oGPT and Quivr stalled; Rewind and Nexa were acquired.
- Generalists (AnythingLLM, Jan, Cherry, Open WebUI) could add encryption plus an MCP-server mode relatively quickly.
- Cloud incumbents (ChatGPT Health, Claude, Gemini Notebook) are moving fast on health and life data, with strong UX and "encrypted, not used for training" messaging.
- Local model quality and RAM limits remain a real objection ("local LLMs are slower and lower quality").
- A mediated-MCP design that lets users *choose* Claude for reasoning over locally-held data may be the pragmatic answer to that objection.

**Launch positioning:**
- Lean into verifiable privacy: an OSI license (the backlash against Open WebUI's and Screenpipe's license changes shows this matters), encryption on by default, no telemetry by default, and a network audit log.
- Build ingestion on commodity parsers (Docling at 68k stars and markitdown at 188k show parsing is solved infrastructure) rather than competing on generic chat.

### Gaps
- No quantitative market sizing was found for consumer demand for a local personal-document vault (e.g., survey data on willingness to pay, or share of users who refuse cloud health uploads).
- No OSS project dedicated to personal medical/tax/ID document management with local LLMs and meaningful traction (>1k stars) was found. It may exist under names not searched; web search was exhausted, and GitHub topic searches for such terms returned nothing relevant.
- The specifics of Apple's on-device personal-context features in iOS/macOS 27 (which could compete directly on Mac) were not verified.
- Whether Msty Stack has shipped, or whether AnythingLLM/Jan plan an MCP-server mode, is unknown beyond the pages cited.
