"""Backfill trademarks.logo_phash from extracted logo PNGs. Idempotent.

Mirrors backfill_mark_name.py. For each trademark with a logo_path, resolve
image_root / logo_path, compute the perceptual hash, and store the hex. Marks
with no logo stay NULL (the engine falls back to typographic). Re-run after a
fresh ingest (the ingest worker also populates it for new rows). Bump
PHASH_VERSION if the hash derivation changes.

No network. Run against the dev DB or inside any worker container:

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.backfill_logo_phash
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._phash import compute_logo_phash
from api.db.models import Trademark
from api.settings import get_settings

log = logging.getLogger("logo_phash.backfill")

PHASH_VERSION = 1
_CHUNK = 1000


async def backfill_logo_phash(
    session: AsyncSession, *, ids: Sequence[object] | None = None
) -> dict[str, int]:
    """Resolve + write logo_phash for every trademark with a logo (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    image_root = get_settings().data_dir / "image"
    stmt = select(
        Trademark.id,
        Trademark.logo_path,
        Trademark.logo_phash,
    ).where(Trademark.logo_path.is_not(None))
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        want = compute_logo_phash(image_root / row.logo_path)
        if want == row.logo_phash:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "logo_phash": want})
        if len(pending) >= _CHUNK:
            await _flush(session, pending)
            stats["updated"] += len(pending)
            pending.clear()

    if pending:
        await _flush(session, pending)
        stats["updated"] += len(pending)
    return stats


async def _flush(session: AsyncSession, rows: list[dict[str, object]]) -> None:
    tbl = Trademark.__table__
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(logo_phash=bindparam("logo_phash"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.logo_phash (PHASH_VERSION=%d)", PHASH_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_logo_phash(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
