# Confidence-aware Visual Weight (Track 3c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Boost the visual axis weight for genuine perceptual-hash (pHash) matches so a nameless figurative look-alike re-flags as "Possible conflict", without touching sound-alike recall.

**Architecture:** A single confidence-and-score-gated weight modifier inside `composite_score` (`tm_similarity/composite.py`): when `visual_confidence == "phash"` **and** the visual score is a real match (`>= PHASH_BOOST_FLOOR`), multiply the visual weight by `PHASH_VISUAL_BOOST` and renormalise the five weights for that pair. Everything below the boost block — `mark_score`, `goods_score`, `mark_strength`, `goods_factor`, verdict bands — is unchanged. No new plumbing: `visual_confidence` is already a `composite_score` parameter.

**Tech Stack:** Python 3.11, `tm_similarity` (stdlib + `jellyfish` only), pytest. No DB / migration / route / frontend change.

---

## Background the engineer needs

- **Run tests from** `app/backend` with the venv active:
  `cd app/backend && source ../.venv/bin/activate`. Run **targeted** pytest only (the full suite resets a live sweep singleton): e.g. `pytest tests/test_similarity.py -q`.
- **Spec:** `docs/superpowers/specs/2026-06-26-confidence-aware-visual-weight-design.md`.
- **The function being changed:** `tm_similarity/composite.py:composite_score(phonetic, visual, semantic, class_o, vienna_o, weights=None, visual_confidence="phash")` returns a frozen `CompositeScore(composite, verdict, verdict_tone)`.
- **Current weights:** `DEFAULT_WEIGHTS = {"phonetic": 0.35, "visual": 0.15, "semantic": 0.15, "class": 0.20, "vienna": 0.15}`.
- **All numbers below were verified** by reproducing the existing committed golden exactly, then applying the gated boost. Trust them.
- **GUARDRAILS:** NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` explicit paths only — never `-A`/`.`/`-u`. `tm_similarity` stays stdlib + jellyfish. Both ruff gates (`ruff check` AND `ruff format --check`). Do not `pnpm build` while `pnpm dev` is live (no frontend work here anyway).

## File map

| File | Change |
|---|---|
| `app/backend/tm_similarity/composite.py` | add `PHASH_VISUAL_BOOST`, `PHASH_BOOST_FLOOR`, the gated boost block (only behavioral change) |
| `app/backend/tm_similarity/__init__.py` | `SIMILARITY_VERSION` `"1.4"` → `"1.5"` |
| `app/backend/tests/test_similarity.py` | figurative-twin test flips to Possible; 4 new unit tests; refresh stale comments on 3 boosted scenario tests |
| `app/backend/tests/fixtures/similarity_golden.json` | regenerate the `composite` array (4 pHash entries change) |
| `app/backend/tests/test_double_metaphone.py` | version pin `"1.4"` → `"1.5"` |
| `app/backend/tests/test_vn_phonetic_routing.py` | version pin `"1.4"` → `"1.5"` |
| `CLAUDE.md` | Track 3c note under the visual-axis section |
| memory `similarity-track3c-confidence-aware-visual-weight.md` + `MEMORY.md` | mark Track 3c done (post-merge) |

---

### Task 1: The gated boost in `composite_score` + behavior tests

**Files:**
- Modify: `app/backend/tm_similarity/composite.py`
- Modify: `app/backend/tests/test_similarity.py`
- Modify: `app/backend/tests/fixtures/similarity_golden.json`

- [ ] **Step 1: Rewrite the figurative-twin test to expect the new verdict (failing test)**

In `app/backend/tests/test_similarity.py`, replace the whole existing function
`test_composite_figurative_phash_visual_with_shared_vienna_now_low_after_reweight` (currently asserts
`c.verdict == "Low risk"`) with:

```python
def test_composite_figurative_phash_twin_flags_possible_after_3c_boost() -> None:
    """A nameless figurative look-alike: near-identical logo (pHash 0.95) sharing
    Vienna codes, no transcribed name (phonetic/semantic 0). Under v1.4 the flat
    0.15 visual weight sank it to 0.492 (Low). Track 3c boosts a genuine pHash
    match's visual weight x2 (renormalised), lifting the composite to 0.552 ->
    Possible. Sight-only, so Possible (not Likely) is the correct severity."""
    c = composite_score(
        phonetic=0.0,
        visual=0.95,
        semantic=0.0,
        class_o=1.0,
        vienna_o=1.0,
        visual_confidence="phash",
    )
    # boosted weights (visual 0.15*2=0.30, renorm /1.15): visual 0.2609
    # mark = 0.2609*0.95 = 0.248; goods = 0.1739*1.0 + 0.1304*1.0 = 0.304
    # mark_strength 0.95 (phash) -> goods_factor 1.0; composite = 0.248 + 0.304 = 0.552
    assert c.composite == pytest.approx(0.552)
    assert c.verdict == "Possible conflict"
    assert c.verdict_tone == "warn"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_similarity.py::test_composite_figurative_phash_twin_flags_possible_after_3c_boost -q`
Expected: FAIL — current code gives `composite == 0.492`, `verdict == "Low risk"`.

- [ ] **Step 3: Add the gated boost to `composite.py`**

In `app/backend/tm_similarity/composite.py`, add the two constants immediately after the
`DEFAULT_WEIGHTS` docstring block (after line ~12):

```python
PHASH_VISUAL_BOOST = 2.0
PHASH_BOOST_FLOOR = 0.50
"""Track 3c: a genuine perceptual (pHash) *match* is independent evidence and is
weighted more than a text-derived typographic visual. Boost the visual weight only
when the visual signal is a pHash comparison AND that comparison actually matched
(`visual >= PHASH_BOOST_FLOOR`), then renormalise the five weights for this pair.
Gating on the score (not just confidence) matters: boosting a low-scoring visual
axis would steal weight from phonetic and dilute a strong name match."""
```

Then, in `composite_score`, replace the single line `w = weights or DEFAULT_WEIGHTS` (currently
line ~111) with:

```python
    w = weights or DEFAULT_WEIGHTS
    if visual_confidence == "phash" and visual >= PHASH_BOOST_FLOOR:
        # Real perceptual match: weight the independent visual evidence higher,
        # then renormalise. Copy first — never mutate the caller's / module-global dict.
        w = dict(w)
        w["visual"] *= PHASH_VISUAL_BOOST
        total = sum(w.values())
        w = {k: v / total for k, v in w.items()}
