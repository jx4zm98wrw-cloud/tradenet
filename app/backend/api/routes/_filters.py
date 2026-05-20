"""Shared WHERE-clause builder for trademark search + facets.

Both `/api/trademarks` and `/api/facets/*` apply the same set of filters; the
only difference is that a facet endpoint excludes its own column from the
filter set so users can see "if I switched/added this value, how many?" rather
than seeing every alternative grayed out to zero.
"""
from __future__ import annotations
from typing import List, Optional
from uuid import UUID

from sqlalchemy import or_, func
from sqlalchemy.sql.elements import ColumnElement

from ..db import RecordType, Trademark


def build_trademark_where(
    *,
    q: Optional[str] = None,
    country: Optional[str] = None,
    nice_class: Optional[List[str]] = None,
    record_type: Optional[RecordType] = None,
    applicant_type: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    gazette_id: Optional[UUID] = None,
    ip_agency: Optional[str] = None,
    exclude: Optional[str] = None,
) -> List[ColumnElement]:
    """Return a list of SQLAlchemy WHERE expressions for the given filters.

    Pass `exclude="<field>"` to skip one filter — used by facet endpoints so a
    selected value doesn't suppress its own facet's other options.
    """
    where: List[ColumnElement] = []
    if q and exclude != "q":
        like = f"%{q.lower()}%"
        where.append(
            or_(
                func.lower(Trademark.applicant_name).like(like),
                func.lower(Trademark.mark_sample).like(like),
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
    if record_type is not None and exclude != "record_type":
        where.append(Trademark.record_type == record_type)
    if applicant_type and exclude != "applicant_type":
        where.append(Trademark.applicant_type == applicant_type)
    if year is not None and exclude != "year":
        where.append(Trademark.year == year)
    if month is not None and exclude != "month":
        where.append(Trademark.month == month)
    if gazette_id is not None and exclude != "gazette_id":
        where.append(Trademark.gazette_id == gazette_id)
    if ip_agency and exclude != "ip_agency":
        where.append(Trademark.ip_agency.ilike(f"%{ip_agency.lower()}%"))
    return where
