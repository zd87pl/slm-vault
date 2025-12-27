═══════════════════════════════════════════════════════════════
  Enclave MVP - Quick Start Guide
═══════════════════════════════════════════════════════════════

Thank you for testing Enclave! This guide will help you get started.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SYSTEM REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ macOS 10.13 or later
✓ Apple Silicon (M1/M2/M3) or Intel Mac
✓ 2GB free disk space
✓ Internet connection (for cloud sync)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  INSTALLATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPTION 1: Quick Launch (Recommended for Testing)
─────────────────────────────────────────────────

1. Extract this ZIP file
2. Double-click "Enclave.app"
3. If macOS shows a security warning:
   • Right-click "Enclave.app"
   • Select "Open"
   • Click "Open" in the security dialog

OPTION 2: Install to Applications Folder
─────────────────────────────────────────

1. Extract this ZIP file
2. Open Terminal
3. Navigate to the extracted folder:
   cd /path/to/Enclave-MVP-v0.1.0
4. Run the installer:
   ./install_enclave.sh
5. Launch from Applications folder or Spotlight

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FIRST LAUNCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Launch Enclave.app
2. Sign up or sign in with your email
3. Create a master password (keep this safe!)
4. Start using Enclave!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHAT IS ENCLAVE?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enclave is a secure encrypted vault for storing:
• Secrets (API keys, passwords, tokens)
• Knowledge (notes, documents, PDFs)
• Personal information

All data is encrypted locally before being synced to the cloud.
The server never sees your unencrypted data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  KEY FEATURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ End-to-end encryption (ChaCha20-Poly1305)
✓ Cloud sync across devices
✓ PDF processing and AI-powered Q&A generation
✓ Beautiful, modern interface
✓ No Python installation required (all bundled)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Problem: "Enclave.app is damaged and can't be opened"
Solution: Right-click the app → Select "Open" → Click "Open"
         This is normal for unsigned apps (MVP testing)

Problem: App won't start
Solution: 
  • Check macOS version: System Settings → General → About
  • Ensure you have 2GB+ free disk space
  • Try launching from Terminal to see error messages

Problem: Features not working
Solution:
  • Check internet connection (required for cloud sync)
  • Verify ~/.vault/ directory exists and is writable
  • Check Console.app for error messages

Problem: Can't sign in
Solution:
  • Verify internet connection
  • Check if backend is accessible
  • Try creating a new account

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DATA STORAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All data is stored locally at:
  ~/.vault/

This includes:
• Encrypted database: ~/.vault/vault.db
• Master key: ~/.vault/master.key (encrypted)
• Configuration: ~/.vault/config.json
• Temporary files: ~/.vault/temp_pdfs/

Your data is encrypted before syncing to the cloud.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  REPORTING ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you encounter issues, please provide:

1. macOS version (System Settings → General → About)
2. Mac model (Apple menu → About This Mac)
3. Steps to reproduce the issue
4. Error messages (if any)
5. Screenshots (if applicable)

Contact the development team with your feedback!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  NOTES FOR MVP TESTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• This is an MVP (Minimum Viable Product) release
• Some features may be incomplete or have bugs
• Your feedback is valuable for improving the product
• Data may be reset between versions (backup important data)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Thank you for testing Enclave!

═══════════════════════════════════════════════════════════════

