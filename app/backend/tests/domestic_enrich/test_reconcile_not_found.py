"""reconcile_not_found prunes orphan negative-cache rows.

An orphan is a domestic_not_found row whose appno is no longer a current
domestic-category trademark (re-ingested/re-categorized after the negative-cache
row was written). It inflates pending_publication on /admin/domestic while being
absent from `remaining`. Reconcile must delete exactly those, leaving rows whose
appno is still a live domestic mark untouched.

Uses the rollback-on-teardown db_session, so the seeded Gazette/Trademark/
not_found rows never persist past the test.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import DomesticNotFound
from domestic_enrich.store import reconcile_not_found

_GZ = uuid.UUID("f0000000-0000-4000-8000-0000000000e1")
_TM = uuid.UUID("f0000000-0000-4000-8000-0000000000e2")
_LIVE_APPNO = "4-9888-88801"  # backed by a current domestic trademark -> kept
_ORPHAN_APPNO = "4-9888-88802"  # no backing domestic trademark -> pruned


@pytest.mark.asyncio
async def test_reconcile_prunes_orphan_keeps_live(db_session):
    db_session.add(
        Gazette(
            id=_GZ,
            filename="A_TEST_reconcile.pdf",
            sha256="reconcile_" + uuid.uuid4().hex,
            gazette_type=GazetteType.A,
            issue_year=2098,
            storage_path="/dev/null",
            size_bytes=0,
            status=GazetteStatus.completed,
        )
    )
    # A current domestic_application mark for the LIVE appno (generated
    # mark_category resolves to 'domestic_application' from application_number).
    db_session.add(
        Trademark(
            id=_TM,
            gazette_id=_GZ,
            record_type=RecordType.A,
            application_number=_LIVE_APPNO,
        )
    )
    # Negative-cache rows: one backed by the live mark, one orphan.
    db_session.add(DomesticNotFound(application_number=_LIVE_APPNO, vnid="VN9888888801"))
    db_session.add(DomesticNotFound(application_number=_ORPHAN_APPNO, vnid="VN9888888802"))
    await db_session.flush()

    deleted = await reconcile_not_found(db_session)

    assert deleted >= 1  # at least our seeded orphan (dev DB may carry others)
    remaining = set((await db_session.execute(select(DomesticNotFound.application_number))).scalars().all())
    assert _ORPHAN_APPNO not in remaining  # orphan pruned
    assert _LIVE_APPNO in remaining  # live mark's negative-cache row untouched


@pytest.mark.asyncio
async def test_reconcile_idempotent(db_session):
    """A second pass over the same session deletes nothing more (the orphans are
    already gone)."""
    db_session.add(DomesticNotFound(application_number=_ORPHAN_APPNO, vnid="VN9888888802"))
    await db_session.flush()

    first = await reconcile_not_found(db_session)
    assert first >= 1
    second = await reconcile_not_found(db_session)
    assert second == 0
