"""Builds the engine's parts from settings, in one place.

Routes ask for what they need through FastAPI dependencies (get_sage, get_conversation_store,
...). Tests swap any of these for in-memory versions with app.dependency_overrides.
"""

from engine.agent import Sage
from engine.context import ContextBuilder, NoAgeWellSource
from engine.conversations import ConversationStore, SupabaseConversationStore
from engine.db import get_supabase
from engine.errors import NotBuiltYetError
from engine.model_adapter import ModelAdapter, get_adapter
from engine.persona import load_persona
from engine.settings import get_settings
from engine.turn_log import SupabaseTurnLogger
from memory.store import MemoryStore
from memory.supabase_store import SupabaseMemoryStore
from safety import get_crisis_screen
from tools import build_registry


def get_conversation_store() -> ConversationStore:
    return SupabaseConversationStore(get_supabase())


def get_memory_store() -> MemoryStore:
    return SupabaseMemoryStore(get_supabase())


def get_background_model() -> ModelAdapter:
    s = get_settings()
    return get_adapter(s.background_provider, s.background_model, s.model_region, s.gcp_project_id)


def get_sage() -> Sage:
    s = get_settings()
    if not s.chat_enabled:
        raise NotBuiltYetError("CHAT_ENABLED is false")
    screen = get_crisis_screen()
    if screen is None:
        raise NotBuiltYetError("No crisis screen registered in safety/__init__.py; chat stays off")

    memory = get_memory_store()
    return Sage(
        settings=s,
        model=get_adapter(s.chat_provider, s.chat_model, s.model_region, s.gcp_project_id),
        tools=build_registry(s),
        conversations=get_conversation_store(),
        context=ContextBuilder(
            persona=load_persona(), memory=memory, agewell=NoAgeWellSource(), summary_count=s.summary_count
        ),
        screen=screen,
        turn_logger=SupabaseTurnLogger(get_supabase()),
    )
