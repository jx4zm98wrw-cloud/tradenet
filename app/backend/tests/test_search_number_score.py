"""_score must treat an exact registration-number query as a strong match.

Regression: build_trademark_where matches q against application/certificate/
madrid number, so a number query found the row (total=1) — but _score only
looked at the mark name, scored ~0.6, and the 0.65 threshold filtered it out,
producing "1 trademarks match" + "No matches" in the UI.
"""

from __future__ import annotations

from api.db.models import Trademark
from api.routes.search import _score


def _mark(**kw) -> Trademark:
    return Trademark(**kw)


def test_exact_madrid_number_scores_high():
    m = _mark(madrid_number="9999999", mark_sample=None, applicant_name="ACME")
    assert _score(m, "9999999", "text") >= 0.95  # passes any sane threshold


def test_exact_certificate_and_application_number_score_high():
    assert _score(_mark(certificate_number="VN-12345", applicant_name="X"), "vn-12345", "text") >= 0.95
    assert _score(_mark(application_number="4-2099-001", applicant_name="X"), "4-2099-001", "text") >= 0.95


def test_number_substring_still_strong():
    m = _mark(madrid_number="1279464", mark_sample="TOYOTA", applicant_name="TOYOTA")
    assert _score(m, "127946", "text") >= 0.9  # substring of the IRN


def test_non_matching_number_stays_low():
    m = _mark(madrid_number="1111111", mark_sample="TOYOTA", applicant_name="TOYOTA")
    assert _score(m, "9999999", "text") < 0.65  # no ID/name overlap → below threshold


def test_name_matching_unaffected():
    m = _mark(madrid_number="1279464", mark_sample="TOYOTA", applicant_name="TOYOTA")
    assert _score(m, "toyota", "text") >= 0.95  # exact wordmark still high
