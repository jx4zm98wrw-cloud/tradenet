"""Derive Vietnam protection status from a parsed MadridRecord.

Gazette-authoritative rule
--------------------------
Every IRN this pipeline enriches is harvested from Vietnam's gazette
"Madrid accepted in VN" section, which means VN protection is *already
established* at the source. The status derivation therefore treats the
gazette as authoritative: when ``gazette_accepted=True`` the record is
"granted", full stop. WIPO's transaction history is consulted only to
supply the grant *date*; it can never downgrade an accepted record to
"refused" or "pending".

Provisional != final
---------------------
A WIPO "provisional refusal of protection" is an *interim* office action
during examination -- it is routinely lifted by a later grant. It is NOT
a terminal refusal. Only a *final* refusal event (a confirmation of total
provisional refusal, a final decision, an invalidation, or a refusal that
is explicitly total/final/confirmed) is treated as terminal, and even
then only in the non-gazette WIPO-refined fallback path used by callers
that do not have a gazette acceptance signal. The previous implementation
conflated provisional with final and wrongly marked accepted records
"refused".
"""

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


def _vn_events(rec: MadridRecord) -> list[tuple[str, date | None]]:
    """VN-party events as (lowercased type, parsed-or-None date) tuples."""
    out: list[tuple[str, date | None]] = []
    for ev in rec.transaction_history or []:
        if "VN" not in (ev.get("parties") or []):
            continue
        out.append((ev.get("type", "").lower(), _iso_to_date(ev.get("date"))))
    return out


def _is_grant(t: str) -> bool:
    return "grant of protection" in t or "statement of grant" in t or "the mark is protected" in t


def _is_designation(t: str) -> bool:
    """A VN *designation* event -- the moment VN protection commences.

    Either a later "Subsequent designation, VN" or the original
    "International Registration" event that lists VN among its parties. Used as
    the grant-date fallback for legacy (Agreement-era) records that carry no
    explicit "Grant of protection, VN" transaction. ``startswith`` deliberately
    excludes "Replacement of national registration by an international
    registration", which mentions VN but is not a designation, and "Renewal",
    which only proves protection predates it (an upper bound, never a grant).
    """
    t = t.strip()
    return t.startswith("subsequent designation") or t.startswith("international registration")


def _is_refusal(t: str) -> bool:
    """Any VN refusal event -- provisional OR final.

    Used to disqualify the designation-date fallback: if VN ever refused
    (even provisionally) after designation, the designation date predates the
    actual grant, so it must not be used as ``vn_grant_date``.
    """
    return "refusal" in t


def _is_final_refusal(t: str) -> bool:
    """A FINAL (terminal) refusal -- NOT a bare provisional refusal."""
    if "confirmation of total provisional refusal" in t:
        return True
    if "final decision" in t:
        return True
    if "invalidation" in t:
        return True
    return "refusal" in t and ("total" in t or "final" in t or "confirm" in t)


def derive_vn(rec: MadridRecord, *, gazette_accepted: bool = False) -> VnStatus:
    designated = gazette_accepted or ("VN" in (rec.designated_countries or []))
    if not designated:
        return VnStatus(designated=False, status=None)

    events = _vn_events(rec)

    grant_dates = [d for (t, d) in events if _is_grant(t) and d is not None]
    grant_date = min(grant_dates) if grant_dates else None

    if gazette_accepted:
        # The gazette is authoritative: VN protection is established. Prefer an
        # explicit WIPO grant date; otherwise fall back to the VN *designation*
        # event date (the accurate commencement of protection). Records whose
        # only VN signal is a Renewal keep grant_date=None (date unrecoverable;
        # granted per gazette).
        if grant_date is None and not any(_is_refusal(t) for (t, _d) in events):
            # Designation date is a valid grant date only when VN never refused
            # (even provisionally). A refusal means the real grant came later, on
            # a date WIPO did not record -> leave grant_date null.
            designation_dates = [d for (t, d) in events if _is_designation(t) and d is not None]
            grant_date = min(designation_dates) if designation_dates else None
        return VnStatus(
            designated=True,
            status="granted",
            grant_date=grant_date,
            refusal_date=None,
        )

    # WIPO-refined fallback for callers without a gazette acceptance signal.
    final_refusal_dates = [d for (t, d) in events if _is_final_refusal(t) and d is not None]
    final_refusal_date = min(final_refusal_dates) if final_refusal_dates else None

    # Guard: an active registration (reg + exp both present) is never refused.
    has_active_registration = rec.registration_date is not None and rec.expiration_date is not None

    if grant_date:
        status = "granted"
        refusal_date = None
    elif final_refusal_date and not has_active_registration:
        status = "refused"
        refusal_date = final_refusal_date
    else:
        status = "pending"
        refusal_date = None

    return VnStatus(
        designated=True,
        status=status,
        grant_date=grant_date,
        refusal_date=refusal_date,
    )
