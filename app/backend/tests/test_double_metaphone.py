"""Vendored Double Metaphone reference-table gate (Track 3a).

These expected codes are the BSD `metaphone` 0.6 reference outputs, captured at
design time. The vendored module must reproduce them exactly.
"""

from __future__ import annotations

import pytest

from tm_similarity.double_metaphone import double_metaphone

# word -> (primary, secondary)  — verified against metaphone==0.6
REFERENCE = {
    "THOMAS": ("TMS", ""),
    "TOMAS": ("TMS", ""),
    "CAESAR": ("SSR", ""),
    "SEZAR": ("SSR", ""),
    "JOAQUIN": ("JKN", "AKN"),
    "WAKEEN": ("AKN", "FKN"),
    "MACHARIA": ("MKR", ""),
    "MAKARIA": ("MKR", ""),
    "SCHNEIDER": ("XNTR", "SNTR"),
    "SNYDER": ("SNTR", "XNTR"),
    "SMITH": ("SM0", "XMT"),
    "SCHMIDT": ("XMT", "SMT"),
    "NIKE": ("NK", ""),
    "ADIDAS": ("ATTS", ""),
    "XAVIER": ("SF", "SFR"),
    "KNIGHT": ("NT", ""),
    "WRIGHT": ("RT", ""),
    "PSYCHOLOGY": ("SXLJ", "SKLK"),
    "GIOVANNI": ("JFN", "KFN"),
    "CIABATTA": ("SPT", "XPT"),
    "GEMY": ("JM", "KM"),
    "KAVIN": ("KFN", ""),
    "SAVING": ("SFNK", ""),
    "POWER": ("PR", ""),
    "SULFANI": ("SLFN", ""),
    "VIET": ("FT", ""),
}


@pytest.mark.parametrize("word, expected", REFERENCE.items())
def test_reference_codes(word, expected):
    assert double_metaphone(word) == expected


def test_empty_and_nonalpha():
    assert double_metaphone("") == ("", "")
    assert double_metaphone("   ") == ("", "")
    assert double_metaphone("123") == ("", "")
    assert double_metaphone(None) == ("", "")