```

Leave everything after it (`mark_score`, `goods_score`, `mark_strength`, `goods_factor`, verdict
bands) byte-identical.

- [ ] **Step 4: Run the figurative-twin test — now passes**

Run: `pytest tests/test_similarity.py::test_composite_figurative_phash_twin_flags_possible_after_3c_boost -q`
Expected: PASS.

- [ ] **Step 5: Add the four guard/behavior unit tests**

Append to `app/backend/tests/test_similarity.py` (these protect the design's invariants):

```python
def test_phash_below_floor_does_not_boost_or_dilute() -> None:
    """A pHash comparison that did NOT match (visual < PHASH_BOOST_FLOOR) must not
    boost the visual weight — otherwise it would steal weight from phonetic. A pair
    with a strong name (phonetic 1.0) but dissimilar logos (visual 0.0, phash) keeps
    its v1.4 composite."""
    c = composite_score(
        phonetic=1.0, visual=0.0, semantic=0.0, class_o=1.0, vienna_o=0.0, visual_confidence="phash"
    )
    # visual 0.0 < 0.50 floor -> no boost -> v1.4 weights:
    # mark = 0.35*1.0 = 0.35; goods = 0.20*1.0 = 0.20; composite = 0.55
    assert c.composite == pytest.approx(0.55)
    assert c.verdict == "Possible conflict"


def test_phash_boost_does_not_mutate_default_weights() -> None:
    """The boost copies weights before scaling; DEFAULT_WEIGHTS (the module global
    used when weights is None) must be unchanged after a phash score."""
    before = dict(DEFAULT_WEIGHTS)
    composite_score(
        phonetic=0.0, visual=0.95, semantic=0.0, class_o=1.0, vienna_o=0.0, visual_confidence="phash"
    )
    assert DEFAULT_WEIGHTS == before
    assert DEFAULT_WEIGHTS["visual"] == 0.15


def test_phash_boost_composes_with_per_matter_weights() -> None:
    """The boost is a multiplier on whatever base weights apply — including a
    watchlist override — not a fixed weight. A visual-heavy matter's phash pair
    scores far above the same pair scored typographic."""
    custom = {"phonetic": 0.20, "visual": 0.40, "semantic": 0.0, "class": 0.25, "vienna": 0.15}
    phash = composite_score(0.1, 0.90, 0.0, 1.0, 0.0, weights=custom, visual_confidence="phash")
    typo = composite_score(0.1, 0.90, 0.0, 1.0, 0.0, weights=custom, visual_confidence="typographic")
    assert phash.composite == pytest.approx(0.707)
    assert typo.composite == pytest.approx(0.38)
    assert phash.composite > typo.composite


