# Browser Extension + MCP Architecture

**Project:** Personal AI Vault Browser Extension
**Integration:** DoRA WDVA + Model Context Protocol (MCP)
**Date:** 2025-01-25

---

## Executive Summary

A browser extension that stores encrypted personal AI adapters locally and uses the Model Context Protocol (MCP) for consent-based access to AI capabilities. This creates a "Personal AI Vault" where users maintain full control over their AI personas.

**Key Innovation:** Zero-knowledge AI personalization with explicit consent management.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Browser Extension (Client)                   │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Adapter Storage (IndexedDB)                               │ │
│  │  - work-email-style.enc (2.1MB)                           │ │
│  │  - creative-writing.enc (3.4MB)                           │ │
│  │  - technical-docs.enc (1.8MB)                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Key Management (WebCrypto API)                            │ │
│  │  - Master key (PBKDF2 from user password)                │ │
│  │  - Adapter keys (HKDF derived)                           │ │
│  │  - Session keys (ephemeral)                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  MCP Consent Manager                                        │ │
│  │  - Consent UI                                              │ │
│  │  - Policy enforcement                                      │ │
│  │  - Session tracking                                        │ │
│  │  - Audit logging                                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  API Client                                                 │ │
│  │  - HTTPS transport                                         │ │
│  │  - Request signing                                         │ │
│  │  - Error handling                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTPS + TLS 1.3
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│                      WDVA Backend (Server)                        │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  API Gateway                                                │ │
│  │  - Rate limiting (100 req/min per user)                   │ │
│  │  - Authentication (JWT)                                    │ │
│  │  - Request validation                                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Ephemeral Inference Engine                                │ │
│  │  - Decrypt adapter (in-memory)                            │ │
│  │  - Load into base model                                   │ │
│  │  - Run inference                                          │ │
│  │  - Clean up (zero memory)                                 │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Adapter Cache (LRU, 10 adapters)                         │ │
│  │  - Hot adapters stay loaded                               │ │
│  │  - Sub-5ms switching                                      │ │
│  │  - Memory-aware eviction                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Browser Extension

#### Manifest V3 Configuration

```json
{
  "manifest_version": 3,
  "name": "Personal AI Vault",
  "version": "1.0.0",
  "description": "Your personal AI adapters with consent-based access",

  "permissions": [
    "storage",
    "activeTab",
    "contextMenus",
    "scripting"
  ],

  "host_permissions": [
    "https://api.personalai.vault/*"
  ],

  "background": {
    "service_worker": "background.js",
    "type": "module"
  },

  "content_scripts": [{
    "matches": ["<all_urls>"],
    "js": ["content.js"],
    "css": ["content.css"]
  }],

  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "48": "icons/icon-48.png",
      "128": "icons/icon-128.png"
    }
  }
}
```

#### Core Modules

**adapter_manager.js:**
```javascript
export class AdapterManager {
  constructor() {
    this.db = null;
    this.initDB();
  }

  async initDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('PersonalAIVault', 1);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Adapters store
        const adapterStore = db.createObjectStore('adapters', {
          keyPath: 'id'
        });
        adapterStore.createIndex('name', 'name', { unique: true });

        // Consent store
        const consentStore = db.createObjectStore('consents', {
          keyPath: 'id'
        });
        consentStore.createIndex('origin_adapter', ['origin', 'adapterId']);
      };
    });
  }

  async saveAdapter(name, encryptedData, metadata) {
    const adapter = {
      id: crypto.randomUUID(),
      name: name,
      encrypted: encryptedData,
      metadata: {
        ...metadata,
        created: Date.now(),
        size: encryptedData.byteLength
      }
    };

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction(['adapters'], 'readwrite');
      const request = tx.objectStore('adapters').add(adapter);

      request.onsuccess = () => resolve(adapter.id);
      request.onerror = () => reject(request.error);
    });
  }

  async getAdapter(adapterId) {
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction(['adapters'], 'readonly');
      const request = tx.objectStore('adapters').get(adapterId);

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async listAdapters() {
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction(['adapters'], 'readonly');
      const request = tx.objectStore('adapters').getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}
```

