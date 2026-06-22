"""Unit tests for the entity grouping-key helpers (Phase 1)."""

from __future__ import annotations

import unicodedata

from api._entity_norm import (
    ENTITY_CLEAN_VERSION,
    norm,
    resolve_applicant,
    resolve_representative,
    strip_madrid_rep_address,
)


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


def test_entity_clean_version_is_a_positive_int():
    assert isinstance(ENTITY_CLEAN_VERSION, int)
    assert ENTITY_CLEAN_VERSION >= 1


def test_resolve_applicant_precedence_noip_over_wipo_over_gazette():
    # NOIP (domestic) wins outright.
    assert resolve_applicant("NOIP Co", "WIPO Co", "Gazette Co")[0] == "NOIP Co"
    # WIPO wins when no NOIP.
    assert resolve_applicant(None, "WIPO Co", "Gazette Co")[0] == "WIPO Co"
    # Gazette is the last-resort fallback.
    assert resolve_applicant(None, None, "Gazette Co")[0] == "Gazette Co"
    # Nothing at all → (None, None).
    assert resolve_applicant(None, None, None) == (None, None)


def test_resolve_applicant_blank_strings_are_skipped():
    # Empty / whitespace-only trusted values fall through to the next source.
    assert resolve_applicant("", "WIPO Co", None)[0] == "WIPO Co"
    assert resolve_applicant("   ", None, "Gazette Co")[0] == "Gazette Co"
    assert resolve_applicant("  ", "", "  ") == (None, None)


def test_resolve_applicant_returns_clean_and_norm():
    from api._entity_norm import norm

    clean, key = resolve_applicant("  Công ty TAGA  ", None, None)
    assert clean == "Công ty TAGA"  # trimmed, spelling preserved
    assert key == norm("Công ty TAGA")


def test_resolve_applicant_variants_collapse_to_one_norm():
    _, a = resolve_applicant("Công ty Luật TAGA", None, None)
    _, b = resolve_applicant("CÔNG TY LUẬT TAGA", None, None)
    _, c = resolve_applicant("Công  ty   Luật   TAGA", None, None)
    assert a == b == c
    _, distinct = resolve_applicant("Distinct Firm XYZ", None, None)
    assert distinct != a


def test_resolve_representative_strips_madrid_glued_address_only_for_wipo():
    # WIPO representative carries a glued trailing address — stripped before norm.
    clean, _ = resolve_representative(None, "OVW REP ALPHA 123 Main St, Zürich", None)
    assert clean == "OVW REP ALPHA"
    # NOIP representative is taken verbatim (no address strip applied).
    clean, _ = resolve_representative("Công ty Luật TAGA 12 Pho X", None, None)
    assert clean == "Công ty Luật TAGA 12 Pho X"


def test_resolve_representative_precedence():
    assert resolve_representative("NOIP Rep", "WIPO Rep 1 St", "Gaz Rep")[0] == "NOIP Rep"
    assert resolve_representative(None, "WIPO Rep 1 St", "Gaz Rep")[0] == "WIPO Rep"
    assert resolve_representative(None, None, "Gaz Rep")[0] == "Gaz Rep"
    assert resolve_representative(None, None, None) == (None, None)
