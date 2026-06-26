# Semantic Axis + 5-Axis Weight Reallocation (Track 3b-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the stored LaBSE embeddings (Track 3b-1) into a live semantic (meaning) axis in the conflict engine and reallocate `DEFAULT_WEIGHTS` across five axes, surfacing cross-language/translation confusion (APPLE↔TÁO) the sound/sight axes miss.

**Architecture:** A pure-stdlib `tm_similarity/semantic.py` decodes the stored `bytea` embeddings via `array` (no numpy) and returns a floor-calibrated cosine. `composite.py` adds the axis to `mark_score` + `mark_strength` with phonetic-protective weights `.35/.15/.15/.20/.15`. `score()` threads it; routes pass `mark_embedding`; the frontend shows a semantic row. Read-only consumer of the 3b-1 column — no schema/model/ingest change.

**Tech Stack:** Python 3 (stdlib `array`/`math`), `jellyfish` (unchanged), pytest; Next.js/TS frontend.

**Spec:** [`docs/superpowers/specs/2026-06-26-semantic-axis-design.md`](../specs/2026-06-26-semantic-axis-design.md)

**Branch:** `track3b2-semantic-axis` (already checked out; spec already committed here).

---

## Pre-flight (read once, do not skip)

- **Working directory for backend:** `app/backend`; activate the venv in the SAME bash call: `cd app/backend && source /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet/app/.venv/bin/activate && <cmd>`.
- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` **explicit paths only**.
- **Targeted pytest only** — never the full suite (resets the live `domestic_sweep_control` singleton).
- **The 470 MB LaBSE model never runs in normal CI.** All engine tests use synthetic in-test byte vectors; the one marked calibration test is `@pytest.mark.skipif TM_RUN_MODEL_TESTS != "1"`.
- **Frontend:** typecheck with `pnpm exec tsc --noEmit` (from `app/frontend`). **NEVER `pnpm build` while `pnpm dev` is live.**
- All composite/golden values below are **prototype-verified** with the planned weights + math.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tm_similarity/semantic.py` | **Create** | `semantic_similarity(a_bytes, b_bytes) -> float` — stdlib cosine + floor map, None/length-safe |
| `tm_similarity/features.py` | Modify | `MarkFeatures.mark_embedding: bytes \| None = None`; `ScoreResult.semantic: float` |
| `tm_similarity/composite.py` | Modify | 5-axis `DEFAULT_WEIGHTS`; `composite_score` semantic arg + `mark_strength`; `resolve_weights` 5th key (automatic) |
| `tm_similarity/__init__.py` | Modify | `score()` threads semantic; `SIMILARITY_VERSION "1.4"`; export `semantic_similarity` |
| `api/routes/marks.py` | Modify | pass `mark_embedding` at the 2 `MarkFeatures` sites |
| `api/routes/compare.py` | Modify | pass `mark_embedding`; `resolve_weights(composite_w)`; `_DEFAULT` weights; `PairScore.semantic` |
| `app/frontend/app/(app)/compare/page.tsx` | Modify | semantic axis row + type + formula string |
| `app/frontend/app/(app)/marks/[id]/page.tsx`, `watchlists/page.tsx` | Modify | semantic row (discover-and-mirror) |
| `tests/_similarity_cases.py`, `tests/fixtures/similarity_golden.json` | Modify | `COMPOSITE_CASES` + `semantic` column; regen composite golden |
| `tests/test_semantic.py` | **Create** | semantic_similarity units + marked real-model calibration test |
| `CLAUDE.md` | Modify | semantic-axis note (v1.4, 5-axis weights, floor, stdlib cosine, deploy caveat) |

---

## Task 1: `tm_similarity/semantic.py` — the pure cosine axis

**Files:**
- Create: `tm_similarity/semantic.py`
- Test: `tests/test_semantic.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_semantic.py`:

