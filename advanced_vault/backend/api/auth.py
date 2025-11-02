"""Authentication API endpoints."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from middleware.auth import get_current_user
from utils.supabase_client import get_supabase
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


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
async def signup(data: SignupRequest):
    """
    Sign up new user.

    Creates user in Supabase Auth and profile in database.
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

    except Exception as e:
        logger.error(f"Signup failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
async def login(data: LoginRequest):
    """
    Log in user with email/password.

    Returns JWT tokens for authentication.
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

    except Exception as e:
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
        logger.error(f"Logout failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str


@router.post("/refresh")
async def refresh_token(data: RefreshTokenRequest):
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

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.get("/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current user profile."""
    try:
        from utils.supabase_client import get_supabase_service
        supabase = get_supabase_service()

        result = supabase.table("profiles")\
            .select("*")\
            .eq("id", user["user_id"])\
            .execute()

        if result.data:
            return result.data[0]
        else:
            raise HTTPException(status_code=404, detail="Profile not found")

    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))
