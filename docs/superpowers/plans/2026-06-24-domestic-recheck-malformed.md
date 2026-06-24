# Domestic Re-check Pending + Malformed Surfacing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Full design: `docs/superpowers/specs/2026-06-24-domestic-recheck-malformed-design.md` — read it before each task.

**Goal:** Add an on-demand "re-check all pending" admin control and surface malformed (unmappable) application numbers as their own dashboard bucket, on `/admin/domestic`.

**Architecture:** Backend-only logic in `api/routes/admin.py` (extend the coverage stats; add one POST action mirroring the existing `domestic-sweep` actions) reusing `domestic_not_found` + `appno_to_vnid` — no schema change. Frontend adds a button + a stat card + list on the existing `/admin/domestic` page.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Next.js 15 + React (frontend).

---

## Reference points (read these)

- `app/backend/api/routes/admin.py:110–187` — `DomesticEnrichmentStats` + `domestic_enrichment` endpoint (Task 1 extends these). Also find the existing `domestic-sweep` POST actions in this file (grep `domestic-sweep`) — Task 2 mirrors their `@router.post` + `require_admin` + `get_session` shape.
- `app/backend/worker/domestic_sweep.py:44` `_NOT_FOUND_BACKOFF = timedelta(days=30)`; `:131–146` the `recent_not_found` exclusion; `_real_enqueue()` (the chunk enqueuer). Task 2 imports `_NOT_FOUND_BACKOFF` + `_real_enqueue`.
- `app/backend/domestic_enrich/idmap.py` `appno_to_vnid(appno) -> str | None` — `None` ⇒ malformed.
- `app/backend/api/db/models.py` — `Trademark`, `Gazette`, `DomesticRecord`, `DomesticNotFound`, `DomesticSweepControl`.
- `app/frontend/app/(app)/admin/domestic/page.tsx` — stat cards (`<Stat .../>`, ~112), sweep-control buttons (~209–227), `api.domesticSweep*` calls. `app/frontend/lib/api.ts` — the `domesticSweep*` methods to mirror.

---

## Task 1: Backend — surface malformed appnos in coverage stats

**Files:** Modify `app/backend/api/routes/admin.py`; Test `app/backend/tests/test_admin_domestic_enrichment.py` (create or extend the existing admin-stats test — grep `tests/` for `domestic-enrichment`/`DomesticEnrichmentStats`).

- [ ] **Step 1: Write the failing test** — seed one domestic Trademark with a malformed appno (`4-2024-1`) and one with a good appno (`4-2099-99999`), both un-enriched (no `domestic_records`/`domestic_not_found` rows), then assert the endpoint splits them:

```python
# tests/test_admin_domestic_enrichment.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_malformed_appno_split(admin_client: AsyncClient, seed_domestic):
    # seed_domestic: helper that inserts a gazette + two domestic trademarks:
    #   ("4-2024-1", applicant="SUSHI CO", category="domestic_application")   # malformed (appno_to_vnid None)
    #   ("4-2099-99999", applicant="REAL CO", category="domestic_application") # mappable, unresolved
    await seed_domestic(
        [("4-2024-1", "SUSHI CO"), ("4-2099-99999", "REAL CO")]
    )
    r = await admin_client.get("/api/v1/admin/domestic-enrichment")
    assert r.status_code == 200
    body = r.json()
    assert body["malformed"] == 1
    assert body["unresolved"] == 1  # the mappable one, NOT the malformed one
    names = {m["application_number"] for m in body["malformed_appnos"]}
    assert names == {"4-2024-1"}
    appl = next(m for m in body["malformed_appnos"] if m["application_number"] == "4-2024-1")
    assert appl["applicant_name"] == "SUSHI CO"
```

> Adapt `admin_client` / `seed_domestic` to the repo's existing admin-auth + seeding fixtures (grep `tests/` for how other admin endpoints are tested + how trademarks/gazettes are inserted). If no `seed_domestic` helper exists, insert rows inline with the session fixture.

- [ ] **Step 2: Run → fail**

Run (from `app/backend`, venv `app/.venv`, env `TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm`): `../.venv/bin/pytest tests/test_admin_domestic_enrichment.py -q`
Expected: FAIL — `KeyError: 'malformed'`.

- [ ] **Step 3: Implement** — in `app/backend/api/routes/admin.py`:

Add the import near the top: `from domestic_enrich.idmap import appno_to_vnid`.

Add a schema above `DomesticEnrichmentStats`:

```python
class MalformedAppno(BaseModel):
    application_number: str
    applicant_name: str | None
    gazette: str | None
```

Add two fields to `DomesticEnrichmentStats` (after `unresolved`):

```python
    malformed: int
    malformed_appnos: list[MalformedAppno]
```

In `domestic_enrichment`, after `pending_publication = min(pending_publication, remaining)` and before the `return`, materialize + partition the unresolved set:

