"""
Folder Manager for organizing vault entries into folders with optional password protection.

Folders are stored as special entries with EntryType.FOLDER:
- service = folder name
- encrypted_data = encrypted password hash (if password protected)
- tags = ["folder"]
- description = optional folder description

Folder passwords are encrypted using the same ChaCha20-Poly1305 algorithm as entries.
"""

import logging
import hashlib
import os
from typing import Optional, Dict, List
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from advanced_vault.encrypted_kv import EncryptedKVStore, EntryType, QueryFilter

logger = logging.getLogger(__name__)


class FolderManager:
    """Manages folders and folder passwords."""
    
    def __init__(self, vault: EncryptedKVStore):
        """
        Initialize folder manager.
        
        Args:
            vault: EncryptedKVStore instance
        """
        self.vault = vault
        self._unlocked_folders: Dict[str, bool] = {}  # Track unlocked folders in session
        self._folder_passwords: Dict[str, str] = {}  # Cache passwords for unlocked folders
    
    def create_folder(
        self,
        folder_name: str,
        password: Optional[str] = None,
        description: Optional[str] = None
    ) -> str:
        """
        Create a new folder.
        
        Args:
            folder_name: Name of the folder
            password: Optional password (if None, folder is unlocked)
            description: Optional folder description
            
        Returns:
            Folder entry ID
        """
        # Check if folder already exists
        existing = self.get_folder(folder_name)
        if existing:
            raise ValueError(f"Folder '{folder_name}' already exists")
        
        # Encrypt password if provided
        encrypted_password_data = b""
        if password:
            # Hash password with salt
            salt = os.urandom(16)
            password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            
            # Encrypt password hash (store salt + hash)
            # Format: salt (16 bytes) + password_hash (32 bytes) = 48 bytes
            password_payload = salt + password_hash
            
            # Use ChaCha20Poly1305 with master key
            cipher = ChaCha20Poly1305(self.vault.master_key)
            nonce = os.urandom(12)
            associated_data = f"folder_password:{folder_name}".encode('utf-8')
            encrypted_password = cipher.encrypt(
                nonce,
                password_payload,
                associated_data
            )
            
            # Store as: nonce (12 bytes) + encrypted_data (variable)
            encrypted_password_data = nonce + encrypted_password
        
        # Create folder entry
        # Note: vault.put() expects secret_value as string, so we convert to hex
        entry_id = self.vault.put(
            service=folder_name,
            secret_value=encrypted_password_data.hex() if encrypted_password_data else "",  # Empty if no password
            entry_type=EntryType.FOLDER,
            tags=["folder"],
            description=description
        )
        
        # Mark as unlocked if no password
        if not password:
            self._unlocked_folders[folder_name] = True
        
        logger.info(f"Created folder: {folder_name} (password protected: {password is not None})")
        return entry_id
    
    def get_folder(self, folder_name: str) -> Optional[Dict]:
        """
        Get folder metadata.
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            Folder dict with metadata, or None if not found
        """
        query_filter = QueryFilter(
            service=folder_name,
            entry_type=EntryType.FOLDER
        )
        results = self.vault.search(query_filter)
        
        if not results:
            return None
        
        entry = results[0]
        has_password = bool(entry.encrypted_data and len(entry.encrypted_data) > 0)
        
        return {
            "id": entry.id,
            "name": entry.service,
            "description": entry.description,
            "has_password": has_password,
            "is_unlocked": self._unlocked_folders.get(folder_name, False),
            "created_at": entry.created_at
        }
    
    def list_folders(self) -> List[Dict]:
        """
        List all folders.
        
        Returns:
            List of folder dicts
        """
        query_filter = QueryFilter(
            entry_type=EntryType.FOLDER
        )
        entries = self.vault.search(query_filter)
        
        folders = []
        for entry in entries:
            has_password = bool(entry.encrypted_data and len(entry.encrypted_data) > 0)
            folders.append({
                "id": entry.id,
                "name": entry.service,
                "description": entry.description,
                "has_password": has_password,
                "is_unlocked": self._unlocked_folders.get(entry.service, False),
                "created_at": entry.created_at
            })
        
        return folders
    
    def unlock_folder(self, folder_name: str, password: str) -> bool:
        """
        Unlock a password-protected folder.
        
        Args:
            folder_name: Name of the folder
            password: Folder password
            
        Returns:
            True if password is correct, False otherwise
        """
        # Get folder entry
        query_filter = QueryFilter(
            service=folder_name,
            entry_type=EntryType.FOLDER
        )
        results = self.vault.search(query_filter)
        
        if not results:
            return False
        
        entry = results[0]
        
        # If no password, unlock immediately
        # encrypted_data is bytes from EncryptedEntry, check if empty
        has_password = bool(entry.encrypted_data and len(entry.encrypted_data) > 0)
        
        if not has_password:
            self._unlocked_folders[folder_name] = True
            return True
        
        # Decrypt password hash
        try:
            # Get decrypted hex string from vault
            # vault.get() decrypts the entry and returns the plaintext hex string
            encrypted_hex = self.vault.get(folder_name, update_access_time=False)
            if not encrypted_hex:
                return False
            
            # Convert hex string to bytes
            encrypted_bytes = bytes.fromhex(encrypted_hex)
            
            if len(encrypted_bytes) < 12:
                return False
            
            # Extract nonce (first 12 bytes) and ciphertext
            password_nonce = encrypted_bytes[:12]
            password_ciphertext = encrypted_bytes[12:]
            
            # Decrypt password payload
            cipher = ChaCha20Poly1305(self.vault.master_key)
            associated_data = f"folder_password:{folder_name}".encode('utf-8')
            password_payload = cipher.decrypt(password_nonce, password_ciphertext, associated_data)
            
            # Extract salt (first 16 bytes) and hash (next 32 bytes)
            if len(password_payload) < 48:
                return False
            
            salt = password_payload[:16]
            stored_hash = password_payload[16:48]
            
            # Verify password
            password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            
            if password_hash == stored_hash:
                # Password correct - unlock folder
                self._unlocked_folders[folder_name] = True
                self._folder_passwords[folder_name] = password
                logger.info(f"Unlocked folder: {folder_name}")
                return True
            else:
                logger.warning(f"Invalid password for folder: {folder_name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to unlock folder {folder_name}: {e}")
            return False
    
    def lock_folder(self, folder_name: str):
        """
        Lock a folder (remove from unlocked cache).
        
        Args:
            folder_name: Name of the folder
        """
        self._unlocked_folders.pop(folder_name, None)
        self._folder_passwords.pop(folder_name, None)
        logger.info(f"Locked folder: {folder_name}")
    
    def is_folder_unlocked(self, folder_name: str) -> bool:
        """
        Check if folder is unlocked.
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            True if unlocked, False otherwise
        """
        # Check if folder exists and has no password
        folder = self.get_folder(folder_name)
        if not folder:
            return False
        
        if not folder["has_password"]:
            return True
        
        # Check unlocked cache
        return self._unlocked_folders.get(folder_name, False)
    
    def delete_folder(self, folder_name: str) -> bool:
        """
        Delete a folder (and optionally move entries to root).
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            True if deleted, False if not found
        """
        # TODO: Optionally move entries to root or delete them
        # For now, just delete the folder entry
        return self.vault.delete(folder_name)
    
    def get_entries_in_folder(self, folder_name: str) -> List:
        """
        Get all entries in a folder.
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            List of entry dicts
        """
        query_filter = QueryFilter(folder=folder_name)
        entries = self.vault.search(query_filter)
        
        result = []
        for entry in entries:
            result.append({
                "id": entry.id,
                "service": entry.service,
                "entry_type": entry.entry_type.value,
                "tags": entry.tags,
                "description": entry.description,
                "created_at": entry.created_at
            })
        
        return result

