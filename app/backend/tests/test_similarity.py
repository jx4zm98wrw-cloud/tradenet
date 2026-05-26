"""Unit tests for the similarity engine.

Each test pair carries an explicit trademark-professional rationale —
the assertions match how an examiner or IP attorney would score the
relationship, not just what the math happens to produce.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.similarity import (
    DEFAULT_WEIGHTS,
    class_overlap,
    composite_score,
    normalize_vn,
    phonetic_similarity,
    vienna_overlap,
    visual_similarity,
)

# ---------------------------------------------------------------------------
# Vietnamese normalisation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CÔNG TY", "CONG TY"),  # diacritic strip
        ("công ty", "CONG TY"),  # case fold
        ("  Bạc   Hồng  ", "BAC HONG"),  # whitespace collapse + diacritics
        ("ZOTT SE & CO. KG", "ZOTT SE & CO. KG"),  # ASCII passes through
        ("", ""),
        (None, ""),
        ("Đặng Văn Hùng", "DANG VAN HUNG"),  # Đ is special — NFD splits it
    ],
)
def test_normalize_vn(raw: str | None, expected: str) -> None:
    assert normalize_vn(raw) == expected


# ---------------------------------------------------------------------------
# Phonetic similarity — paired with trademark-examiner intuition


def test_phonetic_identical_marks() -> None:
    assert phonetic_similarity("MONTINIS", "MONTINIS") == pytest.approx(1.0)


def test_phonetic_spelling_variant_should_match_high() -> None:
    """MONTINIS vs MONTANIS — one-letter substitution, identical Metaphone
    code (MNTNS). An examiner would absolutely flag this as confusable."""
    s = phonetic_similarity("MONTINIS", "MONTANIS")
    assert s >= 0.90, f"expected >=0.90, got {s}"


def test_phonetic_distinct_marks_should_score_low() -> None:
    """The screenshot bug case: MONTINIS vs MF11RCE — visually distinct,
    Metaphone codes diverge (MNTNS vs MFRS), shared first letter only.
    Should be clearly below the 'Possible conflict' threshold."""
    s = phonetic_similarity("MONTINIS", "MF11RCE")
    assert s < 0.50, f"expected <0.50 (not a conflict candidate), got {s}"


def test_phonetic_no_common_prefix_should_score_very_low() -> None:
    """MONTINIS vs SPRINGFERM — different first letter, different Metaphone.
    JW penalises non-matching prefixes; this should be clearly below the
    'Possible conflict' minimum-signal threshold (0.5)."""
    s = phonetic_similarity("MONTINIS", "SPRINGFERM")
    assert s < 0.50, f"expected <0.50 (cannot trigger conflict band), got {s}"


def test_phonetic_sound_alike_with_different_spelling() -> None:
    """NEUREX vs NEUROFAX — different visually, but both encode through
    Metaphone to NRKS / NRFKS (sound-alike). This is the Metaphone path's
    reason for existing — the raw-string JW alone would score this lower
    than the underlying phonetic similarity warrants."""
    s = phonetic_similarity("NEUREX", "NEUROFAX")
    assert s >= 0.75, f"expected >=0.75 (sound-alike), got {s}"


def test_phonetic_vietnamese_diacritic_normalisation() -> None:
    """A Vietnamese examiner reading 'Bạc' and 'BAC' would treat them as
    the same mark for phonetic purposes — diacritics affect tone (Vietnamese
    speakers distinguish 'bạc' from 'bác') but the romanised form drops
    them, and the gazette can carry either form."""
    assert phonetic_similarity("Bạc", "BAC") >= 0.95
    assert phonetic_similarity("Việt Đức", "Viet Duc") >= 0.95


def test_phonetic_empty_inputs_safe() -> None:
    assert phonetic_similarity("", "MONTINIS") == 0.0
    assert phonetic_similarity(None, "MONTINIS") == 0.0
    assert phonetic_similarity(None, None) == 0.0


# ---------------------------------------------------------------------------
# Class overlap (already real, keep covered)


def test_class_overlap_identical() -> None:
    assert class_overlap(["05", "10"], ["05", "10"]) == 1.0


def test_class_overlap_partial() -> None:
    # Anchor has 2 classes, other has 1 in common, 1 different. Union=3, inter=1.
    assert class_overlap(["05", "10"], ["05", "12"]) == pytest.approx(1 / 3)


def test_class_overlap_disjoint() -> None:
    assert class_overlap(["05"], ["41"]) == 0.0


def test_class_overlap_empty_sides_return_zero() -> None:
    assert class_overlap(None, ["05"]) == 0.0
    assert class_overlap([], ["05"]) == 0.0


# ---------------------------------------------------------------------------
# Vienna overlap


def test_vienna_overlap_shared_codes_score_high() -> None:
    """Two marks both classified as 26.1.1 (Circles) — examiners
    consider them visually pre-related at the categorical level."""
    s = vienna_overlap(["26.1.1", "5.7.1"], ["26.1.1", "27.5.1"])
    assert s == pytest.approx(1 / 3)  # one shared out of three unique codes


def test_vienna_overlap_no_codes_returns_zero() -> None:
    """Marks without figurative elements have no Vienna codes — the
    signal correctly reports 'no visual category in common'."""
    assert vienna_overlap(None, ["26.1.1"]) == 0.0
    assert vienna_overlap([], []) == 0.0


# ---------------------------------------------------------------------------
# Visual similarity (no real images in test corpus → typographic fallback)


def test_visual_falls_back_to_typographic_when_no_logos(tmp_path: Path) -> None:
    """Neither mark has a logo file. Engine returns the typographic JW
    score on the wordmark text, with confidence='typographic' so the UI
    can warn the user that this isn't a real visual match."""
    vs = visual_similarity(
        a_logo=None,
        b_logo=None,
        a_text="MONTINIS",
        b_text="MONTANIS",
        image_root=tmp_path,
    )
    assert vs.confidence == "typographic"
    assert vs.score >= 0.85  # similar text


