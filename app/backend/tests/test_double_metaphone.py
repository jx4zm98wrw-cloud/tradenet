"""Vendored Double Metaphone reference-table gate (Track 3a).

These expected codes are the BSD `metaphone` 0.6 reference outputs, captured at
design time. The vendored module must reproduce them exactly.
"""

from __future__ import annotations

import pytest

import tm_similarity as t
from tm_similarity.double_metaphone import double_metaphone
from tm_similarity.phonetic import phonetic_similarity

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


def test_non_vn_pair_uses_double_metaphone():
    # THOMAS/TOMAS: single Metaphone gave 0.898; DM primary handles TH->T -> 0.965.
    assert phonetic_similarity("THOMAS", "TOMAS") >= 0.95
    # JOAQUIN/WAKEEN: the secondary code AKN matches across sets (0.611 -> 0.678).
    assert phonetic_similarity("JOAQUIN", "WAKEEN") >= 0.66


def test_vn_pair_unchanged_by_track3a():
    # VN pair still routes to the Track-2 VN key — identical to its 1.2 value.
    assert phonetic_similarity("TRANG", "CHANG") == 0.813


def test_version_and_export():
    assert t.SIMILARITY_VERSION == "1.3"
    assert t.double_metaphone("THOMAS") == ("TMS", "")
