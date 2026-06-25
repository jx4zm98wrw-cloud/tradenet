"""Committed VN aural-confusion calibration set (Track 2 regression guard).

Asserts the engine now scores documented VN sound-alikes as intended and does
NOT over-merge a segmentally-distinct VN pair. Values verified at design time.
"""

from __future__ import annotations

import pytest

from tm_similarity.phonetic import phonetic_similarity

# (a, b, min_expected) — should be FLAGGED as phonetically confusable.
HIGH_CONFUSION = [
    ("GIA HƯNG", "DA HƯNG", 0.60),  # Northern d/gi -> /z/  (was 0.50 under Metaphone)
    ("TRANG", "CHANG", 0.78),  # ch/tr -> /tɕ/         (was 0.73)
    ("LAKA", "LACCA", 0.80),  # IP-Vietnam short-mark case
    ("MEKO", "MECO", 0.85),  # IP-Vietnam short-mark case
]

# (a, b, max_expected) — must NOT over-merge (toneless over-merge early-warning).
LOW_CONFUSION = [
    ("BAO LONG", "MINH QUAN", 0.50),
]


@pytest.mark.parametrize("a, b, floor", HIGH_CONFUSION)
def test_high_confusion_pairs_flagged(a, b, floor):
    assert phonetic_similarity(a, b) >= floor


@pytest.mark.parametrize("a, b, ceiling", LOW_CONFUSION)
def test_low_confusion_pairs_not_over_merged(a, b, ceiling):
    assert phonetic_similarity(a, b) < ceiling
