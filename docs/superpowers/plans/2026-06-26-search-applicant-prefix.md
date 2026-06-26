# Mark-only Default Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/search` box search the **mark** by default (name/sample + ID numbers), not the owner — remove `applicant_name` from the default `q` matching in both Text and Phonetic modes. Applicant/class/agent filtering stays available through the existing left-sidebar facets.

**Architecture:** Backend-only behavioral change plus a small frontend copy cleanup. Two backend files (`api/routes/_filters.py`, `api/routes/search.py`) drop every `applicant_name` reference that participates in the **default `q`** path (text recall, phonetic recall + trigram rank, and both `_score` targets). The `applicant`/`nice_class`/`ip_agency` filter params (the sidebar facets) are untouched. The frontend drops "applicant" from the placeholder and removes 3 decorative hint chips so the box no longer implies syntax that doesn't exist. No DB / migration / new param / `tm_similarity` change.

**Tech Stack:** FastAPI + SQLAlchemy (Postgres) backend; Next.js 15 + React + Tailwind 4 (TypeScript) frontend. Backend verify: targeted `pytest` + `ruff check` + `ruff format --check` + `mypy api worker tm_similarity` + `alembic check`. Frontend verify: `tsc --noEmit` + lint.

---

## Background the engineer needs

- **Spec:** `docs/superpowers/specs/2026-06-26-search-applicant-prefix-design.md`.
- **What "default `q`" means:** the free-text box value sent as the `q` query param. Two modes use it: **text** (literal `ILIKE %q%` recall in `build_trademark_where`, scored by the `_score` text branch) and **phonetic** (a two-stage pg_trgm `%` + `dmetaphone` recall in `search.py`, scored by the `_score` phonetic branch). Both currently also match `applicant_name`; this plan removes that.
- **What stays:** the `applicant` filter param (`_filters.py:135-140`, `applicant_name.ilike`), `nice_class` (`118-120`), `ip_agency` (`147-148`). These back the left-sidebar facets and are NOT part of `q`. Do not touch them.
- **Backend location:** `cd app/backend`. Run the dev DB per CLAUDE.md (`docker compose -f app/docker-compose.yml up -d`, then the test env vars). Targeted pytest only — **never the full suite** (it resets the live `domestic_sweep_control` singleton).
- **`tm_similarity` rule:** stdlib + jellyfish only. This plan does NOT change `tm_similarity` — `phonetic_similarity` is called with a different `target` string, nothing more.
- **Frontend location:** `cd app/frontend`. Typecheck `pnpm tsc --noEmit`, lint `pnpm lint`. **NEVER `pnpm build` while `pnpm dev` is live** (clobbers `.next`).
- **GUARDRAILS:** NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` explicit paths only — never `-A`/`.`/`-u`.

## File map

| File | Change |
|---|---|
| `app/backend/api/routes/_filters.py` | remove `applicant_name` from the `q` OR-group (text recall) |
| `app/backend/api/routes/search.py` | drop `applicant_name` from `_score` (text bag + phonetic target) and the phonetic recall `or_` + `greatest` trigram rank |
| `app/backend/tests/test_search_mark_only.py` | new test file — applicant no longer recalls by default; facet still works; mark name still matches |
| `app/frontend/components/search/query-band.tsx` | placeholder drops "applicant"; remove the 3 decorative hint chips |
| `CLAUDE.md` | docs-sync: note the search now matches mark name + IDs only by default |

---

### Task 1: Backend test — applicant no longer recalls by default (RED)

**Files:**
- Create: `app/backend/tests/test_search_mark_only.py`

First inspect an existing search test to copy the seeding + client fixtures (do NOT invent a harness):

- [ ] **Step 1: Read an existing search test for the fixture pattern**

Run: `ls app/backend/tests | grep -i search` then read the most relevant one (e.g. `app/backend/tests/test_search_mark_name_recall.py` if it exists, else `test_search*.py`). Note exactly how it: (a) gets an async client, (b) seeds a `Trademark` row into the test session, (c) calls `GET /api/v1/search/trademarks`. Reuse those helpers/fixtures verbatim — the snippet below is illustrative and MUST be adapted to the real fixtures.

- [ ] **Step 2: Write the failing tests**

Create `app/backend/tests/test_search_mark_only.py`. Adapt the seeding/client calls to match the fixtures found in Step 1. The intent of each test is fixed; the plumbing follows the existing suite.

```python
"""Mark-only default search: `q` matches the mark (name/sample + IDs), not the owner.

See docs/superpowers/specs/2026-06-26-search-applicant-prefix-design.md.
"""

