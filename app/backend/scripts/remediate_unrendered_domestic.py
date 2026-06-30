"""Remediate domestic marks that persisted unrendered Angular ``${...}`` template
placeholders (the render-timing bug fixed in ``domestic_enrich.client``).

IP VIETNAM occasionally served the detail TEMPLATE before client-side interpolation:
HTTP 200 WITH ``product-form-label`` but field values left as literal ``${mk}`` /
``${sta}`` / ``${repeating.template.ap}`` bindings. Before the fetch-layer guard
(``client._is_unrendered_template``) those pages were cached and parsed, leaking
``${...}`` into ``domestic_records`` and the derived ``trademarks`` columns.

This script repairs already-corrupted data. For every appno still carrying
``${`` in EITHER ``domestic_records`` (mark_text / applicant_name / status_code)
OR ``trademarks`` (mark_name / applicant_clean / applicant_norm) — the union, so
it also catches rows whose ``domestic_records`` was deleted but whose derived
fields are stale:

  1. delete the poisoned ``{vnid}.html`` cache file (so a failed re-fetch can't
     serve the stale template, and the mark re-enters the sweep work-list),
  2. delete the corrupt ``domestic_records`` row (no ``${...}`` survives even if
     the re-fetch fails / returns not-found),
  3. ``enrich_one(use_cache=False)`` — fresh fetch through the HARDENED client
     (committed Sectigo CA bundle + rate-limiting + the unrendered-template
     guard), re-inserting a clean row on success,
  4. refresh the derived ``trademarks`` columns for the affected ids via the
     idempotent ``backfill_mark_name`` + ``backfill_entity_clean`` recompute.

Idempotent: a clean corpus finds nothing and makes no network calls. Re-runnable.
Needs network access to IP VIETNAM (run in the worker container or any env with the
deps + ``TM_DATABASE_URL`` + ``TM_DATA_DIR``)::

    TM_DATA_DIR=/srv \
    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
    python -m scripts.remediate_unrendered_domestic
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import requests
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db.models import DomesticRecord
from domestic_enrich.enrich import EnrichOutcome, UnrenderedTemplateError, enrich_one
from domestic_enrich.idmap import appno_to_vnid
from scripts.backfill_entity_clean import backfill as backfill_entity_clean
from scripts.backfill_mark_name import backfill_mark_name

log = logging.getLogger("domestic.remediate_unrendered")

# Appnos still carrying `${` in either the raw enrichment row or its derived
# trademark columns. UNION so a row whose domestic_records was already deleted
# (but whose trademarks.mark_name is still stale) is still repaired.
_AFFECTED_APPNOS = text(
    "SELECT application_number FROM domestic_records "
    "WHERE mark_text LIKE '%${%' OR applicant_name LIKE '%${%' OR status_code LIKE '%${%' "
    "UNION "
    "SELECT application_number FROM trademarks "
    "WHERE mark_name LIKE '%${%' OR applicant_clean LIKE '%${%' OR applicant_norm LIKE '%${%'"
)
_AFFECTED_TM_IDS = text("SELECT id FROM trademarks WHERE application_number = ANY(:appnos)")
_REMAINING = text(
    "SELECT "
    "(SELECT count(*) FROM domestic_records "
    " WHERE mark_text LIKE '%${%' OR applicant_name LIKE '%${%' OR status_code LIKE '%${%') AS dr, "
    "(SELECT count(*) FROM trademarks "
    " WHERE mark_name LIKE '%${%' OR applicant_clean LIKE '%${%' OR applicant_norm LIKE '%${%') AS tm"
)


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cache_dir = Path(os.environ["TM_DATA_DIR"]) / "domestic_cache"
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        appnos = [r[0] for r in (await session.execute(_AFFECTED_APPNOS)).all() if r[0]]
    log.info("affected appnos: %d", len(appnos))
    if not appnos:
        log.info("nothing to remediate")
        await engine.dispose()
        return

    http = requests.Session()
    counts = {"wrote": 0, "unchanged": 0, "not_found": 0, "unmappable": 0, "failed": 0}

    for i, appno in enumerate(appnos, 1):
        vnid = appno_to_vnid(appno)
        if vnid:
            cache_file = cache_dir / f"{vnid}.html"
            if cache_file.exists():
                cache_file.unlink()
        # Delete the corrupt row in its own committed txn so no `${...}` survives
        # even if the re-fetch below fails or returns not-found.
        async with sessionmaker() as session:
            await session.execute(delete(DomesticRecord).where(DomesticRecord.application_number == appno))
            await session.commit()
        async with sessionmaker() as session:
            try:
                outcome = await enrich_one(session, appno, cache_dir, http_session=http, use_cache=False)
                await session.commit()
                counts[outcome.value if isinstance(outcome, EnrichOutcome) else "wrote"] += 1
                log.info("[%d/%d] %s -> %s", i, len(appnos), appno, outcome)
            except UnrenderedTemplateError as e:
                await session.rollback()
                counts["failed"] += 1
                log.warning("[%d/%d] %s -> still unrendered (retry later): %s", i, len(appnos), appno, e)
            except Exception as e:  # one bad mark must not stop the remediation run
                await session.rollback()
                counts["failed"] += 1
                log.warning("[%d/%d] %s -> FAILED (retry later): %s", i, len(appnos), appno, e)

    # Refresh derived trademark columns for every affected appno's trademark rows.
    async with sessionmaker() as session:
        tm_ids = [r[0] for r in (await session.execute(_AFFECTED_TM_IDS, {"appnos": appnos})).all()]
    log.info("refreshing derived columns for %d trademark ids", len(tm_ids))
    if tm_ids:
        async with sessionmaker() as session:
            mn = await backfill_mark_name(session, ids=tm_ids)
            await session.commit()
        log.info("mark_name: %s", mn)
        async with sessionmaker() as session:
            ec = await backfill_entity_clean(session, ids=tm_ids)
            await session.commit()
        log.info("entity_clean: %s", ec)

    async with sessionmaker() as session:
        dr, tm = (await session.execute(_REMAINING)).one()
    log.info("re-enrich counts: %s", counts)
    log.info("remaining ${ rows -> domestic_records=%d trademarks=%d", dr, tm)
    if dr or tm:
        log.warning("STILL CORRUPT after remediation (likely transient fetch failures; re-run later)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
