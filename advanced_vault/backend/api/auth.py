"""Authentication API endpoints."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from middleware.auth import get_current_user
from utils.supabase_client import get_supabase, get_supabase_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiter for auth endpoints (stricter than global)
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    """Login request."""
    email: str
    password: str


class SignupRequest(BaseModel):
    """Signup request."""
    email: str
    password: str
    full_name: Optional[str] = None


@router.post("/signup")
@limiter.limit("5/minute")
async def signup(request: Request, data: SignupRequest):
    """
    Sign up new user.

    Creates user in Supabase Auth and profile in database.
    Rate limited to 5 requests per minute per IP.
    """
    try:
        supabase = get_supabase()

        # Sign up user
        result = supabase.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {
                "data": {
                    "full_name": data.full_name
                }
            }
        })

        if result.user:
            return {
                "success": True,
                "user": {
                    "id": result.user.id,
                    "email": result.user.email,
                },
                "session": {
                    "access_token": result.session.access_token if result.session else None,
                    "refresh_token": result.session.refresh_token if result.session else None,
                }
            }
        else:
            raise HTTPException(status_code=400, detail="Signup failed")

    except HTTPException:
        raise
    except Exception as e:
        # Log full error internally but return generic message to client
        logger.error(f"Signup failed: {e}")
        raise HTTPException(status_code=400, detail="Signup failed. Please try again.")


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, data: LoginRequest):
    """
    Log in user with email/password.

    Returns JWT tokens for authentication.
    Rate limited to 10 requests per minute per IP to prevent brute force.
    """
    try:
        supabase = get_supabase()

        # Sign in user
        result = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })

        if result.session:
            return {
                "success": True,
                "user": {
                    "id": result.user.id,
                    "email": result.user.email,
                },
                "session": {
                    "access_token": result.session.access_token,
                    "refresh_token": result.session.refresh_token,
                    "expires_at": result.session.expires_at,
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    except HTTPException:
        raise
    except Exception as e:
        # Log full error internally but return generic message to prevent enumeration
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Log out current user."""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()

        return {"success": True, "message": "Logged out successfully"}

    except Exception as e:
        # Log full error internally but return generic message
        logger.error(f"Logout failed: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh_token(request: Request, data: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    try:
        supabase = get_supabase()

        result = supabase.auth.refresh_session(data.refresh_token)

        if result.session:
            return {
                "success": True,
                "session": {
                    "access_token": result.session.access_token,
                    "refresh_token": result.session.refresh_token,
                    "expires_at": result.session.expires_at,
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.get("/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current user profile."""
    try:
        supabase = get_supabase_service()

        result = supabase.table("profiles")\
            .select("*")\
            .eq("id", user["user_id"])\
            .execute()

        if result.data:
            return result.data[0]
        else:
            raise HTTPException(status_code=404, detail="Profile not found")

    except HTTPException:
        raise
    except Exception as e:
        # Log full error internally but return generic message
        logger.error(f"Failed to get user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user profile")
