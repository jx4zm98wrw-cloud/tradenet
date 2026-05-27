"""Per-field record-quality audit.

Codifies the residual patterns documented in CLAUDE.md so Phase 4 can detect
regressions and any new occurrences after the full re-ingest. Each check
returns a list of suspect rows; the master report aggregates counts.

Categories
==========
1. **Applicant-name pollution**
   - Madrid reg# leaked into (732)  (CLAUDE.md: ~14 B rows)
   - Address fragment leaked into (732)  (CLAUDE.md: ~7 B rows)
   - IP-agency-style name leaked into (732)
   - Looks like a TM marker or pure punctuation

2. **Field-presence rules**
   - VN rows missing applicant_city  (CLAUDE.md: ~31 rows)
   - Any row missing both (540) AND logo_path  (CLAUDE.md: 7 documented)
   - B-rows missing registration_date_151 (should always have it)
   - Nice classes outside 1..45 range

3. **Date sanity**
   - publication_date_441 should match year/month
   - submission_date <= publication_date_441 <= registration_date_151

4. **Marker leakage in mark_sample**
   - Mark sample containing "(591)" / "(531)" / "(740)" — extractor merge bug

Usage
-----
    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    ../.venv/bin/python -m scripts.audit_fields
"""

from __future__ import annotations

import json
import re
import sys

from sqlalchemy import and_, create_engine, func, or_, select

from api.db.models import RecordType, Trademark
from api.settings import get_settings


def _conn():
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    return engine.connect()


def check_madrid_number_in_applicant() -> list[dict]:
    """B-rows where applicant_name starts with a 7-digit Madrid reg#.

    Pattern: "(732) 1529250 (DE) Jack Wolfskin …" — the extractor split
    on the wrong delimiter and kept the number as if it were the name.
    """
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.madrid_number,
                Trademark.applicant_name,
            ).where(
                and_(
                    Trademark.applicant_name.is_not(None),
                    # Starts with 6-8 digits, possibly followed by " (XX) "
                    Trademark.applicant_name.op("~")(r"^[0-9]{6,8}([\s(]|$)"),
                )
            )
        ).all()
    return [
        {
            "id": str(r.id),
            "app_or_cert": r.application_number or r.certificate_number or r.madrid_number,
            "applicant_name": r.applicant_name,
        }
        for r in rows
    ]


_ADDRESS_FRAGMENT_PREFIX = re.compile(
    r"^\d+[A-Za-z]?[-\s,.]"  # "503-ho,", "12 ", "10th,"
    r"|^(SỐ|Số|No\.?|Apt|Suite|Floor|Lô|Lot)\b",
    re.IGNORECASE,
)


def check_address_fragment_in_applicant() -> list[dict]:
    """B-rows where applicant_name is clearly an address fragment, not a name."""
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.applicant_name,
            ).where(Trademark.applicant_name.is_not(None))
        ).all()
    suspects = []
    for r in rows:
        name = (r.applicant_name or "").strip()
        if _ADDRESS_FRAGMENT_PREFIX.match(name):
            suspects.append(
                {
                    "id": str(r.id),
                    "app_or_cert": r.application_number or r.certificate_number,
                    "applicant_name": name,
                }
            )
    return suspects


def check_vn_missing_city() -> list[dict]:
    """VN rows with no applicant_city — extractor failed the city match.
    CLAUDE.md says ~31 before, post-fix ~31; verify count hasn't ballooned.
    """
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.applicant_name,
                Trademark.applicant_raw_731,
            ).where(
                and_(
                    Trademark.applicant_country_code == "VN",
                    Trademark.applicant_city.is_(None),
                )
            )
        ).all()
    return [
        {
            "id": str(r.id),
            "app_or_cert": r.application_number or r.certificate_number,
            "applicant_name": r.applicant_name,
            "raw_731_snippet": (r.applicant_raw_731 or "")[:200],
        }
        for r in rows
    ]


def check_neither_540_nor_logo() -> list[dict]:
    """The documented 7 — only count if it grows."""
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.applicant_name,
                Trademark.record_type,
            ).where(
                and_(
                    Trademark.mark_sample.is_(None),
                    Trademark.logo_path.is_(None),
                )
            )
        ).all()
    return [
        {
            "id": str(r.id),
            "app_or_cert": r.application_number or r.certificate_number,
            "applicant_name": r.applicant_name,
            "record_type": r.record_type.value if r.record_type else None,
        }
        for r in rows
    ]


