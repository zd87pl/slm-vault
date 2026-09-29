# Documentation Index

Start from the main [README](../README.md): it covers installation, the
privacy model and the known limitations, and it is kept in step with the
code. [SECURITY.md](../SECURITY.md) has the security policy and threat model.

## Current

- [Launch plan](launch-plan/README.md) — roadmap and research notes for the
  local, private document vault (September 2026)
- [Quick Start](guides/QUICK_START.md) — pointer to the README quick start
- [Private Language Models](PRIVATE_LANGUAGE_MODELS.md) — CLI profiles:
  ingest, chat, adapters
- [MCP server](../advanced_vault/mcp_server/README.md) — manual client setup
  and the MCP tools

## Older notes

These predate the current plan and may not match the code. Most of them
cover parts of the desktop app that still exist.

- Desktop app internals: [MLX DoRA inference](MLX_DORA_ARCHITECTURE.md),
  [MLX Q&A generation setup](guides/MLX_QA_SETUP.md),
  [GUI code review](gui/GUI_CODE_REVIEW.md),
  [GUI improvements](gui/GUI_IMPROVEMENTS_SUMMARY.md)
- PDF/OCR options: [lighter OCR alternatives](architecture/LIGHTER_OCR_ALTERNATIVES.md),
  [SmolDocling analysis](architecture/SMOLDOCLING_ANALYSIS.md)
- Packaging: [distribution guide](DISTRIBUTION.md),
  [macOS app bundling](deployment/MACOS_APP_BUNDLING.md),
  [macOS distribution](deployment/MACOS_DISTRIBUTION.md)
- The desktop app's optional cloud Q&A and training flow:
  [security analysis](security/SECURITY_ANALYSIS_PDF_QA.md),
  [encrypted training workflow](security/ENCRYPTED_TRAINING_WORKFLOW.md),
  ["encrypt immediately" pattern](security/ENCRYPT_IMMEDIATELY_IMPLEMENTATION.md),
  [practical secure workflow](security/PRACTICAL_SECURE_WORKFLOW.md),
  [Supabase Vault analysis](security/SUPABASE_VAULT_ANALYSIS.md)
- Old test reports, partly about code that has since been removed:
  [new-component test summary](testing/TEST_SUMMARY_NEW_COMPONENTS.md),
  [validation report](testing/TEST_VALIDATION_REPORT.md)

Documentation for the removed cloud-training stack, sync backend, browser
extension and LangChain integration is preserved with that code on the
`legacy-archive-2026-09-29` branch.