```python
    # Materialize the unresolved set (domestic appnos not validated, not recorded
    # not-published) and partition it: appno_to_vnid(appno) is None => malformed
    # (e.g. the truncated "4-2024-1"); else fetchable-unresolved. Cheap — this set
    # is tiny once the sweep has converged.
    unresolved_rows = (
        await session.execute(
            select(Trademark.application_number, Trademark.applicant_name, Gazette.filename)
            .join(Gazette, Gazette.id == Trademark.gazette_id)
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.application_number.is_not(None))
            .where(Trademark.application_number.not_in(select(DomesticRecord.application_number)))
            .where(Trademark.application_number.not_in(select(DomesticNotFound.application_number)))
        )
    ).all()
    seen: set[str] = set()
    malformed_appnos: list[MalformedAppno] = []
    malformed = 0
    fetchable = 0
    for appno, applicant, gazette in unresolved_rows:
        if appno in seen:
            continue
        seen.add(appno)
        if appno_to_vnid(appno) is None:
            malformed += 1
            if len(malformed_appnos) < 50:
                malformed_appnos.append(
                    MalformedAppno(application_number=appno, applicant_name=applicant, gazette=gazette)
                )
        else:
            fetchable += 1
```

Then in the `return DomesticEnrichmentStats(...)`, replace `unresolved=remaining - pending_publication` with:

```python
        unresolved=fetchable,
        malformed=malformed,
        malformed_appnos=malformed_appnos,
```

(Ensure `Gazette` is imported in this module from `api.db.models`.)

- [ ] **Step 4: Run → pass**

Run: `../.venv/bin/pytest tests/test_admin_domestic_enrichment.py -q` → pass.

- [ ] **Step 5: Gates + commit**

```bash
cd app/backend && ../.venv/bin/ruff format api/routes/admin.py tests/test_admin_domestic_enrichment.py \
  && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker
cd ../.. && git add app/backend/api/routes/admin.py app/backend/tests/test_admin_domestic_enrichment.py
git commit -m "feat(domestic): surface malformed appnos in enrichment stats"
```

---

## Task 2: Backend — re-check pending endpoint

**Files:** Modify `app/backend/api/routes/admin.py`; Test `app/backend/tests/test_admin_domestic_recheck.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_domestic_recheck.py
import pytest
from datetime import datetime, UTC, timedelta
from sqlalchemy import select
from api.db.models import DomesticNotFound

@pytest.mark.asyncio
async def test_recheck_pending_resets_backoff(admin_client, db_session, monkeypatch):
    # a recently-checked not_found row (inside the 30d backoff)
    async with db_session() as s:
        s.add(DomesticNotFound(application_number="4-2026-12345", vnid="VN4202612345",
                               first_seen_at=datetime.now(UTC), last_checked_at=datetime.now(UTC), check_count=1))
        await s.commit()
    # stub the enqueue so the test doesn't touch redis
    monkeypatch.setattr("worker.domestic_sweep._real_enqueue", lambda: None)
    r = await admin_client.post("/api/v1/admin/domestic-sweep/recheck-pending")
    assert r.status_code == 200
    assert r.json()["reset"] == 1
    async with db_session() as s:
        row = (await s.execute(select(DomesticNotFound).where(DomesticNotFound.application_number == "4-2026-12345"))).scalar_one()
        # last_checked_at moved back beyond the 30d window -> sweep-eligible again
        assert row.last_checked_at < datetime.now(UTC) - timedelta(days=30)
        assert row.check_count == 1  # history preserved
```

> Adapt fixture names to the repo's admin-auth + async-session test fixtures.

- [ ] **Step 2: Run → fail** — `../.venv/bin/pytest tests/test_admin_domestic_recheck.py -q` → 404/AttributeError.

