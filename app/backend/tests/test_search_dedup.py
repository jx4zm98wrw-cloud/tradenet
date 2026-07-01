"""Query-time dedup: one mark per (appno | IRN), not one row per gazette appearance.

The `trademarks` table holds one row per gazette appearance, so a domestic mark
that has been both published (A-file application row) and granted (B-file
registration row) appears twice — same `application_number`. `/search` read the
table directly and returned both, inflating "N trademarks match" and showing a
duplicate card. These tests pin the fix: collapse rows sharing
`COALESCE(application_number, lineage_key, id)` into one result, keeping the
most-advanced row (registration over application), with `total` reflecting the
deduped count.

Seeds gazette-scoped gold rows (mirrors test_search_granted.py) so the
assertions are independent of the live corpus.
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

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000d1")

# Domestic application+registration pair (same application_number).
_DOM_APP = uuid.UUID("e0000000-0000-4000-8000-0000000000d2")  # application row
_DOM_REG = uuid.UUID("e0000000-0000-4000-8000-0000000000d3")  # registration row
# Application-only mark (no registration row).
_DOM_SOLO = uuid.UUID("e0000000-0000-4000-8000-0000000000d4")
# Madrid registration+renewal pair (same lineage_key = IRN, NULL appno).
_MAD_REG = uuid.UUID("e0000000-0000-4000-8000-0000000000d5")
_MAD_RENEW = uuid.UUID("e0000000-0000-4000-8000-0000000000d6")

_APPNO = "DEDUP-4-2099-001"
_SOLO_APPNO = "DEDUP-4-2099-002"
_IRN = "DEDUP-IRN-9001"


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
                filename="B_TEST_dedup.pdf",
                sha256="dedup_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # NOTE: mark_category + lineage_key are STORED generated columns
        # (functions of the application_number / certificate_number /
        # madrid_number signs), so they are NOT set here — the DB derives them.
        # Each row's column shape is chosen so the generated values match
        # production: domestic rows → lineage_key = application_number; Madrid
        # rows → lineage_key = madrid_number (the IRN).
        #
        # Domestic application row: appno only → mark_category
        # 'domestic_application', lineage_key = appno. Has publication date.
        s.add(
            Trademark(
                id=_DOM_APP,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=_APPNO,
                mark_sample="DEDUPMARK",
                certificate_number=None,
                publication_date_441=date(2099, 1, 1),
                vn_grant_date=None,
            )
        )
        # Domestic registration row: appno + certificate → mark_category
        # 'domestic_registration', lineage_key = appno (same as the application
        # row, so they collapse). Has certificate + grant date.
        s.add(
            Trademark(
                id=_DOM_REG,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number=_APPNO,
                mark_sample="DEDUPMARK",
                certificate_number="CERT-2099-001",
                publication_date_441=None,
                vn_grant_date=date(2099, 5, 1),
            )
        )
        # Application-only mark (no registration counterpart).
        s.add(
            Trademark(
                id=_DOM_SOLO,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=_SOLO_APPNO,
                mark_sample="SOLOMARK",
                certificate_number=None,
                publication_date_441=date(2099, 1, 2),
                vn_grant_date=None,
            )
        )
        # Madrid registration row: madrid_number only (NULL appno/cert) →
        # lineage_key = IRN. Granted (vn_grant_date set) so dedup prefers it.
        s.add(
            Trademark(
                id=_MAD_REG,
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                application_number=None,
                madrid_number=_IRN,
                mark_sample="MADRIDMARK",
                vn_grant_date=date(2099, 6, 1),
            )
        )
        # Madrid renewal row: same IRN, not granted.
        s.add(
            Trademark(
                id=_MAD_RENEW,
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                application_number=None,
                madrid_number=_IRN,
                mark_sample="MADRIDMARK",
                vn_grant_date=None,
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_appno_pair_collapses_to_one_registration(client: AsyncClient) -> None:
    """An appno present as BOTH application + registration → exactly 1 result,
    and it's the registration (certificate present). total == 1."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": _APPNO, "mode": "text", "threshold": 0, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert len(items) == 1, f"expected 1 deduped card, got {len(items)}"
    assert body["total"] == 1
    survivor = items[0]["mark"]
    assert survivor["id"] == str(_DOM_REG), "the registration row (cert present) must survive"
    assert survivor["certificate_number"] == "CERT-2099-001"


@pytest.mark.asyncio
async def test_application_only_mark_unchanged(client: AsyncClient) -> None:
    """A mark with only an application row stays a single result."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": _SOLO_APPNO, "mode": "text", "threshold": 0, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total"] == 1
    assert body["items"][0]["mark"]["id"] == str(_DOM_SOLO)


@pytest.mark.asyncio
async def test_madrid_irn_pair_collapses_to_one(client: AsyncClient) -> None:
    """Madrid registration + renewal share lineage_key (IRN) with NULL appno →
    1 result, keeping the granted (registration) row."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": _IRN, "mode": "text", "threshold": 0, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1, f"expected 1 deduped card, got {len(body['items'])}"
    assert body["total"] == 1
    assert body["items"][0]["mark"]["id"] == str(_MAD_REG), "granted registration row must survive"


@pytest.mark.asyncio
async def test_phonetic_mode_dedups_recall(client: AsyncClient) -> None:
    """Phonetic recall must also collapse the appno pair: a query that recalls
    both rows by mark name returns one card, not two."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={
            "q": "DEDUPMARK",
            "mode": "phonetic",
            "threshold": 0,
            "gazette_id": str(_GZ),
            "limit": 50,
        },
    )
    assert r.status_code == 200
    body = r.json()
    ids = [it["mark"]["id"] for it in body["items"]]
    # Both seeded rows share mark_sample DEDUPMARK; exactly one should survive.
    seeded = [i for i in ids if i in (str(_DOM_APP), str(_DOM_REG))]
    assert len(seeded) == 1, f"phonetic recall returned duplicate cards: {seeded}"
    assert seeded[0] == str(_DOM_REG), "the registration row must survive dedup"
