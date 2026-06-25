"""One-off: measure the Hamming-distance distribution of real logo pHash pairs.

Confirms the unrelated baseline (~32 of 64 bits) that motivates the recalibrated
visual curve. Read-only. Run against the dev DB:

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.calibrate_phash_threshold
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db.models import Trademark
from tm_similarity.visual import _hamming_hex

_SAMPLE = 6000  # random pHash-bearing rows; consecutive pairs → ~3000 random pairs


async def _main() -> None:
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        stmt = (
            select(Trademark.logo_phash)
            .where(Trademark.logo_phash.is_not(None))
            .order_by(Trademark.id)  # deterministic; "random enough" across gazettes
            .limit(_SAMPLE)
        )
        hashes = [r[0] for r in (await s.execute(stmt)).all()]
    await engine.dispose()

    hist: Counter[int] = Counter()
    for a, b in zip(hashes[::2], hashes[1::2]):
        hist[_hamming_hex(a, b)] += 1
    total = sum(hist.values())
    print(f"pairs={total}")
    cum = 0
    for hd in range(0, 65):
        cum += hist.get(hd, 0)
        if hist.get(hd, 0) or hd in (5, 10, 16, 32):
            print(f"hd={hd:2d}  n={hist.get(hd,0):5d}  cum%={100*cum/total:5.1f}")


if __name__ == "__main__":
    asyncio.run(_main())
