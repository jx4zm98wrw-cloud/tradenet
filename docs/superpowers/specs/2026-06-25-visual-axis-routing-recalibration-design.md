# Visual Axis: specimen-type routing + pHash floor recalibration (Track 1) — Design

**Status:** Approved for planning · 2026-06-25

**Goal:** Stop the conflict scorecard's **Visual** axis from inflating unrelated marks
(the reported `/compare` showing **63% / 59%** between visually-unrelated marks). Two
coordinated fixes inside the now-extracted `tm_similarity/` package: (1) **route the
visual axis by specimen type** — a real figurative device is compared by perceptual
hash, a rendered wordmark-strip is not; and (2) **recalibrate the pHash→score curve**
so two unrelated images score ~0 instead of ~0.50. This is **Track 1** of the
five-axis reliability program; it is the **first behaviour-changing track** (Track 0
was strictly behaviour-preserving).

## Why (program context)

Track 0 carved the engine into `tm_similarity/` and moved the logo pHash into a
`trademarks.logo_phash` feature-store column, but kept every score identical —
including the two visual defects below. The user chose **routing-first, recalibration
folded in** (the deepest fix in one pass) over shipping the cheap recalibration alone.

### The two independent defects

1. **Floor miscalibration.** `visual_similarity`'s pHash branch returns
   `max(0.0, 1.0 - hd / 64.0)`. Two *random* 64-bit perceptual hashes differ in ~32
   bits, so unrelated images floor at `1 - 32/64 = 0.50` — a coin-flip, not zero. The
   meaningful "similar" range on a 64-bit pHash is `hd ≲ 10`; everything past ~22 is
   noise. The curve's midpoint is in the wrong place.

2. **Specimen-type contamination.** Many "logos" in the DB are **wordmark-on-white
   strips** (rendered text), not figurative devices. Their pHash is dominated by a
   shared white background plus a central dark text band, so they cluster artificially
   close to each other and to real logos — and that visual score **double-counts** what
   the phonetic axis already measures. Real systems (WIPO/EUIPO) route by mark type:
   text → phonetic/glyph, figurative → image model.

These fail independently: #1 is a pure-math curve change; #2 needs a classifier. The
chosen design fixes both, with #2 as the backbone and #1 folded into its
figurative-figurative branch.

## Current state (what we're changing)

- `tm_similarity/visual.py` — `visual_similarity(a_phash, b_phash, a_text, b_text)`:
  if both pHashes exist → `1 - hd/64` (`phash`); else typographic Jaro-Winkler on the
  wordmark text (`typographic`); else `0.0` (`none`).
- `tm_similarity/features.py` — `MarkFeatures(mark_text, logo_phash, nice_classes,
  vienna_codes)`.
- `tm_similarity/composite.py` — `composite_score(...)` already consumes
  `visual_confidence`: with `'phash'`, `mark_strength = max(phonetic, visual)` (visual
  is independent evidence); with `'typographic'`/`'none'`, `mark_strength = phonetic`
  only (the typographic visual is JW on the same wordmark text the phonetic axis saw,
  so it must NOT double-count). **No structural change to composite is needed** — the
  routing simply feeds it the right `visual_confidence`.
- `api/_phash.py` — `compute_logo_phash(image_path)` (Pillow + imagehash; the ONLY
  place imaging libraries touch similarity).
- Route adapters build `MarkFeatures` from ORM rows: `marks.py:394/406`,
  `compare.py:159/165`; `search.py` reranks via `visual_similarity` against
  `logo_phash`.

## Resolution

### 1. Specimen classifier → `trademarks.logo_kind` (indexer side)

