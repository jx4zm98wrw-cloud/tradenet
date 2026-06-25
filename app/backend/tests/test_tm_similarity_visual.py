"""Track 1: recalibrated pHash curve + specimen-type routing."""

from __future__ import annotations

from tm_similarity.visual import VISUAL_PHASH_THRESHOLD, _phash_score


def test_phash_score_identical_is_one():
    assert _phash_score(0) == 1.0


def test_phash_score_at_threshold_is_zero():
    assert _phash_score(VISUAL_PHASH_THRESHOLD) == 0.0


def test_phash_score_unrelated_baseline_is_zero():
    # ~half the bits differ → unrelated → must floor at 0, not 0.50
    assert _phash_score(32) == 0.0


def test_phash_score_is_monotonic_non_increasing():
    vals = [_phash_score(hd) for hd in range(0, 65)]
    assert all(b <= a for a, b in zip(vals, vals[1:]))


def test_phash_score_threshold_is_ten():
    assert VISUAL_PHASH_THRESHOLD == 10
