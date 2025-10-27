# 🔐 Enclave GUI - Authenticated Vault Interface

Beautiful Material Design GUI for Enclave with multi-tenant authentication support.

## Features

### ✨ Authentication
- **OAuth Sign-In**: Google and GitHub OAuth integration
- **Email/Password**: Traditional email/password authentication
- **Session Management**: Secure local session storage
- **Auto-Login**: Persists sessions across app restarts
- **Logout**: Secure session clearing

### 🔒 Security
- **Supabase Auth**: Enterprise-grade authentication
- **Encrypted Storage**: ChaCha20-Poly1305 encryption for vault data
- **Zero-Knowledge**: Server never sees unencrypted vault contents
- **Token-Based**: JWT tokens for API authentication
- **Secure Sessions**: 0600 permissions on session files

### 💎 UI/UX
- **Material Design 3**: Modern, beautiful interface
- **Dark Theme**: Eye-friendly dark mode
- **Responsive**: Adapts to window size
- **RunPod Status**: Real-time connection monitoring
- **User Info**: Shows logged-in user email
- **Smooth Animations**: Professional transitions

## Quick Start

### 1. Install Dependencies

\`\`\`bash
cd advanced_vault/gui
pip3 install -r requirements.txt
\`\`\`

### 2. Set Environment Variables

\`\`\`bash
export SUPABASE_URL="https://ibiapabkyskoazpgcymo.supabase.co"
export SUPABASE_ANON_KEY="your_supabase_anon_key"
export ENCLAVE_BACKEND_URL="https://keen-curiosity-production-1288.up.railway.app"
\`\`\`

Or use the launch script (already configured):

\`\`\`bash
chmod +x ../../launch_enclave_gui.sh
../../launch_enclave_gui.sh
\`\`\`

### 3. Launch GUI

\`\`\`bash
python3 vault_app.py
\`\`\`

## Try It Now!

The easiest way to test:

\`\`\`bash
# From project root
./launch_enclave_gui.sh
\`\`\`

This script sets all environment variables and launches the GUI.

---

✅ **Backend deployed and ready!**
- Backend URL: `https://keen-curiosity-production-1288.up.railway.app`
- Health check: Passing
- Database: Connected

You can now:
1. Launch the GUI
2. Sign up with email/password (works immediately!)
3. Or configure OAuth for Google/GitHub sign-in (optional)
