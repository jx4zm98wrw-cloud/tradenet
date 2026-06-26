"""Text-mode threshold filters by match-quality bucket, and the count matches.

Regression for two coupled bugs in the non-phonetic branch of search_trademarks:
  A) `total` was the pre-threshold WHERE count, so the header/footer claimed more
     marks than the grid rendered once the threshold filtered any out.
  B) text scores carried a ±0.04 random jitter, so equally-relevant substring
     matches (all bucket 0.92) straddled a high threshold by coin-flip.

Fix: text scores are the un-jittered bucket (exact 0.98 / substring 0.92 / token
0.78 / prefix 0.76), and `total` reflects the post-threshold count.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000e1")
# 1 exact "PILL" + 3 substring ("...pill...") marks, all mark_sample NULL so the
# resolved wordmark is mark_name.
_EXACT = uuid.UUID("e0000000-0000-4000-8000-0000000000e2")
_SUBS = [
    uuid.UUID("e0000000-0000-4000-8000-0000000000e3"),
    uuid.UUID("e0000000-0000-4000-8000-0000000000e4"),
    uuid.UUID("e0000000-0000-4000-8000-0000000000e5"),
]


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="A_TEST_text_threshold.pdf",
                sha256="text_threshold_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        s.add(
            Trademark(
                id=_EXACT,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="TT-2099-0",
                mark_sample=None,
                mark_name="PILL",  # exact wordmark match → bucket 0.98
                applicant_name="EXACT CO",
                publication_date_441=date(2099, 1, 1),
            )
        )
        for i, (mid, name) in enumerate(
            zip(_SUBS, ["PILLOWFORT", "CATERPILLAR", "PAPILLIO"], strict=True), start=1
        ):
            s.add(
                Trademark(
                    id=mid,
                    gazette_id=_GZ,
                    record_type=RecordType.A,
                    application_number=f"TT-2099-{i}",
                    mark_sample=None,
                    mark_name=name,  # contains "pill" → bucket 0.92
                    applicant_name="SUBSTRING CO",
                    publication_date_441=date(2099, 1, 1),
                )
            )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


async def _search(client: AsyncClient, *, threshold: float) -> dict:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "pill", "mode": "text", "threshold": threshold, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    return r.json()


@pytest.mark.asyncio
async def test_substring_matches_score_exactly_092_no_jitter(client: AsyncClient) -> None:
    # Bug B: every substring match must score EXACTLY 0.92 (no random jitter).
    body = await _search(client, threshold=0)
    subs = {it["mark"]["application_number"]: it["score"] for it in body["items"]}
    for appno in ("TT-2099-1", "TT-2099-2", "TT-2099-3"):
        assert subs[appno] == 0.92
    assert subs["TT-2099-0"] == 0.98  # exact wordmark match


@pytest.mark.asyncio
async def test_high_threshold_keeps_only_exact_and_count_matches(client: AsyncClient) -> None:
    # Bug A + B: at 0.95 only the exact 0.98 mark passes; substring 0.92 all drop.
    # total must equal the post-threshold count (1), NOT the WHERE count (4).
    body = await _search(client, threshold=0.95)
    appnos = [it["mark"]["application_number"] for it in body["items"]]
    assert appnos == ["TT-2099-0"]
    assert body["total"] == 1
    assert body["total"] == len(body["items"])  # header/footer match the grid


@pytest.mark.asyncio
async def test_threshold_just_below_substring_keeps_all(client: AsyncClient) -> None:
    # At 0.90 every bucket (0.98 + 0.92) passes deterministically → all 4, total 4.
    body = await _search(client, threshold=0.90)
    assert body["total"] == 4
    assert len(body["items"]) == 4


@pytest.mark.asyncio
async def test_threshold_between_buckets_is_deterministic(client: AsyncClient) -> None:
    # 0.93 sits between the 0.92 and 0.98 buckets: no coin-flip — every substring
    # match drops, only the exact one remains. (Pre-fix, jitter let ~some 0.92
    # marks survive at random.)
    body = await _search(client, threshold=0.93)
    assert body["total"] == 1
    assert [it["mark"]["application_number"] for it in body["items"]] == ["TT-2099-0"]
