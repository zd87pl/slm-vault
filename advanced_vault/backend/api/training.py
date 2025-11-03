"""Training API endpoints - backend manages RunPod credentials."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase
from utils.access_logger import log_access
from config import settings
import requests
import uuid
import hashlib
import logging
import base64
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


class SubmitTrainingRequest(BaseModel):
    """Request to submit a training job."""
    dataset_url: str  # Signed URL to Supabase Storage dataset
    encryption_key_hex: str  # Hex-encoded encryption key (client-side generated)
    adapter_id: Optional[str] = None  # UUID, auto-generated if not provided
    model_name: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    rank: int = 16
    alpha: int = 32
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 2e-4
    enable_compression: bool = True


class TrainingJobResponse(BaseModel):
    """Training job response."""
    success: bool
    job_id: str  # Backend job ID (not RunPod job ID directly)
    adapter_id: str
    status: str  # pending, training, completed, failed
    submitted_at: str


@router.post("/submit")
async def submit_training_job(
    request: Request,
    data: SubmitTrainingRequest,
    user: dict = Depends(get_current_user)
):
    """
    Submit a training job to RunPod.
    
    Backend manages RunPod credentials - users never see them.
    Frontend only provides dataset URL and encryption key.
    """
    try:
        # Validate RunPod configuration
        if not settings.runpod_api_key or not settings.runpod_endpoint_id:
            raise HTTPException(
                status_code=503,
                detail="Training service is not configured. Please contact support."
            )
        
        # Generate adapter_id if not provided
        adapter_id = data.adapter_id or str(uuid.uuid4())
        user_id = user["user_id"]
        
        # Hash encryption key for storage
        key_bytes = bytes.fromhex(data.encryption_key_hex)
        key_hash = hashlib.sha256(key_bytes).hexdigest()
        
        # Register adapter intent with backend first
        # Use service key to bypass RLS (backend verifies user_id via auth middleware)
        from utils.supabase_client import get_supabase_service
        supabase = get_supabase_service()
        adapter_data = {
            "user_id": user_id,
            "adapter_id": adapter_id,
            "adapter_path": f"/workspace/adapters/{user_id}/{adapter_id}/",
            "encryption_key_hash": key_hash,
            "status": "pending"
        }
        
        try:
            result = supabase.table("user_adapters")\
                .insert(adapter_data)\
                .execute()
            
            if not result.data:
                logger.warning(f"Failed to register adapter {adapter_id}, continuing anyway")
        except Exception as e:
            logger.warning(f"Adapter registration error (non-critical): {e}")
            # Continue anyway - training can proceed without backend registration
        
        # Prepare training config for RunPod
        training_config = {
            "task": "train_and_encrypt",
            "user_id": user_id,
            "adapter_id": adapter_id,
            "dataset": data.dataset_url,  # Signed URL to encrypted dataset in Supabase Storage
            "encryption_key": data.encryption_key_hex,  # Required for decrypting encrypted dataset
            "model_name": data.model_name,
            "output_dir": f"/workspace/adapters/{user_id}/{adapter_id}/",
            "encrypted_output_path": f"/workspace/encrypted/{user_id}/{adapter_id}.json",
            "rank": data.rank,
            "alpha": data.alpha,
            "epochs": data.epochs,
            "batch_size": data.batch_size,
            "learning_rate": data.learning_rate,
            "enable_compression": data.enable_compression,
        }
        
        # Submit job to RunPod (backend uses its own credentials)
        runpod_url = f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/run"
        payload = {"input": training_config}
        
        try:
            runpod_response = requests.post(
                runpod_url,
                headers={
                    "Authorization": f"Bearer {settings.runpod_api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            
            if runpod_response.status_code != 200:
                logger.error(f"RunPod API error: {runpod_response.status_code} {runpod_response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to submit training job to RunPod: {runpod_response.status_code}"
                )
            
            runpod_data = runpod_response.json()
            runpod_job_id = runpod_data.get('id')
            
            if not runpod_job_id:
                raise HTTPException(
                    status_code=502,
                    detail="No job ID returned from RunPod"
                )
            
            # Store job metadata in backend (link backend job_id to RunPod job_id)
            # We'll use adapter_id as the primary identifier and store RunPod job_id
            try:
                supabase.table("user_adapters")\
                    .update({"job_id": runpod_job_id, "status": "pending"})\
                    .eq("user_id", user_id)\
                    .eq("adapter_id", adapter_id)\
                    .execute()
            except Exception as e:
                logger.warning(f"Failed to update adapter with job_id: {e}")
            
            logger.info(f"Submitted training job {runpod_job_id} for adapter {adapter_id} (user {user_id})")
            
            # Log access
            await log_access(
                user_id=user_id,
                operation="training_submit",
                request=request,
                success=True,
                metadata={
                    "adapter_id": adapter_id,
                    "runpod_job_id": runpod_job_id
                }
            )
            
            return {
                "success": True,
                "job_id": adapter_id,  # Use adapter_id as backend job identifier
                "adapter_id": adapter_id,
                "runpod_job_id": runpod_job_id,  # Include for reference
                "status": "pending",
                "submitted_at": datetime.now().isoformat()
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error submitting to RunPod: {e}")
            raise HTTPException(
                status_code=502,
                detail="Failed to connect to training service"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit training job: {e}")
        
        await log_access(
            user_id=user.get("user_id"),
            operation="training_submit",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{adapter_id}")
async def get_training_status(
    adapter_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Get status of a training job.
    
    Backend queries RunPod internally and returns status.
    Users identify jobs by adapter_id.
    """
    try:
        # Validate RunPod configuration
        if not settings.runpod_api_key or not settings.runpod_endpoint_id:
            raise HTTPException(
                status_code=503,
                detail="Training service is not configured"
            )
        
        user_id = user["user_id"]
        
        # Get adapter metadata (includes RunPod job_id) - use service key to bypass RLS
        from utils.supabase_client import get_supabase_service
        supabase = get_supabase_service()
        result = supabase.table("user_adapters")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("adapter_id", adapter_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Training job not found"
            )
        
        adapter = result.data[0]
        runpod_job_id = adapter.get("job_id")
        stored_status = adapter.get("status", "pending")
        
        if not runpod_job_id:
            # Job not yet submitted to RunPod
            return {
                "job_id": adapter_id,
                "adapter_id": adapter_id,
                "status": stored_status,
                "message": "Job is queued"
            }
        
        # Query RunPod for current status
        try:
            runpod_url = f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/status/{runpod_job_id}"
            runpod_response = requests.get(
                runpod_url,
                headers={
                    "Authorization": f"Bearer {settings.runpod_api_key}"
                },
                timeout=10
            )
            
            if runpod_response.status_code != 200:
                logger.warning(f"Failed to get RunPod status: {runpod_response.status_code}")
                # Return stored status if RunPod query fails
                return {
                    "job_id": adapter_id,
                    "adapter_id": adapter_id,
                    "status": stored_status,
                    "message": "Unable to fetch latest status"
                }
            
            runpod_data = runpod_response.json()
            runpod_status = runpod_data.get("status", "UNKNOWN")
            
            # Map RunPod statuses to our statuses
            status_mapping = {
                "IN_QUEUE": "pending",
                "IN_PROGRESS": "training",
                "COMPLETED": "completed",
                "FAILED": "failed"
            }
            
            mapped_status = status_mapping.get(runpod_status, stored_status)
            
            # Update stored status if it changed
            if mapped_status != stored_status:
                try:
                    supabase.table("user_adapters")\
                        .update({"status": mapped_status})\
                        .eq("user_id", user_id)\
                        .eq("adapter_id", adapter_id)\
                        .execute()
                except Exception as e:
                    logger.warning(f"Failed to update adapter status: {e}")
            
            # Include output if completed
            output = None
            if mapped_status == "completed" and "output" in runpod_data:
                output = runpod_data["output"]
            
            # Log access
            await log_access(
                user_id=user_id,
                operation="training_status",
                request=request,
                success=True,
                metadata={"adapter_id": adapter_id, "status": mapped_status}
            )
            
            return {
                "job_id": adapter_id,
                "adapter_id": adapter_id,
                "status": mapped_status,
                "runpod_status": runpod_status,
                "output": output,
                "updated_at": datetime.now().isoformat()
            }
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error querying RunPod: {e}")
            # Return stored status
            return {
                "job_id": adapter_id,
                "adapter_id": adapter_id,
                "status": stored_status,
                "message": "Unable to fetch latest status from training service"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        
        await log_access(
            user_id=user.get("user_id"),
            operation="training_status",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


class UploadDatasetRequest(BaseModel):
    """Request to upload encrypted dataset."""
    encrypted_data: str  # Base64-encoded encrypted dataset
    filename: str  # Dataset filename


class UploadDatasetResponse(BaseModel):
    """Response from dataset upload."""
    success: bool
    dataset_url: str  # Signed URL to download the dataset
    message: str


@router.post("/upload-dataset")
async def upload_dataset(
    request: Request,
    data: UploadDatasetRequest,
    user: dict = Depends(get_current_user)
):
    """
    Upload encrypted dataset to Supabase Storage via backend.
    
    Backend uses service key to bypass RLS - users don't need Supabase tokens.
    Dataset is stored in: datasets/{user_id}/{filename}
    """
    try:
        from utils.supabase_client import get_supabase_service
        
        user_id = user["user_id"]
        
        # Decode base64 encrypted dataset
        try:
            encrypted_blob = base64.b64decode(data.encrypted_data)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 data: {str(e)}"
            )
        
        # Use service key to bypass RLS
        supabase = get_supabase_service()
        
        storage_path = f"{user_id}/{data.filename}"
        bucket_name = "datasets"
        
        logger.info(f"Uploading dataset for user {user_id}: {bucket_name}/{storage_path} ({len(encrypted_blob)} bytes)")
        
        # Upload encrypted blob (service key bypasses RLS)
        try:
            response = supabase.storage.from_(bucket_name).upload(
                path=storage_path,
                file=encrypted_blob,
                file_options={
                    "content-type": "application/json",
                    "upsert": "true"  # Allow overwrite
                }
            )
            
            if not response:
                raise HTTPException(
                    status_code=500,
                    detail="Upload failed: No response from storage"
                )
            
            # Create signed URL (valid for 1 hour)
            signed_url_response = supabase.storage.from_(bucket_name).create_signed_url(
                path=storage_path,
                expires_in=3600
            )
            
            if not signed_url_response or 'signedURL' not in signed_url_response:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create signed URL"
                )
            
            signed_url = signed_url_response['signedURL']
            
            logger.info(f"Dataset uploaded successfully: {storage_path}")
            
            # Log access
            await log_access(
                user_id=user_id,
                operation="dataset_upload",
                request=request,
                success=True,
                metadata={"filename": data.filename, "size": len(encrypted_blob)}
            )
            
            return {
                "success": True,
                "dataset_url": signed_url,
                "message": "Dataset uploaded successfully"
            }
            
        except Exception as upload_error:
            logger.error(f"Storage upload error: {upload_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload dataset: {str(upload_error)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload dataset: {e}")
        
        await log_access(
            user_id=user.get("user_id"),
            operation="dataset_upload",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


class InferenceRequest(BaseModel):
    """Request to run inference with trained adapter."""
    adapter_id: str
    encryption_key_hex: str  # Required for decrypting adapter on RunPod
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7


@router.post("/inference")
async def run_inference(
    request: Request,
    data: InferenceRequest,
    user: dict = Depends(get_current_user)
):
    """
    Run inference with trained adapter (demo query).
    
    Backend handles RunPod inference - users provide prompt, adapter_id, and encryption_key_hex.
    The encryption key is only used for RunPod inference and is never stored.
    """
    try:
        # Validate RunPod configuration
        if not settings.runpod_api_key or not settings.runpod_endpoint_id:
            raise HTTPException(
                status_code=503,
                detail="Inference service is not configured"
            )
        
        user_id = user["user_id"]
        adapter_id = data.adapter_id
        
        # Verify adapter ownership (use service key to bypass RLS)
        from utils.supabase_client import get_supabase_service
        supabase = get_supabase_service()
        result = supabase.table("user_adapters")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("adapter_id", adapter_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Adapter not found or access denied"
            )
        
        adapter = result.data[0]
        
        # Check if adapter is completed
        if adapter.get("status") != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Adapter is not ready for inference (status: {adapter.get('status')})"
            )
        
        # Prepare inference config for RunPod
        encrypted_adapter_path = f"/workspace/encrypted/{user_id}/{adapter_id}.json"
        
        inference_config = {
            "task": "inference",
            "user_id": user_id,
            "adapter_id": adapter_id,
            "encrypted_adapter_path": encrypted_adapter_path,
            "encryption_key": data.encryption_key_hex,  # Pass encryption key to RunPod
            "prompt": data.prompt,
            "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "max_tokens": data.max_tokens,
            "temperature": data.temperature,
            "enable_cache": True
        }
        
        # Submit inference job to RunPod
        runpod_url = f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/run"
        payload = {"input": inference_config}
        
        try:
            runpod_response = requests.post(
                runpod_url,
                headers={
                    "Authorization": f"Bearer {settings.runpod_api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            
            if runpod_response.status_code != 200:
                logger.error(f"RunPod inference error: {runpod_response.status_code} {runpod_response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to submit inference job: {runpod_response.status_code}"
                )
            
            runpod_data = runpod_response.json()
            runpod_job_id = runpod_data.get('id')
            
            if not runpod_job_id:
                raise HTTPException(
                    status_code=502,
                    detail="No job ID returned from RunPod"
                )
            
            # Wait for inference to complete (polling)
            import time
            max_wait = 120  # 2 minutes max
            poll_interval = 2  # Check every 2 seconds
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                status_url = f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/status/{runpod_job_id}"
                status_response = requests.get(
                    status_url,
                    headers={
                        "Authorization": f"Bearer {settings.runpod_api_key}"
                    },
                    timeout=10
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    status = status_data.get("status")
                    
                    if status == "COMPLETED":
                        output = status_data.get("output", {})
                        response_text = output.get("response", "")
                        
                        if not response_text:
                            raise HTTPException(
                                status_code=502,
                                detail="Inference completed but no response returned"
                            )
                        
                        # Log access
                        await log_access(
                            user_id=user_id,
                            operation="inference_query",
                            request=request,
                            success=True,
                            metadata={"adapter_id": adapter_id, "prompt_length": len(data.prompt)}
                        )
                        
                        return {
                            "success": True,
                            "response": response_text,
                            "adapter_id": adapter_id
                        }
                    elif status == "FAILED":
                        error = status_data.get("error", "Unknown error")
                        raise HTTPException(
                            status_code=502,
                            detail=f"Inference failed: {error}"
                        )
                
                time.sleep(poll_interval)
            
            raise HTTPException(
                status_code=504,
                detail="Inference timeout - job took too long"
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during inference: {e}")
            raise HTTPException(
                status_code=502,
                detail="Failed to connect to inference service"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run inference: {e}")
        
        await log_access(
            user_id=user.get("user_id"),
            operation="inference_query",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))
