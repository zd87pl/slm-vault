/**
 * Activity Monitor
 * 
 * Monitors and logs secret retrieval requests for user visibility.
 * Non-invasive detection of API/secret usage.
 */

import storageManager from './storage-manager.js';
import vaultClient from './vault-client.js';

class ActivityMonitor {
  constructor() {
    this.activityLog = [];
    this.maxLogSize = 100; // Keep last 100 activities
  }

  /**
   * Log a secret retrieval request
   */
  async logSecretRequest(params) {
    const {
      agentIdentifier,
      service,
      granted,
      decision,
      timestamp = new Date().toISOString()
    } = params;

    const activity = {
      id: crypto.randomUUID(),
      type: 'secret_retrieve',
      agent_identifier: agentIdentifier,
      service,
      granted,
      decision,
      timestamp
    };

    // Add to in-memory log
    this.activityLog.unshift(activity);
    if (this.activityLog.length > this.maxLogSize) {
      this.activityLog.pop();
    }

    // Store in IndexedDB for persistence
    try {
      await storageManager.setSetting(
        `activity_${activity.id}`,
        activity
      );
    } catch (error) {
      console.error('Failed to store activity:', error);
    }

    // Sync to backend (if authenticated)
    try {
      await vaultClient.request('/api/logs', {
        method: 'POST',
        body: JSON.stringify({
          operation: 'extension_secret_retrieve',
          service,
          client_type: 'extension',
          success: granted,
          metadata: {
            agent_identifier: agentIdentifier,
            decision
          }
        })
      });
    } catch (error) {
      // Don't fail if backend sync fails
      console.debug('Failed to sync activity to backend:', error);
    }

    return activity;
  }

  /**
   * Get recent activities
   */
  async getRecentActivities(limit = 20) {
    // Load from IndexedDB if needed
    const stored = await storageManager.getSetting('recent_activities');
    if (stored && Array.isArray(stored)) {
      return stored.slice(0, limit);
    }

    return this.activityLog.slice(0, limit);
  }

  /**
   * Clear activity log
   */
  async clearActivities() {
    this.activityLog = [];
    // Clear from IndexedDB
    const keys = await storageManager.getSetting('activity_keys') || [];
    for (const key of keys) {
      await storageManager.setSetting(`activity_${key}`, null);
    }
    await storageManager.setSetting('activity_keys', []);
  }
}

// Export singleton
const activityMonitor = new ActivityMonitor();
export default activityMonitor;

