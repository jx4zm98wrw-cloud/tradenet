# VN Phonetic Axis (Track 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the conflict engine's phonetic axis catch Vietnamese aural confusion (GIA HƯNG/DA HƯNG, TRANG/CHANG) that English-Metaphone is blind to, by adding a pure-stdlib Vietnamese phonetic key routed in for VN-vs-VN comparisons.

**Architecture:** A new pure module `tm_similarity/vn_phonetic.py` (`re`/`unicodedata` only) exposes `is_vietnamese(text)` and `vn_phonetic_key(token)`. `phonetic.py:phonetic_similarity` routes ONLY its 30% phonetic component to the VN key when both marks read as Vietnamese; the 70% raw-JW and length dampener are byte-for-byte unchanged. Schema-free — no column, migration, backfill, or ingest wiring. Pair-level route (both VN) mirrors Track 1's "both figurative" gate.

**Tech Stack:** Python 3, stdlib `re`/`unicodedata`, `jellyfish` (already a dep). pytest. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-06-25-vn-phonetic-axis-design.md`](../specs/2026-06-25-vn-phonetic-axis-design.md)

**Branch:** `track2-vn-phonetic` (already checked out; spec already committed here).

---

## Pre-flight (read once, do not skip)

- **Working directory for all commands:** `app/backend` (the editable-installed package root). Activate the venv first: `source app/.venv/bin/activate` from the repo root, or `source ../.venv/bin/activate` from `app/backend`.
- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). They are permanently modified-in-worktree. `git add` **explicit paths only** — never `git add -A`/`.`/`-u`.
- **Targeted pytest only.** Running the full suite resets the live `domestic_sweep_control` singleton (a running sweep). Always name the test file/node.
- All key code in this plan has been **prototyped and verified** against the calibration set — the values in the test steps are real, not illustrative.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tm_similarity/vn_phonetic.py` | **Create** | `is_vietnamese` (detector) + `vn_phonetic_key` (onset–glide–nucleus–coda key, Northern merges, toneless). Pure `re`/`unicodedata`. |
| `tm_similarity/phonetic.py` | Modify | Route the 30% component to the VN key when both marks are VN. Only `phonetic_similarity` changes. |
| `tm_similarity/__init__.py` | Modify | Bump `SIMILARITY_VERSION` `"1.1"→"1.2"`; export `is_vietnamese`, `vn_phonetic_key`. |
| `tests/test_vn_phonetic.py` | **Create** | Unit tests for `vn_phonetic_key` (merge equivalences, glide, coda) and `is_vietnamese`. |
| `tests/test_vn_phonetic_routing.py` | **Create** | Routing test: VN pair uses VN key (beats Metaphone); foreign pair unchanged. |
| `tests/test_vn_phonetic_calibration.py` | **Create** | Committed labelled VN confusion set + the toneless over-merge early-warning. |
| `tests/fixtures/similarity_golden.json` | Modify | Regenerate `phonetic[3]` (`Taseko/Tabeko`) `0.878→0.911` — now VN-routed. All other axes byte-identical. |
| `CLAUDE.md` | Modify | Add the Track 2 phonetic-axis note (Northern/toneless scope, version 1.2). |

> **Why `Taseko/Tabeko` changes:** these fixtures parse as VN-shaped syllables (`TA·SE·KO`), so they now route through the VN key. This is *within* frozen-axis discipline — the spec freezes visual/class/vienna and regenerates phonetic values **for VN-routed pairs only**, and this pair is now VN-routed. Visual/class/vienna/composite golden rows stay byte-identical (composite uses hardcoded inputs, not `phonetic_similarity`).

---

## Task 1: `vn_phonetic_key` — the onset–glide–nucleus–coda key

**Files:**
- Create: `tm_similarity/vn_phonetic.py`
- Test: `tests/test_vn_phonetic.py`

