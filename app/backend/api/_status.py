"""Single source of truth for a mark's display status (label + tone).

Label is IP VIETNAM-faithful: the enriched domestic status_code verbatim when
present, else a normalized fallback (Granted/Lapsed/Pending). Tone is normalized
from grant/expiry so even a Vietnamese status string gets a sensible color.
"""

from __future__ import annotations

from datetime import date


def derive_status(
    domestic_status_code: str | None,
    vn_grant_date: date | None,
    expiry_date: date | None,
    *,
    today: date,
) -> tuple[str, str]:
    """Return (label, tone); tone in {"ok", "warn", "mute"}."""
    if vn_grant_date is not None:
        tone = "ok"
    elif expiry_date is not None and expiry_date < today:
        tone = "mute"
    else:
        tone = "warn"

    if domestic_status_code:
        label = domestic_status_code
    elif vn_grant_date is not None:
        label = "Granted"
    elif expiry_date is not None and expiry_date < today:
        label = "Lapsed"
    else:
        label = "Pending"
    return label, tone
