"""HTTP routes. The full contract is in docs/endpoint-contract.md.

/health                          Is the process up? No outside calls.
/ready                           Is everything configured and reachable? Names only, never values.
POST /v1/chat                    One message in, a streamed reply out (Server-Sent Events).
GET  /v1/conversations           The user's recent conversations.
GET  /v1/conversations/{id}      One conversation's messages.
POST /v1/conversations/{id}/close  The user is done; summary is written by the next job run.
POST /internal/jobs/close-idle   Cloud Scheduler only: summarize and close quiet conversations.
"""

import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from engine import __version__
from engine.agent import Sage
from engine.auth import AuthUser, current_user
from engine.container import get_background_model, get_conversation_store, get_memory_store, get_sage
from engine.conversations import ConversationStore
from engine.errors import NotFoundError
from engine.job_auth import require_job_caller
from engine.jobs import close_idle_conversations
from engine.logging_setup import request_id_var
from engine.model_adapter import ModelAdapter
from engine.settings import Settings, get_settings
from memory.store import MemoryStore

log = logging.getLogger("sage.api")
router = APIRouter()


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "version": __version__, "environment": settings.environment}


def _check_supabase() -> tuple[bool, str]:
    from engine.db import get_supabase

    try:
        get_supabase().table("sage_conversations").select("id").limit(1).execute()
        return True, "reachable"
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"; logged and reported
        log.warning("supabase readiness check failed", extra={"error": type(exc).__name__})
        return False, f"unreachable ({type(exc).__name__})"


@router.get("/ready")
async def ready(settings: Settings = Depends(get_settings)) -> JSONResponse:
    from safety import get_crisis_screen

    checks: dict[str, dict] = {}
    if settings.supabase_configured:
        ok, detail = await run_in_threadpool(_check_supabase)
        checks["supabase"] = {"ok": ok, "detail": detail}
    else:
        checks["supabase"] = {"ok": False, "detail": "SUPABASE_URL / SUPABASE_SERVICE_KEY not set"}

    checks["chat_model"] = {
        "ok": bool(settings.chat_model),
        "detail": f"{settings.chat_provider}:{settings.chat_model}",
    }
    checks["auth"] = {
        "ok": not (settings.auth_disabled and settings.environment != "local"),
        "detail": "disabled (local dev)" if settings.auth_disabled else "firebase",
    }

    # Informational: these don't affect readiness, but show at a glance what's switched on.
    status = {
        "chat_enabled": settings.chat_enabled,
        "crisis_screen_registered": get_crisis_screen() is not None,
        "jobs_configured": bool(settings.job_audience and settings.job_invoker_email),
        "model_prices_set": sorted(settings.model_prices),
    }
    optional = {
        "ncbi_api_key": settings.ncbi_api_key is not None,
        "web_search_api_key": settings.web_search_api_key is not None,
        "google_places_api_key": settings.google_places_api_key is not None,
    }

    all_ok = all(c["ok"] for c in checks.values())
    body = {"ready": all_ok, "checks": checks, "status": status, "optional_keys_present": optional}
    return JSONResponse(body, status_code=200 if all_ok else 503)


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Omit to start a new conversation; send it back to continue one."
    )
    message: str = Field(min_length=1, max_length=8000)
    client_context: dict | None = Field(
        default=None, description="Optional hints from the app, e.g. which screen the user opened Sage from."
    )


@router.post("/v1/chat")
async def chat(body: ChatRequest, user: AuthUser = Depends(current_user), sage: Sage = Depends(get_sage)):
    conversation = await sage.open_conversation(user.uid, body.conversation_id)
    request_id = request_id_var.get()

    async def events():
        async for event in sage.run_turn(
            user_id=user.uid,
            conversation=conversation,
            message=body.message,
            request_id=request_id,
            client_context=body.client_context,
        ):
            yield event.to_sse()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # no-transform and X-Accel-Buffering stop proxies from holding the stream back.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "X-Request-ID": request_id},
    )


@router.get("/v1/conversations")
async def list_conversations(
    user: AuthUser = Depends(current_user), store: ConversationStore = Depends(get_conversation_store)
) -> dict:
    items = await store.list_recent(user.uid, limit=20)
    return {
        "conversations": [
            c.model_dump(mode="json", include={"id", "title", "status", "created_at", "updated_at"}) for c in items
        ]
    }


@router.get("/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    store: ConversationStore = Depends(get_conversation_store),
) -> dict:
    conversation = await store.get(user.uid, conversation_id)
    if conversation is None:
        raise NotFoundError(f"conversation {conversation_id} not found for this user")
    history = await store.history(user.uid, conversation_id, limit=200)
    # The app only needs the visible exchange; tool traffic stays server-side.
    messages = [{"role": m.role, "text": m.text} for m in history if m.role in ("user", "assistant") and m.text]
    return {
        "conversation": conversation.model_dump(mode="json", include={"id", "title", "status", "created_at"}),
        "messages": messages,
    }


@router.post("/v1/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    store: ConversationStore = Depends(get_conversation_store),
) -> dict:
    if await store.get(user.uid, conversation_id) is None:
        raise NotFoundError(f"conversation {conversation_id} not found for this user")
    # The next job run writes the summary for it.
    await store.close(user.uid, conversation_id)
    return {"closed": True}


@router.post("/internal/jobs/close-idle", include_in_schema=False)
async def job_close_idle(
    caller: str = Depends(require_job_caller),
    settings: Settings = Depends(get_settings),
    store: ConversationStore = Depends(get_conversation_store),
    memory: MemoryStore = Depends(get_memory_store),
    model: ModelAdapter = Depends(get_background_model),
) -> dict:
    return await close_idle_conversations(
        conversations=store, memory=memory, model=model, idle_minutes=settings.idle_minutes_before_close
    )
