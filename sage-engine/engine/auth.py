"""Who is talking to Sage.

The app signs users in with Firebase Auth, and the frontend sends the user's Firebase ID
token as `Authorization: Bearer <token>`. We verify it here and use the Firebase `uid` as
the user ID everywhere (Supabase rows, memory, logs). No API key is needed for this;
verification only uses the Firebase project ID and Google's public signing certificates.
"""

from dataclasses import dataclass

import firebase_admin
from fastapi import Depends, Header
from firebase_admin import auth as firebase_auth
from starlette.concurrency import run_in_threadpool

from engine.errors import AuthError
from engine.settings import Settings, get_settings

LOCAL_DEV_UID = "local-dev-user"
_APP_NAME = "sage-auth"


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str | None = None


def _firebase_app(project_id: str) -> firebase_admin.App:
    try:
        return firebase_admin.get_app(_APP_NAME)
    except ValueError:
        return firebase_admin.initialize_app(options={"projectId": project_id}, name=_APP_NAME)


def verify_firebase_token(token: str, project_id: str) -> dict:
    """Returns the decoded token claims, or raises if the token is invalid or expired."""
    return firebase_auth.verify_id_token(token, app=_firebase_app(project_id))


async def current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    if settings.auth_disabled:
        return AuthUser(uid=LOCAL_DEV_UID)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()

    try:
        claims = await run_in_threadpool(verify_firebase_token, token, settings.firebase_project_id)
    except Exception as exc:
        raise AuthError(f"Token verification failed: {type(exc).__name__}") from exc

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise AuthError("Token has no uid")
    return AuthUser(uid=uid, email=claims.get("email"))
