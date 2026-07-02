"""Alembic environment — uses the sync DB URL from Settings and reads metadata from api.db."""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from api.db.models import Base
from api.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url at runtime from settings — keeps secrets out of alembic.ini.
config.set_main_option("sqlalchemy.url", get_settings().database_url_sync)

target_metadata = Base.metadata

# Functional / expression indexes created via raw SQL in migrations — they have
# no ORM-model representation, so autogenerate (and `alembic check`) would flag
# them as "extra" objects to drop. Exclude them from drift detection. These back
# the two-stage similar-marks recall (pg_trgm GIN + Double-Metaphone btree).
_MANUAL_INDEXES = {
    "ix_trademarks_mark_sample_trgm",
    "ix_trademarks_applicant_name_trgm",
    "ix_trademarks_mark_name_trgm",
    "ix_trademarks_mark_sample_dmeta",
    "ix_trademarks_applicant_name_dmeta",
    "ix_trademarks_mark_name_dmeta",
    "ix_trademarks_mark_sample_ltrgm",
    "ix_trademarks_pubdate_rep",
    "ix_trademarks_mark_category",
    "ix_trademarks_lineage_key",
    "ix_madrid_records_designated_countries",
}

# STORED generated columns added via raw SQL (mark_category, lineage_key). Their
# stored CASE/COALESCE expression is normalised by Postgres and would be flagged
# as drift against the model's Computed() string, so they're excluded from
# autogenerate comparison.
_MANUAL_COLUMNS = {"mark_category", "lineage_key"}


def _include_object(object_, name, type_, reflected, compare_to) -> bool:
    if type_ == "index":
        return name not in _MANUAL_INDEXES
    if type_ == "column":
        return name not in _MANUAL_COLUMNS
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
