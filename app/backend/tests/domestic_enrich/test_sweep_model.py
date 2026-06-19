import pytest
from sqlalchemy import select

from api.db.models import DomesticSweepControl


@pytest.mark.asyncio
async def test_singleton_seed_row_exists(db_session):
    row = (
        await db_session.execute(select(DomesticSweepControl).where(DomesticSweepControl.id == 1))
    ).scalar_one()
    assert row.status == "idle"
    assert row.chunk_size == 25
    assert row.processed == 0
