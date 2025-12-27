# Native Messaging Host

This directory contains the native messaging host configuration for communicating between the MCP server and the browser extension.

## Overview

Native messaging allows the MCP server (running as a native application) to communicate with the browser extension. This enables the MCP server to request consent from the extension when AI agents try to access secrets.

## Current Status: POC Implementation

For the POC, we're using `chrome.runtime.onMessageExternal` and `chrome.runtime.sendMessage` for communication. A full native messaging host will be implemented in a future update.

## Setup (Future Implementation)

### macOS

1. **Copy native messaging host manifest**:
   ```bash
   cp com.enclave.vault.json ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.enclave.vault.json
   ```

2. **Update the manifest**:
   - Set `path` to the full path of `enclave-native-host.py` (or compiled executable)
   - Set `allowed_origins` to include your extension ID (get it from `chrome://extensions/`)

3. **Make host executable**:
   ```bash
   chmod +x enclave-native-host.py
   ```

### Linux

1. **Copy native messaging host manifest**:
   ```bash
   mkdir -p ~/.config/google-chrome/NativeMessagingHosts
   cp com.enclave.vault.json ~/.config/google-chrome/NativeMessagingHosts/com.enclave.vault.json
   ```

2. **Update paths as above**

### Windows

1. **Create registry entry**:
   ```
   HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.enclave.vault
   ```
   Value: Full path to `com.enclave.vault.json`

2. **Update paths in JSON file**

## Host Executable

The native messaging host (`enclave-native-host.py`) should:

- Read JSON-RPC messages from stdin (from MCP server)
- Forward messages to extension via native messaging API
- Return responses to MCP server via stdout

### Message Format

**Request from MCP server**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "consent_request",
  "params": {
    "agentIdentifier": "mcp-server",
    "service": "openai",
    "toolName": "vault_recall",
    "queryPreview": "Retrieve OpenAI API key"
  }
}
```

**Response to MCP server**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "granted": true,
    "decision": "allow_once"
  }
}
```

## Current POC Implementation

For now, the extension uses `chrome.runtime.onMessageExternal` to receive messages. The MCP server can check if the extension is available and request consent.

**Extension side** (`background/extension-server.js`):
- Listens for external messages
- Handles consent requests
- Returns consent decisions

**MCP server side** (`advanced_vault/mcp_server/consent.py`):
- Checks if extension is available
- Sends consent request via native messaging (or HTTP for POC)
- Receives consent decision

## Testing

1. **Load extension** in Chrome/Comet
2. **Get extension ID** from `chrome://extensions/`
3. **Update native messaging host manifest** with extension ID
4. **Install native messaging host** (copy JSON file)
5. **Test communication**:
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"consent_request","params":{"agentIdentifier":"test","service":"openai"}}' | python3 enclave-native-host.py
   ```

## Future Improvements

- [ ] Full native messaging host implementation
- [ ] Binary protocol for better performance
- [ ] Automatic extension ID detection
- [ ] Cross-platform installation scripts
- [ ] Error handling and reconnection logic

## Troubleshooting

### Extension not receiving messages
- Check extension ID matches in manifest
- Verify native messaging host is installed correctly
- Check Chrome logs: `chrome://extensions/` → Developer mode → Errors

### Native messaging host not found
- Verify JSON file is in correct location
- Check file permissions (should be readable)
- Restart Chrome after installing host

### Permission denied
- Ensure host executable has execute permissions
- Check Python path is correct in manifest
