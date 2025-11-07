/**
 * Service Worker - Main Orchestration
 * 
 * Handles message routing, consent requests, and MCP integration.
 */

import storageManager from './storage-manager.js';
import vaultClient from './vault-client.js';
import consentManager from './consent-manager.js';
import extensionServer from './extension-server.js';
import activityMonitor from './activity-monitor.js';

// Initialize storage on startup
chrome.runtime.onInstalled.addListener(async () => {
  await storageManager.init();
  console.log('Enclave extension installed');
});

// Handle messages from popup, content scripts, and consent dialogs
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true; // Keep channel open for async response
});

async function handleMessage(message, sender, sendResponse) {
  try {
    switch (message.type) {
      case 'consent_decision':
        // Handle consent decision from popup
        consentManager.handleConsentDecision(message.requestId, message.decision);
        sendResponse({ success: true });
        break;

      case 'mcp_consent_request':
        // Handle consent request from MCP server (via native messaging or external message)
        const consentResult = await consentManager.requestConsent({
          agentIdentifier: message.agentIdentifier || 'mcp-server',
          service: message.service || null,
          toolName: message.toolName || 'vault_recall',
          queryPreview: message.queryPreview || ''
        });
        sendResponse(consentResult);
        break;

      case 'request_consent':
        // Request consent for secret access
        const consentResult = await consentManager.requestConsent({
          agentIdentifier: message.agentIdentifier,
          service: message.service,
          toolName: message.toolName || 'vault_recall',
          queryPreview: message.queryPreview || ''
        });
        sendResponse(consentResult);
        break;

      case 'get_secret':
        // Get secret (with consent check)
        const secretResult = await handleGetSecret(message);
        sendResponse(secretResult);
        break;

      case 'store_secret':
        // Store new secret
        const storeResult = await handleStoreSecret(message);
        sendResponse(storeResult);
        break;

      case 'list_secrets':
        // List all secrets
        const secrets = await storageManager.listSecrets();
        sendResponse({ secrets });
        break;

      case 'get_activity':
        // Get recent activity log
        const activities = await activityMonitor.getRecentActivities(message.limit || 20);
        sendResponse({ activities });
        break;

      case 'sync_consents':
        // Sync consents to backend
        const syncResult = await handleSyncConsents();
        sendResponse(syncResult);
        break;

      case 'mcp_request':
        // Handle MCP native messaging request
        handleMCPRequest(message, sendResponse);
        break;

      default:
        sendResponse({ error: `Unknown message type: ${message.type}` });
    }
  } catch (error) {
    console.error('Error handling message:', error);
    sendResponse({ error: error.message });
  }
}

/**
 * Handle secret retrieval with consent check
 */
async function handleGetSecret(message) {
  const { agentIdentifier, service, tag } = message;

  // Check consent first
  const consent = await consentManager.getConsent(agentIdentifier, service);
  
  let granted = false;
  let decision = 'deny';

  if (consent) {
    if (consent.decision === 'allow_always' || consent.decision === 'allow_once') {
      granted = true;
      decision = consent.decision;
    } else if (consent.decision === 'deny_always') {
      // Log denied access
      await activityMonitor.logSecretRequest({
        agentIdentifier,
        service,
        granted: false,
        decision: 'deny_always'
      });
      return {
        error: 'Access denied',
        reason: 'Permanently denied by user'
      };
    }
  }

  if (!granted) {
    // Request consent if not granted
    const consentResult = await consentManager.requestConsent({
      agentIdentifier,
      service,
      toolName: 'vault_recall'
    });

    if (!consentResult.granted) {
      // Log denied access
      await activityMonitor.logSecretRequest({
        agentIdentifier,
        service,
        granted: false,
        decision: consentResult.decision || 'deny'
      });
      return {
        error: 'Access denied',
        reason: consentResult.reason || 'User denied access'
      };
    }

    granted = true;
    decision = consentResult.decision;
  }

  // Get secret from storage
  const secret = await storageManager.getSecretByService(service);
  if (!secret) {
    return { error: 'Secret not found', service };
  }

  // Log successful access
  await activityMonitor.logSecretRequest({
    agentIdentifier,
    service,
    granted: true,
    decision
  });

  // Return encrypted secret (client must decrypt)
  return {
    success: true,
    secret: secret.encrypted_secret,
    service: secret.service,
    entry_id: secret.id
  };
}

/**
 * Handle secret storage
 */
async function handleStoreSecret(message) {
  const { service, encryptedSecret, nonce, tags, description } = message;

  if (!service || !encryptedSecret) {
    return { error: 'Service and encrypted secret are required' };
  }

  const secretData = {
    id: crypto.randomUUID(),
    service,
    encrypted_secret: encryptedSecret,
    nonce,
    tags: tags || [],
    description: description || '',
    created_at: new Date().toISOString(),
    synced_at: null
  };

  // Save locally
  await storageManager.saveSecret(secretData);

  // Sync to backend
  try {
    await vaultClient.storeSecret({
      entry_id: secretData.id,
      encrypted_data: encryptedSecret,
      data_type: 'secret',
      service,
      tags: secretData.tags
    });
    secretData.synced_at = new Date().toISOString();
    await storageManager.saveSecret(secretData);
  } catch (error) {
    console.error('Failed to sync secret to backend:', error);
    // Continue anyway - will sync later
  }

  return { success: true, entry_id: secretData.id };
}

/**
 * Sync consents to backend
 */
async function handleSyncConsents() {
  const consents = await storageManager.listConsents();
  
  // Filter to only sync permanent decisions
  const permanentConsents = consents
    .filter(c => c.decision === 'allow_always' || c.decision === 'deny_always')
    .map(c => ({
      agent_identifier: c.agent_identifier,
      service: c.service,
      decision: c.decision
    }));

  if (permanentConsents.length === 0) {
    return { success: true, synced_count: 0 };
  }

  try {
    const result = await vaultClient.syncConsents(permanentConsents);
    return result;
  } catch (error) {
    console.error('Failed to sync consents:', error);
    return { success: false, error: error.message };
  }
}

/**
 * Handle MCP native messaging requests
 */
function handleMCPRequest(message, sendResponse) {
  // MCP requests come via native messaging
  // For now, route to consent manager
  const { agentIdentifier, service, toolName, queryPreview } = message;

  consentManager.requestConsent({
    agentIdentifier,
    service,
    toolName,
    queryPreview
  }).then(result => {
    sendResponse(result);
  }).catch(error => {
    sendResponse({ error: error.message });
  });
}

// Listen for native messaging (MCP server)
chrome.runtime.onConnectNative?.addListener((port) => {
  console.log('MCP native messaging connected');
  
  port.onMessage.addListener((message) => {
    handleMessage({
      type: 'mcp_request',
      ...message
    }, null, (response) => {
      port.postMessage(response);
    });
  });

  port.onDisconnect.addListener(() => {
    console.log('MCP native messaging disconnected');
  });
});

console.log('Enclave service worker loaded');

