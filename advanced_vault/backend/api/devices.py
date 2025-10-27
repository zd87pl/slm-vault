"""Devices API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterDeviceRequest(BaseModel):
    """Register new device."""
    device_name: str
    device_type: str  # 'cli', 'macos_app', etc.
    device_id: str


@router.get("/")
async def list_devices(user: dict = Depends(get_current_user)):
    """List all devices for current user."""
    try:
        supabase = get_supabase()

        result = supabase.table("devices")\
            .select("*")\
            .eq("user_id", user["user_id"])\
            .is_("revoked_at", "null")\
            .order("last_active", desc=True)\
            .execute()

        return {"devices": result.data, "count": len(result.data)}

    except Exception as e:
        logger.error(f"Failed to list devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register")
async def register_device(
    data: RegisterDeviceRequest,
    user: dict = Depends(get_current_user)
):
    """Register new device."""
    try:
        supabase = get_supabase()

        device_data = {
            "user_id": user["user_id"],
            "device_name": data.device_name,
            "device_type": data.device_type,
            "device_id": data.device_id,
            "last_active": "now()"
        }

        result = supabase.table("devices")\
            .upsert(device_data)\
            .execute()

        return {
            "success": True,
            "device": result.data[0] if result.data else None
        }

    except Exception as e:
        logger.error(f"Failed to register device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}")
async def revoke_device(
    device_id: str,
    user: dict = Depends(get_current_user)
):
    """Revoke device access."""
    try:
        supabase = get_supabase()

        result = supabase.table("devices")\
            .update({"revoked_at": "now()"})\
            .eq("id", device_id)\
            .eq("user_id", user["user_id"])\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Device not found")

        return {"success": True, "message": "Device revoked"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke device: {e}")
        raise HTTPException(status_code=500, detail=str(e))
