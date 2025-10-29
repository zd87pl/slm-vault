"""Authentication middleware and utilities."""

from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from config import settings
from utils.supabase_client import get_supabase
from typing import Optional
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Verify JWT token from Supabase.

    Args:
        credentials: Bearer token from Authorization header

    Returns:
        Decoded JWT payload with user info

    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials

    try:
        # Verify with Supabase JWT secret
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="authenticated"
        )

        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials"
            )

        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "role": payload.get("role"),
        }

    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials"
        )


async def get_current_user(token_data: dict = Depends(verify_token)) -> dict:
    """
    Get current authenticated user.

    Args:
        token_data: Decoded JWT data

    Returns:
        User dict with id, email, role
    """
    return token_data


def get_client_info(request: Request) -> dict:
    """
    Extract client information from request.

    Args:
        request: FastAPI request object

    Returns:
        Dict with IP, user agent, etc.
    """
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "client_type": request.headers.get("x-client-type", "api"),
        "client_version": request.headers.get("x-client-version"),
    }


async def verify_api_key(
    request: Request,
    api_key: str = Security(HTTPBearer())
) -> dict:
    """
    Verify API key for programmatic access.

    Args:
        request: FastAPI request
        api_key: API key from Authorization header

    Returns:
        User info associated with API key

    Raises:
        HTTPException: If API key is invalid or revoked
    """
    from utils.supabase_client import get_supabase_service
    from passlib.hash import bcrypt

    supabase = get_supabase_service()

    # Extract key from Bearer token
    key = api_key.credentials

    # Get key prefix (first 8 chars)
    key_prefix = key[:12] if len(key) >= 12 else key

    # Find API key by prefix
    result = supabase.table("api_keys")\
        .select("*")\
        .eq("key_prefix", key_prefix)\
        .is_("revoked_at", "null")\
        .execute()

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid API key")

    api_key_record = result.data[0]

    # Verify key hash
    if not bcrypt.verify(key, api_key_record["key_hash"]):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check expiration
    if api_key_record.get("expires_at"):
        from datetime import datetime
        expires_at = datetime.fromisoformat(api_key_record["expires_at"])
        if datetime.now() > expires_at:
            raise HTTPException(status_code=401, detail="API key expired")

    # Update last_used
    supabase.table("api_keys")\
        .update({"last_used": "now()"})\
        .eq("id", api_key_record["id"])\
        .execute()

    return {
        "user_id": api_key_record["user_id"],
        "api_key_id": api_key_record["id"],
        "api_key_name": api_key_record["name"],
    }
