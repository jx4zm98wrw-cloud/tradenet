"""Unit tests for parse_applicant_field — name/address split at first valid ISO code.

The original implementation split at the first parenthesized 2-letter token, which
catches non-country abbreviations like (GZ) Guangzhou, truncating the company name
and leaking it into the address. The fix scans for the first VALID ISO 3166-1
alpha-2 country code instead.
"""

from __future__ import annotations

from tm_extractor.applicant import parse_applicant_field


def test_skips_non_iso_city_abbrev_before_real_country_code():
    """Regression: (GZ) is Guangzhou, not an ISO code. The real code is (CN)."""
    names, addresses = parse_applicant_field(
        "MEISHANG (GZ) COSMETICS CO., LTD. (CN) 123 Some St, Guangzhou"
    )
    assert names == ["MEISHANG (GZ) COSMETICS CO., LTD."]
    assert addresses == ["123 Some St, Guangzhou"]


def test_simple_name_country_address():
    names, addresses = parse_applicant_field("ACME LTD (US) 123 Main St, Anywhere")
    assert names == ["ACME LTD"]
    assert addresses == ["123 Main St, Anywhere"]


def test_multi_applicant_numbered_keeps_first_only():
    """1. ... 2. ... pattern: drop the second applicant entirely."""
    names, addresses = parse_applicant_field(
        "1. ACME LTD (US) 123 Main St 2. BETA INC (CN) 456 Oak Rd"
    )
    assert names == ["ACME LTD"]
    assert addresses == ["123 Main St"]


def test_no_country_code_falls_back_to_comma_split():
    names, addresses = parse_applicant_field("NGUYEN VAN A, 5 Some Street, Hanoi")
    assert names == ["NGUYEN VAN A"]
    assert addresses[0].startswith("5 Some Street")


def test_empty_input():
    names, addresses = parse_applicant_field("")
    assert names == []
    assert addresses == []
