# Documentation Organization Plan

## Current Status
- **Total markdown files:** 38+ files in root directory
- **Duplicates identified:** Multiple "status", "next steps", "implementation" files
- **Outdated files:** Some status files reference incomplete phases

## Organization Structure

```
docs/
├── README.md                    # Main documentation index
├── architecture/                # System architecture docs
│   ├── WDVA_ARCHITECTURE.md
│   ├── ARCHITECTURE.md
│   ├── BROWSER_EXTENSION_MCP_ARCHITECTURE.md
│   └── CRYPTOGRAPHIC_SPECS.md
├── implementation/              # Implementation status and summaries
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── STATUS.md                # Consolidated status (merge multiple status files)
│   └── PHASES_COMPLETE.md       # Consolidated from IMPLEMENTATION_COMPLETE.md
├── deployment/                  # Deployment guides
│   ├── RUNPOD_DEPLOYMENT.md
│   ├── RUNPOD_TESTING.md
│   ├── RUNPOD_TROUBLESHOOTING.md
│   ├── RUNPOD_AXOLOTL.md
│   └── MACOS_DISTRIBUTION.md
├── testing/                     # Testing documentation
│   ├── TESTING_GUIDE.md
│   ├── TEST_COVERAGE.md
│   └── TEST_SUMMARY.md          # Consolidated test summaries
├── security/                    # Security analysis and specs
│   ├── SECURITY_ANALYSIS_PDF_QA.md
│   ├── ENCRYPT_IMMEDIATELY_IMPLEMENTATION.md
│   ├── PRACTICAL_SECURE_WORKFLOW.md
│   ├── ENCRYPTED_TRAINING_WORKFLOW.md
│   └── SUPABASE_VAULT_ANALYSIS.md
├── gui/                         # GUI-specific docs
│   ├── GUI_CODE_REVIEW.md
│   └── GUI_IMPROVEMENTS_SUMMARY.md
├── business/                    # Business and product docs
│   ├── BUSINESS_MODEL.md
│   ├── REAL_WORLD_APPLICATIONS.md
│   └── PROGRESSIVE_ONBOARDING.md
└── guides/                      # Quick start and how-to guides
    ├── QUICK_START.md
    ├── POC_QUICKSTART.md
    └── GUIDE_INDEX.md
```

## Files to Consolidate

### Status Files (merge into docs/implementation/STATUS.md)
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_COMPLETE.md
- IMPLEMENTATION_SUMMARY.md
- STATUS_SUMMARY.md

### Next Steps Files (merge into docs/guides/NEXT_STEPS.md)
- NEXT_STEPS.md
- CORRECTED_NEXT_STEPS.md
- QUICK_START.md (keep as separate quick start)

### Test Files (merge into docs/testing/)
- TEST_SUMMARY_NEW_COMPONENTS.md
- TEST_VALIDATION_REPORT.md
- Keep TESTING_GUIDE.md and TEST_COVERAGE.md separate

### Backlog/Roadmap (keep in root)
- BACKLOG.md (keep in root - active development)
- ROADMAP.md (keep in root - high-level roadmap)

## Files to Archive or Remove

### Potentially Outdated
- architecture.md (lowercase - duplicate of ARCHITECTURE.md)
- POC_PLAN.md (if POC is complete, archive)
- POC_READINESS_REVIEW.md (if POC is complete, archive)
- BACKEND_API_TESTING.md (move to testing/ or remove if outdated)

## Action Plan

1. Create docs/ directory structure
2. Move files to appropriate locations
3. Consolidate duplicate status files
4. Create consolidated STATUS.md
5. Create docs/README.md as index
6. Update main README.md to point to docs/
7. Archive outdated POC files
8. Remove duplicate files

