"""HTTP routes.

/health  Is the process up? Cheap, no outside calls. Use for Cloud Run health checks.
/ready   Is everything Sage needs configured and reachable? Reports names, never values.
/v1/chat The conversation endpoint. The request shape is final (see docs/endpoint-contract.md);
         the handler answers 501 until the agent loop is built.
"""

import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from engine import __version__
from engine.auth import AuthUser, current_user
from engine.errors import NotBuiltYetError
from engine.settings import Settings, get_settings

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

    # Optional until the matching tool exists, so they don't affect overall readiness.
    optional = {
        "ncbi_api_key": settings.ncbi_api_key is not None,
        "web_search_api_key": settings.web_search_api_key is not None,
        "google_places_api_key": settings.google_places_api_key is not None,
    }

    all_ok = all(c["ok"] for c in checks.values())
    body = {"ready": all_ok, "checks": checks, "optional_keys_present": optional}
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
async def chat(body: ChatRequest, user: AuthUser = Depends(current_user)):
    raise NotBuiltYetError("POST /v1/chat: agent loop not built yet")