```python
"""semantic_similarity: stdlib cosine + floor mapping, None/length-safe."""

from __future__ import annotations

import array
import math

from tm_similarity.semantic import SEMANTIC_FLOOR, semantic_similarity

_DIM = 768


def _unit(pairs: list[tuple[int, float]]) -> bytes:
    """Build an L2-normalised 768-float32 byte vector from (index, value) pairs."""
    v = array.array("f", [0.0] * _DIM)
    for i, val in pairs:
        v[i] = val
    n = math.sqrt(sum(x * x for x in v))
    for i in range(_DIM):
        v[i] = v[i] / n
    return v.tobytes()


def test_identical_vectors_score_1():
    a = _unit([(0, 1.0)])
    assert semantic_similarity(a, a) == 1.0


def test_orthogonal_vectors_score_0():
    a = _unit([(0, 1.0)])
    b = _unit([(1, 1.0)])
    assert semantic_similarity(a, b) == 0.0  # cos 0 is below the floor


def test_above_floor_maps_linearly():
    # cos = 0.85 -> (0.85 - 0.50)/(1 - 0.50) = 0.70
    b2 = math.sqrt(1.0 - 0.85**2)
    a = _unit([(0, 1.0)])
    b = _unit([(0, 0.85), (1, b2)])
    assert semantic_similarity(a, b) == 0.7


def test_none_returns_zero():
    a = _unit([(0, 1.0)])
    assert semantic_similarity(None, a) == 0.0
    assert semantic_similarity(a, None) == 0.0
    assert semantic_similarity(None, None) == 0.0


def test_malformed_buffer_returns_zero():
    a = _unit([(0, 1.0)])
    assert semantic_similarity(a, b"\x00\x01\x02") == 0.0  # not 768 floats


def test_floor_default():
    assert SEMANTIC_FLOOR == 0.50
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_semantic.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tm_similarity.semantic'`.

- [ ] **Step 3: Implement `tm_similarity/semantic.py`**

```python
"""Semantic (meaning) similarity axis (Track 3b-2).

Pure stdlib. Reads two marks' stored LaBSE embeddings (bytea of 768
L2-normalised float32, written by Track 3b-1) and returns a floor-calibrated
cosine in [0, 1]. No numpy, no model — the engine consumes stored bytes only,
keeping tm_similarity at stdlib + jellyfish.
"""

from __future__ import annotations

import array

_DIM = 768

# Cosine floor. LaBSE cosine for unrelated short text sits well above 0, so map
# (cos - FLOOR) / (1 - FLOOR) clamped to [0, 1] (mirrors the visual axis's
# 1 - hd/T recalibration). Calibrated against real LaBSE — see the marked test
# in tests/test_semantic.py (TM_RUN_MODEL_TESTS=1).
SEMANTIC_FLOOR = 0.50


def _decode(buf: bytes | None) -> array.array | None:
    """Decode bytea into 768 float32, or None if missing/malformed."""
    if not buf:
        return None
    vec = array.array("f")
    try:
        vec.frombytes(buf)
    except ValueError:
        return None
    if len(vec) != _DIM:
        return None
    return vec


def semantic_similarity(a_embedding: bytes | None, b_embedding: bytes | None) -> float:
    """Floor-calibrated cosine of two stored mark embeddings, in [0, 1].

    Returns 0.0 when either embedding is missing or malformed (figurative or
    not-yet-backfilled marks contribute no semantic signal — permissive, like
    Track 1's NULL logo_kind). Both vectors were L2-normalised at write time
    (Track 3b-1), so cosine == dot product.
    """
    a = _decode(a_embedding)
    b = _decode(b_embedding)
    if a is None or b is None:
        return 0.0
    cos = sum(x * y for x, y in zip(a, b))
    score = (cos - SEMANTIC_FLOOR) / (1.0 - SEMANTIC_FLOOR)
    return round(max(0.0, min(1.0, score)), 3)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_semantic.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Add the marked real-model calibration test (skipped in CI)**

Append to `tests/test_semantic.py`:

```python
import os

import pytest


@pytest.mark.skipif(
    os.environ.get("TM_RUN_MODEL_TESTS") != "1",
    reason="loads the 470MB LaBSE model; opt-in via TM_RUN_MODEL_TESTS=1",
)
def test_floor_separates_translation_from_unrelated():
    # Validate (and if needed re-tune) SEMANTIC_FLOOR against real LaBSE:
    # translation equivalents map high, unrelated low.
    from api._embed import compute_mark_embedding

    def sem(a: str, b: str) -> float:
        return semantic_similarity(compute_mark_embedding(a), compute_mark_embedding(b))

    assert sem("APPLE", "TÁO") >= 0.5
    assert sem("RED BULL", "BÒ ĐỎ") >= 0.5
    assert sem("APPLE", "CHAIR") <= 0.15
    assert sem("NIKE", "TABLE") <= 0.15
