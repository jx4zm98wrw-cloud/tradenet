# Mark Embedding Infrastructure (Track 3b-1) — Design

**Status:** Approved for planning · 2026-06-25

**Goal:** Stand up the **feature store** for a future semantic axis: compute a multilingual LaBSE
embedding of each mark's wordmark at ingest, store it per mark, and backfill the corpus — with
**zero scoring change**. This is **Track 3b-1**, the infrastructure half of the semantic-axis epic;
it produces stored vectors that **Track 3b-2** (the semantic axis + 5-axis weight reallocation)
consumes. It follows Track 1's split of the `logo_phash` feature store from the visual routing — the
heavy compute (a model, here) lives in one module on the backfill path, and nothing in the serving
path or the pure engine imports it — but with one deliberate divergence: the embedding is
**backfill-only**, not self-populated at ingest, because its source field (`mark_name`) is itself
backfill-derived (see "Lifecycle" below).

## Why (program context)

The conflict engine scores three mark-similarity dimensions trademark law recognises — **appearance,
sound, and meaning (connotation)**. Tracks 1–3a covered sight (visual pHash routing) and sound
(VN phonetic key + Double Metaphone). **Meaning** is the gap: two marks can be confusingly similar in
concept while diverging in spelling and sound — above all **cross-language translation equivalents**
(`APPLE`↔`TÁO`, `RED BULL`↔`BÒ ĐỎ`), which IP Vietnam examiners weigh. A multilingual sentence
embedding places translation pairs near each other in vector space, so cosine similarity surfaces
them. **LaBSE** (Language-agnostic BERT Sentence Embedding, 109 languages incl. Vietnamese; trained by
translation-pair mining) is purpose-built for exactly this and runs locally — keeping the VN
government data on-prem, the scoring deterministic, and the per-mark cost zero.

3b-1 builds **only the store**. It changes no score, no verdict, no axis. Splitting it out keeps the
~170k-mark backfill and the 470 MB model dependency isolated from the behaviour change, and keeps each
review tractable (the decomposition decision, 2026-06-25).

## Current state (the Track 1 precedent we mirror)

| Track 1 (`logo_phash`) | Track 3b-1 (`mark_embedding`) |
|---|---|
| `api/_phash.py:compute_logo_phash(path) -> str \| None` — the ONLY Pillow importer | `api/_embed.py:compute_mark_embedding(text, *, encoder=None) -> bytes \| None` — the ONLY model importer |
| `trademarks.logo_phash` (hex text) | `trademarks.mark_embedding` (bytea: 768 float32) |
| `scripts/backfill_logo_phash.py` — `PHASH_VERSION=1`, `_CHUNK=1000`, `async backfill_logo_phash(session, *, ids=None) -> dict[str,int]` | `scripts/backfill_mark_embedding.py` — `EMBED_VERSION=1`, same shape |
| self-populated at ingest (source `logo_path` exists at ingest) | **backfill-only** (source `mark_name` is itself backfill-derived — see "Lifecycle") |

No `mark_embedding` exists today. `numpy` is already a dependency; `sentence-transformers`/`torch` are
new.

### Lifecycle: backfill-only (the deliberate divergence from `logo_phash`)

`logo_phash` self-populates at ingest because its source, `logo_path`, is resolved during ingest.
`mark_embedding`'s source is `mark_name` — the resolved display name — which the **ingest worker does
NOT set** (`worker/mapper.py` writes only `mark_sample`; `mark_name` is written by
`scripts/backfill_mark_name.py`, like `vn_grant_date` and the entity-clean columns). Embedding from
`mark_name` at ingest would therefore always be NULL. So `mark_embedding` inherits `mark_name`'s
lifecycle: **populated by its backfill only**, run *after* `backfill_mark_name`. New marks carry NULL
`mark_embedding` until the backfill runs — the identical, already-documented "re-run the backfill
after a fresh ingest" pattern shared by `mark_name`/`vn_grant_date`/entity-clean. There is **no
`worker/ingest.py` change** in 3b-1.

