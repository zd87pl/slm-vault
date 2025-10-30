"""Adapter registry API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase
from utils.access_logger import log_access
import hashlib
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterAdapterRequest(BaseModel):
    """Request to register adapter metadata."""
    adapter_id: Optional[str] = None  # UUID, auto-generated if not provided
    adapter_path: str
    encryption_key_hash: str  # SHA256 hash of encryption key
    job_id: Optional[str] = None  # RunPod job ID
    status: str = "pending"  # pending, training, completed, failed


class AdapterResponse(BaseModel):
    """Adapter metadata response."""
    id: str
    adapter_id: str
    adapter_path: str
    encryption_key_hash: str
    job_id: Optional[str]
    status: str
    training_metrics: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str


@router.post("/register")
async def register_adapter(
    request: Request,
    data: RegisterAdapterRequest,
    user: dict = Depends(get_current_user)
):
    """
    Register adapter metadata with user_id.
    
    All encryption happens client-side. Server stores metadata only.
    """
    try:
        supabase = get_supabase()
        
        # Generate adapter_id if not provided
        import uuid
        adapter_id = data.adapter_id or str(uuid.uuid4())
        
        # Verify encryption_key_hash format (should be SHA256 hex)
        if len(data.encryption_key_hash) != 64:  # SHA256 = 64 hex chars
            raise HTTPException(
                status_code=400,
                detail="encryption_key_hash must be SHA256 hash (64 hex characters)"
            )
        
        # Insert adapter metadata
        adapter_data = {
            "user_id": user["user_id"],
            "adapter_id": adapter_id,
            "adapter_path": data.adapter_path,
            "encryption_key_hash": data.encryption_key_hash,
            "job_id": data.job_id,
            "status": data.status,
        }
        
        result = supabase.table("user_adapters")\
            .insert(adapter_data)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to register adapter"
            )
        
        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="adapter_register",
            request=request,
            success=True,
            metadata={"adapter_id": adapter_id}
        )
        
        return {
            "success": True,
            "adapter_id": adapter_id,
            "message": "Adapter registered successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register adapter: {e}")
        
        await log_access(
            user_id=user["user_id"],
            operation="adapter_register",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters")
async def list_adapters(
    request: Request,
    user: dict = Depends(get_current_user),
    status: Optional[str] = None
):
    """
    List user's adapters (filtered by user_id via RLS).
    
    Filters:
    - status: Filter by status (pending, training, completed, failed)
    """
    try:
        supabase = get_supabase()
        
        query = supabase.table("user_adapters")\
            .select("*")\
            .eq("user_id", user["user_id"])
        
        if status:
            query = query.eq("status", status)
        
        result = query.order("created_at", desc=True).execute()
        
        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="adapter_list",
            request=request,
            success=True
        )
        
        return {
            "adapters": result.data,
            "count": len(result.data)
        }
        
    except Exception as e:
        logger.error(f"Failed to list adapters: {e}")
        
        await log_access(
            user_id=user["user_id"],
            operation="adapter_list",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/{adapter_id}")
async def get_adapter(
    adapter_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Get specific adapter metadata.
    
    RLS ensures user can only access their own adapters.
    """
    try:
        supabase = get_supabase()
        
        result = supabase.table("user_adapters")\
            .select("*")\
            .eq("user_id", user["user_id"])\
            .eq("adapter_id", adapter_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Adapter not found"
            )
        
        adapter = result.data[0]
        
        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="adapter_get",
            request=request,
            success=True,
            metadata={"adapter_id": adapter_id}
        )
        
        return adapter
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get adapter: {e}")
        
        await log_access(
            user_id=user["user_id"],
            operation="adapter_get",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/{adapter_id}/verify")
async def verify_adapter_ownership(
    adapter_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Verify that authenticated user owns the adapter.
    
    This is called before decryption operations to ensure
    user can only decrypt their own adapters.
    """
    try:
        supabase = get_supabase()
        
        # Check ownership (RLS will enforce this, but we verify explicitly)
        result = supabase.table("user_adapters")\
            .select("id")\
            .eq("user_id", user["user_id"])\
            .eq("adapter_id", adapter_id)\
            .execute()
        
        authorized = len(result.data) > 0
        
        # Log access attempt
        await log_access(
            user_id=user["user_id"],
            operation="adapter_verify",
            request=request,
            success=authorized,
            metadata={
                "adapter_id": adapter_id,
                "authorized": authorized
            }
        )
        
        if not authorized:
            return {
                "authorized": False,
                "message": "Adapter not found or access denied"
            }
        
        return {
            "authorized": True,
            "adapter_id": adapter_id,
            "user_id": user["user_id"]
        }
        
    except Exception as e:
        logger.error(f"Failed to verify adapter ownership: {e}")
        
        await log_access(
            user_id=user["user_id"],
            operation="adapter_verify",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/adapters/{adapter_id}/status")
async def update_adapter_status(
    adapter_id: str,
    request: Request,
    status: str,
    training_metrics: Optional[Dict[str, Any]] = None,
    user: dict = Depends(get_current_user)
):
    """
    Update adapter status (e.g., training -> completed).
    
    Only user who owns adapter can update it.
    """
    try:
        supabase = get_supabase()
        
        # Verify ownership first
        verify_result = await verify_adapter_ownership(
            adapter_id=adapter_id,
            request=request,
            user=user
        )
        
        if not verify_result["authorized"]:
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )
        
        # Update status
        update_data = {"status": status}
        if training_metrics:
            update_data["training_metrics"] = training_metrics
        
        result = supabase.table("user_adapters")\
            .update(update_data)\
            .eq("user_id", user["user_id"])\
            .eq("adapter_id", adapter_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Adapter not found"
            )
        
        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="adapter_update_status",
            request=request,
            success=True,
            metadata={"adapter_id": adapter_id, "status": status}
        )
        
        return {
            "success": True,
            "adapter_id": adapter_id,
            "status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update adapter status: {e}")
        
        await log_access(
            user_id=user["user_id"],
            operation="adapter_update_status",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/adapters/{adapter_id}")
async def delete_adapter(
    adapter_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Delete adapter metadata.
    
    Note: This does NOT delete the encrypted adapter file itself,
    only the metadata registry entry.
    """
    try:
        supabase = get_supabase()
        
        # Verify ownership first
        verify_result = await verify_adapter_ownership(
            adapter_id=adapter_id,
            request=request,
            user=user
        )
        
        if not verify_result["authorized"]:
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )
        
        # Delete adapter metadata
        result = supabase.table("user_adapters")\
            .delete()\
            .eq("user_id", user["user_id"])\
            .eq("adapter_id", adapter_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Adapter not found"
            )
        
        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="adapter_delete",
            request=request,
            success=True,
            metadata={"adapter_id": adapter_id}
        )
        
        return {
            "success": True,
            "message": "Adapter deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete adapter: {e}")
        
        await log_access(
            user_id=user["user_id"],
            operation="adapter_delete",
            request=request,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


def hash_encryption_key(key_hex: str) -> str:
    """
    Hash encryption key for storage (SHA256).
    
    Args:
        key_hex: Hex-encoded encryption key
    
    Returns:
        SHA256 hash as hex string
    """
    # Convert hex string to bytes
    key_bytes = bytes.fromhex(key_hex)
    # Hash with SHA256
    return hashlib.sha256(key_bytes).hexdigest()


