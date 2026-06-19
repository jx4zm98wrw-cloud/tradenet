"""Polite, resumable WIPO backfill over Madrid IRNs."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Trademark

from .enrich import enrich_one  # referenced via module attr so tests can monkeypatch

log = logging.getLogger("madrid.backfill")

_MADRID_CATEGORIES = ("madrid_registration", "madrid_renewal")


async def iter_madrid_irns(session: AsyncSession) -> list[str]:
    """Distinct WIPO IRNs (= trademarks.lineage_key) for Madrid rows."""
    rows = (
        (
            await session.execute(
                select(Trademark.lineage_key)
                .where(Trademark.mark_category.in_(_MADRID_CATEGORIES))
                .where(Trademark.lineage_key.is_not(None))
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return [r for r in rows if r]


class CircuitBreaker:
    """Trips after N consecutive failures so a WIPO outage / rate-block halts
    the batch instead of hammering. Any success resets the streak."""

    def __init__(self, max_consecutive: int = 5) -> None:
        self.max_consecutive = max_consecutive
        self._streak = 0

    @property
    def tripped(self) -> bool:
        return self._streak >= self.max_consecutive

    def record_failure(self) -> None:
        self._streak += 1

    def record_success(self) -> None:
        self._streak = 0


@dataclass
class BackfillResult:
    attempted: int = 0
    written: int = 0
    skipped: int = 0
    failed: int = 0
    circuit_broke: bool = False


async def run_backfill(
    session: AsyncSession,
    *,
    cache_dir: Path,
    limit: int | None = None,
    delay: float = 3.0,
    jitter: float = 1.0,
    max_consecutive: int = 5,
    daily_cap: int | None = None,
    force: bool = False,
    progress_every: int = 25,
) -> BackfillResult:
    """Enrich Madrid IRNs politely. Resumable: enrich_one() skips records whose
    content is unchanged (content_hash), so re-running is cheap. `limit` caps the
    count (pilot mode); `daily_cap` is a hard self-imposed network ceiling."""
    irns = await iter_madrid_irns(session)
    if limit is not None:
        irns = irns[:limit]

    res = BackfillResult()
    cb = CircuitBreaker(max_consecutive=max_consecutive)
    for irn in irns:
        if cb.tripped:
            res.circuit_broke = True
            log.warning(
                "circuit breaker tripped after %d consecutive failures — halting",
                max_consecutive,
            )
            break
        if daily_cap is not None and res.attempted >= daily_cap:
            log.info("daily cap %d reached — stopping", daily_cap)
            break
        res.attempted += 1
        try:
            wrote = await enrich_one(session, irn, cache_dir=cache_dir, use_cache=not force)
            await session.commit()
            cb.record_success()
            if wrote:
                res.written += 1
            else:
                res.skipped += 1
        except Exception as exc:  # one bad IRN must not kill the batch
            await session.rollback()
            res.failed += 1
            cb.record_failure()
            log.warning("enrich failed for IRN %s: %s", irn, exc)
        if res.attempted % progress_every == 0:
            log.info(
                "progress: %d attempted (%d written, %d skipped, %d failed)",
                res.attempted,
                res.written,
                res.skipped,
                res.failed,
            )
        if delay:
            await asyncio.sleep(delay + random.uniform(0, jitter))  # jitter, not crypto
    return res
