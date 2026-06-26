# Search `mark_name` recall fix — Design

**Status:** Approved for planning · 2026-06-26

**Goal:** Make `/search` find a mark by the name a user actually *sees* on the result tile. Today the
text and phonetic search index only `mark_sample` + `applicant_name`, not the resolved display name
`mark_name`. A domestic mark whose name came from enrichment (`mark_sample` empty, `mark_name` filled
from `domestic_records.mark_text`) is invisible to a search for its own displayed name. Add `mark_name`
alongside the existing fields so those marks are recalled and ranked.

## Why (the bug)

Concrete repro: searching `josh` returns 4 marks but **misses `Joshida`** and `alojoshop` — both have
"josh" in their displayed `mark_name`, but their `mark_sample` is empty and their applicant does not
contain "josh", so neither the recall filter nor the scorer ever sees the matching text. Of the 6 marks
whose `mark_name` contains "josh", only the 4 with a matching `mark_sample` *or* applicant are returned
— a ~33% recall gap for this query.

Root cause (verified in `api/routes/search.py` + `api/routes/_filters.py`): `mark_name` appears in **no**
search path. The mark-name resolution work fixed `mark_name` for *display* on every surface but never
extended *search* to index it — CLAUDE.md records this: "Display-only: search ranking still matches
`mark_sample`/`applicant_name` (search.py)." This spec closes that gap.

## Decision: augment, not swap

`mark_name` is a content-superset of `mark_sample` *when populated* (resolution rule:
`mark_sample` non-empty → else `domestic.mark_text` → `madrid.mark_text` → NULL). A pure swap
(`mark_sample` → `mark_name`) would be cleaner but couples search recall to backfill currency: a mark
**ingested after the last `backfill_mark_name` run** has a valid `mark_sample` but NULL `mark_name`, and
a swap would make it unsearchable until the backfill catches up. The project explicitly warns that
backfill-derived columns are often stale between runs. So search **augments**: it considers
`mark_sample` OR `mark_name` (plus `applicant_name`). `mark_sample` always covers fresh ingests;
`mark_name` adds the enrichment-named marks. Where the two are identical (the common case) the extra
clause is harmless — `OR` and `greatest()` just see the same value twice.

## Current state (what the search touches)

- **`api/routes/_filters.py:build_trademark_where`** — builds the shared WHERE, including the literal
  `q` substring filter used by **text mode** recall (over `mark_sample` + `applicant_name` + the ID
  number fields). No `mark_name`.
- **`api/routes/search.py:_score`** — the per-row scorer:
  - text branch (~lines 131-132): `wordmark = mark.mark_sample`; `bag = mark_sample + applicant_name`.
  - phonetic branch (~line 97): `target = mark.mark_sample or mark.applicant_name`.
- **`api/routes/search.py`** phonetic two-stage recall (~lines 244-256): pg_trgm `%` + `dmetaphone`
  equality + `greatest(similarity(...))` over `mark_sample` + `applicant_name` only.
- **Indexes (the precedent to mirror):** migration `20260616_0012` adds a GIN `pg_trgm` index on
  `lower(mark_sample)` (and `lower(applicant_name)`); `20260616_0013` adds the btree `dmetaphone`
  index(es). `mark_name` has neither, so it must get them or recall over it would seq-scan.

## Resolution

### 1. Recall — `build_trademark_where` (text mode)

Add a `lower(mark_name) ILIKE %q%` clause to the existing `q` OR-group (alongside `mark_sample`,
`applicant_name`, and the ID fields). This is what makes `Joshida` a *candidate* at all — without it
the row never passes the WHERE and is 0 results, not merely mis-ranked.

### 2. Recall — phonetic two-stage (`search.py` ~244-256)

Add to the `or_(...)` recall group: `func.lower(Trademark.mark_name).op("%")(ql)` and
`func.dmetaphone(func.lower(Trademark.mark_name)) == dmeta_q`. Add
`func.similarity(func.lower(Trademark.mark_name), ql)` to the `func.greatest(...)` trigram rank so a
`mark_name`-only match can sort to the top.

### 3. Scoring — `_score` (`search.py`)

- text branch: `wordmark = (mark.mark_sample or mark.mark_name or "").lower()`; include `mark_name` in
  `bag`. (Keeps `mark_sample` precedence so existing matches score identically.)
- phonetic branch: `target = mark.mark_sample or mark.mark_name or mark.applicant_name`.

### 4. Indexes — new Alembic migration

Mirror `0012`/`0013` for `mark_name`:
- `GIN (lower(mark_name) gin_trgm_ops)` — backs the `%` recall and `similarity()` rank.
- btree `dmetaphone(lower(mark_name))` — backs the sound-alike recall path.
Additive only — no column, no data change. `alembic upgrade head` / `downgrade -1` round-trip cleanly.

## Components & boundaries

| Unit | Change |
|---|---|
| `api/routes/_filters.py` | `build_trademark_where`: add `mark_name` to the `q` substring OR |
| `api/routes/search.py` | `_score` (text + phonetic targets) + phonetic recall/rank gain `mark_name` |
| new Alembic migration | GIN trgm + btree dmetaphone indexes on `lower(mark_name)` |

`tm_similarity`, the worker, the frontend, `SIMILARITY_VERSION`, and every other route are **untouched**.
No new column (the `mark_name` column already exists, migration `20260624_0028`).

## Testing (targeted pytest only — sweep tests reset the live singleton)

1. **Text recall (the bug):** seed a mark with `mark_sample=NULL`, `mark_name="Joshida"`, an applicant
   without "josh" → `GET /api/v1/trademarks?q=josh&mode=text` returns it. Before the fix it does not.
2. **Phonetic recall:** same mark is returned by `mode=phonetic` for a sound-alike query.
3. **No regression:** an existing `mark_sample`-only mark ("MUJOSH") is still returned and its score is
   unchanged (the `mark_sample`-first precedence preserves existing scoring).
4. **Fresh-ingest safety:** a mark with `mark_sample="FOO"`, `mark_name=NULL` is still found by `q=foo`
   (proves augment, not swap — recall doesn't depend on the name backfill having run).
5. **Migration round-trip:** `alembic upgrade head` then `downgrade -1` add/drop the indexes cleanly;
   `alembic check` stays green.

## Out of scope

- **No swap** (would drop fresh-ingest marks) — augment only.
- **No column / no data backfill** — `mark_name` already exists and is already backfilled; this only
  adds indexes + query clauses.
- **No `tm_similarity` / similarity-engine change** — `/search` is a separate code path from
  compare/watchlist scoring; `SIMILARITY_VERSION` does not move.
- **No image/Vienna mode change** — image is a placeholder; Vienna mode ignores `q`.
- **No frontend change** — the result tiles already render `mark_name`; this only changes which rows
  come back.

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check
  && pytest` (both ruff gates; targeted pytest locally — the full suite resets the live sweep singleton).
- Frontend unaffected. Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **Recall + scoring in `_filters.py` + `search.py`**: add `mark_name` to the text `q` OR, the
   phonetic recall `or_`/`greatest`, and both `_score` targets; tests 1-4 above.
2. **Migration**: GIN trgm + btree dmetaphone indexes on `lower(mark_name)`; migration round-trip test.
3. **Docs**: update the CLAUDE.md "Resolved mark name" note — search now also matches `mark_name`
   (no longer display-only).