Build the key-generator first (the detector in Task 2 reuses its onset/coda tables). The key operates on a **normalised** token (diacritic-stripped, uppercased — as produced by `phonetic.normalize_vn`). It greedy-parses `(C1)(w)V(G|C2)` per syllable, looping across multi-syllable tokens (`LAKA` → `la`+`ka`), and emits a compact phoneme-code string. Northern Hanoi merges (Kirby 2011 JIPA): `c/k/q→/k/`, `d/gi/r→/z/`, `ch/tr→/tɕ/`, `s/x→/s/`, `ng/ngh→/ŋ/`, `g/gh→/ɣ/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vn_phonetic.py`:

```python
"""Unit tests for the Vietnamese phonetic key + language detector (Track 2)."""

from __future__ import annotations

from tm_similarity.vn_phonetic import vn_phonetic_key


def test_northern_z_merger_gia_d_r():
    # d / gi / r all merge to /z/ in Hanoi phonology (Kirby 2011).
    assert vn_phonetic_key("GIA") == vn_phonetic_key("DA") == vn_phonetic_key("RA")


def test_northern_affricate_merger_ch_tr():
    # ch / tr both /tɕ/.
    assert vn_phonetic_key("TRANG") == vn_phonetic_key("CHANG")


def test_northern_sibilant_merger_s_x():
    assert vn_phonetic_key("SA") == vn_phonetic_key("XA")


def test_velar_onset_merger_c_k_q():
    assert vn_phonetic_key("CA") == vn_phonetic_key("KA") == vn_phonetic_key("QA")


def test_qu_medial_glide():
    # QU- carries the /w/ on-glide: QUANG keeps a glide slot CANG lacks.
    assert vn_phonetic_key("QUANG") != vn_phonetic_key("CANG")
    assert "w" in vn_phonetic_key("QUANG")


def test_offglide_coda_i_becomes_j():
    # MAI / MAY share the /j/ off-glide coda.
    assert vn_phonetic_key("MAI") == vn_phonetic_key("MAY")
    assert vn_phonetic_key("MAI").endswith("j")


def test_final_consonant_codas():
    # ng -> /ŋ/=q ; c/ch -> /k/ codas.
    assert vn_phonetic_key("TRANG").endswith("q")
    assert vn_phonetic_key("AC").endswith("k")
    assert vn_phonetic_key("ACH").endswith("k")


def test_multi_syllable_token():
    # LAKA parses as two syllables la.ka (maximal onset).
    assert vn_phonetic_key("LAKA") == "laka"
    # LACCA splits the cluster: lac.ca.
    assert vn_phonetic_key("LACCA") == "lakka"


def test_empty_and_nonalpha():
    assert vn_phonetic_key("") == ""
    assert vn_phonetic_key("123") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vn_phonetic.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tm_similarity.vn_phonetic'`.

- [ ] **Step 3: Create `tm_similarity/vn_phonetic.py` with `vn_phonetic_key`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vn_phonetic.py -q`
Expected: PASS (the 9 key tests; `is_vietnamese` is added in Task 2). All `vn_phonetic_key` tests green.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tm_similarity/vn_phonetic.py app/backend/tests/test_vn_phonetic.py
git commit -m "feat(similarity): vn_phonetic_key — Northern-VN onset/glide/nucleus/coda key"
```

---

## Task 2: `is_vietnamese` — language detector

**Files:**
- Modify: `tm_similarity/vn_phonetic.py` (append the detector + its private helpers)
- Test: `tests/test_vn_phonetic.py` (append detector tests)

The detector reads the **original** (diacritic-bearing) text — `phonetic_similarity` passes it the un-normalised string so the diacritic signal survives. Two OR'd signals: (1) any Vietnamese-specific letter/tone mark; (2) phonotactic fallback — every whitespace token parses cleanly as one-or-more VN syllables. It reuses Task 1's `_ONSETS`/`_VOWELS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vn_phonetic.py`:

