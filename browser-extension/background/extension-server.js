/**
 * Extension Server for MCP Communication
 * 
 * Handles communication between MCP server and extension.
 * 
 * For POC, we use message passing via chrome.runtime.sendMessage.
 * MCP server can check extension availability and request consent.
 * 
 * Future: Can implement native messaging host for direct communication.
 */

import consentManager from './consent-manager.js';

class ExtensionServer {
  constructor() {
    this.isRunning = false;
  }

  /**
   * Initialize extension server
   * Sets up message listeners for MCP communication
   */
  async init() {
    if (this.isRunning) return;

    // Listen for messages from external sources (MCP server via native messaging host)
    chrome.runtime.onMessageExternal?.addListener((message, sender, sendResponse) => {
      this.handleExternalMessage(message, sender, sendResponse);
      return true; // Keep channel open for async response
    });

    // Also listen for internal messages (for testing)
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message.type === 'mcp_consent_request') {
        this.handleConsentRequest(message, sendResponse);
        return true;
      }
    });

    this.isRunning = true;
    console.log('Extension server initialized');
  }

  /**
   * Handle external message (from MCP server)
   */
  async handleExternalMessage(message, sender, sendResponse) {
    try {
      if (message.type === 'consent_request') {
        const result = await this.handleConsentRequest(message, sendResponse);
        return result;
      } else if (message.type === 'ping') {
        sendResponse({ status: 'ok', extension_id: chrome.runtime.id });
        return true;
      }
    } catch (error) {
      console.error('Error handling external message:', error);
      sendResponse({ error: error.message });
      return false;
    }
  }

  /**
   * Handle consent request from MCP server
   */
  async handleConsentRequest(message, sendResponse) {
    const { agentIdentifier, service, toolName, queryPreview } = message;

    try {
      // Request consent via consent manager
      const result = await consentManager.requestConsent({
        agentIdentifier: agentIdentifier || 'mcp-server',
        service: service || null,
        toolName: toolName || 'vault_recall',
        queryPreview: queryPreview || ''
      });

      // Map result to response
      const response = {
        granted: result.granted,
        decision: result.decision || (result.granted ? 'allow_once' : 'deny')
      };

      if (sendResponse) {
        sendResponse(response);
      }

      return response;
    } catch (error) {
      console.error('Error handling consent request:', error);
      const errorResponse = {
        granted: false,
        decision: 'deny',
        error: error.message
      };
      if (sendResponse) {
        sendResponse(errorResponse);
      }
      return errorResponse;
    }
  }

  /**
   * Check if extension is available (for MCP server)
   * This is called by native messaging host
   */
  async checkAvailability() {
    return {
      available: true,
      extension_id: chrome.runtime.id,
      version: chrome.runtime.getManifest().version
    };
  }
}

// Initialize server when module loads
const extensionServer = new ExtensionServer();
extensionServer.init().catch(error => {
  console.error('Failed to initialize extension server:', error);
});

export default extensionServer;

