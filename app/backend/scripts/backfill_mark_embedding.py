"""Backfill trademarks.mark_embedding from mark_name. Idempotent.

Mirrors backfill_logo_phash.py. For each trademark with a non-NULL mark_name,
compute the LaBSE embedding and store the bytea. Marks with no mark_name stay
NULL (the future semantic axis falls back to no-signal). BACKFILL-ONLY: the
ingest worker does NOT set mark_embedding (its source mark_name is itself
backfill-derived) — run this AFTER backfill_mark_name, and re-run after a fresh
ingest. Bump EMBED_VERSION if the model or normalisation changes.

No network beyond the one-time model download. Run against the dev DB or any
worker container:

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.backfill_mark_embedding
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._embed import Encoder, compute_mark_embeddings
from api.db.models import Trademark

log = logging.getLogger("mark_embedding.backfill")

EMBED_VERSION = 1
_CHUNK = 1000  # DB write batch (rows per UPDATE flush)
_ENCODE_BATCH = 256  # texts per encoder call — saturates CPU vs the old batch-of-1


async def backfill_mark_embedding(
    session: AsyncSession, *, ids: Sequence[object] | None = None, encoder: Encoder | None = None
) -> dict[str, int]:
    """Resolve + write mark_embedding for every trademark with a mark_name (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}. Rows are encoded in
    chunks of `_ENCODE_BATCH` via compute_mark_embeddings (one encoder call per
    chunk — batched throughput; byte-identical output to the per-row path). `encoder`
    is passed through (tests inject a fake; production uses LaBSE).
    """
    stmt = select(
        Trademark.id,
        Trademark.mark_name,
        Trademark.mark_embedding,
    ).where(Trademark.mark_name.is_not(None))
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for start in range(0, len(rows), _ENCODE_BATCH):
        chunk = rows[start : start + _ENCODE_BATCH]
        wants = compute_mark_embeddings([row.mark_name for row in chunk], encoder=encoder)
        for row, want in zip(chunk, wants, strict=True):
            stats["scanned"] += 1
            if want == row.mark_embedding:
                stats["unchanged"] += 1
                continue
            pending.append({"b_id": row.id, "mark_embedding": want})
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
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(mark_embedding=bindparam("mark_embedding"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.mark_embedding (EMBED_VERSION=%d)", EMBED_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_mark_embedding(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