## Resolution

### 1. `api/_embed.py` — the only model importer (mirrors `_phash.py`)

```python
def compute_mark_embedding(text: str | None, *, encoder: Encoder | None = None) -> bytes | None: ...
```

- Embeds the **resolved wordmark text** (`trademarks.mark_name` — the display name fixed by the earlier
  mark-name resolution work; NEVER the applicant). `None`/blank `mark_name` → returns `None` (figurative
  marks with no transcribed name have no embedding, exactly as they have no `logo_phash`).
- Returns the L2-normalised 768-dim vector as **`numpy.float32().tobytes()`** (3072 bytes), the exact
  round-trip form (`numpy.frombuffer(buf, dtype=float32)`); normalising at write time lets 3b-2's
  cosine be a plain dot product.
- **Lazy model load, cached singleton:** the LaBSE model (`sentence-transformers`) is loaded on first
  use and memoised at module level — the same lazy pattern as `_phash` keeping Pillow off the worker
  boot path. The model is NEVER imported by the API routes or `tm_similarity` (the engine reads stored
  bytes only), so the API image and the pure engine stay model-free.
- **Dependency-injected encoder:** `encoder` is an optional callable `(list[str]) -> ndarray`. Default
  `None` → the real cached LaBSE encoder. Tests pass a fake (deterministic stub) so unit tests never
  download or run the 470 MB model. This is the testability seam.

### 2. `trademarks.mark_embedding` — nullable `bytea` column + Alembic migration

A new nullable `bytea` column. **Not pgvector**: the engine scores candidate pairs it is already
handed (the existing search does retrieval), so no DB-side ANN is needed; a serialized blob is
sufficient and avoids committing the deployment to a Postgres extension. (pgvector remains a clean
future option if semantic *search* is ever wanted — out of scope here.) No index (the column is read
by primary-key-scoped joins, never filtered/ordered on).

### 3. `scripts/backfill_mark_embedding.py` — idempotent corpus backfill

Same shape as `backfill_logo_phash.py`: `EMBED_VERSION = 1`, `_CHUNK`, `async def
backfill_mark_embedding(session, *, ids: list[int] | None = None) -> dict[str, int]` returning
`{"scanned", "updated", "unchanged"}`. **Idempotent recompute-and-compare** — recompute each mark's
embedding and write only when the stored bytes differ, so re-runs are no-ops. Scans marks with a
non-NULL `mark_name` (`ids=`-scoped for targeted reruns). Bump `EMBED_VERSION` if the model or
normalisation changes. **Run after `backfill_mark_name`, and re-run after a fresh ingest** (same
caveat as `mark_name`/`vn_grant_date`/entity-clean — all backfill-derived).

## Data flow

