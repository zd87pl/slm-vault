# Enclave GUI

Local-first desktop experience for Enclave Private Language Models.

The GUI now boots into a `Private Model Studio` flow by default:
- Create or switch local profiles
- Add files or whole folders into encrypted private context
- Chat locally against that context
- Surface Data Sheriff posture and audits next to the model workflow
- Keep WDVA adapters as a first-class part of the product story

Cloud auth and sync are still supported, but they are no longer required to start using the app locally.

## Launch

From the repo root:

```bash
python3 -m advanced_vault.gui.vault_app
```

Or from this folder:

```bash
python3 vault_app.py
```

## Local-First Demo Mode

By default, the GUI will open in local-first mode when there is no saved cloud session.

Recommended setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[mlx,mac-performance,liteparse]"
npm install -g @llamaindex/liteparse
export ENCLAVE_PARSER_BACKEND=auto
python3 -m advanced_vault.gui.vault_app
```

What to expect on first use:
- A default `workspace` Private Model profile is created under `~/.vault/private_models`
- You can add files or folders directly from the landing page
- Chat history is isolated per profile
- Documents stay encrypted at rest and local by default

## Optional Cloud/Auth Mode

If you want the older authenticated flow, set:

```bash
export ENCLAVE_REQUIRE_AUTH=1
python3 -m advanced_vault.gui.vault_app
```

Optional cloud variables:

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_ANON_KEY="your_supabase_anon_key"
export ENCLAVE_BACKEND_URL="https://your-backend.example.com"
```

## Demo Flow

For an investor or product demo, the cleanest path is:

1. Launch the GUI.
2. Create a profile if you want a domain-specific workspace.
3. Click `Add Files` or `Add Folder`.
4. Open `Secure Chat Workspace`.
5. Ask for a summary, risks, themes, or an investor-ready narrative.
6. Open `Data Sheriff` in Settings to show controls, leases, and audit posture.

## Notes

- The recommended local model is `mlx-community/Qwen2.5-1.5B-Instruct-4bit`.
- WDVA adapters are surfaced in the GUI as profile-level adaptive layers.
- OCR/PDF extraction setup is deferred until first use so the app opens quickly.
- `LiteParse` is now supported as an optional PDF backend with automatic fallback to the legacy `PyPDF2 -> SmolDocling/Ollama` pipeline.
- For the Wednesday demo, preinstall `Node.js >= 18`, `@llamaindex/liteparse`, and warm one sample ingest before the meeting.
