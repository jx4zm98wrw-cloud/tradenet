# Mark-only default search — Design

**Status:** Approved for planning · 2026-06-26

**Goal:** Make the `/search` box search the **mark** by default (its name/sample + ID numbers), not
the owner. Applicant (and class / agent) filtering stays available via the **existing left-sidebar
facets** — no new search-box syntax is added.

## Why

Today the default `q` matches `mark_sample`, `mark_name`, `applicant_name`, and the ID numbers — so a
query returns marks by their *owner* as well as their *name*, which the user doesn't want. The box
should be **mark-focused**. Filtering by applicant/class/agent is already possible through the
left-sidebar facets (`applicant` / `nice_class` / `ip_agency` filter params), so no opt-in needs to be
built — the only change is to stop matching `applicant_name` in the free-text `q`.

## Scope (settled)

- Remove `applicant_name` from the default `q` matching in **both Text and Phonetic** modes.
- **Do NOT** wire any `applicant:` / `class:` / `agent:` box prefixes — the sidebar facets already
  cover this. (Earlier-considered prefix wiring is dropped.)

## Current state

- `api/routes/_filters.py:build_trademark_where` — the default `q` OR-group matches `applicant_name`,
  `mark_sample`, `mark_name`, `application_number`, `certificate_number`, `madrid_number`. Separate,
  working filter params already exist: `applicant`, `nice_class`, `ip_agency` (the sidebar facets use
  them).
- `api/routes/search.py:_score` — text branch scores against `mark_sample`/`mark_name` (wordmark) +
  `applicant_name` (bag); phonetic branch target is `mark_sample or mark_name or applicant_name`.
- `api/routes/search.py` phonetic two-stage recall — trgm `%` + `dmetaphone` + `greatest(similarity)`
  over `mark_sample`, `mark_name`, `applicant_name`.
- Frontend `components/search/query-band.tsx` — the box placeholder reads *"Trademark name, applicant,
  mark, application number…"*, and shows decorative `["applicant:", "class:", "agent:"]` `<span>` chips
  that do nothing (never parsed).

## Resolution

### 1. Backend — drop `applicant_name` from default matching (both modes)

Remove `applicant_name` everywhere it participates in the **default `q`** path:
- `_filters.py` `build_trademark_where`: remove `func.lower(Trademark.applicant_name).like(like)` from
  the `q` OR-group. (`mark_sample`, `mark_name`, the three ID numbers stay.)
- `search.py` `_score` text branch: drop `applicant_name` from the `bag`.
- `search.py` phonetic recall `or_(...)`: drop `func.lower(Trademark.applicant_name).op("%")(ql)` and
  `func.dmetaphone(func.lower(Trademark.applicant_name)) == dmeta_q`.
- `search.py` phonetic `trgm_rank = func.greatest(...)`: drop `func.similarity(func.lower(Trademark.applicant_name), ql)`.
- `search.py` `_score` phonetic target: `target = mark.mark_sample or mark.mark_name` (no applicant
  fallback).

The `applicant` / `nice_class` / `ip_agency` **filter params are unchanged** — the sidebar facets keep
working exactly as before.

### 2. Frontend — small copy cleanup (so the box doesn't promise applicant search)

- Update the placeholder to drop "applicant" — e.g. *"Trademark name, mark, application number…"*.
- Remove the decorative `applicant:` / `class:` / `agent:` hint chips (lines ~124-126 of
  `query-band.tsx`). They are non-functional `<span>`s and now imply box syntax that intentionally
  doesn't exist — removing them avoids the false affordance.

No new component, state, param, or backend change on the frontend side.

## Components & boundaries

| Unit | Change |
|---|---|
| `api/routes/_filters.py` | remove `applicant_name` from the `q` OR-group |
| `api/routes/search.py` | remove `applicant_name` from `_score` (text bag + phonetic target) and the phonetic recall/rank |
| `components/search/query-band.tsx` | placeholder copy + remove the 3 decorative hint chips |

No DB / migration / new API param / `tm_similarity` change. No prefix parser. The sidebar facets +
`applicant`/`nice_class`/`ip_agency` params already exist and are untouched.

## Consequence (accepted)

A mark with **no `mark_sample` and no `mark_name`** (nameless figurative) becomes unsearchable by typing
free text — reachable only via the sidebar facets / an ID. This is the intended effect of a mark-only
default box.

## Testing (targeted pytest + frontend tsc)

Backend (`tests/test_search_*.py`, seeded marks):
1. **Applicant no longer matches by default:** a mark with `applicant_name="ACMECORP"`, `mark_name="WIDGET"`,
   `mark_sample=NULL` → `q=acmecorp&mode=text` returns NOTHING; `q=acmecorp&mode=phonetic` returns NOTHING.
2. **Applicant facet still works:** the same mark IS returned by the `applicant=acmecorp` param (both modes).
3. **Mark name still matches:** `q=widget&mode=text` still returns the WIDGET mark.
4. **No regression** on the existing `mark_name`/`mark_sample` recall tests (text + phonetic).

Frontend (`tsc --noEmit` + lint + manual): the placeholder no longer says "applicant"; the hint chips
are gone; the sidebar Applicant/Class/Agent facets still filter as before.

## Out of scope

- No box prefix syntax (`applicant:` etc.) — the sidebar facets cover it.
- No new filter param, column, migration, or `tm_similarity` change.
- Image/Vienna modes unchanged.

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check
  && pytest` (both ruff gates; targeted pytest). Frontend: `tsc --noEmit` + lint; never `pnpm build`
  while `pnpm dev` is live.

## Decomposition (for the plan)

1. **Backend**: remove `applicant_name` from the default `q` path in `_filters.py` + `search.py`
   (recall + scoring, both modes); tests 1-4.
2. **Frontend copy**: placeholder + remove the decorative hint chips in `query-band.tsx`; `tsc --noEmit`
   + lint.
