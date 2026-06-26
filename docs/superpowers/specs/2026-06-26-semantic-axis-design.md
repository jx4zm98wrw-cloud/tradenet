# Semantic Axis + 5-Axis Weight Reallocation (Track 3b-2) — Design

**Status:** Approved for planning · 2026-06-26

**Goal:** Turn the stored LaBSE embeddings (Track 3b-1) into a live **semantic (meaning) axis** in the
conflict engine, so cross-language translation equivalents and conceptual synonyms (`APPLE`↔`TÁO`,
`RED BULL`↔`BÒ ĐỎ`) raise the composite — and reallocate `DEFAULT_WEIGHTS` across **five** axes.
This is the behaviour-changing payoff of the semantic epic: 3b-1 built the feature store with zero
scoring effect; 3b-2 consumes it. The engine stays **pure** (stdlib + `jellyfish` — the cosine is
stdlib `array`, no numpy in `tm_similarity`) and the model is **never** imported here (the engine
reads stored bytes only).

## Why (program context)

Trademark law recognises three mark-similarity dimensions — **appearance, sound, and meaning
(connotation)**. Tracks 1–3a delivered sight (visual pHash routing) and sound (VN phonetic key +
Double Metaphone). 3b-1 stored an L2-normalised 768-float32 LaBSE embedding of each mark's `mark_name`
in `trademarks.mark_embedding` (`bytea`). 3b-2 adds the **meaning** axis: cosine similarity of two
marks' embeddings, surfacing confusion that sound/sight axes are blind to — above all cross-language
translation equivalents IP Vietnam examiners weigh. Decisions taken at design time (2026-06-26):
weight split `phon .35 / vis .15 / sem .15 / class .20 / vienna .15` (phonetic-protective — semantic's
budget comes mostly from visual, keeping phonetic recall close to today, the engine's core job);
ship the frontend axis row with the engine change (no transparency gap).

**Behaviour-shift caveat (accepted, documented):** adding a weighted axis to a fixed-threshold
weighted sum lowers composites for pairs with *no* semantic match (the common case) — e.g. golden
case 0 (`phon .60, vis .63, sem 0`) flips `Possible → Low risk`. Headline conflicts still flag; only
borderline sound/sight-only pairs slip. The phonetic-protective split limits this for phonetic-dominant
pairs. **Deployment hazard:** until 3b-1's backfill has populated `mark_embedding` across the corpus,
every pair has `sem = 0` and composites drop uniformly — **run `backfill_mark_embedding` (after
`backfill_mark_name`) before/with the 3b-2 rollout.** Verdict-threshold recalibration is out of scope
(a later track if recall regresses); weights remain per-matter tunable.

## Current state (what we change)

- `tm_similarity/features.py`: `MarkFeatures(mark_text, logo_phash, nice_classes, vienna_codes,
  logo_kind)`; `ScoreResult(composite, verdict, verdict_tone, phonetic, visual, visual_confidence,
  class_overlap, vienna_overlap)`.
- `tm_similarity/composite.py`: `DEFAULT_WEIGHTS = {phonetic .40, visual .25, class .20, vienna .15}`;
  `composite_score(phonetic, visual, class_o, vienna_o, weights=None, visual_confidence="phash")` —
  `mark_score = w_phon*phon + w_vis*vis`; `goods_score = w_class*class + w_vienna*vienna`;
  `mark_strength = max(phon, vis) if phash else phon`; `goods_factor` ramp;
  verdict bands (Likely ≥.70/.70/class≥.30; Possible ≥.50/.50/class≥.20; else Low).
  `resolve_weights` merges + renormalises the 4 known keys.
- `tm_similarity/__init__.py`: `SIMILARITY_VERSION = "1.3"`; `score()` assembles the result.
- `trademarks.mark_embedding` (`bytea`, 768 L2-normalised float32) — populated by 3b-1's backfill;
  NULL for figurative / not-yet-name-backfilled marks.
- `MarkFeatures(...)` built at 4 route sites: `api/routes/marks.py` (×2), `api/routes/compare.py` (×2).
- Frontend axis breakdown shown on `app/(app)/compare/page.tsx`, `app/(app)/marks/[id]/page.tsx`,
  `app/(app)/watchlists/page.tsx`.

## Resolution

### 1. New pure module `tm_similarity/semantic.py` (stdlib only)

```python
def semantic_similarity(a_embedding: bytes | None, b_embedding: bytes | None) -> float: ...
```

- Decodes each `bytea` into 768 float32 via stdlib **`array`** (`array("f").frombytes(buf)`) — **no
  numpy** (keeps the engine dependency-light; the bytes were L2-normalised at write time in 3b-1).
- Both vectors are unit-norm, so **cosine = dot product** (plain `sum(x*y …)`).
- **Floor-calibrated mapping** (mirrors the Track 1 visual recalibration `1 - hd/T`): LaBSE cosine for
  unrelated short text sits well above 0, so raw cosine would inflate every pair. Map:
  `score = max(0.0, min(1.0, (cos - FLOOR) / (1.0 - FLOOR)))`, `FLOOR` a module constant.
- Returns `0.0` if either embedding is `None` (figurative / pre-backfill marks contribute no semantic
  signal — permissive, exactly like Track 1's NULL `logo_kind` routing).
- Defensive: if a decoded buffer is not 768 floats, treat as no signal (`0.0`).

### 2. `FLOOR` calibration (the model-dependent constant)

`FLOOR` cannot be derived in-repo (the 470 MB model is not run in CI). It is **calibrated at build
time** and validated by a marked test:

- **Default:** `FLOOR = 0.50` (LaBSE is margin-trained; translation pairs cosine ~0.6–0.9, unrelated
  lower — a 0.50 floor maps translation pairs high and unrelated toward ~0). The implementer confirms
  or tunes this against the calibration set.
- **Calibration set + marked real-model test** (`@pytest.mark.skipif TM_RUN_MODEL_TESTS != "1"`):
  embed labeled pairs with real LaBSE (via `api._embed.compute_mark_embedding`) and assert
  `semantic_similarity` maps translation equivalents high (≥ ~0.5) and unrelated low (≤ ~0.15) —
  `APPLE`/`TÁO`, `RED BULL`/`BÒ ĐỎ` high; `APPLE`/`CHAIR`, `NIKE`/`TABLE` low. If the default `FLOOR`
  fails the set, tune it and re-run (document the chosen value). **Not run in normal CI.**
- **All other tests use synthetic in-test L2-normalised byte vectors** (constructed with stdlib
  `array`/`struct`), never the model — so unit + golden + composite tests stay model-free.

### 3. `features.py` — DTO additions

- `MarkFeatures`: add `mark_embedding: bytes | None = None` (keyword-defaulted so existing positional
  construction stays valid).
- `ScoreResult`: add `semantic: float`.

### 4. `composite.py` — 5-axis reweight

- `DEFAULT_WEIGHTS = {"phonetic": 0.35, "visual": 0.15, "semantic": 0.15, "class": 0.20, "vienna":
  0.15}` (sums to 1.0; 0.65 mark / 0.35 goods ratio preserved). Phonetic-protective: semantic's 0.15
  is drawn mostly from visual (0.25→0.15), keeping phonetic (0.40→0.35) close to today so the engine's
  core phonetic-conflict recall is least disturbed; visual and semantic tie at 0.15.
- `composite_score(phonetic, visual, semantic, class_o, vienna_o, weights=None,
  visual_confidence="phash")` — **`semantic` inserted as the 3rd positional arg** (after visual,
  before class_o), matching the mark→goods reading order.
  - `mark_score = w_phon*phon + w_vis*vis + w_sem*semantic`
  - `goods_score = w_class*class_o + w_vienna*vienna_o` (unchanged)
  - `mark_strength = max(phon, semantic, vis-if-phash-else-skip)` — semantic is **independent
    evidence** (like phash visual): a translation-equivalent mark IS strong mark similarity, so it
    enters the conjunction signal and lets the goods axis count. (Typographic/none visual still does
    not, unchanged.)
  - `goods_factor` ramp and verdict bands **unchanged** (the `class_o ≥ .30/.20` guard stays — a
    meaning-similar mark still needs related goods to conflict).
- `resolve_weights` now honours the 5 known keys (add `"semantic"`); same drop-invalid + renormalise
  logic.

### 5. `__init__.py` — wire the axis

- `score()` computes `sem = semantic_similarity(a.mark_embedding, b.mark_embedding)`, passes it to
  `composite_score(..., sem, class_o, vienna_o, ...)`, and sets `ScoreResult.semantic = sem`.
- `SIMILARITY_VERSION = "1.4"`. Export `semantic_similarity`.

### 6. Route adapters — pass the embedding

The 4 `MarkFeatures(...)` sites in `api/routes/marks.py` and `api/routes/compare.py` set
`mark_embedding=<row>.mark_embedding` from the already-loaded `Trademark` row (the column is read in
the existing query; add it to the select if not already loaded). No new query shape — the bytes ride
the existing per-mark fetch.

### 7. Frontend — semantic axis row

Add a "Semantic" (meaning) row to the axis breakdown on the 3 surfaces (compare, mark detail,
watchlists), reading `ScoreResult.semantic` (serialised on `TrademarkOut`/compare payloads). Same
presentation as the existing phonetic/visual/class/vienna rows. If a shared axis-row component exists,
extend it once; otherwise mirror the existing rows on each surface.

## Data flow

```
score(a, b):
  phon   = phonetic_similarity(a.mark_text, b.mark_text)       # unchanged (Tracks 2/3a)
  vis    = visual_similarity(...)                              # unchanged (Track 1)
  sem    = semantic_similarity(a.mark_embedding, b.mark_embedding)   # NEW: stdlib cosine + floor
  class_o, vienna_o = class_overlap(...), vienna_overlap(...)  # unchanged
  cs = composite_score(phon, vis.score, sem, class_o, vienna_o,
                       weights, visual_confidence=vis.confidence)
  return ScoreResult(..., phonetic=phon, visual=vis.score, semantic=sem, ...)
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `semantic.py:semantic_similarity` | bytes → cosine → floor-mapped [0,1]; None-safe | stdlib `array`/`math` |
| `features.py` | `MarkFeatures.mark_embedding`, `ScoreResult.semantic` | — |
| `composite.py` | 5-axis weights; semantic in `mark_score` + `mark_strength` | — |
| `__init__.py:score` | compute + thread semantic; version bump | `semantic` |
| routes `marks.py`/`compare.py` | pass `mark_embedding` into `MarkFeatures` | ORM row |
| frontend axis breakdown ×3 | render the semantic row | `ScoreResult.semantic` |

`phonetic.py`, `visual.py`, `classes.py`, `vn_phonetic.py`, `double_metaphone.py`, `api/_embed.py`,
the ingest worker, the backfill — **untouched**.

## Versioning

- `SIMILARITY_VERSION`: `"1.3" → "1.4"` (composite semantics + a new axis).
- No schema change (the column shipped in 3b-1). No backfill (read-only consumer).

## Behaviour change & testing (targeted pytest only — sweep tests reset the live singleton)

Frozen-axis discipline holds for the **axis functions** (phonetic/visual/class/vienna golden values
unchanged — those functions don't change). The **composite** golden legitimately moves (new weights +
the semantic term) — this is the one track that changes composite math.

1. **`semantic_similarity` units (synthetic vectors):** build L2-normalised 768-float32 byte vectors
   in-test (stdlib `array`); assert identical vectors → 1.0; an orthogonal pair → 0.0 (below floor);
   a pair whose cosine sits above the floor maps to the expected `(cos-FLOOR)/(1-FLOOR)`; `None` on
   either side → 0.0; a wrong-length buffer → 0.0.
2. **Marked real-model calibration test** (`TM_RUN_MODEL_TESTS=1`, skipped in CI): translation pairs
   map high, unrelated low; confirms/tunes `FLOOR`.
3. **`composite_score` 5-axis units:** new `DEFAULT_WEIGHTS`; `semantic` contributes to `mark_score`;
   `mark_strength` reflects `max(phon, sem, vis-if-phash)` (e.g. high semantic + class overlap + low
   phon/vis reaches Possible); verdict-band guards intact; `resolve_weights` renormalises 5 keys and
   still drops invalid/negative.
4. **Golden update:** extend `tests/_similarity_cases.py` `COMPOSITE_CASES` tuples to include a
   `semantic` value (new column) and regenerate `tests/fixtures/similarity_golden.json` `composite`
   under the new weights + math. Add a semantic-input case. `test_score_assembles_result` asserts
   `ScoreResult.semantic`. The `phonetic`/`class`/`vienna` golden arrays stay byte-identical (axis
   functions unchanged).
5. **Route adapters:** a compare/similar request returns a `semantic` field; a mark with NULL
   `mark_embedding` yields `semantic == 0.0` without error.
6. **Frontend:** the semantic row renders on the 3 surfaces (component/render test or the existing
   axis-breakdown test extended); `tsc --noEmit` clean.

## Out of scope (3b-2)

- **No embedding/model work** — the feature store + model live in 3b-1/`api/_embed.py`; the engine
  reads stored bytes only and imports no model.
- **No numpy in `tm_similarity`** — cosine is stdlib `array`; the engine stays stdlib + `jellyfish`.
- **No schema / migration / backfill / ingest change** — read-only consumer of the 3b-1 column.
- **No search-rerank change** — `search.py` phonetic-mode rerank stays as-is; semantic flows through
  `score()` for compare/similar/watchlist surfaces (semantic search/rerank is a separate future
  track if wanted).
- **No new per-matter UI for weights** — `DEFAULT_WEIGHTS` changes; the existing `resolve_weights`
  override path already accepts the 5th key.
- **No pgvector** (the engine scores given pairs; unchanged from 3b-1).

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- `tm_similarity` stays dependency-light (stdlib + `jellyfish`); `semantic.py` is stdlib-only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check
  && pytest` (run BOTH ruff gates; targeted pytest locally). The marked real-model test is excluded
  from normal CI.
- Frontend: `tsc --noEmit` to typecheck; **never `pnpm build` while `pnpm dev` is live**.

## Decomposition (for the plan)

1. **`semantic.py`**: stdlib-`array` cosine + floor mapping + None/length guards; unit tests with
   synthetic vectors; the marked real-model calibration test; `FLOOR` default 0.50.
2. **DTOs + composite + wiring**: `MarkFeatures.mark_embedding`, `ScoreResult.semantic`; 5-axis
   `DEFAULT_WEIGHTS`; `composite_score` semantic arg + `mark_strength`; `resolve_weights` 5th key;
   `score()` threads semantic; `SIMILARITY_VERSION` 1.4; export. Golden regen (COMPOSITE_CASES +
   fixture).
3. **Route adapters**: pass `mark_embedding` at the 4 `MarkFeatures` sites; serialize `semantic`;
   NULL-embedding → 0.0 test.
4. **Frontend**: semantic axis row on compare / mark detail / watchlists; `tsc --noEmit`.
5. **Docs sync**: CLAUDE.md (semantic axis note — version 1.4, 5-axis weights, floor calibration,
   stdlib cosine, consumes the 3b-1 store).
