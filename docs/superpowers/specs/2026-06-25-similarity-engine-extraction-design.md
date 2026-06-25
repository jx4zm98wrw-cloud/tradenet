# Similarity Engine Extraction — standalone `tm_similarity/` package + pHash feature-store (Track 0) — Design

**Status:** Approved for planning · 2026-06-25

**Goal:** Carve the trademark conflict-similarity engine out of `app/backend/api/similarity.py` into a **standalone, dependency-light package `tm_similarity/`** (stdlib + `jellyfish` only) with a pure data-in/scores-out contract, and **decouple it fully from the filesystem** by precomputing the logo pHash once (feature-store) into a `trademarks.logo_phash` column. **Behaviour-preserving: every score is identical before and after** (golden test). This is Track 0 of a five-axis reliability program; the pHash-floor fix and new axes (visual routing, phonetic-VN, conceptual, goods-relatedness) land *inside* this package in later tracks.

## Why (program context)

The conflict scorecard improves reliability along five axes (visual, phonetic, class, vienna, + new conceptual). Before improving any axis we extract the engine so each later track edits one focused file in an independently-testable, independently-deployable module, and so Track 3's heavy ML (multilingual embeddings) never bloats the web/worker images. The user chose **Option A** (in-process package now, microservice deferred) and **LC1** (extraction + pHash feature-store → full filesystem independence, minimal schema).

## Current state (what we're moving)

`api/similarity.py` imports only stdlib (`re`, `unicodedata`, `dataclasses`, `pathlib`, `typing`) + `jellyfish` — **zero** FastAPI/SQLAlchemy/ORM coupling. It is orchestrated by `api/routes/marks.py`, `compare.py`, `search.py`, which pull ORM rows and pass primitives. The **only** infrastructure coupling: `visual_similarity(..., image_root)` reads logo PNGs from disk via `_phash_for()` (Pillow → `imagehash.phash` → 64-bit hash → Hamming distance → `1 - hd/64`), cached in a module-level dict. The other axes (`phonetic_similarity`, `class_overlap`, `vienna_overlap`, `composite_score`) are already pure.

## Resolution

### 1. The package `app/backend/tm_similarity/`

Sibling to `tm_extractor/`, `madrid_enrich/`, `domestic_enrich/` (existing vendored-package idiom). Organised by axis so each future track touches one file:

```
tm_similarity/
  __init__.py     # public API + version (the only import surface for callers)
  features.py     # MarkFeatures DTO + ScoreResult DTO (pure dataclasses, no ORM)
  phonetic.py     # phonetic_similarity, _token_jw, normalize_vn (moved verbatim)
  visual.py       # visual_similarity (now hex-pHash Hamming + typographic fallback; NO filesystem)
  classes.py      # class_overlap, vienna_overlap (moved verbatim)
  composite.py    # composite_score + weights (DEFAULT_WEIGHTS, resolve_weights) (moved verbatim)
```

**Public API (`__init__.py`):**
```python
SIMILARITY_VERSION: str = "1.0"                       # bump when scoring semantics change
score(a: MarkFeatures, b: MarkFeatures, *, weights: dict[str, float] | None = None) -> ScoreResult
# re-exports used directly by callers / future tracks:
phonetic_similarity, composite_score, visual_similarity, class_overlap, vienna_overlap,
resolve_weights, MarkFeatures, ScoreResult, VisualScore, CompositeScore, VisualConfidence
```

**DTOs (`features.py`):**
```python
@dataclass(frozen=True)
class MarkFeatures:
    mark_text: str | None       # resolved name (mark_name ?? mark_sample); NEVER the applicant
    logo_phash: str | None      # 16-char hex pHash, precomputed; None = no usable logo
    nice_classes: list[int]
    vienna_codes: list[str]

@dataclass(frozen=True)
class ScoreResult:              # everything the scorecard needs, assembled once
    composite: float
    verdict: str                # "Likely conflict" | "Possible conflict" | "Low risk"
    verdict_tone: str           # "stamp" | "warn" | "ok"
    phonetic: float
    visual: float
    visual_confidence: str      # "phash" | "typographic" | "none"
    class_overlap: float
    vienna_overlap: float
```

`score()` orchestrates: compute each axis from the two `MarkFeatures`, call `composite_score`, and bundle the sub-scores + verdict + visual confidence into one `ScoreResult`. This replaces the manual per-axis assembly currently duplicated across the three routes.

### 2. Visual axis: hex-pHash Hamming, no filesystem (`visual.py`)

```python
def visual_similarity(a_phash, b_phash, a_text, b_text) -> VisualScore:
    if a_phash and b_phash:
        hd = bin(int(a_phash, 16) ^ int(b_phash, 16)).count("1")   # Hamming on 64-bit hex
        return VisualScore(round(max(0.0, 1.0 - hd / 64.0), 3), "phash")   # SAME formula (floor fix = Track 1)
    # typographic JW fallback on the wordmark text — unchanged
    ...
```
No Pillow, no `imagehash`, no `Path`, no module-level `_phash_cache`. The formula `1 - hd/64` is **unchanged** (recalibration is Track 1). `imagehash` subtraction is itself popcount-of-XOR, so `bin(int(a,16) ^ int(b,16)).count("1")` reproduces the exact Hamming distance the old `ha - hb` produced → identical scores.

### 3. pHash computation lives OUTSIDE the package (`api/_phash.py`)

