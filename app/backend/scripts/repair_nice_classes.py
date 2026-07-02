"""Re-runnable, idempotent repair of trademarks.nice_classes from nice_group_number.

Audit W1: the old ingest mapper re-harvested Nice classes by scanning the raw
(511) goods prose for any 1-2 digit token, so incidental digits (quantities like
"10 kg", "3 chiều", page refs) leaked in as phantom classes, and values were
stored unpadded ("5") instead of the zero-padded convention ("05") used by the
domestic/madrid enrichment tables. ~1.4k rows were corrupted.

The extractor already parsed the classes correctly into `nice_group_number`
(comma-joined, zero-padded, grammar-scoped, 1-45 validated), stored on every
trademark row. This is a PURE RECOMPUTE from that authoritative column — no
network, no re-ingest, no re-parse: nice_classes := deduped split of
nice_group_number (empty group -> NULL). It mirrors the mapper's
`_classes_from_group_number`, so a fresh ingest already produces correct values
and this only needs running once to fix historical rows (and after any bulk load
that predates the mapper fix).

Idempotent: only rows whose recomputed array differs from the stored value are
UPDATEd; a second run is a no-op.

    docker compose -f app/docker-compose.yml exec -T worker-domestic \
        python -m scripts.repair_nice_classes
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Trademark

log = logging.getLogger("nice_classes.repair")

REPAIR_VERSION = 1
_CHUNK = 1000


def _classes_from_group_number(raw: object) -> list[str] | None:
    """Range-validated (1-45), zero-padded, deduped split of `nice_group_number`.

    Kept in sync with worker.mapper._classes_from_group_number (the ingest-time
    twin) — change both together.
    """
    if not raw:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for tok in str(raw).split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            continue
        if not (1 <= n <= 45):
            continue
        c = f"{n:02d}"
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out or None


async def repair_nice_classes(
    session: AsyncSession, *, ids: Sequence[object] | None = None
) -> dict[str, int]:
    """Recompute + write nice_classes for every trademark (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    stmt = select(Trademark.id, Trademark.nice_classes, Trademark.nice_group_number)
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        want = _classes_from_group_number(row.nice_group_number)
        if want == row.nice_classes:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "nice_classes": want})
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
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(nice_classes=bindparam("nice_classes"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("repairing trademarks.nice_classes (REPAIR_VERSION=%d)", REPAIR_VERSION)
    async with sessionmaker() as session:
        stats = await repair_nice_classes(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
