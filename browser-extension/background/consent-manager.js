/**
 * Consent Manager
 * 
 * Manages consent decisions for AI agent access to secrets.
 */

import storageManager from './storage-manager.js';

const CONSENT_DECISIONS = {
  ALLOW_ONCE: 'allow_once',
  ALLOW_ALWAYS: 'allow_always',
  DENY: 'deny',
  DENY_ALWAYS: 'deny_always'
};

class ConsentManager {
  constructor() {
    this.pendingRequests = new Map();
  }

  /**
   * Request consent for secret access
   */
  async requestConsent(params) {
    const {
      agentIdentifier,
      service,
      toolName = 'vault_recall',
      queryPreview = ''
    } = params;

    // Check existing consent
    const existingConsent = await storageManager.getConsent(agentIdentifier, service);

    if (existingConsent) {
      if (existingConsent.decision === CONSENT_DECISIONS.ALLOW_ALWAYS) {
        return { granted: true, decision: 'allow_always' };
      }
      if (existingConsent.decision === CONSENT_DECISIONS.DENY_ALWAYS) {
        return { granted: false, decision: 'deny_always', reason: 'Permanently denied' };
      }
      if (existingConsent.decision === CONSENT_DECISIONS.ALLOW_ONCE) {
        // Check if expired
        if (existingConsent.expires_at && new Date(existingConsent.expires_at) < new Date()) {
          // Expired, need new consent
        } else {
          // Still valid, grant access
          return { granted: true, decision: 'allow_once' };
        }
      }
    }

    // Show consent popup
    const decision = await this.showConsentDialog({
      agentIdentifier,
      service,
      toolName,
      queryPreview
    });

    // Handle decision
    if (decision === CONSENT_DECISIONS.ALLOW_ONCE) {
      // Store one-time consent with expiration (1 hour)
      const expiresAt = new Date();
      expiresAt.setHours(expiresAt.getHours() + 1);

      await storageManager.saveConsent({
        id: crypto.randomUUID(),
        agent_identifier: agentIdentifier,
        service: service || null,
        decision: CONSENT_DECISIONS.ALLOW_ONCE,
        created_at: new Date().toISOString(),
        expires_at: expiresAt.toISOString()
      });

      return { granted: true, decision: 'allow_once' };
    }

    if (decision === CONSENT_DECISIONS.ALLOW_ALWAYS) {
      // Store permanent consent
      await storageManager.saveConsent({
        id: crypto.randomUUID(),
        agent_identifier: agentIdentifier,
        service: service || null,
        decision: CONSENT_DECISIONS.ALLOW_ALWAYS,
        created_at: new Date().toISOString(),
        expires_at: null
      });

      // Sync to backend (create policy)
      await this.syncConsentToBackend(agentIdentifier, service, CONSENT_DECISIONS.ALLOW_ALWAYS);

      return { granted: true, decision: 'allow_always' };
    }

    if (decision === CONSENT_DECISIONS.DENY_ALWAYS) {
      // Store permanent denial
      await storageManager.saveConsent({
        id: crypto.randomUUID(),
        agent_identifier: agentIdentifier,
        service: service || null,
        decision: CONSENT_DECISIONS.DENY_ALWAYS,
        created_at: new Date().toISOString(),
        expires_at: null
      });

      // Sync to backend (create deny policy)
      await this.syncConsentToBackend(agentIdentifier, service, CONSENT_DECISIONS.DENY_ALWAYS);

      return { granted: false, decision: 'deny_always', reason: 'Permanently denied by user' };
    }

    // DENY (one-time)
    return { granted: false, decision: 'deny', reason: 'Denied by user' };
  }

  /**
   * Show consent dialog popup
   */
  async showConsentDialog(params) {
    const {
      agentIdentifier,
      service,
      toolName,
      queryPreview
    } = params;

    return new Promise((resolve) => {
      const requestId = crypto.randomUUID();
      this.pendingRequests.set(requestId, resolve);

      // Create consent popup window
      const url = chrome.runtime.getURL(`consent/consent.html?` + new URLSearchParams({
        requestId,
        agentIdentifier: agentIdentifier || 'unknown',
        service: service || '',
        toolName: toolName || 'vault_recall',
        queryPreview: (queryPreview || '').substring(0, 100) // Limit length
      }));

      chrome.windows.create({
        url: url,
        type: 'popup',
        width: 450,
        height: 400,
        focused: true
      }, (window) => {
        if (chrome.runtime.lastError) {
          console.error('Failed to create consent window:', chrome.runtime.lastError);
          resolve('deny'); // Default to deny on error
          return;
        }
        
        // Store window ID for cleanup
        this.pendingRequests.set(requestId, {
          resolve,
          windowId: window.id
        });
      });
    });
  }

  /**
   * Handle consent decision from popup
   */
  handleConsentDecision(requestId, decision) {
    const pending = this.pendingRequests.get(requestId);
    if (pending) {
      // Close popup window if we have window ID
      if (pending.windowId) {
        chrome.windows.remove(pending.windowId).catch(() => {});
      }
      // Resolve promise
      if (typeof pending === 'function') {
        pending(decision);
      } else if (pending.resolve) {
        pending.resolve(decision);
      }
      this.pendingRequests.delete(requestId);
    }
  }

  /**
   * Sync consent to backend
   */
  async syncConsentToBackend(agentIdentifier, service, decision) {
    try {
      const { vaultClient } = await import('./vault-client.js');
      const consents = [{
        agent_identifier: agentIdentifier,
        service: service || null,
        decision
      }];
      await vaultClient.syncConsents(consents);
    } catch (error) {
      console.error('Failed to sync consent to backend:', error);
      // Don't fail the consent flow if sync fails
    }
  }

  /**
   * Get consent for agent and service
   */
  async getConsent(agentIdentifier, service = null) {
    return storageManager.getConsent(agentIdentifier, service);
  }

  /**
   * List all consents
   */
  async listConsents() {
    return storageManager.listConsents();
  }

  /**
   * Delete consent
   */
  async deleteConsent(id) {
    return storageManager.deleteConsent(id);
  }
}

// Export singleton instance
const consentManager = new ConsentManager();
export default consentManager;

