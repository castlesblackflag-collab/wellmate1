"""Supabase access for the engine.

The engine uses the service key, which bypasses row level security. That makes one rule
critical: every query that touches user data must filter by the authenticated user's uid.
The database backs this up where it can (see the trigger in the migration that stops a
message being written under a different user than its conversation).
"""

from functools import lru_cache

from supabase import Client, create_client

from engine.errors import NotConfiguredError
from engine.settings import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    if not settings.supabase_configured:
        raise NotConfiguredError("SUPABASE_URL or SUPABASE_SERVICE_KEY is not set")
    return create_client(settings.supabase_url, settings.supabase_service_key.get_secret_value())
