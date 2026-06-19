"""Orchestrate fetch -> parse -> store for a single domestic mark."""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from sqlalchemy.ext.asyncio import AsyncSession

from .client import fetch_raw
from .idmap import appno_to_vnid
from .parser import parse
from .store import upsert

log = logging.getLogger("domestic.enrich")


async def enrich_one(
    session: AsyncSession,
    application_number: str,
    cache_dir: Path,
    *,
    http_session: requests.Session | None = None,
    use_cache: bool = True,
) -> bool:
    """Returns True if a row was written, False if skipped (unchanged OR the
    application_number is unmappable). Never raises on a bad app number — logs
    and skips so one bad row can't kill a sweep chunk."""
    vnid = appno_to_vnid(application_number)
    if vnid is None:
        log.warning("unmappable application_number, skipping: %r", application_number)
        return False

    fetched = fetch_raw(vnid, cache_dir, session=http_session, use_cache=use_cache)
    rec = parse(fetched.html)
    rec.application_number = application_number  # key by our gazette id, not the VNID
    return await upsert(session, rec, fetched.html, fetched.source_url)
