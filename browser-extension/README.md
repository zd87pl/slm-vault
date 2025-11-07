# Enclave Browser Extension

Browser extension for Chromium browsers (Chrome, Comet, OpenAI Atlas) that enables secure API key storage with consent-based access for AI agents.

## Features

- **Secure Storage**: Client-side encryption of API keys using WebCrypto API
- **Cloud Sync**: Automatic sync with Enclave backend vault
- **Consent Management**: Four-button consent system (Allow, Deny, Allow Always, Deny Always)
- **MCP Integration**: Works seamlessly with MCP server for AI agent access
- **Auto-Detection**: Non-invasive detection of API keys in form inputs
- **Zero-Knowledge**: Master key never leaves the extension

## Installation

### Development

1. Clone the repository
2. Open Chrome/Comet and navigate to `chrome://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked"
5. Select the `browser-extension/` directory

### Production

1. Build the extension (when ready)
2. Submit to Chrome Web Store / Comet extension store

## Setup

### First Time Setup

1. **Set Master Password**: 
   - Open extension popup
   - Go to Settings
   - Set your master password (used to encrypt/decrypt secrets)

2. **Authenticate with Backend**:
   - Extension will prompt for login
   - Enter your Enclave credentials
   - Tokens are stored securely in extension storage

3. **Add Your First Secret**:
   - Click "Add Secret" in popup
   - Enter service name (e.g., "openai")
   - Enter API key
   - Add tags (optional)
   - Click "Save"

## Usage

### Adding Secrets

1. Click extension icon
2. Click "Add Secret"
3. Fill in service name and secret
4. Click "Save"

### Managing Consents

When an AI agent requests access to a secret:

1. Consent popup appears automatically
2. Choose one of four options:
   - **Allow**: One-time access
   - **Deny**: One-time denial
   - **Allow Always**: Auto-approve future requests
   - **Deny Always**: Permanently block future requests

### Syncing

- Secrets sync automatically when added/edited
- Click "Sync" button to manually sync
- Sync status shown in header

## Architecture

### Components

- **Service Worker** (`background/service-worker.js`): Main orchestration, handles messages
- **Storage Manager** (`background/storage-manager.js`): IndexedDB operations
- **Vault Client** (`background/vault-client.js`): Backend API communication
- **Consent Manager** (`background/consent-manager.js`): Consent decision management
- **Crypto Manager** (`background/crypto-manager.js`): Client-side encryption
- **Popup UI** (`popup/`): User interface for managing secrets
- **Consent UI** (`consent/`): Consent dialog popup
- **Content Script** (`content/content.js`): Optional API key detection

### Data Flow

1. **Secret Storage**: User adds secret → Encrypted locally → Synced to backend
2. **Secret Request**: Agent requests → Check consent → Show popup if needed → Return encrypted secret
3. **Consent Sync**: User decision → Stored locally → Synced to backend policies

## MCP Integration

The extension integrates with the MCP server via:

1. **Native Messaging** (preferred): Direct communication via Chrome native messaging
2. **Local HTTP Server** (fallback): Extension starts local server, MCP connects

### Setup MCP Integration

1. Install extension
2. MCP server detects extension availability
3. Consent requests route through extension instead of OS notifications
4. User sees extension popup instead of system dialog

## Security

- **Master Key**: Derived from password using PBKDF2 (100,000 iterations)
- **Encryption**: AES-GCM with 256-bit keys
- **Storage**: Encrypted secrets stored in IndexedDB
- **Sync**: Only encrypted data sent to backend
- **Permissions**: Minimal extension permissions

## Development

### Building

```bash
cd browser-extension
# No build step needed for development - load unpacked in Chrome
```

### Testing

1. Load extension in Chrome
2. Test secret storage/retrieval
3. Test consent flow
4. Test MCP integration

## Troubleshooting

### "Master password not set"
- Go to Settings and set master password

### "Authentication failed"
- Check backend URL in settings
- Verify credentials are correct
- Check network connection

### "Sync failed"
- Check backend connectivity
- Verify authentication tokens
- Check browser console for errors

## Next Steps

- [ ] Add icon assets
- [ ] Implement native messaging host
- [ ] Add settings page
- [ ] Improve error handling
- [ ] Add unit tests
- [ ] Submit to extension stores

