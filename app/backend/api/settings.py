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
    # Defaults target the docker-compose dev stack (postgres published on host :5435,
    # not the standard :5432). Production deployments must override via TM_DATABASE_URL[_SYNC]
    # — in-cluster postgres is reached on its own DNS name, not these defaults.
    database_url: str = "postgresql+asyncpg://tm:tm@localhost:5435/tm"
    database_url_sync: str = "postgresql+psycopg2://tm:tm@localhost:5435/tm"

    # ---- Redis (RQ + rate limit storage) ----
    # Same convention: defaults target compose-published :6380, not the standard :6379.
    redis_url: str = "redis://localhost:6380/0"

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

    # ---- Worker tuning ----
    # Number of trademark rows the worker bulk-inserts per session.add_all()
    # call. Larger = fewer round trips; smaller = lower memory footprint per
    # batch. 200 is the historical default tuned for the 2026 gazette set.
    worker_batch_size: int = 200

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
        # Crash hard in prod; emit a one-line stderr warning in dev so the
        # default doesn't silently bleed into a non-local environment that
        # forgot to set TM_SECRET_KEY (e.g. a staging instance running with
        # env=development by accident).
        env = info.data.get("env", "").lower()
        if "dev-only" in v:
            if env == "production":
                raise ValueError("TM_SECRET_KEY must be set to a long random string in production")
            import sys

            print(
                "WARNING: TM_SECRET_KEY is the dev default. "
                "Set it to a long random value before any non-local deployment.",
                file=sys.stderr,
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
