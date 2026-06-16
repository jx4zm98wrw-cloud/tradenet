"""Trademark similarity engine — expert-grade signals for conflict scoring.

Replaces the prior mock that returned md5-based jitter regardless of actual
mark content. The goal is to produce scores a seasoned IP/trademark
professional would defend in front of an examiner.

Signals
-------
1. **Phonetic** — max(Jaro-Winkler on raw strings, Jaro-Winkler on Metaphone
   codes). Jaro-Winkler is the industry standard for trademark name matching
   (Cohen-Ravikumar-Fienberg 2003) — it weights matching prefixes higher,
   which mirrors how the eye/ear processes brand names left-to-right.
   Metaphone collapses spelling variants ("MONTINIS" / "MONTANIS" both encode
   to "MNTNS"), surfacing sound-alike conflicts that Levenshtein would miss.

   Vietnamese-aware: diacritics are stripped via NFD decomposition before
   encoding, so "Bạc" / "BAC" / "Bac" all phonetically match.

2. **Visual** — pHash distance on extracted PNG specimens when both marks
   have `logo_path`; typographic Jaro-Winkler on the wordmark text as a
   fallback. The return value includes a `confidence` flag so the UI can
   distinguish "real visual analysis" from "we had to use the text proxy."

3. **Class overlap (Nice)** — Jaccard intersection. Pre-existing; kept.
   A necessary-not-sufficient signal: marks in different classes don't
   confuse consumers, but identical classes alone don't make marks
   confusable.

4. **Vienna code overlap** — Jaccard on Vienna figurative element codes.
   The international standard for categorising mark imagery; marks sharing
   Vienna codes have been examiner-classified as carrying related visual
   elements (circles, leaves, letters, etc.). Independent signal from pHash.

Composite & verdict
-------------------
Default weights: phonetic 40% · visual 25% · class 20% · vienna 15%.
Verdict thresholds match how trademark examiners triage:
  composite >= 0.70 → Likely conflict
  composite >= 0.50 → Possible conflict
  else            → Low risk

Per-matter tunability (the design's stated requirement) belongs at the
composite level via `weights`. The four signal functions stay pure.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jellyfish

# ---------------------------------------------------------------------------
# Vietnamese-aware normalisation


# Vietnamese-specific letters that NFD does NOT decompose. They're encoded
# as single Unicode codepoints rather than base+combining, so we map them
# explicitly. (Đ/đ = D with stroke = U+0110/U+0111.)
_VN_LETTER_MAP = str.maketrans({"Đ": "D", "đ": "d"})


def normalize_vn(s: str | None) -> str:
    """Uppercase, collapse whitespace, and strip Vietnamese diacritics.

    Vietnamese marks frequently appear in mixed forms ("CÔNG TY" / "CONG TY"
    / "Công ty"). NFD decomposes most pre-composed accented letters into
    base + combining accent which we then drop. Đ/đ is a special case —
    not a precomposed combination, so NFD leaves it alone; we map it
    explicitly to D/d first.

    Lowercased and whitespace-collapsed so the downstream similarity
    functions see a single canonical form.

    Returns empty string for None/empty input.
    """
    if not s:
        return ""
    s = s.translate(_VN_LETTER_MAP)
    # NFD splits "ầ" into "a" + combining-grave. Mn = "Mark, nonspacing".
    decomposed = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(stripped.upper().split())


# ---------------------------------------------------------------------------
# Token-level similarity (the multi-word backbone)


_TOKEN_SPLIT = re.compile(r"[\s\-_/&,.]+")


def _tokens(s: str) -> list[str]:
    """Split a normalised mark string into tokens.

    Splits on whitespace and common brand separators (`-`, `_`, `/`, `&`, `,`,
    `.`). Empty tokens are dropped. Single-word marks return a one-element list,
    which keeps the downstream best-pair logic numerically identical to
    whole-string Jaro-Winkler (so MONTINIS/MONTANIS still score 0.94).
    """
    return [t for t in _TOKEN_SPLIT.split(s.strip()) if t]


def _best_pair_jw(short: list[str], long: list[str]) -> float:
    """Greedy best-pairing Jaro-Winkler between two token lists.

    For each token in the *shorter* list, pick the most-similar unmatched
    token in the *longer* list. Average over `len(long)` so unpaired tokens
    in the longer list drag the score down — "BMW" vs "BMW AUTO REPAIR
    SERVICE" must not score 1.0 just because the one BMW token matched.

    The greedy choice (not Hungarian-optimal) is fine for the token counts
    we see in real marks (2-5 tokens); any pathology requires constructing
    a degenerate test case where two tokens both prefer the same third
    token. Hungarian would cost O(n³); greedy is O(n²) with negligible
    quality difference at this scale.

    Why this matters vs. whole-string JW:
    Raw JW on "OMBRES TENDRES" vs "MAYBELLINE SPOT RESCUE" scores 0.70
    purely from shared common letters (E, R, S, T, N) in similar-length
    strings — the algorithm has no notion of word boundaries. Token-level
    pairing reflects how a trademark examiner actually reads multi-word
    marks: "is there a dominant word in common?" USPTO TMEP §1207.01(b)
    and EU IPO comparison guidance both call out the dominant-element
    rule that single-string JW cannot express.
    """
    if not short or not long:
        return 0.0
    used = [False] * len(long)
    pair_scores: list[float] = []
    for t in short:
        best, best_idx = 0.0, -1
        for i, u in enumerate(long):
            if used[i]:
                continue
            s = jellyfish.jaro_winkler_similarity(t, u)
            if s > best:
                best, best_idx = s, i
        if best_idx >= 0:
            used[best_idx] = True
        pair_scores.append(best)
    return sum(pair_scores) / len(long)


def _token_jw(a: str, b: str) -> float:
    """Best-pair Jaro-Winkler between two whitespace-separated strings."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return _best_pair_jw(short, long)


