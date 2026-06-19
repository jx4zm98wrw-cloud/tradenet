# Madrid Enrichment — API + UI Surfacing Implementation Plan (Plan 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the already-populated `madrid_records` WIPO enrichment in the product — a mark-detail enrichment payload + UI section (VN banner, WIPO record card, designated jurisdictions, status-by-jurisdiction, prosecution timeline) and a "designated jurisdiction" + "VN status" search filter.

**Architecture:** Backend joins `madrid_records` to a Madrid `Trademark` on `MadridRecord.irn == Trademark.lineage_key`, exposes it as a nested `enrichment` object on the existing `/api/v1/marks/{id}` detail response (detail-only, like `raw_511_text`), and adds two search filters via a single subquery clause on `lineage_key`. Frontend adds an `enrichment` field to `MarkDetail`, renders a focused `MadridEnrichment` component on the detail page (gazette-authoritative status; WIPO provenance badges; reconciles WIPO-vs-gazette divergence exactly as the approved `/tmp/madrid_demo/pilot.html` mockup), and adds a filter-rail group.

**Tech Stack:** FastAPI + SQLAlchemy 2 (async) + Pydantic v2 (`from_attributes`); Next.js 15 App Router + React + Tailwind 4; pytest + httpx ASGI.

**Spec:** `docs/superpowers/specs/2026-06-17-madrid-wipo-enrichment-design.md` §8 (UI/search surfacing). **Mockup:** `/tmp/madrid_demo/pilot.html` (drawer = the detail layout to mirror; throwaway, not committed).

**Gazette-authoritative reminder:** every enriched IRN comes from VN's accepted-gazette section, so `vn_status` is `granted` for all of them; WIPO's per-country `designation_status` may still show a provisional `refused` that the gazette overrode. The UI must show **our** verdict as the badge and the WIPO fact as a sub-note — never two contradicting badges (this was a real bug caught in the mockup).

---

## Existing patterns to follow (read before starting)

- **Detail route**: `app/backend/api/routes/marks.py:50` `get_mark` → `_build_detail(m)` returns `MarkDetailOut`. `raw_511_text` shows the "detail-only field" pattern.
- **Schemas**: `app/backend/api/schemas.py` — `TrademarkOut` uses `model_config = ConfigDict(from_attributes=True)`. `MarkDetailOut` lives in `marks.py` itself (local `BaseModel`).
- **Filter builder**: `app/backend/api/routes/_filters.py:71` `build_trademark_where(**, exclude=...)` returns `list[ColumnElement]`. The `mark_category` block (lines 126-127) is the template for a new scalar filter.
- **Facet params**: `app/backend/api/routes/facets.py:23` `_filter_params(...)` (a `Depends`-injected dict) + per-facet endpoints; `/facets/mark-categories` (138-157) is the count template; `MARK_CATEGORY_LABELS` (129) mirrors the frontend.
- **Search route**: `app/backend/api/routes/search.py` and `trademarks.py` declare `Query(...)` params and call `build_trademark_where`.
- **Models**: `app/backend/api/db/models.py` — `MadridRecord` (line 283; PK `irn: Text`) and `Trademark.lineage_key` (208), `Trademark.mark_category` (194). `MadridRecord.designated_countries` is `ARRAY(Text)` with GIN index `ix_madrid_records_designated_countries`.
- **Frontend types/fetchers**: `app/frontend/lib/api.ts` — `Trademark` (23), `MarkDetail` (271), `SearchParams` (81), `CountBucket` (119), `api.getMark` (380), facet fetchers (369-377), `MARK_CATEGORY_LABELS` (461).
- **Detail page**: `app/frontend/app/(app)/marks/[id]/page.tsx` — client component, `api.getMark(id)` (69), composes `components/detail/timeline`, `components/detail/opposition-box`, `markCategoryMeta` (badges).
- **Filter rail**: `app/frontend/components/search/filter-rail.tsx` (the `mark_category` group) + `app/frontend/app/(app)/search/page.tsx` (URL read + chips).
- **Tests**: `app/backend/tests/conftest.py` provides `client` (httpx AsyncClient over ASGITransport) and `db_session`. `tests/test_search_filter_only.py` shows the seed-fixture pattern (create_async_engine + async_sessionmaker, idempotent delete-then-insert). Madrid tests live under `tests/madrid_enrich/`.

---

## File structure

