"""Supabase client wrapper."""

from contextvars import ContextVar, Token
from typing import Optional

from supabase import create_client, Client
from config import settings

_request_jwt: ContextVar[Optional[str]] = ContextVar("request_jwt", default=None)


class SupabaseClient:
    """Supabase client factory with request-scoped JWT context."""

    _instance: Client | None = None
    _service_instance: Client | None = None

    @classmethod
    def get_client(cls, use_service_key: bool = False) -> Client:
        """
        Get Supabase client instance.

        Args:
            use_service_key: If True, use service role key (bypasses RLS)

        Returns:
            Supabase client
        """
        if use_service_key:
            if cls._service_instance is None:
                cls._service_instance = create_client(
                    settings.supabase_url,
                    settings.supabase_service_key
                )
            return cls._service_instance
        else:
            if cls._instance is None:
                cls._instance = create_client(
                    settings.supabase_url,
                    settings.supabase_anon_key
                )
            return cls._instance


def get_supabase() -> Client:
    """
    Get Supabase client.

    If a request JWT is present in context, return a client authenticated
    with that JWT so RLS policies evaluate with auth.uid().
    """
    request_jwt = _request_jwt.get()
    if request_jwt:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        client.postgrest.auth(request_jwt)
        return client

    return SupabaseClient.get_client()


def get_supabase_service() -> Client:
    """Get Supabase client with service role (bypasses RLS)."""
    return SupabaseClient.get_client(use_service_key=True)


def set_request_jwt(jwt_token: Optional[str]) -> Token:
    """Set request-scoped JWT token used by get_supabase()."""
    return _request_jwt.set(jwt_token)


def reset_request_jwt(token: Token) -> None:
    """Reset request-scoped JWT token after request lifecycle ends."""
    _request_jwt.reset(token)
