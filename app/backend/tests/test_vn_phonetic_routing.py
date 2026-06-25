"""phonetic_similarity routes VN pairs through the VN key, others through Metaphone."""

from __future__ import annotations

import tm_similarity as t
from tm_similarity.phonetic import phonetic_similarity


def test_vn_pair_routes_to_vn_key_and_beats_metaphone():
    # GIA HƯNG / DA HƯNG: Metaphone scored 0.50 (GIA->"J", DA->"T"); the VN
    # key merges d/gi -> /z/, lifting the phonetic axis to ~0.65.
    assert phonetic_similarity("GIA HƯNG", "DA HƯNG") >= 0.60
    # TRANG / CHANG: Metaphone 0.73 -> VN key ~0.81.
    assert phonetic_similarity("TRANG", "CHANG") >= 0.78


def test_vn_pair_does_not_over_merge():
    # Segmentally-distinct VN pair must stay low — the toneless over-merge
    # early-warning the research called for.
    assert phonetic_similarity("BAO LONG", "MINH QUAN") < 0.50


def test_foreign_pair_unchanged_metaphone_path():
    # Neither mark is VN -> Metaphone path, identical to pre-Track-2 value.
    # 0.851 = undampened blend ~0.907 * length_factor 0.9375 (6 vs 8 chars);
    # exact equality proves the non-VN branch is byte-for-byte the old path.
    assert phonetic_similarity("NEUREX", "NEUROFAX") == 0.851


def test_version_bumped():
    assert t.SIMILARITY_VERSION == "1.2"


def test_new_symbols_exported():
    assert t.is_vietnamese("TRANG") is True
    assert t.vn_phonetic_key("GIA") == t.vn_phonetic_key("DA")
