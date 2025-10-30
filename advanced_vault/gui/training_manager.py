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
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

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
        
        # Prepare training config
        # Upload dataset to cloud storage and get URL
        dataset_url = self._upload_dataset_temporary(dataset_path)
        
        if not dataset_url:
            logger.error(f"Failed to upload dataset. Dataset saved locally at: {dataset_path}")
            raise ValueError(
                "Failed to upload dataset to cloud storage. "
                "RunPod requires a URL-accessible dataset file. "
                f"Local path: {dataset_path}"
            )
        
        training_config = {
            "task": "train_and_encrypt",
            "user_id": self.user_id,
            "adapter_id": adapter_id,
            "dataset": dataset_url,  # URL to dataset file
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
    
    def _upload_dataset_temporary(self, dataset_path: str) -> Optional[str]:
        """
        Upload dataset to temporary file hosting service.
        
        TODO: Replace with Supabase Storage upload for production.
        
        Args:
            dataset_path: Local path to dataset file
            
        Returns:
            Public URL to dataset file or None if failed
        """
        try:
            # Read dataset file
            with open(dataset_path, 'rb') as f:
                dataset_content = f.read()
            
            # Try uploading to file.io (temporary file hosting)
            # This is a simple solution for testing - replace with Supabase Storage in production
            logger.info("Uploading dataset to temporary hosting...")
            
            files = {'file': (os.path.basename(dataset_path), dataset_content, 'application/jsonl')}
            response = requests.post(
                'https://file.io',
                files=files,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    url = result.get('link')
                    logger.info(f"Dataset uploaded successfully: {url}")
                    return url
                else:
                    logger.error(f"File.io upload failed: {result}")
            else:
                logger.error(f"File.io upload failed: {response.status_code} {response.text}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error uploading dataset: {e}")
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