```python
from tm_similarity.vn_phonetic import is_vietnamese


def test_detector_diacritics_true():
    assert is_vietnamese("GIA HƯNG") is True
    assert is_vietnamese("CÔNG TY DƯỢC") is True


def test_detector_toneless_valid_syllables_true():
    assert is_vietnamese("GIA HUNG") is True
    assert is_vietnamese("TRANG") is True
    assert is_vietnamese("BAO LONG") is True


def test_detector_foreign_false():
    # L is not a legal VN coda; PP is not a legal onset/coda cluster.
    assert is_vietnamese("MAYBELLINE") is False
    assert is_vietnamese("APPLE") is False


def test_detector_empty_false():
    assert is_vietnamese("") is False
    assert is_vietnamese(None) is False
    assert is_vietnamese("   ") is False


def test_detector_known_coarseness_documented():
    # Some foreign brands parse as VN-syllabic (SAMSUNG = SAM.SUNG). This is
    # accepted: a mis-route only swaps the 30% encoder; the 70% raw-JW
    # dominates, so a false-positive route is low-harm (see spec §Testing).
    assert is_vietnamese("SAMSUNG") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vn_phonetic.py -k detector -q`
Expected: FAIL with `ImportError: cannot import name 'is_vietnamese'`.

- [ ] **Step 3: Append `is_vietnamese` + helpers to `tm_similarity/vn_phonetic.py`**

```python
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
```

> Note: `is_vietnamese` uppercases/splits inline (it must run on the original text, and `normalize_vn` lives in `phonetic.py` — importing it here would create a cycle since `phonetic.py` imports this module). The diacritic check runs on the raw text before casing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vn_phonetic.py -q`
Expected: PASS (all key + detector tests green).

- [ ] **Step 5: Commit**

```bash
git add app/backend/tm_similarity/vn_phonetic.py app/backend/tests/test_vn_phonetic.py
git commit -m "feat(similarity): is_vietnamese — diacritic + phonotactic VN detector"
```

---

## Task 3: Route the 30% component in `phonetic_similarity`

**Files:**
- Modify: `tm_similarity/phonetic.py` (`phonetic_similarity` only)
- Modify: `tm_similarity/__init__.py` (version + exports)
- Test: `tests/test_vn_phonetic_routing.py` (create)

Branch the 30% phonetic component: VN-vs-VN → best-pair JW on `vn_phonetic_key`s; otherwise the current Metaphone path, unchanged. The 70% raw-JW and `length_factor` are untouched.

- [ ] **Step 1: Write the failing test**

Create `tests/test_vn_phonetic_routing.py`:

```python
"""phonetic_similarity routes VN pairs through the VN key, others through Metaphone."""

from __future__ import annotations

import tm_similarity as t
from tm_similarity.phonetic import phonetic_similarity


def test_vn_pair_routes_to_vn_key_and_beats_metaphone():
    # GIA HƯNG / DA HƯNG: Metaphone scored 0.50 (GIA->"J", DA->"T"); the VN
    # key merges d/gi -> /z/, lifting the phonetic axis to ~0.65.
    assert phonetic_similarity("GIA HƯNG", "DA HƯNG") >= 0.60
    # TRANG / CHANG: Metaphone 0.73 -> VN key ~0.81.
    assert phonetic_similarity("TRANG", "CHANG") >= 0.78


def test_vn_pair_does_not_over_merge():
    # Segmentally-distinct VN pair must stay low — the toneless over-merge
    # early-warning the research called for.
    assert phonetic_similarity("BAO LONG", "MINH QUAN") < 0.50


def test_foreign_pair_unchanged_metaphone_path():
    # Neither mark is VN -> Metaphone path, identical to pre-Track-2 value.
    assert phonetic_similarity("NEUREX", "NEUROFAX") == 0.90


def test_version_bumped():
    assert t.SIMILARITY_VERSION == "1.2"