def check_b_missing_registration_date() -> list[dict]:
    """B-domestic / B-Madrid rows missing the (151) registration date.
    Every B-row should have one — its absence implies parser miss."""
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.certificate_number,
                Trademark.madrid_number,
                Trademark.applicant_name,
                Trademark.record_type,
            ).where(
                and_(
                    Trademark.record_type != RecordType.A,
                    Trademark.registration_date_151.is_(None),
                )
            )
        ).all()
    return [
        {
            "id": str(r.id),
            "cert_or_madrid": r.certificate_number or r.madrid_number,
            "applicant_name": r.applicant_name,
            "record_type": r.record_type.value if r.record_type else None,
        }
        for r in rows
    ]


def check_invalid_nice_classes() -> list[dict]:
    """Any nice_classes value outside 1..45 range."""
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.nice_classes,
            ).where(Trademark.nice_classes.is_not(None))
        ).all()
    bad = []
    for r in rows:
        for c in (r.nice_classes or []):
            try:
                n = int(c)
                if not (1 <= n <= 45):
                    bad.append({"id": str(r.id), "class_value": c})
                    break
            except (ValueError, TypeError):
                bad.append({"id": str(r.id), "class_value": c})
                break
    return bad


_INID_MARKER_IN_TEXT = re.compile(r"\((\d{3})\)")


def check_marker_leakage_in_mark_sample() -> list[dict]:
    """mark_sample (540) containing what looks like another INID marker.
    Extractor merge bug — the (540) section accidentally consumed text
    from the next marker.
    """
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.mark_sample,
            ).where(Trademark.mark_sample.is_not(None))
        ).all()
    suspects = []
    for r in rows:
        if _INID_MARKER_IN_TEXT.search(r.mark_sample or ""):
            suspects.append(
                {
                    "id": str(r.id),
                    "app_or_cert": r.application_number or r.certificate_number,
                    "mark_sample": r.mark_sample,
                }
            )
    return suspects


def check_year_month_vs_pub_date() -> list[dict]:
    """`year` and `month` columns derived from publication_date_441 should agree."""
    with _conn() as conn:
        rows = conn.execute(
            select(
                Trademark.id,
                Trademark.year,
                Trademark.month,
                Trademark.publication_date_441,
            ).where(
                and_(
                    Trademark.publication_date_441.is_not(None),
                    or_(
                        Trademark.year != func.extract("year", Trademark.publication_date_441),
                        Trademark.month != func.extract("month", Trademark.publication_date_441),
                    ),
                )
            )
        ).all()
    return [
        {
            "id": str(r.id),
            "year": r.year,
            "month": r.month,
            "pub_date": r.publication_date_441.isoformat() if r.publication_date_441 else None,
        }
        for r in rows
    ]


CHECKS = {
    "madrid_number_in_applicant": check_madrid_number_in_applicant,
    "address_fragment_in_applicant": check_address_fragment_in_applicant,
    "vn_missing_city": check_vn_missing_city,
    "neither_540_nor_logo": check_neither_540_nor_logo,
    "b_missing_registration_date": check_b_missing_registration_date,
    "invalid_nice_classes": check_invalid_nice_classes,
    "marker_leakage_in_mark_sample": check_marker_leakage_in_mark_sample,
    "year_month_vs_pub_date": check_year_month_vs_pub_date,
}

# Documented baselines from CLAUDE.md — used to flag *regressions* (any
# growth beyond these is new and worth investigating). Set to None where
# no prior baseline is documented.
BASELINES = {
    "madrid_number_in_applicant": 14,
    "address_fragment_in_applicant": 7,
    "vn_missing_city": 31,
    "neither_540_nor_logo": 7,
    "b_missing_registration_date": None,
    "invalid_nice_classes": 0,
    "marker_leakage_in_mark_sample": 0,
    "year_month_vs_pub_date": 0,
}


def main() -> None:
    report = {}
    for name, fn in CHECKS.items():
        suspects = fn()
        baseline = BASELINES.get(name)
        delta = (len(suspects) - baseline) if baseline is not None else None
        report[name] = {
            "count": len(suspects),
            "baseline": baseline,
            "delta_vs_baseline": delta,
            "regression": (delta is not None and delta > 0),
            "first_examples": suspects[:5],
        }
        print(
            f"{name}: {len(suspects)} "
            f"(baseline={baseline}, delta={delta}, regression={report[name]['regression']})",
            file=sys.stderr,
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
