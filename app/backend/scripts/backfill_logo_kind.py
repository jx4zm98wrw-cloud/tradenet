"""Backfill trademarks.logo_kind from Vienna codes + logo PNGs. Idempotent.

Mirrors backfill_logo_phash.py. For each trademark with a logo_path, classify
the specimen (Vienna-primary, pixel backstop) and store the kind. Marks with no
logo stay NULL (the visual axis routes to typographic anyway). Re-run after a
fresh ingest. Bump LOGO_KIND_VERSION if the classification rule changes.

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.backfill_logo_kind
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._phash import classify_logo_kind
from api.db.models import Trademark
from api.settings import get_settings

log = logging.getLogger("logo_kind.backfill")

LOGO_KIND_VERSION = 1
_CHUNK = 1000


async def backfill_logo_kind(session: AsyncSession, *, ids: Sequence[object] | None = None) -> dict[str, int]:
    """Classify + write logo_kind for every trademark with a logo (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    image_root = get_settings().data_dir / "image"
    stmt = select(
        Trademark.id,
        Trademark.logo_path,
        Trademark.vienna_codes,
        Trademark.logo_kind,
    ).where(Trademark.logo_path.is_not(None))
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        want = classify_logo_kind(row.vienna_codes or [], image_root / row.logo_path)
        if want == row.logo_kind:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "logo_kind": want})
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
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(logo_kind=bindparam("logo_kind"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.logo_kind (LOGO_KIND_VERSION=%d)", LOGO_KIND_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_logo_kind(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