def test_new_symbols_exported():
    assert t.is_vietnamese("TRANG") is True
    assert t.vn_phonetic_key("GIA") == t.vn_phonetic_key("DA")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vn_phonetic_routing.py -q`
Expected: FAIL — `test_version_bumped` (still "1.1"), `test_new_symbols_exported` (AttributeError), and `test_vn_pair_routes…` (Metaphone path gives 0.50/0.73, below thresholds).

- [ ] **Step 3a: Edit `phonetic_similarity` in `tm_similarity/phonetic.py`**

Add the import near the top, immediately after `import jellyfish`:

```python
from .vn_phonetic import is_vietnamese, vn_phonetic_key
```

Replace the Metaphone block at the end of `phonetic_similarity` (the current lines from the `# Metaphone per token…` comment through the final `return round((0.7 * raw + 0.3 * phon) * length_factor, 3)`) with the routed version:

```python
    # 30% phonetic component, language-routed. Both marks Vietnamese -> compare
    # VN phonetic keys (same syllabic space; mirrors Track 1's "both figurative"
    # gate). Otherwise the original English-Metaphone path, unchanged. Encoding
    # per token (not the whole string) preserves word boundaries either way.
    if is_vietnamese(a) and is_vietnamese(b):
        a_codes = [k for k in (vn_phonetic_key(tok) for tok in _tokens(na)) if k]
        b_codes = [k for k in (vn_phonetic_key(tok) for tok in _tokens(nb)) if k]
    else:
        a_codes = [c for c in (jellyfish.metaphone(tok) for tok in _tokens(na)) if c]
        b_codes = [c for c in (jellyfish.metaphone(tok) for tok in _tokens(nb)) if c]
    if not a_codes or not b_codes:
        return round(raw * length_factor, 3)
    short, long = (a_codes, b_codes) if len(a_codes) <= len(b_codes) else (b_codes, a_codes)
    phon = _best_pair_jw(short, long)

    return round((0.7 * raw + 0.3 * phon) * length_factor, 3)
```

Then update the `phonetic_similarity` docstring's "Metaphone-encoded JW (30% weight)" bullet — replace that bullet with:

```python
      - Phonetic-code JW (30% weight) — same best-pair scheme on a phonetic
        code per token. The code is the Vietnamese key (vn_phonetic_key) when
        both marks read as Vietnamese, else the English Metaphone code.
        Catches sound-alikes like NEUREX/NEUROFAX (English) and GIA/DA (VN,
        Northern d/gi -> /z/ merger) where surface spellings diverge.
```

- [ ] **Step 3b: Edit `tm_similarity/__init__.py`**

Add the vn_phonetic import directly below the existing phonetic import (line 11):

```python
from .phonetic import normalize_vn, phonetic_similarity
from .vn_phonetic import is_vietnamese, vn_phonetic_key
```

Change `SIMILARITY_VERSION = "1.1"` to:

```python
SIMILARITY_VERSION = "1.2"
```

Add `"is_vietnamese"` and `"vn_phonetic_key"` into `__all__` (keep it sorted) so it reads:

```python
    "class_overlap",
    "composite_score",
    "is_vietnamese",
    "normalize_vn",
    "phonetic_similarity",
    "resolve_weights",
    "score",
    "vienna_overlap",
    "visual_similarity",
    "vn_phonetic_key",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vn_phonetic_routing.py -q`
Expected: PASS (all 5 routing tests).

- [ ] **Step 5: Commit**

```bash
git add app/backend/tm_similarity/phonetic.py app/backend/tm_similarity/__init__.py app/backend/tests/test_vn_phonetic_routing.py
git commit -m "feat(similarity): route phonetic 30% to VN key for VN pairs; bump SIMILARITY_VERSION 1.2"
```

---

## Task 4: Calibration set + golden update

**Files:**
- Create: `tests/test_vn_phonetic_calibration.py`
- Modify: `tests/fixtures/similarity_golden.json` (`phonetic[3]` only)
- Test: re-run the existing golden test `tests/test_tm_similarity_engine.py`