**Backend**
- Modify `app/backend/api/schemas.py` — add `MadridEnrichmentOut` Pydantic model.
- Modify `app/backend/api/routes/marks.py` — attach `enrichment` to `MarkDetailOut`; fetch in `get_mark`.
- Modify `app/backend/api/routes/_filters.py` — add `designated_country` + `vn_status` filters.
- Modify `app/backend/api/routes/facets.py` — add the two params to `_filter_params` + a `/facets/vn-status` endpoint.
- Modify `app/backend/api/routes/search.py` and `trademarks.py` — declare + thread the two query params.
- Modify `app/README.md` — endpoint/facet docs.
- Test `app/backend/tests/test_marks_enrichment.py` (new) — detail payload + filters.

**Frontend**
- Modify `app/frontend/lib/api.ts` — `MadridEnrichment` type, `MarkDetail.enrichment`, `SearchParams` additions, `facetVnStatus`, `VN_STATUS_LABELS`.
- Create `app/frontend/components/detail/madrid-enrichment.tsx` — the enrichment section.
- Modify `app/frontend/app/(app)/marks/[id]/page.tsx` — render `<MadridEnrichment>`.
- Modify `app/frontend/components/search/filter-rail.tsx` — "Designated jurisdiction" + "VN status" groups.
- Modify `app/frontend/app/(app)/search/page.tsx` — URL read, chips, scope label.

---

## GROUP A — Backend: mark-detail enrichment payload

### Task A1: `MadridEnrichmentOut` schema

**Files:**
- Modify: `app/backend/api/schemas.py`

- [ ] **Step 1: Add the schema** (append near the other `*Out` models)

```python
class MadridEnrichmentOut(BaseModel):
    """WIPO Madrid Monitor enrichment for a Madrid mark, joined from
    `madrid_records` on `irn == trademarks.lineage_key`. Detail-only —
    never on TrademarkOut (keeps list/search responses lean)."""

    model_config = ConfigDict(from_attributes=True)

    irn: str
    holder_name: str | None = None
    holder_address: str | None = None
    holder_country: str | None = None
    holder_legal_status: str | None = None
    mark_text: str | None = None
    representative: str | None = None
    registration_date: date | None = None
    expiration_date: date | None = None
    nice_classes: list[str] | None = None
    designated_countries: list[str] | None = None
    basic_registration: str | None = None
    language: str | None = None
    vn_designated: bool | None = None
    vn_status: str | None = None
    vn_grant_date: date | None = None
    vn_refusal_date: date | None = None
    designation_status: dict | None = None
    transaction_history: list | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None
```

- [ ] **Step 2: Ensure imports** — confirm `from datetime import date, datetime` and `from pydantic import BaseModel, ConfigDict` are present at the top of `schemas.py`; add `datetime` to the datetime import if missing.

- [ ] **Step 3: Commit**

```bash
git add app/backend/api/schemas.py
git commit -m "feat(madrid): MadridEnrichmentOut detail schema"
```

### Task A2: attach enrichment to the mark-detail response

**Files:**
- Modify: `app/backend/api/routes/marks.py:35-79`
- Test: `app/backend/tests/test_marks_enrichment.py` (new)

- [ ] **Step 1: Write the failing test** (new file)

```python
"""Mark-detail enrichment payload + Madrid search filters."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import MadridRecord
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000a3")
_MADRID_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000a4")
_DOMESTIC_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000a5")
_IRN = "9000001"


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(MadridRecord).where(MadridRecord.irn == _IRN))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ, filename="B_TEST_enrich.pdf", sha256="enrich_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B, issue_year=2099, storage_path="/dev/null",
                status=GazetteStatus.processed,
            )
        )
        # Madrid registration row: lineage_key == IRN, mark_category derived.
        s.add(
            Trademark(
                id=_MADRID_ID, gazette_id=_GZ, record_type=RecordType.B,
                madrid_number=_IRN, certificate_number=_IRN,
            )
        )
        # Plain domestic registration: no lineage match -> no enrichment.
        s.add(
            Trademark(
                id=_DOMESTIC_ID, gazette_id=_GZ, record_type=RecordType.B,
                certificate_number="VN12345", application_number="4-2099-00001",
            )
        )
        s.add(
            MadridRecord(
                irn=_IRN, holder_name="ACME GLOBAL LLC", mark_text="ACMEX",
                registration_date=date(2015, 6, 26), expiration_date=date(2035, 6, 26),
                nice_classes=["9", "42"], designated_countries=["VN", "SG", "JP"],
                vn_designated=True, vn_status="granted", vn_grant_date=date(2016, 8, 1),
                designation_status={"VN": {"date": "2016-08-01", "status": "granted"}},
                transaction_history=[{"type": "Grant of protection, VN", "date": "2016-08-01", "parties": ["VN"]}],
                source_url="https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.9000001",
            )
        )
        await s.commit()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_madrid_detail_includes_enrichment(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_MADRID_ID}")
    assert r.status_code == 200
    body = r.json()
    enr = body["enrichment"]
    assert enr is not None
    assert enr["irn"] == _IRN
    assert enr["vn_status"] == "granted"
    assert enr["vn_grant_date"] == "2016-08-01"
    assert "VN" in enr["designated_countries"]
    assert enr["holder_name"] == "ACME GLOBAL LLC"


@pytest.mark.asyncio
async def test_domestic_detail_has_null_enrichment(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_DOMESTIC_ID}")
    assert r.status_code == 200
    assert r.json()["enrichment"] is None
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd app/backend && python -m pytest tests/test_marks_enrichment.py::test_madrid_detail_includes_enrichment -v`
Expected: FAIL — `KeyError: 'enrichment'` (field not on response yet).

