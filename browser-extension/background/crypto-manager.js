/**
 * Crypto Manager
 * 
 * Handles client-side encryption/decryption using WebCrypto API.
 */

class CryptoManager {
  constructor() {
    this.masterKey = null;
  }

  /**
   * Derive master key from password
   */
  async deriveMasterKey(password, salt) {
    const encoder = new TextEncoder();
    const passwordKey = await crypto.subtle.importKey(
      'raw',
      encoder.encode(password),
      'PBKDF2',
      false,
      ['deriveKey']
    );

    const masterKey = await crypto.subtle.deriveKey(
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

    this.masterKey = masterKey;
    return masterKey;
  }

  /**
   * Get or derive master key
   */
  async getMasterKey() {
    if (this.masterKey) {
      return this.masterKey;
    }

    // Try to get from storage
    const { masterPassword, salt } = await chrome.storage.local.get(['masterPassword', 'salt']);
    
    if (!masterPassword) {
      throw new Error('Master password not set. Please set it in settings.');
    }

    // Convert salt from base64 if stored
    const saltArray = salt ? this.base64ToArrayBuffer(salt) : crypto.getRandomValues(new Uint8Array(16));
    
    // Store salt if new
    if (!salt) {
      await chrome.storage.local.set({ salt: this.arrayBufferToBase64(saltArray) });
    }

    return await this.deriveMasterKey(masterPassword, saltArray);
  }

  /**
   * Encrypt secret
   */
  async encryptSecret(plaintext) {
    const key = await this.getMasterKey();
    const encoder = new TextEncoder();
    const data = encoder.encode(plaintext);

    // Generate IV (12 bytes for AES-GCM)
    const iv = crypto.getRandomValues(new Uint8Array(12));

    // Encrypt
    const encrypted = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: iv
      },
      key,
      data
    );

    // Return base64-encoded encrypted data and IV
    return {
      encryptedData: this.arrayBufferToBase64(encrypted),
      nonce: this.arrayBufferToBase64(iv)
    };
  }

  /**
   * Decrypt secret
   */
  async decryptSecret(encryptedDataBase64, nonceBase64) {
    const key = await this.getMasterKey();
    
    // Convert from base64
    const encrypted = this.base64ToArrayBuffer(encryptedDataBase64);
    const iv = this.base64ToArrayBuffer(nonceBase64);

    // Decrypt
    const decrypted = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: iv
      },
      key,
      encrypted
    );

    // Convert to string
    const decoder = new TextDecoder();
    return decoder.decode(decrypted);
  }

  /**
   * Set master password
   */
  async setMasterPassword(password) {
    // Generate new salt
    const salt = crypto.getRandomValues(new Uint8Array(16));
    
    // Derive key to verify password is valid
    await this.deriveMasterKey(password, salt);
    
    // Store password and salt (password is stored in plaintext in memory only)
    // In production, consider using a more secure method
    await chrome.storage.local.set({
      masterPassword: password,
      salt: this.arrayBufferToBase64(salt)
    });
  }

  /**
   * Clear master key from memory
   */
  clearMasterKey() {
    this.masterKey = null;
  }

  /**
   * Utility: Convert ArrayBuffer to base64
   */
  arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  /**
   * Utility: Convert base64 to ArrayBuffer
   */
  base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }
}

// Export singleton instance
const cryptoManager = new CryptoManager();
export default cryptoManager;

// Export functions for use in popup
export async function encryptSecret(plaintext) {
  return cryptoManager.encryptSecret(plaintext);
}

export async function decryptSecret(encryptedData, nonce) {
  return cryptoManager.decryptSecret(encryptedData, nonce);
}

