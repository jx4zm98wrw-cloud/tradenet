"""Backfill WIPO Madrid enrichment for the Madrid IRNs in the DB.

Pilot 100:   python -m scripts.enrich_madrid --limit 100
Full sweep:  python -m scripts.enrich_madrid
Re-fetch:    python -m scripts.enrich_madrid --force --limit 50

Politeness: ~`--delay` s between live fetches (+ jitter), a circuit breaker on
consecutive failures, and an optional `--daily-cap`. Resumable — unchanged
records are skipped via content hash, so re-runs are cheap.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from api.db.session import async_session
from api.settings import get_settings
from madrid_enrich.backfill import run_backfill


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WIPO Madrid enrichment backfill")
    p.add_argument("--limit", type=int, default=None, help="cap IRNs (pilot mode)")
    p.add_argument("--delay", type=float, default=3.0, help="seconds between live fetches")
    p.add_argument("--jitter", type=float, default=1.0)
    p.add_argument("--daily-cap", type=int, default=None, help="hard network ceiling")
    p.add_argument("--max-consecutive", type=int, default=5, help="circuit-breaker threshold")
    p.add_argument("--force", action="store_true", help="ignore raw-HTML cache, re-fetch")
    p.add_argument("--cache-dir", type=Path, default=None)
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cache_dir = args.cache_dir or (get_settings().data_dir / "madrid_cache")
    async with async_session() as session:
        res = await run_backfill(
            session,
            cache_dir=cache_dir,
            limit=args.limit,
            delay=args.delay,
            jitter=args.jitter,
            daily_cap=args.daily_cap,
            max_consecutive=args.max_consecutive,
            force=args.force,
        )
    logging.getLogger("madrid.backfill").info(
        "DONE: attempted=%d written=%d skipped=%d failed=%d circuit_broke=%s",
        res.attempted,
        res.written,
        res.skipped,
        res.failed,
        res.circuit_broke,
    )


if __name__ == "__main__":
    asyncio.run(_main())
