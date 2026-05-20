"""Runtime settings (env-driven)."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TM_", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://tm:tm@localhost:5432/tm"
    # Sync URL for Alembic (psycopg2). Derived from database_url if unset.
    database_url_sync: str = "postgresql+psycopg2://tm:tm@localhost:5432/tm"

    # Redis (for RQ workers)
    redis_url: str = "redis://localhost:6379/0"

    # Filesystem
    # Where uploaded PDFs are stored on disk (mounted volume in prod).
    upload_dir: Path = Path("/tmp/tm_uploads")
    # Data dir for cities/suffixes JSON used by tm_extractor.
    data_dir: Path = Path(__file__).resolve().parents[3]  # claude_csvbuilder/


@lru_cache
def get_settings() -> Settings:
    return Settings()
