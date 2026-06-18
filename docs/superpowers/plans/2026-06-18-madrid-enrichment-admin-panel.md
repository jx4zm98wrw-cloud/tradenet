# Madrid Enrichment Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only page showing live Madrid (WIPO) enrichment progress — unique IRNs, validated, remaining, % complete, VN-granted, and a registration/renewal breakdown — backed by one derived-count endpoint.

**Architecture:** One new FastAPI endpoint (`GET /api/v1/admin/madrid-enrichment`, `require_admin`) computes every figure with `count()` queries over `trademarks` + `madrid_records` at request time (no stored counter). One new Next.js admin page renders it with a progress bar + stat cards, gated by the existing `adminCheck` redirect pattern. A nav tab links to it.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), pytest + httpx/ASGI (tests), Next.js 15 App Router + Tailwind 4 (frontend).

**Source spec:** `docs/superpowers/specs/2026-06-18-madrid-enrichment-admin-panel.md`

**Standing constraints (from session):** Commit only by EXPLICIT path. NEVER `git add -A`/`.`. NEVER stage the "rename trio": `README.md` (repo root), `app/.env.example`, `app/backend/api/settings.py`.

---

## File Structure

- **Create** `app/backend/tests/test_admin_madrid_stats.py` — endpoint test (invariants + 403).
- **Modify** `app/backend/api/routes/admin.py` — add `MadridEnrichmentStats` model + `madrid_enrichment` route.
- **Modify** `app/frontend/lib/api.ts` — add `MadridEnrichmentStats` type + `adminMadridStats()` method.
- **Create** `app/frontend/app/(app)/admin/madrid/page.tsx` — the admin page.
- **Modify** `app/frontend/components/top-nav.tsx` — add a "Madrid" tab; tighten the "Gazettes" match.
- **Modify** `CLAUDE.md` — one line documenting the new admin view + endpoint.

Reference patterns (read if helpful, do not modify): `app/backend/api/routes/stats.py` (count-aggregation endpoints), `app/backend/api/routes/admin.py` (router + admin auth), `app/backend/tests/test_marks_enrichment.py` (Madrid seed fixture), `app/frontend/app/(app)/admin/gazettes/page.tsx` (admin-gate + polling page), `app/backend/api/auth.py:228` (`require_admin`).

---

### Task 1: Backend endpoint `GET /api/v1/admin/madrid-enrichment`

**Files:**
- Create: `app/backend/tests/test_admin_madrid_stats.py`
- Modify: `app/backend/api/routes/admin.py`

