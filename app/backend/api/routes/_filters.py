"""Shared WHERE-clause builder for trademark search + facets.

Both `/api/trademarks` and `/api/facets/*` apply the same set of filters; the
only difference is that a facet endpoint excludes its own column from the
filter set so users can see "if I switched/added this value, how many?" rather
than seeing every alternative grayed out to zero.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from ..db import RecordType, Trademark
from ..db.models import MadridRecord


def vienna_code_match(code: str) -> ColumnElement:
    """Build a WHERE clause matching any trademark whose vienna_codes array
    contains `code` (exact) OR a more-specific child under it (prefix).

    Vienna classification is hierarchical: `5.7` is the "Flowers" parent;
    every actual mark carries 3-level child codes like `5.7.1` (single
    flower) or `5.7.20` (stylized flower). The DB stores only the
    3-level codes. A user who clicks the "05.07 Flowers" quick-pick
    expects ANY flower mark to match, not "marks with literally `5.7`
    in their codes" (none exist).

    Implementation: exact match goes through the GIN index via `&&`;
    prefix match scans a comma-delimited form of the array. The exact
    branch is index-fast and cheap; the prefix branch only fires for
    2-level codes (most user queries) and is bounded by the same row
    set the exact filter would touch.
    """
    exact = Trademark.vienna_codes.op("&&")([code])
    if code.count(".") < 2:
        # Bookend with commas so `,5.7.,` and `,5.7,` boundaries don't
        # accidentally match `15.7.x` or `5.70.x`.
        joined = func.concat(",", func.array_to_string(Trademark.vienna_codes, ","), ",")
        prefix = joined.like(f"%,{code}.%")
        return or_(exact, prefix)
    return exact


def normalize_vienna_code(code: str) -> str | None:
    """Normalize a Vienna code to the stored representation.

    The extractor strips leading zeros, so `01.01.01` becomes `1.1.1` in
    the DB. Frontend / WIPO references frequently zero-pad. Strip leading
    zeros from each dotted segment so `01.01` and `1.1` both find the
    same rows. Returns None if the input doesn't look like a Vienna
    code (lets callers cheaply filter out garbage).
    """
    s = code.strip()
    if not s:
        return None
    parts = s.split(".")
    if not (2 <= len(parts) <= 3):
        return None
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p.isdigit():
            return None
        out.append(str(int(p)))  # strips leading zeros
    return ".".join(out)


def build_trademark_where(
    *,
    q: str | None = None,
    country: str | None = None,
    nice_class: list[str] | None = None,
    vienna_codes: list[str] | None = None,
    record_type: RecordType | None = None,
    mark_category: str | None = None,
    applicant_type: str | None = None,
    applicant: str | None = None,
    year: int | None = None,
    month: int | None = None,
    gazette_id: UUID | None = None,
    ip_agency: str | None = None,
    designated_country: str | None = None,
    vn_status: str | None = None,
    granted: bool | None = None,
    grant_date_from: date | None = None,
    grant_date_to: date | None = None,
    exclude: str | None = None,
) -> list[ColumnElement]:
    """Return a list of SQLAlchemy WHERE expressions for the given filters.

    Pass `exclude="<field>"` to skip one filter — used by facet endpoints so a
    selected value doesn't suppress its own facet's other options.

    `nice_class` and `vienna_codes` use ALL-semantics here (each requested
    value must be present). Callers that want ANY-semantics should pass
    None and apply `Trademark.<column>.op("&&")(values)` themselves —
    array overlap is one expression instead of N.
    """
    where: list[ColumnElement] = []
    if q and exclude != "q":
        like = f"%{q.lower()}%"
        where.append(
            or_(
                func.lower(Trademark.mark_sample).like(like),
                func.lower(Trademark.mark_name).like(like),
                Trademark.application_number.ilike(like),
                Trademark.certificate_number.ilike(like),
                Trademark.madrid_number.ilike(like),
            )
        )
    if country and exclude != "country":
        where.append(Trademark.applicant_country_code == country.upper())
    if nice_class and exclude != "nice_class":
        for nc in nice_class:
            where.append(Trademark.nice_classes.contains([nc]))
    if vienna_codes and exclude != "vienna_codes":
        # Each requested code matches exact OR prefix (parent → child).
        for vc in vienna_codes:
            where.append(vienna_code_match(vc))
    if record_type is not None and exclude != "record_type":
        where.append(Trademark.record_type == record_type)
    # Derived classification (domestic_application | domestic_registration |
    # madrid_registration | madrid_renewal | unknown). Correct-by-construction,
    # so it cleanly separates the 2,605 Madrid registrations that record_type
    # lumps under B_domestic. An unrecognised value simply matches no rows.
    if mark_category and exclude != "mark_category":
        where.append(Trademark.mark_category == mark_category)
    if applicant_type and exclude != "applicant_type":
        where.append(Trademark.applicant_type == applicant_type)
    if applicant and exclude != "applicant":
        # Substring + case-insensitive — applicant names vary widely
        # (e.g. "ZOTT SE & CO. KG" vs "Zott SE", "L'OREAL" vs "L'Oréal").
        # Frontend supplies either a full-name pick from the facet list or
        # a free-text fragment; both go through the same ILIKE.
        where.append(Trademark.applicant_name.ilike(f"%{applicant.lower()}%"))
    if year is not None and exclude != "year":
        where.append(Trademark.year == year)
    if month is not None and exclude != "month":
        where.append(Trademark.month == month)
    if gazette_id is not None and exclude != "gazette_id":
        where.append(Trademark.gazette_id == gazette_id)
    if ip_agency and exclude != "ip_agency":
        where.append(Trademark.ip_agency.ilike(f"%{ip_agency.lower()}%"))
    # Designated-jurisdiction filter: marks whose Madrid record covers country
    # `cc`. Joined via lineage_key against madrid_records.designated_countries
    # (a GIN-indexed Postgres array; `@>` containment hits the index). A
    # non-correlated IN-subquery keeps this a single appendable clause.
    if designated_country and exclude != "designated_country":
        cc = designated_country.upper()
        irns = select(MadridRecord.irn).where(MadridRecord.designated_countries.contains([cc]))
        where.append(Trademark.lineage_key.in_(irns))
    # VN protection-status filter (granted | pending | refused), also via the
    # lineage_key join.
    if vn_status and exclude != "vn_status":
        irns = select(MadridRecord.irn).where(MadridRecord.vn_status == vn_status)
        where.append(Trademark.lineage_key.in_(irns))
    # "Granted" status: any mark with a resolved VN grant date (domestic grant
    # OR Madrid grant), via the denormalized trademarks.vn_grant_date column —
    # a single indexed predicate, no per-query join. Replaces the old Madrid-only
    # vn_status='granted' facet that silently missed ~100k domestic grants.
    if granted and exclude != "granted":
        where.append(Trademark.vn_grant_date.is_not(None))
    # Grant-date range filters by the unified VN grant date
    # (trademarks.vn_grant_date) — the same column the Granted facet uses,
    # covering both domestic and Madrid grants. Marks without a resolved grant
    # date have NULL here, so they're naturally excluded from any range filter.
    if grant_date_from is not None and exclude != "grant_date":
        where.append(Trademark.vn_grant_date >= grant_date_from)
    if grant_date_to is not None and exclude != "grant_date":
        where.append(Trademark.vn_grant_date <= grant_date_to)
    return where
