"""Entity-name grouping helpers (Phase 1 of entity canonicalization).

These form a *grouping key* so case/whitespace variants of the SAME trusted
WIPO/IP VIETNAM name collapse into one bucket for the dashboard's "top entities"
counts. They are deliberately NOT fuzzy matching — `norm()` never merges two
genuinely different names. See
docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md.
"""

from __future__ import annotations

import re
import unicodedata

from ._applicant_note import strip_registry_note

_WS_RE = re.compile(r"\s+")
# WIPO `representative` concatenates the firm name with its postal address.
# The address always begins at the first comma or digit-run; cut there. This is
# a deterministic boundary, not a fuzzy guess.
_MADRID_ADDR_RE = re.compile(r"[,\d]")


def norm(s: str) -> str:
    """Grouping key: NFC-normalize → casefold → collapse internal whitespace → trim.

    Collapses trivial case/whitespace/diacritic-encoding variants of one name so
    they count as a single entity. It MUST NOT merge distinct names — it is not
    fuzzy matching.
    """
    s = unicodedata.normalize("NFC", s)
    s = s.casefold()
    s = _WS_RE.sub(" ", s)
    return s.strip()


def strip_madrid_rep_address(s: str) -> str:
    """Deterministically drop a WIPO representative's trailing glued address.

    Takes the text up to the first comma or digit-run. Apply BEFORE `norm()` so
    address-only differences (same firm, different office address) collapse.
    Returns the head verbatim (not normalized) so the caller can keep the raw
    firm spelling for display.
    """
    return _MADRID_ADDR_RE.split(s, maxsplit=1)[0]


ENTITY_CLEAN_VERSION = 2
"""Logical version of the clean-name derivation in resolve_applicant /
resolve_representative. There is NO per-row version column — the backfill
(scripts/backfill_entity_clean.py) is idempotent by recompute-and-compare —
so this constant is a documentation/trigger marker: bump it after changing
the derivation and the next backfill run rewrites the affected rows. Surfaced
in the backfill log."""


def _clean_and_norm(raw: str | None) -> tuple[str | None, str | None]:
    """Trim `raw`, returning (clean_display, norm_key) or (None, None) when it
    is blank or norms to empty. `clean` keeps the original spelling for display;
    `norm_key` is the grouping key."""
    if not raw:
        return None, None
    clean = raw.strip()
    if not clean:
        return None, None
    key = norm(clean)
    if not key:
        return None, None
    return clean, key


def _first_nonblank(*vals: str | None) -> str | None:
    """First value that is non-None and not whitespace-only."""
    for v in vals:
        if v and v.strip():
            return v
    return None


def resolve_applicant(
    domestic: str | None, madrid: str | None, gazette: str | None
) -> tuple[str | None, str | None]:
    """Trusted display name + grouping key for an applicant.

    Precedence: IP VIETNAM (`domestic_records.applicant_name`) → WIPO
    (`madrid_records.holder_name`) → gazette fallback
    (`trademarks.applicant_name`). The callers gate `domestic`/`madrid` by
    `mark_category`, so at most one is set per mark.

    Leading IP VIETNAM processing-notes (delivery/opinion/merge markers) are stripped
    before clean/norm so the note never reaches the display value OR the grouping
    key — the same company can't fragment across a noted and un-noted variant.
    """
    return _clean_and_norm(strip_registry_note(_first_nonblank(domestic, madrid, gazette)))


def resolve_representative(
    domestic: str | None, madrid: str | None, gazette: str | None
) -> tuple[str | None, str | None]:
    """Trusted display name + grouping key for a representative.

    Precedence IP VIETNAM (`domestic_records.representative`) → WIPO
    (`madrid_records.representative`) → gazette fallback
    (`trademarks.ip_agency_raw_740`). The WIPO value glues a trailing postal
    address onto the firm name; strip it (deterministic cut) before clean/norm.
    """
    if domestic and domestic.strip():
        return _clean_and_norm(domestic)
    if madrid and madrid.strip():
        return _clean_and_norm(strip_madrid_rep_address(madrid))
    return _clean_and_norm(gazette)
