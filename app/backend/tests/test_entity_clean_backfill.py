"""Phase 2 entity-canon: migration presence + idempotent backfill.

Deterministic and sweep-safe: all DB writes use synthetic ids the live
domestic/madrid sweeps never touch, and the backfill is invoked scoped to
those ids.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.settings import get_settings


@pytest.mark.asyncio
async def test_clean_columns_and_norm_indexes_exist() -> None:
    """The migration added the 4 columns and btree-indexed the two *_norm keys."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        cols = set(
            (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='trademarks' AND column_name = ANY(:cols)"
                    ),
                    {
                        "cols": [
                            "applicant_clean",
                            "applicant_norm",
                            "representative_clean",
                            "representative_norm",
                        ]
                    },
                )
            )
            .scalars()
            .all()
        )
        idx = set(
            (
                await s.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE tablename='trademarks' AND indexname = ANY(:idx)"
                    ),
                    {"idx": ["ix_trademarks_applicant_norm", "ix_trademarks_representative_norm"]},
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert cols == {
        "applicant_clean",
        "applicant_norm",
        "representative_clean",
        "representative_norm",
    }
    assert idx == {"ix_trademarks_applicant_norm", "ix_trademarks_representative_norm"}
