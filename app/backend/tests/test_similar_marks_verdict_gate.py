"""similar_marks recalls by mark_name and gates on the engine conjunction verdict."""

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

_GZ = uuid.UUID("e2000000-0000-4000-8000-0000000000b1")
_SUBJECT = uuid.UUID("e2000000-0000-4000-8000-0000000000b2")  # "Gemy", class 11
_CLASSMATE = uuid.UUID("e2000000-0000-4000-8000-0000000000b3")  # unrelated name, class 11
_NEAR_SAME = uuid.UUID("e2000000-0000-4000-8000-0000000000b4")  # "Gemmy", class 11
_NEAR_DIFF = uuid.UUID("e2000000-0000-4000-8000-0000000000b5")  # "Gemmy", class 42
_NAMEONLY = uuid.UUID("e2000000-0000-4000-8000-0000000000b6")  # "Gemmy", class 11, NULL mark_sample


def _tm(tid: uuid.UUID, appno: str, sample: str | None, name: str, classes: list[str]) -> Trademark:
    return Trademark(
        id=tid,
        gazette_id=_GZ,
        record_type=RecordType.A,
        application_number=appno,
        mark_sample=sample,
        mark_name=name,
        applicant_name="APPLICANT " + appno,
        nice_classes=classes,
        publication_date_441=date(2099, 1, 1),
    )


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
                filename="A_TEST_verdict_gate.pdf",
                sha256="verdict_gate_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        s.add(_tm(_SUBJECT, "VG-1", None, "Gemy", ["11"]))
        s.add(_tm(_CLASSMATE, "VG-2", "KAVIN SAVING POWER", "KAVIN SAVING POWER", ["11"]))
        s.add(_tm(_NEAR_SAME, "VG-3", "Gemmy", "Gemmy", ["11"]))
        s.add(_tm(_NEAR_DIFF, "VG-4", "Gemmy", "Gemmy", ["42"]))
        # Same as VG-3 but wordmark lives ONLY in mark_name (NULL mark_sample) —
        # the ~172k domestic-mark shape the old mark_sample-gated recall ignored.
        s.add(_tm(_NAMEONLY, "VG-5", None, "Gemmy", ["11"]))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


async def _appnos(client: AsyncClient) -> set[str]:
    r = await client.get(f"/api/v1/marks/{_SUBJECT}/similar", params={"limit": 10})
    assert r.status_code == 200
    return {item["mark"]["application_number"] for item in r.json()}


@pytest.mark.asyncio
async def test_class_only_classmate_excluded(client: AsyncClient) -> None:
    # The reported Gemy bug: a same-class wordmark with no name resemblance. Now
    # filtered out (no trigram/phonetic overlap with "Gemy" → not even recalled,
    # and Low risk if it were). The verdict gate itself is isolated by VG-4 below.
    assert "VG-2" not in await _appnos(client)


@pytest.mark.asyncio
async def test_real_name_match_same_class_included(client: AsyncClient) -> None:
    # "Gemmy" in the same class — real sight-or-sound + related goods → shown.
    assert "VG-3" in await _appnos(client)


@pytest.mark.asyncio
async def test_name_match_but_class_mismatch_excluded(client: AsyncClient) -> None:
    # Same name "Gemmy" but a non-overlapping class → verdict "Low risk" → dropped.
    assert "VG-4" not in await _appnos(client)


@pytest.mark.asyncio
async def test_mark_name_only_candidate_recalled(client: AsyncClient) -> None:
    # B1 regression: a confusable candidate whose wordmark is ONLY in mark_name
    # (NULL mark_sample) must be recalled + shown, exactly like its mark_sample
    # twin VG-3. The old `mark_sample IS NOT NULL` recall gate excluded ~70% of
    # the corpus (all mark_name-only domestic marks) — this would fail on it.
    assert "VG-5" in await _appnos(client)
