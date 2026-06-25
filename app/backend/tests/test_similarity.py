"""Unit tests for the similarity engine.

Each test pair carries an explicit trademark-professional rationale —
the assertions match how an examiner or IP attorney would score the
relationship, not just what the math happens to produce.
"""

from __future__ import annotations

import pytest

from tm_similarity import (
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


def test_phonetic_length_disparity_dampened() -> None:
    """A much shorter mark must not score near-identical via Metaphone's
    vowel-dropping. "KAITO"/"KAT" both encode to "KT" but differ in syllable
    count — the aural length dampener pulls it to "moderate", below a same-length
    variant. Plurals / minor variants within tolerance stay high."""
    short = phonetic_similarity("KAITO", "KAT")
    same_len = phonetic_similarity("KAITO", "KAITA")
    assert short < 0.75, f"expected <0.75 after length dampener, got {short}"
    assert short < same_len, f"disparate ({short}) should score below same-length ({same_len})"
    assert phonetic_similarity("APPLE", "APPLES") >= 0.90


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
# Multi-word marks — the trap whole-string JW falls into


def test_phonetic_multiword_unrelated_brands_should_score_low() -> None:
    """OMBRES TENDRES (Chanel) vs MAYBELLINE SPOT RESCUE (L'Oreal) — two
    multi-word cosmetics marks with no shared distinctive word. Whole-string
    Jaro-Winkler scores 0.70 (false positive) from shared common letters in
    similar-length strings; an examiner would not call these confusable.

    Token-level best-pair JW must reflect: "no token in OMBRES TENDRES has
    a strong match in MAYBELLINE SPOT RESCUE" → well below the 0.50
    conjunction-guard floor.
    """
    s = phonetic_similarity("OMBRES TENDRES", "MAYBELLINE SPOT RESCUE")
    assert s < 0.50, f"expected <0.50 (no shared dominant word), got {s}"


def test_phonetic_multiword_no_shared_word_should_score_low() -> None:
    """OMBRES TENDRES vs PRETTY PEONY — same trap, both 2-token cosmetics
    marks. Whole-string JW finds 0.59 from shared letters; word pairing
    sees no good match between any pair of tokens."""
    s = phonetic_similarity("OMBRES TENDRES", "PRETTY PEONY")
    assert s < 0.50, f"expected <0.50 (no shared dominant word), got {s}"


def test_phonetic_shared_dominant_word_should_still_match() -> None:
    """LIPITOR EXTRA vs LIPITAR PLUS — same dominant 'LIPITOR/LIPITAR'
    family, descriptive variant ('EXTRA'/'PLUS') after. A trademark
    examiner would flag the dominant-word collision. With token-level
    pairing the LIPITOR/LIPITAR pair scores ~0.95 and EXTRA/PLUS scores
    near 0, averaging to a moderate-but-meaningful conflict signal."""
    s = phonetic_similarity("LIPITOR EXTRA", "LIPITAR PLUS")
    assert s >= 0.50, f"expected >=0.50 (shared dominant LIPITOR-family), got {s}"


def test_phonetic_one_shared_distinctive_word() -> None:
    """COCA COLA vs COCA ZERO — one of two tokens shared (the brand
    house), the other is a product descriptor. Examiner takeaway: still
    related (both Coca-branded). Token pairing gives ~0.5."""
    s = phonetic_similarity("COCA COLA", "COCA ZERO")
    assert s >= 0.40, f"expected ~0.5 (one shared brand token), got {s}"


def test_phonetic_token_count_mismatch_penalty() -> None:
    """A single-token mark should not score 1.0 against a multi-token mark
    just because one token matched. BMW vs BMW AUTO REPAIR SERVICE has the
    BMW token in common, but the multi-word longer mark adds distinguishing
    descriptive tokens that should pull the average down."""
    s = phonetic_similarity("BMW", "BMW AUTO REPAIR SERVICE")
    assert s < 0.50, f"expected <0.50 (1-of-4 token match), got {s}"


def test_phonetic_separator_tolerant_tokenisation() -> None:
    """Tokens split on hyphens / slashes / ampersands the same way they
    split on whitespace, so brand variants COCA-COLA vs COCA COLA score
    identically (an examiner reads both as the same two-word mark)."""
    assert phonetic_similarity("COCA-COLA", "COCA COLA") == pytest.approx(
        phonetic_similarity("COCA COLA", "COCA COLA")
    )


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
# Visual similarity (no pHash pair available → typographic fallback)


def test_visual_falls_back_to_typographic_when_no_logos() -> None:
    """Neither mark has a stored pHash. Engine returns the typographic JW
    score on the wordmark text, with confidence='typographic' so the UI
    can warn the user that this isn't a real visual match."""
    vs = visual_similarity(None, None, "MONTINIS", "MONTANIS")
    assert vs.confidence == "typographic"
    assert vs.score >= 0.85  # similar text


def test_visual_typographic_uses_token_level_jw() -> None:
    """The same false-positive trap as phonetic: 'OMBRES TENDRES' vs
    'MAYBELLINE SPOT RESCUE' both lack a pHash, fall to typographic JW.
    Whole-string JW would return 0.70 (looks visually 'similar' purely
    because of letter frequency). Token-level pairing must agree with
    the examiner's read: two visually distinct multi-word wordmarks
    score well below 0.50."""
    vs = visual_similarity(None, None, "OMBRES TENDRES", "MAYBELLINE SPOT RESCUE")
    assert vs.confidence == "typographic"
    assert vs.score < 0.50, f"expected <0.50, got {vs.score}"


def test_visual_returns_none_signal_for_blank_marks() -> None:
    vs = visual_similarity(None, None, "", "")
    assert vs.confidence == "none"
    assert vs.score == 0.0


def test_visual_one_sided_phash_falls_to_typographic() -> None:
    """Only one side has a stored pHash; the other is None. A pHash
    comparison needs BOTH hashes (the `if a_phash and b_phash` branch),
    so a single-sided pHash can't produce a perceptual signal and the
    engine falls back to typographic JW on the wordmark text."""
    vs = visual_similarity("ffffffffffffffff", None, "ALPHA", "ALPHA")
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
        f"max signal {max(0.486, 0.423)} < 0.5 should force Low risk, even with composite={c.composite}"
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


def test_typographic_visual_cannot_satisfy_conjunction_guard_alone() -> None:
    """OMBRES TENDRES vs PRETTY PEONY case: token-level pairing puts
    phonetic at ~0.48 (below the 0.50 sight-or-sound floor) but
    typographic visual JW spikes to ~0.56 because both marks are
    multi-word same-length English-ish strings.

    Typographic visual is JW on the same wordmark text the phonetic
    raw component already saw — it's the same family of signal, not
    independent. Letting it independently satisfy the conjunction
    guard is double-counting. Only real pHash visual (real perceptual
    comparison of extracted logo PNGs) is independent enough to
    satisfy the guard on its own.
    """
    c = composite_score(
        phonetic=0.476,
        visual=0.559,
        class_o=1.0,
        vienna_o=0.0,
        visual_confidence="typographic",
    )
    # composite = 0.4*0.476 + 0.25*0.559 + 0.2*1.0 + 0 = 0.530 — would
    # otherwise hit Possible. But max_sig collapses to phonetic only
    # (0.476 < 0.50) → conjunction guard fails → Low risk.
    assert c.verdict == "Low risk", (
        f"typographic visual {0.559} should NOT independently satisfy "
        f"the conjunction guard; expected Low risk, got {c.verdict}"
    )


def test_composite_figurative_phash_visual_alone_is_low_risk() -> None:
    """Two nameless figurative marks with near-identical logos (real pHash
    visual ~0.95) but NO shared figurative classification (vienna_o = 0) and
    no name/sound signal (phonetic = 0). The conjunction guards both pass —
    pHash visual carries max_sig past the 0.50 sight-or-sound floor, and the
    class guard passes — but the weighted composite lands 0.438, below the
    0.50 floor, so the engine verdicts 'Low risk'.

    This is the precision boundary for the 'Similar marks landing this period'
    card: a bare pHash resemblance with nothing else shared is most likely a
    perceptual-hash coincidence (the gazette classified the two logos'
    elements completely differently), so it is deliberately NOT surfaced."""
    c = composite_score(phonetic=0.0, visual=0.95, class_o=1.0, vienna_o=0.0, visual_confidence="phash")
    # composite = 0.4*0 + 0.25*0.95 + 0.2*1.0 + 0 = 0.438 < 0.50 → Low risk
    assert c.verdict == "Low risk"


def test_composite_figurative_phash_visual_with_shared_vienna_is_conflict() -> None:
    """The genuine figurative-look-alike case: two nameless marks with
    near-identical logos (pHash visual ~0.95) that ALSO share Vienna codes —
    which is the norm, since Vienna codes ARE the classification of a mark's
    figurative elements, so real visual twins almost always share them. The
    second signal pushes the composite to 0.587, clearing the 0.50 floor →
    'Possible conflict'.

    Confirms that dropping the applicant-name fallback from the similar-marks
    scoring does NOT kill genuine figurative matches: the visual + vienna axes
    carry them past the conjunction verdict the card now gates on."""
    c = composite_score(
        phonetic=0.0,
        visual=0.95,
        class_o=1.0,
        vienna_o=1.0,
        visual_confidence="phash",
    )
    # composite = 0.4*0 + 0.25*0.95 + 0.2*1.0 + 0.15*1.0 = 0.587 >= 0.50 → Possible
    assert c.verdict == "Possible conflict"


def test_phash_visual_does_satisfy_conjunction_guard() -> None:
    """Real pHash visual IS independent evidence. If the engine ran a
    perceptual-hash comparison on extracted logo PNGs and found 0.85
    similarity, that's an examiner-grade visual signal — it can carry
    the conjunction guard even when phonetic is weak."""
    c = composite_score(
        phonetic=0.30,
        visual=0.85,
        class_o=1.0,
        vienna_o=0.0,
        visual_confidence="phash",
    )
    # mark_score = 0.4*0.30 + 0.25*0.85 = 0.333
    # mark_strength = 0.85 (phash, max counts) → goods_factor = 1.0
    # composite = 0.333 + 0.2 = 0.533 ≥ 0.50, mark_strength ≥ 0.50 → Possible.
    assert c.verdict == "Possible conflict"


def test_class_overlap_alone_cannot_inflate_composite() -> None:
    """The user's complaint that drove this fix: OMBRES TENDRES vs
    MAYBELLINE SPOT RESCUE scored 45% composite because class overlap
    (1.0) added its full 0.20 weight to the composite even though the
    marks themselves are visually and phonetically distinct.

    With the goods-dampener, mark_strength of 0.38 (Jaro-Winkler
    baseline noise from shared common letters) pulls goods_factor down
    to ~0.20 → class contributes only ~0.04 instead of 0.20, so the
    composite reflects only the (irreducible) JW baseline noise — well
    under 0.30.
    """
    c = composite_score(
        phonetic=0.38,
        visual=0.38,
        class_o=1.0,
        vienna_o=0.0,
        visual_confidence="typographic",
    )
    # mark_score = 0.4*0.38 + 0.25*0.38 = 0.247
    # mark_strength = 0.38 (typographic, phonetic only)
    # goods_factor = (0.38 - 0.30) / 0.40 = 0.20
    # composite = 0.247 + 0.20 * 0.20 = 0.287
    assert c.composite < 0.30, (
        f"two visibly distinct multi-word marks sharing only Nice class "
        f"should land well below 30%, not at the previous 45%. got {c.composite}"
    )
    assert c.verdict == "Low risk"


def test_goods_dampener_does_not_break_real_conflicts() -> None:
    """MONTINIS vs MONTANIS sharing class 30 (sweets) — the dampener
    must NOT demote this. mark_strength ≥ 0.7 → goods contribute fully,
    composite stays in 'Likely conflict' territory."""
    c = composite_score(
        phonetic=0.945,
        visual=0.921,
        class_o=1.0,
        vienna_o=0.0,
        visual_confidence="typographic",
    )
    # mark_strength = 0.945 (phonetic, typographic) → goods_factor = 1.0 capped
    # mark_score = 0.4*0.945 + 0.25*0.921 = 0.608
    # composite = 0.608 + 0.2 = 0.808
    assert c.composite >= 0.70
    assert c.verdict == "Likely conflict"


def test_goods_dampener_preserves_pharma_shared_dominant_word() -> None:
    """LIPITOR EXTRA vs LIPITAR PLUS — shared dominant pharma brand,
    descriptive suffixes vary. mark_strength ≈ 0.56 → goods_factor ≈ 0.64
    → enough goods contribution to keep this in 'Possible conflict'."""
    c = composite_score(
        phonetic=0.557,
        visual=0.675,
        class_o=1.0,
        vienna_o=0.0,
        visual_confidence="typographic",
    )
    # mark_strength = 0.557, goods_factor = (0.557-0.3)/0.4 = 0.643
    # mark_score = 0.4*0.557 + 0.25*0.675 = 0.392
    # composite = 0.392 + 0.2 * 0.643 = 0.521 → Possible
    assert c.verdict == "Possible conflict"
