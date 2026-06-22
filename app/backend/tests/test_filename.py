"""Tests for NOIP gazette filename parsing (api._filename)."""

from __future__ import annotations

import pytest

from api._filename import parse_filename_meta
from api.db.models import GazetteType


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        # Standard NOIP names.
        ("A_T3_2026.pdf", (GazetteType.A, 3, 2026)),
        ("B_T2_2026.pdf", (GazetteType.B, 2, 2026)),
        ("B_T5_2026.pdf", (GazetteType.B, 5, 2026)),
        ("A_T12_2025.pdf", (GazetteType.A, 12, 2025)),
        # Case-insensitive type letter.
        ("a_T3_2026.pdf", (GazetteType.A, 3, 2026)),
        ("b_T2_2026.pdf", (GazetteType.B, 2, 2026)),
        # Split-part halves of an oversized issue — both resolve to the base
        # issue/year (the `_<part>` segment is metadata-neutral).
        ("A_T6_1_2026.pdf", (GazetteType.A, 6, 2026)),
        ("A_T6_2_2026.pdf", (GazetteType.A, 6, 2026)),
        ("B_T6_1_2026.pdf", (GazetteType.B, 6, 2026)),
        ("B_T6_2_2026.pdf", (GazetteType.B, 6, 2026)),
        # A 3-way split still works.
        ("A_T6_3_2026.pdf", (GazetteType.A, 6, 2026)),
    ],
)
def test_parse_filename_meta(filename: str, expected: tuple) -> None:
    assert parse_filename_meta(filename) == expected


def test_split_parts_share_issue_and_year() -> None:
    """Every part of a split issue maps to the same (type, issue, year)."""
    a = parse_filename_meta("A_T6_1_2026.pdf")
    b = parse_filename_meta("A_T6_2_2026.pdf")
    assert a == b == (GazetteType.A, 6, 2026)


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("", GazetteType.A),  # empty -> sensible default, no crash
        ("garbage.pdf", GazetteType.A),
        ("B_random.pdf", GazetteType.B),  # type inferred, issue/year unknown
    ],
)
def test_unrecognised_falls_back_to_type_only(filename: str, expected_type: GazetteType) -> None:
    gtype, num, year = parse_filename_meta(filename)
    assert gtype is expected_type
    assert num is None
    assert year is None
