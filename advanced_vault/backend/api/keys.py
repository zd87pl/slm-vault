"""API Keys endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase
from passlib.hash import bcrypt
import secrets
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateKeyRequest(BaseModel):
    """Create API key request."""
    name: str
    expires_days: Optional[int] = None  # None = no expiration


@router.get("/")
async def list_api_keys(user: dict = Depends(get_current_user)):
    """List all API keys for current user."""
    try:
        supabase = get_supabase()

        result = supabase.table("api_keys")\
            .select("id,name,key_prefix,last_used,expires_at,created_at")\
            .eq("user_id", user["user_id"])\
            .is_("revoked_at", "null")\
            .order("created_at", desc=True)\
            .execute()

        return {"keys": result.data, "count": len(result.data)}

    except Exception as e:
        logger.error(f"Failed to list API keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_api_key(
    data: CreateKeyRequest,
    user: dict = Depends(get_current_user)
):
    """
    Create new API key.

    Returns the full key only once. User must save it.
    """
    try:
        supabase = get_supabase()

        # Generate API key: vlt_<random 32 chars>
        key = f"vlt_{secrets.token_urlsafe(32)}"
        key_prefix = key[:12]  # "vlt_" + first 8 chars
        key_hash = bcrypt.hash(key)

        # Calculate expiration
        expires_at = None
        if data.expires_days:
            expires_at = (datetime.now() + timedelta(days=data.expires_days)).isoformat()

        key_data = {
            "user_id": user["user_id"],
            "name": data.name,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "expires_at": expires_at
        }

        result = supabase.table("api_keys")\
            .insert(key_data)\
            .execute()

        return {
            "success": True,
            "key": key,  # Only shown once!
            "key_prefix": key_prefix,
            "name": data.name,
            "expires_at": expires_at,
            "warning": "Save this key now. It will not be shown again."
        }

    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: dict = Depends(get_current_user)
):
    """Revoke API key."""
    try:
        supabase = get_supabase()

        result = supabase.table("api_keys")\
            .update({"revoked_at": "now()"})\
            .eq("id", key_id)\
            .eq("user_id", user["user_id"])\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="API key not found")

        return {"success": True, "message": "API key revoked"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))