```python
# api/_phash.py — imports Pillow + imagehash (kept OUT of the pure package)
def compute_logo_phash(image_path: Path) -> str | None:
    try:
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))   # 16-char hex, imagehash's native serialization
    except Exception:
        return None                            # corrupt/missing → NULL → engine uses typographic fallback
```
Used by the backfill and the ingest worker (the "indexer" side). The package only *consumes* the hex string — the classic feature-store split: indexers write features, the engine reads them.

### 4. Schema + backfill (feature-store)

- **Migration:** `ALTER TABLE trademarks ADD COLUMN logo_phash text NULL`. No index (loaded per-row, never queried by).
- **`scripts/backfill_logo_phash.py`:** idempotent, version-guarded (`PHASH_VERSION`), recompute-and-compare, `ids=`-scoped + stats-dict shape — mirrors `backfill_mark_name.py`. For each mark with a `logo_path`, resolve `image_root / logo_path`, `compute_logo_phash`, store the hex. Marks with no logo → `logo_phash` stays NULL (engine falls back to typographic, exactly as today when `_phash_for` returned None). **Re-run after a fresh ingest** (same caveat as `mark_name` / `vn_grant_date`).
- **Ingest wiring:** in `worker/ingest.py`, after `_resolve_logo_path`, call `compute_logo_phash` on the resolved PNG and set `trademarks.logo_phash` so new ingests populate it without a backfill.

### 5. Route adapters

`marks.py`, `compare.py`, `search.py` build `MarkFeatures` from ORM rows — `mark_text` from the existing resolved-name chain (`mark_name ?? mark_sample`, never applicant), `logo_phash` from the new column, `nice_classes`/`vienna_codes` as today — then call `score()` (or the re-exported axis functions, for `search.py`'s two-stage rerank). The `image_root` argument disappears from all engine call sites.

## Data flow

```
INDEXER (write features, once):
  ingest/backfill → api/_phash.py:compute_logo_phash(PNG) → trademarks.logo_phash (hex)

ENGINE (read features, per query — pure, no IO):
  route → MarkFeatures(mark_text, logo_phash, nice_classes, vienna_codes)
        → tm_similarity.score(a, b, weights) → ScoreResult → scorecard / similar / search
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `tm_similarity/` | pure scoring: features in → ScoreResult out | stdlib, `jellyfish` only |
| `api/_phash.py` | compute hex pHash from a PNG | Pillow, `imagehash` |
| migration + `backfill_logo_phash.py` | populate `trademarks.logo_phash` | `api/_phash.py` |
| `worker/ingest.py` | populate pHash on new ingests | `api/_phash.py` |
| route adapters | ORM row → `MarkFeatures`; call `score()` | the package + the column |

## Behaviour preservation & testing (targeted pytest only — sweep tests reset the live singleton)

1. **Golden fixture (capture FIRST, before moving code):** a script/test computes `(composite, verdict, sub-scores, visual_confidence)` for ~20 representative mark pairs using the **current** `api/similarity.py`, written to `tests/fixtures/similarity_golden.json`. Pairs span: both-logo, one-logo, no-logo, same-class, cross-class, identical-wordmark, unrelated.
2. **Equivalence test:** after extraction, `tm_similarity.score()` (fed `MarkFeatures` built from the same inputs, with `logo_phash` = the stored hex from `compute_logo_phash`) reproduces every golden value exactly.
3. **pHash parity test:** for a real specimen pair, assert `Hamming(stored_hex_a, stored_hex_b) == (imagehash.phash(img_a) - imagehash.phash(img_b))` — proves precompute equals live compute.
4. **Backfill test:** table-driven — mark with logo → hex set; mark without logo → NULL; second run no-op (idempotent).
5. **Route tests:** existing `marks` / `compare` / `search` / `similar` tests stay green (the adapter is behaviour-neutral).

## Out of scope (Track 0 — strictly behaviour-preserving)

- **No score change:** the `1 - hd/64` floor stays; recalibration is **Track 1**.
- No new axes (visual routing, conceptual, goods-relatedness), no embeddings, no weight reallocation, no microservice. Those are Tracks 1–3.
- No `gin_trgm`/`pgvector`/feature-table — only the single `logo_phash` column (embedding storage is designed in Track 3 alongside the model choice).

## Constraints

- **One migration** (`alembic check` requires it). NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- **Packaging:** add `tm_similarity` to the editable-install packages in `app/backend/pyproject.toml`, and extend the CI type-check target from `mypy api worker` to `mypy api worker tm_similarity`.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check && pytest` (targeted pytest locally).
- Frontend: unaffected (the scorecard renders whatever the routes return; `ScoreResult` carries the same fields the payloads already expose). Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **Capture the golden fixture** from the current `api/similarity.py` (the behaviour baseline). Commit the fixture.
2. **Create the package:** move `similarity.py` logic into `tm_similarity/{phonetic,classes,composite}.py` verbatim; add `features.py` (DTOs) + `__init__.py` (API + `SIMILARITY_VERSION`); add `tm_similarity` to pyproject + mypy target. Equivalence test green (still filesystem pHash at this step via a temporary shim, or fold step 3 in).
3. **Feature-store:** migration `trademarks.logo_phash`; `api/_phash.py`; `backfill_logo_phash.py`; ingest wiring. Run backfill.
4. **Switch visual axis to hex-pHash** in `tm_similarity/visual.py` (no filesystem); update route adapters to build `MarkFeatures` with `logo_phash` and call `score()`; remove `image_root`/`_phash_cache`. Golden + pHash-parity + route tests green.
5. **Delete** the old `api/similarity.py` (now fully replaced); confirm all imports point at `tm_similarity`.