def test_visual_returns_none_signal_for_blank_marks(tmp_path: Path) -> None:
    vs = visual_similarity(None, None, "", "", image_root=tmp_path)
    assert vs.confidence == "none"
    assert vs.score == 0.0


def test_visual_missing_logo_file_falls_to_typographic(tmp_path: Path) -> None:
    """logo_path points at a file that doesn't exist on disk (e.g. extractor
    crashed for that gazette but DB row exists). Don't raise; fall back."""
    vs = visual_similarity(
        a_logo="missing/4-2026-99999.png",
        b_logo=None,
        a_text="ALPHA",
        b_text="ALPHA",
        image_root=tmp_path,
    )
    assert vs.confidence == "typographic"


# ---------------------------------------------------------------------------
# Composite + verdict — the user-visible output


def test_composite_likely_conflict_threshold() -> None:
    """All four signals strong → 'Likely conflict' (examiner would cite
    this in an office action)."""
    c = composite_score(phonetic=1.0, visual=0.8, class_o=1.0, vienna_o=0.5)
    assert c.composite >= 0.70
    assert c.verdict == "Likely conflict"
    assert c.verdict_tone == "stamp"


def test_composite_possible_conflict_threshold() -> None:
    """Moderate phonetic + good class overlap = warrants attorney review."""
    c = composite_score(phonetic=0.7, visual=0.4, class_o=0.5, vienna_o=0.2)
    # 0.4*0.7 + 0.25*0.4 + 0.2*0.5 + 0.15*0.2 = 0.28+0.10+0.10+0.03 = 0.51
    assert 0.50 <= c.composite < 0.70
    assert c.verdict == "Possible conflict"


def test_composite_low_risk() -> None:
    """The screenshot bug case as a composite: low phonetic + low visual
    + full class overlap. Class alone is necessary-not-sufficient."""
    c = composite_score(phonetic=0.2, visual=0.3, class_o=1.0, vienna_o=0.0)
    # 0.4*0.2 + 0.25*0.3 + 0.2*1.0 + 0.15*0 = 0.08+0.075+0.20+0 = 0.355
    assert c.composite < 0.50
    assert c.verdict == "Low risk"
    assert c.verdict_tone == "ok"


def test_composite_low_risk_when_only_class_overlaps() -> None:
    """The actual screenshot bug case: MONTINIS-style phonetic/visual
    against MF11RCE-style mark. Phonetic and visual both below the
    minimum strength threshold (0.5). Class overlap = 100%, but that
    alone doesn't make a conflict — an examiner would dismiss this
    pair even with full class overlap.

    Composite arithmetic alone gives 0.50 (right at the boundary), but
    the max(phon, visual) guard says: insufficient name/visual signal,
    'Low risk' regardless."""
    c = composite_score(phonetic=0.486, visual=0.423, class_o=1.0, vienna_o=0.0)
    # composite = 0.4*0.486 + 0.25*0.423 + 0.2*1.0 + 0 = 0.500
    # max_sig = 0.486 < 0.5 → conjunction guard kicks in → Low risk
    assert c.verdict == "Low risk", (
        f"max signal {max(0.486, 0.423)} < 0.5 should force Low risk, "
        f"even with composite={c.composite}"
    )


def test_composite_conjunction_guard_class_too_low() -> None:
    """Strong name similarity but unrelated goods (class_o = 0) → not a
    conflict. Identical names in unrelated industries (APPLE Records vs
    APPLE Computer in 1976) don't legally confuse consumers."""
    c = composite_score(phonetic=0.95, visual=0.90, class_o=0.0, vienna_o=0.0)
    # composite = 0.4*0.95 + 0.25*0.90 + 0 + 0 = 0.605 — above 0.50 band
    # but class guard (>= 0.20) fails → Low risk
    assert c.verdict == "Low risk"


def test_composite_weights_sum_to_one() -> None:
    """Sanity: default weights cover the full signal space, no silent
    drop or double-count."""
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_composite_per_matter_weights_override() -> None:
    """Per-matter tuning works — the README's 'tunable per matter'
    requirement. Pharma matters often want phonetic weighted at 70%
    because pharmacy product naming heavily relies on phonetic
    distinctiveness ('Lipitor' vs 'Lipator').

    With a strong phonetic match AND minimum class overlap (a real
    pharma case would have both — sound-alikes are most dangerous when
    they're in the same pharmacy class), per-matter weights push the
    composite higher than the default weights would."""
    pharma = {"phonetic": 0.70, "visual": 0.10, "class": 0.15, "vienna": 0.05}
    c = composite_score(phonetic=1.0, visual=0.0, class_o=1.0, vienna_o=0.0, weights=pharma)
    # composite = 0.70*1.0 + 0.10*0 + 0.15*1.0 + 0 = 0.85
    assert c.composite == pytest.approx(0.85)
    assert c.verdict == "Likely conflict"


def test_per_matter_weights_cannot_override_conjunction_guards() -> None:
    """Even custom weights can't manufacture a conflict when there's no
    actual signal — an examiner won't accept 'we weight phonetic at 100%'
    when the marks don't sound alike and aren't in related classes."""
    sketchy = {"phonetic": 1.0, "visual": 0.0, "class": 0.0, "vienna": 0.0}
    c = composite_score(phonetic=0.3, visual=0.0, class_o=0.0, vienna_o=0.0, weights=sketchy)
    # composite = 0.30 — below all bands; conjunction guards moot
    assert c.verdict == "Low risk"
