"""Single source of truth for NOIP gazette filename parsing.

NOIP publishes gazettes named like `A_T3_2026.pdf` (applications, issue 3,
year 2026) and `B_T2_2026.pdf` (registrations, issue 2, year 2026). This
module extracts the three pieces of metadata from the filename.

Lives in `api/` (next to `db/models.GazetteType`, which it returns) and
is imported by both `api/routes/gazettes.py` (upload path) and
`worker/ingest.py` (job-side parsing). Before consolidation, each side
maintained its own near-duplicate regex.
"""

from __future__ import annotations

import re

from api.db.models import GazetteType

_FILENAME_RE = re.compile(r"^([ABab])_T(\d+)_(\d{4})")


def parse_filename_meta(filename: str) -> tuple[GazetteType, int | None, int | None]:
    """Extract gazette_type / issue_number / issue_year from a NOIP filename.

    Example:
        >>> parse_filename_meta("A_T3_2026.pdf")
        (GazetteType.A, 3, 2026)

    Falls back to type-only inference when the issue/year pattern doesn't
    match — an empty or unrecognised filename still produces a sensible
    `(GazetteType.A, None, None)` so the upload path doesn't crash.
    """
    letter = filename[:1].upper() if filename else "A"
    gazette_type = GazetteType.B if letter == "B" else GazetteType.A
    m = _FILENAME_RE.match(filename)
    if m:
        return gazette_type, int(m.group(2)), int(m.group(3))
    return gazette_type, None, None
