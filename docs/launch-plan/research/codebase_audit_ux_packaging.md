# Codebase Audit: User-Facing Experience, GUI, Install, Packaging, Distribution, Docs & Repo Presentation (Enclave / `zd87pl/slm-vault`)

Audit date: 2026-09-29. Repo HEAD `40b6d50` (merge of PR #15, "MVP beta readiness"), 63 commits, no tags.
Primary source is the repository itself. Citation convention: `path:line` refers to files in `/home/user/slm-vault`.
Evidence labels:
- **[RUN]**: I executed or observed it in this audit (Linux x86_64 container, Python 3.11, no display, scratch venvs, isolated `$HOME`).
- **[CODE]**: verified by reading the code at the cited lines.
- **[DOCS]**: something the repo's docs claim, which I did not verify.
- **[INF]**: my inference from the cited evidence.

The GUI was driven headlessly with the repo's own `_FakePage` test harness (`advanced_vault/gui/tests/test_workspace_demo.py:27-50`). No real window was opened, so nothing about visual rendering is verified. No macOS or Windows machine was available, so the Mac timings are not measured.

---

## Q1. How many steps, minutes and GB from clone to first answer, on Mac and on Windows/Linux? What breaks for a non-developer?

### Takeaway
The only supported path is developer-grade: git, Python ≥3.10, Terminal, a bash script, a venv, then `enclave-gui`. There is no packaged, signed download. On Apple Silicon it takes about 12–16 user steps, 3–4 terminal commands and roughly 1.1 GB of model downloads on top of the dependencies (per the README), then another 3 steps for Claude Desktop. On Linux, the "minimal" install alone downloaded 3.1 GB of wheels and occupied 5.9 GB. Two things broke there:
- The GUI chat can never send a message.
- The CLI answered a trivial question wrong.

On Windows there is no setup path at all. Separately, a fresh install today resolves `mcp` 2.2.0, and the MCP server (the flagship Claude Desktop integration) crashes on startup.

### Cited Findings
**Install path and prerequisites**
- The README Quick Start is "macOS, ~5 minutes": `git clone` → `./setup.sh` → `source .venv/bin/activate` → `enclave-gui` / `enclave mcp install` / `enclave doctor` — `README.md:11-35` [DOCS].
- `setup.sh`:
  - passes `bash -n` [RUN]
  - looks for python3.12 / 3.11 / 3.13 / python3 ≥3.10; otherwise it fails with "brew install python@3.12" (`setup.sh:29-38`) [CODE]
  - installs `.[mac]` on Apple Silicon and `.[gui,mac-performance]` elsewhere (`setup.sh:65-74`)
  - runs `doctor` (`setup.sh:78`)
  - is bash-only, with no Windows/PowerShell equivalent anywhere in the repo [CODE]
- It does not create a launcher, `.app` or desktop shortcut. The user must re-activate the venv in Terminal on every launch (`setup.sh:80-89`) [CODE].
- The first model and embedding downloads are about 1 GB (Qwen2.5-1.5B-Instruct-4bit) plus about 130 MB (embeddings) — `README.md:37-42` [DOCS]. The default model constant is `mlx-community/Qwen2.5-1.5B-Instruct-4bit` (`advanced_vault/gui/vault_app.py:152`) [CODE].

**Dependency footprint (measured on Linux)**
- The core `pip install -e .` pulls **torch 2.14 plus the full NVIDIA CUDA 13 stack** because `sentence-transformers` is a *core* dependency (`pyproject.toml:60`) [CODE].
- Measured on Linux [RUN]:
  - 93 packages
  - about **3,119 MB of wheels** downloaded (torch 554.6 MB, nvidia-cudnn 553.1 MB, cublas 423.1 MB, triton 247.9 MB, …)
  - the venv is **5.9 GB** on disk (`nvidia/` 3.2 GB, `torch/` 1.2 GB, `triton/` 897 MB)
  - 100 s install with warm pip wheel cache; network time excluded, so a real first install is longer
- The README claims "~3 GB disk for dependencies + ~1.5 GB for models" (`README.md:313`) and calls the plain install "Minimal — CLI + MCP server only" (`README.md` Installation Options) [DOCS]. It is contradicted on Linux [RUN].

**First CLI answer on Linux (measured)**
- `enclave --help` responds in 0.5 s. `enclave doctor` finishes in 0.36 s and reports "Ready to go — 5 optional improvement(s)", including "✅ Local LLM (PyTorch)" [RUN].
- `enclave model ingest workspace file.txt` on a fresh install fails with a raw Python traceback, `FileNotFoundError: Profile 'workspace' does not exist` (`advanced_vault/private_models/manager.py:290`). The profile is only auto-created by the GUI (`vault_app.py:463-478`); the CLI user must first run `enclave model create workspace` [RUN].
- After creating the profile:
  - Ingest took 15.7 s, including a 129 MB embedding download [RUN].
  - The first `enclave model chat` took **45 s**, including a TinyLlama-1.1B-Chat download; the HF cache reached 2.2 GB [RUN].
  - The torch fallback model is `TinyLlama/TinyLlama-1.1B-Chat-v1.0` (`advanced_vault/gui/local_inference.py:142`) [CODE].
- **The answer was wrong.** For "What was Q3 revenue?" over a one-line file stating $4.2M, it returned a paraphrase of its own system prompt ("Enclave, a private local language model, is operating entirely on the user's local device…"). Retrieval did find `q3.txt` (score 0.86) [RUN].

**GUI chat on Linux, Windows and Intel Mac (never sends)**
- `LocalInferenceEngine.is_model_available()` returns `False` whenever MLX is not importable (`advanced_vault/gui/local_inference.py:181-185`) [CODE].
- Every Send first checks this. If it is false, the app shows "Download the local model first. Your message is still in the box." and opens the download dialog instead of sending (`vault_app.py:6326-6334`, `localization.py:51`) [CODE].
- The download succeeds via the torch/TinyLlama path, but availability never flips to True, so chat on non-MLX machines loops on the download dialog [CODE+INF].
- With the fake page on Linux, the workspace rendered "Download local model … once on this Mac before private Q&A can start" and `_get_local_private_model_status()` returned `available: False` [RUN].
- README contradiction: "Desktop GUI: Native macOS/Windows/Linux application" (`README.md:89`) and "macOS (Apple Silicon recommended), Windows, or Linux" (`README.md:311`) [DOCS].

**MCP server crashes on a fresh install**
- `pyproject.toml:50` only requires `mcp>=1.0.0`, and there is no lockfile [CODE].
- pip resolved **mcp 2.2.0** (MCP SDK 2.0.0 was published 2026-07-28 and 2.2.0 on 2026-09-07 — [PyPI mcp JSON](https://pypi.org/pypi/mcp/json)). The repo's last push was 2026-07-10 ([GitHub repo metadata](https://github.com/zd87pl/slm-vault)).
- `enclave-mcp` then dies on the `initialize` request with `AttributeError: 'Server' object has no attribute 'list_tools'` at `advanced_vault/mcp_server/server.py:130` [RUN].
- `enclave mcp status` prints "MCP server self-test: ❌ Error: 'Server' object has no attribute 'list_tools'" [RUN].
- The CI "Beta-user smoke test" (`.github/workflows/ci.yml:94-129`) installs unpinned, so it would now fail the same way [INF].

**`enclave mcp install` safety**
- It merges into existing config. However, if the existing `claude_desktop_config.json` fails to parse, `_load_config_at_path` returns `None` (`advanced_vault/gui/mcp_setup.py:195-206`). `merge_config` then returns only Enclave's config (`mcp_setup.py:223-226`), and `write_config` overwrites the file with no backup (`mcp_setup.py:229-245`) [CODE].
- This contradicts "safe: merges, never overwrites" (`README.md:29`) [DOCS vs CODE].

**Non-developer blockers**
- There are no releases (0 releases via the GitHub API, `git tag` empty) [RUN].
- There is no PyPI package: `https://pypi.org/pypi/enclave-vault/json` returns HTTP 404 [RUN].
- There is no Homebrew formula or cask and no winget package (grep finds only "Future" mentions in `docs/deployment/MACOS_DISTRIBUTION.md:125,196`) [CODE].
- The only pre-built-app path (`install_enclave.sh`) needs an `Enclave.app` produced by an unsigned build script (see Q6).
- To my knowledge (general, not verified here), macOS's CLT-provided `/usr/bin/python3` is 3.9, which `setup.sh` rejects. A non-developer would therefore need Homebrew and Python first.

**Mac GUI path, counted from code [CODE+INF]**
1. Install Python ≥3.10 and git, if missing.
2. `git clone`.
3. `./setup.sh`.
4. `source .venv/bin/activate`.
5. `enclave-gui`.
6. On the welcome screen, click "Add Private Files" (`welcome_screen.py`; `localization.py:22`).
7. Use the AppleScript file chooser (`vault_app.py:976-1016`).
8. Wait for embedding download and indexing; the only feedback is a toast (`vault_app.py:900-957`).
9. Type a question and press Send; the download dialog appears instead (`vault_app.py:6326-6334`).
10. Wait for about 1 GB with an indeterminate progress bar and no size shown (`vault_app.py:598-611`, `localization.py:50`).
11. Press OK.
12. Press Send again.
13. Wait for the full answer; there is no streaming (see Q2).

For Claude Desktop, add three more steps:
14. `enclave mcp install`.
15. Restart Claude Desktop.
16. Approve the consent prompt (`README.md:40-42`, [DOCS]).

### Inferences
- The README's "~5 minutes" is plausible only for a developer on Apple Silicon with Python already installed and a fast network. It does not hold for Linux or Windows users, who get a multi-GB CUDA stack, a GUI that cannot chat, and a weak 2023-era 1.1B model in float32 on CPU.
- The single highest-leverage fixes for first-run success are:
  1. Pin or upper-bound `mcp` and fix the server for SDK 2.x, with a lockfile.
  2. Move `sentence-transformers`/torch out of core, since fastembed/ONNX is already supported per `doctor` (`advanced_vault/cli/doctor.py:171-174`).
  3. Fix the MLX-only availability check, or explicitly declare Mac-only.
  4. Ship a signed app.
- For a "non-developer" there is currently no path at all.

### Gaps
- Mac timings and the `[mac]` install size (torch macOS arm64 wheel, mlx, flet) were not measured; no macOS host was available.
- The actual consent dialog, AppleScript picker permissions and Claude Desktop behaviour were not exercised.
- Windows was not tested. The conclusion "no path" rests on the absence of any non-bash setup and the MLX-only availability check.

---

## Q2. What is the GUI's information architecture, and what are the top UX problems?

### Takeaway
The live app is a four-item sidebar shell: Chat, Vaults, Files, Settings. It is rendered by `demo_shell.py` on top of a 16k-line `VaultApp`, and underneath it sits a second, older UI of secrets, training, policies and activity screens, reachable through Settings → Advanced.

The primary flow (add files → ask → see sources) exists, but it is thin:
- no streaming
- no Markdown
- non-clickable citations
- no drag-drop
- no delete or new-chat in the main shell

Onboarding crashes into a fallback with investor-demo copy, and the Settings tab is dominated by "Data Sheriff" and mock-wallet controls.

### Cited Findings
**Information architecture (as shipped) [CODE]**
- The sidebar has four text-only items, "Chat, Vaults, Files, Settings" (`advanced_vault/gui/modern_sidebar.py` `_build_nav_section`; `routes.py:6-13`). Routing is in `vault_app.py:8568-8586`.
- **Chat** (`demo_shell.py:34-309`): empty state "Ask anything about your files", three suggestion chips, a model-download card when needed, and a single-line input plus Send.
- **Vaults** (`demo_shell.py:485-571`): Health/Finance/Legal/Personal cards with Upload and Train.
- **Files** (`demo_shell.py:311-482`): "Create Profile", a search box, "Personalization Layers" (WDVA adapters) and the "Documents & Folders" list.
- **Settings** (`vault_app.py:9353-9456`): titled "Security & Integrations", with tabs Security (default, Data Sheriff), Integrations and Advanced. Advanced opens legacy "System Setup", "Training Queue", "Policies" and "Activity Log" (`vault_app.py:9398-9405`).
- **Connections** (`demo_shell.py:574-838`) has no sidebar item (index −1). It is reachable from onboarding "protect" and from Settings → Integrations.
- **First launch**: `check_authentication` goes to local-first mode (`vault_app.py:1191-1225`), then `_show_initial_authenticated_view`, which tries prosumer onboarding and falls back to the legacy `WelcomeScreen` (`vault_app.py:2004-2016`).

**Top UX problems, ranked**

1. **Onboarding crashes silently.**
   - `OnboardingFlow.__init__` calls `self._build_step()`, which calls `self.update()` before the control is on a page (`prosumer_components.py:215, 217-231`). Flet 0.28.3 asserts `"Control must be added to the page first"` [RUN: reproduced by constructing it; the log showed "Prosumer onboarding failed, falling back to legacy"].
   - The 5-step "What do you want to protect? / Train your personal AI" flow therefore never shows.
   - Even if fixed, its upload step is a decorative "Drag & drop files here" box with no click handler or file picker, only "Skip for now" (`prosumer_components.py:299-351`). "Train My AI" is a stub: `# Would trigger actual training via LocalTrainingManager` (`prosumer_components.py:449-451`) [CODE].
   - Category chips are rebuilt on every toggle without a `selected=` state (`prosumer_components.py:259-270, 438-443`), so the selection visual likely resets [INF].

2. **The fallback welcome screen is off-message.**
   - The welcome text shown to users is "Private AI workspace for the agentic web … decide what Claude, ChatGPT-like/MCP tools, browsers, and ecommerce agents can see". The trust badge "Runs on this Mac" appears even on Linux, and a button reads **"Open Investor Demo"** (`localization.py:16-26`) [RUN: strings captured from the first screen].
   - The investor-demo sample files include "payments_guardrails.md", and the success copy is "Ask: What blocks autonomous spending above $75?" (`vault_app.py:2322-2389`, `localization.py:44`) [CODE].

3. **Adding documents is hard to find and has no drag-and-drop.**
   - The Files view has no "Add files" button, only "Create Profile" (`demo_shell.py:420-425`). It tells the user to "Use Workspace to add more files or folders" (`demo_shell.py:471`), but the Chat/workspace view has no add button either (`demo_shell.py:34-309`) [CODE, RUN strings].
   - In the main shell, the only upload entry is on Vaults (`demo_shell.py:530, 550`), and it ignores the chosen category (`on_upload=lambda cid: app._open_private_files_picker()`).
   - There is no OS file drag-and-drop anywhere. Flet 0.28.3 has no OS file-drop API: no `file_drop`/`on_drop`/`dropped_files` in the installed `flet` package, and `DragTarget` only handles in-app `Draggable`s [RUN grep].
   - The README's "Drop documents, instantly queryable" (`README.md:83`) and the legacy welcome response text "**Drop a PDF** on the home screen" (`vault_app.py:6483`) are therefore unfulfilled.
   - There is no watch-folder UI in the main shell. `WatchedFolder` exists only in the legacy library view (`vault_app.py:15703-15836`).

4. **Chat is not a modern chat.**
   - No streaming: a "Thinking..." spinner shows until the full answer arrives (`vault_app.py:6378, 6512-6522`), and there is no stop/cancel.
   - Answers are plain `ft.Text`, with no Markdown rendering, although the app's own canned text uses `**bold**` (`vault_app.py:5925-5930, 6483`). No `ft.Markdown` is used anywhere in the GUI [RUN grep].
   - Citations are up to 3 non-clickable rows, "name (score%)" plus a 2-line excerpt. There is no open-file action, preview, page number or highlight (`vault_app.py:5932-5956`).
   - Suggestion chips only fill the input and do not send; auto-submit is commented out (`vault_app.py:6022-6028`).
   - There are no copy, regenerate or conversation-list actions, and `_new_chat` is unreachable from any UI (static reachability analysis, see Q3).
   - The input is single-line and submits on Enter (`demo_shell.py:52-73`).

5. **Failures are silent and misleading.**
   - Chat runs a four-tier fallback: private profile → legacy LocalAgent → MLX base model → canned text (`vault_app.py:6415-6494`).
   - Errors are logged at warning/debug (`vault_app.py:6424, 6446, 6467`), and the user sees only "Your local Private Language Model is unavailable right now. Try again after local model setup finishes." (`vault_app.py:6490`).
   - `_run_on_ui_thread` swallows scheduling failures at `debug` level (`vault_app.py:2425-2436`) [CODE].
   - The sidebar always says **"Local model active"** (`modern_sidebar.py:150`), even while the workspace shows "Download local model" [RUN: both strings present on the same screen].

6. **Model management is opaque.**
   - The download dialog has an indeterminate bar, no size, ETA or cancel, and only the text "First download can take a few minutes" (`vault_app.py:584-655`, `localization.py:45-51`).
   - The main UI has no model picker or switcher. The model is set per profile at creation (`vault_app.py:463-478`).
   - Model copy is Mac-specific ("on this Mac") on every OS (`localization.py:49`) [RUN on Linux].

7. **Settings is a security console, not preferences.**
   - The default Settings tab is "Data Sheriff": filesystem scans of `~/Documents` up to 2,000 files, leases, kill switch and hardening (`vault_app.py:260-272, 9353-9389, 9611-10119`).
   - It includes mock wallet buttons "Create Wallet", "$19 test" and "$85 approval" (`vault_app.py:9979-9991`; also `demo_shell.py:1144-1146`).
   - The language selector is only in the legacy "System Setup" screen (`vault_app.py:14320-14360`).
   - Settings creates its sidebar without `translate` or `document_count` (`vault_app.py:9450-9452`), so the sidebar differs from other screens [CODE].

8. **Two UIs are glued together.**
   - Legacy screens (System Setup, Activity Log, Training Queue, Policies) call `build_ui()`, which sets `page.appbar` and adds a floating chat button overlay (`vault_app.py:7189-7398`).
   - `page.appbar` is assigned in exactly one place and never reset (grep: only `vault_app.py:7207`). The FAB is only removed in dead code (`vault_app.py:4085-4093`) and in `build_ui`.
   - After visiting Advanced, the old AppBar and FAB probably persist over the new shell [CODE+INF; not visually verified].
   - Every navigation is a full `page.clean()` and rebuild (16 `page.clean()` calls across `vault_app.py` and `demo_shell.py`).

9. **The Vaults and "Train AI" story does not work end-to-end.**
   - Category counts come from filename keywords, e.g. `"lab"`, `"will"`, `"statement"` (`demo_shell.py:496-509`, "Simple heuristic: use filename to guess category"). The loop re-counts the same active-profile documents once per profile [CODE].
   - "Train" looks for encrypted-KV entries tagged with the category (`vault_app.py:2106-2125`). The main upload path writes to the private-model RAG DB, not tagged KV entries (`vault_app.py:900-957`), so training likely always hits "Need at least 3 documents" (`vault_app.py:2150-2155`) [INF].
   - The training data is templated as "What information is contained in this document?" → first 800 chars (`vault_app.py:2127-2143`).
   - The fallback text tells users to `pip install -e '.[prosumer]'`, an extra that does not exist in `pyproject.toml` (`demo_shell.py:535`).

10. **Accessibility, theming, i18n and privacy gaps.**
    - **Accessibility**: 0 uses of `semantics_label`/`ft.Semantics` in `advanced_vault/gui/*.py` [RUN grep]. Navigation items are `Container(on_click=…)` text with no icons (`modern_sidebar.py` `_nav_item`). 83 occurrences of font sizes 9–11 appear in the main-shell files; the sidebar section label is size 9.
    - **Dark mode**: `page.theme_mode = ft.ThemeMode.LIGHT` is hard-coded (`vault_app.py:171`). `LightTheme` holds static hex constants (`light_theme.py:10-34`), plus 54 raw hex literals in view code. There is no dark theme.
    - **Window**: the title is "🔐 Enclave" with an emoji (`vault_app.py:170`). The window size assumes a 1440×900 screen on Mac rather than reading the display (`vault_app.py:176-195`).
    - **i18n**: only EN and PL are supported (`localization.py:6-9`), at roughly 175 keys each, while most main-shell strings in `demo_shell.py` are hard-coded English. Sidebar labels pass literal English as keys (`modern_sidebar.py`).
    - **Privacy**: chat history is written as **plaintext JSON** in `~/.vault/chat_history_<profile>.json` (`vault_app.py:429-436, 6053-6060`), and Q&A snippets go to `~/.vault/question_history.json` (`vault_app.py:230, 6547-6571`). This contradicts "Encryption at rest: All content encrypted" (`README.md:275`) [CODE vs DOCS].

**Other verified issues**
- **Supported file types in the GUI and CLI** are `.pdf .txt .md .csv .json .html .yaml/.yml .toml`, plus code files (`private_models/manager.py:48-71`). There is no `.docx/.xlsx/.pptx/.rtf/.eml/.pages` or images.
  - Unsupported files are silently counted as "skipped" (`vault_app.py:926-930`).
  - PDF text comes from `extract_pdf_text` (`manager.py:749-757`) [CODE]. OCR coverage of scanned PDFs is for the core-engine audit to confirm.
- **The macOS file picker is AppleScript** `tell application "System Events" … choose file` (`vault_app.py:976-1016`), run as a blocking subprocess with a 120 s timeout from the click handler.
  - It splits the returned text on `", "` (`vault_app.py:1006`). With AppleScript's default empty text-item delimiters, `list as text` concatenates paths without separators, so multi-file selection likely yields one bogus path [INF].
  - Calling System Events generally triggers a macOS Automation permission prompt [INF, general macOS behaviour, not verified].
- **Every GUI launch logs** "Configuration incomplete. Missing: SUPABASE_ANON_KEY" [RUN], and `__init__` sets RunPod env keys (`vault_app.py:163-166, 7035-7049`).
- **GUI cold start**: in [RUN] with the fake page, module import took about 1.5 s and `VaultApp(page)` took **4.3–4.7 s** before the first frame, with peak RSS about 910 MB.
  - The cause is that `local_inference.py:96-120` imports `mlx`/`mlx_lm` **and** `torch`/`transformers` at module import time, triggered by the first model-status check (`vault_app.py:560-567`). `torch` was in `sys.modules` after init [RUN].
  - The Flet client window startup is additional (not measured).

### Inferences
- The polished-looking shell sits on top of legacy flows. The core loop — add files, ask, get a cited answer — works on Apple Silicon only, and lacks the table-stakes interactions users expect from 2026 chat-with-docs apps: streaming, Markdown, clickable citations with preview, drag-drop, delete, and new chat.
- The onboarding and Settings copy position Enclave as an "agentic web / ecommerce / investor demo" security console rather than a private document vault. That is a direct positioning conflict with the stated launch goal.

### Gaps
- No real-window rendering was possible, so layout correctness is unverified. That includes whether the chat input stays pinned: `_render_primary_shell` wraps an `expand=True` column in a `ListView` (`vault_app.py:5822-5836`). Visual polish, the AppBar/FAB persistence and the AppleScript multi-select behaviour are also unverified.
- The consent dialog UX (`README.md:40-42`) was not examined; it belongs to the MCP/core audit.

---

## Q3. Is the 16k-line `vault_app.py` maintainable, what would a refactor or rewrite cost, and is Flet the right long-term foundation?

### Takeaway
No. `vault_app.py` is one 16,145-line god class with 250 methods. About a quarter of it is statically unreachable, it has 187 `except Exception` blocks, 20 ad-hoc threads, sibling imports hacked through `sys.path`, and a duplicated method.

The reachable consumer surface is small: 4 views in `demo_shell.py` plus about 20 helpers. The real logic sits in reusable modules (`PrivateModelManager`, `MCPSetupHelper`). A clean v1 UI therefore means rewriting the UI layer, not the product.

Flet reached 1.0 on 2026-09-14, but the app is pinned to 0.28 (May 2025), and 1.0 is explicitly not drop-in. The app already pays a migration cost either way, which makes this the natural decision point to choose the long-term UI stack.

### Cited Findings
**Structure and dead code**
- **Size** [RUN]:
  - `advanced_vault/gui/` has 29,183 Python LOC excluding tests, about 56% of the ~52k LOC in `advanced_vault/`.
  - `vault_app.py` is 16,145 lines: a single `class VaultApp` (`vault_app.py:160`) with 250 methods.
  - Other large GUI files: `qa_generator.py` 1,741 lines, `demo_shell.py` 1,186, `multi_adapter_engine.py` 955.
- **Dead code** [RUN, AST analysis]:
  - `show_landing_page` is 1,306 lines. It calls `_show_workspace_view()` and `return`s at line 4081, so lines 4082–5384 (**~1,303 lines**) are unreachable.
  - 20 methods are never referenced (873 lines), for example `show_knowledge_view`, `show_statistics`, `_set_inference_mode` and `_run_cloud_inference`.
  - A transitive reachability pass from `__init__` plus methods called by sibling modules finds **50 unreachable methods / 2,757 lines**, including `_new_chat`, `_delete_document`, `_show_adapter_selector` and `_start_landing_status_polling`. Together with the dead tail, that is **about 4,060 lines (~25%)**.
- **Code-smell signals** [RUN grep/AST]:
  - `_close_dialog` is defined 3 times (`vault_app.py:3283, 5904, 16124`); the last one wins.
  - 187 `except Exception` blocks.
  - 20 `threading.Thread(` calls in `vault_app.py` (26 across the GUI).
  - 230 `page.update()` calls.
  - 193 `page.snack_bar` uses.
  - Largest methods: `show_settings` 610 lines, `_build_sheriff_content` 508, `_start_training_workflow` 430, `show_langchain_policies` 334.
- **Coupling**:
  - Sibling modules are imported through a `sys.path.insert` hack, with `try/except ImportError` fallbacks that silently degrade features (`vault_app.py:31-146`). For example, if `demo_shell` fails to import, every navigation raises `RuntimeError("demo_shell module is unavailable")` (`vault_app.py:5840-5868`).
  - `demo_shell.py` functions take `app: Any` and call dozens of `VaultApp` private methods (`demo_shell.py:34-45`) [CODE].
- **Tests**: the GUI suite has 83 tests with a fake page; my run gave **67 passed, 16 skipped** in 16 s [RUN]. It has no test that constructs `OnboardingFlow`, which is why the onboarding crash shipped.
- **Reusable backend**: `PrivateModelManager`/`PrivateModelSession` handle profiles, ingest and ask (`advanced_vault/private_models/manager.py`, 970 LOC total). `MCPSetupHelper` (`gui/mcp_setup.py`, 411 LOC) is already shared by the CLI (`advanced_vault/cli/main.py:1558-1618`) [CODE]. FastAPI and uvicorn are already an optional extra (`pyproject.toml` `backend`).

**Flet status and fit**
- **Pin and release history**: the project pins `flet[all]>=0.28.3,<0.29` (`pyproject.toml:95`).
  - Flet 0.28.3 was released 2025-05-20.
  - 0.80.0 on 2025-12-25.
  - **1.0.0 on 2026-09-14**; the latest is 1.0.2 (2026-09-28).
  - Source: [PyPI flet JSON](https://pypi.org/pypi/flet/json) [RUN via curl].
- **Flet 1.0 announcement** ([Flet 1.0 blog](https://flet.dev/blog/flet-1-0), via fetch):
  - It is "not a drop-in replacement" for 0.28.x.
  - "In 0.28 every sync event handler ran on its own thread, so blocking code never froze the UI. In 1.0 handlers run on the app's event loop."
  - It adds a declarative UI, `flet build` for "Windows, macOS, Linux, iOS, Android, and web", up to 6.7× faster control diffing, and a deprecation policy of "three minor releases".
  - The summary I fetched mentions nothing about code signing, notarization or bundle size.
- **The code already anticipates the break**: `run()` switches between `ft.app()` and `ft.run()` based on `FilePickerResultEvent` existing (`vault_app.py:16135-16141`). Everything else uses 0.28-era APIs: 7 `ft.FilePicker(`, 9 `FilePickerResultEvent`, 81 `ft.ElevatedButton(`, 193 `page.snack_bar`, 42 `page.overlay` [RUN grep].
- **Threading assumption**: many handlers do blocking work, for example the AppleScript picker subprocess with a 120 s timeout (`vault_app.py:992-997`) and synchronous SQLite and status calls on each render (`vault_app.py:657-711`). These rely on 0.28's thread-per-handler model and would freeze the UI under 1.0 unless refactored [CODE+INF].
- **Capability limits in 0.28** [RUN]:
  - no OS file drag-and-drop API in the installed package
  - `flet[all]` 0.28.3 installs about 130 MB of site-packages, with `flet_desktop` 16 MB and `flet_web` 13 MB
  - `enclave.spec` hidden-imports `flet_core`/`flet_runtime`, which do not exist in 0.28.3
- **Native feel**: the UI uses Material `ft.Theme(color_scheme_seed=…)` (`vault_app.py:199`) and Flutter-drawn controls. The app has no native menu-bar integration [CODE].

### Inferences
- **Refactor vs rewrite**: salvaging `vault_app.py` in place is poor value. About 25% is dead, the reachable legacy screens (secrets, policies, training queue, sheriff, wallet) are mostly out of v1 scope (see Q5), and the Flet 1.0 migration touches most of the remaining UI code anyway.
  - The v1 product surface — Chat, Library, Model/Settings, Connect-to-Claude — can be rebuilt as roughly 4 screens on top of `PrivateModelManager` and `MCPSetupHelper`.
  - Rough sizing, as inference only: a few thousand lines of UI code and weeks rather than months for one experienced developer, with the existing engine code reused.
- **Stack options** (inference, not externally sourced in this audit because the web-search budget was exhausted):
  - **Flet 1.0 (Python)**:
    - Pros: lowest switching cost, since it is the same language and process as the MLX/RAG stack; now "production-ready" per the maintainers; declarative mode suits a rewrite.
    - Cons: non-native Material look, no OS drag-drop (unverified for 1.0), and the same heavy Python/ML bundling problem.
  - **Tauri or Electron with a Python sidecar (local HTTP/IPC)**:
    - Pros: web-grade chat UX (streaming, Markdown, PDF preview, drag-drop are commodity), a mature signing/notarization/auto-update ecosystem, and consistency with how popular local-LLM desktop apps present.
    - Cons: two languages, and the Python sidecar still needs PyInstaller-style packaging of torch/MLX.
  - **Swift-native (macOS only)**:
    - Pros: best feel, with MLX-Swift available.
    - Cons: loses Windows/Linux and the Python engine reuse.
  - **Local web UI served by `enclave serve`**:
    - Pros: cheapest cross-platform option and easy to demo in a GIF.
    - Cons: weaker "app" feel, with no dock icon or file associations.
- Given the Apple-Silicon/MLX focus and a Python engine, the pragmatic choices are:
  - a Tauri shell + Python sidecar, if the goal is a consumer-grade feel and auto-update;
  - a clean Flet 1.0 rewrite, if speed of shipping with one language dominates.
- Either way, the UI must not import torch or MLX in-process at startup.

### Gaps
- Flet 1.0's desktop packaging maturity (signing, notarization, auto-update, bundle size with torch/MLX) and its drag-and-drop support were not verified; the fetched blog summary did not cover them.
- No external benchmarks for Tauri, Electron or Flet bundle size or startup were gathered, because the web-search budget was exhausted.

---

## Q4. What does a first-time GitHub visitor see, and what's missing to convert them into a star or install?

### Takeaway
A visitor lands on a 400+ line README with no screenshot, GIF or demo, three badges, an unsourced statistic, and an "MCP gatekeeper for agents" pitch that sprawls into personal-data vaults, adapter training, DPO/GRPO env vars and encrypted adapter sharing. There are no releases, no installer, and no PyPI one-liner.

Naming is fragmented: slm-vault / Enclave / enclave-vault / "Enclave Vault" / "Personal Vault", and "Enclave" collides heavily with TEE terminology. The docs are sprawling and partly describe a different product (RunPod health or genomics fine-tuning), with 24 broken links. The standard OSS trust files are missing.

### Cited Findings
**Repository metadata** ([GitHub API via MCP](https://github.com/zd87pl/slm-vault)) [RUN]
- The repo is public: 2 stars, 0 forks, 2 open issues.
- It was created 2025-10-11 and last pushed 2026-07-10.
- It has 0 releases and 0 tags; Discussions are disabled.
- The homepage field is `getenclave.io`, and topics are set.

**README first impression**
- The title and tagline read "# Enclave — Privacy-First AI Personal Data Manager — Your local agent that external AIs command via MCP" (`README.md:1-5`).
- There are only License, Python and MCP badges: no CI, release or download badges.
- **There are zero images in the repo**, apart from three browser-extension icons (`git ls-files` for png/jpg/gif/svg/mp4/icns/ico) [RUN]. There is no screenshot, GIF, video or app icon; the `assets/` directory referenced by `enclave.spec` and `flet.json` does not exist [RUN].
- It uses an unsourced statistic, "79% of organizations are adopting agentic AI, but only 48% have frameworks…" (`README.md:55`).
- **Scope sprawl**: the README contains sections on MCP tools, Personal Data Vaults with emoji tables, auto-classification, one-click adapter training, encrypted adapter backup, SFT/DPO/ORPO/GRPO/QAT env vars, and adapter packaging (`README.md` ~150-370).
- The claims below are contradicted by the audit (see Q1/Q2):
  - "Drop documents, instantly queryable" (`README.md:83`)
  - "Desktop GUI: Native macOS/Windows/Linux application" (`README.md:89`)
  - "Encryption at rest: All content encrypted" (`README.md:275`)
  - "Train via GUI: Drop docs → Click 'Train AI' → Done in 5-15 min" (`README.md:216`)
  - "safe: merges, never overwrites" (`README.md:29`)
- The "Documentation" section links first to `docs/architecture/ARCHITECTURE.md`. That file describes "a secure, scalable platform for continuously finetuning private Small Language Models using multimodal personal health data on RunPod infrastructure", with a "Genetic Data Pipeline" of VCF/FASTA files (`docs/architecture/ARCHITECTURE.md:1-20`). The "Deployment Guide" link goes to RunPod (`README.md:389-393`).
- "Contributing" consists of 5 generic bullets (`README.md:411+`).

**Naming inconsistency** [CODE/RUN]
| Surface | Name used |
|---|---|
| Repo | `slm-vault` |
| Product in README, window title and sidebar | Enclave |
| PyPI distribution | `enclave-vault` (unpublished; 404) |
| `.app`, Makefile and spec | "Enclave Vault" (`Makefile:91`, `enclave.spec` CFBundleDisplayName) |
| CLI help | "Personal Vault CLI" (`advanced_vault/cli/main.py:64-74`) |
| macOS menu-bar app | "Personal Vault" (`advanced_vault/macos_app/vault_app.py:2`) |
| Docs index | "SLM Vault documentation" (`docs/README.md:3`) |

- Bundle IDs conflict: `ai.enclave.vault` (`enclave.spec:33`, `Makefile:93`) versus `com.enclave.vault` (`advanced_vault/gui/flet.json:5,10`; `browser-extension/native-messaging-host/com.enclave.vault.json`).
- Taglines differ across surfaces:
  - `pyproject.toml` description: "Privacy-first AI personal data manager…"
  - onboarding: "Private AI workspace for the agentic web"
  - prosumer onboarding: "Your personal AI that learns from your documents"
  - `flet.json`: "Secure Encrypted Vault with AI Inference"
  - `INSTALLER_README.txt`: "secure encrypted vault for storing Secrets (API keys, passwords, tokens)"

**"Enclave" name collisions** [RUN]
- A GitHub repository search for `enclave in:name` returns **1,914 repos**. The top results are TEE and security projects: keystone-enclave/keystone (537★), trailofbits/SecureEnclaveCrypto (288★), enclaver-io/enclaver (164★), aws/aws-nitro-enclaves-cli (156★).
- It also includes an AI app literally named **"Enclave"**, yuanzui0728/Enclave (189★, created 2026-03, Tauri AI-companion app), and "Enclave-Local", an offline AI tool.
- The PyPI name `enclave` is already taken (HTTP 200).
- In security vocabulary, "enclave" means hardware TEEs such as Apple Secure Enclave and AWS Nitro Enclaves. That invites confusion or skepticism for a product that does not use a TEE [INF].

**Docs sprawl and staleness** [RUN]
- `docs/` has 37 files, and the repo has 65 Markdown files excluding research notes.
- **24 broken relative links**, for example `docs/README.md` → `../BACKLOG.md`, `../ROADMAP.md`, `./business/*` and `./architecture/WDVA_ARCHITECTURE.md`; `langchain-enclave/README.md` → `../../CONTRIBUTING.md` and `../../docs/API_REFERENCE.md`; `advanced_vault/README.md` → `docs/API.md` and `docs/SECURITY.md`.
- **28 Markdown files mention RunPod.**
- `docs/implementation/STATUS.md:3-4` says "Last Updated: 2025-01-30 — Status: Alpha Release Ready ✅" and lists RunPod and Supabase phases.
- `docs/README.md` lists 4 RunPod deployment docs under "Deployment".
- The GUI docs use internal jargon, e.g. "Private Model Studio", "Keep WDVA adapters as a first-class part of the product story" (`advanced_vault/gui/README.md:1-12`).
- `INSTALLER_README.txt` is stale: "Sign up or sign in with your email… Create a master password… Internet connection (for cloud sync)… macOS 10.13" (`INSTALLER_README.txt:12-50`). The app is now local-first, and the spec's minimum OS is 10.15 (`enclave.spec:145`).

**Repo hygiene** [RUN]
- Missing: CONTRIBUTING, CODE_OF_CONDUCT, **SECURITY.md** (notable for a crypto/privacy product), CHANGELOG, and `.github/ISSUE_TEMPLATE`. `.github/` contains only `labeler.yml`, `pull_request_template.md` and 2 workflows (`ci.yml`, `pr-review.yml`).
- CI is Ubuntu-only: lint, tests, GUI tests with mock display, beta smoke test and security scan (`.github/workflows/ci.yml`). There is no macOS runner and no build or release job.
- **Root clutter** — 33 top-level entries, including:
  - 4 root Dockerfiles (`Dockerfile`, `.axolotl`, `.dev`, `.minimal`) plus `docker/`, with 3 more Dockerfiles and QA scripts
  - `docker-compose.yml`
  - `test_runpod.sh`, which hard-codes a RunPod endpoint `https://api.runpod.ai/v2/ayi3s70ihlpbtg` (`test_runpod.sh:7`)
  - `test_runpod_comprehensive.sh`, `test_full_workflow.py`, `verify_backend.py` (targets `localhost:8000` backend)
  - `requirements.txt`: the legacy RunPod stack with `torch==2.1.0`, `kubernetes`, `wandb`, `differential-privacy` (`requirements.txt:1-60`)
  - `requirements-poc.txt`
  - both `config/` and `configs/`
  - `src/`: 10,725 LOC of legacy code including `src/genomics`, `rp_handler.py` and `openai_gpt_integration.py`
  - `reports/`, `integrations/openclaw-enclave`, `langchain-enclave/`
  - a 25 KB `.secrets.baseline`
- **Stub packages**: `advanced_vault/{threshold_crypto,speculative,homomorphic,federated}` are one line each.

### Inferences
What is missing to convert a visitor:
1. A 10–20 s GIF or video of drop-a-PDF → ask → cited answer, plus a screenshot, above the fold.
2. A one-sentence positioning statement for the target ("A private, local AI for your documents — nothing leaves your Mac").
3. A signed `.dmg` in GitHub Releases, a Homebrew cask, and optionally `pipx install` / `uvx` from PyPI.
4. Honest platform scope (Apple Silicon first).
5. Trust signals: SECURITY.md with threat model, reproducible builds or checksums, CI badge, CHANGELOG, a short "How it works / what leaves your machine" section.
6. Pruning: move RunPod/src/Docker/genomics/browser extension to an `archive/` branch or a separate repo, and collapse docs to about 5 current pages.
7. A distinct, searchable name: rename or qualify "Enclave", and align the repo, package, app and bundle IDs.

### Gaps
- `getenclave.io` was not checked.
- The trademark status of "Enclave" in the app or software class was not researched, because the web-search budget was exhausted.
- The two open GitHub issues were not reviewed.

---

## Q5. Which GUI and repo features are over-scoped for a v1 consumer app and should be hidden or cut? Is the browser extension useful?

### Takeaway
The app ships several products at once: an agent-governance console (Data Sheriff, policies, leases, kill switch), a mock payments wallet, a secrets/API-key manager, an adapter-training lab (WDVA/DoRA, DPO/GRPO, queues), cloud auth and sync (Supabase), RunPod cloud QA, prosumer "vaults", plus a browser extension and a LangChain package. For a "private LLM document vault" v1, nearly all of these should be hidden or cut, leaving Chat, Library, Model and Connect-to-Claude.

### Cited Findings
**Surfaces visible in the GUI today** [CODE]
- **Data Sheriff** is the default Settings tab (`vault_app.py:9353-9389`), with a ~500-line panel (`vault_app.py:9611-10119`). The CLI has `sheriff scan/protect/access/read/revoke/audit/hardening/status` (`cli/main.py:974-1185`).
- **Wallet**: "Create Wallet / $19 test / $85 approval" buttons (`vault_app.py:9979-9991`; `demo_shell.py:1144-1146`); the global kill switch is in `demo_shell.py:901`. The CLI describes it as "wallet — Mock-only governed spend workflows" [RUN `enclave --help`]. There are 1,118 LOC in `advanced_vault/wallet/`.
- **Investor demo**: "Investor Demo Flow" panel (`demo_shell.py:736`), "Open Investor Demo" button (`localization.py:23`), and 6 "investor" strings in `vault_app.py` [RUN grep].
- **Adapter training and personalization**: "Personalization Layers" and "Create Profile" on Files (`demo_shell.py:420-462`), "Train" on each Vault card, and "Training Queue" under Advanced. The GUI includes `training_manager.py` (801 lines), `training_queue.py` (734), `qa_generator.py` (1,741), `qa_generator_mlx.py` (555), `mlx_dora_inference.py` (783), `multi_adapter_engine.py` (955) and `local_training_manager.py` (300).
- **Legacy secrets manager**: `build_ui`/`load_secrets`/`create_secret_card`/`show_add_dialog` (`vault_app.py:7189-8221`), plus CLI `add-secret`/`get`, whose help examples are wrong: `enclave add secret …` gives "No such command 'add'" [RUN].
- **LangChain policies editor**: `show_langchain_policies` and its create/edit/delete dialogs (`vault_app.py:10807-11517`).
- **Cloud auth and sync**: `auth_screen.py` (526 lines), `cloud_sync.py` (356 lines), `OAUTH_SETUP.md`. They are off by default via `ENCLAVE_LOCAL_FIRST=1` (`vault_app.py:241`) but still imported, and Supabase is still validated at startup [RUN log].
- **RunPod cloud QA and training**: 45 "runpod" references in `vault_app.py` [RUN grep], including env mutation in `__init__` (`vault_app.py:163-166, 7035-7049`) and `flet.json` env keys (`advanced_vault/gui/flet.json:15-24`).
- **Ollama and OCR setup**: `ollama_setup.py` (456 lines) and `_setup_ollama_with_progress` (`vault_app.py:1543-1613`), even though MLX is the actual default path.
- **macOS menu-bar app**: `advanced_vault/macos_app/vault_app.py` is a `rumps` app titled "Personal Vault", not wired to any entry point, and `rumps` is not a dependency (grep: no references outside the module) [RUN].

**Browser extension** [CODE]
- It is described as "Secure API key storage with consent-based access for AI agents" (`browser-extension/manifest.json:5`).
- It holds `host_permissions` for a hard-coded Railway dev backend, `https://keen-curiosity-production-1288.up.railway.app/*` (`manifest.json:10-12`; `background/vault-client.js:7`), with login and refresh flows (`vault-client.js:36, 101`).
- Its content script is injected on `<all_urls>` (`manifest.json:31-36`) and pattern-matches OpenAI, Stripe, GitHub and Slack keys in form inputs (`content/content.js:1-30`).
- Its README advertises "Cloud Sync: Automatic sync with Enclave backend vault" and lists "Production: Build the extension (when ready)" (`browser-extension/README.md`). There is no store listing [INF].
- It totals about 2.7k JS LOC.

### Inferences
**Cut or hide for v1:**
- Wallet, the investor-demo flows, Data Sheriff (keep at most a simple "Activity" log of what Claude asked), the policies editor, the legacy secrets UI, the training queue and adapter training (keep as a later "Labs" feature), prosumer vault categories (filename heuristics that mislabel), cloud auth/sync, RunPod, and Ollama/OCR setup UIs.
- The browser extension, `langchain-enclave`, `integrations/`, `src/`, the stub crypto packages and `macos_app`.

**Keep:** Chat with cited answers, a Library with add/remove, drag-drop and watch-folder, a model choice and download manager, Connect to Claude Desktop/Cursor with an access log, and Settings for theme, language, storage location and privacy.

**The browser extension is a distraction and a trust liability.** It is an API-key manager that phones a third-party dev backend and injects into every page, which is the opposite of the "nothing leaves your machine" story. It should be removed from the repo's main story, archived, or rebuilt later as a local-only companion.

### Gaps
- The test-suite health of the cut-candidate modules was not assessed; that belongs to the core audit.
- There is no usage telemetry to inform which features existing beta users actually touch.

---

## Q6. What is the state of packaging and distribution: signed/notarized .dmg, Homebrew, Windows/Linux installers, auto-update, GitHub Releases?

### Takeaway
Nothing is shipped. There are three overlapping, unverified build pipelines (`flet pack`, PyInstaller spec, `flet build macos`). None signs or notarizes, and there is no app icon, CI build, release, Homebrew cask, Windows installer or auto-update. The shipped instructions tell users to right-click → Open, which no longer bypasses Gatekeeper on macOS Sequoia and later. A frozen `.app` also cannot serve MCP to Claude Desktop as currently coded.

### Cited Findings
**Three overlapping pipelines** [CODE]
1. `make build-mac` / `build-win` / `build-linux` use `flet pack advanced_vault/gui/vault_app.py … --add-data "advanced_vault:advanced_vault"` (`Makefile:86-123`).
2. `make build-mac-pyinstaller` runs `pyinstaller enclave.spec` (`Makefile:96-99`).
3. `advanced_vault/gui/build_macos_app.sh:69` runs `flet build macos`; it is used by `scripts/build_release.sh` and `scripts/package_for_distribution.sh`. `scripts/build.py` supports `flet` or `pyinstaller` (`scripts/build.py:250-295`).

**Details of each pipeline** [CODE]
- **Signing and notarization**:
  - `enclave.spec` has `codesign_identity=None`, `entitlements_file=None` (`enclave.spec:118-119, 169-170, 193-194`).
  - The DMG is a plain `hdiutil create … UDZO` with no signing (`Makefile:139-150`; `scripts/build.py:123-160`).
  - The docs list notarization, code signing and a DMG as "Future" or as checklist items (`docs/DISTRIBUTION.md:126-131, 186-196, 248`; `docs/deployment/MACOS_DISTRIBUTION.md:114`).
- **Gatekeeper instructions are stale**:
  - `install_enclave.sh:99-107` says "This is normal for unsigned apps (MVP testing)… Right-click the app… Select 'Open'". `INSTALLER_README.txt:24-28, 77-78` and `scripts/build_release.sh:153` say the same.
  - Apple: "In macOS Sequoia, users will no longer be able to Control-click to override Gatekeeper when opening software that isn't signed correctly or notarized. They'll need to visit System Settings > Privacy & Security…" (Aug 6, 2024) — [Apple Developer News](https://developer.apple.com/news/?id=saqachfa).
- **No icon or assets**: `assets/` does not exist, yet it is referenced for `icon.icns`/`icon.ico` (`enclave.spec:37-40, 135, 171`; `flet.json:8, 13`; `Makefile:166`) [RUN].
- **Broken or odd inputs**:
  - `enclave.spec` hidden-imports `flet_core` and `flet_runtime`, which are absent in Flet 0.28.3 [RUN].
  - It also hidden-imports `torch`/`transformers` and excludes `PIL` (`enclave.spec:45-77`) [CODE].
  - The app-bundle requirements file (`advanced_vault/gui/requirements.txt`) lists supabase, gotrue, PyPDF2, outlines, mlx-vlm and docling-core, but **not** the `advanced_vault` package that `vault_app.py:37-43` imports. `flet build macos` runs from `advanced_vault/gui/` (`build_macos_app.sh:69`), so the bundle likely lacks `advanced_vault.*` [INF].
- **MCP from a packaged app**: when frozen, `get_python_path` falls back to Homebrew or system `python3` (`gui/mcp_setup.py:118-150`), and the generated config runs `python -m advanced_vault.mcp_server` with `PYTHONPATH=<project root>` (`mcp_setup.py:173-181`). A `.app` user's system Python will not have `advanced_vault` or its deps, so Claude Desktop integration from a packaged app is broken by design [INF].
- **Windows**: `make msi` only echoes "requires WiX toolset… use dist/Enclave.exe directly" (`Makefile:174-177`). There is no Windows build in CI and no Windows setup script [CODE].
- **Linux**: an AppImage target depends on a locally installed `appimagetool` and falls back to printing a note (`Makefile:153-171`) [CODE].
- **Releases and CI**: there are no release workflows (`.github/workflows/` has only `ci.yml` and `pr-review.yml`), 0 GitHub releases and 0 tags [RUN].
- **Other channels**:
  - No Homebrew, winget or PyPI; `enclave-vault` returns 404 on PyPI [RUN].
  - No auto-update: the only mention is "Optional: Implement Sparkle or similar" (`docs/deployment/MACOS_DISTRIBUTION.md:196`) [RUN grep].
- **Version**: 0.1.0 is hard-coded in `pyproject.toml`, `Makefile:24`, `enclave.spec:31`, `flet.json:3` and `scripts/build_release.sh:11`. There is no single source of truth [CODE].

### Inferences
Minimum viable distribution for a consumer macOS launch:
1. One pipeline, not three.
2. A real icon.
3. Developer ID signing, notarization and stapling in a macOS GitHub Actions job.
4. A `.dmg` attached to GitHub Releases with checksums.
5. A Homebrew cask.
6. An auto-updater (Sparkle for native or Tauri updater, or an equivalent for Flet).
7. A bundled `enclave-mcp` executable inside the app for Claude Desktop to launch.
8. Models downloaded on first run rather than bundled.

Windows and Linux should be explicitly deferred or labeled experimental until the non-MLX inference path works.

### Gaps
- No build was attempted: macOS is required, and `flet build` needs the Flutter SDK. Resulting bundle size, startup time and whether the `.app` launches at all are unmeasured.
- Flet 1.0's signing and notarization support was not confirmed.
