"""Runtime settings — env-driven, typed via Pydantic.

All settings come from environment variables prefixed `TM_`. A `.env` file is
read at the project root if present. See `.env.example` for the full list.

For production deployments, supply env vars via the orchestrator's secret
mechanism (e.g. Kubernetes Secrets, AWS Parameter Store) rather than .env.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TM_", extra="ignore")

    # ---- Identity ----
    env: str = "development"  # development | staging | production
    """Used by Sentry tagging + log structure. CI sets `staging`/`production`."""

    # ---- Database ----
    database_url: str = "postgresql+asyncpg://tm:tm@localhost:5432/tm"
    database_url_sync: str = "postgresql+psycopg2://tm:tm@localhost:5432/tm"

    # ---- Redis (RQ + rate limit storage) ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- Filesystem ----
    upload_dir: Path = Path("/tmp/tm_uploads")
    data_dir: Path = Path(__file__).resolve().parents[3]  # claude_csvbuilder/

    # ---- Security ----
    # Comma-separated list of allowed CORS origins. Empty = no cross-origin allowed.
    cors_origins: str = "http://localhost:3000"
    # HMAC key for signed cookies / future JWT issuance. MUST be set in prod.
    secret_key: str = "dev-only-do-not-use-in-prod"
    # Hard cap on uploaded file size (bytes). 500 MB matches the PDF intent.
    max_upload_bytes: int = 500 * 1024 * 1024
    # Rate-limit budget per IP (slowapi syntax: "<count>/<period>")
    rate_limit_default: str = "120/minute"
    rate_limit_upload: str = "10/minute"

    # ---- Observability ----
    sentry_dsn: str = ""  # blank disables
    enable_prometheus: bool = True

    # ---- Computed ----
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @field_validator("secret_key", mode="after")
    @classmethod
    def _warn_default_secret(cls, v: str, info) -> str:
        # Don't crash dev, but make prod misconfiguration loud.
        if info.data.get("env", "").lower() == "production" and "dev-only" in v:
            raise ValueError("TM_SECRET_KEY must be set to a long random string in production")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