- [ ] **Step 3: Add the field + fetch.** In `marks.py`, import the model + schema near the top:

```python
from ..db.models import MadridRecord
from ..schemas import MadridEnrichmentOut, TrademarkOut
```

(Replace the existing `from ..schemas import TrademarkOut`.)

Add the field to `MarkDetailOut` (after `raw_511_text`):

```python
    # WIPO Madrid enrichment, present only for Madrid marks that have a
    # madrid_records row (joined on lineage_key). None for domestic marks
    # and for Madrid marks not yet enriched — never fabricated.
    enrichment: MadridEnrichmentOut | None = None
```

Change `get_mark` to fetch the record and thread it through:

```python
@router.get("/{id}", response_model=MarkDetailOut)
async def get_mark(id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> MarkDetailOut:
    m = await session.get(Trademark, id)
    if m is None:
        raise HTTPException(404, "Mark not found")
    enrichment = None
    if m.lineage_key:
        rec = await session.get(MadridRecord, m.lineage_key)
        if rec is not None:
            enrichment = MadridEnrichmentOut.model_validate(rec)
    return _build_detail(m, enrichment)
```

Change `_build_detail`'s signature and return:

```python
def _build_detail(m: Trademark, enrichment: MadridEnrichmentOut | None = None) -> MarkDetailOut:
```

…and add `enrichment=enrichment,` to the `MarkDetailOut(...)` constructor call.

- [ ] **Step 4: Run both tests — expect pass**

Run: `cd app/backend && python -m pytest tests/test_marks_enrichment.py -v`
Expected: both PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd app/backend && ruff format api/routes/marks.py api/schemas.py tests/test_marks_enrichment.py && ruff check api/routes/marks.py api/schemas.py tests/test_marks_enrichment.py
git add api/routes/marks.py api/schemas.py tests/test_marks_enrichment.py
git commit -m "feat(madrid): attach WIPO enrichment to mark detail"
```

---

## GROUP B — Backend: designated-jurisdiction + VN-status search filters

### Task B1: filter clauses in `build_trademark_where`

**Files:**
- Modify: `app/backend/api/routes/_filters.py`
- Test: append to `app/backend/tests/test_marks_enrichment.py`

- [ ] **Step 1: Write the failing test** (append; reuses the autouse `seed` fixture)

```python
@pytest.mark.asyncio
async def test_search_filter_designated_country(client: AsyncClient) -> None:
    # The Madrid mark designates VN/SG/JP. Filtering by SG returns it; by US does not.
    r_sg = await client.get("/api/v1/trademarks", params={"designated_country": "SG", "limit": 50})
    ids = {row["id"] for row in r_sg.json()["items"]}
    assert str(_MADRID_ID) in ids
    r_us = await client.get("/api/v1/trademarks", params={"designated_country": "US", "limit": 50})
    assert str(_MADRID_ID) not in {row["id"] for row in r_us.json()["items"]}


@pytest.mark.asyncio
async def test_search_filter_vn_status(client: AsyncClient) -> None:
    r = await client.get("/api/v1/trademarks", params={"vn_status": "granted", "limit": 50})
    assert str(_MADRID_ID) in {row["id"] for row in r.json()["items"]}
    r2 = await client.get("/api/v1/trademarks", params={"vn_status": "refused", "limit": 50})
    assert str(_MADRID_ID) not in {row["id"] for row in r2.json()["items"]}
```

> NOTE for the implementer: confirm the list endpoint path + response envelope key (`items` vs `results`) by reading `app/backend/api/routes/trademarks.py` and matching the test to the real shape before running. Adjust `"/api/v1/trademarks"` / `row["id"]` / `["items"]` to the actual route if they differ.

- [ ] **Step 2: Run it — expect failure**

Run: `cd app/backend && python -m pytest tests/test_marks_enrichment.py::test_search_filter_designated_country -v`
Expected: FAIL — unknown query param ignored, so the mark is absent / param rejected.

- [ ] **Step 3: Add the clauses.** In `_filters.py`, import the model and `select`:

```python
from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from ..db import RecordType, Trademark
from ..db.models import MadridRecord
```

Add two params to `build_trademark_where`'s signature (after `ip_agency`):

```python
    designated_country: str | None = None,
    vn_status: str | None = None,
