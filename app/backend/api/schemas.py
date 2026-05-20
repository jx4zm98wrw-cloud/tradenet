"""Pydantic schemas for API request/response payloads."""
from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GazetteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    sha256: str
    gazette_type: str
    issue_year: Optional[int]
    issue_number: Optional[int]
    status: str
    row_count: int
    error_message: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]
    size_bytes: int
    # Mocked OCR metrics until the OCR pipeline lands. Stable per gazette via
    # hash of the sha256 — same gazette always reports the same confidence.
    ocr_confidence: Optional[float] = None
    flagged_row_count: Optional[int] = None
    needs_review: bool = False


class GazetteListOut(BaseModel):
    items: List[GazetteOut]
    total: int


class TrademarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gazette_id: UUID
    record_type: str
    application_number: Optional[str]
    certificate_number: Optional[str]
    madrid_number: Optional[str]
    publication_date_441: Optional[date]
    publication_date_450: Optional[date]
    registration_date_151: Optional[date]
    nice_classes: Optional[List[str]]
    nice_total: Optional[int]
    mark_sample: Optional[str]
    applicant_name: Optional[str]
    applicant_country_code: Optional[str]
    applicant_city: Optional[str]
    applicant_type: Optional[str]
    ip_agency: Optional[str]
    year: Optional[int]
    month: Optional[int]


class TrademarkListOut(BaseModel):
    items: List[TrademarkOut]
    total: int
    limit: int
    offset: int
