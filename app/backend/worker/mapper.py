"""Map tm_extractor section dicts → Trademark ORM rows.

The section dict uses WIPO marker codes as keys (e.g. "(111)", "(731)") plus
derived columns ("Applicant Name", "Total Group", "Month", etc.). This module
normalizes those into typed columns matching the ORM model.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from api._applicant_note import strip_registry_note
from api.db.models import RecordType, Trademark
from tm_extractor.constants import MISSING_COUNTRY_CODE

_DATE_DMY_RE = re.compile(r"^\s*(\d{1,2})[./](\d{1,2})[./](\d{4})\s*$")
_DATE_MDY_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def _parse_date(value: Any) -> date | None:
    """Section dicts come from the post-`reformat_date` pipeline which emits MM/DD/YYYY
    for date markers. Be lenient and accept DD/MM/YYYY too just in case.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # First try ISO date.
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    # The pipeline canonical form is MM/DD/YYYY.
    m = _DATE_MDY_RE.match(s)
    if m:
        mm, dd, yyyy = m.groups()
        try:
            return date(int(yyyy), int(mm), int(dd))
        except ValueError:
            return None
    return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s if s != "" else None


def _country_code(value: Any) -> str | None:
    """Coerce the extractor's `Applicant Country Code` to an ISO-2 or NULL.

    The extractor writes MISSING_COUNTRY_CODE (currently "Unknown") when no
    ISO code was matched in the applicant text; that's a missing-value
    sentinel, not a real code — store NULL so DB constraints (varchar(2))
    and queries stay clean. Lowercase comparison so the sentinel's case
    convention can change without breaking this normalisation.
    """
    s = _str(value)
    if s is None:
        return None
    s = s.strip().lower()
    if not s or s == MISSING_COUNTRY_CODE.lower():
        return None
    return s.upper()[:2]


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _classes_from_group_number(raw: Any) -> list[str] | None:
    """Nice-class array from the extractor's already-parsed ``Group Number``.

    ``Group Number`` (from ``compute_511_fields``) is the source of truth for a
    section's Nice classes: comma-joined, grammar-scoped (only "Nhóm N" digits,
    or a strict all-numeric list). We split, range-validate to 1-45, zero-pad,
    and dedup (preserving order) — so the queryable array holds only real Nice
    classes in the canonical 2-digit form used across domestic/madrid
    enrichment. (The raw ``Group Number`` string is kept verbatim in
    ``nice_group_number`` and may still contain e.g. an out-of-range "Nhóm 99"
    the gazette printed; the ``Nhóm N`` grammar is not range-validated upstream.)

    Do NOT re-harvest classes from the raw (511) goods text — that prose carries
    incidental digits (quantities like "10 kg", "3 chiều", page refs) that a
    blind ``\\d{1,2}`` scan turns into phantom classes. That older approach
    corrupted ~1.4k rows before this fix (audit W1).
    """
    if not raw:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for tok in str(raw).split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            continue
        if not (1 <= n <= 45):
            continue
        c = f"{n:02d}"
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out or None


def _vienna_to_array(raw: Any) -> list[str] | None:
    if not raw:
        return None
    # Vienna codes are dotted numerics separated by ; or whitespace.
    parts = re.split(r"[;\s]+", str(raw).strip())
    return [p for p in (p.strip() for p in parts) if p] or None


def section_to_trademark(
    gazette_id: uuid.UUID,
    record_type: RecordType,
    section: dict[str, Any],
    logo_path: str | None = None,
) -> Trademark:
    """Build a Trademark row from a tm_extractor section dict.

    `logo_path` is the relative path of the extracted logo PNG under
    `<data_dir>/image/`, e.g. ``"2026/A_T2_2026/4-2026-00001.png"``. Pass
    None when no logo was extracted for this row — the column stays NULL
    and the frontend falls back to mark_sample text rendering.
    """
    # The section dict still uses raw "(NNN)" keys (the rename to "NNN <desc>"
    # happens inside create_csv, after this function would have run).
    s = section
    return Trademark(
        gazette_id=gazette_id,
        record_type=record_type,
        application_number=_str(s.get("(210)")),
        certificate_number=_str(s.get("(111)")),
        madrid_number=_str(s.get("(116)")),
        submission_date=_parse_date(s.get("(220)")),
        publication_date_441=_parse_date(s.get("(441)")),
        publication_date_450=_parse_date(s.get("(450)")),
        registration_date_151=_parse_date(s.get("(151)")),
        renewal_date_156=_parse_date(s.get("(156)")),
        expiry_date_141=_parse_date(s.get("(141)")),
        expiry_date_181=_parse_date(s.get("(181)")),
        validity_171=_str(s.get("(171)")),
        validity_176=_str(s.get("(176)")),
        month=_int(s.get("Month")),
        year=_int(s.get("Year")),
        nice_classes=_classes_from_group_number(s.get("Group Number")),
        nice_total=_int(s.get("Total Group")),
        nice_group_number=_str(s.get("Group Number")),
        raw_511_text=_str(s.get("(511)")),
        vienna_codes=_vienna_to_array(s.get("(531)")),
        raw_531_text=_str(s.get("(531)")),
        mark_sample=_str(s.get("(540)")),
        mark_status=_str(s.get("(551)")),
        protected_colors=_str(s.get("(591)")),
        priority_300=_str(s.get("(300)")),
        related_app_641=_str(s.get("(641)")),
        origin_822=_str(s.get("(822)")),
        territory_831=_str(s.get("(831)")),
        applicant_raw_731=_str(s.get("(731)")),
        owner_raw_732=_str(s.get("(732)")),
        applicant_name=strip_registry_note(_str(s.get("Applicant Name"))),
        applicant_address=_str(s.get("Applicant Address")),
        applicant_country_code=_country_code(s.get("Applicant Country Code")),
        applicant_city=_str(s.get("Applicant City")),
        applicant_type=_str(s.get("Applicant Type")),
        ip_agency_raw_740=_str(s.get("(740)")),
        ip_agency=_str(s.get("IPAgency")),
        ip_agency_status=_str(s.get("IPAgencyStatus")),
        gazette_ref_field=_str(s.get("Gazette")),
        date_combined=_str(s.get("DateCombined_441_450")),
        extra_markers=None,
        logo_path=logo_path,
    )


def infer_record_type(gazette_letter: str, section: dict[str, Any]) -> RecordType:
    if gazette_letter == "A":
        return RecordType.A
    # B-file: split by whether (116) is non-empty.
    if str(section.get("(116)", "")).strip():
        return RecordType.B_madrid
    return RecordType.B_domestic
