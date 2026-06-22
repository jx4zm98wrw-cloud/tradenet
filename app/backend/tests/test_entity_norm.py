"""Unit tests for the entity grouping-key helpers (Phase 1)."""

from __future__ import annotations

import unicodedata

from api._entity_norm import norm, strip_madrid_rep_address


def test_norm_collapses_case() -> None:
    assert norm("CÔNG TY LUẬT TAGA") == norm("Công ty Luật TAGA")


def test_norm_collapses_internal_whitespace() -> None:
    assert norm("Công  ty   Luật\tTAGA") == norm("Công ty Luật TAGA")


def test_norm_trims_outer_whitespace() -> None:
    assert norm("   ACME Co.  ") == "acme co."


def test_norm_nfc_normalizes_diacritics() -> None:
    # Same name as NFC (precomposed) vs NFD (decomposed base + combining accent).
    base = "L'Oréal"
    nfc = unicodedata.normalize("NFC", base)
    nfd = unicodedata.normalize("NFD", base)
    assert nfc != nfd  # different byte sequences...
    assert norm(nfc) == norm(nfd)  # ...but the same grouping key


def test_norm_keeps_distinct_names_distinct() -> None:
    # Trivial-variant collapse must NEVER merge two genuinely different firms.
    assert norm("Distinct Firm XYZ") != norm("Distinct Firm ABC")
    assert norm("Pham & Associates") != norm("Pham Associates")


def test_strip_madrid_rep_cuts_at_first_digit() -> None:
    # WIPO glues the firm name to its postal address; cut at the first digit run.
    assert strip_madrid_rep_address("OVW REP ALPHA 123 Main St, Zürich").strip() == "OVW REP ALPHA"


def test_strip_madrid_rep_cuts_at_first_comma() -> None:
    assert strip_madrid_rep_address("Smith & Partners, 5 High Road").strip() == "Smith & Partners"


def test_strip_madrid_rep_no_address_unchanged() -> None:
    assert strip_madrid_rep_address("Plain Firm Name").strip() == "Plain Firm Name"


def test_madrid_rep_address_variants_group_together() -> None:
    a = norm(strip_madrid_rep_address("OVW REP ALPHA 123 Main St, Zürich"))
    b = norm(strip_madrid_rep_address("OVW REP ALPHA 456 Other Rd, Bern"))
    assert a == b
