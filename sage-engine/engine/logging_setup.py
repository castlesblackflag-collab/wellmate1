"""Structured logging that Cloud Logging understands, plus a request ID on every log line.

Every request gets an ID (taken from an incoming X-Request-ID header or generated). It is
returned in the response header and in every error body, so a user-facing error can be
matched to its log entry in seconds.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("sage.errors")

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class CloudJsonFormatter(logging.Formatter):
    """One JSON object per line. Cloud Logging reads `severity` and `message` automatically."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": request_id_var.get(),
        }
        # Anything passed with logger.info("...", extra={...}) comes along as structured fields.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    # Replace only our own handler, so test tools and other libraries keep theirs.
    root.handlers = [h for h in root.handlers if not getattr(h, "_sage_handler", False)]
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CloudJsonFormatter())
    handler._sage_handler = True
    root.addHandler(handler)
    root.setLevel(level.upper())


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if 0 < len(incoming) <= 100 else uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        except Exception:
            # Unexpected errors would otherwise be handled outside this middleware, after the
            # request ID is gone. Handling them here keeps the ID in both the log and the reply.
            from engine.errors import unexpected_error_response

            log.exception("unhandled_error", extra={"path": request.url.path})
            response = unexpected_error_response()
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
