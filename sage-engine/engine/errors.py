"""Errors the engine can raise, and the single place they turn into responses.

The rule for this codebase: nothing fails silently. Every failure is logged with its cause,
and the caller always gets the same JSON shape:

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

`message` is safe to show a user. Technical detail goes to the logs, never into the response.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from engine.logging_setup import request_id_var

log = logging.getLogger("sage.errors")


class SageError(Exception):
    status_code = 500
    code = "internal_error"
    user_message = "Something went wrong on our side. Please try again in a moment."

    def __init__(self, detail: str = "", *, user_message: str | None = None):
        super().__init__(detail or self.code)
        self.detail = detail
        if user_message:
            self.user_message = user_message


class AuthError(SageError):
    status_code = 401
    code = "unauthorized"
    user_message = "Please sign in again to keep chatting with Sage."


class NotFoundError(SageError):
    status_code = 404
    code = "not_found"
    user_message = "We couldn't find that conversation."


class NotConfiguredError(SageError):
    status_code = 503
    code = "not_configured"
    user_message = "Sage isn't fully set up yet. Please try again later."


class UpstreamError(SageError):
    """A service we depend on (model, Supabase, search) failed or timed out."""

    status_code = 502
    code = "upstream_error"
    user_message = "Sage is having trouble reaching one of its services. Please try again shortly."


class NotBuiltYetError(SageError):
    status_code = 501
    code = "not_implemented"
    user_message = "This part of Sage is still being built."


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id_var.get()}}


def unexpected_error_response() -> JSONResponse:
    return JSONResponse(error_body(SageError.code, SageError.user_message), status_code=500)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SageError)
    async def _sage_error(request: Request, exc: SageError):
        # 4xx and "not built yet" are expected; real server failures are errors.
        level = logging.ERROR if exc.status_code >= 500 and exc.status_code != 501 else logging.WARNING
        log.log(
            level,
            "%s: %s",
            exc.code,
            exc.detail or exc.user_message,
            extra={"path": request.url.path, "status": exc.status_code},
            exc_info=exc.status_code >= 500 and exc.status_code != 501,
        )
        return JSONResponse(error_body(exc.code, exc.user_message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, exc: RequestValidationError):
        log.warning("invalid_request", extra={"path": request.url.path, "errors": exc.errors()})
        return JSONResponse(
            error_body("invalid_request", "That request wasn't in the format Sage expects."),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)

    # Unexpected exceptions are caught in RequestIdMiddleware (engine/logging_setup.py) so the
    # request ID survives. This handler is a last resort in case that middleware is ever removed.
    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log.exception("unhandled_error", extra={"path": request.url.path})
        return unexpected_error_response()
