/**
 * Popup Logic
 */

import storageManager from '../background/storage-manager.js';
import vaultClient from '../background/vault-client.js';
import '../background/crypto-manager.js';

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await storageManager.init();
  await loadSecrets();
  setupEventListeners();
  updateAccessCount();
  checkPauseState();
});

// Event listeners
function setupEventListeners() {
  document.getElementById('add-secret-btn').addEventListener('click', showAddDialog);
  document.getElementById('sync-btn').addEventListener('click', syncSecrets);
  document.getElementById('close-dialog-btn').addEventListener('click', hideAddDialog);
  document.getElementById('cancel-btn').addEventListener('click', hideAddDialog);
  document.getElementById('save-btn').addEventListener('click', saveSecret);
  document.getElementById('toggle-password-btn').addEventListener('click', togglePassword);
  document.getElementById('settings-link').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: chrome.runtime.getURL('settings/settings.html') });
  });

  document.getElementById('activity-link').addEventListener('click', async (e) => {
    e.preventDefault();
    await showActivityLog();
  });

  document.getElementById('pause-toggle').addEventListener('click', togglePause);
}

// Load secrets from storage
async function loadSecrets() {
  const loadingEl = document.getElementById('loading');
  const emptyStateEl = document.getElementById('empty-state');
  const secretsListEl = document.getElementById('secrets-list');

  try {
    const secrets = await storageManager.listSecrets();
    
    loadingEl.style.display = 'none';

    if (secrets.length === 0) {
      emptyStateEl.style.display = 'block';
      secretsListEl.innerHTML = '';
      return;
    }

    emptyStateEl.style.display = 'none';
    secretsListEl.innerHTML = secrets.map(secret => `
      <div class="secret-item" data-id="${secret.id}">
        <div class="secret-header">
          <span class="secret-service">${escapeHtml(secret.service)}</span>
          <div class="secret-actions">
            <button class="secret-action-btn" onclick="copySecret('${secret.id}')" title="Copy">📋</button>
            <button class="secret-action-btn" onclick="deleteSecret('${secret.id}')" title="Delete">🗑</button>
          </div>
        </div>
        <div class="secret-meta">
          ${secret.tags && secret.tags.length > 0 ? `
            <div class="secret-tags">
              ${secret.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
            </div>
          ` : ''}
          <span>${formatDate(secret.created_at)}</span>
        </div>
      </div>
    `).join('');
  } catch (error) {
    console.error('Failed to load secrets:', error);
    loadingEl.textContent = 'Error loading secrets';
  }
}

// Show add secret dialog
function showAddDialog() {
  document.getElementById('add-dialog').style.display = 'flex';
  document.getElementById('service-input').focus();
}

// Hide add secret dialog
function hideAddDialog() {
  document.getElementById('add-dialog').style.display = 'none';
  // Clear form
  document.getElementById('service-input').value = '';
  document.getElementById('secret-input').value = '';
  document.getElementById('tags-input').value = '';
  document.getElementById('description-input').value = '';
}

// Toggle password visibility
function togglePassword() {
  const input = document.getElementById('secret-input');
  const btn = document.getElementById('toggle-password-btn');
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
  }
}

// Save secret
async function saveSecret() {
  const service = document.getElementById('service-input').value.trim();
  const secret = document.getElementById('secret-input').value.trim();
  const tagsStr = document.getElementById('tags-input').value.trim();
  const description = document.getElementById('description-input').value.trim();

  if (!service || !secret) {
    alert('Service name and secret are required');
    return;
  }

  const tags = tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(t => t) : [];

  try {
    // Encrypt secret (using crypto manager - will be implemented)
    const { encryptSecret } = await import('../background/crypto-manager.js');
    const { encryptedData, nonce } = await encryptSecret(secret);

    // Save via background script
    const result = await chrome.runtime.sendMessage({
      type: 'store_secret',
      service,
      encryptedSecret: encryptedData,
      nonce,
      tags,
      description
    });

    if (result.error) {
      alert(`Error: ${result.error}`);
      return;
    }

    hideAddDialog();
    await loadSecrets();
    updateSyncStatus('synced');
  } catch (error) {
    console.error('Failed to save secret:', error);
    alert(`Failed to save secret: ${error.message}`);
  }
}

// Copy secret to clipboard
async function copySecret(id) {
  try {
    const secret = await storageManager.getSecret(id);
    if (!secret) {
      alert('Secret not found');
      return;
    }

    // Decrypt secret (using crypto manager)
    const { decryptSecret } = await import('../background/crypto-manager.js');
    const decrypted = await decryptSecret(secret.encrypted_secret, secret.nonce);

    // Copy to clipboard
    await navigator.clipboard.writeText(decrypted);
    
    // Show feedback
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '✓';
    setTimeout(() => {
      btn.textContent = originalText;
    }, 1000);
  } catch (error) {
    console.error('Failed to copy secret:', error);
    alert('Failed to copy secret');
  }
}

// Delete secret
async function deleteSecret(id) {
  if (!confirm('Are you sure you want to delete this secret?')) {
    return;
  }

  try {
    await storageManager.deleteSecret(id);
    
    // Also delete from backend
    try {
      await vaultClient.deleteSecret(id);
    } catch (error) {
      console.error('Failed to delete from backend:', error);
      // Continue anyway
    }

    await loadSecrets();
  } catch (error) {
    console.error('Failed to delete secret:', error);
    alert('Failed to delete secret');
  }
}

