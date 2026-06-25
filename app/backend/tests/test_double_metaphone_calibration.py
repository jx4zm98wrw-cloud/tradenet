"""Committed non-VN (English) aural-confusion calibration set (Track 3a).

Asserts Double Metaphone lifts documented alternate-pronunciation pairs above
single Metaphone, and does NOT over-merge a realistic non-confusable pair.
Values verified at design time (single MP -> DM).
"""

from __future__ import annotations

import pytest

from tm_similarity.phonetic import phonetic_similarity

# (a, b, floor) — alternate-pronunciation pairs DM should flag. Floors sit just
# below the verified DM score; each is strictly above its single-Metaphone value
# (THOMAS/TOMAS 0.898->0.965, CAESAR/SEZAR 0.646->0.712, JOAQUIN/WAKEEN 0.611->0.678).
HIGH_CONFUSION = [
    ("THOMAS", "TOMAS", 0.95),
    ("CAESAR", "SEZAR", 0.70),
    ("JOAQUIN", "WAKEEN", 0.66),
]

# (a, b, ceiling) — realistic non-confusable English pair must stay low.
# NIKE/ADIDAS = 0.275 under both single MP and DM (encoder swap doesn't inflate it).
LOW_CONFUSION = [
    ("NIKE", "ADIDAS", 0.40),
]


@pytest.mark.parametrize("a, b, floor", HIGH_CONFUSION)
def test_high_confusion_pairs_flagged(a, b, floor):
    assert phonetic_similarity(a, b) >= floor


@pytest.mark.parametrize("a, b, ceiling", LOW_CONFUSION)
def test_low_confusion_pairs_not_over_merged(a, b, ceiling):
    assert phonetic_similarity(a, b) < ceiling
