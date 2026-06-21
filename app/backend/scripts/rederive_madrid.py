"""Offline re-derive of every ``madrid_records`` row from its cached WIPO HTML.

No network: reads only the on-disk raw-HTML cache and re-runs parse -> derive ->
upsert. ``store.upsert`` rewrites a row when either the content hash OR the
``PARSE_VERSION`` changed, so bumping ``PARSE_VERSION`` (see store.py) makes this
re-derive every row even though the cached HTML is byte-identical.

Used after a parser change that must propagate to already-fetched records
without re-hitting WIPO (mirrors how domestic_enrich re-derives offline). Run
inside the worker-madrid container where the cache lives:

    docker compose -f app/docker-compose.yml exec -T worker-madrid \
        python -m scripts.rederive_madrid

A cache miss is SKIPPED (counted), never fetched, so this can never touch the
network.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from madrid_enrich.backfill import iter_madrid_irns
from madrid_enrich.derive import derive_vn
from madrid_enrich.parser import parse
from madrid_enrich.store import PARSE_VERSION, upsert

log = logging.getLogger("madrid.rederive")

CACHE_DIR = Path(os.environ.get("TM_MADRID_CACHE_DIR", "/data/madrid_cache"))


async def rederive(session: AsyncSession, cache_dir: Path) -> dict[str, int]:
    irns = await iter_madrid_irns(session)
    stats = {"total": len(irns), "rewritten": 0, "unchanged": 0, "missing_cache": 0, "errors": 0}
    for n, irn in enumerate(irns, 1):
        path = cache_dir / f"{irn}.html"
        if not path.exists():
            stats["missing_cache"] += 1
            continue
        try:
            html = path.read_text(encoding="utf-8")
            rec = parse(html)
            rec.irn = irn
            vn = derive_vn(rec, gazette_accepted=True)
            wrote = await upsert(session, rec, vn, html, f"cache://{irn}")
            await session.commit()
            stats["rewritten" if wrote else "unchanged"] += 1
        except Exception as exc:  # one bad row must not abort the batch
            await session.rollback()
            stats["errors"] += 1
            log.warning("re-derive failed for IRN %s: %s", irn, exc)
        if n % 500 == 0:
            log.info("progress %d/%d: %s", n, stats["total"], stats)
    return stats


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_url = os.environ["TM_DATABASE_URL"]
    engine = create_async_engine(db_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("re-deriving madrid_records to PARSE_VERSION=%d from cache %s", PARSE_VERSION, CACHE_DIR)
    async with sessionmaker() as session:
        stats = await rederive(session, CACHE_DIR)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
