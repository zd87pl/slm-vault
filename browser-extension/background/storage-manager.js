/**
 * Storage Manager for Enclave Extension
 * 
 * Manages IndexedDB storage for secrets, consents, and sync state.
 */

const DB_NAME = 'EnclaveVault';
const DB_VERSION = 1;

const STORES = {
  SECRETS: 'secrets',
  CONSENTS: 'consents',
  SYNC_STATE: 'sync_state',
  SETTINGS: 'settings'
};

class StorageManager {
  constructor() {
    this.db = null;
  }

  /**
   * Initialize IndexedDB database
   */
  async init() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Secrets store
        if (!db.objectStoreNames.contains(STORES.SECRETS)) {
          const secretsStore = db.createObjectStore(STORES.SECRETS, {
            keyPath: 'id'
          });
          secretsStore.createIndex('service', 'service', { unique: false });
          secretsStore.createIndex('synced_at', 'synced_at', { unique: false });
        }

        // Consents store
        if (!db.objectStoreNames.contains(STORES.CONSENTS)) {
          const consentsStore = db.createObjectStore(STORES.CONSENTS, {
            keyPath: 'id'
          });
          consentsStore.createIndex('agent_service', ['agent_identifier', 'service'], { unique: false });
          consentsStore.createIndex('agent', 'agent_identifier', { unique: false });
        }

        // Sync state store
        if (!db.objectStoreNames.contains(STORES.SYNC_STATE)) {
          db.createObjectStore(STORES.SYNC_STATE, {
            keyPath: 'key'
          });
        }

        // Settings store
        if (!db.objectStoreNames.contains(STORES.SETTINGS)) {
          db.createObjectStore(STORES.SETTINGS, {
            keyPath: 'key'
          });
        }
      };
    });
  }

  /**
   * Save secret to storage
   */
  async saveSecret(secret) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SECRETS], 'readwrite');
      const request = tx.objectStore(STORES.SECRETS).put({
        ...secret,
        updated_at: new Date().toISOString()
      });

      request.onsuccess = () => resolve(secret.id);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get secret by ID
   */
  async getSecret(id) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SECRETS], 'readonly');
      const request = tx.objectStore(STORES.SECRETS).get(id);

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get secret by service name
   */
  async getSecretByService(service) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SECRETS], 'readonly');
      const index = tx.objectStore(STORES.SECRETS).index('service');
      const request = index.getAll(service);

      request.onsuccess = () => {
        // Return most recent
        const results = request.result;
        if (results.length === 0) {
          resolve(null);
        } else {
          // Sort by created_at descending
          results.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
          resolve(results[0]);
        }
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * List all secrets
   */
  async listSecrets() {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SECRETS], 'readonly');
      const request = tx.objectStore(STORES.SECRETS).getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Delete secret
   */
  async deleteSecret(id) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SECRETS], 'readwrite');
      const request = tx.objectStore(STORES.SECRETS).delete(id);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Save consent decision
   */
  async saveConsent(consent) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.CONSENTS], 'readwrite');
      const request = tx.objectStore(STORES.CONSENTS).put({
        ...consent,
        updated_at: new Date().toISOString()
      });

      request.onsuccess = () => resolve(consent.id);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get consent decision for agent and service
   */
  async getConsent(agentIdentifier, service = null) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.CONSENTS], 'readonly');
      const index = tx.objectStore(STORES.CONSENTS).index('agent_service');
      const key = [agentIdentifier, service || null];
      const request = index.get(key);

      request.onsuccess = () => {
        const result = request.result;
        if (!result) {
          // Try to find consent for all services (service = null)
          if (service !== null) {
            const allServicesRequest = index.get([agentIdentifier, null]);
            allServicesRequest.onsuccess = () => resolve(allServicesRequest.result);
            allServicesRequest.onerror = () => reject(allServicesRequest.error);
          } else {
            resolve(null);
          }
        } else {
          // Check if expired (for allow_once)
          if (result.decision === 'allow_once' && result.expires_at) {
            if (new Date(result.expires_at) < new Date()) {
              resolve(null);
            } else {
              resolve(result);
            }
          } else {
            resolve(result);
          }
        }
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * List all consents
   */
  async listConsents() {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.CONSENTS], 'readonly');
      const request = tx.objectStore(STORES.CONSENTS).getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Delete consent
   */
  async deleteConsent(id) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.CONSENTS], 'readwrite');
      const request = tx.objectStore(STORES.CONSENTS).delete(id);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get sync state
   */
  async getSyncState(key) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SYNC_STATE], 'readonly');
      const request = tx.objectStore(STORES.SYNC_STATE).get(key);

      request.onsuccess = () => resolve(request.result?.value || null);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Set sync state
   */
  async setSyncState(key, value) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SYNC_STATE], 'readwrite');
      const request = tx.objectStore(STORES.SYNC_STATE).put({
        key,
        value,
        updated_at: new Date().toISOString()
      });

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get setting
   */
  async getSetting(key) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SETTINGS], 'readonly');
      const request = tx.objectStore(STORES.SETTINGS).get(key);

      request.onsuccess = () => resolve(request.result?.value || null);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Set setting
   */
  async setSetting(key, value) {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction([STORES.SETTINGS], 'readwrite');
      const request = tx.objectStore(STORES.SETTINGS).put({
        key,
        value,
        updated_at: new Date().toISOString()
      });

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }
}

// Export singleton instance
const storageManager = new StorageManager();
export default storageManager;

