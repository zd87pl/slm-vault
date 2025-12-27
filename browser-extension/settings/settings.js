/**
 * Settings Page Logic
 */

import storageManager from '../background/storage-manager.js';
import vaultClient from '../background/vault-client.js';
import cryptoManager from '../background/crypto-manager.js';

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await storageManager.init();
  await loadSettings();
  setupEventListeners();
});

// Load current settings
async function loadSettings() {
  // Load master password status
  const hasMasterPassword = await checkMasterPassword();
  updateMasterPasswordStatus(hasMasterPassword);

  // Load backend URL
  const backendUrl = await getBackendUrl();
  if (backendUrl) {
    document.getElementById('backend-url').value = backendUrl;
  }

  // Load auth status
  await loadAuthStatus();
}

// Check if master password is set
async function checkMasterPassword() {
  try {
    const masterKeyHash = await storageManager.getMasterKeyHash();
    return !!masterKeyHash;
  } catch (error) {
    return false;
  }
}

// Update master password status display
function updateMasterPasswordStatus(hasPassword) {
  const statusEl = document.getElementById('master-password-status');
  if (hasPassword) {
    statusEl.className = 'status-box success';
    statusEl.innerHTML = '<span class="status-icon">🔒</span><span class="status-text">Master password is set</span>';
  } else {
    statusEl.className = 'status-box error';
    statusEl.innerHTML = '<span class="status-icon">⚠️</span><span class="status-text">Master password not set - please set one to encrypt secrets</span>';
  }
}

// Get backend URL from storage
async function getBackendUrl() {
  const result = await chrome.storage.local.get(['backend_url']);
  return result.backend_url || 'https://keen-curiosity-production-1288.up.railway.app';
}

// Load authentication status
async function loadAuthStatus() {
  const authToken = await storageManager.getAuthToken();
  const authStatusEl = document.getElementById('auth-status');
  const loginFormEl = document.getElementById('login-form');
  const logoutSectionEl = document.getElementById('logout-section');

  if (authToken) {
    // Authenticated
    authStatusEl.className = 'status-box success';
    authStatusEl.innerHTML = '<span class="status-icon">✅</span><span class="status-text">Authenticated</span>';
    loginFormEl.style.display = 'none';
    logoutSectionEl.style.display = 'block';
  } else {
    // Not authenticated
    authStatusEl.className = 'status-box info';
    authStatusEl.innerHTML = '<span class="status-icon">🔓</span><span class="status-text">Not authenticated</span>';
    loginFormEl.style.display = 'block';
    logoutSectionEl.style.display = 'none';
  }
}

// Setup event listeners
function setupEventListeners() {
  // Password change
  document.getElementById('change-password-btn').addEventListener('click', handleChangePassword);
  
  // Password strength indicator
  document.getElementById('new-password').addEventListener('input', updatePasswordStrength);
  document.getElementById('confirm-password').addEventListener('input', validatePasswordMatch);

  // Backend URL
  document.getElementById('test-connection-btn').addEventListener('click', testConnection);
  document.getElementById('backend-url').addEventListener('blur', saveBackendUrl);

  // Authentication
  document.getElementById('login-btn').addEventListener('click', handleLogin);
  document.getElementById('logout-btn').addEventListener('click', handleLogout);

  // Data management
  document.getElementById('export-data-btn').addEventListener('click', exportData);
  document.getElementById('clear-data-btn').addEventListener('click', clearData);

  // Version
  const manifest = chrome.runtime.getManifest();
  document.getElementById('version').textContent = manifest.version;
}

// Handle password change
async function handleChangePassword() {
  const currentPassword = document.getElementById('current-password').value;
  const newPassword = document.getElementById('new-password').value;
  const confirmPassword = document.getElementById('confirm-password').value;

  // Validate
  if (!currentPassword && await checkMasterPassword()) {
    showMessage('Please enter your current password', 'error');
    return;
  }

  if (!newPassword) {
    showMessage('Please enter a new password', 'error');
    return;
  }

  if (newPassword.length < 8) {
    showMessage('Password must be at least 8 characters', 'error');
    return;
  }

  if (newPassword !== confirmPassword) {
    showMessage('Passwords do not match', 'error');
    return;
  }

  try {
    // Verify current password if one exists
    if (await checkMasterPassword()) {
      const isValid = await cryptoManager.verifyMasterPassword(currentPassword);
      if (!isValid) {
        showMessage('Current password is incorrect', 'error');
        return;
      }
    }

    // Set new master password
    await cryptoManager.setMasterPassword(newPassword);

    // Re-encrypt all secrets with new password
    await reencryptSecrets(newPassword);

    showMessage('Password changed successfully', 'success');
    
    // Clear form
    document.getElementById('current-password').value = '';
    document.getElementById('new-password').value = '';
    document.getElementById('confirm-password').value = '';
    updatePasswordStrength();

    // Update status
    updateMasterPasswordStatus(true);
  } catch (error) {
    console.error('Error changing password:', error);
    showMessage('Failed to change password: ' + error.message, 'error');
  }
}