```

Append the clauses (before `return where`):

```python
    # Designated-jurisdiction filter: marks whose Madrid record covers country
    # `cc`. Joined via lineage_key against madrid_records.designated_countries
    # (a GIN-indexed Postgres array; `@>` containment hits the index). A
    # non-correlated IN-subquery keeps this a single appendable clause.
    if designated_country and exclude != "designated_country":
        cc = designated_country.upper()
        irns = select(MadridRecord.irn).where(MadridRecord.designated_countries.contains([cc]))
        where.append(Trademark.lineage_key.in_(irns))
    # VN protection-status filter (granted | pending | refused), also via the
    # lineage_key join. Gazette-authoritative: practically all enriched rows are
    # "granted", but the filter is general.
    if vn_status and exclude != "vn_status":
        irns = select(MadridRecord.irn).where(MadridRecord.vn_status == vn_status)
        where.append(Trademark.lineage_key.in_(irns))
```

- [ ] **Step 4: Thread params through the list/search routes.** In `app/backend/api/routes/trademarks.py` AND `app/backend/api/routes/search.py`, add the two `Query` params to the handler signature(s) (mirror how `mark_category` is declared) and pass them into the `build_trademark_where(...)` call. Example additions to the signature:

```python
    designated_country: str | None = Query(None, description="Madrid designated jurisdiction ISO2 (covers country X)"),
    vn_status: str | None = Query(None, description="VN protection status: granted|pending|refused"),
```

…and in the `build_trademark_where(...)` call add `designated_country=designated_country, vn_status=vn_status,`.

- [ ] **Step 5: Run filter tests — expect pass**

Run: `cd app/backend && python -m pytest tests/test_marks_enrichment.py -v`
Expected: all 4 PASS.

- [ ] **Step 6: Lint + commit**

```bash
cd app/backend && ruff format api/routes/_filters.py api/routes/trademarks.py api/routes/search.py && ruff check api/routes/_filters.py api/routes/trademarks.py api/routes/search.py
git add api/routes/_filters.py api/routes/trademarks.py api/routes/search.py tests/test_marks_enrichment.py
git commit -m "feat(madrid): designated-jurisdiction + vn_status search filters"
```

### Task B2: facet plumbing + `/facets/vn-status`

**Files:**
- Modify: `app/backend/api/routes/facets.py`
- Test: append to `app/backend/tests/test_marks_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_facet_vn_status(client: AsyncClient) -> None:
    r = await client.get("/api/v1/facets/vn-status")
    assert r.status_code == 200
    buckets = {b["key"]: b["count"] for b in r.json()}
    assert buckets.get("granted", 0) >= 1
```

- [ ] **Step 2: Run it — expect 404**

Run: `cd app/backend && python -m pytest tests/test_marks_enrichment.py::test_facet_vn_status -v`
Expected: FAIL — 404 (endpoint missing).

- [ ] **Step 3: Implement.** In `facets.py`, add the two params to `_filter_params` (mirror `mark_category` at line 28 + 43):

```python
    designated_country: str | None = Query(None),
    vn_status: str | None = Query(None),
```

…and in the returned dict: `designated_country=designated_country, vn_status=vn_status,`.

Add the labels + endpoint (after the mark-categories facet):

```python
VN_STATUS_LABELS: dict[str, str] = {
    "granted": "Granted in VN",
    "pending": "Pending in VN",
    "refused": "Refused in VN",
}


