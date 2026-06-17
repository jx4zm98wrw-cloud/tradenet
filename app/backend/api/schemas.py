"""Pydantic schemas for API request/response payloads."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GazetteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    sha256: str
    gazette_type: str
    issue_year: int | None
    issue_number: int | None
    status: str
    row_count: int
    error_message: str | None
    uploaded_at: datetime
    processed_at: datetime | None
    size_bytes: int
    # Mocked OCR metrics until the OCR pipeline lands. Stable per gazette via
    # hash of the sha256 — same gazette always reports the same confidence.
    ocr_confidence: float | None = None
    flagged_row_count: int | None = None
    needs_review: bool = False


class GazetteListOut(BaseModel):
    items: list[GazetteOut]
    total: int


class TrademarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gazette_id: UUID
    record_type: str
    # Derived (generated) classification + lifecycle identity. mark_category is
    # one of: domestic_application | domestic_registration | madrid_registration
    # | madrid_renewal | unknown. lineage_key links a mark's rows across gazette
    # years (domestic by 210, Madrid by WIPO IRN).
    mark_category: str | None = None
    lineage_key: str | None = None
    application_number: str | None
    certificate_number: str | None
    madrid_number: str | None
    publication_date_441: date | None
    publication_date_450: date | None
    registration_date_151: date | None
    nice_classes: list[str] | None
    nice_total: int | None
    vienna_codes: list[str] | None = None
    mark_sample: str | None
    # Relative path to the extracted logo PNG (under /static/). NULL when no
    # logo was extracted for this row — frontend should fall back to mark_sample.
    logo_path: str | None = None
    applicant_name: str | None
    applicant_country_code: str | None
    applicant_city: str | None
    applicant_type: str | None
    ip_agency: str | None
    year: int | None
    month: int | None
    # Optional claim fields surfaced on the detail hero — only populated for
    # rows where the gazette explicitly carried them. Empty for everything else,
    # so the UI hides the corresponding claim rows.
    mark_status: str | None = None
    protected_colors: str | None = None
    validity_171: str | None = None
    validity_176: str | None = None
    submission_date: date | None = None
    expiry_date_141: date | None = None
    expiry_date_181: date | None = None


class TrademarkListOut(BaseModel):
    items: list[TrademarkOut]
    total: int
    limit: int
    offset: int