Commit the labelled VN confusion set as a regression artifact, then update the one golden phonetic value that intentionally moved.

- [ ] **Step 1: Write the calibration test**

Create `tests/test_vn_phonetic_calibration.py`:

```python
"""Committed VN aural-confusion calibration set (Track 2 regression guard).

Asserts the engine now scores documented VN sound-alikes as intended and does
NOT over-merge a segmentally-distinct VN pair. Values verified at design time.
"""

from __future__ import annotations

import pytest

from tm_similarity.phonetic import phonetic_similarity

# (a, b, min_expected) — should be FLAGGED as phonetically confusable.
HIGH_CONFUSION = [
    ("GIA HƯNG", "DA HƯNG", 0.60),   # Northern d/gi -> /z/  (was 0.50 under Metaphone)
    ("TRANG", "CHANG", 0.78),        # ch/tr -> /tɕ/         (was 0.73)
    ("LAKA", "LACCA", 0.80),         # IP-Vietnam short-mark case
    ("MEKO", "MECO", 0.85),          # IP-Vietnam short-mark case
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
```

- [ ] **Step 2: Run the calibration test (should pass) and the golden test (should fail)**

Run: `pytest tests/test_vn_phonetic_calibration.py -q`
Expected: PASS (5 parametrized cases).

Run: `pytest tests/test_tm_similarity_engine.py::test_phonetic_matches_golden -q`
Expected: FAIL — got `[1.0, 0.0, 0.556, 0.911, 0.0, 0.67]` vs golden `[..., 0.878, ...]`. Only index 3 (`Taseko/Tabeko`, now VN-routed) differs.

- [ ] **Step 3: Update the golden fixture**

In `tests/fixtures/similarity_golden.json`, change the `phonetic` array's 4th value (index 3) from `0.878` to `0.911`. The full `phonetic` block becomes:

```json
  "phonetic": [
    1.0,
    0.0,
    0.556,
    0.911,
    0.0,
    0.67
  ],
```

Leave `class`, `vienna`, and `composite` **byte-identical** (frozen axes — composite uses hardcoded inputs, not `phonetic_similarity`).

- [ ] **Step 4: Run the full golden + calibration suite to verify green**

Run: `pytest tests/test_tm_similarity_engine.py tests/test_vn_phonetic_calibration.py -q`
Expected: PASS (golden phonetic/class/vienna/composite all match; calibration green).

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_vn_phonetic_calibration.py app/backend/tests/fixtures/similarity_golden.json
git commit -m "test(similarity): VN confusion calibration set; regen Taseko golden (now VN-routed)"
```

---

## Task 5: Verify search rerank + full CI gates + docs sync

**Files:**
- Modify: `CLAUDE.md` (Track 2 phonetic-axis note)
- Verify: `tests/test_search_phonetic_two_stage.py`

Confirm the search two-stage rerank still passes (it calls `phonetic_similarity`), run the backend CI gates over `tm_similarity`, then sync the docs.

- [ ] **Step 1: Verify the search rerank test is unaffected**

Run: `pytest tests/test_search_phonetic_two_stage.py -q`
Expected: PASS. If a VN query's ranking shifted to a new (intended) order, update the expectation in that test to the new order — do not silently weaken the assertion. (The fixtures are English brand marks, so no shift is expected.)

- [ ] **Step 2: Run the CI gates locally over the changed package**

Run from `app/backend`:
```bash
ruff check tm_similarity tests/test_vn_phonetic.py tests/test_vn_phonetic_routing.py tests/test_vn_phonetic_calibration.py
ruff format --check tm_similarity
mypy tm_similarity
```
Expected: all clean (no lint errors, format OK, `Success: no issues found` from mypy). Fix any issues inline and re-run.

- [ ] **Step 3: Run the full similarity test set once (targeted, no sweep singleton)**

Run: `pytest tests/test_tm_similarity_engine.py tests/test_vn_phonetic.py tests/test_vn_phonetic_routing.py tests/test_vn_phonetic_calibration.py tests/test_search_phonetic_two_stage.py -q`
Expected: PASS (entire Track 2 surface + frozen golden + search rerank).

- [ ] **Step 4: Docs sync — add the Track 2 note to `CLAUDE.md`**

In `CLAUDE.md`, immediately after the "### Visual axis routing (Track 1)" subsection (which ends with `SIMILARITY_VERSION is 1.1.` and the Track 1 spec reference), insert a new subsection:

```markdown
### Phonetic axis routing (Track 2)

