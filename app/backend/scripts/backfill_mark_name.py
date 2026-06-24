"""Re-runnable, idempotent backfill of the denormalized trademarks.mark_name.

Per trademark, resolves the display name from the trusted source by
deterministic priority:
  1. trademarks.mark_sample   (the gazette (540) wordmark, case preserved)
  2. domestic_records.mark_text  (IP VIETNAM, joined by application_number)
     for domestic marks
  3. madrid_records.mark_text    (WIPO, joined by lineage_key = irn)
     for Madrid marks
  else NULL (figurative-only mark with no transcribed name).

~172k domestic marks otherwise display their applicant instead of the real
mark name; this column lets every API consumer read the resolved name without
a per-request join (mirrors trademarks.vn_grant_date). The ingest worker does
NOT populate this column, so re-run this after a fresh ingest or a
domestic/Madrid enrichment sweep to pick up newly resolvable names.

Idempotent: only rows whose computed name differs from the stored value are
UPDATEd, so a second run is a no-op. Bump MARK_NAME_VERSION after changing the
derivation; the next run then rewrites the affected rows.

No network. Run against the dev DB or inside any worker container:

    docker compose -f app/docker-compose.yml exec -T worker-domestic \
        python -m scripts.backfill_mark_name
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import DomesticRecord, MadridRecord, Trademark

log = logging.getLogger("mark_name.backfill")

MARK_NAME_VERSION = 1

_DOMESTIC = ("domestic_application", "domestic_registration")
_MADRID = ("madrid_registration", "madrid_renewal")
_CHUNK = 1000


def _clean(value: object) -> str | None:
    """Trim whitespace; treat empty/blank as absent (None)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def backfill_mark_name(session: AsyncSession, *, ids: Sequence[object] | None = None) -> dict[str, int]:
    """Resolve + write mark_name for every trademark (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    stmt = (
        select(
            Trademark.id,
            Trademark.mark_category,
            Trademark.mark_sample,
            Trademark.mark_name,
            DomesticRecord.mark_text.label("dom_mark_text"),
            MadridRecord.mark_text.label("mad_mark_text"),
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
        want = _clean(row.mark_sample)
        if want is None:
            if row.mark_category in _DOMESTIC:
                want = _clean(row.dom_mark_text)
            elif row.mark_category in _MADRID:
                want = _clean(row.mad_mark_text)
            else:
                want = None

        if want == row.mark_name:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "mark_name": want})
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
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(mark_name=bindparam("mark_name"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.mark_name (MARK_NAME_VERSION=%d)", MARK_NAME_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_mark_name(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