# ---------------------------------------------------------------------------
# Phonetic similarity


def phonetic_similarity(a: str | None, b: str | None) -> float:
    """Return token-level Jaro-Winkler phonetic similarity in [0, 1].

    Weighted blend of two signals, both computed at the *token* level:
      - Raw JW (70% weight) — best-pair JW between tokens of the two marks,
        on diacritic-normalised uppercase strings.
      - Metaphone-encoded JW (30% weight) — same best-pair scheme on the
        Metaphone code of each token; catches sound-alike variants like
        NEUREX/NEUROFAX where the surface spellings diverge but the
        phoneme sequences align.

    Why token-level matters:
    Whole-string Jaro-Winkler over multi-word marks ("OMBRES TENDRES"
    vs "MAYBELLINE SPOT RESCUE") spikes to ~0.70 purely from shared
    common letters in similar-length strings — no examiner would call
    those confusable, but the algorithm has no word boundaries.
    Best-pair token JW correctly drops that to ~0.38 because no token
    in OMBRES TENDRES has a strong match in MAYBELLINE SPOT RESCUE.

    Single-word marks are unchanged: best-pair JW on one-element token
    lists reduces to whole-string JW. MONTINIS/MONTANIS still scores
    0.94; NEUREX/NEUROFAX still scores 0.90.

    Why a weighted blend rather than max:
    Metaphone reduces aggressively for short/alphanumeric marks
    ("MF11RCE" → "MFRS"), and JW between two short reduced codes can
    spike to 0.6+ purely because they share a first letter and a last
    letter. The blend keeps Metaphone as supporting evidence — a real
    sound-alike scores high on both raw and Metaphone; a coincidental
    Metaphone match alone won't carry the score over the threshold.

    Empty/blank inputs return 0.0 (no signal).
    """
    na, nb = normalize_vn(a), normalize_vn(b)
    if not na or not nb:
        return 0.0

    raw = _token_jw(na, nb)

    # Metaphone per token, then best-pair JW on the resulting codes.
    # Encoding the whole multi-word string in one call produces a single
    # blob ("OMBRSTNTRS") that loses the same word-boundary information
    # whole-string JW does — defeats the point of going token-level.
    ma_codes = [c for c in (jellyfish.metaphone(t) for t in _tokens(na)) if c]
    mb_codes = [c for c in (jellyfish.metaphone(t) for t in _tokens(nb)) if c]
    if not ma_codes or not mb_codes:
        return round(raw, 3)
    short, long = (ma_codes, mb_codes) if len(ma_codes) <= len(mb_codes) else (mb_codes, ma_codes)
    phon = _best_pair_jw(short, long)

    return round(0.7 * raw + 0.3 * phon, 3)


# ---------------------------------------------------------------------------
# Visual similarity (pHash + typographic fallback)

VisualConfidence = Literal["phash", "typographic", "none"]


@dataclass(frozen=True)
class VisualScore:
    """A visual-similarity score with its provenance.

    `confidence='phash'` means we ran a real perceptual hash comparison on
    extracted PNG specimens — the gold standard. `confidence='typographic'`
    means we fell back to string similarity on the wordmark text because
    at least one mark had no extracted logo; the score is still meaningful
    but a trademark expert should weigh it less than a real pHash match.
    `confidence='none'` means we have no signal at all.
    """

    score: float
    confidence: VisualConfidence


