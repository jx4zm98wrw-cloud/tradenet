"""Re-runnable, idempotent backfill of the denormalized clean entity columns.

Per trademark, resolves the trusted display name + grouping key for the
applicant and representative by deterministic identifier:
  IP VIETNAM   domestic_records  (joined by application_number)
  WIPO   madrid_records    (joined by lineage_key = irn)
  gazette fallback         (trademarks.applicant_name / ip_agency_raw_740)
Candidates are gated by mark_category so each mark draws only from its own
regime's trusted source (mirrors the Phase-1 /overview sourcing).

Reuses api._entity_norm so the stored *_norm is byte-identical to what the
dashboard groups by. Idempotent: only rows whose computed (clean, norm) differ
from the stored values are UPDATEd, so a second run is a no-op. Bump
ENTITY_CLEAN_VERSION (api/_entity_norm.py) after changing the derivation; the
next run then rewrites the affected rows.

No network. Run against the dev DB or inside any worker container:

    docker compose -f app/docker-compose.yml exec -T worker-domestic \
        python -m scripts.backfill_entity_clean
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._entity_norm import (
    ENTITY_CLEAN_VERSION,
    resolve_applicant,
    resolve_representative,
)
from api.db.models import DomesticRecord, MadridRecord, Trademark

log = logging.getLogger("entity.backfill")

_DOMESTIC = ("domestic_application", "domestic_registration")
_MADRID = ("madrid_registration", "madrid_renewal")
_CHUNK = 1000


async def backfill(session: AsyncSession, *, ids: Sequence[object] | None = None) -> dict[str, int]:
    """Resolve + write clean columns for every trademark (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    stmt = (
        select(
            Trademark.id,
            Trademark.mark_category,
            Trademark.applicant_clean,
            Trademark.applicant_norm,
            Trademark.representative_clean,
            Trademark.representative_norm,
            DomesticRecord.applicant_name.label("dom_app"),
            DomesticRecord.representative.label("dom_rep"),
            MadridRecord.holder_name.label("mad_app"),
            MadridRecord.representative.label("mad_rep"),
            Trademark.applicant_name.label("gaz_app"),
            Trademark.ip_agency_raw_740.label("gaz_rep"),
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
        is_dom = row.mark_category in _DOMESTIC
        is_mad = row.mark_category in _MADRID
        app_clean, app_norm = resolve_applicant(
            row.dom_app if is_dom else None,
            row.mad_app if is_mad else None,
            row.gaz_app,
        )
        rep_clean, rep_norm = resolve_representative(
            row.dom_rep if is_dom else None,
            row.mad_rep if is_mad else None,
            row.gaz_rep,
        )
        if (app_clean, app_norm, rep_clean, rep_norm) == (
            row.applicant_clean,
            row.applicant_norm,
            row.representative_clean,
            row.representative_norm,
        ):
            stats["unchanged"] += 1
            continue
        pending.append(
            {
                "b_id": row.id,
                "applicant_clean": app_clean,
                "applicant_norm": app_norm,
                "representative_clean": rep_clean,
                "representative_norm": rep_norm,
            }
        )
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
    stmt = (
        update(tbl)
        .where(tbl.c.id == bindparam("b_id"))
        .values(
            applicant_clean=bindparam("applicant_clean"),
            applicant_norm=bindparam("applicant_norm"),
            representative_clean=bindparam("representative_clean"),
            representative_norm=bindparam("representative_norm"),
        )
    )
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling entity clean columns (ENTITY_CLEAN_VERSION=%d)", ENTITY_CLEAN_VERSION)
    async with sessionmaker() as session:
        stats = await backfill(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