def test_typographic_soundalikes_unchanged_by_3c() -> None:
    """Regression guard: sound-alike pairs are typographic, so Track 3c must leave
    them byte-identical to v1.4 — LIPITOR/LIPITAR stays Low, MONTINIS/MONTANIS
    stays Possible. This is the whole point of gating on confidence."""
    lipitor = composite_score(
        0.557, 0.675, 0.0, 1.0, 0.0, visual_confidence="typographic"
    )
    montinis = composite_score(
        0.945, 0.921, 0.0, 1.0, 0.0, visual_confidence="typographic"
    )
    assert lipitor.composite == pytest.approx(0.425)
    assert lipitor.verdict == "Low risk"
    assert montinis.composite == pytest.approx(0.669)
    assert montinis.verdict == "Possible conflict"
```

If `DEFAULT_WEIGHTS` is not already imported in this test module, add it to the existing
`from tm_similarity import (...)` import.

- [ ] **Step 6: Run the new unit tests**

Run: `pytest tests/test_similarity.py -k "phash_below_floor or mutate_default or composes_with_per_matter or soundalikes_unchanged" -q`
Expected: PASS (4 tests).

- [ ] **Step 7: Regenerate the composite golden fixture**

The boost changes the 4 pHash entries in `COMPOSITE_CASES` (indices 0,1,2,4 — all have visual >= 0.50);
the 2 typographic entries (3,5) are unchanged. In
`app/backend/tests/fixtures/similarity_golden.json`, replace the value of the `"composite"` key with:

```json
[[0.49, "Low risk", "ok"], [0.35, "Low risk", "ok"], [0.813, "Likely conflict", "stamp"], [0.296, "Low risk", "ok"], [0.329, "Low risk", "ok"], [0.378, "Low risk", "ok"]]
```

(Old value was `[[0.47,...],[0.308,...],[0.8,...],[0.296,...],[0.289,...],[0.378,...]]`.) Do not touch
the `phonetic` / `class` / `vienna` keys.

- [ ] **Step 8: Run the engine golden test**

Run: `pytest tests/test_tm_similarity_engine.py::test_composite_matches_golden -q`
Expected: PASS.

- [ ] **Step 9: Refresh stale inline comments on the three boosted scenario tests**

These tests still PASS (their assertions are verdicts / inequalities), but their inline arithmetic
comments now cite v1.4 numbers. Update the comments only (no assertion change) so the docs match:

- `test_composite_likely_conflict_threshold` (phash default, visual 0.8 >= floor): composite
  `0.745` → `0.752`. Update the comment block to:
  `# boosted (phash, visual>=0.50): mark = 0.3043*1.0 + 0.2609*0.8 = 0.513; goods = 0.1739*1.0 + 0.1304*0.5 = 0.239; composite = 0.752`
- `test_composite_possible_conflict_threshold` (phash default, visual 0.6 >= floor): composite
  `0.535` → `0.544`. Update the comment to reflect boosted weights (composite 0.544; still in
  `[0.50, 0.70)`).
- `test_composite_conjunction_guard_class_too_low` (phash default, visual 1.0 >= floor): the comment
  `composite = ... = 0.50` → `0.565` (mark only; class_o=0 so goods=0; still Low via the class guard).

Note: `test_composite_low_risk` (visual 0.3) and `test_composite_low_risk_when_only_class_overlaps`
(visual 0.423) are BELOW the floor → not boosted → unchanged; leave them.

- [ ] **Step 10: Run the full similarity + engine test files**

Run: `pytest tests/test_similarity.py tests/test_tm_similarity_engine.py -q`
Expected: PASS (all).

- [ ] **Step 11: Commit**

```bash
git add app/backend/tm_similarity/composite.py app/backend/tests/test_similarity.py app/backend/tests/fixtures/similarity_golden.json
git commit -m "feat(similarity): confidence-aware visual weight — pHash match boost (Track 3c)"
```

---

### Task 2: Version bump + version-pin tests

**Files:**
- Modify: `app/backend/tm_similarity/__init__.py`
- Modify: `app/backend/tests/test_double_metaphone.py`
- Modify: `app/backend/tests/test_vn_phonetic_routing.py`

- [ ] **Step 1: Update the two version-pin tests (failing)**

In `app/backend/tests/test_double_metaphone.py`, `test_version_and_export`:
`assert t.SIMILARITY_VERSION == "1.4"` → `assert t.SIMILARITY_VERSION == "1.5"`.

In `app/backend/tests/test_vn_phonetic_routing.py`, `test_version_bumped`:
`assert t.SIMILARITY_VERSION == "1.4"` → `assert t.SIMILARITY_VERSION == "1.5"`.