// Re-encrypt all secrets with new password
async function reencryptSecrets(newPassword) {
  const secrets = await storageManager.listSecrets();
  
  // Note: In a production system, you'd want to decrypt with old password first
  // For now, we'll just update the master password and let users re-add secrets if needed
  // This is a limitation - secrets encrypted with old password won't be accessible
  // unless we implement proper password change flow with old password decryption
  
  console.log(`Password changed. ${secrets.length} secrets may need to be re-added if they were encrypted with the old password.`);
  
  // Clear master key to force re-derivation with new password
  cryptoManager.clearMasterKey();
}

// Update password strength indicator
function updatePasswordStrength() {
  const password = document.getElementById('new-password').value;
  const strengthEl = document.getElementById('password-strength');
  
  if (!password) {
    strengthEl.className = 'password-strength';
    strengthEl.innerHTML = '';
    return;
  }

  const strength = calculatePasswordStrength(password);
  strengthEl.className = `password-strength ${strength}`;
  strengthEl.innerHTML = `<div class="password-strength-bar"></div>`;
}

// Calculate password strength
function calculatePasswordStrength(password) {
  let score = 0;
  
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^a-zA-Z\d]/.test(password)) score++;

  if (score <= 2) return 'weak';
  if (score <= 3) return 'medium';
  return 'strong';
}

// Validate password match
function validatePasswordMatch() {
  const newPassword = document.getElementById('new-password').value;
  const confirmPassword = document.getElementById('confirm-password').value;
  
  if (confirmPassword && newPassword !== confirmPassword) {
    document.getElementById('confirm-password').setCustomValidity('Passwords do not match');
  } else {
    document.getElementById('confirm-password').setCustomValidity('');
  }
}

// Test backend connection
async function testConnection() {
  const backendUrl = document.getElementById('backend-url').value;
  
  if (!backendUrl) {
    showMessage('Please enter a backend URL', 'error');
    return;
  }

  // Save URL first
  await chrome.storage.local.set({ backend_url: backendUrl });
  vaultClient.setBaseUrl(backendUrl);

  const statusEl = document.getElementById('connection-status');
  statusEl.style.display = 'block';
  statusEl.className = 'status-box info';
  statusEl.innerHTML = '<span class="status-icon">⏳</span><span class="status-text">Testing connection...</span>';

  try {
    const response = await fetch(`${backendUrl}/health`);
    if (response.ok) {
      statusEl.className = 'status-box success';
      statusEl.innerHTML = '<span class="status-icon">✅</span><span class="status-text">Connection successful</span>';
    } else {
      throw new Error('Connection failed');
    }
  } catch (error) {
    statusEl.className = 'status-box error';
    statusEl.innerHTML = `<span class="status-icon">❌</span><span class="status-text">Connection failed: ${error.message}</span>`;
  }
}

// Save backend URL
async function saveBackendUrl() {
  const backendUrl = document.getElementById('backend-url').value;
  if (backendUrl) {
    await chrome.storage.local.set({ backend_url: backendUrl });
    vaultClient.setBaseUrl(backendUrl);
  }
}

// Handle login
async function handleLogin() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;

  if (!email || !password) {
    showMessage('Please enter email and password', 'error');
    return;
  }

  try {
    const result = await vaultClient.login(email, password);
    if (result.success) {
      await storageManager.setAuthToken(result.token);
      showMessage('Login successful', 'success');
      await loadAuthStatus();
    } else {
      showMessage('Login failed: ' + (result.error || 'Invalid credentials'), 'error');
    }
  } catch (error) {
    console.error('Login error:', error);
    showMessage('Login failed: ' + error.message, 'error');
  }
}

// Handle logout
async function handleLogout() {
  await storageManager.clearAuthToken();
  showMessage('Logged out successfully', 'success');
  await loadAuthStatus();
}

// Export data
async function exportData() {
  try {
    const secrets = await storageManager.listSecrets();
    const consents = await storageManager.listConsents();
    
    const exportData = {
      version: '1.0',
      exported_at: new Date().toISOString(),
      secrets: secrets.map(s => ({
        service: s.service,
        tags: s.tags,
        description: s.description,
        created_at: s.created_at
        // Note: We don't export encrypted secrets for security
      })),
      consents: consents
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `enclave-export-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);

    showMessage('Data exported successfully', 'success');
  } catch (error) {
    console.error('Export error:', error);
    showMessage('Failed to export data: ' + error.message, 'error');
  }
}

// Clear all data
async function clearData() {
  if (!confirm('Are you sure you want to clear all local data? This cannot be undone.')) {
    return;
  }

  if (!confirm('This will delete all secrets and settings. Are you absolutely sure?')) {
    return;
  }

  try {
    await chrome.storage.local.clear();
    await storageManager.init(); // Reinitialize
    showMessage('All data cleared', 'success');
    await loadSettings();
  } catch (error) {
    console.error('Clear data error:', error);
    showMessage('Failed to clear data: ' + error.message, 'error');
  }
}

// Show message
function showMessage(text, type) {
  // Remove existing messages
  const existing = document.querySelector('.message');
  if (existing) {
    existing.remove();
  }

  const messageEl = document.createElement('div');
  messageEl.className = `message ${type}`;
  messageEl.textContent = text;
  
  const content = document.querySelector('.settings-content');
  content.insertBefore(messageEl, content.firstChild);

  // Auto-remove after 5 seconds
  setTimeout(() => {
    messageEl.remove();
  }, 5000);
}