// Sync secrets with backend
async function syncSecrets() {
  updateSyncStatus('syncing');
  
  try {
    const secrets = await storageManager.listSecrets();
    const unsynced = secrets.filter(s => !s.synced_at);

    if (unsynced.length === 0) {
      // Pull from backend instead
      const backendSecrets = await vaultClient.listSecrets({ data_type: 'secret' });
      
      // Merge with local secrets
      for (const backendSecret of backendSecrets.entries || []) {
        const localSecret = await storageManager.getSecret(backendSecret.entry_id);
        if (!localSecret) {
          // Add from backend
          await storageManager.saveSecret({
            id: backendSecret.entry_id,
            service: backendSecret.service,
            encrypted_secret: backendSecret.encrypted_data,
            nonce: null, // Backend doesn't store nonce separately
            tags: backendSecret.tags || [],
            created_at: backendSecret.created_at,
            synced_at: new Date().toISOString()
          });
        }
      }
    } else {
      // Sync local secrets to backend
      await vaultClient.syncSecrets(unsynced.map(s => ({
        entry_id: s.id,
        encrypted_data: s.encrypted_secret,
        data_type: 'secret',
        service: s.service,
        tags: s.tags
      })));

      // Update synced_at
      for (const secret of unsynced) {
        secret.synced_at = new Date().toISOString();
        await storageManager.saveSecret(secret);
      }
    }

    updateSyncStatus('synced');
    await loadSecrets();
  } catch (error) {
    console.error('Failed to sync:', error);
    updateSyncStatus('error');
    alert('Failed to sync secrets');
  }
}

// Update sync status
function updateSyncStatus(status) {
  const indicator = document.getElementById('status-indicator');
  const text = document.getElementById('status-text');
  
  indicator.className = 'status-indicator';
  
  switch (status) {
    case 'syncing':
      indicator.classList.add('syncing');
      text.textContent = 'Syncing...';
      break;
    case 'synced':
      text.textContent = 'Synced';
      break;
    case 'error':
      indicator.classList.add('error');
      text.textContent = 'Error';
      break;
  }
}

// Utility functions
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatDate(dateString) {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return date.toLocaleDateString();
}

// Show activity log
async function showActivityLog() {
  try {
    const response = await chrome.runtime.sendMessage({
      type: 'get_activity',
      limit: 20
    });

    if (response && response.activities) {
      // Create activity dialog
      const dialog = document.createElement('div');
      dialog.className = 'dialog-overlay';
      dialog.innerHTML = `
        <div class="dialog" style="max-width: 500px;">
          <div class="dialog-header">
            <h2>Recent Activity</h2>
            <button class="dialog-close" onclick="this.closest('.dialog-overlay').remove()">×</button>
          </div>
          <div class="dialog-content">
            ${response.activities.length === 0 
              ? '<p style="text-align: center; color: #666; padding: 40px;">No activity yet</p>'
              : response.activities.map(activity => `
                <div style="padding: 12px; border-bottom: 1px solid #e5e5e5;">
                  <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <strong>${escapeHtml(activity.service || 'Unknown')}</strong>
                    <span style="color: ${activity.granted ? '#4caf50' : '#f44336'}; font-size: 12px;">
                      ${activity.granted ? '✓ Allowed' : '✕ Denied'}
                    </span>
                  </div>
                  <div style="font-size: 11px; color: #666;">
                    Agent: ${escapeHtml(activity.agent_identifier || 'Unknown')}<br>
                    ${formatDate(activity.timestamp)}
                  </div>
                </div>
              `).join('')
            }
          </div>
        </div>
      `;
      document.body.appendChild(dialog);
    }
  } catch (error) {
    console.error('Failed to load activity log:', error);
    alert('Failed to load activity log');
  }
}

// Status bar functions
async function updateAccessCount() {
    try {
        const response = await chrome.runtime.sendMessage({ type: 'get_activity', limit: 100 });
        const activities = response?.activities || [];
        const today = new Date().toISOString().split('T')[0];
        const count = activities.filter(a => a.timestamp && a.timestamp.startsWith(today)).length;
        const el = document.getElementById('access-count');
        if (el) el.textContent = `${count} access${count !== 1 ? 'es' : ''} today`;
    } catch (e) {
        console.debug('Failed to update access count:', e);
    }
}

async function togglePause() {
    try {
        const response = await chrome.runtime.sendMessage({ type: 'toggle_pause' });
        const btn = document.getElementById('pause-toggle');
        if (btn && response) {
            btn.textContent = response.paused ? 'Resume' : 'Pause All';
            btn.classList.toggle('paused', response.paused);
        }
    } catch (e) {
        console.debug('Failed to toggle pause:', e);
    }
}

async function checkPauseState() {
    try {
        const response = await chrome.runtime.sendMessage({ type: 'get_pause_state' });
        const btn = document.getElementById('pause-toggle');
        if (btn && response) {
            btn.textContent = response.paused ? 'Resume' : 'Pause All';
            btn.classList.toggle('paused', response.paused);
        }
    } catch (e) {
        console.debug('Failed to check pause state:', e);
    }
}

// Listen for real-time events from service worker
chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'agent_querying') {
        const indicator = document.getElementById('live-indicator');
        if (indicator) indicator.classList.add('active');
    } else if (message.type === 'agent_query_complete') {
        const indicator = document.getElementById('live-indicator');
        if (indicator) indicator.classList.remove('active');
        updateAccessCount();
    }
});

// Make functions available globally for onclick handlers
window.copySecret = copySecret;
window.deleteSecret = deleteSecret;

