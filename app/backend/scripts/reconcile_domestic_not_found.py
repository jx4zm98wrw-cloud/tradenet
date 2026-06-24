"""Prune orphan rows from the ``domestic_not_found`` negative cache.

A ``domestic_not_found`` row can outlive its mark: a mark recorded not-published,
then re-ingested or re-categorized so its appno is no longer a current
domestic-category trademark. The orphan still counts toward
``pending_publication`` on /admin/domestic (that bucket counts not_found rows,
not work-list membership) while being absent from ``remaining`` — so it inflates
the bucket split above ``remaining`` and forces the invariant test to be ``>=``
rather than ``==``.

This deletes exactly those orphans (appnos not in the domestic-category
trademark work-list), restoring ``pending + unresolved + malformed == remaining``.
Idempotent: a clean DB deletes nothing. No network. Run inside the worker
container (or any env with TM_DATABASE_URL):

    docker compose -f app/docker-compose.yml exec -T worker-domestic \
        python -m scripts.reconcile_domestic_not_found
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domestic_enrich.store import reconcile_not_found

log = logging.getLogger("domestic.reconcile")


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        deleted = await reconcile_not_found(session)
        await session.commit()
    await engine.dispose()
    log.info("DONE: pruned %d orphan domestic_not_found row(s)", deleted)
    print({"reconciled": deleted})


if __name__ == "__main__":
    asyncio.run(_main())