(These two files are the exact ones a targeted run missed during the 3b-2 CI pass — they are named
here on purpose.)

- [ ] **Step 2: Run them to confirm they fail**

Run: `pytest tests/test_double_metaphone.py::test_version_and_export tests/test_vn_phonetic_routing.py::test_version_bumped -q`
Expected: FAIL (`'1.4' == '1.5'`).

- [ ] **Step 3: Bump `SIMILARITY_VERSION`**

In `app/backend/tm_similarity/__init__.py`: `SIMILARITY_VERSION = "1.4"` → `SIMILARITY_VERSION = "1.5"`.

- [ ] **Step 4: Run them to confirm they pass**

Run: `pytest tests/test_double_metaphone.py::test_version_and_export tests/test_vn_phonetic_routing.py::test_version_bumped -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tm_similarity/__init__.py app/backend/tests/test_double_metaphone.py app/backend/tests/test_vn_phonetic_routing.py
git commit -m "chore(similarity): SIMILARITY_VERSION 1.4 -> 1.5 (Track 3c)"
```

---

### Task 3: Docs + full CI gate

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the Track 3c note to CLAUDE.md**

In `CLAUDE.md`, immediately after the `### Visual axis routing (Track 1)` subsection, add:

```markdown
### Confidence-aware visual weight (Track 3c)

**Track 3c:** the visual axis weight is now confidence-aware. In
`tm_similarity/composite.py`, when `visual_confidence == "phash"` AND the visual
score is a real match (`visual >= PHASH_BOOST_FLOOR`, 0.50), the visual weight is
multiplied by `PHASH_VISUAL_BOOST` (2.0 → 0.15 to ~0.26 effective after per-pair
renormalisation); typographic / none, and pHash non-matches, are unchanged. This
closes the permanent figurative-twin recall gap from 3b-2 (a nameless near-identical
logo: Low → Possible, composite 0.492 → 0.552) without touching sound-alike recall
(LIPITOR/LIPITAR and MONTINIS/MONTANIS are byte-identical, being typographic). The
score-floor gate prevents a low-scoring pHash axis from stealing weight from
phonetic. `mark_strength`, the goods dampener, and the verdict bands are unchanged.
SIMILARITY_VERSION is 1.5. **Schema-free** — engine-only, no column/migration/route/
frontend change. See `docs/superpowers/specs/2026-06-26-confidence-aware-visual-weight-design.md`.
```

- [ ] **Step 2: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs(similarity): document Track 3c confidence-aware visual weight (v1.5)"
```

- [ ] **Step 3: Run the full backend CI gate locally (BOTH ruff gates)**

```bash
cd app/backend && source ../.venv/bin/activate
ruff check .
ruff format --check .
mypy api worker tm_similarity
alembic check
pytest tests/test_similarity.py tests/test_tm_similarity_engine.py tests/test_double_metaphone.py tests/test_vn_phonetic_routing.py tests/test_per_matter_weights.py -q
```

Expected: all green. (Targeted pytest — do NOT run the whole suite; it resets the live sweep
singleton. CI runs the full suite in isolation.)

- [ ] **Step 4: Open the PR**

Push the branch and open a PR (base `main`) titled **"Track 3c: confidence-aware visual weight"**.
Body should note: `SIMILARITY_VERSION 1.4 → 1.5`; engine-only / schema-free; the figurative-twin
fix (Low → Possible) and that sound-alike pairs are byte-identical; the score-floor gate rationale.
Do NOT merge — the human reviews and squash-merges.

> Memory housekeeping (post-merge, by the controller, not the chip): flip the
> `similarity-track3c-confidence-aware-visual-weight.md` memory + its `MEMORY.md` line from "queued"
> to "done".

---

## Self-Review

**1. Spec coverage:** boost mechanism + multiplier + copy-on-write (Task 1 Step 3); score-floor gate
(Task 1 Step 3 + tests Step 5); figurative-twin flip (Task 1 Step 1); sound-alike regression guard
(Task 1 Step 5 + Task 3 Step 3 full run); per-matter compose (Task 1 Step 5); golden regen (Task 1
Step 7); version bump + pin tests (Task 2); docs (Task 3). All spec sections mapped.

**2. Placeholder scan:** none — every code/JSON block is literal and every value is computed.

**3. Type/identifier consistency:** `PHASH_VISUAL_BOOST`, `PHASH_BOOST_FLOOR`, `visual_confidence`,
`DEFAULT_WEIGHTS`, `composite_score` used consistently; constant values (2.0 / 0.50) and all
composite numbers (0.552, 0.55, 0.707, 0.38, 0.425, 0.669, golden array) match the spec and the
prototype run.