**mcp_consent.js:**
```javascript
export class MCPConsentManager {
  constructor() {
    this.activeConsents = new Map();
  }

  async requestConsent(params) {
    const { origin, adapterId, action, durationMinutes = 60 } = params;

    // Check if valid consent already exists
    const existingConsent = this.getActiveConsent(origin, adapterId);
    if (existingConsent && existingConsent.expiry > Date.now()) {
      return true;
    }

    // Show consent UI
    const approved = await this.showConsentDialog(params);

    if (approved) {
      // Store consent
      const consent = {
        id: crypto.randomUUID(),
        origin: origin,
        adapterId: adapterId,
        action: action,
        granted: Date.now(),
        expiry: Date.now() + (durationMinutes * 60 * 1000)
      };

      this.activeConsents.set(`${origin}:${adapterId}`, consent);

      // Persist to storage
      await this.saveConsent(consent);

      return true;
    }

    return false;
  }

  async showConsentDialog(params) {
    return new Promise((resolve) => {
      // Create consent popup
      chrome.windows.create({
        url: chrome.runtime.getURL(`consent.html?${new URLSearchParams(params)}`),
        type: 'popup',
        width: 450,
        height: 350,
        focused: true
      }, (window) => {
        // Listen for user decision
        const listener = (msg, sender) => {
          if (msg.type === 'consent_decision' && sender.tab.windowId === window.id) {
            chrome.runtime.onMessage.removeListener(listener);
            chrome.windows.remove(window.id);
            resolve(msg.approved);
          }
        };

        chrome.runtime.onMessage.addListener(listener);
      });
    });
  }

  getActiveConsent(origin, adapterId) {
    return this.activeConsents.get(`${origin}:${adapterId}`);
  }

  async revokeConsent(origin, adapterId) {
    this.activeConsents.delete(`${origin}:${adapterId}`);
    // Delete from storage
    await this.deleteConsent(origin, adapterId);
  }

  async saveConsent(consent) {
    // Save to IndexedDB for persistence across sessions
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(['consents'], 'readwrite');
      const request = tx.objectStore('consents').add(consent);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }
}
```

**crypto_manager.js:**
```javascript
export class CryptoManager {
  async deriveKey(password, salt) {
    // Convert password to key material
    const passwordKey = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(password),
      'PBKDF2',
      false,
      ['deriveKey']
    );

    // Derive master key with PBKDF2
    return await crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt,
        iterations: 100000,
        hash: 'SHA-256'
      },
      passwordKey,
      { name: 'AES-GCM', length: 256 },
      true,
      ['encrypt', 'decrypt']
    );
  }

  async deriveAdapterKey(masterKey, adapterId) {
    // Use HKDF to derive adapter-specific key
    const masterKeyBytes = await crypto.subtle.exportKey('raw', masterKey);
    const info = new TextEncoder().encode(`adapter:${adapterId}`);

    // Simple HKDF implementation
    const hkdf = await crypto.subtle.importKey(
      'raw',
      masterKeyBytes,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );

    const prk = await crypto.subtle.sign('HMAC', hkdf, info);
    return await crypto.subtle.importKey(
      'raw',
      prk.slice(0, 32),
      { name: 'AES-GCM', length: 256 },
      true,
      ['encrypt', 'decrypt']
    );
  }

  async encryptAdapter(adapterData, key) {
    const iv = crypto.getRandomValues(new Uint8Array(12));

    const encrypted = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: iv },
      key,
      adapterData
    );

    // Combine IV + encrypted data
    const combined = new Uint8Array(iv.length + encrypted.byteLength);
    combined.set(iv, 0);
    combined.set(new Uint8Array(encrypted), iv.length);

    return combined;
  }

  async decryptAdapter(encryptedData, key) {
    // Extract IV
    const iv = encryptedData.slice(0, 12);
    const ciphertext = encryptedData.slice(12);

    return await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: iv },
      key,
      ciphertext
    );
  }
}
```

