"""Idempotent upsert of a parsed domestic record, keyed by application_number."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api._applicant_note import strip_registry_note
from api.db.models import DomesticNotFound, DomesticRecord, Trademark

from .parser import DomesticRecord as ParsedRecord

PARSE_VERSION = 1  # bump on any parser change → triggers offline re-derive

# Domestic mark categories — must match worker.domestic_sweep / the admin
# enrichment endpoint's work-list definition.
_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")


async def reconcile_not_found(session: AsyncSession) -> int:
    """Delete negative-cache rows whose appno is no longer a current
    domestic-category trademark, returning the number removed.

    A `domestic_not_found` row can outlive its mark: e.g. a mark recorded
    not-published, then re-ingested/re-categorized so it leaves the domestic
    work-list. Such an orphan still counts toward `pending_publication` on
    /admin/domestic (which counts not_found rows, not work-list membership) while
    being absent from `remaining` — so it inflates the bucket split above
    `remaining`. Pruning orphans restores the `pending + unresolved + malformed ==
    remaining` invariant. Flushes only — the caller owns the commit."""
    stmt = delete(DomesticNotFound).where(
        DomesticNotFound.application_number.not_in(
            select(Trademark.application_number)
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.application_number.is_not(None))
        )
    )
    result = cast("CursorResult[None]", await session.execute(stmt))
    await session.flush()
    return result.rowcount or 0


async def upsert_not_found(
    session: AsyncSession,
    application_number: str,
    vnid: str | None,
) -> None:
    """Record a definitive not-published mark in the negative cache. Idempotent:
    first sighting inserts (check_count=1); a re-check bumps last_checked_at +
    check_count. Flushes only — the caller owns the commit (same contract as
    `upsert`)."""
    now = datetime.now(UTC)
    stmt = (
        pg_insert(DomesticNotFound)
        .values(
            application_number=application_number,
            vnid=vnid,
            first_seen_at=now,
            last_checked_at=now,
            check_count=1,
        )
        .on_conflict_do_update(
            index_elements=[DomesticNotFound.application_number],
            set_={
                "vnid": vnid,
                "last_checked_at": now,
                "check_count": DomesticNotFound.check_count + 1,
            },
        )
    )
    await session.execute(stmt)
    await session.flush()


async def upsert(
    session: AsyncSession,
    rec: ParsedRecord,
    raw_html: str,
    source_url: str,
) -> bool:
    """Insert or update. Returns False (no write) when content_hash and
    parse_version are unchanged from the stored row."""
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    existing = (
        await session.execute(
            select(DomesticRecord).where(DomesticRecord.application_number == rec.application_number)
        )
    ).scalar_one_or_none()

    if existing and existing.content_hash == digest and existing.parse_version == PARSE_VERSION:
        return False

    values = dict(
        mark_text=rec.mark_text,
        mark_type=rec.mark_type,
        applicant_name=strip_registry_note(rec.applicant_name),
        applicant_address=rec.applicant_address,
        representative=rec.representative,
        colors=rec.colors,
        nice_classes=rec.nice_classes or None,
        goods_services=rec.goods_services or None,
        vienna_codes=rec.vienna_codes or None,
        status_code=rec.status_code,
        filing_date=rec.filing_date,
        publication_no=rec.publication_no,
        publication_date=rec.publication_date,
        grant_date=rec.grant_date,
        expiry_date=rec.expiry_date,
        logo_url=rec.logo_url,
        timeline=rec.timeline or None,
        raw=rec.raw or None,
        source_url=source_url,
        content_hash=digest,
        parse_version=PARSE_VERSION,
    )
    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        session.add(DomesticRecord(application_number=rec.application_number, **values))
    await session.flush()
    return True