**Context:** `admin.py` currently holds only `GET /api/v1/admin/check`. We add a second route on the same router (`prefix="/api/v1/admin"`). `mark_category` and `lineage_key` are Postgres **generated columns** (`Computed(persisted=True)`): set `certificate_number` only ⇒ `mark_category='madrid_registration'`, `lineage_key=<that value>`; set `madrid_number` only ⇒ `'madrid_renewal'`. Tests run against the **shared dev DB** while the enrichment sweep may be writing rows, so assert internal consistency + seeded-row inclusion, never absolute counts.

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_admin_madrid_stats.py`:

```python
"""Admin Madrid-enrichment progress endpoint.

Runs against the shared dev DB while the enrichment sweep may be writing
rows, so we assert the response's internal consistency (relationships that
hold at any instant) plus that our seeded registration IRN is counted —
never absolute counts, which move under the sweep.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import MadridRecord
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000b1")
_REG_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000b2")
_IRN = "9100001"  # synthetic, above the live WIPO IRN range; no collision


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(delete(MadridRecord).where(MadridRecord.irn == _IRN))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_admin_madrid.pdf",
                sha256="adminmadrid_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # certificate_number only → generated mark_category='madrid_registration',
        # lineage_key=_IRN, which soft-joins to the madrid_records row below.
        s.add(
            Trademark(
                id=_REG_ID,
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                certificate_number=_IRN,
            )
        )
        s.add(
            MadridRecord(
                irn=_IRN,
                mark_text="ADMINX",
                vn_status="granted",
                vn_designated=True,
                designated_countries=["VN"],
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_madrid_enrichment_invariants(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/admin/madrid-enrichment")
    assert r.status_code == 200
    d = r.json()
    # Relationships that hold at any snapshot, even while the sweep writes.
    assert d["remaining"] == max(d["unique_irns"] - d["validated"], 0)
    assert d["unique_irns"] >= d["validated"] >= 0
    assert d["vn_granted"] <= d["validated"]
    if d["unique_irns"]:
        assert abs(d["pct_complete"] - d["validated"] / d["unique_irns"]) < 1e-9
    # by_category covers exactly the two Madrid categories and sums to unique.
    assert set(d["by_category"]) == {"madrid_registration", "madrid_renewal"}
    assert sum(d["by_category"].values()) == d["unique_irns"]
    # Our seeded registration IRN + its madrid_record are reflected.
    assert d["unique_irns"] >= 1
    assert d["by_category"]["madrid_registration"] >= 1
    assert d["validated"] >= 1
    assert d["vn_granted"] >= 1


@pytest.mark.asyncio
async def test_madrid_enrichment_requires_admin(viewer_client: AsyncClient) -> None:
    r = await viewer_client.get("/api/v1/admin/madrid-enrichment")
    assert r.status_code == 403
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest tests/test_admin_madrid_stats.py -v`
Expected: FAIL — `test_madrid_enrichment_invariants` gets 404 (route not defined yet); `test_madrid_enrichment_requires_admin` may also be 404 instead of 403.

- [ ] **Step 3: Implement the endpoint**

Edit `app/backend/api/routes/admin.py`. Replace the import block and append the new model + route. The final file:

```python
"""Admin check — role-aware, used by the frontend to gate /admin/* pages.

Returns 200 with `isAdmin` reflecting the logged-in user's actual role.
Non-admins get `isAdmin: false` (so the page can redirect them to "/")
rather than a 403 — the response is a routing signal, not an auth gate.
The real auth gate is on the underlying admin endpoints themselves
(`require_admin` on `/gazettes` listing, etc.) — defense in depth.

Returns 401 if no one is logged in (handled by `require_user`).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, require_admin, require_user
from ..db import Trademark, get_session
from ..db.models import MadridRecord, UserRole

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Madrid mark categories — must match madrid_enrich.backfill.iter_madrid_irns so
# the panel's denominator equals the sweep's work-list.
_MADRID_CATEGORIES = ("madrid_registration", "madrid_renewal")


class AdminCheck(BaseModel):
    isAdmin: bool
    role: UserRole
    reason: str


@router.get("/check", response_model=AdminCheck)
async def check(user: User = Depends(require_user)) -> AdminCheck:
    if user.is_admin:
        return AdminCheck(isAdmin=True, role=user.role, reason="admin role")
    return AdminCheck(
        isAdmin=False,
        role=user.role,
        reason=f"role={user.role.value}; admin required",
    )


class MadridEnrichmentStats(BaseModel):
    unique_irns: int
    validated: int
    remaining: int
    pct_complete: float  # 0.0–1.0
    vn_granted: int
    by_category: dict[str, int]


@router.get("/madrid-enrichment", response_model=MadridEnrichmentStats)
async def madrid_enrichment(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MadridEnrichmentStats:
    """Live Madrid-enrichment coverage, derived from the DB at request time.

    unique_irns = distinct Madrid lineage_keys (= the sweep's work-list);
    validated = madrid_records rows (the durable outcome, not the cache);
    remaining = unique − validated.
    """
    unique_irns = (
        await session.execute(
            select(func.count(distinct(Trademark.lineage_key)))
            .where(Trademark.mark_category.in_(_MADRID_CATEGORIES))
            .where(Trademark.lineage_key.is_not(None))
        )
    ).scalar_one()
    validated = (
        await session.execute(select(func.count()).select_from(MadridRecord))
    ).scalar_one()
    vn_granted = (
        await session.execute(
            select(func.count()).select_from(MadridRecord).where(MadridRecord.vn_status == "granted")
        )
    ).scalar_one()
    cat_rows = (
        await session.execute(
            select(Trademark.mark_category, func.count(distinct(Trademark.lineage_key)))
            .where(Trademark.mark_category.in_(_MADRID_CATEGORIES))
            .where(Trademark.lineage_key.is_not(None))
            .group_by(Trademark.mark_category)
        )
    ).all()
    by_category = {c: n for c, n in cat_rows}
    for c in _MADRID_CATEGORIES:
        by_category.setdefault(c, 0)
    return MadridEnrichmentStats(
        unique_irns=unique_irns,
        validated=validated,
        remaining=max(unique_irns - validated, 0),
        pct_complete=(validated / unique_irns) if unique_irns else 0.0,
        vn_granted=vn_granted,
        by_category=by_category,
    )
```

Note: verify `from ..db import Trademark, get_session` resolves (check `api/db/__init__.py` re-exports both — `stats.py` imports `Trademark` and `get_session` from `..db`, so this matches). If `MadridRecord` is not re-exported from `..db`, import it from `..db.models` as shown.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest tests/test_admin_madrid_stats.py -v`
Expected: PASS — both tests green.

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest -q`
Expected: all prior tests pass + 2 new = green.

- [ ] **Step 6: Commit (explicit paths only)**

```bash
git add app/backend/api/routes/admin.py app/backend/tests/test_admin_madrid_stats.py
git commit -m "feat(admin): Madrid enrichment progress endpoint"
```

---

### Task 2: Frontend API client

**Files:**
- Modify: `app/frontend/lib/api.ts`

**Context:** `lib/api.ts` exposes typed wrappers via the `api` object. `adminCheck` (line ~454) is the model: `adminCheck: () => json<AdminCheck>(\`/api/v1/admin/check\`)`. The `AdminCheck` type sits near line 21. Add the stats type next to it and the method next to `adminCheck`.

- [ ] **Step 1: Add the type**

In `app/frontend/lib/api.ts`, immediately after the `AdminCheck` type (line ~21):

```ts
export type MadridEnrichmentStats = {
  unique_irns: number;
  validated: number;
  remaining: number;
  pct_complete: number; // 0..1
  vn_granted: number;
  by_category: Record<string, number>;
};
```

- [ ] **Step 2: Add the method**

In the `api` object, on the line after `adminCheck: () => json<AdminCheck>(\`/api/v1/admin/check\`),`:

```ts
  adminMadridStats: () => json<MadridEnrichmentStats>(`/api/v1/admin/madrid-enrichment`),
```

- [ ] **Step 3: Type-check**

Run: `cd app/frontend && pnpm tsc --noEmit`
Expected: no errors (the new type/method are consumed in Task 3; standalone they still type-check).

- [ ] **Step 4: Commit**

```bash
git add app/frontend/lib/api.ts
git commit -m "feat(admin): adminMadridStats API client method + type"
```

---

### Task 3: Frontend admin page `/admin/madrid`

**Files:**
- Create: `app/frontend/app/(app)/admin/madrid/page.tsx`

**Context:** Mirror `app/(app)/admin/gazettes/page.tsx`: `api.adminCheck()` redirect gate, conditional polling, `Card`/`Button`/`Pill` from `@/components/ui`, `formatNumber`/`errorMessage` from `@/lib/format`. Build the progress bar inline (same primitive the gazettes upload bar uses: a `bg-line` track with a `bg-stamp` fill sized by width %). No new shared component.

- [ ] **Step 1: Create the page**

Create `app/frontend/app/(app)/admin/madrid/page.tsx`:

```tsx
"use client";

/** /admin/madrid — Madrid (WIPO) enrichment progress.
 *
 * Read-only ops view: how many unique Madrid IRNs the system holds, how many
 * have been validated against the WIPO endpoint, and how many remain. Every
 * number is derived from the DB at request time (no stored counter), so it
 * cannot drift. Admin-gated like /admin/gazettes: client-side redirect for
 * non-admins + backend require_admin on the endpoint (defense in depth). */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Pill } from "@/components/ui";