```
# ingest is UNCHANGED in 3b-1 (mark_embedding stays NULL on new rows until backfill).
backfill_mark_name(session)        # prerequisite: resolves trademarks.mark_name
backfill_mark_embedding(session, ids=None):
  for each mark with non-NULL mark_name:
      recompute embedding(mark_name); write bytea if changed              # idempotent
# 3b-2 (LATER) reads trademarks.mark_embedding into MarkFeatures and does cosine. NOT in 3b-1.
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `api/_embed.py` | text → normalised 768-float32 bytes; lazy LaBSE; DI encoder seam | `sentence-transformers`, `numpy` (lazy) |
| `trademarks.mark_embedding` (model + migration) | persist the per-mark vector | Alembic / SQLAlchemy |
| `scripts/backfill_mark_embedding.py` | idempotent corpus backfill, `EMBED_VERSION` | `api._embed`, ORM |

`worker/ingest.py`, `tm_similarity/*`, `composite.py`, the API routes, the frontend — **untouched**
(embedding is backfill-only). The semantic axis,
`MarkFeatures` field, `composite_score` reweight, and route adapters are all **Track 3b-2**.

## Versioning

- `EMBED_VERSION = 1` (data-derivation version, like `PHASH_VERSION`). No `SIMILARITY_VERSION` change
  (the engine does not change in 3b-1).

## Testing (targeted pytest only — sweep tests reset the live singleton)

The 470 MB model must NOT run in normal CI. The DI encoder is the seam:

1. **`compute_mark_embedding` units (mocked encoder):** a fake encoder returning a fixed vector →
   assert output is `bytes` of length `768*4`, round-trips via `numpy.frombuffer`, is L2-normalised,
   and that `None`/blank text → `None`. No model load.
2. **Backfill units (mocked encoder):** seed marks, run `backfill_mark_embedding` with a fake encoder
   → assert `scanned`/`updated`/`unchanged` counts; a second run is all-`unchanged` (idempotent);
   `ids=` scoping touches only those rows; NULL-`mark_name` marks get NULL embedding.
3. **Backfill prerequisite/scope:** a mark whose `mark_name` is NULL (not yet name-backfilled) is
   scanned-but-skipped (stays NULL `mark_embedding`); after its `mark_name` is set, the embedding
   backfill populates it — confirming the `backfill_mark_name` → `backfill_mark_embedding` chain.
4. **One marked/optional real-model integration test** (`@pytest.mark.slow` or skipped unless an env
   flag is set): load real LaBSE and assert **cross-lingual ordering** —
   `cos(APPLE, TÁO) > cos(APPLE, CHAIR)` and `cos(RED BULL, BÒ ĐỎ) > cos(RED BULL, TABLE)` — proving
   the model + normalisation produce the intended translation-equivalence signal. NOT run in normal CI.
5. **Migration round-trips:** `alembic upgrade head` then `downgrade -1` cleanly adds/drops the column
   (`alembic check` stays green).

## Out of scope (3b-1)

- **No scoring change** — no `tm_similarity/semantic.py`, no `composite.py` / `DEFAULT_WEIGHTS`
  reweight, no `MarkFeatures.mark_embedding` field, no `score()`/route-adapter change, no
  `SIMILARITY_VERSION` bump. All of that is **Track 3b-2**.
- **No pgvector / no semantic search** — serialized `bytea`, read by id-scoped joins only.
- **No `worker/ingest.py` change / no ingest self-population** — embedding is backfill-only (its
  source `mark_name` is backfill-derived). New marks carry NULL until the backfill runs.
- **No model in the API image or `tm_similarity`** — `_embed.py` is imported only by the backfill
  script (and, in 3b-2, nothing — the engine reads stored bytes).
- **No embedding of goods/classes/applicant** — only the resolved `mark_name` wordmark (the goods axis
  is separate; mixing dilutes the meaning signal).
- No frontend change.

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- The new model dependency (`sentence-transformers`/`torch`) is used ONLY by `api/_embed.py` (ingest +
  backfill). It materially grows the worker image and Trivy-scan time — an accepted, flagged cost.
  `tm_similarity` stays dependency-light (stdlib + `jellyfish`); it gains nothing in 3b-1.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check
  && pytest` (run BOTH ruff gates; targeted pytest locally). The model-loading test is excluded from
  normal CI.
- Frontend unaffected. Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **`api/_embed.py`**: `compute_mark_embedding(text, *, encoder=None)` with the DI seam + lazy cached
   LaBSE loader; unit tests with a fake encoder (shape/normalisation/None); the one marked real-model
   cross-lingual ordering test.
2. **Model + migration**: add nullable `bytea` `trademarks.mark_embedding`; Alembic up/down; model
   attribute; migration round-trip test.
3. **`scripts/backfill_mark_embedding.py`**: `EMBED_VERSION`, chunked idempotent recompute-and-compare,
   non-NULL-`mark_name` scope, `ids=` scoping, stats dict; backfill units with a fake encoder (counts,
   idempotency, scoping, NULL-`mark_name` skip).
4. **Deps + docs**: add `sentence-transformers` to requirements (backfill use only); CLAUDE.md
   (new `mark_embedding` feature-store entry + "backfill-only, run after `backfill_mark_name`,
   re-run after a fresh ingest" caveat + the 3b-1/3b-2 split note).
