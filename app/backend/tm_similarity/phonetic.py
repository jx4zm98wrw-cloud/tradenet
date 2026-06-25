from __future__ import annotations

import re
import unicodedata

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

# Aural length-disparity tolerance. JW + Metaphone ignore syllable count and
# rhythm — Metaphone drops vowels, so "KAITO" and "KAT" both encode to "KT" and
# spuriously score ~0.93. When the two surface forms differ in length by more
# than this fraction, the phonetic score is scaled down proportionally; within
# it (the shorter is ≥80% of the longer) the score is unchanged, so plurals /
# minor variants (NIKE/NIKEE, APPLE/APPLES) and same-length sound-alikes
# (MONTINIS/MONTANIS) are unaffected. Mirrors how USPTO/EUIPO examiners weigh
# syllable count and overall length in the aural-similarity assessment.
_PHONETIC_LENGTH_TOLERANCE = 0.8


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

    # Aural length-disparity dampener (see _PHONETIC_LENGTH_TOLERANCE): scale the
    # score down when the two surface forms differ a lot in length, mirroring how
    # examiners weigh syllable count / rhythm. Within the tolerance the factor is
    # 1.0 (no change).
    la, lb = len(na.replace(" ", "")), len(nb.replace(" ", ""))
    length_factor = min(1.0, (min(la, lb) / max(la, lb)) / _PHONETIC_LENGTH_TOLERANCE) if la and lb else 1.0

    # Metaphone per token, then best-pair JW on the resulting codes.
    # Encoding the whole multi-word string in one call produces a single
    # blob ("OMBRSTNTRS") that loses the same word-boundary information
    # whole-string JW does — defeats the point of going token-level.
    ma_codes = [c for c in (jellyfish.metaphone(t) for t in _tokens(na)) if c]
    mb_codes = [c for c in (jellyfish.metaphone(t) for t in _tokens(nb)) if c]
    if not ma_codes or not mb_codes:
        return round(raw * length_factor, 3)
    short, long = (ma_codes, mb_codes) if len(ma_codes) <= len(mb_codes) else (mb_codes, ma_codes)
    phon = _best_pair_jw(short, long)

    return round((0.7 * raw + 0.3 * phon) * length_factor, 3)