The two routing signals split across the **index/score boundary**: Vienna-presence is
pure metadata (already in `MarkFeatures`, evaluable at score-time), but the pixel
backstop needs the PNG (index-time only). To keep the engine **filesystem-free**
(Track 0's whole point), fold both into one persisted verdict computed at index-time.

New helper on the indexer side (Pillow-using; lives next to `compute_logo_phash`, e.g.
`api/_phash.py` or a sibling `api/_logo_kind.py` — implementer's call, but it MUST stay
out of `tm_similarity/`):

```python
LogoKind = Literal["figurative", "wordmark"]

def classify_logo_kind(vienna_codes: list[str], image_path: Path | None) -> str | None:
    if vienna_codes:            # (531) present → has a figurative element
        return "figurative"
    if image_path is None:      # no logo at all → no kind
        return None
    return _pixel_backstop(image_path)   # no Vienna but a PNG exists → look at pixels

def _pixel_backstop(png: Path) -> str:   # cheap, deterministic, Pillow-only
    # load → grayscale → measure:
    #   aspect_ratio = width / height
    #   ink_coverage = fraction of non-background (sufficiently dark) pixels
    # wordmark-strip iff aspect_ratio >= AR_MIN and ink_coverage <= INK_MAX
    #   (wide, short, sparse = a text strip) → "wordmark"; else "figurative"
    ...
```

- The **Vienna branch resolves the vast majority** of marks for free (already-extracted
  metadata); the pixel backstop only fires for the **no-Vienna minority** (Madrid marks,
  extraction gaps). Pixel I/O is paid only on that residual.
- `AR_MIN` (provisional ~3.0) and `INK_MAX` (provisional ~0.20) are **finalized
  empirically** against real specimens during implementation, not fixed in this spec.
- `unreadable PNG → return "figurative"` (fail toward keeping the pHash path; a corrupt
  read should not silently suppress a real logo — matches `compute_logo_phash`'s
  fail-soft posture, where an unreadable image yields `logo_phash = None` and the engine
  already falls back to typographic on its own).

### 2. Routing in `visual_similarity` (engine side)

`MarkFeatures` gains `logo_kind: str | None`. `visual_similarity` gains `a_kind`,
`b_kind` and routes:

| `a_kind` × `b_kind` (and pHash availability) | Visual score | Confidence |
|---|---|---|
| both `figurative` **and** both `logo_phash` present | **recalibrated** `max(0, 1 - hd/T)` | `phash` |
| either `wordmark`, or either `logo_phash` missing/`None` | typographic JW on `mark_text` | `typographic` |
| neither side has usable text | `0.0` | `none` |

The **mixed case** (one `figurative`, one `wordmark`) correctly lands in row 2:
comparing a real logo's pHash to rendered text is meaningless, so it routes to text
comparison. This generalises the existing fallback — the `phash` branch now requires
**both** specimens to be genuine figurative devices, not merely both having a hash.

`score(a, b, *, weights)` passes `a.logo_kind`/`b.logo_kind` into `visual_similarity`;
the rest of the orchestration is unchanged.

### 3. Recalibrated curve (the `phash`-`phash` branch only)

```
visual = round(max(0.0, 1.0 - hd / T), 3)      # hd >= T → 0.0
```

- `T` replaces the hard-coded `64`. With `T ≈ 10`, anything past `hd = 10` (including
  the entire unrelated mass around 32) maps to `0`, and only genuinely close hashes
  score. Literature anchors: `hd ≤ 5` ≈ near-duplicate, `hd ≤ 10` ≈ visually similar.
- **`T` is finalized empirically.** The plan's first task measures the Hamming-distance
  distribution over a random sample of real DB pHash pairs, confirms the unrelated mode
  sits ~30-34, and commits that measurement as the artifact justifying the chosen `T`.
  Provisional `T = 10`, exposed as a named module constant (e.g.
  `VISUAL_PHASH_THRESHOLD`) so the calibration is one obvious line, not a magic literal.
- Only the `phash` branch changes. The typographic and none branches are untouched.

## Data flow

```
INDEXER (write features, once — ingest or backfill):
  resolve PNG → compute_logo_phash → trademarks.logo_phash (hex)
             → classify_logo_kind(vienna_codes, PNG) → trademarks.logo_kind

ENGINE (read features, per query — pure, no IO):
  route → MarkFeatures(mark_text, logo_phash, logo_kind, nice_classes, vienna_codes)
        → tm_similarity.score(a, b, weights):
            visual_similarity(a_phash, b_phash, a_kind, b_kind, a_text, b_text)
              → routes (table above) → VisualScore(score, confidence)
            composite_score(..., visual_confidence=confidence)
        → ScoreResult → scorecard / similar / search
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `classify_logo_kind` + `_pixel_backstop` (indexer) | metadata-or-pixel verdict → `logo_kind` | Pillow (kept OUT of `tm_similarity`) |
| migration + `backfill_logo_kind.py` | populate `trademarks.logo_kind` | `classify_logo_kind` |
| `worker/ingest.py` | set `logo_kind` on new ingests | `classify_logo_kind` |
| `tm_similarity/visual.py` | route by kind; recalibrated `phash` curve | stdlib, `jellyfish` |
| `tm_similarity/features.py` | `MarkFeatures` gains `logo_kind` | — |
| route adapters | ORM row → `MarkFeatures(logo_kind=...)`; call `score()` | the package + the column |
| `composite.py` | unchanged (already routes on `visual_confidence`) | — |

## Versioning

- `tm_similarity.SIMILARITY_VERSION`: `"1.0" → "1.1"` (scoring semantics changed).
- New `LOGO_KIND_VERSION = 1` in `backfill_logo_kind.py` (recompute-and-compare guard).
- `PHASH_VERSION` unchanged (the stored hex is unchanged; only its interpretation moves).

## Behaviour change & testing (targeted pytest only — sweep tests reset the live singleton)

This is the **first track that intentionally changes scores.** The discipline:
phonetic / class / vienna golden values stay **frozen** (their code is untouched);
visual + composite values for pHash pairs are **regenerated under the new curve and
reviewed as intentional**.

1. **Calibration measurement (plan Task 1, committed artifact):** a script samples
   random real pHash pairs and reports the Hamming-distance histogram, confirming the
   unrelated mode ~30-34 and justifying the chosen `T`. Output committed alongside the
   spec/plan so the number is reproducible, not asserted.
2. **Curve unit tests:** `hd = 0 → 1.0`; `hd = T → 0.0`; `hd = 32 → 0.0`; strictly
   monotonic non-increasing in `hd`.
3. **Classifier unit tests:** Vienna-present → `figurative` (no image fixture needed —
   pure-data branch); no-Vienna + wide/sparse PNG → `wordmark`; no-Vienna + dense/square
   PNG → `figurative`; no logo → `None`; unreadable PNG → `figurative`.
4. **Routing tests** (`visual_similarity`): both-figurative+both-hash → `phash` with the
   recalibrated value; one-`wordmark` → `typographic`; missing-hash → `typographic`;
   no-text → `none`.
5. **Regression test (the reported bug):** an unrelated figurative pair that scored
   ~0.59-0.63 visual under the old curve now scores low visual → composite verdict
   `Low risk`. This is the regression guard for the `/compare 63%/59%` report.
6. **Golden fixture update:** regenerate the visual + composite columns for pHash pairs
   under the new curve; assert the phonetic / class / vienna columns are byte-identical
   to Track 0's fixture (frozen-axis guard).
7. **Backfill test:** table-driven — mark with Vienna → `figurative`; mark no-Vienna
   with wordmark PNG → `wordmark`; mark with no logo → `None`; second run no-op
   (idempotent).
8. **Route integration** (`compare` / `marks` / `similar` / `search`): stay green;
   updated to assert the new (lower) visual on unrelated pairs rather than the old
   inflated value.

## Out of scope (Track 1)

- **No new weights / no weight reallocation** — `DEFAULT_WEIGHTS` and `composite_score`
  math are untouched; only the visual sub-score and its confidence change. Weight
  reallocation is Track 3.
- **No ML / embeddings / OCR.** The classifier is metadata + a cheap deterministic
  pixel heuristic. Conceptual/semantic axes are Track 3.
- **No re-pHash.** `logo_phash` (and `PHASH_VERSION`) are unchanged; only the
  interpretation curve and the routing move.
- **No `logo_kind` index** — read per-row, never queried by.
- No change to the phonetic axis (Track 2) or the frontend (the scorecard renders
  whatever the routes return; `ScoreResult` keeps the same fields).

## Constraints

- **One migration** (`alembic check` requires it). NEVER commit the rename trio
  (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit
  paths only.
- `tm_similarity` stays **dependency-light** (stdlib + `jellyfish`): the pixel backstop
  and `classify_logo_kind` live on the **indexer** side, never imported by the package.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity
  && alembic check && pytest` (targeted pytest locally).
- Re-run `scripts/backfill_logo_kind.py` after a fresh ingest/enrichment (same
  operational caveat as `logo_phash` / `mark_name` / `vn_grant_date`).
- Frontend: unaffected. Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **Calibrate `T`:** measure the Hamming-distance distribution over sampled real pHash
   pairs; commit the artifact; set `VISUAL_PHASH_THRESHOLD`.
2. **Recalibrate the curve:** swap `1 - hd/64` for `1 - hd/T` in `visual.py`'s `phash`
   branch (still kind-agnostic at this step); curve unit tests; regenerate golden
   visual/composite for pHash pairs; assert frozen axes unchanged.
3. **Classifier:** `classify_logo_kind` + `_pixel_backstop` (indexer side); unit tests
   (Vienna branch fixture-free; backstop with PNG fixtures).
4. **Feature-store:** migration `trademarks.logo_kind`; `backfill_logo_kind.py`
   (`LOGO_KIND_VERSION`); ingest wiring; backfill test; run the backfill.
5. **Route by kind:** `MarkFeatures.logo_kind`; `visual_similarity` gains `a_kind`/
   `b_kind` and the routing table; `score()` threads `logo_kind`; route adapters build
   `MarkFeatures(logo_kind=...)`; routing + regression + route-integration tests; bump
   `SIMILARITY_VERSION` to `"1.1"`.
6. **Docs sync:** CLAUDE.md (the similarity engine note + the new backfill re-run
   caveat).
