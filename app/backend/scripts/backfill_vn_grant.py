"""Re-runnable, idempotent backfill of the denormalized trademarks.vn_grant_date.

Per trademark, resolves the unified VN registration grant date (NULL = not
granted) from the trusted source by deterministic identifier:
  IP VIETNAM   domestic_records.grant_date          (joined by application_number)
  WIPO         madrid_records.vn_grant_date          (joined by lineage_key = irn,
                                                       only when vn_status='granted')
Candidates are gated by mark_category so each mark draws only from its own
regime's trusted source (mirrors the Phase-1 /overview sourcing). The ingest
worker does NOT populate this column (like *_norm), so re-run this after a fresh
ingest or a domestic/Madrid enrichment sweep to pick up newly granted marks.

Idempotent: only rows whose computed grant date differs from the stored value
are UPDATEd, so a second run is a no-op. Bump VN_GRANT_VERSION after changing
the derivation; the next run then rewrites the affected rows.

No network. Run against the dev DB or inside any worker container:

    docker compose -f app/docker-compose.yml exec -T worker-domestic \
        python -m scripts.backfill_vn_grant
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import DomesticRecord, MadridRecord, Trademark

log = logging.getLogger("vn_grant.backfill")

VN_GRANT_VERSION = 1

_DOMESTIC = ("domestic_application", "domestic_registration")
_MADRID = ("madrid_registration", "madrid_renewal")
_CHUNK = 1000


async def backfill_vn_grant(session: AsyncSession, *, ids: Sequence[object] | None = None) -> dict[str, int]:
    """Resolve + write vn_grant_date for every trademark (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    stmt = (
        select(
            Trademark.id,
            Trademark.mark_category,
            Trademark.vn_grant_date,
            DomesticRecord.grant_date.label("dom_grant_date"),
            MadridRecord.vn_grant_date.label("mad_vn_grant_date"),
            MadridRecord.vn_status.label("mad_vn_status"),
        )
        .select_from(Trademark)
        .outerjoin(
            DomesticRecord,
            DomesticRecord.application_number == Trademark.application_number,
        )
        .outerjoin(MadridRecord, MadridRecord.irn == Trademark.lineage_key)
    )
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        if row.mark_category in _DOMESTIC:
            want = row.dom_grant_date
        elif row.mark_category in _MADRID:
            want = row.mad_vn_grant_date if row.mad_vn_status == "granted" else None
        else:
            want = None

        if want == row.vn_grant_date:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "vn_grant_date": want})
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
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(vn_grant_date=bindparam("vn_grant_date"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.vn_grant_date (VN_GRANT_VERSION=%d)", VN_GRANT_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_vn_grant(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
