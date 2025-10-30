"""
Training Manager Service

Manages training job submission to RunPod with user isolation.
Handles adapter registration and tracking.
"""

import logging
import requests
import json
import time
import uuid
import hashlib
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class TrainingManager:
    """
    Service for submitting training jobs to RunPod with user isolation.
    """
    
    def __init__(
        self,
        backend_url: str,
        session_data: dict,
        runpod_endpoint_id: Optional[str] = None,
        runpod_api_key: Optional[str] = None
    ):
        """
        Initialize training manager.
        
        Args:
            backend_url: Backend API base URL
            session_data: Session data with access_token and user_id
            runpod_endpoint_id: RunPod endpoint ID for training
            runpod_api_key: RunPod API key
        """
        self.backend_url = backend_url.rstrip('/')
        self.session_data = session_data
        # Extract user_id from nested structure if needed
        user_info = session_data.get("user", {})
        self.user_id = session_data.get("user_id") or user_info.get("id") or user_info.get("user_id")
        self.access_token = session_data.get("access_token")
        
        self.runpod_endpoint_id = runpod_endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        self.runpod_api_key = runpod_api_key or os.getenv("RUNPOD_API_KEY")
        self.runpod_base_url = f"https://api.runpod.ai/v2/{self.runpod_endpoint_id}" if self.runpod_endpoint_id else None
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Initialize Supabase client for secure storage
        # Get Supabase credentials from environment variables
        # Set SUPABASE_URL and SUPABASE_ANON_KEY in launch script or environment
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        
        if supabase_url and supabase_anon_key:
            try:
                self.supabase = create_client(supabase_url, supabase_anon_key)
                # Set the session for authenticated storage operations
                # Note: Storage operations work with anon key + access token in headers
                # We don't need to set_session here - the storage API uses the access token
                # when making requests via the authenticated client
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client: {e}")
                self.supabase = None
        else:
            self.supabase = None
            if not supabase_url:
                logger.warning("SUPABASE_URL not set - secure storage unavailable")
            if not supabase_anon_key:
                logger.warning("SUPABASE_ANON_KEY not set - secure storage unavailable")
        
        # Create datasets directory
        if self.user_id:
            self.datasets_dir = Path("~/.vault/datasets").expanduser() / self.user_id
            self.datasets_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.datasets_dir = None
            logger.warning("TrainingManager initialized without user_id - datasets directory not created")
        
        logger.info(f"Initialized TrainingManager for user: {self.user_id}")
    
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
        Submit training job to RunPod with user isolation.
        
        Args:
            dataset_path: Path to training dataset (JSONL)
            encryption_key_hex: Hex-encoded encryption key (generated client-side)
            adapter_id: Adapter UUID (auto-generated if None)
            model_name: Base model name
            **kwargs: Additional training parameters
            
        Returns:
            Dictionary with job_id, adapter_id, status
        """
        if not self.runpod_endpoint_id or not self.runpod_api_key:
            raise ValueError("RunPod endpoint not configured")
        
        # Generate adapter_id if not provided
        if not adapter_id:
            adapter_id = str(uuid.uuid4())
        
        # Try to register adapter intent with backend (non-blocking - don't fail if backend auth fails)
        try:
            registration_success = self.register_adapter_intent(adapter_id, encryption_key_hex)
            if not registration_success:
                logger.warning("Adapter registration failed (backend auth issue), continuing with training anyway")
        except Exception as e:
            logger.warning(f"Adapter registration error (non-critical): {e}")
            # Continue anyway - training can proceed without backend registration
        
        # Upload dataset to secure Supabase Storage
        dataset_url = self._upload_dataset_to_supabase_storage(dataset_path)
        
        if not dataset_url:
            logger.error(f"Failed to upload dataset to secure storage. Dataset saved locally at: {dataset_path}")
            raise ValueError(
                "Failed to upload dataset to secure storage. "
                "RunPod requires a URL-accessible dataset file. "
                "Please ensure Supabase Storage is configured and accessible."
            )
        
        # Prepare training config
        training_config = {
            "task": "train_and_encrypt",
            "user_id": self.user_id,
            "adapter_id": adapter_id,
            "dataset": dataset_url,  # Signed URL to secure Supabase Storage
            "model_name": model_name,
            "encryption_key": encryption_key_hex,
            "output_dir": f"/workspace/adapters/{self.user_id}/{adapter_id}/",
            "encrypted_output_path": f"/workspace/encrypted/{self.user_id}/{adapter_id}.json",
            "rank": kwargs.get("rank", 16),
            "alpha": kwargs.get("alpha", 32),
            "epochs": kwargs.get("epochs", 3),
            "batch_size": kwargs.get("batch_size", 4),
            "learning_rate": kwargs.get("learning_rate", 2e-4),
            "enable_compression": kwargs.get("enable_compression", True),
        }
        
        # Submit job to RunPod
        payload = {
            "input": training_config
        }
        
        try:
            response = requests.post(
                f"{self.runpod_base_url}/run",
                headers={
                    "Authorization": f"Bearer {self.runpod_api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to submit training job: {response.status_code} {response.text}")
            
            job_data = response.json()
            runpod_job_id = job_data.get('id')
            
            if not runpod_job_id:
                raise Exception(f"No job ID in response: {job_data}")
            
            logger.info(f"Submitted training job {runpod_job_id} for adapter {adapter_id}")
            
            return {
                "success": True,
                "runpod_job_id": runpod_job_id,
                "adapter_id": adapter_id,
                "user_id": self.user_id,
                "status": "pending",
                "submitted_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error submitting training job: {e}")
            raise
    
    def get_job_status(self, runpod_job_id: str) -> Dict[str, Any]:
        """
        Get status of RunPod training job.
        
        Args:
            runpod_job_id: RunPod job ID
            
        Returns:
            Job status dictionary
        """
        if not self.runpod_endpoint_id or not self.runpod_api_key:
            raise ValueError("RunPod endpoint not configured")
        
        try:
            response = requests.get(
                f"{self.runpod_base_url}/status/{runpod_job_id}",
                headers={
                    "Authorization": f"Bearer {self.runpod_api_key}"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get job status: {response.status_code}")
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            raise
    
    def save_dataset(self, qa_pairs: List[Dict[str, str]], filename: str) -> str:
        """
        Save training dataset to local storage.
        
        Args:
            qa_pairs: List of Q&A pairs
            filename: Dataset filename
            
        Returns:
            Path to saved dataset file
        """
        if not self.datasets_dir:
            raise ValueError("Cannot save dataset: datasets_dir not initialized (user_id missing)")
        
        dataset_path = self.datasets_dir / filename
        
        with open(dataset_path, 'w') as f:
            for pair in qa_pairs:
                record = {
                    "instruction": pair.get("instruction", ""),
                    "input": "",
                    "output": pair.get("output", "")
                }
                f.write(json.dumps(record) + '\n')
        
        logger.info(f"Saved dataset with {len(qa_pairs)} pairs to {dataset_path}")
        return str(dataset_path)
    
    def _upload_dataset_to_supabase_storage(self, dataset_path: str) -> Optional[str]:
        """
        Upload dataset to Supabase Storage securely.
        
        Files are stored in: datasets/{user_id}/{filename}
        Access is controlled via RLS policies set in Supabase dashboard.
        
        Args:
            dataset_path: Local path to dataset file
            
        Returns:
            Signed URL to download the dataset (valid for 1 hour) or None if failed
        """
        if not self.supabase or not self.user_id:
            logger.error("Supabase client not initialized or user_id missing")
            return None
        
        try:
            # Read dataset file
            with open(dataset_path, 'rb') as f:
                dataset_content = f.read()
            
            filename = os.path.basename(dataset_path)
            storage_path = f"{self.user_id}/{filename}"
            bucket_name = "datasets"
            
            logger.info(f"Uploading dataset to Supabase Storage: {bucket_name}/{storage_path} ({len(dataset_content)} bytes)")
            
            # Upload file to Supabase Storage
            # For authenticated storage operations with RLS, we need to set the session
            # Set session if we have both access_token and refresh_token
            if self.access_token and self.session_data.get("refresh_token"):
                try:
                    self.supabase.auth.set_session(
                        access_token=self.access_token,
                        refresh_token=self.session_data.get("refresh_token")
                    )
                except Exception as session_error:
                    logger.warning(f"Failed to set session (will try without): {session_error}")
            
            # Try upload
            try:
                response = self.supabase.storage.from_(bucket_name).upload(
                    path=storage_path,
                    file=dataset_content,
                    file_options={
                        "content-type": "application/jsonl",
                        "upsert": "false"  # Don't overwrite existing files
                    }
                )
            except Exception as upload_error:
                logger.error(f"Upload failed: {upload_error}")
                return None
            
            if response:
                # Get signed URL (valid for 1 hour)
                signed_url_response = self.supabase.storage.from_(bucket_name).create_signed_url(
                    path=storage_path,
                    expires_in=3600  # 1 hour
                )
                
                if signed_url_response and 'signedURL' in signed_url_response:
                    signed_url = signed_url_response['signedURL']
                    logger.info(f"Dataset uploaded successfully to Supabase Storage")
                    logger.info(f"Signed URL expires in 1 hour")
                    return signed_url
                else:
                    logger.error(f"Failed to create signed URL: {signed_url_response}")
                    return None
            else:
                logger.error(f"Upload failed: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error uploading dataset to Supabase Storage: {e}")
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
            
            if response.status_code == 200:
                logger.info(f"Updated adapter {adapter_id} status to {status}")
                return True
            else:
                logger.error(f"Failed to update adapter status: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating adapter status: {e}")
            return False


