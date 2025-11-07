# Browser Extension Setup Guide

## Overview

The Enclave browser extension enables secure API key storage with consent-based access for AI agents. It integrates with the MCP server to provide a seamless consent experience.

## Installation

### Development Installation

1. **Clone the repository** (if not already done)
2. **Open Chrome/Comet**:
   - Navigate to `chrome://extensions/` (or `comet://extensions/`)
   - Enable "Developer mode" (toggle in top-right)
3. **Load Extension**:
   - Click "Load unpacked"
   - Select the `browser-extension/` directory
4. **Verify Installation**:
   - Extension icon should appear in toolbar
   - Click icon to open popup

### Production Installation

1. Extension will be available in Chrome Web Store / Comet extension store
2. Install like any other extension
3. Follow first-time setup below

## First-Time Setup

### 1. Set Master Password

1. Click extension icon
2. Click "Settings" (or extension will prompt on first use)
3. Enter a strong master password
4. This password encrypts all secrets locally
5. **Important**: Don't lose this password - secrets cannot be recovered without it

### 2. Authenticate with Backend

1. Extension will prompt for Enclave login
2. Enter your email and password
3. Tokens are stored securely in extension storage
4. Extension will auto-refresh tokens when needed

### 3. Add Your First Secret

1. Click "Add Secret" in popup
2. Enter:
   - **Service**: e.g., "openai", "github", "stripe"
   - **Secret**: Your API key or password
   - **Tags**: Optional (e.g., "production", "api-key")
   - **Description**: Optional
3. Click "Save"
4. Secret is encrypted and synced to cloud vault

## Usage

### Managing Secrets

- **View Secrets**: Click extension icon to see list
- **Add Secret**: Click "Add Secret" button
- **Copy Secret**: Click 📋 icon on secret item
- **Delete Secret**: Click 🗑 icon on secret item
- **Sync**: Click "Sync" button to sync with cloud

### Consent Management

When an AI agent (via MCP) requests access to a secret:

1. **Consent popup appears automatically**
2. **Choose one of four options**:
   - **Allow**: Grant one-time access (expires after use)
   - **Deny**: Deny this request (no storage)
   - **Allow Always**: Auto-approve all future requests from this agent
   - **Deny Always**: Permanently block this agent

3. **Decision is stored**:
   - Locally in extension storage
   - Synced to backend (for "Always" decisions)
   - Applied to future requests automatically

### Auto-Detection

The extension can detect API keys in form inputs:

- When you type an API key in a password field
- Extension shows a small badge: "💡 Save to Enclave?"
- Click "Save" to quickly add to vault
- Non-invasive - only observes, doesn't interfere

## MCP Integration

### How It Works

1. **MCP Server** detects extension availability
2. **Consent requests** route through extension instead of OS notifications
3. **Extension shows popup** with four-button consent UI
4. **User decision** is stored and synced

### Setup MCP Integration

1. **Install extension** (see Installation above)
2. **Start MCP server** (if not already running):
   ```bash
   python -m advanced_vault.mcp_server
   ```
3. **MCP server automatically detects extension**:
   - Tries to connect to extension's local HTTP server (port 8765)
   - Falls back to OS notifications if extension not available

### Testing MCP Integration

1. **Start MCP server**
2. **Use Claude Desktop or Cursor** with MCP configured
3. **Ask AI agent to access vault**: "Get my OpenAI API key"
4. **Extension popup should appear** (instead of OS notification)
5. **Choose consent decision**
6. **Agent receives encrypted secret**

## Architecture

### Communication Flow

```
MCP Server → Extension HTTP Server (localhost:8765) → Consent Manager → Popup UI → User Decision → Backend Sync
```

### Components

- **Service Worker**: Background orchestration
- **Storage Manager**: IndexedDB for local storage
- **Vault Client**: Backend API communication
- **Consent Manager**: Consent decision logic
- **Crypto Manager**: Client-side encryption
- **Extension Server**: Local HTTP server for MCP communication

## Security

### Encryption

- **Master Key**: Derived from password (PBKDF2, 100,000 iterations)
- **Secrets**: Encrypted with AES-GCM before storage
- **Master Key**: Never stored, only derived when needed
- **Zero-Knowledge**: Backend never sees plaintext secrets

### Permissions

Extension requests minimal permissions:
- `storage`: For local data storage
- `activeTab`: For content script access
- `nativeMessaging`: For MCP communication (future)
- `host_permissions`: Only for Enclave backend API

### Best Practices

1. **Use Strong Master Password**: At least 16 characters, mix of characters
2. **Don't Share Master Password**: It decrypts all your secrets
3. **Review Consents Regularly**: Check "Allow Always" decisions
4. **Keep Extension Updated**: Security updates are important

## Troubleshooting

### Extension Not Loading

- Check browser console for errors (`chrome://extensions/` → "Errors")
- Verify `manifest.json` is valid JSON
- Check that all files exist

### "Master password not set"

- Go to Settings (or extension will prompt)
- Set master password
- Password is stored locally only

### "Authentication failed"

- Check backend URL in settings (default: production URL)
- Verify credentials are correct
- Check network connectivity
- Try logging out and back in

### "Sync failed"

- Check backend connectivity
- Verify authentication tokens are valid
- Check browser console for errors
- Try manual sync button

### Consent Popup Not Appearing

- Verify MCP server is running
- Check extension server is running (port 8765)
- Check browser console for errors
- Try restarting extension

### MCP Server Can't Connect to Extension

- Verify extension is installed and enabled
- Check extension server started (should log on extension load)
- Try restarting browser
- Check firewall isn't blocking localhost:8765

## Development

### File Structure

```
browser-extension/
├── manifest.json
├── background/
│   ├── service-worker.js
│   ├── storage-manager.js
│   ├── vault-client.js
│   ├── consent-manager.js
│   ├── crypto-manager.js
│   └── extension-server.js
├── popup/
│   ├── popup.html
│   ├── popup.js
│   └── popup.css
├── consent/
│   ├── consent.html
│   ├── consent.js
│   └── consent.css
├── content/
│   └── content.js
└── icons/
    └── (icon files)
```

### Testing

1. **Load extension** in Chrome (Developer mode)
2. **Open popup** and test secret management
3. **Test consent flow** by triggering MCP request
4. **Check browser console** for errors
5. **Verify sync** with backend

### Debugging

- **Service Worker**: `chrome://extensions/` → Extension → "Service worker" link
- **Popup**: Right-click popup → Inspect
- **Content Script**: Browser DevTools → Console
- **Storage**: DevTools → Application → IndexedDB → EnclaveVault

## Next Steps

- [ ] Create icon assets
- [ ] Add settings page UI
- [ ] Implement native messaging host (alternative to HTTP server)
- [ ] Add unit tests
- [ ] Improve error handling
- [ ] Add analytics (privacy-preserving)
- [ ] Submit to extension stores

## Support

- **Issues**: GitHub Issues
- **Documentation**: See `browser-extension/README.md`
- **MCP Integration**: See `docs/MCP_INTEGRATION_PLAN.md`