- [ ] **Step 3: Implement** — in `app/backend/api/routes/admin.py`, add (mirroring the existing `domestic-sweep` actions' decorator + `require_admin`/`get_session` deps):

```python
@router.post("/domestic-sweep/recheck-pending")
async def domestic_sweep_recheck_pending(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Reset the not_found backoff on all unvalidated marks so the sweep re-probes
    them now (instead of waiting out the 30-day window). Preserves check_count /
    first_seen_at. If the sweep is idle, kick one chunk so it actually runs."""
    from datetime import UTC, datetime, timedelta
    from worker.domestic_sweep import _NOT_FOUND_BACKOFF, _real_enqueue

    new_ts = datetime.now(UTC) - (_NOT_FOUND_BACKOFF + timedelta(days=1))
    res = await session.execute(
        update(DomesticNotFound)
        .where(DomesticNotFound.application_number.not_in(select(DomesticRecord.application_number)))
        .values(last_checked_at=new_ts)
    )
    await session.commit()
    reset = res.rowcount or 0
    status = (
        await session.execute(select(DomesticSweepControl.status).where(DomesticSweepControl.id == 1))
    ).scalar_one_or_none()
    if status == "idle":
        await session.execute(
            update(DomesticSweepControl).where(DomesticSweepControl.id == 1).values(
                status="running", started_at=datetime.now(UTC)
            )
        )
        await session.commit()
        _real_enqueue()
    return {"reset": reset}
```

Ensure `update` is imported from sqlalchemy and `DomesticSweepControl` from `api.db.models` (add to existing imports if missing).

- [ ] **Step 4: Run → pass** — `../.venv/bin/pytest tests/test_admin_domestic_recheck.py -q` → pass.

- [ ] **Step 5: Gates + commit**

```bash
cd app/backend && ../.venv/bin/ruff format api/routes/admin.py tests/test_admin_domestic_recheck.py \
  && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker
cd ../.. && git add app/backend/api/routes/admin.py app/backend/tests/test_admin_domestic_recheck.py
git commit -m "feat(domestic): admin re-check-pending endpoint (reset not_found backoff)"
```

---

## Task 3: Frontend — re-check button + malformed card

**Files:** Modify `app/frontend/lib/api.ts`; `app/frontend/app/(app)/admin/domestic/page.tsx`.

- [ ] **Step 1: api.ts** — mirror the existing `domesticSweep*` methods. Add:

```ts
domesticSweepRecheckPending: () =>
  post<{ reset: number }>("/api/v1/admin/domestic-sweep/recheck-pending"),
```

And extend the `DomesticEnrichmentStats` TS type (find it where `domestic-enrichment` is typed) with:

```ts
  malformed: number;
  malformed_appnos: { application_number: string; applicant_name: string | null; gazette: string | null }[];
```

(Match the exact `post`/`get` helper signatures already used in the file.)

- [ ] **Step 2: page.tsx — re-check button.** Near the Pending-publication stat / sweep controls (~209–227), add a button mirroring the existing `<Button … onClick={() => act(...)}>`:

```tsx
<Button
  variant="ghost"
  disabled={busy || (stats?.pending_publication ?? 0) === 0}
  onClick={() => {
    if (confirm(`Re-check ${stats?.pending_publication ?? 0} pending marks against IP VIETNAM now?`)) {
      act(async () => { await api.domesticSweepRecheckPending(); });
    }
  }}
>
  Re-check pending ({stats?.pending_publication ?? 0})
</Button>
```

(`act`, `busy`, `stats` already exist in the component; match their real names from the file.)

- [ ] **Step 3: page.tsx — malformed card + list.** Next to the Unresolved/Pending `<Stat>` cards (~112–113) add:

```tsx
<Stat label="Malformed — needs review" value={stats.malformed} />
```

And below the stat grid, render the list when non-empty:

```tsx
{stats.malformed_appnos.length > 0 && (
  <div className="mt-4 rounded-lg border p-3 text-sm">
    <div className="mb-2 font-semibold">Malformed application numbers — fix the appno, then they enrich</div>
    <ul className="space-y-1">
      {stats.malformed_appnos.map((m) => (
        <li key={m.application_number} className="flex gap-3 text-ink-soft">
          <span className="font-mono text-ink">{m.application_number}</span>
          <span>{m.applicant_name ?? "—"}</span>
          <span className="text-ink-faint">{m.gazette ?? "—"}</span>
        </li>
      ))}
    </ul>
  </div>
)}
```

(Match existing Tailwind tokens/classes used elsewhere on the page.)

- [ ] **Step 4: Verify** — `cd app/frontend && npx tsc --noEmit && pnpm lint` (NEVER `pnpm build` while `pnpm dev` is live). Browser-check `/admin/domestic`: the Malformed card shows the count, the list shows any malformed appno, and "Re-check pending (N)" triggers a re-check.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/lib/api.ts "app/frontend/app/(app)/admin/domestic/page.tsx"
git commit -m "feat(domestic): re-check-pending button + malformed-appno card on /admin/domestic"
```

---

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest` (targeted tests only — sweep tests reset the live `domestic_sweep_control` singleton). No migration in this feature.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.
- Open a PR `feat(domestic): re-check pending + malformed-appno surfacing`. Update CLAUDE.md's domestic_enrich description to note the malformed bucket + re-check control.

## Self-review

- **Spec coverage:** re-check endpoint (Task 2 ✓), idle-enqueue (Task 2 ✓), malformed detection via `appno_to_vnid` (Task 1 ✓), unresolved-now-means-fetchable (Task 1 ✓), malformed list with applicant+gazette (Task 1 ✓), frontend button + card + list (Task 3 ✓), no migration (✓). All spec sections mapped.
- **Type consistency:** `MalformedAppno{application_number,applicant_name,gazette}` defined in Task 1 is consumed verbatim by the TS type + list in Task 3; `domesticSweepRecheckPending` returns `{reset}` from Task 2.
- **Placeholders:** none — novel logic (malformed partition, reset SQL) given in full; route/frontend boilerplate references the exact existing patterns to mirror.
