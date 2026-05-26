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
# Phonetic similarity


def phonetic_similarity(a: str | None, b: str | None) -> float:
    """Return Jaro-Winkler-based phonetic similarity in [0, 1].

    Weighted blend of two signals:
      - Raw JW on diacritic-normalised uppercase strings (70% weight) —
        the authoritative signal; trademark examiners compare what's
        actually written before they consider sound-alikes.
      - JW on Metaphone codes (30% weight) — catches genuine sound-alike
        variants ("NEUREX" / "NEUROFAX" both encode to NRKS/NRFKS) but
        only as a *boost* on top of the raw signal.

    Why a weighted blend rather than max:
    Metaphone reduces aggressively for short/alphanumeric marks
    ("MF11RCE" → "MFRS"), and JW between two short reduced codes can
    spike to 0.6+ purely because they share a first letter and a last
    letter. Taking the max would let that coincidence dominate. The
    blend keeps Metaphone as supporting evidence — a real sound-alike
    will score high on both raw and Metaphone, so the blend still
    rewards it; a coincidental Metaphone match alone won't carry the
    score over the conflict threshold.

    Empty/blank inputs return 0.0 (no signal).
    """
    na, nb = normalize_vn(a), normalize_vn(b)
    if not na or not nb:
        return 0.0

    raw = jellyfish.jaro_winkler_similarity(na, nb)

    ma, mb = jellyfish.metaphone(na), jellyfish.metaphone(nb)
    if not ma or not mb:
        return raw
    phon = jellyfish.jaro_winkler_similarity(ma, mb)

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

    # Typographic fallback. Uses the same JW as phonetic but on raw text
    # (no Metaphone) since "visual" means glyph similarity, not sound.
    na, nb = normalize_vn(a_text), normalize_vn(b_text)
    if na and nb:
        sim = jellyfish.jaro_winkler_similarity(na, nb)
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
) -> CompositeScore:
    """Weighted sum + verdict, with examiner-grade conjunction guards.

    The numeric composite is a straight weighted sum across the four
    signals. The *verdict* requires both:
      1. The composite to clear the band's threshold, AND
      2. At least one of {phonetic, visual} to clear a minimum strength
         (i.e. there's *some* sight-or-sound similarity, not just class
         overlap), AND
      3. Some class proximity (marks in unrelated classes don't confuse
         consumers regardless of similarity).

    This matches how examiners think: confusion = similar marks IN
    related goods, not "any signal high enough." The screenshot bug
    case — MONTINIS (confectionery) vs MF11RCE (a model number)
    sharing 100% Nice classes but no phonetic or visual similarity
    — should land in 'Low risk', because neither phonetic nor visual
    signal clears the 0.5 minimum.

    Bands:
      Likely:   composite >= 0.70, max(phon,vis) >= 0.70, class >= 0.30
      Possible: composite >= 0.50, max(phon,vis) >= 0.50, class >= 0.20
      else:     Low risk
    """
    w = weights or DEFAULT_WEIGHTS
    composite = round(
        w["phonetic"] * phonetic + w["visual"] * visual + w["class"] * class_o + w["vienna"] * vienna_o,
        3,
    )
    max_sig = max(phonetic, visual)

    if composite >= 0.70 and max_sig >= 0.70 and class_o >= 0.30:
        return CompositeScore(composite, "Likely conflict", "stamp")
    if composite >= 0.50 and max_sig >= 0.50 and class_o >= 0.20:
        return CompositeScore(composite, "Possible conflict", "warn")
    return CompositeScore(composite, "Low risk", "ok")
