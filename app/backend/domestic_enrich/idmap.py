"""Map a gazette application number to the IP VIETNAM WIPOPublish detail id.

`trademarks.application_number` is `4-YYYY-NNNNN` (sometimes `VN`-prefixed or
dashed differently). IP VIETNAM's detail endpoint keys on `VN` + the digits:
`4-2026-18514` -> `VN4202618514`. Validated on 8 random marks. Unmappable /
malformed inputs return None so the caller can skip + log rather than crash.
"""

from __future__ import annotations

import re

# A mappable VN trademark application number must contain a leading type-code
# digit, a 4-digit year, and a serial — at least 7 digits once non-alphanumerics
# are stripped (e.g. 4 + 2026 + 18514). Anything shorter is an extraction
# artifact, not a real id.
_MIN_DIGITS = 7
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")
_LEADING_VN = re.compile(r"^VN", re.IGNORECASE)


def appno_to_vnid(application_number: str | None) -> str | None:
    if not application_number or not application_number.strip():
        return None
    # Strip any VN prefix first, then every non-alphanumeric (dashes, spaces).
    core = _NON_ALNUM.sub("", _LEADING_VN.sub("", application_number.strip()))
    if not core.isdigit() or len(core) < _MIN_DIGITS:
        return None
    return f"VN{core}"
