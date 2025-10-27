"""Supabase client wrapper."""

from supabase import create_client, Client
from config import settings


class SupabaseClient:
    """Singleton Supabase client."""

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
    """Get Supabase client (anon key)."""
    return SupabaseClient.get_client()


def get_supabase_service() -> Client:
    """Get Supabase client with service role (bypasses RLS)."""
    return SupabaseClient.get_client(use_service_key=True)