**Track 2 (phonetic axis):** the 30% phonetic sub-component is now
language-routed. A new pure module `tm_similarity/vn_phonetic.py` (stdlib `re`
only) adds `is_vietnamese(text)` (diacritic + phonotactic VN detector) and
`vn_phonetic_key(token)` (toneless Northern-Hanoi onset–glide–nucleus–coda key:
`c/k/q→/k/`, `d/gi/r→/z/`, `ch/tr→/tɕ/`, `s/x→/s/`, `ng/ngh→/ŋ/`; 8-segment
coda `/p t k m n ŋ j w/`; cited from Kirby 2011 JIPA / Pham 2006). When BOTH
marks read as Vietnamese, `phonetic_similarity` compares VN keys instead of
English Metaphone — catching aural confusion Metaphone is blind to (GIA HƯNG/DA
HƯNG 0.50→0.65; TRANG/CHANG 0.73→0.81). Non-VN pairs keep the single-Metaphone
path unchanged (Double Metaphone deferred to Track 3). The 70% raw-JW backbone
and length dampener are unchanged. SIMILARITY_VERSION is 1.2. **Schema-free** —
no column, migration, backfill, or ingest wiring (unlike Track 1). See
`docs/superpowers/specs/2026-06-25-vn-phonetic-axis-design.md`.
```

(Leave the Track 1 subsection's `SIMILARITY_VERSION is 1.1.` line as its historical statement; the current version lives in the new Track 2 note.)

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Track 2 VN phonetic-axis routing (SIMILARITY_VERSION 1.2)"
```

---

## Self-Review (completed at plan-authoring time)

**Spec coverage** — every spec section maps to a task:
- §1 new module `vn_phonetic.py` → Tasks 1+2.
- §2 `is_vietnamese` (diacritic + phonotactic, on original text) → Task 2.
- §3 `vn_phonetic_key` (onset/glide/nucleus/coda, Northern merges, toneless, 8-coda) → Task 1.
- §4 routing in `phonetic_similarity` (pair-level, only the 30%) → Task 3.
- §Versioning (`1.1→1.2`, exports) → Task 3.
- §Testing items 1–6 (calibration set, `is_vietnamese` units, `vn_phonetic_key` units, routing test, golden update, search rerank green) → Tasks 1/2/3/4/5.
- §Docs sync (CLAUDE.md) → Task 5.
- §Out-of-scope (no Southern, no tone, no weight change, no schema, no new dep, no Double Metaphone, no semantic/frontend) → respected: no `composite.py`/`DEFAULT_WEIGHTS`/`features.py`/migration/frontend files are touched.

**Placeholder scan** — none. All code blocks are complete and prototype-verified.

**Type/name consistency** — `vn_phonetic_key`, `is_vietnamese`, `_ONSETS`, `_VOWELS`, `_canon_coda`, `_is_vn_token`, `_has_vn_diacritic` are used consistently across Tasks 1–3. `_tokens`, `_best_pair_jw`, `normalize_vn` referenced from `phonetic.py` match its current API. Golden value `0.911` matches the verified regeneration.

**Verified at design time (venv prototype):** key equivalences (GIA=DA=RA=`za`, TRANG=CHANG=`caq`, MAI=MAY=`maj`), detector routing, calibration scores (0.65/0.813/0.865/0.907/0.443), and the single golden delta (`phonetic[3]` 0.878→0.911).
