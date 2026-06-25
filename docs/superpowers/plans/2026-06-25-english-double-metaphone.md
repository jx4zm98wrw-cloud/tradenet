# English Double Metaphone (Track 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the conflict engine's non-Vietnamese phonetic encoder from single Metaphone to vendored Double Metaphone, so alternate-pronunciation marks (THOMAS/TOMAS, CAESAR/SEZAR, JOAQUIN/WAKEEN) score correctly on the 30% phonetic sub-component.

**Architecture:** A vendored pure-Python `tm_similarity/double_metaphone.py` (BSD-3, no new external dependency) exposes `double_metaphone(word) -> (primary, secondary)`. `phonetic.py:phonetic_similarity` routes ONLY its non-VN (else) branch to Double Metaphone, comparing each token's 1–2 code-set via best-pair max-cross-product Jaro-Winkler. The VN branch (Track 2), the 70% raw-JW, and the length dampener are byte-for-byte unchanged. Schema-free.

**Tech Stack:** Python 3, stdlib, `jellyfish` (already a dep, for Jaro-Winkler). pytest. No new runtime dependency.

**Spec:** [`docs/superpowers/specs/2026-06-25-english-double-metaphone-design.md`](../specs/2026-06-25-english-double-metaphone-design.md)

**Branch:** `track3a-double-metaphone` (already checked out; spec already committed here).

---

## Pre-flight (read once, do not skip)

- **Working directory for all commands:** `app/backend`. Activate the venv: `source /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet/app/.venv/bin/activate` (the `cd` and `source` must be in the SAME Bash call — cwd persists between calls but a fresh shell loses the venv).
- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` **explicit paths only** — never `git add -A`/`.`/`-u`.
- **Targeted pytest only** — never the full suite (it resets the live `domestic_sweep_control` singleton). Name the specific test file/node.
- All calibration/golden values below are **prototype-verified** against the merged Track 2 engine + the BSD `metaphone==0.6` reference. They are real, not illustrative.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tm_similarity/double_metaphone.py` | **Create (vendor)** | BSD-3 pure-Python Double Metaphone (Andrew Collins et al.) consolidated into one module + a typed `double_metaphone(word)` wrapper. Stdlib only. |
| `tm_similarity/phonetic.py` | Modify | Add `_codeset` + `_best_pair_codeset_jw`; route the non-VN branch to Double Metaphone; drop `jellyfish.metaphone` from `phonetic_similarity`. |
| `tm_similarity/__init__.py` | Modify | Bump `SIMILARITY_VERSION` `"1.2"→"1.3"`; export `double_metaphone`. |
| `tests/test_double_metaphone.py` | **Create** | Reference-table unit test for the vendored module (the correctness gate) + the routing test. |
| `tests/test_double_metaphone_calibration.py` | **Create** | Committed non-VN confusion set (DM lifts + NIKE/ADIDAS guard). |
| `tests/fixtures/similarity_golden.json` | Modify | Regenerate `phonetic[1]` (`Gemy/KAVIN SAVING POWER`) `0.0→0.019` — now non-empty under DM. All other axes byte-identical. |
| `CLAUDE.md` | Modify | Extend the phonetic-axis note: non-VN now Double Metaphone, version 1.3, accepted precision trade-off. |

---

## Task 1: Vendor the Double Metaphone module

**Files:**
- Create: `tm_similarity/double_metaphone.py`
- Test: `tests/test_double_metaphone.py`