# pHash module-level cache: `logo_path` → ImageHash. Two reasons for caching:
# (a) The Compare / similar pages compare one anchor against several others,
#     so the anchor's hash is computed N times without it.
# (b) ImageHash construction loads the file via Pillow — measurable on the
#     hot path. Eviction isn't critical (logo files don't change; ~46k max
#     entries times 8 bytes ≈ 400KB worst case).
_phash_cache: dict[str, object] = {}


def _phash_for(image_root: Path, logo_path: str | None):
    """Compute or fetch the perceptual hash for a logo PNG.

    Returns None if logo_path is empty, the file is missing, or Pillow can't
    decode it. Caller treats None as "no visual signal from this side."
    """
    if not logo_path:
        return None
    if logo_path in _phash_cache:
        return _phash_cache[logo_path]
    try:
        # Import lazily — Pillow + imagehash add ~30MB of module-load weight
        # the API doesn't need on cold start when no comparison is requested.
        import imagehash
        from PIL import Image

        abs_path = image_root / logo_path
        if not abs_path.is_file():
            return None
        with Image.open(abs_path) as img:
            h = imagehash.phash(img)
        _phash_cache[logo_path] = h
        return h
    except Exception:
        # Corrupt PNG / unsupported codec / etc. Cache the failure so we
        # don't retry on every request. None is a fine sentinel here.
        _phash_cache[logo_path] = None
        return None


def visual_similarity(
    a_logo: str | None,
    b_logo: str | None,
    a_text: str | None,
    b_text: str | None,
    image_root: Path,
) -> VisualScore:
    """Compare two marks visually.

    Preference order:
      1. Real pHash distance — both marks have extracted logo PNGs. The
         standard "perceptually similar" threshold is HD/64 <= 10
         (~84% similarity); we surface the raw 1 - HD/64 ratio.
      2. Typographic JW — one or both marks have no logo. Fall back to
         Jaro-Winkler on the wordmark text. Less authoritative — a
         trademark expert would want to inspect the actual specimens.
      3. None — both marks are wordmark-only and have no displayable text
         either. No visual signal.
    """
    ha, hb = _phash_for(image_root, a_logo), _phash_for(image_root, b_logo)
    if ha is not None and hb is not None:
        # imagehash subtraction returns Hamming distance (0 = identical, 64 = max).
        hd = ha - hb
        sim = max(0.0, 1.0 - hd / 64.0)
        return VisualScore(round(sim, 3), "phash")

    # Typographic fallback. Token-level best-pair JW on the wordmark text —
    # same reasoning as phonetic_similarity: whole-string JW on multi-word
    # marks finds spurious overlap from shared common letters. No Metaphone
    # here since "visual" means glyph similarity, not sound.
    na, nb = normalize_vn(a_text), normalize_vn(b_text)
    if na and nb:
        sim = _token_jw(na, nb)
        return VisualScore(round(sim, 3), "typographic")

    return VisualScore(0.0, "none")


# ---------------------------------------------------------------------------
# Set-similarity signals (Nice classes, Vienna codes)


def _jaccard(a: list[str] | None, b: list[str] | None) -> float:
    """Standard Jaccard: size of intersection over size of union. Returns 0
    when either side is empty (no signal to compute against)."""
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def class_overlap(a: list[str] | None, b: list[str] | None) -> float:
    """Jaccard on Nice classification. Necessary-not-sufficient for confusion."""
    return _jaccard(a, b)


def vienna_overlap(a: list[str] | None, b: list[str] | None) -> float:
    """Jaccard on Vienna figurative codes. Independent visual signal from pHash:
    marks can share Vienna codes (both have circles) without their actual
    rendered logos being pHash-similar."""
    return _jaccard(a, b)


# ---------------------------------------------------------------------------
# Composite + verdict

DEFAULT_WEIGHTS = {"phonetic": 0.40, "visual": 0.25, "class": 0.20, "vienna": 0.15}
"""Per-matter overrides land here. The README design called for 40/30/30
across phonetic/visual/class; adding Vienna as a 4th signal redistributes:
phonetic stays 40 (the dominant signal in name-confusion cases),
visual drops to 25 to make room for vienna at 15, class stays at 20.
A trademark professional working a specific matter (e.g. pharma where
phonetics dominate) should tune these per matter — exactly the design's
'tunable per matter' requirement."""


def resolve_weights(overrides: dict[str, float] | None) -> dict[str, float]:
    """Merge per-matter weight overrides over DEFAULT_WEIGHTS and renormalise to 1.

    The single source of truth for turning a stored/requested weights dict into
    the normalised weights `composite_score` expects. Shared by the per-matter
    surfaces (watchlist-scoped similar marks) and the /compare endpoint so they
    validate identically.

    - None / empty → DEFAULT_WEIGHTS (a fresh copy).
    - Only the four known keys (phonetic/visual/class/vienna) are honoured;
      unknown keys are ignored and missing keys inherit their default.
    - Non-numeric / negative values are dropped (fall back to the default for
      that key); a non-positive total falls back entirely to DEFAULT_WEIGHTS.
    """
    if not overrides:
        return dict(DEFAULT_WEIGHTS)
    merged = dict(DEFAULT_WEIGHTS)
    for k in DEFAULT_WEIGHTS:
        v = overrides.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            merged[k] = float(v)
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in merged.items()}