**api_client.js:**
```javascript
export class APIClient {
  constructor(baseURL) {
    this.baseURL = baseURL;
    this.jwt = null;
  }

  async authenticate(userId, apiKey) {
    const response = await fetch(`${this.baseURL}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, apiKey })
    });

    const data = await response.json();
    this.jwt = data.token;
    return this.jwt;
  }

  async inference(encryptedAdapter, sessionKey, prompt, maxTokens = 256) {
    const response = await fetch(`${this.baseURL}/v1/inference`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.jwt}`
      },
      body: JSON.stringify({
        encrypted_adapter: Array.from(encryptedAdapter),
        encryption_key: Array.from(sessionKey),
        prompt: prompt,
        max_tokens: maxTokens
      })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return await response.json();
  }
}
```

### 2. MCP Integration

#### Consent UI (consent.html)

```html
<!DOCTYPE html>
<html>
<head>
  <title>AI Consent Request</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen;
      padding: 20px;
      margin: 0;
      background: #f5f5f5;
    }
    .consent-card {
      background: white;
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .origin {
      color: #0066cc;
      font-weight: 600;
      margin-bottom: 16px;
    }
    .adapter-info {
      background: #f0f7ff;
      border-left: 3px solid #0066cc;
      padding: 12px;
      margin: 16px 0;
    }
    .actions {
      display: flex;
      gap: 12px;
      margin-top: 24px;
    }
    button {
      flex: 1;
      padding: 12px;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
    .approve {
      background: #0066cc;
      color: white;
    }
    .deny {
      background: #e5e5e5;
      color: #333;
    }
  </style>
</head>
<body>
  <div class="consent-card">
    <h2>🔐 AI Access Request</h2>

    <div class="origin">
      From: <span id="origin"></span>
    </div>

    <div class="adapter-info">
      <strong>Adapter:</strong> <span id="adapter-name"></span><br>
      <strong>Action:</strong> <span id="action"></span><br>
      <strong>Duration:</strong> <span id="duration"></span>
    </div>

    <div class="actions">
      <button class="deny" id="deny-btn">Deny</button>
      <button class="approve" id="approve-btn">Approve</button>
    </div>
  </div>

  <script src="consent.js"></script>
</body>
</html>
```

#### Consent Logic (consent.js)

```javascript
// Parse URL parameters
const params = new URLSearchParams(window.location.search);
const origin = params.get('origin');
const adapterId = params.get('adapterId');
const action = params.get('action');
const duration = params.get('durationMinutes') || 60;

// Populate UI
document.getElementById('origin').textContent = origin;
document.getElementById('adapter-name').textContent = adapterId;
document.getElementById('action').textContent = action;
document.getElementById('duration').textContent = `${duration} minutes`;

// Handle user decision
document.getElementById('approve-btn').onclick = () => {
  chrome.runtime.sendMessage({
    type: 'consent_decision',
    approved: true,
    origin: origin,
    adapterId: adapterId
  });
};

document.getElementById('deny-btn').onclick = () => {
  chrome.runtime.sendMessage({
    type: 'consent_decision',
    approved: false
  });
};
```

### 3. Content Script Integration

**content.js:**
```javascript
// Add AI Assist button to text inputs
function augmentTextInputs() {
  const textAreas = document.querySelectorAll('textarea, [contenteditable="true"]');

  textAreas.forEach(el => {
    if (el.dataset.aiAugmented) return; // Already augmented

    // Create AI button
    const button = document.createElement('button');
    button.className = 'personal-ai-assist-btn';
    button.textContent = '✨ AI Assist';
    button.style.cssText = `
      position: absolute;
      top: 8px;
      right: 8px;
      padding: 6px 12px;
      background: #0066cc;
      color: white;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      z-index: 9999;
    `;

    // Position button
    const parent = el.parentElement;
    parent.style.position = 'relative';
    parent.appendChild(button);

    // Handle click
    button.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const prompt = el.value || el.textContent;
      if (!prompt.trim()) {
        alert('Please enter some text first');
        return;
      }

      button.textContent = '⏳ Generating...';
      button.disabled = true;

      try {
        // Request AI assistance from background script
        const response = await chrome.runtime.sendMessage({
          type: 'ai_assist',
          prompt: prompt,
          origin: window.location.origin
        });

        if (response.error) {
          alert(`Error: ${response.error}`);
        } else {
          // Show suggestion
          showSuggestion(el, response.text);
        }
      } catch (error) {
        alert(`Error: ${error.message}`);
      } finally {
        button.textContent = '✨ AI Assist';
        button.disabled = false;
      }
    };

    el.dataset.aiAugmented = 'true';
  });
}

function showSuggestion(element, suggestion) {
  // Create suggestion overlay
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position: absolute;
    background: white;
    border: 2px solid #0066cc;
    border-radius: 8px;
    padding: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    max-width: 400px;
    z-index: 10000;
  `;

  overlay.innerHTML = `
    <div style="margin-bottom: 12px;">
      <strong>AI Suggestion:</strong>
    </div>
    <div style="margin-bottom: 16px; color: #333;">
      ${suggestion}
    </div>
    <div style="display: flex; gap: 8px;">
      <button class="accept-btn" style="padding: 8px 16px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer;">
        Accept
      </button>
      <button class="reject-btn" style="padding: 8px 16px; background: #e5e5e5; color: #333; border: none; border-radius: 4px; cursor: pointer;">
        Reject
      </button>
    </div>
  `;

  document.body.appendChild(overlay);

  // Position overlay
  const rect = element.getBoundingClientRect();
  overlay.style.top = `${rect.bottom + window.scrollY + 8}px`;
  overlay.style.left = `${rect.left + window.scrollX}px`;

  // Handle accept
  overlay.querySelector('.accept-btn').onclick = () => {
    if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
      element.value = suggestion;
    } else {
      element.textContent = suggestion;
    }
    overlay.remove();
  };

  // Handle reject
  overlay.querySelector('.reject-btn').onclick = () => {
    overlay.remove();
  };
}

