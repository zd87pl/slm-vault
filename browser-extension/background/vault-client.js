/**
 * Vault API Client
 * 
 * Handles communication with Enclave backend API.
 */

const DEFAULT_BASE_URL = 'https://keen-curiosity-production-1288.up.railway.app';

class VaultClient {
  constructor(baseUrl = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.accessToken = null;
    this.refreshToken = null;
  }

  /**
   * Set base URL
   */
  setBaseUrl(baseUrl) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Set authentication tokens
   */
  setAuth(accessToken, refreshToken) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
  }

  /**
   * Login with email and password
   */
  async login(email, password) {
    try {
      const response = await fetch(`${this.baseUrl}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email,
          password
        })
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        return { success: false, error: error.detail || 'Login failed' };
      }

      const data = await response.json();
      this.accessToken = data.access_token;
      this.refreshToken = data.refresh_token;

      // Save to storage
      await chrome.storage.local.set({
        accessToken: this.accessToken,
        refreshToken: this.refreshToken
      });

      return { success: true, token: this.accessToken };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  /**
   * Get access token (from storage or refresh)
   */
  async getAccessToken() {
    if (this.accessToken) {
      return this.accessToken;
    }

    // Try to load from storage
    const { accessToken, refreshToken } = await chrome.storage.local.get(['accessToken', 'refreshToken']);
    if (accessToken) {
      this.accessToken = accessToken;
      this.refreshToken = refreshToken;
      return accessToken;
    }

    return null;
  }

  /**
   * Refresh access token
   */
  async refreshAccessToken() {
    if (!this.refreshToken) {
      const { refreshToken } = await chrome.storage.local.get(['refreshToken']);
      this.refreshToken = refreshToken;
    }

    if (!this.refreshToken) {
      throw new Error('No refresh token available');
    }

    try {
      const response = await fetch(`${this.baseUrl}/api/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          refresh_token: this.refreshToken
        })
      });

      if (!response.ok) {
        throw new Error('Token refresh failed');
      }

      const data = await response.json();
      this.accessToken = data.access_token;
      this.refreshToken = data.refresh_token || this.refreshToken;

      // Save to storage
      await chrome.storage.local.set({
        accessToken: this.accessToken,
        refreshToken: this.refreshToken
      });

      return this.accessToken;
    } catch (error) {
      // Clear tokens on error
      this.accessToken = null;
      this.refreshToken = null;
      await chrome.storage.local.remove(['accessToken', 'refreshToken']);
      throw error;
    }
  }

  /**
   * Make authenticated API request
   */
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    let accessToken = await this.getAccessToken();

    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    let response = await fetch(url, {
      ...options,
      headers
    });

    // If 401, try to refresh token
    if (response.status === 401 && accessToken) {
      try {
        accessToken = await this.refreshAccessToken();
        headers['Authorization'] = `Bearer ${accessToken}`;
        response = await fetch(url, {
          ...options,
          headers
        });
      } catch (error) {
        throw new Error('Authentication failed');
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
  }

  /**
   * Store encrypted secret
   */
  async storeSecret(secretData) {
    return this.request('/api/vault/store', {
      method: 'POST',
      body: JSON.stringify(secretData)
    });
  }

  /**
   * List secrets (metadata only)
   */
  async listSecrets(filters = {}) {
    const params = new URLSearchParams();
    if (filters.data_type) params.append('data_type', filters.data_type);
    if (filters.service) params.append('service', filters.service);
    if (filters.tag) params.append('tag', filters.tag);

    const query = params.toString();
    return this.request(`/api/vault/entries${query ? `?${query}` : ''}`);
  }

  /**
   * Get secret by ID
   */
  async getSecret(entryId) {
    return this.request(`/api/vault/entry/${entryId}`);
  }

  /**
   * Delete secret
   */
  async deleteSecret(entryId) {
    return this.request(`/api/vault/entry/${entryId}`, {
      method: 'DELETE'
    });
  }

  /**
   * Sync secrets from extension
   */
  async syncSecrets(secrets) {
    return this.request('/api/vault/sync', {
      method: 'POST',
      body: JSON.stringify({
        entries: secrets
      })
    });
  }

  /**
   * Retrieve secret for LangChain agent (with policy check)
   */
  async retrieveSecretForAgent(service, tag = null) {
    return this.request('/api/langchain/secrets/retrieve', {
      method: 'POST',
      body: JSON.stringify({
        service,
        tag
      })
    });
  }

  /**
   * Sync consent decisions
   */
  async syncConsents(consents) {
    return this.request('/api/langchain/consent/sync', {
      method: 'POST',
      body: JSON.stringify({
        consents
      })
    });
  }

  /**
   * Check consent for request
   */
  async checkConsent(agentIdentifier, service) {
    return this.request('/api/langchain/consent/check', {
      method: 'POST',
      body: JSON.stringify({
        agent_identifier: agentIdentifier,
        service
      })
    });
  }
}

// Export singleton instance
const vaultClient = new VaultClient();
export default vaultClient;

