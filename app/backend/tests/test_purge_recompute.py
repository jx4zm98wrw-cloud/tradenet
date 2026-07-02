"""Purge must repair is_representative for cross-gazette dedup groups (audit W2).

`worker.ingest._purge_trademarks` deletes every row of one gazette. If a deleted
row was its dedup group's representative and the group ALSO has a surviving row
in another gazette (a domestic appno present as an A-file application row AND a
B-file registration row), the survivor must be PROMOTED to representative — else
the mark falls out of `representative_marks` (search/browse/facets) entirely.

Sync session (psycopg2) to match the worker. Synthetic gazettes/appnos in a
private range so the shared dev DB is never disturbed.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from api._dedup import recompute_is_representative_sql
from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from worker.ingest import _purge_trademarks

_G_APP = uuid.UUID("e3000000-0000-4000-8000-0000000009a1")  # A-file gazette (survives)
_G_REG = uuid.UUID("e3000000-0000-4000-8000-0000000009a2")  # B-file gazette (purged)
_APP = uuid.UUID("e3000000-0000-4000-8000-0000000009a3")
_REG = uuid.UUID("e3000000-0000-4000-8000-0000000009a4")
_SOLO = uuid.UUID("e3000000-0000-4000-8000-0000000009a5")  # only in the purged gazette
_APPNO = "PURGE-4-2098-001"
_SOLO_APPNO = "PURGE-4-2098-002"


def _gz(gid: uuid.UUID, fn: str, gt: GazetteType) -> Gazette:
    return Gazette(
        id=gid,
        filename=fn,
        sha256="purge_" + uuid.uuid4().hex,
        gazette_type=gt,
        issue_year=2098,
        storage_path="/dev/null",
        size_bytes=0,
        status=GazetteStatus.completed,
    )


@pytest.fixture
def sync_session() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(get_settings().database_url_sync, future=True)
    Session = sessionmaker(engine)
    gids = [_G_APP, _G_REG]
    with Session() as s:
        s.execute(delete(Trademark).where(Trademark.gazette_id.in_(gids)))
        s.execute(delete(Gazette).where(Gazette.id.in_(gids)))
        s.commit()
        s.add(_gz(_G_APP, "A_TEST_purge.pdf", GazetteType.A))
        s.add(_gz(_G_REG, "B_TEST_purge.pdf", GazetteType.B))
        # appno _APPNO: application row in G_APP + registration row in G_REG.
        s.add(
            Trademark(
                id=_APP,
                gazette_id=_G_APP,
                record_type=RecordType.A,
                application_number=_APPNO,
                applicant_name="PURGE CO",
                mark_sample="PURGEMARK",
            )
        )
        s.add(
            Trademark(
                id=_REG,
                gazette_id=_G_REG,
                record_type=RecordType.B_domestic,
                application_number=_APPNO,
                applicant_name="PURGE CO",
                mark_sample="PURGEMARK",
                certificate_number="CERT-2098-1",
                vn_grant_date=date(2098, 1, 1),
            )
        )
        # A mark that lives ONLY in the purged gazette (no survivor).
        s.add(
            Trademark(
                id=_SOLO,
                gazette_id=_G_REG,
                record_type=RecordType.B_domestic,
                application_number=_SOLO_APPNO,
                applicant_name="PURGE SOLO",
                mark_sample="SOLOMARK",
                certificate_number="CERT-2098-2",
            )
        )
        s.commit()
        # Establish the true representatives: the registration row wins the
        # cross-gazette group (certificate present), the solo wins its own.
        s.execute(text(recompute_is_representative_sql(scoped_to_gazette=True)), {"gid": _G_REG})
        s.commit()
    yield Session
    with Session() as s:
        s.execute(delete(Trademark).where(Trademark.gazette_id.in_(gids)))
        s.execute(delete(Gazette).where(Gazette.id.in_(gids)))
        s.commit()
    engine.dispose()


def _rep(s: Session, tid: uuid.UUID) -> bool | None:
    return s.execute(select(Trademark.is_representative).where(Trademark.id == tid)).scalar_one_or_none()


def test_purge_promotes_surviving_cross_gazette_row(sync_session: sessionmaker[Session]) -> None:
    with sync_session() as s:
        # Precondition: the registration row is the representative, the
        # application row is not.
        assert _rep(s, _REG) is True
        assert _rep(s, _APP) is False

        purged = _purge_trademarks(s, _G_REG)
        assert purged == 2  # registration + solo

        # The purged registration row is gone; its surviving application-row twin
        # must now be the representative so the mark stays visible.
        assert _rep(s, _REG) is None
        assert _rep(s, _APP) is True


def test_purge_of_solo_mark_is_clean(sync_session: sessionmaker[Session]) -> None:
    # The solo mark had no survivor; purge simply removes it with no error and no
    # orphaned representative left behind.
    with sync_session() as s:
        _purge_trademarks(s, _G_REG)
        assert _rep(s, _SOLO) is None
        # No row anywhere still claims the solo's dedup key.
        remaining = s.execute(select(Trademark.id).where(Trademark.application_number == _SOLO_APPNO)).all()
        assert remaining == []
