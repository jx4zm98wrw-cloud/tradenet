"""Idempotent upsert of a parsed + derived Madrid record, keyed by IRN."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import MadridRecord

from .derive import VnStatus
from .parser import MadridRecord as ParsedRecord

PARSE_VERSION = 3


async def upsert(
    session: AsyncSession,
    rec: ParsedRecord,
    vn: VnStatus,
    raw_html: str,
    source_url: str,
) -> bool:
    """Insert or update. Returns False (no write) when the content hash and
    parse_version are unchanged from the stored row."""
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    existing = (
        await session.execute(select(MadridRecord).where(MadridRecord.irn == rec.irn))
    ).scalar_one_or_none()

    if existing and existing.content_hash == digest and existing.parse_version == PARSE_VERSION:
        return False

    values = dict(
        holder_name=rec.holder_name,
        holder_address=rec.holder_address,
        holder_country=rec.holder_country,
        holder_legal_status=rec.holder_legal_status,
        mark_text=rec.mark_text,
        representative=rec.representative,
        registration_date=rec.registration_date,
        expiration_date=rec.expiration_date,
        nice_classes=rec.nice_classes or None,
        designated_countries=rec.designated_countries or None,
        basic_registration=rec.basic_registration,
        language=rec.language,
        vn_designated=vn.designated,
        vn_status=vn.status,
        vn_grant_date=vn.grant_date,
        vn_refusal_date=vn.refusal_date,
        transaction_history=rec.transaction_history or None,
        designation_status=rec.designation_status or None,
        raw=rec.raw or None,
        source_url=source_url,
        content_hash=digest,
        parse_version=PARSE_VERSION,
    )
    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        session.add(MadridRecord(irn=rec.irn, **values))
    await session.flush()
    return True
