# Mark-only default search + functional field prefixes — Design

**Status:** Approved for planning · 2026-06-26

**Goal:** Make the `/search` box search the **mark** by default (its name/sample + ID numbers), not
the owner. Move applicant matching to an explicit, opt-in **`applicant:` prefix**, and while we're
wiring the prefix parser, make the already-displayed **`class:`** and **`agent:`** hint chips functional
too (they map to existing filter params).

## Why

Today the default `q` matches `mark_sample`, `mark_name`, `applicant_name`, and the ID numbers — so a
query returns marks by their *owner* as well as their *name*, which the user doesn't want. The search
box also shows decorative `applicant:` / `class:` / `agent:` chips that **do nothing** (plain
non-parsed `<span>`s) — typing `applicant:samsung` is sent literally as `q`. This change makes the box
mark-focused and turns those three hints into real field-scoped filters.

## Decisions (settled)

- **Scope: Text AND Phonetic modes** — remove `applicant_name` from the default matching of both.
- **Prefixes: wire all three** — `applicant:`, `class:`, `agent:`.

## Current state

- `api/routes/_filters.py:build_trademark_where` — the default `q` OR-group matches `applicant_name`,
  `mark_sample`, `mark_name`, `application_number`, `certificate_number`, `madrid_number`. It ALSO
  already has separate, working filter params: `applicant` (→ `applicant_name ILIKE`), `nice_class`
  (→ `nice_classes.contains`), `ip_agency` (→ `ip_agency ILIKE`).
- `api/routes/search.py:_score` — text branch scores against `mark_sample`/`mark_name` (wordmark) +
  `applicant_name` (bag); phonetic branch target is `mark_sample or mark_name or applicant_name`.
- `api/routes/search.py` phonetic two-stage recall — trgm `%` + `dmetaphone` + `greatest(similarity)`
  over `mark_sample`, `mark_name`, `applicant_name`.
- Frontend `components/search/query-band.tsx` — the box; the `["applicant:", "class:", "agent:"]`
  chips are decorative `<span>`s. `app/(app)/search/page.tsx` already reads `applicant`/`nice_class`/
  `ip_agency` from the URL and renders removable filter chips for them.

## Resolution

### 1. Backend — drop `applicant_name` from default matching (both modes)

In `api/routes/_filters.py` and `api/routes/search.py`, remove `applicant_name` everywhere it
participates in the **default `q`** path:
- `_filters.py` `build_trademark_where`: remove `func.lower(Trademark.applicant_name).like(like)` from
  the `q` OR-group. (The other fields — `mark_sample`, `mark_name`, the three ID numbers — stay.)
- `search.py` `_score` text branch: drop `applicant_name` from the `bag`.
- `search.py` phonetic recall `or_(...)`: drop `func.lower(Trademark.applicant_name).op("%")(ql)` and
  `func.dmetaphone(func.lower(Trademark.applicant_name)) == dmeta_q`.
- `search.py` phonetic `trgm_rank = func.greatest(...)`: drop `func.similarity(func.lower(Trademark.applicant_name), ql)`.
- `search.py` `_score` phonetic target: `target = mark.mark_sample or mark.mark_name` (no applicant
  fallback).

The `applicant`, `nice_class`, `ip_agency` **filter params are unchanged** — they remain the opt-in.

### 2. Frontend — parse the field prefixes from the box

When the box is submitted (text/phonetic mode), parse the query string into the free-text `q` plus the
field filters, then route them to the existing filter params (so the existing removable chips appear
and the existing backend params apply):

- Recognise `applicant:`, `class:`, `agent:` followed by a whitespace-delimited value token.
  - `applicant:<token>` → set the `applicant` filter (substring).
  - `agent:<token>` → set the `ip_agency` filter (substring).
  - `class:<token>` → set the `nice_class` filter; the token may be comma-separated (`class:9,12` →
    `["9","12"]`); non-numeric class tokens are dropped.
- Whatever remains after stripping the prefixes becomes the free-text `q`.
- Multiple prefixes are allowed in one query; e.g. `class:9 applicant:samsung widget` →
  `nice_class=["9"]`, `applicant="samsung"`, `q="widget"`.
- Multi-word applicant/agent names are matched by **substring**, so a single token usually suffices
  (`applicant:samsung` finds "SAMSUNG ELECTRONICS"); the sidebar Applicant facet remains for exact
  picks. No quoted-string parsing (YAGNI).

The parse happens in the frontend submit/URL-sync path (`app/(app)/search/page.tsx`), reusing the
`applicant`/`nice_class`/`ip_agency` filters it already manages — no new endpoint, no backend prefix
parsing.

### 3. Frontend — placeholder + chips

- Update the box placeholder (currently *"Trademark name, applicant, mark, application number…"*) to
  drop "applicant" and signal the prefixes — e.g. *"Mark name, application number… (applicant:, class:, agent:)"*.
- The three hint chips stay; they now reflect real, working prefixes.

## Components & boundaries

| Unit | Change |
|---|---|
| `api/routes/_filters.py` | remove `applicant_name` from the `q` OR-group |
| `api/routes/search.py` | remove `applicant_name` from `_score` (text bag + phonetic target) and the phonetic recall/rank |
| `app/(app)/search/page.tsx` | parse `applicant:`/`class:`/`agent:` from the box → set existing filters |
| `components/search/query-band.tsx` | placeholder copy |

No DB / migration / new API param / `tm_similarity` change. The `applicant`/`nice_class`/`ip_agency`
params, the sidebar facets, and the removable filter chips already exist and are reused.

## Consequence (accepted)

A mark with **no `mark_sample` and no `mark_name`** (nameless figurative) becomes unsearchable by
typing free text — reachable only via `applicant:` / the sidebar facet / an ID. This is the intended
effect of a mark-only default box.

## Testing (targeted pytest + frontend tsc)

Backend (`tests/test_search_*.py`, seeded marks):
1. **Applicant no longer matches by default:** a mark with `applicant_name="ACMECORP"`, `mark_name="WIDGET"`,
   `mark_sample=NULL` → `q=acmecorp&mode=text` returns NOTHING; `q=acmecorp&mode=phonetic` returns NOTHING.
2. **Applicant param still works:** the same mark IS returned by `applicant=acmecorp` (both modes / filter).
3. **Mark name still matches:** `q=widget&mode=text` still returns the WIDGET mark.
4. **No regression** on the existing `mark_name`/`mark_sample` recall tests (text + phonetic).

Frontend (`tsc --noEmit` + manual): typing `applicant:samsung` sets the Applicant filter (chip appears),
`class:9` sets the class filter, `agent:foo` sets the agency filter; remaining words become `q`.

## Out of scope

- No backend prefix parsing (parsed on the frontend; backend keeps its clean structured params).
- No new filter param, column, migration, or `tm_similarity` change.
- No quoted/multi-word prefix syntax (substring single-token only).
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
2. **Frontend parser**: parse `applicant:`/`class:`/`agent:` → existing filters in `search/page.tsx`;
   placeholder copy in `query-band.tsx`; `tsc --noEmit` + lint.