```

- [ ] **Step 6: (Optional, slow) run the calibration test to confirm/tune the floor**

Run: `TM_RUN_MODEL_TESTS=1 pytest tests/test_semantic.py::test_floor_separates_translation_from_unrelated -q`
Expected: PASS with `SEMANTIC_FLOOR = 0.50`. If it fails (LaBSE cosine distribution differs for short trademark tokens), tune `SEMANTIC_FLOOR` until translation pairs clear 0.5 and unrelated stay ≤0.15, then re-run. Document the chosen value in the module comment. Skip this step if the model is unavailable in the worktree — normal CI does not run it.

- [ ] **Step 7: Commit**

```bash
git add app/backend/tm_similarity/semantic.py app/backend/tests/test_semantic.py
git commit -m "feat(similarity): semantic axis — stdlib floor-calibrated cosine on stored embeddings"
```

---

## Task 2: DTOs + 5-axis composite + score wiring + golden

**Files:**
- Modify: `tm_similarity/features.py`, `tm_similarity/composite.py`, `tm_similarity/__init__.py`
- Modify: `tests/_similarity_cases.py`, `tests/fixtures/similarity_golden.json`
- Test: `tests/test_tm_similarity_engine.py` (existing golden test, updated)

- [ ] **Step 1: Update the shared cases + golden test to the 5-axis shape (failing)**

In `tests/_similarity_cases.py`, replace `COMPOSITE_CASES` with the 6-tuple form (semantic inserted as the 3rd element, plus one semantic-driven case):

```python
# (phonetic, visual, semantic, class_o, vienna_o, visual_confidence)
COMPOSITE_CASES = [
    (0.60, 0.63, 0.00, 1.0, 0.0, "phash"),
    (0.14, 0.63, 0.00, 1.0, 0.0, "phash"),
    (0.90, 0.90, 0.00, 1.0, 1.0, "phash"),
    (0.49, 0.20, 0.00, 1.0, 0.0, "typographic"),
    (0.16, 0.59, 0.00, 1.0, 0.0, "phash"),
    (0.10, 0.10, 0.85, 1.0, 0.0, "typographic"),  # semantic-driven (translation equiv)
]
```

In `tests/test_tm_similarity_engine.py`, update `test_composite_matches_golden` to unpack the semantic column and pass it positionally, and update `test_score_assembles_result` to assert the semantic field:

```python
def test_composite_matches_golden():
    got = [
        [(cs := t.composite_score(p, v, s, c, vi, visual_confidence=vc)).composite, cs.verdict, cs.verdict_tone]
        for p, v, s, c, vi, vc in COMPOSITE_CASES
    ]
    assert got == GOLDEN["composite"]