from __future__ import annotations

import pytest

# NOTE: import the SAME async-client + session-seeding fixtures the other
# tests/test_search_*.py modules use. Adapt seed_trademark(...) to the real helper.


@pytest.mark.asyncio
async def test_applicant_not_recalled_by_default_text(client, seed_trademark) -> None:
    # mark_sample empty, name is WIDGET, owner is ACMECORP.
    await seed_trademark(applicant_name="ACMECORP", mark_name="WIDGET", mark_sample=None)
    r = await client.get("/api/v1/search/trademarks", params={"q": "acmecorp", "mode": "text"})
    assert r.status_code == 200
    assert r.json()["total"] == 0  # owner text no longer matches the default box


@pytest.mark.asyncio
async def test_applicant_not_recalled_by_default_phonetic(client, seed_trademark) -> None:
    await seed_trademark(applicant_name="ACMECORP", mark_name="WIDGET", mark_sample=None)
    r = await client.get("/api/v1/search/trademarks", params={"q": "acmecorp", "mode": "phonetic"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_applicant_facet_still_filters(client, seed_trademark) -> None:
    await seed_trademark(applicant_name="ACMECORP", mark_name="WIDGET", mark_sample=None)
    # The sidebar facet param is unchanged — owner is still reachable via `applicant=`.
    r = await client.get("/api/v1/search/trademarks", params={"applicant": "acmecorp", "mode": "text"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_mark_name_still_matches(client, seed_trademark) -> None:
    await seed_trademark(applicant_name="ACMECORP", mark_name="WIDGET", mark_sample=None)
    r = await client.get("/api/v1/search/trademarks", params={"q": "widget", "mode": "text"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_fresh_ingest_mark_sample_still_matches(client, seed_trademark) -> None:
    # Augment-not-swap safety: a fresh-ingest mark (mark_sample set, mark_name NULL)
    # is still found by its sample — proves mark_sample recall is intact.
    await seed_trademark(applicant_name="OTHERCO", mark_name=None, mark_sample="FOOBRAND")
    r = await client.get("/api/v1/search/trademarks", params={"q": "foobrand", "mode": "text"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1
```

- [ ] **Step 3: Run the tests, confirm they fail for the right reason**

Run (with the test DB env vars from CLAUDE.md):
```bash
cd app/backend && python -m pytest tests/test_search_mark_only.py -v
```
Expected: `test_applicant_not_recalled_by_default_text` and `..._phonetic` FAIL (they return `total >= 1` today because applicant still matches). The facet / mark-name / fresh-ingest tests should already PASS. If the two applicant tests pass before any code change, the seeding is wrong (the applicant isn't actually being matched) — fix the fixture before continuing.

---

### Task 2: Backend — drop `applicant_name` from the default `q` path (GREEN)

**Files:**
- Modify: `app/backend/api/routes/_filters.py`
- Modify: `app/backend/api/routes/search.py`

- [ ] **Step 1: `_filters.py` — remove applicant from the text `q` OR-group**

In `build_trademark_where` (the `if q and exclude != "q":` block, ~lines 104-115), delete the `applicant_name` line so the OR-group is mark + IDs only.

Before:
```python
        where.append(
            or_(
                func.lower(Trademark.applicant_name).like(like),
                func.lower(Trademark.mark_sample).like(like),
                func.lower(Trademark.mark_name).like(like),
                Trademark.application_number.ilike(like),
                Trademark.certificate_number.ilike(like),
                Trademark.madrid_number.ilike(like),
            )
        )
```
After:
```python
        where.append(
            or_(
                func.lower(Trademark.mark_sample).like(like),
                func.lower(Trademark.mark_name).like(like),
                Trademark.application_number.ilike(like),
                Trademark.certificate_number.ilike(like),
                Trademark.madrid_number.ilike(like),
            )
        )
```

- [ ] **Step 2: `search.py` `_score` — phonetic target drops applicant fallback**

In `_score`, the phonetic branch (~line 97):
```python
        target = mark.mark_sample or mark.mark_name or mark.applicant_name
```
becomes:
```python
        target = mark.mark_sample or mark.mark_name or ""
```
(Empty string, not `None` — `phonetic_similarity` takes a `str`. A mark with neither name scores ~0 against any query, which is correct: a nameless mark has no name to sound like.)

Also update the comment just above it so it no longer says "fall back to applicant_name" — replace the `# Compare against the wordmark first, / fall back to applicant_name only when…` lines with: `# Compare against the resolved mark name (mark_sample → mark_name); a mark / with no transcribed name scores ~0 (nothing to sound like).`

- [ ] **Step 3: `search.py` `_score` — text bag drops applicant**

In the text branch (~lines 131-140), remove `applicant_name` from `bag` (keep `wordmark` as-is — it's already `mark_sample or mark_name`):

Before:
```python
        wordmark = (mark.mark_sample or mark.mark_name or "").lower()
        bag = " ".join(
            t
            for t in (
                (mark.mark_sample or "").lower(),
                (mark.mark_name or "").lower(),
                (mark.applicant_name or "").lower(),
            )
            if t
        )
```
After:
```python
        wordmark = (mark.mark_sample or mark.mark_name or "").lower()
        bag = " ".join(
            t
            for t in (
                (mark.mark_sample or "").lower(),
                (mark.mark_name or "").lower(),
            )
            if t
        )
```

- [ ] **Step 4: `search.py` phonetic recall — drop applicant arms**

In the `mode == "phonetic" and q` block (~lines 251-260), remove the two `applicant_name` arms from the `or_(...)` recall group. Also update the comment that says "The mark_sample / applicant_name arms are index-backed…" to drop the applicant reference.

Before:
```python
            or_(
                func.lower(Trademark.mark_sample).op("%")(ql),
                func.lower(Trademark.applicant_name).op("%")(ql),
                func.lower(Trademark.mark_name).op("%")(ql),
                func.dmetaphone(func.lower(Trademark.mark_sample)) == dmeta_q,
                func.dmetaphone(func.lower(Trademark.applicant_name)) == dmeta_q,
                func.dmetaphone(func.lower(Trademark.mark_name)) == dmeta_q,
            ),
```
After:
```python
            or_(
                func.lower(Trademark.mark_sample).op("%")(ql),
                func.lower(Trademark.mark_name).op("%")(ql),
                func.dmetaphone(func.lower(Trademark.mark_sample)) == dmeta_q,
                func.dmetaphone(func.lower(Trademark.mark_name)) == dmeta_q,
            ),
```

- [ ] **Step 5: `search.py` phonetic rank — drop applicant from `greatest`**

In the same block (~lines 266-270), remove the `applicant_name` similarity arm from `trgm_rank`. Update the adjacent comment to drop the applicant mention (now "best trigram similarity across mark_sample / mark_name").

Before:
```python
        trgm_rank = func.greatest(
            func.similarity(func.lower(Trademark.mark_sample), ql),
            func.similarity(func.lower(Trademark.applicant_name), ql),
            func.similarity(func.lower(Trademark.mark_name), ql),
        )
```
After:
```python
        trgm_rank = func.greatest(
            func.similarity(func.lower(Trademark.mark_sample), ql),
            func.similarity(func.lower(Trademark.mark_name), ql),
        )
```

- [ ] **Step 6: Run the new tests, confirm GREEN**

Run:
```bash
cd app/backend && python -m pytest tests/test_search_mark_only.py -v
```
Expected: all 5 PASS.

- [ ] **Step 7: Run the existing search tests for no regression**

Run the existing search-related tests (use the names found in Task 1 Step 1):
```bash
cd app/backend && python -m pytest tests/test_search_mark_name_recall.py tests/test_search.py -v
```
(Adjust filenames to those that exist.) Expected: PASS. If a prior test asserted that an applicant query returns rows **via `q`**, that test encoded the old behavior — update it to use the `applicant=` param instead (or assert 0), and note the change in the commit. Do NOT weaken a test that legitimately checks mark/ID recall.

- [ ] **Step 8: Backend lint + type + drift gates**

Run:
```bash
cd app/backend && ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check
```
Expected: all clean. (`alembic check` must stay green — no migration in this change.)

- [ ] **Step 9: Commit**

```bash
git add app/backend/api/routes/_filters.py app/backend/api/routes/search.py app/backend/tests/test_search_mark_only.py
git commit -m "feat(search): mark-only default q — drop applicant_name from text+phonetic matching"
```

---

### Task 3: Frontend — copy cleanup (placeholder + remove decorative chips)

**Files:**
- Modify: `app/frontend/components/search/query-band.tsx`

- [ ] **Step 1: Update the text-mode placeholder**

In `TextSearchInput` (~line 108), the text-mode default placeholder:
```tsx
    : "Trademark name, applicant, mark, application number…";
```
becomes (drop "applicant"):
```tsx
    : "Trademark name, mark, application number…";
```
(Leave the `phonetic` and `vienna` placeholders unchanged.)

- [ ] **Step 2: Remove the decorative hint chips**

Delete the entire `mode === "text"` chip block (~lines 122-130), since those `applicant:` / `class:` / `agent:` `<span>`s are non-functional and now imply box syntax that intentionally doesn't exist:
```tsx
      {mode === "text" && (
        <div className="hidden md:flex items-center gap-1.5 shrink-0">
          {["applicant:", "class:", "agent:"].map((k) => (
            <span key={k} className="font-mono text-[11px] bg-paper-3 border border-line rounded px-1.5 py-0.5 text-mute">
              {k}
            </span>
          ))}
        </div>
      )}
```
Remove the whole block. After removal, the `<form>` ends right after the `<input>`. Verify no now-unused imports remain (`mode` stays used by the placeholder ternary, so it remains a valid prop).

- [ ] **Step 3: Typecheck**

Run: `cd app/frontend && pnpm tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Lint**

Run: `cd app/frontend && pnpm lint`
Expected: clean (no new warnings in `query-band.tsx`).

- [ ] **Step 5: Manual verification (dev app, if running)**

With `pnpm dev` running, open `localhost:3000/search`:
- Text-mode placeholder no longer says "applicant".
- The 3 grey `applicant:` / `class:` / `agent:` chips are gone.
- The left sidebar Applicant / Class / Agent facets still filter as before.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/components/search/query-band.tsx
git commit -m "feat(search): box copy — drop applicant from placeholder, remove decorative hint chips"
```

---

### Task 4: Docs-sync

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "Resolved mark name" search note**

In `CLAUDE.md`, the "Resolved mark name" section currently says search recalls + ranks on `mark_name` "augmenting `mark_sample`/`applicant_name`". Update that sentence to reflect that the **default `q` no longer matches `applicant_name`** — search matches the resolved mark name (`mark_sample`/`mark_name`) + ID numbers; applicant/class/agent filtering is via the left-sidebar facet params (`applicant`/`nice_class`/`ip_agency`), not the free-text box. Keep it to one or two sentences in the existing note; don't restructure the section.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(search): default q is mark-only; applicant/class/agent via sidebar facets"
```

---

### Task 5: Open the PR

- [ ] **Step 1: Push and open the PR**

Push the branch (`search-applicant-prefix`) and open a PR (base `main`) titled **"Search: mark-only default box (drop applicant_name from q)"**.
Body: explains the change (default `q` matched the owner as well as the mark; now matches mark name/sample + IDs only, both Text and Phonetic), that applicant/class/agent filtering is unchanged via the sidebar facets, the frontend copy cleanup, and that there is **no DB/migration/param/`tm_similarity` change**. Note the accepted consequence: a nameless figurative mark (no `mark_sample`, no `mark_name`) is unreachable by free text — reachable via the sidebar facets or an ID. Do NOT merge — the human reviews and squash-merges. After squash-merge, reset local `main` to `origin/main` (stash the rename trio first, pop after).

---

## Self-Review

**1. Spec coverage:**
- Backend remove applicant from default `q` (both modes): Task 2 — `_filters.py` text OR (Step 1), `_score` phonetic target (Step 2) + text bag (Step 3), phonetic recall `or_` (Step 4), phonetic `greatest` rank (Step 5). All five spec bullets in §1 mapped.
- Frontend placeholder + remove chips: Task 3 Steps 1-2. (spec §2)
- "No prefix wiring / no new param / no migration / sidebar facets untouched": no task adds any — `applicant`/`nice_class`/`ip_agency` params explicitly not touched.
- Testing (spec §Testing tests 1-4 + fresh-ingest): Task 1 — 5 tests covering applicant-no-match (text+phonetic), facet-still-works, mark-name-match, fresh-ingest safety.
- Docs-sync: Task 4 (CLAUDE.md "Resolved mark name" note).

**2. Placeholder scan:** The test file body is illustrative-but-complete in intent; Task 1 Step 1 explicitly requires adapting `client`/`seed_trademark` to the real fixtures before running — a deliberate "match the existing harness" instruction, not a TODO. All code edits show full before/after. No "TBD"/"add error handling"/"similar to" placeholders.

**3. Type/identifier consistency:** `target` stays a `str` (`... or ""`, never `None`) for `phonetic_similarity(q, target)`. `bag`/`wordmark` keep their types. `or_`/`func.greatest`/`func.dmetaphone`/`func.similarity` signatures unchanged — only arms removed. `applicant`/`nice_class`/`ip_agency` params and the `applicant_name.ilike` facet clause are referenced as UNCHANGED consistently across the plan. Frontend `mode` prop stays used by the placeholder ternary after the chip block is removed.
