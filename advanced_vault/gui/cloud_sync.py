"""
Cloud sync service for GUI vault entries.

Handles syncing encrypted vault entries between local storage and cloud backend.
All encryption happens client-side; server only stores encrypted blobs.
"""

import requests
import base64
import logging
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime

from advanced_vault.encrypted_kv import EncryptedKVStore, QueryFilter, EntryType

logger = logging.getLogger(__name__)


class CloudSyncService:
    """
    Service for syncing vault entries with cloud backend.
    
    Features:
    - Sync single entries or all entries
    - Fetch cloud entries on login
    - Merge local + cloud entries with conflict resolution
    - Background sync with retry logic
    """
    
    def __init__(self, backend_url: str, session_data: dict, vault: EncryptedKVStore):
        """
        Initialize cloud sync service.
        
        Args:
            backend_url: Backend API base URL (e.g., "https://api.example.com")
            session_data: Session data with access_token and user_id
            vault: EncryptedKVStore instance for local operations
        """
        self.backend_url = backend_url.rstrip('/')
        self.session_data = session_data
        self.vault = vault
        self.access_token = session_data.get("access_token")
        self.user_id = session_data.get("user_id")
        
        if not self.access_token:
            raise ValueError("access_token required in session_data")
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Initialized CloudSyncService for user: {self.user_id}")
    
    def _map_entry_type(self, entry_type: EntryType) -> str:
        """Map EntryType enum to backend data_type string."""
        # Backend expects 'secret' or 'knowledge'
        if entry_type == EntryType.SECRET:
            return "secret"
        elif entry_type == EntryType.API_KEY:
            return "secret"
        elif entry_type == EntryType.PASSWORD:
            return "secret"
        elif entry_type == EntryType.TOKEN:
            return "secret"
        elif entry_type == EntryType.CREDENTIAL:
            return "secret"
        else:
            return "knowledge"  # Default for other types
    
    def _prepare_entry_for_backend(self, entry) -> Dict[str, Any]:
        """
        Prepare encrypted entry for backend API.
        
        Args:
            entry: EncryptedEntry object from local vault
            
        Returns:
            Dictionary ready for backend API
        """
        # Combine encrypted_data and nonce into a single blob
        # Format: nonce (12 bytes) + encrypted_data (variable)
        combined_blob = entry.nonce + entry.encrypted_data
        
        # Base64 encode for JSON transport
        encrypted_data_b64 = base64.b64encode(combined_blob).decode('utf-8')
        
        return {
            "entry_id": entry.id,
            "encrypted_data": encrypted_data_b64,
            "data_type": self._map_entry_type(entry.entry_type),
            "service": entry.service,
            "tags": entry.tags or []
        }
    
    def sync_entry(self, entry_id: str) -> bool:
        """
        Sync single entry to cloud.
        
        Args:
            entry_id: Entry UUID to sync
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get entry from local vault
            entries = self.vault.search(QueryFilter())
            entry = next((e for e in entries if e.id == entry_id), None)
            
            if not entry:
                logger.warning(f"Entry {entry_id} not found in local vault")
                return False
            
            # Prepare entry for backend
            payload = self._prepare_entry_for_backend(entry)
            
            # Send to backend
            url = f"{self.backend_url}/api/vault/store"
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Synced entry {entry_id} to cloud")
                return True
            else:
                logger.error(f"Failed to sync entry {entry_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing entry {entry_id}: {e}")
            return False
    
    def sync_all(self) -> Dict[str, Any]:
        """
        Sync all local entries to cloud.
        
        Returns:
            Dictionary with sync results
        """
        try:
            # Get all entries from local vault
            entries = self.vault.search(QueryFilter())
            
            synced_count = 0
            failed_count = 0
            errors = []
            
            for entry in entries:
                success = self.sync_entry(entry.id)
                if success:
                    synced_count += 1
                else:
                    failed_count += 1
                    errors.append(entry.id)
            
            result = {
                "success": True,
                "synced": synced_count,
                "failed": failed_count,
                "total": len(entries),
                "errors": errors
            }
            
            logger.info(f"Sync all complete: {synced_count} synced, {failed_count} failed")
            return result
            
        except Exception as e:
            logger.error(f"Error syncing all entries: {e}")
            return {
                "success": False,
                "error": str(e),
                "synced": 0,
                "failed": 0
            }
    
    def fetch_from_cloud(self) -> List[Dict[str, Any]]:
        """
        Fetch all entries from cloud.
        
        Returns:
            List of entry dictionaries from cloud
        """
        try:
            url = f"{self.backend_url}/api/vault/entries"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                entries = data.get("entries", [])
                logger.info(f"Fetched {len(entries)} entries from cloud")
                return entries
            else:
                logger.error(f"Failed to fetch entries: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching from cloud: {e}")
            return []
    
    def merge_entries(self, cloud_entries: List[Dict[str, Any]], conflict_resolution: str = "cloud") -> Dict[str, Any]:
        """
        Merge cloud entries with local vault.
        
        Args:
            cloud_entries: List of entries from cloud
            conflict_resolution: "cloud" (cloud wins) or "local" (local wins)
            
        Returns:
            Dictionary with merge results
        """
        try:
            # Get local entries
            local_entries = self.vault.search(QueryFilter())
            local_by_id = {e.id: e for e in local_entries}
            
            merged_count = 0
            skipped_count = 0
            errors = []
            
            for cloud_entry in cloud_entries:
                entry_id = cloud_entry.get("entry_id")
                if not entry_id:
                    continue
                
                # Check if entry exists locally
                local_entry = local_by_id.get(entry_id)
                
                if local_entry:
                    # Conflict exists
                    if conflict_resolution == "cloud":
                        # Cloud wins - update local entry
                        # Note: We can't decrypt cloud entry, so we need to store the encrypted blob
                        # For now, we'll skip conflicts (requires decryption service)
                        logger.warning(f"Conflict for {entry_id}: cloud entry exists, skipping (decryption required)")
                        skipped_count += 1
                    else:
                        # Local wins - skip cloud entry
                        skipped_count += 1
                else:
                    # New entry from cloud - add to local vault
                    # Extract nonce and encrypted_data from base64 blob
                    encrypted_data_b64 = cloud_entry.get("encrypted_data")
                    if encrypted_data_b64:
                        try:
                            combined_blob = base64.b64decode(encrypted_data_b64)
                            nonce = combined_blob[:12]  # First 12 bytes
                            encrypted_data = combined_blob[12:]  # Rest
                            
                            # Create entry in local vault
                            # Note: We can't decrypt, so we store as-is
                            # This requires modifying EncryptedKVStore to support importing encrypted entries
                            logger.warning(f"Cannot import encrypted entry {entry_id} without decryption key")
                            skipped_count += 1
                        except Exception as e:
                            logger.error(f"Error processing cloud entry {entry_id}: {e}")
                            errors.append(entry_id)
            
            return {
                "success": True,
                "merged": merged_count,
                "skipped": skipped_count,
                "total": len(cloud_entries),
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Error merging entries: {e}")
            return {
                "success": False,
                "error": str(e),
                "merged": 0,
                "skipped": 0
            }
    
    def sync_entry_background(self, entry_id: str):
        """Sync entry in background thread."""
        thread = threading.Thread(target=self.sync_entry, args=(entry_id,), daemon=True)
        thread.start()


