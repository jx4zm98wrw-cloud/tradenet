"""Entity-name grouping helpers (Phase 1 of entity canonicalization).

These form a *grouping key* so case/whitespace variants of the SAME trusted
WIPO/NOIP name collapse into one bucket for the dashboard's "top entities"
counts. They are deliberately NOT fuzzy matching — `norm()` never merges two
genuinely different names. See
docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md.
"""

from __future__ import annotations

import re
import unicodedata

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
