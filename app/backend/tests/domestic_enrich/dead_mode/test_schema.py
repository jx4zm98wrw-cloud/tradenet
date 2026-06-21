import pytest
from sqlalchemy import select

from api.db.models import DomesticSweepControl as C


@pytest.mark.asyncio
async def test_dead_mode_columns_exist_with_defaults(db_session):
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.mode in ("normal", "dead")
    assert isinstance(row.concurrency, int)


@pytest.mark.asyncio
async def test_can_set_dead_and_concurrency(db_session):
    # flush (NOT commit) so the live dev singleton is never actually mutated.
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    row.mode = "dead"
    row.concurrency = 4
    await db_session.flush()
    again = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert again.mode == "dead"
    assert again.concurrency == 4
