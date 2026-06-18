"""Orchestrate fetch -> parse -> derive -> store for a single IRN."""

from __future__ import annotations

from pathlib import Path

import requests
from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Trademark

from .client import fetch_raw
from .derive import derive_vn
from .parser import parse
from .store import upsert


async def enrich_one(
    session: AsyncSession,
    irn: str,
    cache_dir: Path,
    *,
    http_session: requests.Session | None = None,
    use_cache: bool = True,
    gazette_accepted: bool = True,
) -> bool:
    """Returns True if a row was written, False if skipped (unchanged).

    ``gazette_accepted`` defaults to True: every IRN this pipeline enriches
    comes from a VN-accepted gazette Madrid row (``iter_madrid_irns`` selects
    only madrid_registration / madrid_renewal rows), so VN protection is
    already established and the gazette is authoritative for VN status.
    """
    fetched = fetch_raw(irn, cache_dir, session=http_session, use_cache=use_cache)
    rec = parse(fetched.html)
    rec.irn = irn
    vn = derive_vn(rec, gazette_accepted=gazette_accepted)
    wrote = await upsert(session, rec, vn, fetched.html, fetched.source_url)

    # Backfill the gazette mark sample from the WIPO mark name when the gazette
    # transcribed no field-540 wordmark (common for Madrid 3-D/figurative marks,
    # e.g. "Hennessy PARADIS"). Only fills NULL/empty samples — never overwrites
    # a real gazette wordmark. Runs every call (idempotent) so it applies even
    # when the WIPO record itself was unchanged.
    if rec.mark_text:
        await session.execute(
            update(Trademark)
            .where(
                Trademark.lineage_key == irn,
                or_(Trademark.mark_sample.is_(None), Trademark.mark_sample == ""),
            )
            .values(mark_sample=rec.mark_text)
        )
    return wrote