import { api, type MadridEnrichmentStats } from "@/lib/api";
import { errorMessage, formatNumber } from "@/lib/format";

export default function AdminMadridPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = React.useState<boolean | null>(null);
  const [stats, setStats] = React.useState<MadridEnrichmentStats | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Gate: redirect non-admins to Today.
  React.useEffect(() => {
    api.adminCheck()
      .then((c) => { if (!c.isAdmin) router.replace("/today"); else setIsAdmin(true); })
      .catch(() => setError("Admin check failed"));
  }, [router]);

  const refresh = React.useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      setStats(await api.adminMadridStats());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  React.useEffect(() => { if (isAdmin) refresh(); }, [isAdmin, refresh]);

  // Light auto-poll while the sweep still has IRNs to fetch.
  React.useEffect(() => {
    if (!stats || stats.remaining <= 0) return;
    const id = setInterval(() => refresh(true), 5000);
    return () => clearInterval(id);
  }, [stats, refresh]);

  if (error && !stats) {
    return <div className="max-w-container mx-auto px-6 py-12"><p className="text-rose-600">{error}</p></div>;
  }
  if (isAdmin === null || !stats) {
    return <div className="max-w-container mx-auto px-6 py-12 text-mute text-sm">Loading…</div>;
  }

  const pct = Math.round(stats.pct_complete * 1000) / 10; // one decimal place

  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-5">
      <div className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="head-serif text-[26px] font-semibold tracking-tight">Madrid enrichment</h1>
            <Pill tone="mute" size="sm">Admin</Pill>
          </div>
          <p className="text-sm text-mute mt-1 max-w-prose">
            WIPO validation coverage across all Madrid international registrations.
            Derived live from the database.
          </p>
        </div>
        <Button variant="ghost" onClick={() => refresh()} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {/* Progress bar */}
      <Card>
        <div className="px-4 py-4">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-sm font-semibold">
              {formatNumber(stats.validated)} of {formatNumber(stats.unique_irns)} validated
            </span>
            <span className="text-sm font-mono text-mute">{pct}%</span>
          </div>
          <div className="h-2 bg-line rounded overflow-hidden">
            <div className="h-full bg-stamp transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-[11.5px] text-mute mt-2">
            {formatNumber(stats.remaining)} remaining{stats.remaining > 0 ? " · sweep in progress" : " · complete"}
          </p>
        </div>
      </Card>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat label="Unique IRNs" value={stats.unique_irns} />
        <Stat label="Validated" value={stats.validated} />
        <Stat label="Remaining" value={stats.remaining} />
        <Stat label="VN granted" value={stats.vn_granted} />
        <Stat label="Registrations" value={stats.by_category["madrid_registration"] ?? 0} />
        <Stat label="Renewals" value={stats.by_category["madrid_renewal"] ?? 0} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <div className="px-4 py-3">
        <div className="text-[11px] uppercase tracking-[0.08em] text-mute font-mono">{label}</div>
        <div className="text-2xl font-semibold tabular mt-1">{formatNumber(value)}</div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd app/frontend && pnpm tsc --noEmit`
Expected: no errors. If `Card`/`Button`/`Pill` are not all exported from `@/components/ui`, check `app/frontend/app/(app)/admin/gazettes/page.tsx`'s import (it imports all three from `@/components/ui`) and match it.

- [ ] **Step 3: Lint**

Run: `cd app/frontend && pnpm lint`
Expected: no errors for the new file.

- [ ] **Step 4: Commit**

```bash
git add "app/frontend/app/(app)/admin/madrid/page.tsx"
git commit -m "feat(admin): Madrid enrichment progress page"
```

---

### Task 4: Navigation tab

**Files:**
- Modify: `app/frontend/components/top-nav.tsx`

**Context:** The `TABS` array (line ~12) drives the top nav. The current "Gazettes" tab matches `p.startsWith("/admin")`, which would also light up on `/admin/madrid`. Tighten it and add a "Madrid" tab.

- [ ] **Step 1: Edit the TABS array**

In `app/frontend/components/top-nav.tsx`, replace the Gazettes line:

```ts
  { href: "/admin/gazettes", label: "Gazettes", match: (p: string) => p.startsWith("/admin") || p.startsWith("/gazettes") },
