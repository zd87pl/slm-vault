# MCP / AI-Agent Ecosystem and Privacy-Security-Trust Engineering for a Local Document Vault (state as of late September 2026)

Research date: 2026-09-29. Dates are given wherever the sources give them. Items marked **[older]** come from 2025 and may be superseded. Items marked **[secondary]** come from aggregators or blogs, not primary sources.

---

## 1. MCP spec versions, major 2025–2026 features, registry, .mcpb bundles, and client support

### Takeaway
The current MCP specification is **2026-07-28**, published July 28, 2026. It makes the protocol **stateless**: there is no `initialize` handshake and no `Mcp-Session-Id`. It also adds a formal extensions framework, with MCP Apps, Tasks and Enterprise-Managed Auth as official extensions, and tightens OAuth. It **deprecates Roots, Sampling, Logging, HTTP+SSE and Dynamic Client Registration**, each with a minimum 12-month window. This suits a vault well: it will run its own local LLM (it doesn't need client-side sampling) and can ask for user confirmation mid-call through Multi Round-Trip Requests. For local desktop distribution, the .mcpb one-click bundle is the de facto path into Claude Desktop. ChatGPT only accepts remote HTTPS servers.

### Cited Findings
**Spec version timeline**
- 2024-11-05: first spec. It defined tools, resources and prompts over JSON-RPC 2.0, with stdio and HTTP+SSE transports — [hidekazu-konishi timeline](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html) [secondary]
- 2025-03-26: OAuth 2.1 authorization, **Streamable HTTP** (replacing HTTP+SSE), tool annotations, audio content, completions, JSON-RPC batching — [timeline](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html) [older]
- 2025-06-18: **structured tool output**, **elicitation**, **resource links in tool results**, MCP servers classified as OAuth Resource Servers, batching removed, security best-practices doc added — [timeline](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html) [older]
- 2025-11-25: OpenID Connect Discovery, icon metadata, standards-based elicitation enums, tool calling inside sampling, **Client ID Metadata Documents (CIMD)**, experimental tasks, JSON Schema 2020-12 as default — [timeline](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html) [older]
- **2026-07-28 (current)**. The RC was published May 21, 2026 and the final spec on July 28, 2026 — [MCP blog: RC](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/); [MCP blog: final](https://blog.modelcontextprotocol.io/posts/2026-07-28/). Contents:
  - "MCP is transforming from a bidirectional stateful protocol into a request/response stateless protocol." The `initialize`/`initialized` handshake and the `Mcp-Session-Id` header are removed. Each request now carries protocol version, client identity and capabilities in `_meta`. An optional `server/discover` RPC is available — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  - **Multi Round-Trip Requests (MRTR)** replace server-initiated `elicitation/create`, `sampling/createMessage` and `roots/list`. The server returns `resultType: "input_required"`, and the client retries the call with `inputResponses`, "enabling mid-call confirmations over stateless protocols" — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  - `Mcp-Method` and `Mcp-Name` HTTP headers let gateways and WAFs route and meter requests without parsing the body. List and read results carry `ttlMs`/`cacheScope` for caching — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  - Auth hardening:
    - RFC 9207 `iss` validation (defends against mix-up attacks)
    - `application_type` in client registration, so desktop and CLI localhost redirects work
    - client credentials bound to their issuer
    - CIMD formally replaces DCR, with DCR deprecated on a 12-month window
    - [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  - Official extensions: **Tasks** (`tasks/get`, `tasks/update`, `tasks/cancel`; notifications consolidated into `subscriptions/listen`), **MCP Apps**, and **Enterprise Managed Authorization** — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  - **Deprecated:** Roots, Sampling, Logging, HTTP+SSE transport, DCR. The formal deprecation policy guarantees a minimum 12-month window, so nothing deprecated on 2026-07-28 can be removed before a revision dated on or after 2027-07-28 — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/); [AAIF migration post](https://aaif.io/blog/mcp-2026-07-28-whats-changing-and-how-to-migrate)
  - Tier-1 SDKs updated to 2026-07-28: TypeScript, Python, Go and C#. The Rust SDK is in beta — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
  - GitHub's MCP server supported the new spec by July 23, 2026 — [GitHub Changelog](https://github.blog/changelog/2026-07-23-github-mcp-server-supports-the-next-mcp-specification/)
  - One secondary source says the revision "adds OAuth/OIDC formalization and OpenTelemetry tracing but omits permission models and response integrity verification" — [The Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/) [secondary]. The official blog summary I read does not mention OpenTelemetry, so treat that part as unverified.

**Governance**
- On Dec 9, 2025 the Linux Foundation formed the **Agentic AI Foundation (AAIF)**. Its founding projects were Anthropic's MCP, Block's **goose** and OpenAI's **AGENTS.md**. Platinum members: AWS, Anthropic, Block, Bloomberg, Cloudflare, Google, Microsoft, OpenAI — [Linux Foundation press release](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)
- AAIF reportedly had 146 members by April 2026 — [search summary citing IntuitionLabs/ChatForest](https://intuitionlabs.ai/articles/agentic-ai-foundation-open-standards) [secondary]
- Adoption milestones: OpenAI Agents SDK adopted MCP on Mar 26, 2025; Google committed Gemini to MCP on Apr 9, 2025; OpenAI joined the steering committee on May 21, 2025 — [timeline](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html) [secondary, older]

**MCP Apps (UI extension)**
- MCP Apps launched on 2026-01-26 as "the first official MCP extension". Tools can return interactive UI (forms, dashboards, multi-step workflows). UI is declared as `ui://` resources that render in sandboxed iframes — [MCP blog, Jan 26 2026](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/); [spec](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx)
- August 2026 host support: Claude (web and Desktop), VS Code GitHub Copilot, Microsoft 365 Copilot, Goose, Postman, MCPJam, **ChatGPT**, **Cursor**, Archestra.AI, PostHog Code. JetBrains, Kiro and Antigravity were still "exploring" — [DevMoment field log](https://www.devmoment.dev/journal/mcp-apps-field-log-2026) [secondary]. That source says "eleven clients" but lists ten.
- Gotchas:
  - The extension negotiates under the identifier `io.modelcontextprotocol/ui`.
  - If either side omits the declaration, tools silently fall back to text.
  - The sandbox uses a deny-by-default CSP, and apps "cannot touch the parent DOM, cannot read the host's cookies or local storage".
  - [DevMoment](https://www.devmoment.dev/journal/mcp-apps-field-log-2026)

**Registry**
- The official MCP Registry launched in **preview on Sept 8, 2025**. It provides standardized server metadata, namespace verification, package references and an API that downstream registries build on — [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry); [registry docs](https://registry.modelcontextprotocol.io/docs)
- It was reported as **still in preview as of July 20, 2026**. It is "intentionally minimal", and browsing UIs are left to Smithery, Glama, PulseMCP and others — [Digital Thought Disruption](https://digitalthoughtdisruption.com/2026/07/20/mcp-registry-discover-verify-safely-connect-servers/) [secondary]

**.mcpb (MCP Bundles, formerly .dxt Desktop Extensions)**
- An .mcpb is a zip archive holding a local MCP server plus a `manifest.json`. Installation is one click or drag-and-drop in Claude Desktop (Settings > Extensions) — [modelcontextprotocol/mcpb](https://github.com/modelcontextprotocol/mcpb); [Claude docs](https://claude.com/docs/connectors/building/mcpb)
- The format was renamed from .dxt in late 2025. On Nov 20, 2025 it moved to the MCP org as an open format — [MCP blog: adopting MCPB](https://blog.modelcontextprotocol.io/posts/2025-11-20-adopting-mcpb/)
- The manifest supports `user_config`, with **sensitive fields stored in the OS keychain**. The CLI has `mcpb sign`/`verify`. Node.js is recommended because it ships inside Claude for macOS/Windows, and Python bundles are supported through the UV runtime (v0.4+). About 2.1k GitHub stars — [mcpb repo](https://github.com/modelcontextprotocol/mcpb)
- Other vendors ship .mcpb too, e.g. the Azure MCP Server — [Azure SDK Blog](https://devblogs.microsoft.com/azure-sdk/azure-mcp-server-mcpb-support/)

**Client support snapshot**
- **ChatGPT:**
  - Developer Mode with full MCP tools was announced Sept 2025.
  - It connects only to **remote HTTPS servers (Streamable HTTP/SSE), not local stdio**.
  - It's available on Plus, Pro, Business, Enterprise and Edu, not the free tier.
  - The Apps SDK adds UI, OAuth scaffolding and catalog review.
  - Sources: [OpenAI Help Center](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt); [OpenAI dev docs](https://developers.openai.com/api/docs/guides/developer-mode); [DesignRevision](https://designrevision.com/blog/add-mcp-server-to-chatgpt) [secondary]
- **LM Studio** has been an MCP host since v0.3.17 (June 2025). It supports local and remote servers configured via `mcp.json`, plus an "Add to LM Studio" deeplink button — [LM Studio docs](https://lmstudio.ai/docs/app/mcp); [LM Studio blog](https://lmstudio.ai/blog/lmstudio-v0.3.17)
- **Zed** supports only the MCP **Tools and Prompts** features (no resources) — [Zed docs](https://zed.dev/docs/ai/mcp)
- **Cursor** historically capped MCP tools at **40 in total**, across all servers — [Cursor forum](https://forum.cursor.com/t/mcp-server-40-tool-limit-in-cursor-is-this-frustrating-your-workflow/81627) [older, 2025; may have changed]
- **VS Code / GitHub Copilot** caps each request at **128 tools** — [search summary / microsoft/vscode#248368](https://github.com/microsoft/vscode/issues/248368) [older]
- **Windows 11** has native MCP through the **On-device Agent Registry (ODR)**:
  - MCP servers are "contained in a separate environment by default".
  - Users and admins control access per agent through Settings/Intune.
  - Interactions are logged and auditable.
  - `odr.exe` is the CLI.
  - Built-in File Explorer and Settings connectors are included.
  - The docs still carry a "prereleased product" notice, updated 2026-06-04.
  - Sources: [Microsoft Learn](https://learn.microsoft.com/en-us/windows/ai/mcp/overview); [Windows Dev Blog, Ignite Nov 2025](https://blogs.windows.com/windowsdeveloper/2025/11/18/ignite-2025-furthering-windows-as-the-premier-platform-for-developers-governed-by-security/)
- **OpenClaw** supports MCP servers natively ("the same MCP servers that work with Claude Code work with OpenClaw"). It can also run as a stdio MCP server — [search summary of Developers Digest/CrewClaw](https://www.developersdigest.tech/blog/what-is-openclaw-guide-2026) [secondary]

### Inferences
- **Target spec 2026-07-28 with a stdio transport for local clients.** Keep 2025-11-25 compatibility, because many clients will lag through 2027. Don't design around Sampling (deprecated). The vault's local LLM should do the synthesis itself, which fits the product thesis.
- **Use MRTR `input_required` for in-band confirmation, but keep the real consent gate out-of-band.** The vault's own OS-level prompt or tray UI should own consent. The calling agent's UI may auto-approve or be compromised.
- **ChatGPT needs a remote HTTPS endpoint (tunnel or relay).** That breaks "local-only" and should be an explicit, off-by-default, advanced option with its own threat-model disclosure.
- **Distribution:** ship an .mcpb for Claude Desktop, an "Add to LM Studio"/Cursor/VS Code deeplink, and a registry entry. Consider Windows ODR registration once it is out of preview, because its containment, logging and admin controls are trust signals.
- **MCP Apps could give the vault a native-looking consent and citation-viewer UI** inside Claude, ChatGPT, VS Code and Cursor. It needs graceful text fallback.

### Gaps
- I found no authoritative, current (2026) feature-support matrix for each client (elicitation/MRTR, resources, resource links, structured output, tasks) across Claude Desktop, Claude Code, Cursor, Windsurf, Zed, Goose and OpenClaw. The modelcontextprotocol.io "clients" page now redirects to an intro page.
- I couldn't confirm whether the Registry reached GA after July 2026, or whether Cursor's 40-tool cap still applies in 2026.
- Clients' adoption of 2026-07-28 (beyond the Tier-1 SDKs and GitHub) is unknown.

---

## 2. OpenClaw and other personal-agent platforms; where a "private context provider" fits; personal memory/context MCP projects

### Takeaway
OpenClaw was named Warelay, then Clawdbot/Moltbot, and is now run by the OpenClaw Foundation. It is the breakout personal agent of 2026: 247k GitHub stars by March 2026 and OpenClaw 2.0 on Aug 30, 2026. It is also a well-known security liability: unvetted skills, plaintext secrets, and no sandbox by default. Every major platform (Microsoft, Google, Apple) is building agent surfaces that consume MCP- or App-Intents-style connectors. That makes a hardened, consent-gated "private context provider" a well-placed complement, particularly for OpenClaw users who need safe access to sensitive documents.

### Cited Findings
**OpenClaw history, scale and security**
- Launched Nov 24, 2025 as "Warelay" by Peter Steinberger. The assistant was named Clawd (later Molty), inspired by Claude.
- Renamed **Moltbot** on Jan 27, 2026 after Anthropic trademark complaints, then **OpenClaw** on Jan 30, 2026.
- On Feb 14, 2026 Steinberger joined OpenAI and the **OpenClaw Foundation** (non-profit) was set up.
- **247,000 stars / 47,700 forks as of Mar 2, 2026.** It is MIT licensed and written in TypeScript and Swift, with a skills system based on `SKILL.md`.
- Source: [Wikipedia: OpenClaw](https://en.wikipedia.org/wiki/OpenClaw)
- It crossed 100k stars in its first week (late Jan 2026). Users reach it through Telegram, Slack, Discord, WhatsApp, iMessage, Teams and others — [search summary of DEV/freeCodeCamp](https://dev.to/kfuras/set-up-openclaw-as-your-personal-ai-agent-in-2026-h5o) [secondary]
- Security record:
  - Jan 28, 2026: Cisco found third-party skills doing **data exfiltration and prompt injection**, and the skill repository lacked vetting.
  - Mar 2026: Chinese authorities restricted its use in state-run enterprises, agencies and banks.
  - **OpenClaw 2.0 (v2026.8.1), Aug 30, 2026:** The Register criticized the "absence of network/file-system security boundaries, unencrypted stored secrets… and non-default sandbox".
  - NanoClaw is positioned as the containerized alternative.
  - A maintainer warned: "if you can't understand how to run a command line, this is far too dangerous of a project for you to use safely."
  - Source: [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)
- Competitive responses: Nadella (Feb 2026) called it a "virus"-like risk, and by May 2026 Microsoft's "Project Lobster" was testing "ClawPilot". Google built "Remy" — [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)
- A Personal AI Agents Summit (July 21, 2026) featured Anthropic, OpenAI, Google, Perplexity and OpenClaw, with talks on agent security and MCP — [ODSC](https://odsc.medium.com/personal-ai-agents-summit-2026-9-sessions-on-security-mcp-claude-code-openclaw-and-gemini-2b1eb57aa617)

**Other platforms**
- **Goose** (Block) is "an open source, local-first AI agent framework" built on MCP and is now an AAIF project — [LF press](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation). It supports MCP Apps — [MCP Apps blog](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- **Microsoft:**
  - Native MCP / ODR (see §1).
  - **Agent Workspace**: "a contained, policy-controlled and auditable environment where agents can interact with software… in a parallel and separate desktop". MCP and computer-use agent interactions run there.
  - Built-in File Explorer connector ("with user consent").
  - Sources: [Windows Dev Blog, Nov 18 2025](https://blogs.windows.com/windowsdeveloper/2025/11/18/ignite-2025-furthering-windows-as-the-premier-platform-for-developers-governed-by-security/); [Microsoft Support: experimental agentic features](https://support.microsoft.com/en-us/windows/ai/ai-features/experimental-agentic-features)
- **Apple:**
  - Sept 2025: macOS 26.1 beta code showed groundwork for **MCP support inside App Intents** — [9to5Mac](https://9to5mac.com/2025/09/22/macos-tahoe-26-1-beta-1-mcp-integration/) [older]
  - WWDC 2026 (June): Siri was rebuilt on a Google Gemini model; **SiriKit was deprecated and App Intents became the only way Siri calls third-party apps**; new entity/intent schemas feed Spotlight's semantic index — [TechTimes](https://www.techtimes.com/articles/318005/20260608/wwdc-2026-app-intents-replaces-sirikit-gemini-siri-migration-clock-starts.htm); [MacRumors](https://www.macrumors.com/2026/06/09/apple-outlines-major-ai-and-developer-tool-updates/)
  - A community `intents-mcp` server exposes Mac App Intents as MCP tools through signed Shortcuts — [mcp.so issue](https://github.com/chatmcp/mcpso/issues/4411)
- **Google:**
  - "Remy" was rebranded as **Gemini Spark**, a 24/7 agent (inbox triage, purchases), around May 13–14, 2026 — [Pillitteri](https://pasqualepillitteri.it/en/news/2624/gemini-spark-google-remy-rebrand-ai-agent-2026) [secondary]
  - The Gemini API's Managed Agents added remote MCP support and background tasks — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/expanding-managed-agents-gemini-api/)

**Personal memory/context MCP projects (comparable products)**
- **OpenMemory MCP (Mem0):** "a private, local-first memory layer with a built-in UI compatible with all MCP clients", pitched as portable memory across AI apps — [Mem0 blog](https://mem0.ai/blog/introducing-openmemory-mcp); [OpenMemory](https://mem0.ai/openmemory)
- **Screenpipe** (YC S26): records the screen locally and serves it as context to agents (Claude, Codex, OpenClaw, Hermes…) via MCP — [GitHub screenpipe](https://github.com/screenpipe/screenpipe)
- **Obsidian:**
  - PulseMCP lists **104** Obsidian MCP servers — [PulseMCP](https://www.pulsemcp.com/servers?q=obsidian)
  - "In July 2026 the Local REST API plugin started serving MCP on its own" — [ContextBolt](https://contextbolt.com/blog/obsidian-mcp-claude/) [secondary]
- Basic Memory and Supermemory appear in comparison posts, but I found no reliable 2026 popularity metrics — [Substratia comparison](https://substratia.io/blog/memory-mcp-vs-alternatives/) [secondary]

### Inferences
- **OpenClaw's weaknesses define the vault's positioning.** Its skills are untrusted, secrets sit in plaintext, and it has no default sandbox. The vault can present itself as the "safe way to give OpenClaw (or any agent) access to your tax, medical and legal docs": answers not files, consent per agent, audit log, local encryption.
- **Most existing "personal context via MCP" tools hand over raw content** (memory stores, screen history, note files). A vault that returns *synthesized, cited, policy-filtered answers* is a real product differentiator. It also sits closer to an "agent" than a "tool" (see §3).
- **Build connectors for all three OS surfaces over time:** Windows ODR, Apple App Intents (for Siri and Spotlight-semantic-index reach), and MCP for everything else.

### Gaps
- Live GitHub star counts for mem0, supermemory, basic-memory, screenpipe, goose and openclaw couldn't be retrieved; the GitHub API was blocked in this session. The one Mem0 figure I saw (7,760 stars) came from a fork page and is **unreliable**.
- I found no primary-source confirmation that Apple **shipped** native MCP in macOS/iOS 26.x or 27. One secondary blog asserts "native support for MCP", but it's unverified.
- OpenClaw's active-user counts and ClawHub skill-marketplace size for 2026 weren't found.

---

## 3. Agent-to-agent protocols (A2A): do they matter for this product?

### Takeaway
A2A reached **v1.0 on April 9, 2026** under the Linux Foundation, with 150+ supporting organizations and integrations across Google, Microsoft and AWS. It is enterprise-oriented. Consumer desktop agents (Claude Desktop, ChatGPT, Cursor, OpenClaw) reach local data through MCP, so A2A is a "watch / later" item rather than a launch requirement.

### Cited Findings
- Google announced A2A on Apr 9, 2025 and donated it to the Linux Foundation on June 23, 2025 — [Wikipedia: Agent2Agent](https://en.wikipedia.org/wiki/Agent2Agent) [search summary]
- On Apr 9, 2026 the Linux Foundation reported 150+ organizations, integration into Google, Microsoft and AWS platforms, and production deployments in supply chain, finance, insurance and IT ops — [Linux Foundation press](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year); [Google Open Source Blog](https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html)
- The v1.0 spec was released Apr 9, 2026. There are 22k+ GitHub stars and SDKs in Python, JS, Java, Go and .NET — [AIwire/HPCwire](https://www.hpcwire.com/aiwire/2026/04/09/linux-foundation-a2a-protocol-marks-one-year-with-broad-enterprise-and-cloud-adoption/); [search summary] [secondary for the numbers]
- Google pairs **A2UI** (declarative agent UI) with MCP Apps — [Google Developers Blog](https://developers.googleblog.com/a2ui-and-mcp-apps/)

### Inferences
- **The product is conceptually closer to an A2A "remote agent" than an MCP "tool".** It is an opaque agent that answers questions over private data without exposing its internals. A thin A2A Agent Card adapter could be cheap later and would help with enterprise/B2B pilots.
- **Exposing MCP is sufficient for the launch.** An A2A endpoint would add network attack surface (it is HTTP-based) for little consumer reach.

### Gaps
- I found no evidence that any consumer desktop agent (Claude Desktop, ChatGPT desktop, Cursor, OpenClaw) acts as an A2A client in 2026.

---

## 4. MCP server UX best practices (install, tool design, citations, consent)

### Takeaway
Keep the tool surface **small and consolidated**, a few intent-level tools such as `ask_vault`, `search_vault` and `get_citation`. Namespace them, write descriptions for "a new hire", return human-readable references plus resource links, paginate and truncate with guidance, and keep one-click install behind an explicit and honest consent screen. Tool-count caps in clients (Cursor 40, Copilot 128) and context cost punish large toolsets.

### Cited Findings
- Anthropic, "Writing effective tools for agents" (Sept 11, 2025) — [Anthropic Engineering](https://www.anthropic.com/engineering/writing-tools-for-agents) [older but still canonical]:
  - Build a few "thoughtful tools targeting specific high-impact workflows" rather than wrapping every endpoint.
  - Namespace with prefixes (e.g. `asana_search`).
  - Return human-readable names instead of UUIDs.
  - Offer a `response_format` enum (`concise`/`detailed`).
  - Paginate, filter and truncate with "helpful instructions". Claude Code caps tool responses at **25,000 tokens** by default.
  - Write actionable errors and use unambiguous parameter names (`user_id`, not `user`).
  - Evaluate with agentic loops.
- "Too many tools or overlapping tools can distract agents." MCP metadata can use 20–40%+ of the context window in tool-heavy setups — [search summary incl. Anthropic advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use); [Substack](https://codeagentsalpha.substack.com/p/tokenefficient-agents-building-mcpheavy) [secondary for the percentage]
- Client tool caps: Cursor 40 total ([Cursor forum](https://forum.cursor.com/t/tools-limited-to-40-total/67976), 2025), Copilot 128 per request ([vscode#248368](https://github.com/microsoft/vscode/issues/248368)) [older]
- Spec primitives useful for citations and output: **resource links** in tool results and **structured tool output** arrived in 2025-06-18 — [timeline](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html). Icons arrived in 2025-11-25 — [same](https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html)
- Official MCP security best practices (2026-07-28 docs) — [modelcontextprotocol.io security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices):
  - Clients offering one-click local install **MUST** show "the exact command that will be executed, without truncation" and require explicit approval.
  - Clients **SHOULD** sandbox servers with minimal default privileges.
  - Local servers **SHOULD** "use the stdio transport to limit access to just the MCP client". If they use HTTP, they should require an authorization token or use unix domain sockets/IPC with restricted access.
  - Servers **MUST NOT** treat possession of a state handle as authentication. Handles should be random and bound to the authenticated user.
  - Scope minimization: start with a minimal scope and elevate step-up via `WWW-Authenticate` challenges.
  - Avoid wildcard or omnibus scopes.
- .mcpb `user_config` keeps secrets in the OS keychain, and bundles can be signed — [mcpb repo](https://github.com/modelcontextprotocol/mcpb)
- The Windows ODR model has per-agent access control in Settings/Intune, containment by default, and logging — [Microsoft Learn](https://learn.microsoft.com/en-us/windows/ai/mcp/overview)

### Inferences
- **Suggested toolset:**
  - `vault_ask(question, scope?, response_format)` returns a synthesized answer plus citation handles.
  - `vault_search(query)` returns titles, snippets and resource links, gated by policy.
  - `vault_open_citation(id)` returns a redacted excerpt and needs consent.
  - Optionally `vault_list_collections`.
  - Stay well under 10 tools.
- **Put the vault's own trust statement in the server `instructions` and descriptions,** e.g. "answers only; raw documents require user approval". Never put dynamic, document-derived text in tool descriptions: that is the poisoning vector.
- **Per-agent identity is weak over stdio,** where the client is basically "whoever launched me". Bind consent to (client name from `_meta` + launch config + a per-install token placed in the client config at install time). Show that identity in the audit log, with the caveat that it is self-asserted.

### Gaps
- I found no published UX study on consent-prompt fatigue specific to MCP. Anthropic's newer "advanced tool use" (tool search, deferred loading) specifics weren't read in full.

---

## 5. Threat model: prompt injection, lethal trifecta, tool poisoning/rug pulls, confused deputy, extraction via synthesized answers, and 2025–2026 incidents/CVEs

### Takeaway
A document vault serving external agents is **one leg (private data) of the lethal trifecta by design**. Its documents can also be **the second leg** (untrusted content: a malicious PDF or email can carry injected instructions). The calling agent usually supplies **the third** (web, email, and other outbound channels). So the vault must assume:
- (a) the caller may be hijacked;
- (b) its own documents may hijack its internal LLM;
- (c) synthesized answers are an exfiltration channel.

Research shows automated agents can pull large parts of a RAG corpus out through many queries (RAG-Thief). Defenses are layered: per-agent scopes and quotas, query-pattern detection, PII redaction, no raw text by default, and human confirmation for sensitive categories. There's no single fix. Willison: "95% is very much a failing grade."

The MCP ecosystem had a very large volume of 2025–2026 incidents, especially STDIO command injection, malicious packages, and unsandboxed desktop extensions.

### Cited Findings
**Frameworks**
- **Lethal trifecta** (Simon Willison, June 16, 2025): "Access to your private data", "Exposure to untrusted content", "The ability to externally communicate". The only reliable fix is to "avoid that lethal trifecta combination entirely". With MCP mix-and-match, "there's nothing those vendors can do to protect you". Guardrails claiming 95% are inadequate. He recommends the "Design Patterns for Securing LLM Agents against Prompt Injections" paper and DeepMind's **CaMeL** — [Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- **OWASP Top 10 for Agentic Applications 2026** (published Dec 9, 2025; ASI01–ASI10) introduces "**Least Agency**" and puts Agent Goal Hijack first — [OWASP GenAI](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/); [Palo Alto](https://www.paloaltonetworks.com/blog/cloud-security/owasp-agentic-ai-security/)
- One secondary source says OWASP's June 2026 report maps prompt injection to six of the ten categories — [Airia](https://airia.com/blog/ai-security-in-2026-prompt-injection-the-lethal-trifecta-and-how-to-defend/) [secondary]

**Tool poisoning, rug pulls, cross-server shadowing**
- Invariant Labs (April 2025) showed malicious instructions hidden in tool descriptions that users can't see but the model reads. A "Fact of the Day" tool exfiltrated a WhatsApp history. **Rug pulls** change a tool's description or behavior after approval. A malicious server can shadow tools from other trusted servers. Invariant's `mcp-scan` checks for these — [Invariant Labs](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks); [CSA note](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-tool-poisoning-ai-agent-exfiltration-2/)
- Academic benchmarks: MCPTox ([arXiv 2508.14925](https://arxiv.org/pdf/2508.14925)), ETDI signed tool definitions against rug pulls ([arXiv 2506.01333](https://arxiv.org/pdf/2506.01333)), and a large-scale ecosystem analysis ([arXiv 2509.06572](https://arxiv.org/pdf/2509.06572))

**Confused deputy (spec-level)**
- MCP proxy servers that use a static third-party client ID plus DCR plus consent cookies can be abused. The fix is **per-client consent** before forwarding, exact redirect-URI matching, and single-use `state`. Token passthrough is forbidden — [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)

**Timeline of incidents and CVEs**
- **May 2025**, GitHub MCP (Invariant Labs): one official server gave private-repo access, exposure to attacker-authored issues, and a publishing channel through PRs — [UpGuard](https://www.upguard.com/blog/ai-github-agents-issue-leaked-private-repos) [older]
- **July 2025**, Supabase MCP + Cursor: a support ticket carried an injection that made the agent dump `integration_tokens` into the ticket thread — [Simon Willison](https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/); Supabase's response — [Supabase blog](https://supabase.com/blog/defense-in-depth-mcp) [older]
- **CVE-2025-6514** (mcp-remote, CVSS 9.6): OS command execution when connecting to an untrusted server. Fixed in 0.1.16 — [JFrog](https://jfrog.com/blog/2025-6514-critical-mcp-remote-rce-vulnerability/); [GHSA](https://github.com/advisories/GHSA-6xpm-ggf7-wc3p) [older]
- **CVE-2025-49596** (MCP Inspector, critical); **CVE-2025-54136** (Cursor "MCPoison") — [The Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/) [secondary, older]
- **Sept 2025, postmark-mcp: the first known malicious MCP server.** It shipped 15 clean releases, then v1.0.16 (Sept 17, 2025) added a line that BCC'd every email to the attacker. It had about 1,500 weekly downloads — [Snyk](https://snyk.io/blog/malicious-mcp-server-on-npm-postmark-mcp-harvests-emails/); [Postmark](https://postmarkapp.com/blog/information-regarding-malicious-postmark-mcp-package) [older]
- **Feb 2026, LayerX: zero-click RCE in Claude Desktop Extensions (DXT).** A malicious Google Calendar event could chain into an unsandboxed local executor extension. LayerX scored it CVSS 10 and said it affected 10k+ users and 50+ extensions. Anthropic reportedly declined, saying it "falls outside our current threat model" — [LayerX](https://layerxsecurity.com/blog/claude-desktop-extensions-rce/); [The Register](https://www.theregister.com/2026/02/11/claude_desktop_extensions_prompt_injection/); [Infosecurity](https://www.infosecurity-magazine.com/news/zeroclick-flaw-claude-dxt/)
- **Jan 28, 2026:** Cisco found OpenClaw skills performing exfiltration and prompt injection — [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)
- **Apr 15, 2026, OX Security, "Mother of All AI Supply Chains":**
  - A systemic STDIO command-injection pattern across official SDKs (Python, TS, Java, Rust) and products (LiteLLM, LangChain, LangFlow, Cursor, Windsurf, VS Code, GPT Researcher, Agent Zero…).
  - OX cites **150M+ downloads, 7,000+ exposed servers, up to 200k vulnerable instances and 10 CVEs**.
  - Anthropic reportedly called the behavior intended and said sanitization is the developer's job.
  - Sources: [OX Security](https://www.ox.security/blog/the-mother-of-all-ai-supply-chains-critical-systemic-vulnerability-at-the-core-of-the-mcp/); [OX advisory](https://www.ox.security/blog/mcp-supply-chain-advisory-rce-vulnerabilities-across-the-ai-ecosystem/)
- **Q1 2026 CVEs:** CVE-2026-30615 (Windsurf, zero-click prompt injection to RCE), CVE-2026-30623 (LiteLLM), CVE-2026-26015 (DocsGPT), CVE-2026-30624 (Agent Zero), CVE-2026-40933 (Flowise), and others — [The Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/) [secondary]
- **July 2026, "DuneSlide":** CVE-2026-50548/50549, Cursor sandbox escape and symlink canonicalization bypass (CVSS 9.8) — [The Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/) [secondary]
- A secondary source reports SDK session-ID confusion bugs (**CVE-2026-67431, CVE-2026-33946**): the SDK accepted a session ID to authorize `tools/call` without checking the presenter — [DEV Community](https://dev.to/piiiico/mcp-security-vulnerabilities-in-2026-40-cves-and-counting-4pco) [secondary, unverified]
- **Counts conflict.** DEV claims "40+ CVEs Jan–Apr 2026" ([DEV](https://dev.to/piiiico/mcp-security-vulnerabilities-in-2026-40-cves-and-counting-4pco)); The Agent Report tallies 14 ([Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/)). The Vulnerable MCP Project keeps a database — [vulnerablemcp.info](https://vulnerablemcp.info/). CSA also published an "MCP Security Crisis" note on May 4, 2026 — [CSA](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-security-crisis-20260504-csa-styled/)
- Endor Labs studied 2,614 implementations: 82% were prone to path traversal, 67% used code-injection-prone APIs, and 34% were susceptible to command injection — [The Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/) [secondary]

**Extraction through synthesized answers (RAG privacy)**
- **RAG-Thief:** an agent-based automated attack that "extracts scalable amounts of private data from private knowledge bases". It uses composite prompts that steer retrieval and instruct the LLM to repeat the retrieved text — [arXiv 2411.14110](https://arxiv.org/html/2411.14110v1)
- Other attacks: fine-grained extraction via knowledge asymmetry ([arXiv 2507.23229](https://arxiv.org/pdf/2507.23229)); implicit knowledge extraction ([OpenReview](https://openreview.net/pdf?id=F5TD0OExsf)); membership inference against retrieval data ([arXiv 2505.22061](https://arxiv.org/html/2505.22061v1))
- **Defenses:**
  - **RAG-CT** (Sept 2026) detects malicious queries from retrieval distribution. Benign queries retrieve several related records, while extraction queries tend to retrieve a single sensitive record. It uses entropy and margin indicators — [arXiv 2609.16095](https://arxiv.org/pdf/2609.16095)
  - Query keyword detection and rewriting — [search summary of ACL Findings 2024](https://aclanthology.org/2024.findings-acl.267.pdf)
  - Synthetic-data retrieval stores — [arXiv 2406.14773 / EMNLP 2025](https://aclanthology.org/2025.emnlp-main.1247.pdf)
  - **Differential privacy:** DPVoteRAG spends privacy budget only on tokens that need sensitive info ([arXiv 2412.04697](https://arxiv.org/abs/2412.04697)); DP-SynRAG ([arXiv 2510.06719](https://arxiv.org/pdf/2510.06719)); local-DP entity perturbation LPRAG ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0306457325000913))
- **PII detection locally:**
  - Microsoft Presidio separates detection from anonymization. It has a built-in `GLiNERRecognizer`, and the Apache-2.0 model `urchade/gliner_multi_pii-v1` handles multilingual PII. Presidio can also use local LLMs/SLMs via Ollama — [Presidio GLiNER sample](https://presidio.dataprivacystack.org/samples/python/gliner/); [PyPI presidio-analyzer](https://pypi.org/project/presidio-analyzer/)
  - The GitHub result now shows the project under a "data-privacy-stack" org — [GitHub](https://github.com/data-privacy-stack/presidio). I didn't verify the org change.
  - Knowledgator's `gliner-pii-base-v1.0` is an alternative — [Hugging Face](https://huggingface.co/knowledgator/gliner-pii-base-v1.0)

**Recommended ops mitigations (ecosystem consensus)**
- Disable auto-install from public registries, containerize or sandbox, prefer read-only, pin versions and re-validate, monitor config files, and scan responses for injection patterns — [The Agent Report](https://the-agent-report.com/2026/07/mcp-security-landscape-2026-vulnerabilities-mitigations/)

### Inferences
Threat model for the vault (for the report writer to structure):
1. **Hostile or hijacked caller** (prompt-injected Claude, Cursor or OpenClaw) runs bulk extraction.
   - Mitigations:
     - per-agent scopes (collections/tags)
     - rate limits and daily token/answer quotas
     - RAG-CT-style detection of "single-record, verbatim" query patterns
     - answer-length and verbatim-overlap caps, e.g. n-gram overlap against source chunks
     - PII/PHI redaction by default (Presidio+GLiNER)
     - "sensitive collection" answers require out-of-band human approval
     - an anomaly dashboard in the audit log
2. **Malicious document** (indirect injection into the vault's own LLM).
   - Mitigations:
     - the vault's synthesis LLM has **no tools and no network** (it removes the exfiltration leg inside the vault)
     - treat document text strictly as data (spotlighting/delimiting)
     - never let document text reach tool descriptions or server instructions
     - flag documents with instruction-like content at ingest
3. **Vault answer as an injection vector into the caller.** The answer is untrusted content for the calling agent too. Strip or neutralize markdown images/links and instruction-like text, and mark provenance in structured output.
4. **Local attack surface:**
   - stdio by default; if HTTP, loopback only plus a random bearer token plus Origin/Host checks against DNS rebinding
   - no shell execution
   - no `npx`-style dynamic fetch at launch
   - signed .mcpb
5. **Supply chain:** pinned dependencies, SBOM, signed releases (see §8). The vault should never itself be a proxy that forwards tokens (confused deputy).

- **Differential privacy is research-grade.** It's worth mentioning as roadmap, not as a launch claim. Quotas, redaction and human approval are the practical launch controls.
- **Honest positioning:** "answers, not documents" reduces bulk-exfiltration risk but **cannot prevent** a determined, authorized agent from learning the facts in your documents. That *is* the product. Consent and audit are the real controls.

### Gaps
- I found no published real-world incident of RAG corpus extraction through a consumer MCP "memory/vault" server. Evidence is academic.
- I didn't verify any NVD entry for CVE-2026-67431/33946, or the exact CVSS for most 2026 CVEs.
- There's no source here for Embrace The Red's 2026 work on markdown/image exfiltration. The search budget ran out.

---

## 6. Encryption at rest for desktop apps (2026)

### Takeaway
The prevailing pattern:
- Encrypt the whole database (SQLCipher or an equivalent AES-256 page cipher) **plus** encrypt blobs and files with an AEAD (XChaCha20-Poly1305 / AES-GCM).
- Use a random Data Encryption Key, wrapped by a Key Encryption Key.
- Derive the KEK from a passphrase with **Argon2id** (OWASP minimum m=19 MiB, t=2, p=1; higher for local vault unlock), and/or store it in the OS keychain. Offer passkey-PRF or biometric unlock where supported.
- Python can't reliably zeroize `bytes`. Use `bytearray`/`memoryview` or push secrets into a Rust/native layer.

### Cited Findings
- **OWASP Argon2id** equivalent parameter sets: m=47104 (46 MiB), t=1, p=1; **m=19456 (19 MiB), t=2, p=1 (minimum)**; m=12288, t=3; m=9216, t=4; m=7168, t=5. scrypt fallback N=2^17, r=8, p=1. PBKDF2-HMAC-SHA256 at 600,000 iterations if FIPS is needed — [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- SQLCipher gives full-database AES-256 encryption, including metadata, indexes and journals — [OneUptime, Feb 2026](https://oneuptime.com/blog/post/2026-02-02-sqlcipher-encryption/view) [secondary]
- For Electron, `better-sqlite3-multiple-ciphers` is recommended as the default encrypted SQLite — [codenote](https://codenote.net/en/posts/electron-encrypted-sqlite-libraries-comparison/) [secondary]
- A common local-first pattern is Rust+Tauri 2 + XChaCha20-Poly1305 + Argon2id + SQLCipher + OS keychain. "The key must never sit next to the data." Keychain plus an Argon2id master password is advised for high-assurance apps — [search summary of GitHub issues/blogs](https://github.com/topics/argon2id?l=rust) [secondary]
- **Passkey PRF (WebAuthn PRF extension)** derives a deterministic 32-byte secret per credential, usable as key material:
  - Aug 2026 community testing: **Apple Passwords and Google Password Manager at 100% success**; third-party managers ranged from 0% to 100% — [Corbado](https://www.corbado.com/blog/passkeys-prf-webauthn)
  - Apple shipped PRF in iOS/macOS 18 (2024–25), with limits for roaming authenticators — [Corbado](https://www.corbado.com/blog/passkeys-prf-webauthn)
  - Bitwarden and Dashlane ship PRF-based vault unlock — [Bitwarden blog](https://bitwarden.com/blog/prf-webauthn-and-its-role-in-passkeys/); [Bitwarden contrib docs](https://contributing.bitwarden.com/architecture/deep-dives/passkeys/implementations/relying-party/prf/); [Yubico PRF guide](https://developers.yubico.com/WebAuthn/Concepts/PRF_Extension/Developers_Guide_to_PRF.html)
- **1Password two-secret key derivation (2SKD):** the account password plus a 34-character **Secret Key** derive separate encryption and authentication keys, so server data can't be brute-forced. An **Emergency Kit** PDF holds the Secret Key for recovery — [1Password white paper](https://1passwordstatic.com/files/security/1password-white-paper.pdf); [APSK chapter](https://agilebits.github.io/security-design/apsk.html); [Emergency Kit](https://support.1password.com/emergency-kit/)
- **Python zeroization:** "there is no way to clear immutable structures such as bytes". APIs accept buffer-protocol types, so you can pass a `memoryview`/`bytearray` and overwrite it after use — [pyca/cryptography limitations](https://cryptography.io/en/latest/limitations/). The `zeroize-python` package (Rust-backed) zeroes `bytearray`/numpy buffers — [GitHub](https://github.com/radumarias/zeroize-python)
- Windows ODR connectors and .mcpb `user_config` both lean on OS-managed secure storage (keychain for sensitive config) — [mcpb](https://github.com/modelcontextprotocol/mcpb)

### Inferences
- **Recommended vault design:**
  - Random 256-bit DEK per vault, with optional per-collection sub-keys so sensitive collections can be revoked or locked separately.
  - Wrap the DEK with several KEKs: (1) an Argon2id passphrase KEK at desktop-grade parameters, above the OWASP web minimum, e.g. ≥256 MiB and t≥3, tuned to about 0.5–1 s; (2) an OS keychain/Secure Enclave/TPM-protected KEK for convenience unlock; (3) an optional passkey-PRF KEK; (4) a printable recovery key, the "Emergency Kit" model.
- **Encrypt the vector index and embeddings,** not only the documents. Embeddings can be inverted to approximate text. Either store the index inside SQLCipher (sqlite-vec) or encrypt the index files with the DEK. Decrypt into memory only while unlocked.
- **Audit logs should be encrypted and append-only** (hash-chained) so tampering is detectable.
- **Say the limits plainly:** secure deletion on SSDs is unreliable, so rely on crypto-erase (destroy keys). Python memory hygiene is best-effort, and unlocking exposes plaintext to anything running as the same user.

### Gaps
- I didn't verify 2026 primary docs for: macOS Keychain + Secure Enclave access-control flags (biometry-bound keys), Windows DPAPI-NG / TPM-bound keys / Windows Hello `KeyCredentialManager`, Linux Secret Service/libsecret and TPM2 unlock, or SSD secure-deletion guidance (NIST SP 800-88). These are standard, but no source was retrieved in this pass.
- I found no published attack benchmark specific to "embedding inversion of local vector DBs" in this pass. The claim above is background knowledge and should be verified.

---

## 7. E2EE multi-device sync and local-first architecture

### Takeaway
CRDT libraries are mature: Automerge 3 (May 2025, about 10x less memory), Yjs (dominant for editors), and Loro 1.0 (movable trees). Server-authoritative sync engines (Zero 1.0 in June 2026, Electric, PowerSync) are **not** E2EE by design. The E2EE-friendly options are CRDT or op-log sync over a blind relay (the Anytype any-sync model, Standard Notes, Obsidian Sync with E2EE mode), Jazz, or plain P2P (Syncthing-style). Audits of Obsidian Sync show the real trade-offs that remain: deterministic encryption and visible metadata.

### Cited Findings
- **Automerge 3.0** (May 2025) has a Rust core and cut memory by about 10x. **Yjs** remains dominant for real-time editors. **Loro** hit 1.0 in 2024, with rich-text and movable-tree CRDTs (Rust, JS/WASM, Swift) — [PkgPulse](https://www.pkgpulse.com/guides/yjs-vs-automerge-vs-loro-crdt-libraries-2026) [secondary]; [Kanaries on Loro](https://docs.kanaries.net/topics/OpenSource/loro) [secondary]
- **Zero 1.0** (Rocicorp, stable in June 2026) has a server-authoritative cache architecture. Rocicorp points teams wanting "fully decentralised, end-to-end setups toward Jazz" — [InfoQ](https://www.infoq.com/news/2026/06/zero-version-1/); [Zero docs: when to use](https://zero.rocicorp.dev/docs/when-to-use)
- ElectricSQL is Postgres sync. **PowerSync** supports Postgres, MongoDB, MySQL and SQL Server through declarative "Sync Streams" into client SQLite — [BuildPilot](https://trybuildpilot.com/648-electric-sql-vs-powersync-vs-zero-2026) [secondary]
- **Anytype / any-sync:** data lives on-device in an encrypted local DB with **per-object keys**. It syncs P2P and through backup nodes over the open-source any-sync protocol, and you can self-host — [search summaries](https://beginnersinai.org/anytype-private-workspace/); [Dexi comparison](https://www.dexi.net/compare/obsidian-vs-anytype) [secondary]
- **Standard Notes:** E2EE by default with AES-256-GCM, and XChaCha20-Poly1305 in newer clients. The server is a blind relay — [stateofsurveillance.org](https://stateofsurveillance.org/guides/basic/encrypted-note-apps-compared/) [secondary]
- **Obsidian Sync:** E2EE with AES-256 and scrypt-derived keys, but it has to be chosen when the remote vault is created. Paths, timestamps and version history are visible to the server — [Obsidian Help: Sync security](https://obsidian.md/help/sync/security); [search summary](https://thebusinessdive.com/obsidian-vs-anytype)
- Audits (Cure53, Oct 2024; Trail of Bits, Dec 2025; published around May 2026) kept two intentional trade-offs: **deterministic encryption** (identical content gives an identical ciphertext hash, which enables dedupe but leaks equality) and **path metadata visibility**. "Managed encryption" was renamed "standard encryption" for clarity — [dsebastien summary](https://www.dsebastien.net/2026-05-14-obsidian-sync-passes-cure53-and-trail-of-bits-audits/); [Obsidian blog](https://obsidian.md/blog/cure53-tob-sync-audits/)
- **Key recovery:** the 1Password Secret Key plus Emergency Kit model (see §6) — [1Password](https://support.1password.com/emergency-kit/)

### Inferences
- **Keep sync out of the public launch or make it optional,** because it widens the threat model. If built:
  - encrypt on the client with per-object keys and an AEAD (randomized, not deterministic)
  - pad or obscure sizes and paths
  - use an untrusted blob relay or Syncthing-style P2P as the self-host option
  - store Loro/Automerge updates as encrypted op-logs, not a server-authoritative engine
  - enroll new devices through QR/PAKE key transfer
  - give users a printable recovery kit
- **Sync only source documents and user metadata, not derived indexes.** Each device re-embeds locally. That avoids syncing an invertible embedding store and version-skew bugs.

### Gaps
- I didn't retrieve primary docs for Proton Drive's E2EE sync, Syncthing's 2026 status, Jazz's E2EE design, or Ditto. Secondary sources only for Standard Notes and Anytype crypto details.

---

## 8. Trust signals for privacy-conscious users and security reviewers

### Takeaway
The signals that reviewers can actually check:
- signed releases with Sigstore/cosign and SLSA provenance, which OpenSSF Scorecard checks
- published full third-party audit reports; Obsidian's run of Cure53 and Trail of Bits reports is the benchmark for this category
- signed .mcpb bundles
- reproducible or verifiable builds
- SBOMs
- telemetry off by default
- verifiable egress, i.e. an offline mode the user can check
- SECURITY.md with a disclosure process

### Cited Findings
- **OpenSSF Scorecard "Signed-Releases"** looks for `.sig/.sigstore/.asc/.minisig/.intoto.jsonl` assets in the last 5 releases. Plain checksums don't count — [Scorecard issue example](https://github.com/jeedo/oneshot/issues/71) [secondary]
- SLSA was contributed to OpenSSF in 2021. **SLSA v1.1 is stable, with v1.2 in development.** Hermetic and reproducible builds are recommended, not required — [Practical DevSecOps](https://www.practical-devsecops.com/slsa-framework-guide-software-supply-chain-security/) [secondary]
- Sigstore signs release files, container images, binaries and SBOMs — [OpenSSF Sigstore](https://openssf.org/projects/sigstore/)
- 2026 research on build verifiability: attested builds (Kettle, [arXiv 2605.08363](https://arxiv.org/pdf/2605.08363)); "Reproducibility is Not Enough" ([arXiv 2608.18180](https://arxiv.org/pdf/2608.18180))
- **Obsidian's audit record:**
  - Cure53 client pentest and code audit, fixes in 1.5.3 (Dec 26, 2023) — [Obsidian blog](https://obsidian.md/blog/cure53-security-audit/)
  - Cure53 second client audit, Dec 2024 — [AlternativeTo](https://alternativeto.net/news/2024/12/obsidian-undergoes-a-second-independent-security-assessment/)
  - Cure53 Sync audit, Oct 2024 (4 low, 1 medium) and Trail of Bits Sync audit, Dec 2025 (11 findings). Full reports were published with remediations validated by the auditors — [dsebastien](https://www.dsebastien.net/2026-05-14-obsidian-sync-passes-cure53-and-trail-of-bits-audits/); [Obsidian on Threads](https://www.threads.com/@obsdmd/post/DYSfkv-DzO2/two-new-security-audits-of-obsidian-sync-by-cure-and-trail-of-bits-are-now)
- .mcpb supports `mcpb sign`/`verify` — [mcpb](https://github.com/modelcontextprotocol/mcpb)
- **Negative signals security reviewers will cite:** OpenClaw stores secrets unencrypted and has no default sandbox ([Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)); DXT extensions run unsandboxed with full host privileges ([LayerX](https://layerxsecurity.com/blog/claude-desktop-extensions-rce/)); vendors call vulnerabilities "by design" ([OX](https://www.ox.security/blog/the-mother-of-all-ai-supply-chains-critical-systemic-vulnerability-at-the-core-of-the-mcp/))

### Inferences
- **Launch checklist for the report:**
  1. SECURITY.md plus `/.well-known/security.txt` plus a private advisory channel (GitHub Security Advisories).
  2. Signed releases via Sigstore/cosign with SLSA v1 provenance from GitHub Actions, plus OS code signing and notarization.
  3. SBOM (CycloneDX/SPDX) attached to each release.
  4. OpenSSF Scorecard badge and pinned CI actions.
  5. A published threat model document and data-flow diagram.
  6. Telemetry off by default, with any opt-in payload shown verbatim.
  7. A "network egress" panel and a hard offline mode. Users should be able to verify it with Little Snitch/OpenSnitch, and the app should list every domain it can contact (model downloads, update checks).
  8. Signed .mcpb and published tool manifests with hashes, which lets users detect rug pulls.
  9. Budget for a Cure53, Trail of Bits or similar audit after the public beta, and publish the full report, following Obsidian's precedent.
  10. A tamper-evident local audit log of every agent query, answer and citation access.
- **Publish a "what the vault will never do" statement,** e.g. "never returns raw files without your click; synthesis model has no network access". Reviewers can test it.

### Gaps
- I didn't verify current OSTIF funding programs, bug-bounty platforms suitable for small OSS projects, or reproducible-build feasibility for Tauri/Electron or PyInstaller-style bundles (not retrieved).

---

## 9. Regulatory and compliance angle (health/finance docs) and 2026 data-portability sources

### Takeaway
A purely local, open-source app processing a user's own documents is mostly outside HIPAA, and likely **minimal-risk under the EU AI Act**. The EU AI Act's high-risk deadlines slipped to Dec 2027 / Aug 2028; Article 50 transparency still applies from Aug 2, 2026. The **FTC Health Breach Notification Rule** (amended July 2024) can apply to consumer health apps that pull data from multiple sources. That matters most if a company runs sync or cloud features.

On ingestion: the US CMS Aligned Networks (FHIR patient access by July 2026) is the most promising new health-records source. US open banking (CFPB 1033) is stalled. EU EHDS patient-access obligations phase in from 2029.

### Cited Findings
- **FTC Health Breach Notification Rule:**
  - It covers **vendors of personal health records**, meaning records that "draw information from multiple sources and that is managed, shared, and controlled by or primarily for the individual", including health apps. It also covers PHR-related entities and third-party service providers.
  - HIPAA covered entities are excluded.
  - A "breach" includes **unauthorized disclosure by the company itself**, not only hacking.
  - Amendments took effect **July 2024**.
  - Source: [FTC business guidance](https://www.ftc.gov/business-guidance/resources/complying-ftcs-health-breach-notification-rule-0)
- **EU AI Act Digital Omnibus:**
  - Parliament approved it June 16, 2026; the Council adopted it June 29, 2026; it was signed July 8 and **entered into force July 27, 2026**.
  - Annex III high-risk obligations moved to **Dec 2, 2027**, and Annex I to **Aug 2, 2028**.
  - **Article 50 transparency obligations still apply from Aug 2, 2026.**
  - Sources: [Council press release](https://www.consilium.europa.eu/en/press/press-releases/2026/06/29/artificial-intelligence-council-gives-final-green-light-to-simplify-and-streamline-rules/); [Gibson Dunn](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/); [Jones Walker](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/yes-august-2-still-matters-the-eu-approved-a-high-risk-ai-delay-but-most-trans.html?id=102nbon)
- **CMS Interoperability Framework / Aligned Networks (US):**
  - At a July 30, 2025 White House event, 21 networks pledged to become CMS Aligned Networks, and 60+ companies pledged patient-facing tools by Q1 2026.
  - By **July 4, 2026** networks had to provide FHIR API access plus a patient-initiated record locator service.
  - Patients get clinical, claims and prior-auth data "via an app of the patient's choice that meets CMS requirements".
  - Sources: [Wilson Sonsini](https://www.wsgr.com/en/insights/cms-announces-creation-of-health-tech-ecosystem-for-improving-access-to-patient-data.html); [KFF](https://www.kff.org/patient-consumer-protections/charting-the-way-forward-new-efforts-to-advance-electronic-health-information-sharing/); [Fierce Healthcare](https://www.fiercehealthcare.com/health-tech/cms-advances-interoperability-initiative-showcases-provider-directory-meeting-industry)
- **CFPB Section 1033 (open banking):**
  - The Oct 2024 final rule is **enjoined** and being rewritten. The ANPRM was Aug 22, 2025, and the **April 1, 2026 compliance date passed without effect**.
  - A new proposal was sent to OIRA in **Aug 2026**. States are moving on data-sharing.
  - Sources: [Consumer Finance Monitor, Aug 6 2026](https://www.consumerfinancemonitor.com/2026/08/06/cfpb-sends-new-section-1033-open-banking-proposal-to-oira-for-review/); [Cozen O'Connor](https://www.cozen.com/news-resources/publications/2026/section-1033-compliance-date-open-banking-rule-enjoined-and-under-reconsideration); [Consumer Finance Monitor, June 2026](https://www.consumerfinancemonitor.com/2026/06/26/open-banking-regulation-in-2026-federal-regulation-resurfaces-as-states-bring-data-sharing-into-focus/)
- **European Health Data Space (EHDS):**
  - In force March 2025.
  - Patient summaries and ePrescriptions must be exchangeable EU-wide via MyHealth@EU by **March 2029**; images, labs and discharge reports follow from **March 2031**.
  - The Commission's implementing acts are due by March 2027.
  - Sources: [Wikipedia: EHDS](https://en.wikipedia.org/wiki/European_Health_Data_Space); [EC FAQ](https://health.ec.europa.eu/document/download/4dd47ec2-71dd-49fc-b036-ad7c14f6ed68_en?filename=ehealth_ehds_qa_en.pdf); [DSV Europa, Sept 2026](https://dsv-europa.de/en/news/2026/09/ehds.html)

### Inferences
- **HIPAA:** the FTC rule's exclusion shows HIPAA's scope is covered entities (providers, plans, clearinghouses) and their business associates. A user storing their own records in a local app isn't a covered entity, and an OSS publisher without access to the data isn't a business associate. The app can say "HIPAA-aligned safeguards" but shouldn't claim to be "HIPAA compliant" as a certification.
- **FTC HBNR exposure** grows if the project or a company offers hosted sync, cloud backup or analytics touching health data. Default local-only with no telemetry keeps that exposure minimal. Document this.
- **GDPR:** local-only processing on the user's device, with no vendor access, keeps the vendor out of the controller/processor role for vault contents. Data minimization still applies to any telemetry, crash reports or sync service. (Background reasoning; see Gaps.)
- **EU AI Act:** a personal document Q&A assistant is not an Annex III use case. Article 50 transparency (disclosing AI interaction and AI-generated content) is the likely relevant obligation. It's cheap to comply by labeling synthesized answers as AI-generated with citations.
- **Ingestion roadmap:** FHIR patient-access import (CMS Aligned Networks apps; SMART on FHIR), Apple Health Records export, bank statements via OFX/CSV/PDF now, and FDX/1033 APIs later, if the new rule settles.

### Gaps
- The HHS HIPAA covered-entity page returned 403, so HIPAA scope rests on the FTC page plus background knowledge.
- I didn't retrieve GDPR household-exemption or controller analysis for local-only software, Apple Health Records export/FHIR details for iOS 26/27, or FDX adoption numbers in 2026.
- I couldn't confirm how many CMS Aligned Networks actually went live by the July 4, 2026 deadline.
