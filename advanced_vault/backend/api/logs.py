"""Access logs API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def get_logs(
    request: Request,
    user: dict = Depends(get_current_user),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    operation: Optional[str] = None,
    client_type: Optional[str] = None,
    service: Optional[str] = None,
):
    """
    Get access logs for current user.

    Supports filtering and pagination.
    """
    try:
        supabase = get_supabase()

        query = supabase.table("access_logs")\
            .select("*")\
            .eq("user_id", user["user_id"])\
            .order("created_at", desc=True)\
            .range(offset, offset + limit - 1)

        if operation:
            query = query.eq("operation", operation)
        if client_type:
            query = query.eq("client_type", client_type)
        if service:
            query = query.eq("service", service)

        result = query.execute()

        # Get total count
        count_result = supabase.table("access_logs")\
            .select("count", count="exact")\
            .eq("user_id", user["user_id"])\
            .execute()

        return {
            "logs": result.data,
            "count": len(result.data),
            "total": count_result.count if hasattr(count_result, 'count') else 0,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_log_stats(
    user: dict = Depends(get_current_user),
    days: int = Query(default=30, le=365)
):
    """Get access log statistics."""
    try:
        supabase = get_supabase()

        # Call Supabase function
        result = supabase.rpc("get_access_stats", {
            "p_user_id": user["user_id"],
            "p_days": days
        }).execute()

        return result.data

    except Exception as e:
        logger.error(f"Failed to get log stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
