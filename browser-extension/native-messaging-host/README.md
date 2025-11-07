# Native Messaging Host

This directory contains the native messaging host configuration for communicating between the MCP server and the browser extension.

## Setup

### macOS

1. Copy `com.enclave.vault.json` to:
   ```
   ~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.enclave.vault.json
   ```

2. Update the `path` in the JSON file to point to the actual host executable

3. Update `allowed_origins` with your extension ID (get it from `chrome://extensions/`)

### Linux

1. Copy `com.enclave.vault.json` to:
   ```
   ~/.config/google-chrome/NativeMessagingHosts/com.enclave.vault.json
   ```

2. Update paths as above

### Windows

1. Create registry entry:
   ```
   HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.enclave.vault
   ```
   Value: Path to `com.enclave.vault.json`

2. Update paths in JSON file

## Host Executable

The native messaging host executable should:
- Read JSON-RPC messages from stdin
- Forward messages to extension via `chrome.runtime.sendNativeMessage`
- Return responses to MCP server

For POC, this can be a simple Python script or Node.js executable.

## Future Implementation

A native messaging host executable will be created to bridge MCP server and extension for seamless communication.

