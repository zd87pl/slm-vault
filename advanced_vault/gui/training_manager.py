"""
Training Manager Service

Manages training job submission via backend API.
Backend handles all RunPod communication - users never see RunPod credentials.
"""

import logging
import requests
import json
import time
import uuid
import hashlib
import os
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
# Supabase client no longer needed - backend handles storage

# Encryption imports - use PyCryptodome for consistency with DoRA adapters
CRYPTO_BACKEND = None
try:
    from Crypto.Cipher import ChaCha20_Poly1305
    from Crypto.Random import get_random_bytes
    CRYPTO_AVAILABLE = True
    CRYPTO_BACKEND = "pycryptodome"
except ImportError:
    # Fallback to cryptography library if PyCryptodome not available
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        CRYPTO_AVAILABLE = True
        CRYPTO_BACKEND = "cryptography"
    except ImportError:
        CRYPTO_AVAILABLE = False
        CRYPTO_BACKEND = None

logger = logging.getLogger(__name__)


class TrainingManager:
    """
    Service for submitting training jobs via backend API.
    
    Backend manages RunPod credentials - frontend never touches them.
    """
    
    def __init__(
        self,
        backend_url: str,
        session_data: dict,
        supabase_client=None,
        supabase_url: Optional[str] = None,
        supabase_anon_key: Optional[str] = None
    ):
        """
        Initialize training manager.
        
        Args:
            backend_url: Backend API base URL
            session_data: Session data with access_token and user_id
            supabase_client: Supabase client instance (for token refresh)
            supabase_url: Supabase URL (for dataset storage, optional)
            supabase_anon_key: Supabase anon key (for dataset storage, optional)
        """
        self.backend_url = backend_url.rstrip('/')
        self.session_data = session_data
        # Extract user_id from nested structure if needed
        user_info = session_data.get("user", {})
        self.user_id = session_data.get("user_id") or user_info.get("id") or user_info.get("user_id")
        self.access_token = session_data.get("access_token")
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Store Supabase client for token refresh (same approach as CloudSyncService)
        self.supabase_client = supabase_client
        
        # Note: We no longer initialize Supabase client here for storage
        # Dataset uploads go through backend API which uses service key
        # This avoids RLS issues and token management in GUI
        self.supabase = None  # Not needed - backend handles storage
        
        # Create datasets directory
        if self.user_id:
            self.datasets_dir = Path("~/.vault/datasets").expanduser() / self.user_id
            self.datasets_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.datasets_dir = None
            logger.warning("TrainingManager initialized without user_id - datasets directory not created")
        
        logger.info(f"Initialized TrainingManager for user: {self.user_id}")
    
    def _sync_token_from_session_data(self) -> None:
        """
        Sync access token from session_data if it was updated by another service.
        
        This prevents "Already Used" errors when CloudSyncService refreshes the token
        and TrainingManager tries to use the old refresh token.
        """
        current_access_token = self.session_data.get("access_token")
        if current_access_token and current_access_token != self.access_token:
            logger.debug("Syncing access token from session_data (updated by another service)")
            self.access_token = current_access_token
            self.headers["Authorization"] = f"Bearer {self.access_token}"
    
    def _is_token_expired(self) -> bool:
        """
        Check if access token is expired or will expire soon.
        
        Returns:
            True if token is expired or will expire in < 60 seconds
        """
        expires_at = self.session_data.get("expires_at")
        if not expires_at:
            # No expiry info, assume token might be expired if we get 401
            return False
        
        # Refresh if token expires in < 60 seconds
        return time.time() >= (expires_at - 60)
    
    def _refresh_token_if_needed(self, response: Optional[requests.Response] = None) -> bool:
        """
        Refresh access token if needed (on 401 errors or proactively).
        
        Uses Supabase client directly (same approach as CloudSyncService) for reliability.
        Falls back to backend API if Supabase client not available.
        
        IMPORTANT: Checks if session_data has been updated by another service (e.g., CloudSyncService)
        before attempting refresh to avoid "Already Used" errors.
        
        Args:
            response: Optional response object to check status code
            
        Returns:
            True if token was refreshed or not needed, False if refresh failed
        """
        # Check if we need to refresh (401 error)
        if response and response.status_code != 401:
            return True
        
        # IMPORTANT: First, sync with session_data in case another service refreshed the token
        # This prevents "Already Used" errors when multiple services share the same session_data
        old_token = self.access_token
        self._sync_token_from_session_data()
        # If token was synced and changed, we got a fresh token from another service
        if old_token != self.access_token:
            logger.info("Token synced from session_data (updated by another service), using it")
            return True
        
        refresh_token = self.session_data.get("refresh_token")
        if not refresh_token:
            logger.warning("No refresh token available")
            return False
        
        # Prefer Supabase client directly (more reliable, same as CloudSyncService)
        if self.supabase_client:
            try:
                session = self.supabase_client.auth.refresh_session(refresh_token)
                
                # Update tokens
                new_access_token = session.session.access_token
                new_refresh_token = session.session.refresh_token
                
                # Update session data
                self.session_data["access_token"] = new_access_token
                self.session_data["refresh_token"] = new_refresh_token
                self.access_token = new_access_token
                
                # Update headers
                self.headers["Authorization"] = f"Bearer {self.access_token}"
                
                logger.info("Token refreshed successfully via Supabase client")
                return True
                
            except Exception as e:
                error_msg = str(e)
                # If token was already used, check if session_data was updated by another service
                if "Already Used" in error_msg or "already used" in error_msg.lower():
                    logger.warning("Refresh token already used, checking if updated by another service...")
                    # Sync token from session_data (may have been updated by CloudSyncService)
                    old_token = self.access_token
                    self._sync_token_from_session_data()
                    if old_token != self.access_token:
                        logger.info("Token was refreshed by another service, synced successfully")
                        return True
                    else:
                        logger.error("Refresh token already used and no update found in session_data. User needs to log in again.")
                        # IMPORTANT: Don't try backend API fallback - it uses the same refresh token
                        return False
                
                logger.error(f"Failed to refresh token via Supabase client: {e}")
                # Fall through to backend API fallback (only if NOT "Already Used")
        
        # Fallback to backend API if Supabase client not available or failed
        try:
            # Refresh via backend API
            # Backend expects refresh_token as JSON body (RefreshTokenRequest model)
            refresh_response = requests.post(
                f"{self.backend_url}/api/auth/refresh",
                json={"refresh_token": refresh_token},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if refresh_response.status_code == 200:
                data = refresh_response.json()
                session_data = data.get("session", {})
                new_access_token = session_data.get("access_token")
                new_refresh_token = session_data.get("refresh_token")
                
                if new_access_token:
                    # Update tokens
                    self.session_data["access_token"] = new_access_token
                    self.session_data["refresh_token"] = new_refresh_token or refresh_token
                    self.access_token = new_access_token
                    
                    # Update headers
                    self.headers["Authorization"] = f"Bearer {self.access_token}"
                    
                    logger.info("Token refreshed successfully via backend API")
                    return True
                else:
                    logger.error("Backend refresh response missing access_token")
                    return False
            else:
                logger.error(f"Backend refresh failed: {refresh_response.status_code} - {refresh_response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to refresh token via backend API: {e}")
            return False
    
    def hash_encryption_key(self, key_hex: str) -> str:
        """Hash encryption key for storage."""
        key_bytes = bytes.fromhex(key_hex)
        return hashlib.sha256(key_bytes).hexdigest()
    
    def register_adapter_intent(self, adapter_id: str, encryption_key_hex: str) -> bool:
        """
        Register adapter intent with backend before training.
        
        Args:
            adapter_id: Adapter UUID
            encryption_key_hex: Hex-encoded encryption key
            
        Returns:
            True if successful
        """
        try:
            key_hash = self.hash_encryption_key(encryption_key_hex)
            
            payload = {
                "adapter_id": adapter_id,
                "adapter_path": f"/workspace/adapters/{self.user_id}/{adapter_id}/",
                "encryption_key_hash": key_hash,
                "status": "pending"
            }
            
            response = requests.post(
                f"{self.backend_url}/api/adapters/register",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            
            # Refresh token on 401 error
            if response.status_code == 401:
                if self._refresh_token_if_needed(response):
                    # Retry with new token
                    response = requests.post(
                        f"{self.backend_url}/api/adapters/register",
                        headers=self.headers,
                        json=payload,
                        timeout=10
                    )
            
            if response.status_code == 200:
                logger.info(f"Registered adapter intent: {adapter_id}")
                return True
            else:
                logger.error(f"Failed to register adapter: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error registering adapter intent: {e}")
            return False
    
    def submit_training_job(
        self,
        dataset_path: str,
        encryption_key_hex: str,
        adapter_id: Optional[str] = None,
        model_name: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submit training job via backend API.
        
        Backend handles RunPod communication - users never see RunPod credentials.
        
        Args:
            dataset_path: Path to training dataset (JSONL)
            encryption_key_hex: Hex-encoded encryption key (generated client-side)
            adapter_id: Adapter UUID (auto-generated if None)
            model_name: Base model name
            **kwargs: Additional training parameters (rank, alpha, epochs, etc.)
            
        Returns:
            Dictionary with job_id (adapter_id), adapter_id, status
        """
        # Generate adapter_id if not provided
        if not adapter_id:
            adapter_id = str(uuid.uuid4())
        
        # Upload dataset to secure Supabase Storage (required for backend to access)
        dataset_url = self._upload_dataset_to_supabase_storage(dataset_path)
        
        if not dataset_url:
            logger.error(f"Failed to upload dataset to secure storage. Dataset saved locally at: {dataset_path}")
            raise ValueError(
                "Failed to upload dataset to secure storage. "
                "Training requires a URL-accessible dataset file. "
                "Please ensure Supabase Storage is configured and accessible."
            )
        
        # Prepare training request for backend API
        payload = {
            "dataset_url": dataset_url,  # Signed URL to Supabase Storage
            "encryption_key_hex": encryption_key_hex,
            "adapter_id": adapter_id,
            "model_name": model_name,
            "rank": kwargs.get("rank", 16),
            "alpha": kwargs.get("alpha", 32),
            "epochs": kwargs.get("epochs", 3),
            "batch_size": kwargs.get("batch_size", 4),
            "learning_rate": kwargs.get("learning_rate", 2e-4),
            "enable_compression": kwargs.get("enable_compression", True),
        }
        
        # Submit job via backend API (backend handles RunPod)
        try:
            response = requests.post(
                f"{self.backend_url}/api/training/submit",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            # Refresh token on 401 error
            if response.status_code == 401:
                if self._refresh_token_if_needed(response):
                    # Retry with new token
                    response = requests.post(
                        f"{self.backend_url}/api/training/submit",
                        headers=self.headers,
                        json=payload,
                        timeout=30
                    )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Backend API error: {response.status_code} {error_text}")
                
                # Provide user-friendly error messages
                if response.status_code == 503:
                    raise ValueError(
                        "Training service is not configured. Please contact support."
                    )
                elif response.status_code == 502:
                    raise ValueError(
                        "Training service is temporarily unavailable. Please try again later."
                    )
                else:
                    raise ValueError(f"Failed to submit training job: {response.status_code}")
            
            result = response.json()
            
            logger.info(f"Submitted training job for adapter {adapter_id}")
            
            return {
                "success": True,
                "job_id": result.get("job_id", adapter_id),  # Backend uses adapter_id as job_id
                "adapter_id": adapter_id,
                "runpod_job_id": result.get("runpod_job_id"),  # For reference
                "user_id": self.user_id,
                "status": result.get("status", "pending"),
                "submitted_at": result.get("submitted_at", datetime.now().isoformat())
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error submitting training job: {e}")
            raise ValueError("Failed to connect to training service. Please check your connection.")
        except ValueError:
            raise  # Re-raise ValueError as-is
        except Exception as e:
            logger.error(f"Error submitting training job: {e}")
            raise ValueError(f"Failed to submit training job: {str(e)}")
    
    def get_job_status(self, adapter_id: str) -> Dict[str, Any]:
        """
        Get status of training job via backend API.
        
        Backend queries RunPod internally and returns status.
        
        Args:
            adapter_id: Adapter UUID (used as job identifier)
            
        Returns:
            Job status dictionary with status, output (if completed), etc.
        """
        try:
            response = requests.get(
                f"{self.backend_url}/api/training/status/{adapter_id}",
                headers=self.headers,
                timeout=10
            )
            
            # Refresh token on 401 error
            if response.status_code == 401:
                if self._refresh_token_if_needed(response):
                    # Retry with new token
                    response = requests.get(
                        f"{self.backend_url}/api/training/status/{adapter_id}",
                        headers=self.headers,
                        timeout=10
                    )
            
            if response.status_code == 404:
                raise ValueError(f"Training job not found: {adapter_id}")
            elif response.status_code != 200:
                error_text = response.text
                logger.error(f"Backend API error: {response.status_code} {error_text}")
                
                if response.status_code == 503:
                    raise ValueError("Training service is not configured")
                else:
                    raise ValueError(f"Failed to get job status: {response.status_code}")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error getting job status: {e}")
            raise ValueError("Failed to connect to training service. Please check your connection.")
        except ValueError:
            raise  # Re-raise ValueError as-is
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            raise ValueError(f"Failed to get job status: {str(e)}")
    
    def get_training_status(self, adapter_id: str) -> Dict[str, Any]:
        """
        Alias for get_job_status (for compatibility).
        
        Get status of training job via backend API.
        """
        return self.get_job_status(adapter_id)
    
    def encrypt_dataset_in_memory(
        self, 
        qa_pairs: List[Dict[str, str]], 
        encryption_key: bytes
    ) -> Dict[str, Any]:
        """
        Encrypt dataset in memory using XChaCha20-Poly1305.
        
        NEVER persists plaintext - encrypts immediately after generation.
        
        Args:
            qa_pairs: List of Q&A pairs (plaintext in memory only)
            encryption_key: 32-byte encryption key
            
        Returns:
            Encrypted dataset package (dict with nonce, ciphertext, tag, etc.)
        """
        if not CRYPTO_AVAILABLE:
            raise ValueError("Encryption library not available. Install pycryptodome or cryptography.")
        
        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be exactly 32 bytes")
        
        # Validate Q&A pairs format
        if not isinstance(qa_pairs, list):
            raise ValueError(f"Q&A pairs must be a list, got {type(qa_pairs)}")
        
        if len(qa_pairs) == 0:
            raise ValueError("Cannot encrypt empty Q&A pairs list")
        
        # Validate each pair has required fields
        for i, pair in enumerate(qa_pairs):
            if not isinstance(pair, dict):
                raise ValueError(f"Q&A pair {i} must be a dict, got {type(pair)}")
            if 'instruction' not in pair or 'output' not in pair:
                raise ValueError(f"Q&A pair {i} missing required fields: 'instruction' or 'output'")
        
        # Serialize Q&A pairs to JSON
        dataset_json = json.dumps(qa_pairs, ensure_ascii=False)
        dataset_bytes = dataset_json.encode('utf-8')
        
        # Generate nonce and encrypt based on backend
        if CRYPTO_BACKEND == "cryptography":
            # Use cryptography library (ChaCha20-Poly1305 with 12-byte nonce)
            nonce = os.urandom(12)  # 12 bytes for ChaCha20Poly1305
            cipher = ChaCha20Poly1305(encryption_key)
            # encrypt() returns ciphertext + tag concatenated
            ciphertext_with_tag = cipher.encrypt(nonce, dataset_bytes, None)
            # Extract tag (last 16 bytes) and ciphertext
            tag = ciphertext_with_tag[-16:]
            ciphertext_only = ciphertext_with_tag[:-16]
            algorithm = "ChaCha20-Poly1305"
        else:
            # Use PyCryptodome (XChaCha20-Poly1305 with 24-byte nonce)
            nonce = get_random_bytes(24)  # 192-bit nonce for XChaCha20
            cipher = ChaCha20_Poly1305.new(key=encryption_key, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(dataset_bytes)
            ciphertext_only = ciphertext
            algorithm = "XChaCha20-Poly1305"
        
        # Package encrypted data
        encrypted_package = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext_only).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'algorithm': algorithm,
            'version': '1.0',
            'num_pairs': len(qa_pairs)  # Metadata only
        }
        
        logger.info(f"Encrypted dataset with {len(qa_pairs)} Q&A pairs")
        return encrypted_package
    
    def save_dataset(
        self, 
        qa_pairs: List[Dict[str, str]], 
        filename: str,
        encryption_key: Optional[bytes] = None
    ) -> str:
        """
        Save training dataset - ENCRYPTED ONLY.
        
        NEVER persists plaintext datasets. Encrypts immediately after generation.
        
        Args:
            qa_pairs: List of Q&A pairs (plaintext in memory only)
            filename: Dataset filename (without extension)
            encryption_key: 32-byte encryption key (generated if not provided)
            
        Returns:
            Path to saved encrypted dataset file
        """
        if not self.datasets_dir:
            raise ValueError("Cannot save dataset: datasets_dir not initialized (user_id missing)")
        
        # Generate encryption key if not provided
        if encryption_key is None:
            encryption_key = os.urandom(32)
            logger.info("Generated new encryption key for dataset")
        
        # Encrypt dataset in memory (never persist plaintext)
        encrypted_package = self.encrypt_dataset_in_memory(qa_pairs, encryption_key)
        
        # Save encrypted dataset only
        encrypted_filename = f"{filename}.encrypted"
        encrypted_path = self.datasets_dir / encrypted_filename
        
        with open(encrypted_path, 'w') as f:
            json.dump(encrypted_package, f, indent=2)
        
        logger.info(f"Saved encrypted dataset to {encrypted_path}")
        
        # Save encryption key to separate file for resume functionality
        # This allows resuming training if upload fails (session expiration, etc.)
        # The key file is stored alongside the encrypted dataset
        key_path = encrypted_path.with_suffix('.key')
        key_path.write_text(encryption_key.hex())
        logger.debug(f"Saved encryption key to {key_path}")
        
        return str(encrypted_path)
    
    def _upload_dataset_to_supabase_storage(self, dataset_path: str) -> Optional[str]:
        """
        Upload encrypted dataset to Supabase Storage via backend API.
        
        Backend uses service key to bypass RLS - no need for user tokens.
        This is the correct approach: GUI should not directly access Supabase Storage.
        
        Args:
            dataset_path: Local path to encrypted dataset file
            
        Returns:
            Signed URL to download the encrypted dataset (valid for 1 hour) or None if failed
        """
        if not self.backend_url or not self.user_id:
            logger.error("Backend URL or user_id missing")
            return None
        
        try:
            # Read encrypted dataset file
            with open(dataset_path, 'rb') as f:
                encrypted_blob = f.read()
            
            filename = os.path.basename(dataset_path)
            
            logger.info(f"Uploading encrypted dataset via backend: {filename} ({len(encrypted_blob)} bytes)")
            
            # Sync token from session_data before request (may have been updated by CloudSyncService)
            self._sync_token_from_session_data()
            
            # Proactively refresh token if expired or expiring soon
            if self._is_token_expired():
                logger.info("Access token expired or expiring soon, refreshing proactively...")
                if not self._refresh_token_if_needed():
                    logger.error("Failed to refresh expired token. User may need to log in again.")
                    raise Exception("Session expired. Please log out and log in again to continue.")
            
            # Encode as base64 for JSON transport
            encrypted_data_b64 = base64.b64encode(encrypted_blob).decode('utf-8')
            
            # Upload via backend API
            payload = {
                "encrypted_data": encrypted_data_b64,
                "filename": filename
            }
            
            response = requests.post(
                f"{self.backend_url}/api/training/upload-dataset",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            # Refresh token on 401 error
            if response.status_code == 401:
                if self._refresh_token_if_needed(response):
                    # Retry with new token
                    response = requests.post(
                        f"{self.backend_url}/api/training/upload-dataset",
                        headers=self.headers,
                        json=payload,
                        timeout=60
                    )
                else:
                    # Token refresh failed - user needs to re-authenticate
                    raise Exception("Session expired. Please log out and log in again to upload datasets.")
            
            if response.status_code == 200:
                result = response.json()
                dataset_url = result.get("dataset_url")
                if dataset_url:
                    logger.info(f"Dataset uploaded successfully via backend: {dataset_url}")
                    return dataset_url
                else:
                    logger.error(f"Backend response missing dataset_url: {result}")
                    return None
            else:
                logger.error(f"Backend upload failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error uploading dataset via backend: {e}")
            return None
    
    def update_adapter_status(
        self,
        adapter_id: str,
        status: str,
        training_metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update adapter status in backend.
        
        Args:
            adapter_id: Adapter UUID
            status: New status (pending, training, completed, failed)
            training_metrics: Optional training metrics
            
        Returns:
            True if successful
        """
        try:
            payload = {
                "status": status
            }
            if training_metrics:
                payload["training_metrics"] = training_metrics
            
            response = requests.patch(
                f"{self.backend_url}/api/adapters/{adapter_id}/status",
                headers=self.headers,
                params={"status": status},
                json=payload if training_metrics else None,
                timeout=10
            )
            
            # Refresh token on 401 error
            if response.status_code == 401:
                if self._refresh_token_if_needed(response):
                    # Retry with new token
                    response = requests.patch(
                        f"{self.backend_url}/api/adapters/{adapter_id}/status",
                        headers=self.headers,
                        params={"status": status},
                        json=payload if training_metrics else None,
                        timeout=10
                    )
            
            if response.status_code == 200:
                logger.info(f"Updated adapter {adapter_id} status to {status}")
                return True
            else:
                logger.error(f"Failed to update adapter status: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating adapter status: {e}")
            return False
    
    def inference_with_adapter(
        self,
        adapter_id: str,
        query: str,
        encryption_key_hex: str,
        max_tokens: int = 512,  # Increased for better responses
        temperature: float = 0.3  # Lower temperature for more precise, deterministic responses
    ) -> Dict[str, Any]:
        """
        Run inference with trained adapter (demo query).
        
        Args:
            adapter_id: Adapter UUID
            query: User's question/prompt
            encryption_key_hex: Hex-encoded encryption key for decrypting adapter
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            
        Returns:
            Dictionary with "response" field containing model's answer
        """
        try:
            payload = {
                "adapter_id": adapter_id,
                "encryption_key_hex": encryption_key_hex,
                "prompt": query,  # Backend expects "prompt"
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            response = requests.post(
                f"{self.backend_url}/api/training/inference",
                headers=self.headers,
                json=payload,
                timeout=240  # Increased: RunPod cold start (30-60s) + inference (10-30s) + backend processing = up to 180s
            )
            
            # Refresh token on 401 error
            if response.status_code == 401:
                if self._refresh_token_if_needed(response):
                    # Retry with new token
                    response = requests.post(
                        f"{self.backend_url}/api/training/inference",
                        headers=self.headers,
                        json=payload,
                        timeout=240  # Increased timeout for retry
                    )
                else:
                    raise ValueError("Session expired. Please sign in again to continue cloud inference.")
            
            if response.status_code == 404:
                raise ValueError("Adapter not found or access denied")
            elif response.status_code == 400:
                error_data = response.json()
                raise ValueError(error_data.get("detail", "Adapter is not ready for inference"))
            elif response.status_code == 503:
                raise ValueError("Inference service is not configured")
            elif response.status_code != 200:
                error_text = response.text
                logger.error(f"Backend API error: {response.status_code} {error_text}")
                if response.status_code == 401:
                    raise ValueError("Session expired. Please sign in again to continue cloud inference.")
                raise ValueError(f"Failed to run inference: {response.status_code}")
            
            result = response.json()
            
            # Backend returns {"response": "..."}
            if "response" not in result:
                logger.warning(f"Unexpected inference response format: {result}")
                raise ValueError("Invalid response from inference service")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error running inference: {e}")
            raise ValueError("Failed to connect to inference service. Please check your connection.")
        except ValueError:
            raise  # Re-raise ValueError as-is
        except Exception as e:
            logger.error(f"Error running inference: {e}")
            raise ValueError(f"Failed to run inference: {str(e)}")