// Initialize
augmentTextInputs();

// Watch for dynamically added elements
const observer = new MutationObserver(() => {
  augmentTextInputs();
});

observer.observe(document.body, {
  childList: true,
  subtree: true
});
```

---

## Security Considerations

### Key Management

**Master Key Derivation:**
```
User Password (UTF-8 string)
  ↓
PBKDF2 (100,000 iterations, SHA-256)
  ↓
Master Key (256-bit AES-GCM key)
  ↓
HKDF (per-adapter derivation)
  ↓
Adapter Keys (256-bit AES-GCM keys)
```

**Session Key Flow:**
```
Adapter Key (browser)
  ↓
One-time derivation with nonce
  ↓
Session Key (sent to backend)
  ↓
Backend decrypts adapter
  ↓
Inference
  ↓
Session key destroyed
```

### Threat Model

| Threat | Mitigation |
|--------|------------|
| **Malicious Website** | MCP consent required per origin |
| **XSS Attack** | Content Security Policy, isolated storage |
| **Network Eavesdropping** | TLS 1.3 encryption |
| **Backend Compromise** | Zero-knowledge (backend never has master key) |
| **Extension Compromise** | Code signing, auto-updates, permissions model |
| **User Device Theft** | Master key encrypted with password |

---

## Implementation Timeline

**Phase 1: Core Extension (4 weeks)**
- Week 1: Extension scaffolding, IndexedDB setup
- Week 2: Crypto module, key management
- Week 3: MCP consent UI
- Week 4: Testing, bug fixes

**Phase 2: Backend Integration (2 weeks)**
- Week 5: API client, authentication
- Week 6: End-to-end testing

**Phase 3: Beta Launch (2 weeks)**
- Week 7: Documentation, onboarding
- Week 8: Beta user testing, feedback

**Total: 8 weeks to MVP**

---

## Conclusion

This architecture provides:
- ✅ **User Privacy**: Zero-knowledge design
- ✅ **Explicit Consent**: MCP integration
- ✅ **Security**: Defense-in-depth
- ✅ **Performance**: Sub-5ms adapter switching
- ✅ **Scalability**: Supports thousands of users
- ✅ **User Experience**: Seamless browser integration

**Next Steps:**
1. Prototype consent UI
2. Test crypto module
3. Build proof-of-concept
4. User testing with 10 beta users

---

Generated: 2025-01-25