Vendor the BSD-3-licensed `metaphone` 0.6 implementation (Lawrence Philips' algorithm, Python port by Andrew Collins et al.) into a single stdlib-only module, retaining the license, and expose a typed wrapper. The reference-table test is the correctness gate — it FAILS if the vendored copy is wrong, regardless of how the source was obtained.

- [ ] **Step 1: Write the failing reference-table test**

Create `tests/test_double_metaphone.py`:

```python
"""Vendored Double Metaphone reference-table gate (Track 3a).

These expected codes are the BSD `metaphone` 0.6 reference outputs, captured at
design time. The vendored module must reproduce them exactly.
"""

from __future__ import annotations

import pytest

from tm_similarity.double_metaphone import double_metaphone

# word -> (primary, secondary)  — verified against metaphone==0.6
REFERENCE = {
    "THOMAS": ("TMS", ""),
    "TOMAS": ("TMS", ""),
    "CAESAR": ("SSR", ""),
    "SEZAR": ("SSR", ""),
    "JOAQUIN": ("JKN", "AKN"),
    "WAKEEN": ("AKN", "FKN"),
    "MACHARIA": ("MKR", ""),
    "MAKARIA": ("MKR", ""),
    "SCHNEIDER": ("XNTR", "SNTR"),
    "SNYDER": ("SNTR", "XNTR"),
    "SMITH": ("SM0", "XMT"),
    "SCHMIDT": ("XMT", "SMT"),
    "NIKE": ("NK", ""),
    "ADIDAS": ("ATTS", ""),
    "XAVIER": ("SF", "SFR"),
    "KNIGHT": ("NT", ""),
    "WRIGHT": ("RT", ""),
    "PSYCHOLOGY": ("SXLJ", "SKLK"),
    "GIOVANNI": ("JFN", "KFN"),
    "CIABATTA": ("SPT", "XPT"),
    "GEMY": ("JM", "KM"),
    "KAVIN": ("KFN", ""),
    "SAVING": ("SFNK", ""),
    "POWER": ("PR", ""),
    "SULFANI": ("SLFN", ""),
    "VIET": ("FT", ""),
}


@pytest.mark.parametrize("word, expected", REFERENCE.items())
def test_reference_codes(word, expected):
    assert double_metaphone(word) == expected


def test_empty_and_nonalpha():
    assert double_metaphone("") == ("", "")
    assert double_metaphone("   ") == ("", "")
    assert double_metaphone("123") == ("", "")
    assert double_metaphone(None) == ("", "")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_double_metaphone.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tm_similarity.double_metaphone'`.

- [ ] **Step 3: Vendor the source into `tm_similarity/double_metaphone.py`**

Obtain the BSD-3 `metaphone` 0.6 source deterministically (from `app/backend`, venv active):

```bash
python -m pip download metaphone==0.6 --no-deps --no-binary :all: -d /tmp/dm_src
tar -xzf /tmp/dm_src/metaphone-0.6.tar.gz -C /tmp/dm_src
ls /tmp/dm_src/metaphone-0.6/metaphone/   # -> metaphone.py, word.py, __init__.py, ...
```

Create `tm_similarity/double_metaphone.py` by consolidating the upstream `word.py` (the small `Word` helper class) and `metaphone.py` (the `DoubleMetaphone` class + `doublemetaphone` function) into ONE module — paste `word.py`'s `Word` class first, then `metaphone.py`'s body with its `from .word import Word` line removed (Word is now in-module). Keep the upstream module docstring. Prepend this license header block ABOVE everything (BSD-3 requires retaining the copyright notice):

```python
"""Vendored Double Metaphone (Track 3a) — phonetic encoder for non-Vietnamese marks.

Vendored verbatim from the BSD-3-licensed `metaphone` package, version 0.6
(https://github.com/oubiwann/metaphone / PyPI `metaphone==0.6`), consolidating
its `word.py` (Word helper) and `metaphone.py` (DoubleMetaphone) into this one
stdlib-only module. We vendor rather than depend so `tm_similarity` stays
dependency-light (stdlib + jellyfish). Algorithm: Lawrence Philips, "The Double
Metaphone Search Algorithm," C/C++ Users Journal 18(6), 2000.

BSD-3 license (retained per its terms):

    Copyright (c) 2007 Andrew Collins, Chris Leong
    Copyright (c) 2009 Matthew Somerville
    Copyright (c) 2010 Maximillian Dornseif, Richard Barran
    Copyright (c) 2012 Duncan McGreggor
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:
      * Redistributions of source code must retain the above copyright notice,
        this list of conditions and the following disclaimer.
      * Redistributions in binary form must reproduce the above copyright
        notice, this list of conditions and the following disclaimer in the
        documentation and/or other materials provided with the distribution.
      * Neither the name "Metaphone" nor the names of its contributors may be
        used to endorse or promote products derived from this software without
        specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
    ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
    LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
    CONSEQUENTIAL DAMAGES HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY ARISING
    IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.
"""

from __future__ import annotations
```

Then, at the END of the module, add the typed public wrapper (the engine's entry point):

```python
def double_metaphone(word: str | None) -> tuple[str, str]:
    """Return the (primary, secondary) Double Metaphone codes for one word.

    Thin typed wrapper over the vendored `doublemetaphone`. Empty/blank/
    non-alphabetic input returns ("", ""). The secondary code is "" when the
    word has no alternate pronunciation.
    """
    if not word or not word.strip():
        return ("", "")
    primary, secondary = doublemetaphone(word)
    return (primary, secondary)
```

Notes for the implementer:
- The upstream `doublemetaphone(input)` calls `DoubleMetaphone().parse(input)` and returns a 2-tuple. Do not alter the algorithm body — vendor it verbatim so the reference table matches.
- If upstream uses `from __future__ import unicode_literals` or Python-2 idioms, they are harmless under Python 3; keep them or drop `unicode_literals` (Py3 strings are already unicode). Do NOT otherwise edit the algorithm.
- Remove the now-redundant `from .word import Word` import (Word is defined in-module above).

- [ ] **Step 4: Run the reference-table test to verify it passes**

Run: `pytest tests/test_double_metaphone.py::test_reference_codes tests/test_double_metaphone.py::test_empty_and_nonalpha -q`
Expected: PASS (26 reference rows + empty-input case). If any row mismatches, the vendored copy is wrong — re-copy verbatim; do not "fix" the algorithm to match.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tm_similarity/double_metaphone.py app/backend/tests/test_double_metaphone.py
git commit -m "feat(similarity): vendor BSD-3 Double Metaphone module + reference-table gate"
```

---

## Task 2: Route the non-VN branch to Double Metaphone

**Files:**
- Modify: `tm_similarity/phonetic.py` (add helpers; edit `phonetic_similarity` else-branch)
- Modify: `tm_similarity/__init__.py` (version + export)
- Test: `tests/test_double_metaphone.py` (append routing test)

Each non-VN token → its 1–2 non-empty DM codes; token-pair similarity = max JW over the code-set cross-product; best-pair across tokens. VN branch and the 70% blend unchanged.

- [ ] **Step 1: Write the failing routing test**

Append to `tests/test_double_metaphone.py`:

```python
import tm_similarity as t
from tm_similarity.phonetic import phonetic_similarity


def test_non_vn_pair_uses_double_metaphone():
    # THOMAS/TOMAS: single Metaphone gave 0.898; DM primary handles TH->T -> 0.965.
    assert phonetic_similarity("THOMAS", "TOMAS") >= 0.95
    # JOAQUIN/WAKEEN: the secondary code AKN matches across sets (0.611 -> 0.678).
    assert phonetic_similarity("JOAQUIN", "WAKEEN") >= 0.66


def test_vn_pair_unchanged_by_track3a():
    # VN pair still routes to the Track-2 VN key — identical to its 1.2 value.
    assert phonetic_similarity("TRANG", "CHANG") == 0.813


def test_version_and_export():
    assert t.SIMILARITY_VERSION == "1.3"
    assert t.double_metaphone("THOMAS") == ("TMS", "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_double_metaphone.py -k "non_vn or unchanged or version_and_export" -q`
Expected: FAIL — `test_non_vn_pair_uses_double_metaphone` (single MP gives 0.898 < 0.95), `test_version_and_export` (still "1.2"; `t.double_metaphone` AttributeError).

- [ ] **Step 3a: Add the comparison helpers to `tm_similarity/phonetic.py`**

Add the import after the existing `from .vn_phonetic import is_vietnamese, vn_phonetic_key`:

```python
from .double_metaphone import double_metaphone
```

Add these two helpers immediately ABOVE `phonetic_similarity` (after `_token_jw`):

```python
def _codeset(token: str) -> tuple[str, ...]:
    """The 1–2 non-empty Double Metaphone codes for a token, else ("",).

    The secondary code captures an alternate pronunciation (THOMAS/TOMAS share
    a primary; JOAQUIN/WAKEEN match only via the secondary). Empty fallback
    keeps the token in the best-pair denominator without ever matching.
    """
    return tuple(c for c in double_metaphone(token) if c) or ("",)


def _best_pair_codeset_jw(short: list[tuple[str, ...]], long: list[tuple[str, ...]]) -> float:
    """Greedy best-pairing JW between two lists of DM code-sets.

    Mirrors `_best_pair_jw` (average over the longer list so unpaired tokens
    drag the score down) but each token is a code-SET: the per-pair score is
    the MAX Jaro-Winkler over the cross-product of the two sets, so an alternate
    pronunciation on either side can match.
    """
    if not short or not long:
        return 0.0
    used = [False] * len(long)
    pair_scores: list[float] = []
    for a_codes in short:
        best, best_idx = 0.0, -1
        for i, b_codes in enumerate(long):
            if used[i]:
                continue
            s = max(jellyfish.jaro_winkler_similarity(x, y) for x in a_codes for y in b_codes)
            if s > best:
                best, best_idx = s, i
        if best_idx >= 0:
            used[best_idx] = True
        pair_scores.append(best)
    return sum(pair_scores) / len(long)
```

- [ ] **Step 3b: Edit the else-branch of `phonetic_similarity`**

Replace the current routed block (from the `if is_vietnamese(a) and is_vietnamese(b):` line through the final `return round((0.7 * raw + 0.3 * phon) * length_factor, 3)`) with:

```python
    # 30% phonetic component, language-routed. Vietnamese -> VN key (Track 2);
    # otherwise vendored Double Metaphone (Track 3a). DM emits a (primary,
    # secondary) pair, so each token is a code-SET and the per-pair score is the
    # best cross-product JW — catching alternate pronunciations (THOMAS/TOMAS,
    # JOAQUIN/WAKEEN) single Metaphone collapsed wrong.
    if is_vietnamese(a) and is_vietnamese(b):
        a_codes = [k for k in (vn_phonetic_key(tok) for tok in _tokens(na)) if k]
        b_codes = [k for k in (vn_phonetic_key(tok) for tok in _tokens(nb)) if k]
        if not a_codes or not b_codes:
            return round(raw * length_factor, 3)
        short, long = (a_codes, b_codes) if len(a_codes) <= len(b_codes) else (b_codes, a_codes)
        phon = _best_pair_jw(short, long)
    else:
        a_sets = [_codeset(tok) for tok in _tokens(na)]
        b_sets = [_codeset(tok) for tok in _tokens(nb)]
        if not a_sets or not b_sets:
            return round(raw * length_factor, 3)
        short_s, long_s = (a_sets, b_sets) if len(a_sets) <= len(b_sets) else (b_sets, a_sets)
        phon = _best_pair_codeset_jw(short_s, long_s)

    return round((0.7 * raw + 0.3 * phon) * length_factor, 3)
```

Update the `phonetic_similarity` docstring's "Phonetic-code JW (30% weight)" bullet — replace it with:

```python
      - Phonetic-code JW (30% weight) — best-pair scheme on a phonetic code per
        token. Vietnamese marks use the VN key (vn_phonetic_key); all others use
        vendored Double Metaphone, comparing each token's (primary, secondary)
        code-set by best cross-product JW. Catches GIA/DA (VN /z/ merger) and
        THOMAS/TOMAS, JOAQUIN/WAKEEN (English alternate pronunciations).
```

> The VN branch now early-returns on empty codes itself (it previously shared the post-block guard). This is behaviour-equivalent — a VN pair with empty keys already returned `raw * length_factor`.

- [ ] **Step 3c: Edit `tm_similarity/__init__.py`**

Add the export import after the `from .vn_phonetic import ...` line:

```python
from .double_metaphone import double_metaphone
```

Bump the version:

```python
SIMILARITY_VERSION = "1.3"
```

Add `"double_metaphone"` to `__all__` (keep it sorted — it goes just before `"is_vietnamese"`):

```python
    "composite_score",
    "double_metaphone",
    "is_vietnamese",
```

- [ ] **Step 4: Run the routing test to verify it passes**

Run: `pytest tests/test_double_metaphone.py -q`
Expected: PASS (reference table + empty + 3 routing tests).

- [ ] **Step 5: Commit**

```bash
git add app/backend/tm_similarity/phonetic.py app/backend/tm_similarity/__init__.py app/backend/tests/test_double_metaphone.py
git commit -m "feat(similarity): route non-VN phonetic to Double Metaphone; bump SIMILARITY_VERSION 1.3"
```

---

## Task 3: Calibration set + golden update

**Files:**
- Create: `tests/test_double_metaphone_calibration.py`
- Modify: `tests/fixtures/similarity_golden.json` (`phonetic[1]` only)
- Test: re-run `tests/test_tm_similarity_engine.py`

- [ ] **Step 1: Write the calibration test**

Create `tests/test_double_metaphone_calibration.py`:

```python
"""Committed non-VN (English) aural-confusion calibration set (Track 3a).

Asserts Double Metaphone lifts documented alternate-pronunciation pairs above
single Metaphone, and does NOT over-merge a realistic non-confusable pair.
Values verified at design time (single MP -> DM).
"""

from __future__ import annotations

import pytest

from tm_similarity.phonetic import phonetic_similarity

# (a, b, floor) — alternate-pronunciation pairs DM should flag. Floors sit just
# below the verified DM score; each is strictly above its single-Metaphone value
# (THOMAS/TOMAS 0.898->0.965, CAESAR/SEZAR 0.646->0.712, JOAQUIN/WAKEEN 0.611->0.678).
HIGH_CONFUSION = [
    ("THOMAS", "TOMAS", 0.95),
    ("CAESAR", "SEZAR", 0.70),
    ("JOAQUIN", "WAKEEN", 0.66),
]

# (a, b, ceiling) — realistic non-confusable English pair must stay low.
# NIKE/ADIDAS = 0.275 under both single MP and DM (encoder swap doesn't inflate it).
LOW_CONFUSION = [
    ("NIKE", "ADIDAS", 0.40),
]


@pytest.mark.parametrize("a, b, floor", HIGH_CONFUSION)
def test_high_confusion_pairs_flagged(a, b, floor):
    assert phonetic_similarity(a, b) >= floor


@pytest.mark.parametrize("a, b, ceiling", LOW_CONFUSION)
def test_low_confusion_pairs_not_over_merged(a, b, ceiling):
    assert phonetic_similarity(a, b) < ceiling
```

- [ ] **Step 2: Run the calibration test (pass) and the golden test (fail)**

Run: `pytest tests/test_double_metaphone_calibration.py -q`
Expected: PASS (4 cases).

Run: `pytest tests/test_tm_similarity_engine.py::test_phonetic_matches_golden -q`
Expected: FAIL — got `[1.0, 0.019, 0.556, 0.911, 0.0, 0.67]` vs golden `[1.0, 0.0, ...]`. Only index 1 (`Gemy/KAVIN SAVING POWER`) differs: single MP gave the multi-word pair 0.0; DM gives a hair of code signal → 0.019.

- [ ] **Step 3: Update the golden fixture**

In `tests/fixtures/similarity_golden.json`, change the `phonetic` array's 2nd value (index 1) from `0.0` to `0.019`. The full `phonetic` block becomes:

```json
  "phonetic": [
    1.0,
    0.019,
    0.556,
    0.911,
    0.0,
    0.67
  ],
```

Leave `class`, `vienna`, and `composite` **byte-identical** (frozen axes).

- [ ] **Step 4: Run golden + calibration to verify green**

Run: `pytest tests/test_tm_similarity_engine.py tests/test_double_metaphone_calibration.py -q`
Expected: PASS (golden phonetic/class/vienna/composite match; calibration green).

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_double_metaphone_calibration.py app/backend/tests/fixtures/similarity_golden.json
git commit -m "test(similarity): non-VN DM calibration set; regen Gemy golden (0.0->0.019)"
```

---

## Task 4: Verify search rerank + CI gates + docs sync

**Files:**
- Modify: `CLAUDE.md`
- Verify: `tests/test_search_phonetic_two_stage.py`

- [ ] **Step 1: Verify the search rerank test is unaffected**

Run: `pytest tests/test_search_phonetic_two_stage.py -q`
Expected: PASS. If a non-VN query's ranking shifted to a new (intended) order, update the expectation explicitly — do not silently weaken the assertion.

- [ ] **Step 2: Run the CI gates locally over the changed package**

Run (from `app/backend`, venv active):
```bash
ruff check tm_similarity tests/test_double_metaphone.py tests/test_double_metaphone_calibration.py
ruff format --check tm_similarity/double_metaphone.py tm_similarity/phonetic.py tm_similarity/__init__.py tests/test_double_metaphone.py tests/test_double_metaphone_calibration.py
mypy tm_similarity
```
Expected: all clean. Run BOTH `ruff check` AND `ruff format --check` — they are separate gates (a Track 2 CI failure came from skipping `ruff format`). Note: the vendored `double_metaphone.py` may carry upstream style ruff flags (e.g. long lines, archaic idioms); apply `ruff format tm_similarity/double_metaphone.py` and, if `ruff check` flags vendored-algorithm constructs that shouldn't be rewritten, add a per-file ignore in `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` for `tm_similarity/double_metaphone.py` (vendored code — minimal edits). Prefer `ruff format` + targeted ignores over rewriting the algorithm. If mypy flags the untyped vendored body, a per-module `[[tool.mypy.overrides]]` with `disable_error_code` for `tm_similarity.double_metaphone` is acceptable (vendored code); the typed `double_metaphone` wrapper keeps the public surface clean.

- [ ] **Step 3: Run the full Track 3a test surface (targeted)**

Run: `pytest tests/test_double_metaphone.py tests/test_double_metaphone_calibration.py tests/test_tm_similarity_engine.py tests/test_vn_phonetic.py tests/test_vn_phonetic_routing.py tests/test_search_phonetic_two_stage.py -q`
Expected: PASS (DM surface + frozen golden + Track 2 VN tests still green + search rerank).

- [ ] **Step 4: Docs sync — extend the phonetic-axis note in `CLAUDE.md`**

In `CLAUDE.md`, in the "### Phonetic axis routing (Track 2)" subsection, the sentence currently reads "Non-VN pairs keep the single-Metaphone path unchanged (Double Metaphone deferred to Track 3)." Replace that sentence with:

```markdown
Non-VN pairs use vendored **Double Metaphone** (Track 3a — BSD-3
`tm_similarity/double_metaphone.py`, no new dependency): each token's
`(primary, secondary)` code-set is compared by best cross-product JW, catching
alternate-pronunciation marks single Metaphone collapsed wrong (THOMAS/TOMAS
0.90→0.97, CAESAR/SEZAR 0.65→0.71, JOAQUIN/WAKEEN 0.61→0.68). This trades a
little precision on spelling-similar short pairs (the 70% raw-JW stays dominant
and the verdict guards gate any lone phonetic bump). SIMILARITY_VERSION is 1.3.
```

(The Track 2 note's `SIMILARITY_VERSION is 1.2.` line is superseded by this 1.3 statement; leave the rest of the Track 2 paragraph intact.)

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: non-VN phonetic now Double Metaphone (Track 3a, SIMILARITY_VERSION 1.3)"
```

---

## Self-Review (completed at plan-authoring time)

**Spec coverage** — every spec section maps to a task:
- §1 vendored `double_metaphone.py` (BSD-3, stdlib, wrapper) → Task 1.
- §2 comparison `_codeset` / `_best_pair_codeset_jw` (max cross-product) → Task 2.
- §3 routing edit (non-VN branch only; remove `jellyfish.metaphone`) → Task 2.
- §Versioning (`1.2→1.3`, export `double_metaphone`) → Task 2.
- §Testing 1–5 (reference-table gate, calibration with strictly-greater + NIKE/ADIDAS guard, routing + VN-unchanged, golden regen index 1, search rerank) → Tasks 1/2/3/4.
- §Out-of-scope (no weight/composite change, no semantic axis, no VN change, no comparison redesign, no new dep, no schema) → respected: no `composite.py`/`DEFAULT_WEIGHTS`/`vn_phonetic.py`/migration/frontend touched.
- §Docs sync (CLAUDE.md) → Task 4.

**Placeholder scan** — none. The vendored source is a copy operation gated by the exact reference table (the airtight correctness check); all engine-value code (wrapper, helpers, routing, tests, golden) is concrete and prototype-verified.

**Type/name consistency** — `double_metaphone`, `_codeset`, `_best_pair_codeset_jw` used consistently across Tasks 1–2. `_tokens`, `_best_pair_jw`, `_PHONETIC_LENGTH_TOLERANCE`, `is_vietnamese`, `vn_phonetic_key` match the current `phonetic.py` API. Golden value `0.019` (index 1) and calibration floors (0.95/0.70/0.66) and ceiling (0.40) match the verified prototype.

**Verified at design time (venv prototype vs `metaphone==0.6`):** reference table (26 words), calibration (THOMAS/TOMAS 0.965, CAESAR/SEZAR 0.712, JOAQUIN/WAKEEN 0.678, NIKE/ADIDAS 0.275), VN-unchanged (TRANG/CHANG 0.813), and the single golden delta (`phonetic[1]` 0.0→0.019).