@router.get("/vn-status", response_model=list[CountBucket])
async def facet_vn_status(
    filters: dict = Depends(_filter_params),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Count marks per VN protection status under the current filter set
    (excluding the vn_status filter itself), via the lineage_key join."""
    where = build_trademark_where(**filters, exclude="vn_status")
    stmt = (
        select(MadridRecord.vn_status, func.count())
        .join(Trademark, Trademark.lineage_key == MadridRecord.irn)
        .where(*where)
        .group_by(MadridRecord.vn_status)
    )
    rows = (await session.execute(stmt)).all()
    return [
        CountBucket(key=st, label=VN_STATUS_LABELS.get(st, st), count=n)
        for st, n in rows
        if st is not None
    ]
```

Ensure `facets.py` imports `MadridRecord` (`from ..db.models import MadridRecord`) and that `Trademark`, `select`, `func`, `CountBucket`, `get_session` are already imported (they are — used by the other facets).

- [ ] **Step 4: Run — expect pass**

Run: `cd app/backend && python -m pytest tests/test_marks_enrichment.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd app/backend && ruff format api/routes/facets.py && ruff check api/routes/facets.py
git add api/routes/facets.py tests/test_marks_enrichment.py
git commit -m "feat(madrid): /facets/vn-status + filter plumbing"
```

### Task B3: backend docs

**Files:**
- Modify: `app/README.md`

- [ ] **Step 1: Update docs.** Find the endpoint/facet table in `app/README.md` (grep `facets/mark-categories`). Add rows documenting: `GET /api/v1/marks/{id}` now returns an `enrichment` object for Madrid marks; the `designated_country` + `vn_status` query params on the trademark list/search; and `GET /api/v1/facets/vn-status`. Match the table's existing column format.

- [ ] **Step 2: Commit**

```bash
git add app/README.md
git commit -m "docs(madrid): document enrichment payload + Madrid filters"
```

---

## GROUP C — Frontend: types

### Task C1: API types + fetchers

**Files:**
- Modify: `app/frontend/lib/api.ts`

- [ ] **Step 1: Add the `MadridEnrichment` type** (near `MarkDetail`, line ~271)

```typescript
export type MadridEnrichment = {
  irn: string;
  holder_name: string | null;
  holder_address: string | null;
  holder_country: string | null;
  holder_legal_status: string | null;
  mark_text: string | null;
  representative: string | null;
  registration_date: string | null;
  expiration_date: string | null;
  nice_classes: string[] | null;
  designated_countries: string[] | null;
  basic_registration: string | null;
  language: string | null;
  vn_designated: boolean | null;
  vn_status: string | null;
  vn_grant_date: string | null;
  vn_refusal_date: string | null;
  /** WIPO per-country snapshot: { "VN": { date, status, gazette? }, ... } */
  designation_status: Record<string, { date?: string; status?: string; gazette?: string }> | null;
  /** Chronological WIPO events: [{ type, date, parties:[ISO2], gazette? }] */
  transaction_history: Array<{ type?: string; date?: string; parties?: string[]; gazette?: string }> | null;
  source_url: string | null;
  fetched_at: string | null;
};
```

- [ ] **Step 2: Add `enrichment` to `MarkDetail`** (inside the `MarkDetail` type, after `raw_511_text`):

```typescript
  /** WIPO Madrid enrichment — present only for enriched Madrid marks. */
  enrichment: MadridEnrichment | null;
```

- [ ] **Step 3: Add filter params to `SearchParams`** (after `ip_agency`):

```typescript
  /** Madrid designated jurisdiction (ISO2). Matches marks whose Madrid record
   * covers this country. "VN" = protected/processed in Vietnam. */
  designated_country?: string;
  /** VN protection status: granted | pending | refused. */
  vn_status?: string;
```

- [ ] **Step 4: Add the facet fetcher + labels.** Next to `facetMarkCategories` (line ~377):

```typescript
  facetVnStatus: (filters: SearchParams, init?: RequestInit) =>
    json<CountBucket[]>(`/api/v1/facets/vn-status?${qs({ ...filters, offset: undefined })}`, init),
```

And near `MARK_CATEGORY_LABELS` (line ~461):

```typescript
// VN protection-status labels (mirrors backend VN_STATUS_LABELS in facets.py).
export const VN_STATUS_LABELS: Record<string, string> = {
  granted: "Granted in VN",
  pending: "Pending in VN",
  refused: "Refused in VN",
};
```

- [ ] **Step 5: Typecheck + commit**

```bash
cd app/frontend && pnpm tsc --noEmit
git add lib/api.ts
git commit -m "feat(madrid): frontend types for enrichment + filters"
```

---

## GROUP D — Frontend: mark-detail enrichment UI

### Task D1: the `MadridEnrichment` component

**Files:**
- Create: `app/frontend/components/detail/madrid-enrichment.tsx`

This component mirrors the approved drawer in `/tmp/madrid_demo/pilot.html` (open it for exact visual reference). It renders, top → bottom: a 🇻🇳 VN banner, a "WIPO Madrid record" card (with `WIPO` provenance badge), designated-jurisdiction flag chips (VN pinned + highlighted), and a two-pane "Status by jurisdiction" / "Prosecution timeline" card. Match the existing detail cards' Tailwind classes (read a sibling like `components/detail/opposition-box.tsx` for the card shell / token usage — e.g. `rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)]`).

**Critical reconciliation rule (from the mockup bug):** in "Status by jurisdiction", the VN row must show **`enrichment.vn_status`** as the badge (our gazette-authoritative verdict). If `designation_status.VN.status` differs from `vn_status` (e.g. WIPO shows `refused`), render it as a muted side-note `WIPO: refused 2016-06-30`, NOT as a second contradicting badge. The VN banner shows `granted${grant_date ? " " + grant_date : ""}` — never the literal "null".

- [ ] **Step 1: Write the component**

```tsx
"use client";

import * as React from "react";
import type { MadridEnrichment } from "@/lib/api";
import { VN_STATUS_LABELS } from "@/lib/api";
import { formatDate } from "@/lib/format";

const COUNTRY_NAME: Record<string, string> = {
  VN: "Vietnam", SG: "Singapore", JP: "Japan", CN: "China", US: "United States",
  // Fallback to the code when a name isn't listed; extend as needed.
};
const cname = (cc: string) => COUNTRY_NAME[cc] ?? cc;

function statusTone(s: string | null | undefined): "ok" | "warn" | "mute" {
  if (s === "granted") return "ok";
  if (s === "refused") return "warn";
  return "mute";
}

function Badge({ status }: { status: string | null | undefined }) {
  const tone = statusTone(status);
  const cls =
    tone === "ok"
      ? "bg-[var(--ok-2,#e8f5ee)] text-[var(--ok,#1a7f4b)]"
      : tone === "warn"
        ? "bg-[var(--warn-2,#fdeaea)] text-[var(--warn,#b4232a)]"
        : "bg-[var(--mute-2,#eee)] text-[var(--mute,#666)]";
  return (
    <span className={`rounded px-2 py-0.5 text-[11px] font-semibold uppercase ${cls}`}>
      {status ?? "—"}
    </span>
  );
}

export function MadridEnrichment({ e }: { e: MadridEnrichment }) {
  const granted = e.vn_status === "granted";
  const ds = e.designation_status ?? {};
  const vnWipo = ds["VN"];
  const wipoDiffers = !!vnWipo?.status && vnWipo.status !== e.vn_status;

  const countries = [...(e.designated_countries ?? [])].sort((a, b) =>
    a === "VN" ? -1 : b === "VN" ? 1 : 0,
  );

  const statEntries = Object.entries(ds).sort((a, b) => {
    if (a[0] === "VN") return -1;
    if (b[0] === "VN") return 1;
    const ord = (s?: string) => (s === "granted" ? 0 : s === "refused" ? 1 : 2);
    return ord(a[1]?.status) - ord(b[1]?.status);
  });

  const timeline = [...(e.transaction_history ?? [])]
    .filter((t) => t.date)
    .sort((a, b) => ((a.date ?? "") < (b.date ?? "") ? -1 : 1));

  return (
    <section className="flex flex-col gap-4">
      {/* VN banner */}
      <div
        className={`flex items-center gap-3 rounded-[var(--radius-lg)] border p-4 ${
          granted
            ? "border-[var(--ok,#1a7f4b)] bg-[var(--ok-2,#e8f5ee)]"
            : "border-[var(--line)] bg-[var(--surface)]"
        }`}
      >
        <span className="text-2xl">{granted ? "🇻🇳" : "🏳️"}</span>
        <div>
          <div className="font-semibold">
            {granted
              ? `Protected in Vietnam — granted${e.vn_grant_date ? ` ${formatDate(e.vn_grant_date)}` : ""}`
              : `VN status: ${e.vn_status ?? "—"}`}
          </div>
          <div className="text-sm text-[var(--mute)]">
            {e.vn_refusal_date ? `refused ${formatDate(e.vn_refusal_date)} · ` : ""}
            expires {e.expiration_date ? formatDate(e.expiration_date) : "—"}
          </div>
        </div>
      </div>

      {/* WIPO Madrid record card */}
      <div className="rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] p-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          WIPO Madrid record
          <span className="rounded bg-[var(--brand-2,#eef)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--brand,#34c)]">
            WIPO
          </span>
        </h3>
        <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-sm">
          <dt className="text-[var(--mute)]">Holder</dt>
          <dd className="font-medium">{e.holder_name ?? "—"}</dd>
          <dt className="text-[var(--mute)]">Country</dt>
          <dd>{e.holder_country ? cname(e.holder_country) : "—"}</dd>
          <dt className="text-[var(--mute)]">Legal nature</dt>
          <dd>{e.holder_legal_status ?? "—"}</dd>
          <dt className="text-[var(--mute)]">Representative</dt>
          <dd>{e.representative ?? "—"}</dd>
          <dt className="text-[var(--mute)]">Registered</dt>
          <dd>{e.registration_date ? formatDate(e.registration_date) : "—"}</dd>
          <dt className="text-[var(--mute)]">Expiration</dt>
          <dd className="font-medium">{e.expiration_date ? formatDate(e.expiration_date) : "—"}</dd>
          <dt className="text-[var(--mute)]">Nice</dt>
          <dd>{(e.nice_classes ?? []).join(", ") || "—"}</dd>
          <dt className="text-[var(--mute)]">Basic reg.</dt>
          <dd>{e.basic_registration ?? "—"}</dd>
        </dl>
      </div>

      {/* Designated jurisdictions */}
      <div className="rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] p-4">
        <h3 className="mb-3 text-sm font-semibold">
          Designated jurisdictions ({countries.length})
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {countries.map((cc) => (
            <span
              key={cc}
              className={`rounded px-2 py-1 text-xs ${
                cc === "VN"
                  ? "bg-[var(--ok-2,#e8f5ee)] font-semibold text-[var(--ok,#1a7f4b)]"
                  : "bg-[var(--mute-2,#f1f1f1)] text-[var(--ink)]"
              }`}
            >
              {cc}
            </span>
          ))}
        </div>
      </div>

      {/* Two-pane: status by jurisdiction + prosecution timeline */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] p-4">
          <h3 className="mb-3 text-sm font-semibold">Status by jurisdiction</h3>
          <div className="flex flex-col gap-1.5">
            {statEntries.length === 0 ? (
              <div className="text-sm text-[var(--mute)]">No per-country status parsed.</div>
            ) : (
              statEntries.map(([cc, s]) => {
                const isVN = cc === "VN";
                // VN row: show OUR verdict; surface WIPO divergence as a note.
                const badgeStatus = isVN ? e.vn_status : s?.status;
                const dt = isVN ? e.vn_grant_date ?? "" : s?.date ?? "";
                const note =
                  isVN && wipoDiffers
                    ? `WIPO: ${vnWipo?.status} ${vnWipo?.date ?? ""}`
                    : null;
                return (
                  <div
                    key={cc}
                    className={`flex items-center gap-2 ${isVN ? "font-medium" : ""}`}
                  >
                    <span className="w-28 shrink-0">{cname(cc)}</span>
                    <span className="flex-1 text-xs text-[var(--mute)]">
                      {dt ? formatDate(dt) : ""}
                    </span>
                    {note && (
                      <span className="text-[11px] text-[var(--mute)]">{note}</span>
                    )}
                    <Badge status={badgeStatus} />
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] p-4">
          <h3 className="mb-3 text-sm font-semibold">Prosecution timeline</h3>
          <div className="flex flex-col gap-2">
            {timeline.length === 0 ? (
              <div className="text-sm text-[var(--mute)]">No transaction history parsed.</div>
            ) : (
              timeline.map((ev, i) => {
                const isVN = (ev.parties ?? []).includes("VN");
                return (
                  <div
                    key={i}
                    className={`border-l-2 pl-3 ${
                      isVN ? "border-[var(--ok,#1a7f4b)]" : "border-[var(--line)]"
                    }`}
                  >
                    <div className="text-xs text-[var(--mute)]">
                      {ev.date ? formatDate(ev.date) : ""}
                      {ev.gazette ? ` · Gaz ${ev.gazette}` : ""}
                    </div>
                    <div className="text-sm">{ev.type ?? ""}</div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {e.source_url && (
        <a
          href={e.source_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-[var(--brand,#34c)] underline"
        >
          View on WIPO Madrid Monitor ↗
        </a>
      )}
    </section>
  );
}
```

> Implementer: verify the CSS-variable token names against the project's `globals.css` / Tailwind config (e.g. `--line`, `--surface`, `--mute`, `--ok`, `--radius-lg`). The fallbacks (`#e8f5ee` etc.) keep it rendering if a token is absent, but prefer the real tokens. Confirm `formatDate` is exported from `@/lib/format`.

- [ ] **Step 2: Typecheck**

Run: `cd app/frontend && pnpm tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/components/detail/madrid-enrichment.tsx
git commit -m "feat(madrid): MadridEnrichment detail component"
```

### Task D2: render it on the detail page

**Files:**
- Modify: `app/frontend/app/(app)/marks/[id]/page.tsx`

- [ ] **Step 1: Import + render.** Add the import near the other detail imports (line ~18-20):

```typescript
import { MadridEnrichment } from "@/components/detail/madrid-enrichment";
```

Render the section where the page composes its detail cards (after the main mark card / goods-services block; place it before "similar marks"). Use the already-loaded `detail`:

```tsx
{detail?.enrichment && <MadridEnrichment e={detail.enrichment} />}
```

- [ ] **Step 2: Verify in the running app.** Start the stack (`docker compose -f app/docker-compose.yml up -d`; backend `uvicorn api.main:app --reload --port 8000`; frontend `pnpm dev`). Open a known enriched Madrid mark detail (find one: a `Trademark` whose `lineage_key` matches a `madrid_records.irn` — e.g. query the DB for `mark_category='madrid_registration'` with an enriched IRN from the pilot 100). Confirm the VN banner, WIPO card, jurisdiction chips, and the reconciled VN status row render, and a domestic mark shows none of it.

- [ ] **Step 3: Typecheck + commit**

```bash
cd app/frontend && pnpm tsc --noEmit
git add app/frontend/app/\(app\)/marks/\[id\]/page.tsx
git commit -m "feat(madrid): render enrichment on mark detail page"
```

---

## GROUP E — Frontend: search filter UI

### Task E1: filter-rail groups

**Files:**
- Modify: `app/frontend/components/search/filter-rail.tsx`

- [ ] **Step 1: Add a "VN status" group + a "Designated jurisdiction" control.** Mirror the existing `mark_category` group: a labelled section listing facet buckets (from `api.facetVnStatus`) with counts, each toggling `vn_status` in the active filters; plus a compact country input/select that sets `designated_country` (a VN quick-toggle "Protected in VN" = `designated_country: "VN"` is the primary control; a free ISO2 country picker is secondary). Read the existing group's props (how it receives `filters`, `facets`, and an `onChange`/URL updater) and follow it exactly — do not invent a new state mechanism.

> Because the rail's exact prop wiring is local to this file, the implementer reads the `mark_category` group in `filter-rail.tsx` and clones it for `vn_status` (facet-backed) and `designated_country` (VN toggle + optional picker). Counts come from `api.facetVnStatus(filters)`.

- [ ] **Step 2: Typecheck + commit**

```bash
cd app/frontend && pnpm tsc --noEmit
git add app/frontend/components/search/filter-rail.tsx
git commit -m "feat(madrid): VN-status + designated-jurisdiction filter rail"
```

### Task E2: wire filters into the search page

**Files:**
- Modify: `app/frontend/app/(app)/search/page.tsx`

- [ ] **Step 1: Read `vn_status` + `designated_country` from the URL** into the `SearchParams` the page builds (mirror `mark_category`), fetch the `facetVnStatus` counts alongside the other facets, render an active-filter chip for each (label via `VN_STATUS_LABELS` / "Covers {cc}"), and include them in the scope/summary label. Follow the `mark_category` handling in this file line-for-line.

- [ ] **Step 2: Verify in the running app.** Apply "Protected in VN" and a `vn_status=granted` filter; confirm the result count changes, a chip appears, and clearing it restores results. Confirm facet counts render.

- [ ] **Step 3: Typecheck + commit**

```bash
cd app/frontend && pnpm tsc --noEmit
git add app/frontend/app/\(app\)/search/page.tsx
git commit -m "feat(madrid): wire VN/jurisdiction filters into search page"
```

---

## Finalization

- [ ] **Backend full suite green**: `cd app/backend && python -m pytest -q`
- [ ] **Frontend typecheck + lint**: `cd app/frontend && pnpm tsc --noEmit && pnpm lint`
- [ ] **Docs sync pass**: confirm `app/README.md` reflects the new endpoint/params/facet; confirm the design spec §8 still matches what shipped (update if the implementation diverged).
- [ ] **Standing constraint**: never stage `README.md` (repo root), `app/.env.example`, or `app/backend/api/settings.py` — they stay as uncommitted working changes. Always `git add` by explicit path; never `git add -A`/`.`.
- [ ] Use **superpowers:finishing-a-development-branch** to decide merge/PR for the whole `madrid-enrichment` branch.

---

## Self-review notes

- **Spec §8 coverage**: VN banner (D1) ✓; WIPO record card + provenance badge (D1) ✓; designated-jurisdiction chips with VN highlight (D1) ✓; two-pane status/timeline (D1) ✓; designated-jurisdiction + optional vn_status search filter (B1/B2/E1/E2) ✓. **Deliberately deferred (YAGNI):** the sidebar "Renewal watch" widget and the `● enriched` source indicator (spec §8 "Sidebar") — additive polish, not required for the core surfacing; surfaced to the user rather than silently dropped. A full per-country designated-jurisdiction *facet* (84 buckets) is omitted; the filter accepts any ISO2 but only VN-status gets a facet (avoids an expensive 84-row group-by; revisit if users want country counts).
- **Type consistency**: `MadridEnrichmentOut` (backend) ↔ `MadridEnrichment` (frontend) field names match the `MadridRecord` columns; `vn_status` values `granted|pending|refused` consistent across filter, facet, labels, and component.
- **Detail-only**: enrichment is on `MarkDetailOut`, never `TrademarkOut` — list/search stay lean (matches the `raw_511_text` precedent).
