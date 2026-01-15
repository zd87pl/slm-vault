/**
 * Crypto Manager
 *
 * Handles client-side encryption/decryption using WebCrypto API.
 */

// Security constants
const PBKDF2_ITERATIONS = 100000;
const SALT_LENGTH = 16;
const IV_LENGTH = 12;
const KEY_LENGTH = 256;

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
        iterations: PBKDF2_ITERATIONS,
        hash: 'SHA-256'
      },
      passwordKey,
      { name: 'AES-GCM', length: KEY_LENGTH },
      true,
      ['encrypt', 'decrypt']
    );

    this.masterKey = masterKey;
    return masterKey;
  }

  /**
   * Get or derive master key (requires unlock first)
   */
  async getMasterKey() {
    if (this.masterKey) {
      return this.masterKey;
    }

    // Master key must be unlocked first via unlockVault()
    throw new Error('Vault is locked. Please unlock it first.');
  }

  /**
   * Unlock vault with password (derives key and verifies against stored hash)
   */
  async unlockVault(password) {
    const { salt, verificationHash } = await chrome.storage.local.get(['salt', 'verificationHash']);

    if (!salt || !verificationHash) {
      throw new Error('Master password not set. Please set it in settings.');
    }

    // Convert salt from base64
    const saltArray = this.base64ToArrayBuffer(salt);

    // Derive key from password
    const masterKey = await this.deriveMasterKey(password, saltArray);

    // Verify the password by comparing hashes
    const computedHash = await this._computeVerificationHash(masterKey, saltArray);

    // Use constant-time comparison
    if (!this._constantTimeCompare(computedHash, verificationHash)) {
      this.masterKey = null;
      throw new Error('Invalid master password');
    }

    this.masterKey = masterKey;
    return masterKey;
  }

  /**
   * Compute verification hash from master key (for password verification)
   */
  async _computeVerificationHash(masterKey, salt) {
    // Export the key and hash it with the salt for verification
    const keyData = await crypto.subtle.exportKey('raw', masterKey);
    const combined = new Uint8Array(keyData.byteLength + salt.byteLength);
    combined.set(new Uint8Array(keyData), 0);
    combined.set(new Uint8Array(salt), keyData.byteLength);

    const hashBuffer = await crypto.subtle.digest('SHA-256', combined);
    return this.arrayBufferToBase64(hashBuffer);
  }

  /**
   * Constant-time string comparison to prevent timing attacks
   */
  _constantTimeCompare(a, b) {
    if (a.length !== b.length) {
      return false;
    }
    let result = 0;
    for (let i = 0; i < a.length; i++) {
      result |= a.charCodeAt(i) ^ b.charCodeAt(i);
    }
    return result === 0;
  }

  /**
   * Encrypt secret using the current master key
   */
  async encryptSecret(plaintext) {
    const key = await this.getMasterKey();
    const encoder = new TextEncoder();
    const data = encoder.encode(plaintext);

    // Generate IV (12 bytes for AES-GCM)
    const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));

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
   * Set master password (stores only verification hash, never plaintext)
   */
  async setMasterPassword(password) {
    // Generate new salt
    const salt = crypto.getRandomValues(new Uint8Array(SALT_LENGTH));

    // Derive key from password
    const masterKey = await this.deriveMasterKey(password, salt);

    // Compute verification hash (NOT the password itself)
    const verificationHash = await this._computeVerificationHash(masterKey, salt);

    // Store only the salt and verification hash - NEVER the plaintext password
    await chrome.storage.local.set({
      salt: this.arrayBufferToBase64(salt),
      verificationHash: verificationHash
    });

    // Keep key in memory for current session
    this.masterKey = masterKey;
  }

  /**
   * Verify master password (constant-time comparison)
   */
  async verifyMasterPassword(password) {
    try {
      const { salt, verificationHash } = await chrome.storage.local.get(['salt', 'verificationHash']);

      if (!salt || !verificationHash) {
        return false;
      }

      const saltArray = this.base64ToArrayBuffer(salt);
      const masterKey = await this.deriveMasterKey(password, saltArray);
      const computedHash = await this._computeVerificationHash(masterKey, saltArray);

      // Constant-time comparison to prevent timing attacks
      return this._constantTimeCompare(computedHash, verificationHash);
    } catch (error) {
      return false;
    }
  }

  /**
   * Encrypt secret with specific password (for re-encryption)
   */
  async encryptSecretWithPassword(plaintext, password) {
    const salt = crypto.getRandomValues(new Uint8Array(SALT_LENGTH));
    const key = await this.deriveMasterKey(password, salt);
    const encoder = new TextEncoder();
    const data = encoder.encode(plaintext);
    const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));

    const encrypted = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: iv },
      key,
      data
    );

    return {
      encryptedData: this.arrayBufferToBase64(encrypted),
      nonce: this.arrayBufferToBase64(iv),
      salt: this.arrayBufferToBase64(salt)
    };
  }

  /**
   * Check if vault is unlocked
   */
  isUnlocked() {
    return this.masterKey !== null;
  }

  /**
   * Check if master password has been set
   */
  async isInitialized() {
    const { salt, verificationHash } = await chrome.storage.local.get(['salt', 'verificationHash']);
    return !!(salt && verificationHash);
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