@dataclass(frozen=True)
class CompositeScore:
    composite: float
    verdict: Literal["Likely conflict", "Possible conflict", "Low risk"]
    verdict_tone: Literal["stamp", "warn", "ok"]


def composite_score(
    phonetic: float,
    visual: float,
    class_o: float,
    vienna_o: float,
    weights: dict[str, float] | None = None,
    visual_confidence: VisualConfidence = "phash",
) -> CompositeScore:
    """Composite conflict score + verdict.

    The composite is a sum of two contributions:
      - mark_score    = w_phon * phonetic + w_vis * visual   (the sight-or-sound axis)
      - goods_score   = w_class * class_o + w_vienna * vienna_o   (the goods-relatedness axis)

    They are NOT simply added with full weight. Trademark confusion
    requires similar marks AND related goods, multiplicatively — Apple
    Records vs Apple Computer (1976) had identical marks but unrelated
    goods → zero confusion. The symmetric case must hold: same goods
    + clearly different marks → minimal conflict score.

    So `goods_score` is dampened by mark strength. With no real
    sight-or-sound signal the goods axis contributes ~0 (class overlap
    alone can't carry a "conflict score"). At mark_strength ≥ 0.7 the
    goods axis contributes fully.

      composite = mark_score + goods_score * min(1, mark_strength / 0.7)

    `mark_strength` uses the same rule as the conjunction guard:
      - `'phash'` visual: max(phonetic, visual) — they're independent signals.
      - `'typographic'` / `'none'`: phonetic only — typographic visual is
        JW on the same wordmark text the phonetic raw saw, not independent.

    Verdict bands (applied after the math above):
      Likely:   composite >= 0.70, mark_strength >= 0.70, class >= 0.30
      Possible: composite >= 0.50, mark_strength >= 0.50, class >= 0.20
      else:     Low risk

    Conjunction guards (the mark_strength + class_o clauses) remain
    because the dampener fixes the numeric composite but not the
    verdict on edge cases. A pair with mark_strength 0.49 and class
    overlap 1.0 might still produce a composite ~0.5 from the
    dampener; the guard pins it as Low risk for examiner-grade
    consistency.

    Why this matters in practice — OMBRES TENDRES vs MAYBELLINE SPOT
    RESCUE was scoring 0.447 because class overlap added its full
    0.20 weight even though the marks themselves are clearly
    different. The dampener reduces that to ~0.36 — still nonzero
    (the marks DO share class-3 cosmetics, and JW always returns
    some baseline overlap for similar-length strings), but no longer
    visually misleading.
    """
    w = weights or DEFAULT_WEIGHTS

    mark_score = w["phonetic"] * phonetic + w["visual"] * visual
    goods_score = w["class"] * class_o + w["vienna"] * vienna_o

    # Conjunction signal: pHash visual is independent evidence; typographic
    # / none is just JW on the wordmark text and shouldn't double-count.
    mark_strength = max(phonetic, visual) if visual_confidence == "phash" else phonetic

    # Goods-dampener ramp:
    #   mark_strength <= 0.30  → goods contribute 0 (Jaro-Winkler baseline
    #                            noise; no real mark similarity to amplify)
    #   0.30 < mark_strength < 0.70 → linear ramp 0 → 1
    #   mark_strength >= 0.70  → goods contribute fully
    #
    # The 0.30 floor matters: JW returns ~0.30–0.45 for *any* two
    # similar-length strings just from shared common letters
    # (OMBRES TENDRES vs MAYBELLINE SPOT RESCUE scores phonetic 0.38
    # purely from that effect). Without the floor, class overlap would
    # still inflate the composite even though the marks are clearly
    # different. The floor cuts JW noise out of the goods contribution.
    goods_factor = max(0.0, min(1.0, (mark_strength - 0.30) / 0.40))
    composite = round(mark_score + goods_score * goods_factor, 3)

    if composite >= 0.70 and mark_strength >= 0.70 and class_o >= 0.30:
        return CompositeScore(composite, "Likely conflict", "stamp")
    if composite >= 0.50 and mark_strength >= 0.50 and class_o >= 0.20:
        return CompositeScore(composite, "Possible conflict", "warn")
    return CompositeScore(composite, "Low risk", "ok")
