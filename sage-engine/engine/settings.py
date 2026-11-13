"""All configuration comes from environment variables.

On Cloud Run, secrets are stored in Secret Manager and exposed to the service as
environment variables (Cloud Run console: Edit & deploy new revision > Variables & Secrets),
so this code never talks to Secret Manager directly and never sees a key in the repo.
Locally, the same variables come from a `.env` file that git ignores.

See `.env.example` for the full list and `config/secrets-inventory.md` for where each one lives.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8080",
    "https://thewellmate.live",
    "https://www.thewellmate.live",
    "https://wellmate-i.web.app",
    "https://wellmate-i.firebaseapp.com",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    # Where we're running. "production" switches on the strictest checks.
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Google Cloud
    gcp_project_id: str = "wellmate-i"
    gcp_region: str = "us-central1"
    # Region used for model calls on Vertex AI. Claude models are offered in specific regions
    # (and a "global" endpoint); confirm in Model Garden which ones our project can use.
    model_region: str = "us-east5"

    # Models. Vertex AI model IDs carry a version suffix; confirm the exact IDs in Model Garden.
    chat_provider: Literal["claude", "gemini", "fake"] = "claude"
    chat_model: str = "claude-sonnet-5-5"
    background_provider: Literal["claude", "gemini", "fake"] = "claude"
    background_model: str = "claude-haiku-5-5"

    # Firebase Auth (the app's sign-in). Only the project ID is needed to verify user tokens.
    firebase_project_id: str = "wellmate-i"
    # Local development only: skip token checks and treat every request as a test user.
    auth_disabled: bool = False

    # Supabase
    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None

    # Outside services for tools (all optional until the matching tool is built)
    ncbi_api_key: SecretStr | None = None
    web_search_api_key: SecretStr | None = None
    google_places_api_key: SecretStr | None = None

    # Browsers allowed to call the engine. Lovable preview hosts change, so they can be
    # allowed with a pattern instead, e.g. ALLOWED_ORIGIN_REGEX=https://.*\.lovable\.app
    allowed_origins: list[str] = DEFAULT_ORIGINS
    allowed_origin_regex: str | None = None

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            if self.auth_disabled:
                raise ValueError("AUTH_DISABLED must never be true in production.")
            if "fake" in (self.chat_provider, self.background_provider):
                raise ValueError("The fake model provider is for tests only, not production.")
        return self

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