```

with these two lines:

```ts
  { href: "/admin/gazettes", label: "Gazettes", match: (p: string) => p.startsWith("/admin/gazettes") || p.startsWith("/gazettes") },
  { href: "/admin/madrid", label: "Madrid", match: (p: string) => p.startsWith("/admin/madrid") },
```

- [ ] **Step 2: Type-check + lint**

Run: `cd app/frontend && pnpm tsc --noEmit && pnpm lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/components/top-nav.tsx
git commit -m "feat(admin): add Madrid tab to top nav"
```

---

### Task 5: Docs

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-06-18-madrid-enrichment-admin-panel.md`

**Context:** Project docs discipline: a new endpoint + admin view must be recorded. Update the `madrid_enrich/` description in `CLAUDE.md`'s project layout, and flip the spec status to Implemented. DO NOT touch `README.md` (rename trio) — `CLAUDE.md` is a different file and is safe.

- [ ] **Step 1: Note the admin view in CLAUDE.md**

In `CLAUDE.md`, find the `madrid_enrich/` bullet in the Project layout block (it ends "...with WIPO-fetched Madrid bibliographic data."). Append one sentence to that paragraph:

```
An admin-only progress view (`GET /api/v1/admin/madrid-enrichment` →
`app/(app)/admin/madrid`) reports enrichment coverage (unique IRNs vs validated
vs remaining), all derived live from the DB.
```

- [ ] **Step 2: Flip the spec status**

In `docs/superpowers/specs/2026-06-18-madrid-enrichment-admin-panel.md`, change the status line:

```
**Status:** Approved for planning · 2026-06-18
```

to:

```
**Status:** Implemented · 2026-06-18
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-06-18-madrid-enrichment-admin-panel.md
git commit -m "docs(admin): record Madrid enrichment progress panel"
```

---

## Final verification (after all tasks)

- [ ] Backend suite green: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest -q`
- [ ] Frontend clean: `cd app/frontend && pnpm tsc --noEmit && pnpm lint`
- [ ] Manual smoke (app running): log in as admin, open `/admin/madrid` — progress bar + 6 stat cards render, numbers match `GET /api/v1/admin/madrid-enrichment`; the "Madrid" nav tab highlights only on that route; a non-admin (viewer) is redirected to `/today`.
- [ ] Confirm `git status` still shows the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`) as **unstaged/modified** — they must never be committed.
