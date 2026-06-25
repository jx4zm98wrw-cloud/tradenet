"""Vietnamese-aware phonetic key + language detector (Track 2).

Pure stdlib (``re``/``unicodedata``). Reimplements the published Northern
(Hanoi) phonological correspondences — Kirby (2011), JIPA "Vietnamese (Hanoi
Vietnamese)"; Pham (2006) G2P rules as used by vPhon — to encode a toneless
onset–(glide)–nucleus–(coda) key for fuzzy aural-confusion matching. No code
is copied from vPhon; only the cited phonological facts are reused.

Routed in by ``phonetic.phonetic_similarity`` for VN-vs-VN comparisons only.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Onset table — longest spelling first so greedy prefix matching is correct
# (NGH before NG before N; GI before G; CH before C; TR/TH before T; …).
# Each onset maps to a single internal phoneme code; codes are a private,
# collision-free alphabet — Northern merges are baked in (same code => merged):
#   /k/=k (c,k,q)   /z/=z (d,gi,r)   /tɕ/=c (ch,tr)   /s/=s (s,x)
#   /ŋ/=q (ng,ngh)  /ɣ/=g (g,gh)     /f/=f (ph)       /x/=x (kh)
#   /tʰ/=d (th)     /ɲ/=J (nh)       plus b l m n p t v h.
# "QU" emits onset /k/ + the /w/ on-glide via the trailing "w" sentinel.
_ONSETS: list[tuple[str, str]] = [
    ("NGH", "q"), ("NG", "q"), ("GH", "g"), ("GI", "z"), ("CH", "c"),
    ("TR", "c"), ("TH", "d"), ("KH", "x"), ("PH", "f"), ("QU", "kw"),
    ("NH", "J"), ("C", "k"), ("K", "k"), ("Q", "k"), ("G", "g"),
    ("D", "z"), ("R", "z"), ("S", "s"), ("X", "s"), ("B", "b"),
    ("L", "l"), ("M", "m"), ("N", "n"), ("P", "p"), ("T", "t"),
    ("V", "v"), ("H", "h"),
]

_VOWELS = frozenset("AEIOUY")


def _canon_coda(cons: str) -> str:
    """Map a syllable-final consonant cluster to one of the 8 VN coda codes.

    VN has exactly eight codas /p t k m n ŋ j w/ (Kirby 2011). Orthographic
    finals collapse: ``c``/``ch`` -> /k/, ``ng`` -> /ŋ/, ``nh`` -> palatal.
    A cluster with no legal VN coda returns "" (dropped from the key).
    """
    if cons == "NG":
        return "q"
    if cons == "NH":
        return "J"
    head = cons[:1]
    if head == "C":  # C or CH -> /k/
        return "k"
    return {"P": "p", "T": "t", "M": "m", "N": "n"}.get(head, "")


def vn_phonetic_key(token: str) -> str:
    """Return a toneless Northern-Vietnamese phonetic key for one token.

    Greedy-parses ``(onset)(glide)nucleus(coda)`` per syllable, looping over
    multi-syllable tokens with maximal-onset syllabification (a single
    intervocalic consonant starts the next syllable; a cluster splits). The
    key is a string of internal phoneme codes; compare two keys with
    Jaro-Winkler the same way the Metaphone path does.

    Examples: ``GIA``/``DA``/``RA`` -> ``"za"``; ``TRANG``/``CHANG`` ->
    ``"caq"``; ``QUANG`` -> ``"kwaq"``; ``MAI`` -> ``"maj"``.
    Empty / non-alphabetic input returns "".
    """
    t = "".join(ch for ch in token.upper() if ch.isalpha())
    if not t:
        return ""
    pos = 0
    codes: list[str] = []
    while pos < len(t):
        # --- onset (optional) ---
        onset = ""
        for spelling, code in _ONSETS:
            if t.startswith(spelling, pos):
                onset = code
                pos += len(spelling)
                break
        # --- medial on-glide /w/ ---
        glide = ""
        if onset.endswith("w"):  # QU-
            glide, onset = "w", onset[:-1]
        elif t.startswith("O", pos) and pos + 1 < len(t) and t[pos + 1] in "AE":
            glide, pos = "w", pos + 1  # oa / oe
        elif t.startswith("U", pos) and pos + 1 < len(t) and t[pos + 1] == "Y":
            glide, pos = "w", pos + 1  # uy
        # --- nucleus (one or more vowels) ---
        vstart = pos
        while pos < len(t) and t[pos] in _VOWELS:
            pos += 1
        nucleus = t[vstart:pos].replace("Y", "I")
        if not nucleus:
            # leading consonant cluster with no vowel — emit onset and stop.
            codes.append(onset)
            break
        # --- coda: trailing consonant run, else vowel off-glide ---
        cstart = pos
        while pos < len(t) and t[pos] not in _VOWELS:
            pos += 1
        cons = t[cstart:pos]
        vowel_after = pos < len(t)
        coda = ""
        if cons:
            if not vowel_after:
                coda, pos = _canon_coda(cons), cstart + len(cons)
            elif len(cons) >= 2:
                coda, pos = _canon_coda(cons[0]), cstart + 1
            else:
                pos = cstart  # single intervocalic consonant -> next onset
        elif len(nucleus) >= 2 and nucleus[-1] == "I":
            coda, nucleus = "j", nucleus[:-1]  # off-glide /j/
        elif len(nucleus) >= 2 and nucleus[-1] in "OU":
            coda, nucleus = "w", nucleus[:-1]  # off-glide /w/
        codes.append(onset + glide + nucleus.lower() + coda)
    return "".join(codes)


# ---------------------------------------------------------------------------
# Language detector

# Vietnamese-specific base letters (đ + the seven extra vowels). Their
# presence is an unambiguous VN signal even before tone marks are considered.
_VN_DIACRITIC = re.compile(r"[ăâêôơưđĂÂÊÔƠƯĐ]")

# Legal VN syllable-final codas (orthographic), for the phonotactic check.
_VALID_FINAL = frozenset({"C", "CH", "NG", "NH", "P", "T", "M", "N"})
_VALID_FINAL_HEAD = frozenset({"C", "P", "T", "M", "N"})  # first char of a split cluster


def _has_vn_diacritic(text: str) -> bool:
    """True if the text carries any Vietnamese letter or tone mark."""
    if _VN_DIACRITIC.search(text):
        return True
    # NFD exposes combining tone/vowel marks (Mn = Mark, nonspacing).
    return any(unicodedata.category(c) == "Mn" for c in unicodedata.normalize("NFD", text))


def _is_vn_token(token: str) -> bool:
    """True if a toneless ASCII token parses cleanly as VN syllable(s).

    Maximal-onset parse mirroring ``vn_phonetic_key``: every consonant run
    must form a legal onset or coda, and every syllable needs a vowel. Rejects
    tokens with a consonant cluster that no VN syllabification can absorb
    (e.g. ``MAYBELLINE`` -> ``…LL…`` has no vowel between, ``APPLE`` -> ``PPL``).
    """
    t = "".join(ch for ch in token.upper() if ch.isalpha())
    if not t:
        return False
    pos = 0
    saw_syllable = False
    while pos < len(t):
        for spelling, _code in _ONSETS:
            if t.startswith(spelling, pos):
                pos += len(spelling)
                break
        vstart = pos
        while pos < len(t) and t[pos] in _VOWELS:
            pos += 1
        if pos == vstart:
            return False  # consonant(s) with no following vowel — not VN-shaped
        saw_syllable = True
        cstart = pos
        while pos < len(t) and t[pos] not in _VOWELS:
            pos += 1
        cons = t[cstart:pos]
        if cons:
            if pos >= len(t):  # word-final coda
                if cons not in _VALID_FINAL:
                    return False
            elif len(cons) >= 2:  # cluster: first char must be a legal coda
                if cons[0] not in _VALID_FINAL_HEAD and cons[:2] not in ("NG", "NH", "CH"):
                    return False
                pos = cstart + 1
            else:
                pos = cstart  # single intervocalic consonant -> next onset
    return saw_syllable


def is_vietnamese(text: str | None) -> bool:
    """Heuristic: does this mark read as Vietnamese?

    Diacritic signal OR every token parsing as VN syllable(s). Deliberately
    coarse on the phonotactic side (some foreign brands look VN-syllabic) — a
    false-positive only changes the 30% phonetic encoder, never the 70%
    raw-JW backbone. Empty/blank -> False.
    """
    if not text or not text.strip():
        return False
    if _has_vn_diacritic(text):
        return True
    tokens = " ".join(text.upper().split()).split()
    return bool(tokens) and all(_is_vn_token(tok) for tok in tokens)
