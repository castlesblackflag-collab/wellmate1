"""Sage engine: FastAPI entry point.

Cloud Run starts this through the Procfile (`uvicorn main:app`).
The app is built by `create_app()` so tests can build fresh copies with different settings.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine import __version__
from engine.api import router as api_router
from engine.errors import install_error_handlers
from engine.logging_setup import RequestIdMiddleware, configure_logging
from engine.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Sage Engine",
        version=__version__,
        description="The Wellmate's conversational health guide.",
        # Interactive API docs are handy locally but not something we expose in production.
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=settings.allowed_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)

    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
