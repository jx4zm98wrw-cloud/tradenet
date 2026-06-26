# Search `mark_name` Recall Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/search` find a mark by its resolved display name (`mark_name`), not just `mark_sample`/`applicant_name`, so enrichment-named marks (e.g. `Joshida`/`TRADAGUI` with an empty `mark_sample`) are recalled and ranked.

**Architecture:** Augment — wherever the search considers `mark_sample`, also consider `mark_name`, in both text and phonetic modes (recall + scoring). Back the new recall paths with GIN-trgm + dmetaphone indexes on `lower(mark_name)`, mirroring migrations `0012`/`0013` for `mark_sample`.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Postgres (pg_trgm, fuzzystrmatch); pytest (httpx ASGI). No `tm_similarity`, no frontend.

---

## Background the engineer needs

- Run from `app/backend` with the venv: `cd app/backend && source ../.venv/bin/activate`. The dev DB is Postgres on `localhost:5435` (compose). Run **targeted** pytest only (the full suite resets a live sweep singleton).
- Spec: `docs/superpowers/specs/2026-06-26-search-mark-name-recall-design.md`.
- The search endpoint is `GET /api/v1/search/trademarks` (params: `q`, `mode` ∈ text|phonetic|image|vienna, `threshold`, `gazette_id`, …).
- `mark_name` is a content-superset of `mark_sample` *when populated*; **augment, never swap** (a fresh-ingest mark has `mark_sample` but NULL `mark_name` until `backfill_mark_name` runs — a swap would drop it from search).
- pg_trgm `%` and `dmetaphone()` work as soon as their extensions exist (already installed by `0012`/`0013`); the new indexes only make recall *fast*, so the behavioral tests in Task 1 pass before the migration in Task 2.
- **GUARDRAILS:** NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` explicit paths only — never `-A`/`.`/`-u`. Both ruff gates (`ruff check` AND `ruff format --check`). `mypy api worker tm_similarity` + `alembic check` must stay green.

## File map

| File | Change |
|---|---|
| `app/backend/api/routes/_filters.py` | `build_trademark_where`: add `lower(mark_name) LIKE %q%` to the `q` OR (text-mode recall) |
| `app/backend/api/routes/search.py` | `_score` text + phonetic targets, and phonetic two-stage recall/rank, gain `mark_name` |
| `app/backend/tests/test_search_mark_name.py` | extend seed + add recall tests |
| `app/backend/alembic/versions/20260626_0032_mark_name_recall_indexes.py` | new migration: GIN trgm + dmetaphone indexes on `lower(mark_name)` |
| `CLAUDE.md` | "Resolved mark name" note: search now matches `mark_name` (no longer display-only) |

---

### Task 1: Add `mark_name` to recall + scoring

**Files:**
- Modify: `app/backend/tests/test_search_mark_name.py`
- Modify: `app/backend/api/routes/_filters.py`
- Modify: `app/backend/api/routes/search.py`

- [ ] **Step 1: Extend the seed fixture with a fresh-ingest mark, and add the failing recall tests**

In `app/backend/tests/test_search_mark_name.py`, add a second mark UUID near the top:

```python
_MARK2 = uuid.UUID("e0000000-0000-4000-8000-0000000000c3")
```

Inside the `seed` fixture, after the existing `s.add(Trademark(... id=_MARK1 ...))` block (the `TRADAGUI`,
`mark_sample=None` mark) and before `await s.commit()`, add a fresh-ingest mark (has `mark_sample`, no
`mark_name` yet):

```python
        # Fresh-ingest mark: has a wordmark but its mark_name hasn't been backfilled yet.
        s.add(
            Trademark(
                id=_MARK2,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="MN-2099-2",
                mark_sample="FRESHWIDGET",
                mark_name=None,
                applicant_name="ACME CO",
                publication_date_441=date(2099, 1, 1),
            )
        )
```

Then append these tests to the file:

```python
@pytest.mark.asyncio
async def test_text_search_finds_mark_name_only_mark(client: AsyncClient) -> None:
    # TRADAGUI lives only in mark_name (mark_sample is NULL, applicant has no "tradagui").
    # Before this fix the search indexed only mark_sample/applicant_name → 0 hits.
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "tradagui", "mode": "text", "threshold": 0.4, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    appnos = [it["mark"]["application_number"] for it in r.json()["items"]]
    assert "MN-2099-1" in appnos


