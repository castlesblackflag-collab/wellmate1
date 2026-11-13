"""Checks that a call to /internal/jobs/* really comes from our Cloud Scheduler.

Cloud Scheduler signs each call with a Google ID token for a service account we choose.
We accept it only if Google signed it, it was issued for this service (audience), and it
belongs to that one service account.
"""

from fastapi import Depends, Header
from starlette.concurrency import run_in_threadpool

from engine.errors import AuthError, NotConfiguredError
from engine.settings import Settings, get_settings


def verify_google_token(token: str, audience: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)


async def require_job_caller(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.job_audience or not settings.job_invoker_email:
        raise NotConfiguredError("JOB_AUDIENCE / JOB_INVOKER_EMAIL not set")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing bearer token on job call")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = await run_in_threadpool(verify_google_token, token, settings.job_audience)
    except Exception as exc:
        raise AuthError(f"Job token rejected: {type(exc).__name__}") from exc
    if claims.get("email") != settings.job_invoker_email or not claims.get("email_verified"):
        raise AuthError(f"Job token from unexpected account: {claims.get('email')}")
    return claims["email"]