def test_score_assembles_result():
    a = t.MarkFeatures(mark_text="Gemy", logo_phash=None, nice_classes=["11"], vienna_codes=[])
    b = t.MarkFeatures(mark_text="Gemy", logo_phash=None, nice_classes=["11"], vienna_codes=[])
    r = t.score(a, b)
    assert r.phonetic == t.phonetic_similarity("Gemy", "Gemy")
    assert r.semantic == 0.0  # no embeddings -> no semantic signal
    assert r.verdict in {"Likely conflict", "Possible conflict", "Low risk"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_tm_similarity_engine.py -q`
Expected: FAIL — `composite_score()` takes the old 4-axis positional args / `ScoreResult` has no `semantic` / golden mismatch.

- [ ] **Step 3: Add the DTO fields in `tm_similarity/features.py`**

Add to `MarkFeatures` (after `logo_kind`, keyword-defaulted so positional construction stays valid):

```python
    mark_embedding: bytes | None = None  # 768 L2-normalised float32 (Track 3b-1); None = no semantic signal
```

Add to `ScoreResult` (after `visual_confidence`):

```python
    semantic: float
```

(`ScoreResult` is assembled by keyword in `__init__.py` Step 5, so field order is irrelevant; place it logically next to the other axis floats.)

- [ ] **Step 4: Rework `tm_similarity/composite.py` to 5 axes**

Replace `DEFAULT_WEIGHTS`:

```python
DEFAULT_WEIGHTS = {"phonetic": 0.35, "visual": 0.15, "semantic": 0.15, "class": 0.20, "vienna": 0.15}
"""Phonetic-protective 5-axis split (Track 3b-2). Semantic's 0.15 is drawn
mostly from visual (0.25->0.15), keeping phonetic (0.40->0.35) close to prior
behaviour so phonetic-conflict recall is least disturbed. 0.65 mark / 0.35
goods ratio preserved. Per-matter tunable via resolve_weights."""
```

`resolve_weights` needs **no change** — it iterates `for k in DEFAULT_WEIGHTS`, so the new `"semantic"` key is honoured automatically (overrides fill it, missing inherits the default, renormalised).

Replace `composite_score` with the semantic-aware version (signature gains `semantic` as the 3rd positional arg; `mark_score` and `mark_strength` include it; ramp + verdict bands unchanged):

```python
def composite_score(
    phonetic: float,
    visual: float,
    semantic: float,
    class_o: float,
    vienna_o: float,
    weights: dict[str, float] | None = None,
    visual_confidence: VisualConfidence = "phash",
) -> CompositeScore:
    """Composite conflict score + verdict across 5 axes.

    mark_score  = w_phon*phonetic + w_vis*visual + w_sem*semantic   (sight/sound/meaning)
    goods_score = w_class*class_o + w_vienna*vienna_o               (goods relatedness)
    composite   = mark_score + goods_score * goods_factor(mark_strength)

    `semantic` (cross-language/conceptual meaning) is independent evidence like a
    pHash visual match, so it enters `mark_strength` and lets the goods axis
    count. Typographic/none visual still does not. Verdict bands and the
    class-overlap conjunction guard are unchanged.
    """
    w = weights or DEFAULT_WEIGHTS

    mark_score = w["phonetic"] * phonetic + w["visual"] * visual + w["semantic"] * semantic
    goods_score = w["class"] * class_o + w["vienna"] * vienna_o

    candidates = [phonetic, semantic]
    if visual_confidence == "phash":
        candidates.append(visual)
    mark_strength = max(candidates)

    goods_factor = max(0.0, min(1.0, (mark_strength - 0.30) / 0.40))
    composite = round(mark_score + goods_score * goods_factor, 3)

    if composite >= 0.70 and mark_strength >= 0.70 and class_o >= 0.30:
        return CompositeScore(composite, "Likely conflict", "stamp")
    if composite >= 0.50 and mark_strength >= 0.50 and class_o >= 0.20:
        return CompositeScore(composite, "Possible conflict", "warn")
    return CompositeScore(composite, "Low risk", "ok")
```

Keep the existing module docstring on `composite_score`'s rationale where still accurate; the bands and goods-dampener are unchanged — only the `semantic` term and `mark_strength` candidate are new.

- [ ] **Step 5: Wire the axis in `tm_similarity/__init__.py`**

Add the import next to the other axis imports:

```python
from .semantic import semantic_similarity
```

In `score()`, compute and thread semantic:

```python
def score(a: MarkFeatures, b: MarkFeatures, *, weights: dict[str, float] | None = None) -> ScoreResult:
    """Score one pair of marks across all axes; assemble the full ScoreResult."""
    phon = phonetic_similarity(a.mark_text, b.mark_text)
    vis = visual_similarity(a.logo_phash, b.logo_phash, a.logo_kind, b.logo_kind, a.mark_text, b.mark_text)
    sem = semantic_similarity(a.mark_embedding, b.mark_embedding)
    class_o = class_overlap(a.nice_classes, b.nice_classes)
    vienna_o = vienna_overlap(a.vienna_codes, b.vienna_codes)
    cs = composite_score(
        phon, vis.score, sem, class_o, vienna_o, weights=weights, visual_confidence=vis.confidence
    )
    return ScoreResult(
        composite=cs.composite,
        verdict=cs.verdict,
        verdict_tone=cs.verdict_tone,
        phonetic=phon,
        visual=vis.score,
        semantic=sem,
        visual_confidence=vis.confidence,
        class_overlap=class_o,
        vienna_overlap=vienna_o,
    )
```

Bump the version and export:

```python
SIMILARITY_VERSION = "1.4"
```

Add `"semantic_similarity"` to `__all__` (sorted — just before `"vienna_overlap"`).

- [ ] **Step 6: Regenerate the composite golden fixture**

In `tests/fixtures/similarity_golden.json`, replace the `composite` array with the prototype-verified new values (the `phonetic`/`class`/`vienna` arrays stay byte-identical — those axis functions are unchanged):

```json
  "composite": [
    [0.47, "Low risk", "ok"],
    [0.308, "Low risk", "ok"],
    [0.8, "Likely conflict", "stamp"],
    [0.296, "Low risk", "ok"],
    [0.289, "Low risk", "ok"],
    [0.378, "Low risk", "ok"]
  ]
```

- [ ] **Step 7: Run the engine golden + unit tests to verify green**

Run: `pytest tests/test_tm_similarity_engine.py tests/test_semantic.py -q`
Expected: PASS (golden composite matches the new array; phonetic/class/vienna unchanged; `score()` returns `semantic`).

- [ ] **Step 8: Commit**

```bash
git add app/backend/tm_similarity/features.py app/backend/tm_similarity/composite.py app/backend/tm_similarity/__init__.py app/backend/tests/_similarity_cases.py app/backend/tests/fixtures/similarity_golden.json app/backend/tests/test_tm_similarity_engine.py
git commit -m "feat(similarity): 5-axis composite with semantic axis; SIMILARITY_VERSION 1.4"
```

---

## Task 3: Route adapters — feed embeddings + 5-axis weights + serialize semantic

**Files:**
- Modify: `api/routes/marks.py`, `api/routes/compare.py`
- Test: the existing compare test (locate with `ls tests | grep compare`)

- [ ] **Step 1: Write/extend a failing route test**

Locate the existing compare test file (`ls tests | grep -i compare`). Add a test asserting the `semantic` field is present and `0.0` when the seeded marks have no embedding, reusing that file's client fixture and seed/IDs:

```python
@pytest.mark.asyncio
async def test_compare_returns_semantic_zero_without_embeddings(client):
    # Reuse the file's existing seed helpers/IDs for two marks with NULL mark_embedding.
    resp = await client.post("/api/v1/compare", json={"anchorId": "<seeded id>", "otherIds": ["<seeded id2>"]})
    assert resp.status_code == 200
    assert resp.json()["scores"][0]["semantic"] == 0.0
```

Match the request body shape to the other compare tests in the file (field names/route path may differ — copy a working call and add the `semantic` assertion).

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/<compare_test_file>.py -q`
Expected: FAIL — the response has no `semantic` key (KeyError on the assertion).

- [ ] **Step 3: `api/routes/marks.py` — pass `mark_embedding`**

At the `m_feat = MarkFeatures(...)` builder (~line 394) add `mark_embedding=m.mark_embedding`; at the candidate `MarkFeatures(...)` builder inside the loop (~line 407) add `mark_embedding=r.mark_embedding`. marks.py already routes weights through `resolve_weights` (now 5-key automatically) — no weight change. If the `Trademark` query uses `load_only`/explicit columns, add `Trademark.mark_embedding` so `m`/`r` carry it (it is a mapped column, so a normal full-entity load already includes it).

- [ ] **Step 4: `api/routes/compare.py` — embedding, 5-axis weights, schema, response**

(a) Add `mark_embedding=anchor.mark_embedding` and `mark_embedding=other.mark_embedding` to the two `MarkFeatures(...)` builders (~lines 159, 166).

(b) Import `resolve_weights` and wrap the weights so the 5th key is filled + renormalised. Change the import to:

```python
from tm_similarity import MarkFeatures, resolve_weights, score
```

and the score call's weights arg (~line 173) from `weights=composite_w` to:

```python
        weights=resolve_weights(composite_w),
```

(`composite_w` carries the 4 public axes mapped to engine keys; `resolve_weights` inserts `semantic` at its default 0.15 and renormalises to sum 1.0.)

(c) Update the `_DEFAULT` public weights block (~lines 41-44) so the compare default matches the new engine default after `resolve_weights` fills semantic:

```python
    "phonetic": 0.35,
    "visual": 0.15,
    "classOverlap": 0.20,
    "viennaOverlap": 0.15,
```

(These sum to 0.85; `resolve_weights` adds `semantic` 0.15 → 1.0, exactly `DEFAULT_WEIGHTS`.)

(d) Add `semantic: float` to the `PairScore` schema (next to `phonetic: float`/`visual: float`, ~lines 56-59).

(e) Add `semantic=round(result.semantic, 3)` to the `PairScore(...)` response construction (next to `phonetic=`/`visual=`, ~lines 176-184).

- [ ] **Step 5: Run the route test to verify it passes**

Run: `pytest tests/<compare_test_file>.py -q`
Expected: PASS (response includes `semantic`, `0.0` for embedding-less marks).

- [ ] **Step 6: Commit**

```bash
git add app/backend/api/routes/marks.py app/backend/api/routes/compare.py app/backend/tests/<compare_test_file>.py
git commit -m "feat(api): feed mark_embedding into scoring; 5-axis weights; serialize semantic"
```

---

## Task 4: Frontend — semantic axis row

**Files:**
- Modify: `app/frontend/app/(app)/compare/page.tsx`
- Modify: `app/frontend/app/(app)/marks/[id]/page.tsx`, `app/frontend/app/(app)/watchlists/page.tsx`

- [ ] **Step 1: Compare page — add the semantic row + type + formula**

In `app/frontend/app/(app)/compare/page.tsx`:
- The score row type that has `phonetic`, `visual`, `classOverlap`, `viennaOverlap` (the `data.scores[i].*` fields used ~lines 156-174) — add `semantic: number`.
- Add a semantic axis row mirroring the sibling rows. The phonetic row is ~156, class ~170, vienna ~174; copy the `classOverlap` row's container/label structure and swap to a "Semantic (meaning)" label and the `semantic` field:

```tsx
            {others.map((m, i) => <ScoreInline key={m.id} value={data.scores[i].semantic} />)}
```

Place it after the visual row (sight → sound → meaning → goods order).
- If the weight-formula caption (~lines 285-286) enumerates axes, append `· {pct(w.semantic)}% semantic` and add `semantic: weights.semantic ?? 0.15` to the local `w` defaults (~lines 266-269). If the caption is static text, just update the wording to include semantic.

- [ ] **Step 2: Mark detail + watchlists — mirror (discover-and-mirror)**

For `marks/[id]/page.tsx` and `watchlists/page.tsx`: search each for `classOverlap`/`viennaOverlap`/`phonetic` to find where the per-axis breakdown renders. If a surface renders the breakdown, add a "Semantic (meaning)" row mirroring the existing axis rows (reading the `semantic` field) and extend that file's score type with `semantic: number`. If a surface shows only the composite/verdict (no per-axis breakdown), make no change there — state which in the commit message.

- [ ] **Step 3: Typecheck**

Run (from `app/frontend`): `pnpm exec tsc --noEmit`
Expected: clean. Do NOT run `pnpm build` while `pnpm dev` is live.

- [ ] **Step 4: Commit**

```bash
git add "app/frontend/app/(app)/compare/page.tsx" "app/frontend/app/(app)/marks/[id]/page.tsx" "app/frontend/app/(app)/watchlists/page.tsx"
git commit -m "feat(ui): semantic (meaning) axis row in score breakdowns"
```

---

## Task 5: CI gates + docs sync

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Backend CI gates**

Run (from `app/backend`, venv active):
```bash
ruff check tm_similarity api/routes/compare.py api/routes/marks.py tests/test_semantic.py
ruff format --check tm_similarity api/routes/compare.py api/routes/marks.py tests/test_semantic.py tests/_similarity_cases.py
mypy api worker tm_similarity
alembic check
```
Expected: all clean. Run BOTH ruff gates (a Track 2 failure came from skipping `ruff format`). `alembic check` stays green (no schema change). Fix inline.

- [ ] **Step 2: Run the full Track 3b-2 backend surface (targeted)**

Run: `pytest tests/test_semantic.py tests/test_tm_similarity_engine.py tests/<compare_test_file>.py -q`
Expected: PASS (semantic units + frozen-axis golden with new composite + route serialization).

- [ ] **Step 3: Docs sync — add the semantic-axis subsection to `CLAUDE.md`**

In `CLAUDE.md`, after the "### Mark embedding feature store (Track 3b-1)" subsection, add:

```markdown
### Semantic axis (Track 3b-2)

`tm_similarity/semantic.py:semantic_similarity(a_bytes, b_bytes)` is the 5th
axis: it decodes the stored `trademarks.mark_embedding` bytea (768 L2-normalised
float32) with stdlib `array` (no numpy — the engine stays stdlib + jellyfish)
and returns a **floor-calibrated cosine** `max(0, (cos - SEMANTIC_FLOOR)/(1 -
SEMANTIC_FLOOR))` (`SEMANTIC_FLOOR = 0.50`, calibrated vs real LaBSE; the marked
`TM_RUN_MODEL_TESTS=1` test in `tests/test_semantic.py` validates/tunes it). NULL
embedding → 0.0. `composite.py` adds it to `mark_score` and `mark_strength`
(independent evidence like a pHash visual match) with phonetic-protective
`DEFAULT_WEIGHTS` `{phonetic .35, visual .15, semantic .15, class .20, vienna
.15}`; verdict bands + the class-overlap guard are unchanged. `SIMILARITY_VERSION`
is 1.4. **Deployment caveat:** adding a weighted axis lowers composites for pairs
with no semantic match (some borderline Possible→Low), and until
`backfill_mark_embedding` has populated the corpus every pair scores `sem=0` —
**run the embedding backfill (after `backfill_mark_name`) before/with rollout.**
See `docs/superpowers/specs/2026-06-26-semantic-axis-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Track 3b-2 semantic axis + 5-axis weights (SIMILARITY_VERSION 1.4)"
```

---

## Self-Review (completed at plan-authoring time)

**Spec coverage:**
- §1 `semantic.py` (stdlib cosine + floor + None/length guards) → Task 1.
- §2 FLOOR calibration (default 0.50, marked test, synthetic-vector units) → Task 1.
- §3 DTOs (`MarkFeatures.mark_embedding`, `ScoreResult.semantic`) → Task 2.
- §4 5-axis `composite_score` + weights + `mark_strength` + `resolve_weights` → Task 2.
- §5 `score()` wiring + version 1.4 + export → Task 2.
- §6 route adapters (4 `MarkFeatures` sites; compare weights via `resolve_weights`; serialize `semantic`) → Task 3.
- §7 frontend semantic row (3 surfaces) → Task 4.
- §Testing 1–6 (semantic units, marked calibration, composite 5-axis, golden regen, route NULL→0.0, frontend) → Tasks 1/2/3/4.
- §Out-of-scope (no model/numpy/schema/ingest/search-rerank/pgvector) → respected.
- §Docs + deploy caveat → Task 5.

**Placeholder scan:** the only non-literal fill-ins are (a) the exact compare test file name + seed IDs (the implementer reuses that file's fixtures) and (b) Task 4 Step 2's discover-and-mirror for the two non-compare surfaces (their exact JSX wasn't read; pattern + fields specified). All backend code, signatures, weights, and the golden array are concrete and prototype-verified.

**Type/name consistency:** `semantic_similarity(a_embedding, b_embedding) -> float`, `SEMANTIC_FLOOR=0.50`, `_DIM=768`; `composite_score(phonetic, visual, semantic, class_o, vienna_o, weights=None, visual_confidence="phash")` with `semantic` 3rd positional matches the golden test unpack `(p, v, s, c, vi, vc)`; `MarkFeatures.mark_embedding` / `ScoreResult.semantic` / `PairScore.semantic` consistent across Tasks 2–4; `DEFAULT_WEIGHTS` `.35/.15/.15/.20/.15` matches the prototype-verified composite golden `[0.47, 0.308, 0.8, 0.296, 0.289, 0.378]`.
