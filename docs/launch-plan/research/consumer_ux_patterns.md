# Consumer UX Patterns, Magic Moments and App-Platform Choices for a Local, Private AI Document Vault (state as of late Sept 2026)

Research notes for the Enclave public-launch roadmap. Scope: what makes consumer AI and knowledge apps feel great and keep users in 2026, and which desktop/mobile stacks make that level of polish achievable. Dates are marked; anything from before 2026 is tagged **[older: YYYY]**. Sources marked **(secondary)** are SEO, review or aggregator sites. Treat their numbers as indicative only.

---

## Q1. Onboarding: what do best-in-class AI apps do in the first 60 seconds?

### Takeaway
The best 2026 AI apps get to a first useful result before asking the user to configure anything. They pick hardware-appropriate defaults (engine, model size, quantization), show "will this fit on my machine?" before any download, ask for one integration or permission at the moment it is needed with a plain-language reason, and teach features in context rather than through an upfront tour. For a local vault, the magic moment is: install → point at a folder (or open a sample vault) → first cited answer from the user's own documents, in minutes.

### Cited Findings
- **Jan v0.8.0 (May 22, 2026)**: the Hub shows a colored fit badge ("Fits", "May be slow", "Won't fit") based on the user's hardware *before* any download. Quantizations are grouped as Small / Balanced / Large with "Recommended" tags. Failed downloads clear themselves from the queue. A new backend dependency checker and a Factory Reset that can keep selected data were added. — [Jan changelog v0.8.0](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- Jan v0.8.0 also added live prompt-processing progress percentages, loading indicators and a confirmation dialog when closing during active work. — [Jan changelog v0.8.0](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- **LM Studio 0.4.x**: on first launch it asks the user to pick a hardware backend with a sensible default (Metal on Apple Silicon, CUDA on NVIDIA, Vulkan or ROCm on AMD). It detects GPU and RAM and shows them in the UI. The Discover tab searches Hugging Face and filters by size, quantization and hardware compatibility. The download page picks the right build for the visitor's platform. — [tech-insider LM Studio setup 2026 (secondary)](https://tech-insider.org/how-to-set-up-lm-studio-local-ai-models-2026/)
- **Msty Studio**: reviewers call its onboarding a "killer feature": someone who has never run a local model can install Msty, click a model and be chatting in under five minutes, because Msty ships its own engine (a bundled, renamed Ollama plus managed llama.cpp and MLX). — [The AI Tool Bible Msty review (secondary)](https://theaitoolbible.com/tools/msty); [ModelPiper local-AI comparison (secondary)](https://modelpiper.com/blog/local-ai-platforms-compared-mac)
- **Ollama desktop app [older: July 30, 2025]**: moved from CLI-only to a GUI on macOS and Windows with model download, chat, file drag-and-drop (PDF, md, txt, code) and a context-length setting. Ollama framed it as "an easier way to chat with models." — [Ollama blog: new app](https://ollama.com/blog/new-app)
- **Granola**:
  - Onboarding needs only a single calendar integration, a deliberate choice to cut clicks. The copy handles the main objection up front: "No creepy bots joining your meeting," because Granola captures system audio. — [UX Planet on Granola (secondary)](https://uxplanet.org/the-art-of-invisible-ai-what-granolas-70-retention-teaches-us-about-product-design-2de5a2836d17?gi=30990bbf688a)
  - The same piece reports roughly 70% weekly retention. This is a claim, not audited. — [UX Planet on Granola (secondary)](https://uxplanet.org/the-art-of-invisible-ai-what-granolas-70-retention-teaches-us-about-product-design-2de5a2836d17?gi=30990bbf688a)
  - Onboarding is contextual: help appears inline when the user first does something (e.g., creates a private folder) instead of an upfront tutorial. The Google sync opens a small side widget instead of a full modal, so the main window stays visible and the step feels less worrying. — [Built for Mars: Granola](https://builtformars.com/company/granola)
- **Dia (The Browser Company)**: first run imports bookmarks and history from an installed browser, then opens the default profile with the AI sidebar already open. It includes a short "Skills" walkthrough and an explicit Memory opt-in. Reviewers call it "smooth, polished, and unusually thoughtful" compared with Arc. — [SupaSidebar Dia review 2026 (secondary)](https://supasidebar.com/blog/dia-browser-mac-review-2026); [kvibber Dia review](https://kvibber.com/reviews/software/dia-browser/)
- **Superhuman [older pattern, still cited]**: onboarding is scripted so the "magic moment" (a shortcut, automation or filter that visibly saves time) lands within about 60 seconds. Historically this included 1:1 30-minute coaching sessions, a deliberate "positive friction" trade of slower acquisition for higher retention. — [Flowjam Superhuman teardown (secondary)](https://www.flowjam.com/blog/superhuman-onboarding-teardown-30-minute-wow-session); [Superhuman blog](https://blog.superhuman.com/the-fastest-way-to-inbox-zero-a-single-coaching-session/)
- **Claude Desktop Quick Entry** asks for macOS permissions per capability, each tied to a feature the user can see: Accessibility (Quick Entry), Screen Recording (screenshots and window sharing), Speech Recognition (dictation). — [Claude Help Center: Quick Entry](https://support.claude.com/en/articles/12626668-use-quick-entry-with-claude-desktop-on-mac)
- **ChatGPT Computer History (Aug 13, 2026)** is off by default and opt-in per user. In Business and Enterprise an admin must enable it first, then each member opts in individually. — [Unite.AI](https://www.unite.ai/openais-computer-history-turns-mac-activity-into-chatgpt-memory/); [TechRepublic](https://www.techrepublic.com/article/ews-openai-computer-history-chatgpt-mac-activity/)
- **Microsoft Recall [older: Sept 2024 redesign]**: after the privacy backlash, the Copilot+ PC setup asks explicitly whether to turn Recall on. It is off unless the user opts in. — [Windows Experience Blog](https://blogs.windows.com/windowsexperience/2024/09/27/update-on-recall-security-and-privacy-architecture/)
- **NN/g, State of UX 2026**: "Lazy AI features and AI slop are now ubiquitous, and the shine is fading fast." People burned by bad AI experiences hesitate to try new features. Trust needs "transparency, control, consistency, and support when the system fails." — [NN/g State of UX 2026](https://www.nngroup.com/articles/state-of-ux-2026/)

### Inferences
- **Recommended first-60-seconds flow for Enclave:**
  1. Welcome screen with one promise ("Your documents never leave this computer") and a visible offline/local badge.
  2. Automatic hardware check with a plain-language result ("This Mac can run the Balanced model, 4.1 GB") and a Jan-style fit badge.
  3. The model downloads in the background with a progress bar and ETA. Meanwhile the user either (a) opens a pre-indexed **sample vault** (e.g., a fictional family's passport, lease, insurance, tax PDFs) and asks a suggested question right away, or (b) points at a folder, which gets a live "indexed N of M" counter.
  4. The first answer arrives with clickable citations.

  The sample vault removes the "empty state + 3 GB download" dead zone that most local-LLM apps have.
- Ask for OS permissions (Full Disk Access, Accessibility for a hotkey, Notifications for reminders) only when the feature that needs them is first used, with a one-line reason. This is the Claude Quick Entry / Granola pattern.
- Put a "why this is safe" line right next to each sensitive step, like Granola's "no creepy bots" framing.
- Given NN/g's AI-fatigue finding, the onboarding pitch should lead with outcomes ("find any warranty in 2 seconds", "never miss a passport renewal"), not with "AI".

### Gaps
- No primary first-run teardowns found for Claude Desktop, ChatGPT desktop, Raycast AI or NotebookLM onboarding in 2026. Coverage is from help docs and secondary reviews.
- No public activation or retention benchmarks for local-LLM desktop apps (Jan, LM Studio, Msty). Granola's 70% figure comes from a secondary article.

---

## Q2. Core interaction patterns for document AI

### Takeaway
The 2026 standard is source-grounded chat. Every claim carries a citation that opens the exact passage in a side-by-side viewer. Around that sit one-click "studio" outputs from the same sources (audio, video, mind map, study guide, flashcards, data table, slides), generative UI (charts, tables, interactive widgets rendered inside the answer), and ways to invoke the AI from anywhere: global hotkey, OS context menu, Spotlight actions, drag-and-drop. NotebookLM remains the reference design for the whole bundle and has moved into agentic, code-executing research.

### Cited Findings

**NotebookLM / Gemini Notebook (reference design)**
- **Timeline**:
  - Audio Overviews **[older: Sept 2024]**; interactive "Join" mode for Audio Overviews **[older: Dec 2024]**.
  - Video Overviews (narrated slide-style videos) **[older: 2025]**; cinematic video mode **[older: July 29, 2025]**.
  - Infographics and Slide Decks **[older: Nov 2025]**; Data Table output **[older: Dec 2025]**.
  - Rebranded to **Gemini Notebook on July 16, 2026**, with a secure cloud computer per notebook that runs code. Short 60-second vertical Video Overviews in **July 2026**.

  — [Wikipedia: NotebookLM](https://en.wikipedia.org/wiki/NotebookLM)
- **June 8, 2026 upgrade** (updated July 16, 2026): NotebookLM runs on Gemini 3.5 plus "Antigravity" with a "secure cloud computer" that writes and runs code, backed by "more than 100 curated software skills."
  - It can "guide you through building your source repository directly in your chat" using Google Search (source discovery).
  - It exports PDF, docx, markdown, xlsx, pptx and charts.
  - Google reports a "78.2% win rate" in web research against prior versions.

  — [Google blog: Do your best research with NotebookLM](https://blog.google/innovation-and-ai/products/notebooklm/better-research-notebooklm/)
- Visible reasoning steps shown in chat, and flashcards generated only from the user's sources, were part of the 2026 update. — [Geeky Gadgets NotebookLM 2.0 guide (secondary)](https://www.geeky-gadgets.com/notebooklm-2026-new-features/); [Jeff Su (secondary)](https://www.jeffsu.org/notebooklm-changed-completely-heres-what-matters-in-2026/)
- In August 2026 Google began folding notebooks into AI Mode in Search. — [search-result summary of NotebookLM coverage; not verified against a primary Google post](https://notebooklm-guide.com/notebooklm-updates/)
- **Citation UX**: every chat answer has clickable citations. Clicking one opens the Source Viewer and scrolls to the exact passage. Clicking a mind-map node opens a scoped chat whose citations point only to sources about that branch. — [notebooklm-guide Mind Maps (secondary)](https://notebooklm-guide.com/notebooklm-mind-maps/); [XDA on NotebookLM mind maps](https://www.xda-developers.com/notebooklm-mind-maps-uses-in-new-hobby-gamechanging/)
- Deep Research in NotebookLM **[older: Nov 2025]** marked the shift from a retrieval tool to an agent that goes out and finds new sources. Audio and Video Overviews expanded to 80+ languages. — [Medium analysis (secondary)](https://medium.com/@jimmisound/the-cognitive-engine-a-comprehensive-analysis-of-notebooklms-evolution-2023-2026-90b7a7c2df36); [Google blog on Audio/Video Overviews languages](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebook-lm-audio-video-overviews-more-languages-longer-content/)

**Local-first competitors**
- **Jan v0.8.0**: RAG results appear as **numbered citation cards with source previews**. — [Jan changelog v0.8.0](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- **Msty "Knowledge Stacks"**: named, reusable document collections attached to conversations (RAG). All data is stored locally and there is zero telemetry. — [Msty docs: Knowledge Stacks](https://docs.msty.studio/features/knowledge-stacks/overview); [Miraheze Msty Studio (secondary)](https://ai.miraheze.org/wiki/Msty_Studio)
- **DEVONthink 4 (macOS document manager)**:
  - AI chat as a popover or inspector over selected documents, with one-click "save conversation to database as note."
  - Works with ChatGPT, Claude or Mistral, or locally through Ollama, LM Studio or GPT4All.

  — [MacStories DEVONthink 4 review](https://www.macstories.net/reviews/ai-adds-a-new-dimension-to-devonthink-4/); [DEVONtechnologies: local AI](https://www.devontechnologies.com/blog/20251111-local-ai-devonthink)

**Generative UI inside answers**
- **MCP Apps** (first official MCP extension, live **Jan 26, 2026**; SEP-1865, co-authored by Anthropic, OpenAI and MCP-UI): tools return interactive UI (dashboards, forms, charts, multi-step flows) that renders inline. Claude, ChatGPT, Goose and VS Code support it. — [MCP blog: MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/); [The Register](https://www.theregister.com/special-features/2026/01/26/claude-supports-mcp-apps-presents-ui-within-chat-window/4645652)
- **Gemini generative UI**:
  - "Dynamic view" codes a single-purpose interactive UI for each prompt; "visual layout" produces a magazine-style answer.
  - Generative UI also ships in Google Search AI Mode.
  - Dynamic view is not available in the Gemini mobile app.

  — [Google Research: Generative UI](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/); [Gemini Help](https://support.google.com/gemini/answer/16741341)
- **ChatGPT Pulse [older: Sept 2025]**: proactive research delivered as "topical visual cards you can scan quickly or open for more detail." This is the answer-card pattern applied to digests. — [OpenAI: Introducing ChatGPT Pulse](https://openai.com/index/introducing-chatgpt-pulse/)

**Invoke-from-anywhere patterns**
- **Claude Desktop Quick Entry**: double-tap Option from any app. Type, drag to capture part of the screen, click a window to attach it, or dictate with Caps Lock. Needs macOS 12+ (dictation 14+). The app can stay in the background. — [Claude Help Center: Quick Entry](https://support.claude.com/en/articles/12626668-use-quick-entry-with-claude-desktop-on-mac)
- **Windows 11 File Explorer "AI actions" [older: rolled out Oct 2025]**: right-click (or Shift+F10) a file → AI actions → edit an image or summarize a document. Copilot Summarize needs Microsoft 365 plus a Copilot license and works on OneDrive/SharePoint files. — [Windows Experience Blog Oct 16, 2025](https://blogs.windows.com/windowsexperience/2025/10/16/new-experiences-currently-rolling-out-for-windows-11/); [Windows Central](https://www.windowscentral.com/microsoft/windows-11/how-to-manage-ai-actions-in-file-explorer-on-windows-11)
- **macOS Tahoe (26) Spotlight actions**: third-party apps that adopt the **App Intents** API show up as Spotlight actions with parameters. "Quick keys" (short strings such as "sm" for Send Message) trigger them. Items in the current app's menu bar are also searchable. — [MacStories Tahoe overview](https://www.macstories.net/news/macos-tahoe-the-macstories-overview/); [AppleInsider quick keys](https://appleinsider.com/inside/macos-tahoe/tips/how-to-use-quick-keys-in-macos-tahoe-spotlight)
- **Raycast v2 (Sept 2026)**:
  - Restored bring-your-own-model: Ollama local models, OpenAI-compatible providers, OpenRouter. With local models there is "no internet required, no AI credits used, and nothing leaves your machine."
  - Supports local stdio MCP servers.
  - Windows now matches Mac core features. BYOK and local models require Pro.

  — [AlternativeTo: Raycast v2](https://alternativeto.net/news/2026/9/raycast-v2-restores-external-ai-models-and-expands-window-tools/); [Raycast Manual: Local Models](https://manual.raycast.com/ai/local-models); [Raycast Windows changelog](https://www.raycast.com/changelog/windows)
- **Ollama app**: drag-and-drop a file into chat. — [Ollama blog](https://ollama.com/blog/new-app)

**Memory, timelines and ambient capture**
- **ChatGPT Computer History (macOS, Aug 13, 2026)**:
  - Turns accessibility-exposed activity (clicks, typing, app switches) into text summaries, **local memory files** and a searchable **timeline** used by ChatGPT and Codex.
  - No screenshots, microphone or system audio; private browsing is excluded. Does not need Screen Recording permission.
  - Pro, Business and Enterprise only.

  — [Unite.AI](https://www.unite.ai/openais-computer-history-turns-mac-activity-into-chatgpt-memory/); [Elephas explainer (secondary)](https://elephas.app/resources/chatgpt-desktop-computer-history-privacy)
- **ChatGPT macOS app** added Projects on Mac and "Record mode" (captures meeting audio → transcript → editable notes). — [OpenAI macOS release notes](https://help.openai.com/en/articles/9703738-chatgpt-macos-app-release-notes); [Coursiv on Record mode (secondary)](https://coursiv.io/blog/chatgpt-record-mode)
- **Granola** shows user-typed notes and AI-generated notes in different colors, so provenance is always visible. — [UX Planet on Granola (secondary)](https://uxplanet.org/the-art-of-invisible-ai-what-granolas-70-retention-teaches-us-about-product-design-2de5a2836d17?gi=30990bbf688a)

### Inferences
- **Magic moments a private vault can own** (drawn from the patterns above):
  1. Ask "when does my passport expire?" and get the date plus a citation chip; clicking it opens the scanned passport page with the MRZ line highlighted.
  2. Drop a 40-page lease on the window and get a one-card summary (rent, term, notice period, penalties), each field cited.
  3. "Make a table of all my insurance policies" renders a sortable table with renewal dates. This is generative UI, a vault-scoped version of MCP Apps / Gemini dynamic view.
  4. A household "life timeline" auto-built from document dates (bought car, lease signed, child's vaccination record).
  5. A NotebookLM-style private audio briefing ("your finances this month"), generated locally.
- **Must-have document-AI primitives for Enclave:**
  - numbered inline citations that deep-link to page and highlight;
  - a split view (chat | document);
  - AI vs user content visually distinguished (Granola);
  - saved "stacks" or collections (Msty);
  - save-answer-as-note (DEVONthink);
  - one-click structured outputs (table, timeline, checklist) before audio/video, because those are cheap to generate locally.
- **Invoke-from-anywhere priority for desktop:**
  1. Global hotkey quick-ask panel (Claude/Raycast pattern).
  2. Drag-and-drop anywhere.
  3. Watch folders.
  4. OS integration: Finder/Explorer "Ask Enclave about this file" and Spotlight App Intents on macOS. This tier needs native code (see Q9).
- Computer History and Recall show where ambient capture is heading, but also how sensitive it is (see Q5). A document vault should keep capture explicit (watch folders, share sheet, scan) rather than passive screen or activity recording.

### Gaps
- No primary 2026 source found on the release dates of NotebookLM Mind Maps or "Discover sources". They are well documented in secondary guides but were not checked against Google posts.
- Nothing found on auto-tagging/smart collections UX benchmarks, or on consumer "life timeline" products built from documents. Google Photos and Apple Photos are analogues but were not researched.
- Perplexity answer-card UX in 2026 and Claude Projects/Artifacts changes in 2026 were not covered from primary sources.
- The "Gemini Notebook" rename comes from Wikipedia. The Google blog post (updated July 16, 2026) still says "NotebookLM". Treat naming as unsettled.

---

## Q3. Proactive and ambient patterns: digests, reminders from documents, anomaly detection

### Takeaway
Proactive AI moved into mainstream products in 2025–26 (ChatGPT Pulse daily cards; a crop of consumer "expiry tracker" apps that pull dates from IDs, warranties and policies). Research is consistent: proactivity helps when it is moderate, explainable and easy to control, and feels creepy when the system's use of personal context is unclear. A local vault has a structural advantage here, because it can truthfully say "we found this in *your* document, on *your* device."

### Cited Findings
- **ChatGPT Pulse [older: Sept 2025 preview, Pro on mobile]**:
  - Researches overnight using past chats, Memory, feedback and connected apps such as calendar, then delivers a morning set of visual cards.
  - Users valued it most once they *steered* it. OpenAI added thumbs up/down and preference controls as a result.

  — [OpenAI: Introducing ChatGPT Pulse](https://openai.com/index/introducing-chatgpt-pulse/); [Forbes Dec 2025](https://www.forbes.com/sites/moinroberts-islam/2025/12/19/chatgpt-pulse-and-the-race-to-curate-your-day-with-ai/)
- **Document-expiry apps (2026)**:
  - **Expiro**: OCR pulls expiration dates from driver's licenses, passports, visas, insurance and more, and reminds at 30/7/1 days before. — [Expiro](https://mwm.ai/apps/expiro-app/6758278098)
  - **Orlo**: UK households; connect Gmail or upload documents; reminders for insurance, MOT, tax returns, contracts, passports. — [Orlo](https://www.getorlo.app/)
  - **Remindax**: extracts expiry date, document type, reference numbers, VIN or serial and creates a reminder in one click. — [Remindax](https://www.remindax.com/expiration-reminder)
  - **ExpireAI**: photo of receipt, warranty or ID → auto-reminder. — [ExpireAI on Google Play](https://play.google.com/store/apps/details?id=com.expireai.app&hl=en_IN)
- **CHI 2026 extended abstract** "Proactive, But Not Creepy": proactive generative assistants reduce effort, but "proactive initiation can raise privacy concerns and uncertainty about system use of personal context," which makes acceptance hard to predict. — [ACM DL, CHI EA 2026](https://dl.acm.org/doi/10.1145/3772363.3798894)
- In a consumer-behaviour study, privacy concerns, uncertainty avoidance and technology anxiety increase perceived creepiness and distrust of digital assistants, which leads users to disengage. — [Maduku et al., Journal of Consumer Behaviour 2025](https://onlinelibrary.wiley.com/doi/10.1002/cb.2462)
- Proactive assistants at *moderate* levels were rated more helpful, natural and appropriate than very high or very low proactivity (in-vehicle LLM assistant study). — [arXiv 2403.09135](https://arxiv.org/pdf/2403.09135)
- **Microsoft Recall** is the cautionary tale: it had to become opt-in, gated by Windows Hello, with app/website filters, pause, delete and a sensitive-info filter on by default. — [Microsoft Support: Recall privacy](https://support.microsoft.com/en-us/windows/privacy/privacy-and-control-over-your-recall-experience); [Computerworld [older: 2024]](https://www.computerworld.com/article/2140187/microsoft-makes-windows-recall-opt-in-after-privacy-security-backlash.html)

### Inferences
- **Recommended Enclave proactive design:**
  - An opt-in weekly "Vault Digest" card stack: upcoming expiries, renewals, tax deadlines, prescription refills, "3 new documents filed".
  - Every card carries (a) the source document chip, (b) "why am I seeing this", and (c) snooze / not relevant / never for this type. That covers the CHI transparency-and-control factors and Pulse's steering lesson.
  - Default to the moderate tier: date-based reminders on by default *after* the user confirms an extracted date. Anomaly detection (unusual bank charges, duplicate subscriptions) off by default, offered as an "Insights" upgrade.
  - Present reminders as extracted facts the user confirms ("We found an expiry date: 12 Mar 2027 — add reminder?"), not silent inferences. This turns a possibly creepy moment into a helpful one and fixes extraction errors at the same time.
- The standalone expiry apps show that users will pay for exactly this job. Enclave can bundle it for free because the documents are already in the vault.

### Gaps
- No quantitative data on consumer reactions to bank-statement anomaly detection in personal (non-bank) apps.
- No public retention or engagement data for Pulse or the expiry-tracker apps.

---

## Q4. Voice and multimodal UX

### Takeaway
Hold-to-talk on a hardware key is the default voice pattern on desktop (Wispr Flow; Claude's Caps Lock dictation). Screenshot or window capture from a global hotkey is now standard in AI desktop apps. On mobile, the OS document scanner (VisionKit on iOS) is the fastest route to scan-to-vault, with some iOS 26 UI rough edges.

### Cited Findings
- **Wispr Flow**:
  - Hold-to-talk works in any text field on Mac, Windows, iOS and Android. Default is hold **Fn** on Mac.
  - If onboarding finds no Apple Fn key, it switches to Ctrl+Opt (push-to-talk), Ctrl+Opt+Space (hands-free) and Cmd+Ctrl+Opt (command mode).
  - Each action allows up to 4 bindings.

  — [Wispr Flow Help: shortcuts](https://docs.wisprflow.ai/articles/2612050838-supported-unsupported-keyboard-hotkey-shortcuts); [Wispr Flow Help: hands-free](https://docs.wisprflow.ai/articles/6391241694-use-flow-hands-free)
- A June 2026 Linux-port bug shows how this fails: a push-to-talk key mapped to a Mac-only key left dictation "completely untriggerable, with no error and no visible binding." — [GitHub issue, wispr-flow-linux](https://github.com/wispr-flow-linux/wispr-flow-linux/issues/33)
- **Claude Desktop Quick Entry**: drag to capture part of the screen, click a window to attach it, or dictate with Caps Lock. Each capability is gated by a matching macOS permission. — [Claude Help Center](https://support.claude.com/en/articles/12626668-use-quick-entry-with-claude-desktop-on-mac)
- **NotebookLM interactive Audio Overviews [older: Dec 2024]**: the user taps "Join" to interrupt the AI hosts and ask questions by voice. — [Wikipedia: NotebookLM](https://en.wikipedia.org/wiki/NotebookLM)
- **ChatGPT Record mode (macOS)**: records meetings or voice notes → transcript → editable notes. — [OpenAI macOS release notes](https://help.openai.com/en/articles/9703738-chatgpt-macos-app-release-notes)
- **iOS VisionKit `VNDocumentCameraViewController`**: native document camera with edge detection that returns scanned pages to the app with no extra dependencies. It allows very little customization and has iOS/iPadOS 26 UI glitches (missing cancel button on iPad; hard-to-read top bar on iOS). — [Apple VisionKit docs](https://developer.apple.com/documentation/visionkit); [Scanbot: WeScan vs VisionKit](https://scanbot.io/blog/ios-document-scanners-wescan-vs-visionkit/)
- **Jan v0.8.0** added audio file attachments (WAV/MP3) with preview chips. — [Jan changelog](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)

### Inferences
- Enclave desktop:
  - a hold-to-talk key inside the quick-ask panel, using local speech-to-text so voice stays offline;
  - a "capture screenshot to vault" hotkey;
  - visible fallbacks when a key binding is invalid (the Wispr Linux failure).
- Enclave mobile: scan-to-vault should call the OS scanner (VisionKit on iOS; ML Kit / CameraX doc scanner on Android, not researched here), then run OCR, extract dates and suggest a reminder right away. That capture → reminder moment is the mobile magic moment.
- A local "Audio Overview" of a document set is feasible with local TTS and a strong differentiator, but it is second priority behind cited Q&A and reminders.

### Gaps
- Android document-scanner APIs (ML Kit Document Scanner) and 2026 voice-mode UX in ChatGPT/Claude/Gemini were not researched from primary sources.
- No data found on how much users tolerate latency for local speech-to-text.

---

## Q5. Trust and privacy UX: showing "nothing leaves your device"; consent for agents and MCP

### Takeaway
The strongest privacy UX in 2026 makes privacy *inspectable*, not just claimed:
- Apple lets users export a JSON log of every off-device AI request.
- Jan labels providers Local vs Remote.
- Apple's own WWDC26 guidance tells developers that users "deserve to know" whether a model is on-device or cloud.

For agent/MCP consent, research shows blanket prompts fail: 81% of users click "Always Allow" just to dismiss them. The better pattern is inline approval cards that show exact arguments and offer *scoped* reusable grants.

### Cited Findings
- **Apple Intelligence & PCC Report**:
  - Location: System Settings → Privacy & Security → Apple Intelligence Report.
  - Duration: last 15 minutes (default) or last 7 days.
  - Export: "Export Activity" writes `Apple_Intelligence_Report.json`.
  - Content: requests sent to Private Cloud Compute (including from watchOS) and to Apple Intelligence Extensions.

  — [Apple Support: Apple Intelligence and privacy on Mac](https://support.apple.com/guide/mac-help/apple-intelligence-and-privacy-mchlfc0d4779/mac); [Daring Fireball [older: Mar 2025]](https://daringfireball.net/linked/2025/03/15/how-to-generate-a-report-of-apple-intelligence-requests-sent-to-private-cloud-compute)
- **WWDC26 session 339**: Foundation Models now accepts any provider behind one Swift API (`SystemLanguageModel`, `PrivateCloudComputeLanguageModel`, `CoreAILanguageModel`, `MLXLanguageModel`). Apple states: "On-device and cloud-based models have very different privacy characteristics, and your users deserve to know which they're getting." — [Apple Developer: WWDC26 session 339](https://developer.apple.com/videos/play/wwdc2026/339/)
- **Jan v0.8.0**:
  - Providers split into **Local** (llama.cpp, MLX) and **Remote** (cloud), so users can see what runs on-device.
  - Settings moved from browser localStorage to local files.
  - **Inline MCP approval**: tool calls appear as cards in the chat showing "the exact arguments", with accept/deny, replacing blocking modal dialogs.

  — [Jan changelog v0.8.0](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- **ConLeash (arXiv, May 2026)**:
  - In the user study, "only 3 of 16 read prompts carefully, and 13 of 16 (81%) use 'Always Allow' simply to dismiss prompts."
  - Proposed alternative: offer *boundary-scoped* options along four dimensions (input scope: exact file → folder → filesystem; output sink: internal → external; data sensitivity; effects: read/write/delete/execute). Each decision becomes a reusable scoped rule.
  - Results: scoped Always-Allow adoption 46.3% vs 13.3%; 98.3% of benign calls auto-permitted; 99.4% of escalations caught; 15/16 participants preferred it.

  — [arXiv 2605.11360](https://arxiv.org/html/2605.11360v1)
- The MCP ecosystem is moving toward just-in-time "progressive consent" through **URL elicitation (SEP-1036)**. — [Nextcloud MCP server ADR-006](https://glama.ai/mcp/servers/@cbcoutinho/nextcloud-mcp-server/blob/4712235390bdd57a53bc7d6336a217765478c464/docs/ADR-006-progressive-consent-elicitation.md)
- **Proton Lumo 2.0 (June 30, 2026)**: markets "zero-access encryption", a no-logs policy, asymmetric encryption of prompts so only Lumo GPU servers can decrypt them, open source, Tor access and guest use without an account. — [Proton: Lumo 2.0](https://proton.me/blog/lumo-2); [Proton: Lumo security model](https://proton.me/blog/lumo-security-model)
- **Brave Leo**: no IP logging, no conversation storage, no account needed; chat history only in local storage. Bring-your-own-model connects to local Ollama or OpenAI-compatible servers. Brave warns that BYOM privacy "will vary" by provider. — [Brave Leo](https://brave.com/leo/); [Brave: BYOM](https://brave.com/blog/byom-nightly/)
- **Msty**: "zero telemetry"; BYOK calls go directly to providers, not through Msty servers. — [Miraheze Msty Studio (secondary)](https://ai.miraheze.org/wiki/Msty_Studio)
- **Raycast local models**: "no internet required, no AI credits used, and nothing leaves your machine." — [Raycast Manual: Local Models](https://manual.raycast.com/ai/local-models)
- **Microsoft Recall trust mechanics**:
  - Windows Hello re-auth every time Recall is opened or its settings change.
  - Just-in-time decryption under Enhanced Sign-in Security.
  - Per-app and per-website exclusions, pause, delete-all, sensitive-info filter on by default.

  — [Windows Experience Blog [older: 2024]](https://blogs.windows.com/windowsexperience/2024/09/27/update-on-recall-security-and-privacy-architecture/); [Microsoft Support](https://support.microsoft.com/en-us/windows/privacy/privacy-and-control-over-your-recall-experience)
- **ChatGPT Computer History** reassures by listing what is *not* captured (screenshots, microphone, system audio, private browsing) and by not needing Screen Recording permission. — [Unite.AI](https://www.unite.ai/openais-computer-history-turns-mac-activity-into-chatgpt-memory/)
- **Granola** answers the main privacy fear in its onboarding copy ("no creepy bots"). — [UX Planet (secondary)](https://uxplanet.org/the-art-of-invisible-ai-what-granolas-70-retention-teaches-us-about-product-design-2de5a2836d17?gi=30990bbf688a)

### Inferences
- **Recommended Enclave trust surfaces:**
  1. A persistent **"Local only" status pill** in the title bar. Clicking it shows the network state and a live connection log. Ideally the product has zero outbound connections by default, apart from an update check the user can see and turn off.
  2. A **"What the AI saw" drawer** on every answer, listing the exact chunks and pages retrieved. This doubles as the citation UI.
  3. An **exportable activity log** (JSON/CSV) of AI actions, tool calls and any network events, modeled on the Apple Intelligence Report.
  4. **Local vs Remote** labeling on any optional cloud model (Jan; Apple's WWDC26 guidance).
  5. **Biometric or OS re-auth** for vault unlock and sensitive categories (IDs, medical), modeled on Recall/Windows Hello and Touch ID.
- **MCP/agent consent for Enclave**: inline tool cards with exact arguments (Jan), plus ConLeash-style scoped grants: "Allow reading *this folder* for *this session* / always", separated by read vs write vs export. Never offer a bare tool-level "Always Allow". Default-deny any tool that sends data off-device, and mark it in red.
- Proton, Brave and Msty all advertise "no logs / zero telemetry". For a local vault this is table stakes. Differentiation comes from *proof*: network log, open-source components, reproducible builds.

### Gaps
- No primary research found on Little Snitch-style in-app network monitors in consumer AI apps, or on how Signal and 1Password communicate encryption state in 2026. Those would be design references rather than documented AI patterns.
- No quantitative study found on whether "local-only" badges measurably raise trust or conversion.

---

## Q6. Speed perception: streaming, skeletons, optimistic UI, indexing progress, latency budgets for local models

### Takeaway
Users judge speed by what happens *during* the wait. Streaming, visible progress and stage labels make local models feel fast even when total time is longer. Rough budgets: UI response under 100 ms; first visible token (or a meaningful progress stage) within about 1 s; generation at roughly 10–20+ tokens/s so output keeps up with reading. Local apps now expose prompt-processing progress because long-document prefill is the main source of perceived slowness.

### Cited Findings
- Nielsen's classic limits: 0.1 s feels instantaneous, 1 s keeps flow of thought, 10 s is the attention limit. **[older: 1993/2014, still the canonical reference]** — [NN/g: Response Times — The 3 Important Limits](https://www.nngroup.com/articles/response-times-3-important-limits/)
- A 2026 practitioner analysis says people rate wait time by what happens during the wait: a 10-second blank wait "feels like 20 seconds," while one with visible progress "feels like 5." Its title claim: "a 3-second stream feels faster than a 1-second batch." — [TianPan.co, Apr 2026 (secondary; opinion)](https://tianpan.co/blog/2026/04/20/latency-perception-gap-ai-interfaces)
- Rules of thumb for local-model throughput: 20+ tok/s "feels instant", 10–20 comfortable, 5–10 usable but slow, under 5 frustrating. — [InventiveHQ local LLM performance (secondary)](https://inventivehq.com/blog/local-llm-performance-what-to-expect)
- Academic serving papers treat human reading speed as the throughput floor. One reports most readers aged 25–44 read about 4–5 tokens/s. Figures came from search-result excerpts of device-server streaming papers and were **not verified by direct reading**. — [DiSCo, arXiv 2502.11417](https://arxiv.org/pdf/2502.11417); [Speed and Conversational LLMs, arXiv 2502.16721](https://arxiv.org/pdf/2502.16721)
- **Jan v0.8.0** added live prompt-processing % progress, loading indicators, per-thread activity indicators in the sidebar, upload progress bars, and llama.cpp "router mode" (one process with on-demand load/unload) for faster model switching. — [Jan changelog v0.8.0](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- **Voice** has tighter budgets. Practitioner guidance targets about 300 ms and says above about 600 ms feels like the system is "processing" rather than "understanding." — [AssemblyAI: the 300ms rule (secondary/vendor)](https://www.assemblyai.com/blog/low-latency-voice-ai)
- **DEVONthink's rule of thumb** for local model sizing: use roughly 50–70% of total RAM (GB) as the maximum model parameter count (B). — [DEVONtechnologies: choosing a local AI](https://www.devontechnologies.com/blog/20251111-local-ai-devonthink)

### Inferences
- **Enclave latency budget:**
  - Keystroke → search-as-you-type results in under 100 ms from a local full-text/vector index (search results appear before the LLM answer does).
  - Ask → a retrieval-stage indicator ("Found 6 passages in 3 documents") within about 300 ms.
  - First generated token in under 1.5 s on the recommended model tier.
  - Generation at 15 tok/s or more on baseline hardware.
- Show *stages* (Searching → Reading 3 documents → Writing) with the source chips appearing *before* the answer streams. Users see grounding immediately, and it hides prefill time.
- Background indexing: a persistent, low-key progress indicator ("Indexing 1,240 / 3,000 · you can ask questions now") plus the ability to query partial results. Blocking the UI until indexing finishes is the most common local-RAG anti-pattern.
- Optimistic UI for filing, tagging and reminder creation: apply instantly, reconcile in the background, and offer undo instead of confirmation dialogs.

### Gaps
- No peer-reviewed 2025–26 study found that sets acceptable time-to-first-token specifically for *local* models or long-document RAG.
- No published indexing-throughput benchmarks for consumer local-RAG apps (Jan, Msty, AnythingLLM) to set a competitive bar.

---

## Q7. Design language trends 2026: Liquid Glass, Fluent/Mica, native feel, keyboard-first, accessibility

### Takeaway
Apple's Liquid Glass (macOS/iOS 26) is now permanent: Xcode 27 removes the opt-out in 2027. It is easy to adopt from SwiftUI/AppKit, impossible to match exactly from Flutter-rendered UIs, and partly reachable from Electron through a new native glass API. Keyboard-first entry points (global hotkey panels, Spotlight quick keys, Cmd-K palettes) are now expected in pro-consumer AI apps. The practical bar for "native feel" is correct system menus, windowing, shortcuts, materials and accessibility, not pixel-perfect glass.

### Cited Findings
- Apple introduced Liquid Glass in June 2025 as the biggest redesign since iOS 7, with updated SwiftUI, UIKit and AppKit APIs for adoption. — [Apple Newsroom, June 2025](https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/)
- **Permanence (March 2026)**: "Xcode 27 will absolutely not have the deferral flag, and it will not respect it if you leave it there." Once Xcode 27 is required for App Store builds (expected Q1 2027), "glass will be enabled globally." Commenters pointed to Flutter and Avalonia as ways to avoid it, and noted that Electron/web apps cannot match it. — [Michael Tsai: Liquid Glass Is Permanent](https://mjtsai.com/blog/2026/03/23/liquid-glass-is-permanent/)
- **Adoption is mixed**: native Mac apps are adopting it, cross-platform Electron apps "can't follow," and some developers report zero customer requests for Liquid Glass. — [OpenMark: macOS Tahoe apps](https://openmarkapp.com/blog/macos-tahoe-apps-liquid-glass); [MacSales blog](https://eshop.macsales.com/blog/97650-blurry-or-beautiful-the-tweaks-and-tenets-of-apples-controversial-liquid-glass-design-in-macos-tahoe/)
- **Electron** has a PR adding native Liquid Glass on macOS 26+: `win.setGlassEffect()` puts an `NSGlassEffectView` behind web contents (style, cornerRadius, tint) and `setGlassEffectRegions()` adds overlays. Merge/release status was not verified. — [electron/electron PR #50415](https://github.com/electron/electron/pull/50415)
- **Flutter desktop (July 2026)**:
  - `PlatformMenuBar` renders a real native macOS menu bar but *replaces* the default system menus, with no way to access them (open issue).
  - The multi-window API is still experimental and `@internal` as of Flutter 3.44.8 (2026-07-23). Production apps use the `desktop_multi_window` package.

  — [flutter/flutter issue #162566](https://github.com/flutter/flutter/issues/162566); [Start Debugging, Aug 2026](https://startdebugging.net/2026/08/how-to-enable-multi-window-support-in-a-flutter-desktop-app/)
- **Flet's `MenuBar`** is drawn by Flet, not the native macOS top menu bar. A discussion requesting native menus exists. Status in Flet 1.0 was not confirmed. — [Flet docs: MenuBar](https://flet.dev/docs/controls/menubar/); [flet-dev discussion #3016](https://github.com/flet-dev/flet/discussions/3016)
- **Keyboard-first entry points in 2026**: Claude's double-tap-Option Quick Entry; Raycast AI (Mac and now Windows); macOS Tahoe Spotlight quick keys running App Intents actions. — [Claude Help Center](https://support.claude.com/en/articles/12626668-use-quick-entry-with-claude-desktop-on-mac); [Raycast Windows changelog](https://www.raycast.com/changelog/windows); [AppleInsider quick keys](https://appleinsider.com/inside/macos-tahoe/tips/how-to-use-quick-keys-in-macos-tahoe-spotlight)
- **Global shortcuts on macOS** may trigger an Accessibility permission prompt. Users on MDM-managed machines may be unable to grant it. — [dev.to: Global shortcuts in Tauri v2](https://dev.to/hiyoyok/global-keyboard-shortcuts-in-tauri-v2-the-right-way-and-the-wrong-way-2h6d)

### Inferences
- For a Python+Flet app, Liquid Glass fidelity and native menus/windows are the most visible "developer tool" giveaways on macOS. Options, in increasing cost:
  1. Accept Flutter-rendered UI but copy macOS spacing, typography and sidebar conventions.
  2. Add a thin native shell (Swift menu bar extra plus Finder/Share extensions) around the Flet UI.
  3. Move the UI to Tauri or native (see Q9).
- Keyboard-first checklist: a global hotkey quick-ask panel; Cmd/Ctrl-K command palette; every action reachable by keyboard; App Intents on macOS so "Ask Enclave" and "Add to Enclave" appear in Spotlight.

### Gaps
- Windows 11 Fluent 2 / Mica / WinUI 3 guidance for 2026 was not researched from Microsoft docs, and neither was Windows' equivalent of Spotlight actions.
- Accessibility (screen readers with Flutter/Flet vs web vs native; WCAG 2.2) was not researched. This is a known risk area for canvas-rendered UIs and needs a dedicated check.
- The claim that "users don't care about Liquid Glass" is anecdotal (a developer comment).

---

## Q8. Multi-device and family: E2EE sync, mobile companions, shared vaults, emergency access

### Takeaway
The accepted patterns come from password managers and note apps:
- end-to-end encrypted sync with a user-held key (Obsidian Sync);
- shared vaults with named members (1Password Family, Obsidian shared vaults);
- account recovery by a family organizer (1Password Family Recovery);
- emergency access with a waiting period (Bitwarden);
- a printable Emergency Kit (1Password);
- OS-level legacy contacts (Apple).

A family document vault should combine these. No mainstream *AI* document app yet offers E2EE family vaults with emergency access, which leaves a gap Enclave can fill.

### Cited Findings
- **Obsidian Sync**:
  - E2EE (AES-256) by default; the user keeps the encryption password; "no one — not even the Obsidian team — can access your notes."
  - Shared vaults: up to 20 collaborators; each needs a Sync subscription; collaborators must enter the E2EE password; no real-time co-editing.

  — [Obsidian Help: Sync security](https://obsidian.md/help/sync/security); [Obsidian Help: shared vault](https://obsidian.md/help/sync/collaborate)
- **Bitwarden Emergency Access** (Premium): designate trusted contacts who can *request* access to the vault. They need a Bitwarden account and must accept the invite, which the owner confirms. No limit on the number of contacts. — [Bitwarden Help: Emergency Access](https://bitwarden.com/help/emergency-access/)
- **1Password** has no emergency-access feature. It offers:
  - a printable **Emergency Kit** (account details, Secret Key, space for the password);
  - **Family Recovery**, where the organizer can recover a family member's account;
  - a default shared family vault plus scoped vaults.

  — [DocSats: password managers after death (secondary)](https://www.docsats.com/blog/password-manager-after-death/); [Funeral.com guide (secondary)](https://funeral.com/blogs/the-journal/using-a-password-manager-for-family-access-emergency-contacts-vault-sharing-and-safer-workflows)
- **Apple Legacy Contact**: Settings → name → Sign-In & Security → Legacy Contact. The contact receives an access key. — [Funeral.com guide (secondary)](https://funeral.com/blogs/the-journal/using-a-password-manager-for-family-access-emergency-contacts-vault-sharing-and-safer-workflows)
- **Proton Lumo** added Projects and long-term memory under zero-access encryption (the cross-device encrypted history pattern). — [Proton: Lumo 2.0](https://proton.me/blog/lumo-2)
- **Tauri 2** and **Flet 1.0** both target iOS and Android from the desktop codebase, which makes a mobile companion (scan-to-vault, reminders, read-only Q&A) reachable. — [Tauri 2.0 stable](https://v2.tauri.app/blog/tauri-20/); [Flet 1.0](https://flet.dev/blog/flet-1-0/)

### Inferences
- **Recommended Enclave family model:**
  - Personal vault plus an optional "Household" shared vault with per-folder sharing.
  - E2EE sync using a user-held key and a printable **Emergency Kit** (QR code plus recovery phrase) at setup.
  - **Emergency access** with a configurable waiting period and owner veto (Bitwarden model).
  - A "Household organizer can recover" option (1Password Family model).
- Mobile companion MVP: scan-to-vault, reminders/notifications, search and read-only chat. Two options: run a small on-device model, or query the desktop over an E2EE LAN/relay link. Either way, keep "nothing on our servers" true.
- Sync can be done without running servers by using the user's own cloud folder (iCloud Drive / Dropbox / OneDrive) holding encrypted blobs. This fits a local-first privacy promise.

### Gaps
- No consumer AI document app found that ships E2EE family sharing plus emergency access. This absence was not proven exhaustively.
- Did not verify 1Password's current (Sept 2026) feature set directly on 1password.com; relied on secondary summaries.
- Proton Drive/Pass family sharing and emergency access were not researched.

---

## Q9. App-platform choice for a polished cross-platform desktop AI app (2026)

### Takeaway
Among successful local-AI apps:
- **Jan** moved to **Tauri** (Next.js UI plus Rust core, inference as a sidecar) for bundle size, memory, security and a mobile path.
- **LM Studio** and **Cherry Studio** remain on **Electron**.
- **Msty** bundles its own engine.
- **Flet 1.0** (Sept 15, 2026) is now a credible *Python-native* option that bundles CPython on all six targets. It still renders Flutter widgets rather than native controls, and lacks first-class tray, native menu and OS-extension support.

For Enclave, the realistic choices are:
- **(A)** keep Flet 1.0 and add small native shims;
- **(B)** move the UI to Tauri 2 with the Python backend as a signed sidecar;
- **(C)** native SwiftUI on macOS plus a web/Tauri UI elsewhere.

Deep OS integrations (Finder/Explorer extensions, Quick Look, Share extensions, Spotlight App Intents) require native code whichever you choose.

### Cited Findings
**What the local-AI apps use**
- **Jan**:
  - Issue opened Jan 20, 2025; architecture decision Mar 31, 2025. Reasons: "Electron app size has become really big"; Tauri gives "MBs vs. Electron's hundreds of MBs", "lower memory & CPU usage", security features by default; and "Electron embeds Chromium and Node.js, which are not suitable for scaling to mobile platforms."
  - Structure: app logic in the Next.js frontend, native functions in Tauri's Rust backend, inference engine "shipped as a sidecar binary."

  — [janhq/jan issue #4485](https://github.com/janhq/jan/issues/4485)
- **Jan today**: Tauri wrapper plus in-app llama.cpp (the old Cortex layer was retired). An experimental MLX engine for Apple Silicon arrived Feb 2026. An OpenAI-compatible server runs on port 1337. — [aimadetools Jan guide (secondary)](https://www.aimadetools.com/blog/jan-ai-complete-guide/); [Jan v0.8.0](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- **LM Studio**: Electron app, proprietary, free for personal and work use. The app uses under 400 MB RAM at idle; the loaded model dominates memory. — [PromptQuorum LM Studio review (secondary)](https://www.promptquorum.com/power-local-llm/lm-studio-review); [Kunavo comparison (secondary)](https://kunavo.com/guides/msty-vs-lm-studio-vs-anythingllm)
- **Cherry Studio**: TypeScript/Electron client with no inference engine of its own (connects to local servers over HTTP). — [Codersera Cherry Studio guide (secondary)](https://codersera.com/blog/cherry-studio-complete-guide-2026/); [CherryHQ/cherry-studio](https://github.com/CherryHQ/cherry-studio)
- **Msty**: bundles a renamed Ollama plus managed llama.cpp and MLX services. — [ModelPiper comparison (secondary)](https://modelpiper.com/blog/local-ai-platforms-compared-mac)
- **Ollama**: native GUI app for macOS/Windows since July 2025. — [Ollama blog](https://ollama.com/blog/new-app)
- **Raycast**: Mac and Windows with a shared core feature set in 2026. — [Raycast Windows changelog](https://www.raycast.com/changelog/windows)

**Tauri 2**
- Stable since Oct 2024. Desktop plus iOS/Android from one codebase. Mobile is "less mature" than desktop and not all plugins are ported. Around 2.11.5 in July 2026. — [Tauri 2.0 stable](https://v2.tauri.app/blog/tauri-20/); [Rustify Tauri v2 tutorial 2026 (secondary)](https://rustify.rs/articles/rust-tauri-v2-desktop-app-tutorial-2026)
- Uses the system webview (WebView2 on Windows, WKWebView on macOS, WebKitGTK on Linux) instead of bundling Chromium. — [Wikipedia: Tauri](https://en.wikipedia.org/wiki/Tauri_(software_framework))
- Secondary benchmarks cite installers of about 8 MB (Tauri) vs about 165 MB (Electron), idle RAM about 45 MB vs about 180 MB, cold start about 1.4 s vs 3.2 s. Treat as indicative. — [tech-insider (secondary)](https://tech-insider.org/tauri-vs-electron-2026/); [Rustify (secondary)](https://rustify.rs/articles/rust-tauri-vs-electron-2026); [levminer real-world comparison](https://www.levminer.com/blog/tauri-vs-electron)
- **Sidecars**: `bundle.externalBin` in `tauri.conf.json` embeds external binaries, commonly a Python API server built with PyInstaller. — [Tauri docs: Embedding External Binaries](https://v2.tauri.app/develop/sidecar/); [example Tauri v2 + Python sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar)
- **Signing pitfall on macOS**: a PyInstaller `--onefile` sidecar embeds an ad-hoc-signed Python.framework with no Team ID. Under the hardened runtime, library validation then refuses to load it after Tauri re-signs the app. Sidecar signing is a known gap. — [ResumeCompiler PR #63](https://github.com/raphaellith/ResumeCompiler/pull/63)
- A reference repo shows a production-grade Python sidecar in Tauri v2: supervised restart with backoff, authenticated local transport, SQLite migrations and WAL crash recovery, Nuitka packaging, signing and auto-update. — [matshoppenbrouwers/tauri-python-sidecar](https://github.com/matshoppenbrouwers/tauri-python-sidecar)
- **Plugins**: `tauri-plugin-global-shortcut`, `tauri-plugin-updater` (signed updater artifacts plus `latest.json`), tray support. A Quick Look extension can be added to a Tauri Mac app by placing a native extension in `Contents/PlugIns/`. — [Tauri: Global Shortcut](https://v2.tauri.app/plugin/global-shortcut/); [Tauri: migrate from v1](https://v2.tauri.app/start/migrate/from-tauri-1/); [markquill PR #6: Quick Look in a Tauri app](https://github.com/sarat03/markquill/pull/6)

**Electron**
- Bundles Chromium plus Node, giving consistent rendering. It is the best choice when the team is all JS/TS and depends on Node-native packages. Now gaining native Liquid Glass via `setGlassEffect` (PR). — [BuildMVPFast (secondary)](https://www.buildmvpfast.com/blog/tauri-v2-vs-electron-desktop-apps-2026); [electron PR #50415](https://github.com/electron/electron/pull/50415)

**Flet 1.0 (Sept 15, 2026)**
- Bundles CPython 3.12–3.14. Direct Python↔Dart bridge ("dart-bridge") with no socket overhead. Binary data channels.
- Android loads Python packages directly from the APK. Over 100 prebuilt mobile wheels (NumPy, pandas, SciPy, scikit-learn).
- `flet test` runs integration tests on packaged apps across Windows, macOS, Linux, iOS, Android and web.
- **Breaking change**: event handlers now run on a single event loop, so blocking code freezes the UI unless moved off-loop.

  — [Flet blog: Flet 1.0](https://flet.dev/blog/flet-1-0/); [MarkTechPost (secondary)](https://www.marktechpost.com/2026/09/20/flet-1-0-released-build-production-web-desktop-and-mobile-apps-in-python-only/)
- Can build single-binary Windows/Linux apps (including numpy/pandas) and single app bundles on Mac. — [note.com: Flet 1.0 (secondary)](https://note.com/shibats/n/nd793193b088c?hl=en)
- System tray today means using a third-party library (pystray) alongside Flet. The Flet MenuBar is not the native macOS menu bar. — [Flet-as-System-Tray-Icon](https://github.com/ndonkoHenri/Flet-as-System-Tray-Icon); [flet-dev discussion #3016](https://github.com/flet-dev/flet/discussions/3016)
- **Flutter desktop** (Flet's renderer): native macOS menu bar only via `PlatformMenuBar`, which replaces default menus; multi-window still experimental as of July 2026. — [flutter issue #162566](https://github.com/flutter/flutter/issues/162566); [Start Debugging (secondary)](https://startdebugging.net/2026/08/how-to-enable-multi-window-support-in-a-flutter-desktop-app/)

**Native Apple options that matter for local AI**
- **Foundation Models framework** (macOS/iOS 26): Swift access to Apple's ~3B on-device model with guided generation and tool calling; offline and free to run. — [Apple Newsroom, Sept 2025](https://www.apple.com/newsroom/2025/09/apples-foundation-models-framework-unlocks-new-intelligent-app-experiences/)
- **WWDC26** opened it to any provider (`MLXLanguageModel`, `CoreAILanguageModel`, cloud providers) behind one `LanguageModelSession` API. — [WWDC26 session 339](https://developer.apple.com/videos/play/wwdc2026/339/)
- **App Intents** make an app's actions available in Spotlight on Tahoe. — [MacStories Tahoe overview](https://www.macstories.net/news/macos-tahoe-the-macstories-overview/)

### Inferences
- **Decision frame for Enclave:**
  - **Option A — Stay on Flet 1.0 (lowest cost).** The Python stack already exists, 1.0 is stable, CPython is bundled, and the mobile path is real. Fill gaps with small native helpers:
    - a Swift menu-bar/tray and global-hotkey helper (or pystray plus a hotkey library);
    - a Finder Sync/Share extension and an App Intents target on macOS;
    - an Explorer context-menu handler on Windows.

    Risks: canvas-rendered UI (no Liquid Glass, custom menus, accessibility unknowns) and the single-event-loop migration.
  - **Option B — Tauri 2 UI + Python (or Rust) backend sidecar.** This is the proven local-AI pattern (Jan). Benefits: smallest installers, first-party updater/global-shortcut/tray plugins, web UI ecosystem (streaming chat, PDF viewer with highlight, charts), and iOS/Android.

    Costs: rewriting the UI in TS/React. Python-sidecar signing on macOS needs care: avoid PyInstaller `--onefile`; prefer onedir or Nuitka, signed with the same Team ID.
  - **Option C — Native SwiftUI (Mac) + WinUI/Tauri (Win).** Highest polish and direct access to Liquid Glass, Foundation Models, App Intents, Quick Look and Core Spotlight. It roughly doubles UI effort. Worth it only if Mac is the primary market.
- A pragmatic hybrid is **Tauri shell + existing Python backend as a sidecar + small Swift/C++ extensions** for Finder/Explorer, Quick Look and Spotlight. This gives the "consumer app" feel (web-grade UI polish, a PDF.js citation viewer, small downloads) while reusing the Python RAG/inference code.
- Electron is still defensible if the team wants Chromium consistency and Node packages (LM Studio shows it can feel polished). Its size and RAM overhead cut against a "lightweight, private" brand, next to a multi-GB model download.

### Gaps
- AnythingLLM desktop's framework (assumed Electron) and Khoj's current desktop client were **not verified** in this pass.
- No authoritative 2026 benchmark comparing Flet 1.0 startup, RAM and bundle size against Tauri/Electron was found.
- Wails, Slint, Dioxus and React Native for desktop (macOS/Windows) were not researched in this pass. No evidence was found of a major local-AI consumer app shipping on them.
- The merge/release status of Electron's native Liquid Glass PR and Flet 1.0's native-menu/tray status were not confirmed.

---

## Q10. Packaging and install UX: signing, notarization, Homebrew, winget, Flatpak/AppImage, Mac App Store, auto-update, size

### Takeaway
Signing and notarization are now mandatory in practice:
- Homebrew disabled every cask failing Gatekeeper on **Sept 1, 2026** and removed `--no-quarantine`.
- Apple Silicon Macs will not run unsigned native arm64 code.

Auto-update should be signed and delta-capable (Sparkle 2 on macOS; tauri-plugin-updater or electron-updater elsewhere). The Mac App Store is viable only if the app works inside the sandbox (security-scoped bookmarks for watch folders, no arbitrary helper processes). Most local-AI apps ship direct DMG/EXE plus Homebrew/winget instead.

### Cited Findings
- **Homebrew**:
  - Stopped supporting casks that fail Gatekeeper on **2026-09-01** and removed `--no-quarantine`; about 387 of 7,624 casks (~5%) had been deprecated for failing.
  - Disabled casks will not return unless upstream ships a compliant build.
  - Apple Silicon Macs don't "permit native arm64 code to execute unless a valid signature is attached."

  — [Homebrew Discussion #6482](https://github.com/orgs/Homebrew/discussions/6482); [Homebrew/brew issue #20755](https://github.com/Homebrew/brew/issues/20755); [QtPass macOS note](https://qtpass.org/macos)
- **Sparkle 2**: EdDSA-signed updates plus Apple code signing, delta updates, atomic installs, and sandboxed app support. Only static files (appcast XML) are needed on a server. — [Sparkle documentation](https://sparkle-project.org/documentation/); [sparkle-project/Sparkle](https://github.com/sparkle-project/Sparkle)
- **Electron update pattern**: Sparkle on macOS through an N-API bridge (it works with ad-hoc signing, whereas Squirrel.Mac needs Developer ID); electron-updater with NSIS differential updates or AppImage on Windows/Linux; or store channels (MSIX/winget, Snap/Flatpak). — [electron-sparkle-updater](https://github.com/miguel-heygen/electron-sparkle-updater)
- **Tauri updater**: each release emits updater artifacts plus detached signatures, and `latest.json` must reference them. — [BhayanakLegends issue #27](https://github.com/theHimanshuShekhar/BhayanakLegends/issues/27); [Tauri migrate guide](https://v2.tauri.app/start/migrate/from-tauri-1/)
- **Mac App Store sandbox**:
  - User-granted folder access lasts only until the app quits unless the app stores **security-scoped bookmarks**, which it must bracket with `startAccessingSecurityScopedResource`/`stop…`.
  - Bookmarks created before macOS 14.7.5 could fail to resolve after the update.

  — [AppCoda: remembering user intent for folders](https://www.appcoda.com/mac-apps-user-intent/); [Apple docs: security-scoped bookmarks](https://developer.apple.com/documentation/professional-video-applications/enabling-security-scoped-bookmark-and-url-access); [CODEBIT (secondary)](https://codebit-inc.com/blog/mastering-file-access-macos-sandboxed-apps/)
- **macOS sidecar signing**: every embedded binary and framework must be signed with the same Team ID under the hardened runtime, or library validation blocks loading. — [ResumeCompiler PR #63](https://github.com/raphaellith/ResumeCompiler/pull/63)
- **LM Studio** download page auto-picks the build (Apple Silicon DMG, Windows x64 AVX2, Linux AppImage/.deb x64/ARM64). — [tech-insider LM Studio setup (secondary)](https://tech-insider.org/how-to-set-up-lm-studio-local-ai-models-2026/)
- **Jan v0.8.0** keeps model storage manageable in-app ("Delete All" shows freed disk space). — [Jan changelog](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)
- **Flet 1.0** single-binary (Win/Linux) and single-bundle (Mac) builds with CPython included. — [Flet 1.0](https://flet.dev/blog/flet-1-0/); [note.com (secondary)](https://note.com/shibats/n/nd793193b088c?hl=en)

### Inferences
- **Recommended Enclave distribution:**
  - **macOS**: Developer ID-signed, notarized, stapled DMG (drag-to-Applications) plus a Homebrew cask, which now *requires* notarization. Sparkle 2 or tauri-updater with EdDSA signatures and delta updates.
  - **Windows**: signed MSIX or NSIS installer plus winget.
  - **Linux**: AppImage plus Flatpak.
- Keep the app installer small (under ~50 MB for Tauri/Flet; under ~150 MB for Electron) and download models separately after install, with the hardware-fit UI. Offer "portable/offline installer with model bundled" as a secondary download for air-gapped users.
- Defer the Mac App Store: sandboxing complicates watch folders, sidecar inference processes and Finder integration. Ship MAS later as a "Lite" edition if discovery matters.
- A one-line install script is fine for developers, but consumer channels should be DMG/MSIX/winget/Homebrew. `curl | sh` works against the "private, trustworthy" positioning.

### Gaps
- winget, Flatpak and Microsoft Store (MSIX) 2026 policy changes were not researched directly.
- No data on installer-size thresholds where consumer download abandonment rises.
- The current Mac App Store review stance on apps that download multi-GB models after install was not researched.
