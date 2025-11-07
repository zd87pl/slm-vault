# API Key Detection Mechanism

## Overview

The browser extension provides a **non-invasive mechanism** to detect when API keys or secrets are being retrieved by AI agents or browsers. This helps users understand what's happening with their secrets without being intrusive.

## Detection Methods

### 1. Backend Access Logs (Primary)

**How it works:**
- All secret retrievals go through the backend API (`/api/langchain/secrets/retrieve`)
- Backend logs every access attempt in `access_logs` table
- Extension can query these logs to show activity

**Implementation:**
- Extension polls `/api/logs` endpoint periodically
- Shows recent activity in popup
- Highlights extension-originated requests

**Benefits:**
- Centralized logging
- Works for all access methods (MCP, LangChain, direct API)
- No browser-specific code needed

### 2. Extension Message Monitoring

**How it works:**
- Service worker logs all `get_secret` message requests
- Stores request metadata (agent, service, timestamp)
- Shows in extension popup's activity view

**Implementation:**
- In `service-worker.js`, log all secret requests:
  ```javascript
  case 'get_secret':
    // Log request
    await logSecretRequest(message.agentIdentifier, message.service);
    // ... handle request
  ```

**Benefits:**
- Real-time detection
- Works for extension-originated requests
- No backend dependency

### 3. Content Script Observation (Optional)

**How it works:**
- Content script observes network requests
- Detects API calls to known services (OpenAI, Anthropic, etc.)
- Shows notification: "API key used on openai.com"

**Implementation:**
- Use `chrome.webRequest` API (requires permission)
- Match against known API endpoints
- Show non-intrusive badge

**Benefits:**
- Detects usage even outside extension
- Helps users understand where keys are used
- Completely optional (user can disable)

## Recommended Approach: Hybrid

For the best user experience without being invasive:

1. **Backend Logs** (always on):
   - Query `/api/logs` every 30 seconds
   - Show in extension popup
   - Works for all access methods

2. **Extension Messages** (always on):
   - Log all extension-originated requests
   - Immediate feedback
   - No network delay

3. **Content Script** (opt-in):
   - User can enable in settings
   - Detects usage on websites
   - Shows subtle notifications

## Implementation

### Backend Log Query

```javascript
// In popup.js or service-worker.js
async function loadActivityLog() {
  try {
    const logs = await vaultClient.request('/api/logs', {
      limit: 20,
      client_type: 'extension'
    });
    
    // Display in popup
    displayActivityLog(logs);
  } catch (error) {
    console.error('Failed to load activity log:', error);
  }
}
```

### Extension Message Logging

```javascript
// In service-worker.js
async function handleGetSecret(message) {
  // Log request
  await storageManager.setSetting(
    `last_request_${Date.now()}`,
    {
      agent: message.agentIdentifier,
      service: message.service,
      timestamp: new Date().toISOString()
    }
  );
  
  // ... handle request
}
```

### Content Script Detection (Optional)

```javascript
// In content/content.js (if enabled)
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    // Check if request uses API key
    if (isApiKeyRequest(details)) {
      // Show subtle notification
      showUsageNotification(details.url);
    }
  },
  { urls: ["<all_urls>"] },
  ["requestBody"]
);
```

## User Experience

### Activity View in Popup

```
Recent Activity
─────────────────
🕐 2 minutes ago
  Agent: langchain-agent-1
  Service: openai
  Action: Retrieved secret
  Status: ✓ Allowed

🕐 15 minutes ago
  Agent: claude-desktop
  Service: github
  Action: Retrieved secret
  Status: ✓ Allowed (Always)
```

### Settings Option

- **"Show activity notifications"**: Enable/disable popup notifications
- **"Detect API key usage on websites"**: Enable content script detection
- **"Activity log retention"**: How long to keep logs (7/30/90 days)

## Privacy Considerations

1. **No Content Inspection**: Content script only observes network requests, doesn't read page content
2. **Opt-In Only**: Website detection is disabled by default
3. **Local Storage**: Activity logs stored locally, synced only if user enables
4. **Minimal Data**: Only metadata (service, timestamp), not actual secrets

## Future Enhancements

1. **Real-time WebSocket**: Push activity updates instead of polling
2. **Usage Analytics**: Aggregate statistics (how often keys used, by which agents)
3. **Alerts**: Notify on unusual patterns (e.g., key used from new location)
4. **Export**: Allow users to export activity logs

