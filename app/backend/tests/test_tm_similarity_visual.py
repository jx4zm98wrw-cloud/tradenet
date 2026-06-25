"""Track 1: recalibrated pHash curve + specimen-type routing."""

from __future__ import annotations

from itertools import pairwise

import tm_similarity as t
from tm_similarity.visual import VISUAL_PHASH_THRESHOLD, _phash_score, visual_similarity


def test_phash_score_identical_is_one():
    assert _phash_score(0) == 1.0


def test_phash_score_at_threshold_is_zero():
    assert _phash_score(VISUAL_PHASH_THRESHOLD) == 0.0


def test_phash_score_unrelated_baseline_is_zero():
    # ~half the bits differ → unrelated → must floor at 0, not 0.50
    assert _phash_score(32) == 0.0


def test_phash_score_is_monotonic_non_increasing():
    vals = [_phash_score(hd) for hd in range(0, 65)]
    assert all(b <= a for a, b in pairwise(vals))


def test_phash_score_threshold_is_ten():
    assert VISUAL_PHASH_THRESHOLD == 10


def test_both_figurative_uses_phash():
    vs = visual_similarity("ffffffffffffffff", "ffffffffffffffff", "figurative", "figurative", None, None)
    assert vs.confidence == "phash" and vs.score == 1.0


def test_wordmark_side_routes_to_typographic():
    vs = visual_similarity("ffffffffffffffff", "0000000000000000", "wordmark", "figurative", "ACME", "ACMI")
    assert vs.confidence == "typographic"


def test_missing_phash_routes_to_typographic():
    vs = visual_similarity(None, "ffffffffffffffff", "figurative", "figurative", "ACME", "ACMI")
    assert vs.confidence == "typographic"


def test_unclassified_none_is_permissive_uses_phash():
    # NULL kind (pre-backfill) must NOT go dark — behaves like today (phash).
    vs = visual_similarity("ffffffffffffffff", "fffffffffffffffe", None, None, None, None)
    assert vs.confidence == "phash"


def test_no_text_no_phash_is_none():
    vs = visual_similarity(None, None, "wordmark", "wordmark", "", "")
    assert vs.confidence == "none" and vs.score == 0.0


def test_regression_unrelated_phash_pair_is_low_risk():
    # The reported /compare 63/59 bug: unrelated figurative logos (hd~32) used to
    # score ~0.59 visual and slip past the gate. Now visual≈0 → Low risk.
    a = t.MarkFeatures(
        mark_text=None,
        logo_phash="ffffffffffffffff",
        logo_kind="figurative",
        nice_classes=["3"],
        vienna_codes=["1.1"],
    )
    b = t.MarkFeatures(
        mark_text=None,
        logo_phash="00000000ffffffff",
        logo_kind="figurative",
        nice_classes=["3"],
        vienna_codes=["2.2"],
    )
    r = t.score(a, b)
    assert r.visual == 0.0
    assert r.verdict == "Low risk"
