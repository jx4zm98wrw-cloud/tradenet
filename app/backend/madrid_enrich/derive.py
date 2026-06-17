"""Derive Vietnam protection status from a parsed MadridRecord."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from .parser import MadridRecord


class VnStatus(BaseModel):
    designated: bool
    status: str | None  # "granted" | "refused" | "pending" | None
    grant_date: date | None = None
    refusal_date: date | None = None


def _iso_to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in s.split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def derive_vn(rec: MadridRecord) -> VnStatus:
    if "VN" not in (rec.designated_countries or []):
        return VnStatus(designated=False, status=None)

    grant_date: date | None = None
    refusal_date: date | None = None
    for ev in rec.transaction_history or []:
        if "VN" not in (ev.get("parties") or []):
            continue
        t = ev.get("type", "").lower()
        d = _iso_to_date(ev.get("date"))
        if "grant of protection" in t and grant_date is None:
            grant_date = d
        elif "refusal" in t and refusal_date is None:
            refusal_date = d

    if grant_date:
        status = "granted"
    elif refusal_date:
        status = "refused"
    else:
        status = "pending"
    return VnStatus(designated=True, status=status, grant_date=grant_date, refusal_date=refusal_date)
