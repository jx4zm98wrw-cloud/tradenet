"""Orchestrate fetch -> parse -> derive -> store for a single IRN."""

from __future__ import annotations

from pathlib import Path

import requests
from sqlalchemy.ext.asyncio import AsyncSession

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
    return await upsert(session, rec, vn, fetched.html, fetched.source_url)
