"""Derive a human status from a parsed DomesticRecord's NOIP status field.

NOIP's status field is polymorphic: a numeric code (e.g. 1904) for pending
applications, or Vietnamese text ("Cấp bằng" = granted) once granted. Numeric
codes get mapped to a label via STATUS_LABELS (extend as observed); text
statuses are already human-readable and pass through unchanged. `is_granted`
is true when a grant date exists OR the status text is a recognized granted
phrase. Pure — no I/O.
"""

from __future__ import annotations

from pydantic import BaseModel

from .parser import DomesticRecord

STATUS_LABELS: dict[str, str] = {
    "1904": "Under examination",
}
_GRANTED_TEXT = ("cấp bằng", "granted")


class DomesticStatus(BaseModel):
    code: str | None
    label: str
    is_granted: bool


def derive_status(rec: DomesticRecord) -> DomesticStatus:
    code = rec.status_code
    label = STATUS_LABELS.get(code or "", code or "Unknown")
    norm = (code or "").strip().lower()
    is_granted = rec.grant_date is not None or any(g in norm for g in _GRANTED_TEXT)
    return DomesticStatus(code=code, label=label, is_granted=is_granted)