@pytest.mark.asyncio
async def test_phonetic_search_finds_mark_name_only_mark(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "tradagui", "mode": "phonetic", "threshold": 0.4, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    appnos = [it["mark"]["application_number"] for it in r.json()["items"]]
    assert "MN-2099-1" in appnos


@pytest.mark.asyncio
async def test_text_search_still_finds_mark_sample_only_mark(client: AsyncClient) -> None:
    # Augment, not swap: a fresh-ingest mark (mark_sample set, mark_name NULL) must still be found.
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "freshwidget", "mode": "text", "threshold": 0.4, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    appnos = [it["mark"]["application_number"] for it in r.json()["items"]]
    assert "MN-2099-2" in appnos
```

- [ ] **Step 2: Run the new tests to confirm the recall tests fail**

Run: `pytest tests/test_search_mark_name.py -q`
Expected: `test_text_search_finds_mark_name_only_mark` and `test_phonetic_search_finds_mark_name_only_mark`
FAIL (MN-2099-1 not in results); `test_text_search_still_finds_mark_sample_only_mark` and the existing
serialization test PASS.

- [ ] **Step 3: Add `mark_name` to the text-mode recall filter (`_filters.py`)**

In `app/backend/api/routes/_filters.py`, the `q` block (currently lines ~104-113) is:

```python
    if q and exclude != "q":
        like = f"%{q.lower()}%"
        where.append(
            or_(
                func.lower(Trademark.applicant_name).like(like),
                func.lower(Trademark.mark_sample).like(like),
                Trademark.application_number.ilike(like),
                Trademark.certificate_number.ilike(like),
                Trademark.madrid_number.ilike(like),
            )
        )
```

Add the `mark_name` clause inside the `or_(...)`:

```python
    if q and exclude != "q":
        like = f"%{q.lower()}%"
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

- [ ] **Step 4: Add `mark_name` to the phonetic two-stage recall + rank (`search.py`)**

In `app/backend/api/routes/search.py`, the phonetic recall `or_(...)` (currently ~lines 243-248) becomes:

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

and the `trgm_rank = func.greatest(...)` (currently ~lines 253-256) becomes:

```python
        trgm_rank = func.greatest(
            func.similarity(func.lower(Trademark.mark_sample), ql),
            func.similarity(func.lower(Trademark.applicant_name), ql),
            func.similarity(func.lower(Trademark.mark_name), ql),
        )
```

- [ ] **Step 5: Add `mark_name` to both `_score` targets (`search.py`)**

In `_score`, the phonetic branch target (currently ~line 97):

```python
        target = mark.mark_sample or mark.mark_name or mark.applicant_name
```

and the text branch (currently ~lines 131-132):

```python
        wordmark = (mark.mark_sample or mark.mark_name or "").lower()
        bag = " ".join(
            t for t in ((mark.mark_sample or "").lower(), (mark.mark_name or "").lower(), (mark.applicant_name or "").lower()) if t
        )
```

(The `mark_sample`-first precedence keeps existing matches scoring identically; `mark_name` only adds reach.)

- [ ] **Step 6: Run the tests — all pass**

Run: `pytest tests/test_search_mark_name.py -q`
Expected: PASS (all tests, including the two previously-failing recall tests).

- [ ] **Step 7: Run the broader search suite for no regressions**

Run: `pytest tests/test_search_filter_only.py tests/test_search_number_score.py tests/test_search_granted.py tests/test_vienna_search.py -q`
Expected: PASS (the `mark_sample`-first precedence + augment means existing behavior is unchanged).

- [ ] **Step 8: Commit**

```bash
git add app/backend/api/routes/_filters.py app/backend/api/routes/search.py app/backend/tests/test_search_mark_name.py
git commit -m "feat(search): recall + rank marks by resolved mark_name (augment)"
```

---

### Task 2: Index migration for `mark_name` recall

**Files:**
- Create: `app/backend/alembic/versions/20260626_0032_mark_name_recall_indexes.py`

- [ ] **Step 1: Create the migration (mirrors 0012 + 0013 for mark_name)**

Create `app/backend/alembic/versions/20260626_0032_mark_name_recall_indexes.py`:

```python
"""mark_name recall indexes: GIN trgm + dmetaphone on lower(mark_name).

Backs the search recall/rank paths added alongside mark_sample/applicant_name so a
mark found only by its resolved display name doesn't seq-scan. Mirrors 0012 (pg_trgm)
and 0013 (dmetaphone). Additive — no column, no data change.
"""

from __future__ import annotations

from alembic import op

revision: str = "20260626_0032"
down_revision: str | None = "20260625_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_name_trgm "
        "ON trademarks USING gin (lower(mark_name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_name_dmeta "
        "ON trademarks (dmetaphone(lower(mark_name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_name_dmeta")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_name_trgm")
```

- [ ] **Step 2: Apply + round-trip the migration**

Run:
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```
Expected: each completes without error; the two `ix_trademarks_mark_name_*` indexes are created, dropped, recreated.

- [ ] **Step 3: Confirm no model drift**

Run: `alembic check`
Expected: "No new upgrade operations detected." (raw-SQL functional indexes aren't in the ORM metadata, so no drift — same as `0012`/`0013`.)

- [ ] **Step 4: Commit**

```bash
git add app/backend/alembic/versions/20260626_0032_mark_name_recall_indexes.py
git commit -m "feat(search): GIN trgm + dmetaphone indexes on lower(mark_name)"
```

---

### Task 3: Docs + full CI gate + PR

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "Resolved mark name" note in CLAUDE.md**

In `CLAUDE.md`, find the sentence in the `### Resolved mark name` section:
`Display-only: search ranking still matches \`mark_sample\`/\`applicant_name\` (search.py).`
Replace it with:

```markdown
Search now ALSO recalls + ranks on `mark_name` (augmenting `mark_sample`/`applicant_name` in
`build_trademark_where` + `search.py`, backed by GIN-trgm + dmetaphone indexes on `lower(mark_name)`,
migration `20260626_0032`), so a mark found only by its resolved display name (e.g. `Joshida`, empty
`mark_sample`) is no longer missed. Augment (not swap) keeps fresh-ingest marks (NULL `mark_name`)
searchable via `mark_sample`.
```

- [ ] **Step 2: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs(search): mark_name is now searchable, not display-only"
```

- [ ] **Step 3: Run the full backend CI gate locally**

```bash
cd app/backend && source ../.venv/bin/activate
ruff check .
ruff format --check .
mypy api worker tm_similarity
alembic check
pytest tests/test_search_mark_name.py tests/test_search_filter_only.py tests/test_search_number_score.py tests/test_search_granted.py tests/test_vienna_search.py -q
```
Expected: all green. (Targeted pytest — do NOT run the whole suite; it resets the live sweep singleton.)

- [ ] **Step 4: Open the PR**

Push the branch and open a PR (base `main`) titled **"Search: recall marks by resolved mark_name"**.
Body: explains the bug (enrichment-named marks like `Joshida` missed by their own displayed name), the
augment-not-swap decision, the new indexes (migration `20260626_0032`), and that `tm_similarity`/frontend
are untouched. Do NOT merge — the human reviews and squash-merges.

---

## Self-Review

**1. Spec coverage:** text-mode recall (Task 1 Step 3); phonetic recall + rank (Step 4); both `_score`
targets (Step 5); index migration (Task 2); docs (Task 3). Tests cover the bug (text + phonetic recall),
no-regression, and fresh-ingest safety (Task 1 Steps 1-2,6-7). All spec sections mapped.

**2. Placeholder scan:** none — every code block and the migration are literal; exact endpoint, params,
and revision ids included.

**3. Type/identifier consistency:** `mark_name`, `Trademark.mark_name`, `func.lower`, `func.dmetaphone`,
`func.similarity`, `_MARK2`, `MN-2099-2`, revision `20260626_0032` / down `20260625_0031` used
consistently; the migration index names match the `0012`/`0013` naming pattern.
