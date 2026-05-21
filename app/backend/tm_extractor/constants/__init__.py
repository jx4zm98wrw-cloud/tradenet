"""Static constants for the trademark extractor.

Split across submodules to keep individual files small and reviewable:
- markers.py        — WIPO INID markers, regex patterns, CSV column order
- countries.py      — ISO 3166-1 alpha-2 country code → name
- classifier.py     — VN surnames + company-suffix rules for applicant classification
"""

from .classifier import (
    STRONG_COMPANY_SUFFIXES,
    TYPO_TOLERANT_COMPANY_PATTERNS,
    VN_SURNAMES,
    VN_SURNAMES_UPPER,
)
from .countries import COUNTRY_CODES
from .markers import CSV_COLUMNS, MARKER_CODES, MARKER_DESCRIPTIONS, MARKERS, PATTERNS, MarkerConfig


class TrademarkConstants:
    """Namespace for the static constants. Mirrors the original monolithic class so
    callers can still do `TrademarkConstants.MARKERS` etc. Data-dependent fields
    (`CITIES_BY_COUNTRY`, `CITY_PATTERNS`, `COMPANY_SUFFIXES`) now live on the
    PDFProcessor instance — they need a config to know where to read from.
    """

    MARKERS = MARKERS
    MARKER_CODES = MARKER_CODES
    MARKER_DESCRIPTIONS = MARKER_DESCRIPTIONS
    PATTERNS = PATTERNS
    CSV_COLUMNS = CSV_COLUMNS
    COUNTRY_CODES = COUNTRY_CODES
    VN_SURNAMES = VN_SURNAMES
    VN_SURNAMES_UPPER = VN_SURNAMES_UPPER
    STRONG_COMPANY_SUFFIXES = STRONG_COMPANY_SUFFIXES
    TYPO_TOLERANT_COMPANY_PATTERNS = TYPO_TOLERANT_COMPANY_PATTERNS
