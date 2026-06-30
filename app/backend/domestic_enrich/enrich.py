"""Orchestrate fetch -> parse -> store for a single domestic mark."""

from __future__ import annotations

import enum
import logging
from pathlib import Path

import requests
from sqlalchemy.ext.asyncio import AsyncSession

from .client import fetch_raw
from .idmap import appno_to_vnid
from .parser import has_unrendered_placeholder, parse
from .store import upsert, upsert_not_found

log = logging.getLogger("domestic.enrich")


class UnrenderedTemplateError(RuntimeError):
    """The parsed record still carries un-interpolated ``${...}`` Angular bindings
    — IP VIETNAM served the detail template before client-side rendering. Transient,
    not a real page: raise so the sweep counts a retryable failure and stores
    nothing. Defense-in-depth behind ``client._is_unrendered_template`` (which
    already rejects these before caching); this catches any variant that slips
    past the raw-body detector."""


class EnrichOutcome(enum.Enum):
    """How an enrich_one call resolved. Lets the caller distinguish a real write
    from a definitive not-published negative from a no-op — so the sweep can keep
    its `ok` / `not_found` / skip accounting straight (and NOT treat a not_found
    as a fetch failure that trips the circuit breaker)."""

    WROTE = "wrote"  # a domestic_records row was inserted/updated
    UNCHANGED = "unchanged"  # content_hash + parse_version matched; no write
    NOT_FOUND = "not_found"  # IP VIETNAM has no published detail yet (negative-cached)
    UNMAPPABLE = "unmappable"  # application_number couldn't map to a IP VIETNAM id


async def enrich_one(
    session: AsyncSession,
    application_number: str,
    cache_dir: Path,
    *,
    http_session: requests.Session | None = None,
    use_cache: bool = True,
) -> EnrichOutcome:
    """Fetch, parse, and store one domestic mark. Returns an EnrichOutcome rather
    than raising on a bad app number (logs + skips so one bad row can't kill a
    sweep chunk). A IP VIETNAM "not published yet" (HTTP 200 + skeleton, no detail
    marker) is recorded in the negative cache and returned as NOT_FOUND — it is
    NOT a failure."""
    vnid = appno_to_vnid(application_number)
    if vnid is None:
        log.warning("unmappable application_number, skipping: %r", application_number)
        return EnrichOutcome.UNMAPPABLE

    fetched = fetch_raw(vnid, cache_dir, session=http_session, use_cache=use_cache)
    if fetched.outcome == "not_found":
        await upsert_not_found(session, application_number, vnid)
        return EnrichOutcome.NOT_FOUND

    rec = parse(fetched.html)
    if has_unrendered_placeholder(rec):
        # Unrendered Angular template leaked through the fetch layer. Refuse to
        # store the `${...}` placeholders — raise a transient failure the sweep
        # re-attempts later (the page usually renders on a retry).
        raise UnrenderedTemplateError(
            f"unrendered template for {application_number} (vnid {vnid}); not storing"
        )
    rec.application_number = application_number  # key by our gazette id, not the VNID
    wrote = await upsert(session, rec, fetched.html, fetched.source_url)
    return EnrichOutcome.WROTE if wrote else EnrichOutcome.UNCHANGED
