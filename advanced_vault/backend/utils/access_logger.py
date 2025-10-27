"""Access logging utility."""

from utils.supabase_client import get_supabase_service
from typing import Optional
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


async def log_access(
    user_id: str,
    operation: str,
    request: Request = None,
    service: Optional[str] = None,
    entry_id: Optional[str] = None,
    client_type: str = "api",
    client_version: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Log vault access to Supabase.

    Args:
        user_id: User ID performing the operation
        operation: Operation type (store, recall, delete, etc.)
        request: FastAPI request object (for IP, user agent)
        service: Service name (for secrets)
        entry_id: Entry ID (if applicable)
        client_type: Client type (cli, web, mcp, etc.)
        client_version: Client version
        success: Whether operation succeeded
        error_message: Error message if failed
        metadata: Additional metadata
    """
    try:
        supabase = get_supabase_service()

        log_data = {
            "user_id": user_id,
            "operation": operation,
            "service": service,
            "entry_id": entry_id,
            "client_type": client_type,
            "client_version": client_version,
            "success": success,
            "error_message": error_message,
            "metadata": metadata,
        }

        # Extract request info if available
        if request:
            log_data["ip_address"] = request.client.host if request.client else None
            log_data["user_agent"] = request.headers.get("user-agent")

            # Override client info from headers if present
            if request.headers.get("x-client-type"):
                log_data["client_type"] = request.headers.get("x-client-type")
            if request.headers.get("x-client-version"):
                log_data["client_version"] = request.headers.get("x-client-version")

        # Insert log
        result = supabase.table("access_logs").insert(log_data).execute()

        logger.debug(f"Logged access: {operation} by {user_id}")

    except Exception as e:
        # Don't fail the request if logging fails
        logger.error(f"Failed to log access: {e}")


def access_logged(operation: str):
    """
    Decorator to automatically log API endpoint access.

    Usage:
        @app.get("/vault/entries")
        @access_logged("list")
        async def list_entries(user=Depends(get_current_user)):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract user and request from kwargs
            user = kwargs.get("user") or kwargs.get("current_user")
            request = kwargs.get("request")

            if not user:
                # Try to find user in args
                for arg in args:
                    if isinstance(arg, dict) and "user_id" in arg:
                        user = arg
                        break

            try:
                # Execute the function
                result = await func(*args, **kwargs)

                # Log successful access
                if user:
                    await log_access(
                        user_id=user.get("user_id"),
                        operation=operation,
                        request=request,
                        client_type=user.get("client_type", "api"),
                        success=True
                    )

                return result

            except Exception as e:
                # Log failed access
                if user:
                    await log_access(
                        user_id=user.get("user_id"),
                        operation=operation,
                        request=request,
                        client_type=user.get("client_type", "api"),
                        success=False,
                        error_message=str(e)
                    )
                raise

        return wrapper
    return decorator
