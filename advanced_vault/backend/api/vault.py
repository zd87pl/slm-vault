"""Vault API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase, get_supabase_service
from utils.access_logger import log_access
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class StoreEntryRequest(BaseModel):
    """Request to store encrypted entry."""
    entry_id: str
    encrypted_data: str  # Base64-encoded encrypted data (nonce + ciphertext)
    data_type: str  # 'secret' or 'knowledge'
    service: Optional[str] = None
    tags: Optional[List[str]] = None


class SyncRequest(BaseModel):
    """Request to sync multiple entries."""
    entries: List[StoreEntryRequest]


@router.post("/store")
async def store_entry(
    request: Request,
    data: StoreEntryRequest,
    user: dict = Depends(get_current_user)
):
    """
    Store encrypted entry in cloud vault.

    All encryption happens client-side. Server stores encrypted blobs.
    """
    try:
        # Use service key to bypass RLS (backend verifies user_id via auth middleware)
        supabase = get_supabase_service()

        # Insert or update entry
        entry_data = {
            "user_id": user["user_id"],
            "entry_id": data.entry_id,
            "encrypted_data": data.encrypted_data,
            "data_type": data.data_type,
            "service": data.service,
            "tags": data.tags or [],
        }

        result = supabase.table("vault_entries")\
            .upsert(entry_data)\
            .execute()

        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="store",
            request=request,
            service=data.service,
            entry_id=data.entry_id,
            success=True
        )

        return {
            "success": True,
            "entry_id": data.entry_id,
            "message": "Entry stored successfully"
        }

    except Exception as e:
        logger.error(f"Failed to store entry: {e}")

        # Log failed access
        await log_access(
            user_id=user["user_id"],
            operation="store",
            request=request,
            service=data.service,
            entry_id=data.entry_id,
            success=False,
            error_message=str(e)
        )

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entries")
async def list_entries(
    request: Request,
    user: dict = Depends(get_current_user),
    data_type: Optional[str] = None,
    service: Optional[str] = None,
    tag: Optional[str] = None
):
    """
    List vault entries (metadata only, not encrypted data).

    Filters:
    - data_type: 'secret' or 'knowledge'
    - service: Filter by service name
    - tag: Filter by tag
    """
    try:
        supabase = get_supabase()

        query = supabase.table("vault_entries")\
            .select("id,entry_id,data_type,service,tags,created_at,updated_at")\
            .eq("user_id", user["user_id"])\
            .is_("deleted_at", "null")

        if data_type:
            query = query.eq("data_type", data_type)
        if service:
            query = query.eq("service", service)
        if tag:
            query = query.contains("tags", [tag])

        result = query.execute()

        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="list",
            request=request,
            success=True,
            metadata={"filters": {"data_type": data_type, "service": service, "tag": tag}}
        )

        return {
            "entries": result.data,
            "count": len(result.data)
        }

    except Exception as e:
        logger.error(f"Failed to list entries: {e}")

        await log_access(
            user_id=user["user_id"],
            operation="list",
            request=request,
            success=False,
            error_message=str(e)
        )

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entry/{entry_id}")
async def get_entry(
    entry_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Get specific entry (including encrypted data).

    Returns encrypted blob for client-side decryption.
    """
    try:
        supabase = get_supabase()

        result = supabase.table("vault_entries")\
            .select("*")\
            .eq("user_id", user["user_id"])\
            .eq("entry_id", entry_id)\
            .is_("deleted_at", "null")\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Entry not found")

        entry = result.data[0]

        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="recall",
            request=request,
            service=entry.get("service"),
            entry_id=entry_id,
            success=True
        )

        return entry

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entry: {e}")

        await log_access(
            user_id=user["user_id"],
            operation="recall",
            request=request,
            entry_id=entry_id,
            success=False,
            error_message=str(e)
        )

        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entry/{entry_id}")
async def delete_entry(
    entry_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Delete entry (soft delete).
    """
    try:
        # Use service key to bypass RLS (backend verifies user_id via auth middleware)
        supabase = get_supabase_service()

        # Soft delete
        result = supabase.table("vault_entries")\
            .update({"deleted_at": "now()"})\
            .eq("user_id", user["user_id"])\
            .eq("entry_id", entry_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Entry not found")

        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="delete",
            request=request,
            entry_id=entry_id,
            success=True
        )

        return {
            "success": True,
            "message": "Entry deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete entry: {e}")

        await log_access(
            user_id=user["user_id"],
            operation="delete",
            request=request,
            entry_id=entry_id,
            success=False,
            error_message=str(e)
        )

        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_entries(
    request: Request,
    data: SyncRequest,
    user: dict = Depends(get_current_user)
):
    """
    Batch sync multiple entries from local vault.

    Used by CLI/app to push local vault to cloud.
    """
    try:
        # Use service key to bypass RLS (backend verifies user_id via auth middleware)
        supabase = get_supabase_service()

        # Prepare batch insert
        entries_data = [
            {
                "user_id": user["user_id"],
                "entry_id": entry.entry_id,
                "encrypted_data": entry.encrypted_data,
                "data_type": entry.data_type,
                "service": entry.service,
                "tags": entry.tags or [],
            }
            for entry in data.entries
        ]

        # Batch upsert
        result = supabase.table("vault_entries")\
            .upsert(entries_data)\
            .execute()

        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="sync",
            request=request,
            success=True,
            metadata={"entries_count": len(data.entries)}
        )

        return {
            "success": True,
            "synced_count": len(data.entries),
            "message": f"Synced {len(data.entries)} entries"
        }

    except Exception as e:
        logger.error(f"Failed to sync entries: {e}")

        await log_access(
            user_id=user["user_id"],
            operation="sync",
            request=request,
            success=False,
            error_message=str(e)
        )

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Get vault statistics."""
    try:
        supabase = get_supabase()

        # Call Supabase function
        result = supabase.rpc("get_vault_stats", {"p_user_id": user["user_id"]}).execute()

        # Log access
        await log_access(
            user_id=user["user_id"],
            operation="stats",
            request=request,
            success=True
        )

        return result.data

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")

        await log_access(
            user_id=user["user_id"],
            operation="stats",
            request=request,
            success=False,
            error_message=str(e)
        )

        raise HTTPException(status_code=500, detail=str(e))
