"""similar_marks scores on the resolved mark_name, never the applicant name."""

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

_GZ = uuid.UUID("e1000000-0000-4000-8000-0000000000a1")
_SUBJECT = uuid.UUID("e1000000-0000-4000-8000-0000000000a2")
_CANDIDATE = uuid.UUID("e1000000-0000-4000-8000-0000000000a3")


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
                filename="A_TEST_similar_name.pdf",
                sha256="similar_name_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Subject: figurative (no mark_sample) with a resolved name "Gemy".
        # Its APPLICANT is phonetically identical to the candidate's wordmark —
        # the old code (m_text = applicant) would score them as a match.
        s.add(
            Trademark(
                id=_SUBJECT,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="SN-2099-1",
                mark_sample=None,
                mark_name="Gemy",
                applicant_name="FOSHAN AILIHUA SANITARY WARE",
                nice_classes=["11"],
                publication_date_441=date(2099, 1, 1),
            )
        )
        # Candidate wordmark phonetically close to the subject's APPLICANT, not
        # its name. Must NOT be surfaced once we stop scoring the applicant.
        s.add(
            Trademark(
                id=_CANDIDATE,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="SN-2099-2",
                mark_sample="FOSHAN AILIHUA SANITARY WORKS",
                mark_name="FOSHAN AILIHUA SANITARY WORKS",
                applicant_name="SOME OTHER CO",
                nice_classes=["11"],
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


@pytest.mark.asyncio
async def test_similar_does_not_score_applicant_name(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_SUBJECT}/similar", params={"limit": 4})
    assert r.status_code == 200
    appnos = {item["mark"]["application_number"] for item in r.json()}
    # The candidate only "matches" via the subject's applicant text, which is no
    # longer scored, so it must not appear.
    assert "SN-2099-2" not in appnos
