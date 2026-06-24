# Mark Status Single Source of Truth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Full design: `docs/superpowers/specs/2026-06-24-mark-status-derivation-design.md` — read it before each task.

**Goal:** Replace the `record_type`-based status heuristic (duplicated in compare + mark-detail) with one shared helper that derives an IP VIETNAM-faithful label + a normalized tone from the enriched data, and surface real status on `/compare` (drop the `isA` stub).

**Architecture:** A new pure `api/_status.py:derive_status`. mark-detail and compare both call it; compare gains `status_label`/`status_tone` payload fields. No migration (uses `domestic_records.status_code` + the existing `trademarks.vn_grant_date`).

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Next.js 15 + React (frontend).

---

## Reference points (read these)

- `app/backend/api/routes/marks.py:82–101` — the mark-detail status heuristic to replace (`status_label`/`status_tone` returned via `MarkDetailOut`; uses `DEMO_TODAY`, `m.record_type`, `m.expiry_date_141`). Read how the endpoint exposes the joined domestic record (CLAUDE.md: the mark API returns a `domestic` field from `domestic_records`) to get `status_code`.
- `app/backend/api/routes/compare.py` — `CompareResponse` (`:68`) + the per-mark builder; the compare query (add a LEFT JOIN to `domestic_records` for `status_code`; `vn_grant_date` is already on `Trademark`).
- `app/backend/api/db/models.py` — `Trademark.vn_grant_date`, `DomesticRecord.status_code`, the mark expiry field.
- `app/frontend/app/(app)/compare/page.tsx:112–122` — the `isA ? "Pending publication" : "Active"` stub to replace.
- `app/frontend/lib/api.ts` — the compare-mark TS type to extend; `PulseDot` tone prop usage.

---

## Task 1: `derive_status` helper + wire into mark-detail

**Files:** Create `app/backend/api/_status.py`, `app/backend/tests/test_status.py`; Modify `app/backend/api/routes/marks.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_status.py
from datetime import date
from api._status import derive_status

T = date(2026, 6, 24)

def test_enriched_status_code_verbatim_with_grant():
    assert derive_status("Cấp bằng", date(2024, 12, 9), None, today=T) == ("Cấp bằng", "ok")

def test_enriched_status_code_no_grant_warn():
    assert derive_status("Đang giải quyết", None, None, today=T) == ("Đang giải quyết", "warn")

def test_unenriched_granted():
    assert derive_status(None, date(2023, 1, 2), None, today=T) == ("Granted", "ok")

def test_expired_lapsed():
    assert derive_status(None, None, date(2020, 1, 1), today=T) == ("Lapsed", "mute")

def test_pending_default():
    assert derive_status(None, None, None, today=T) == ("Pending", "warn")

def test_empty_status_code_falls_back():
    assert derive_status("", None, None, today=T) == ("Pending", "warn")
```

- [ ] **Step 2: Run → fail** — `cd app/backend && ../.venv/bin/pytest tests/test_status.py -q` → ImportError.

- [ ] **Step 3: Implement `app/backend/api/_status.py`**

```python
"""Single source of truth for a mark's display status (label + tone).

Label is IP VIETNAM-faithful: the enriched domestic status_code verbatim when
present, else a normalized fallback (Granted/Lapsed/Pending). Tone is normalized
from grant/expiry so even a Vietnamese status string gets a sensible color.
"""

from __future__ import annotations

from datetime import date


def derive_status(
    domestic_status_code: str | None,
    vn_grant_date: date | None,
    expiry_date: date | None,
    *,
    today: date,
) -> tuple[str, str]:
    """Return (label, tone); tone in {"ok", "warn", "mute"}."""
    if vn_grant_date is not None:
        tone = "ok"
    elif expiry_date is not None and expiry_date < today:
        tone = "mute"
    else:
        tone = "warn"

    if domestic_status_code:
        label = domestic_status_code
    elif vn_grant_date is not None:
        label = "Granted"
    elif expiry_date is not None and expiry_date < today:
        label = "Lapsed"
    else:
        label = "Pending"
    return label, tone
```

- [ ] **Step 4: Run → pass** — 6 passed.

- [ ] **Step 5: Wire into mark-detail.** In `marks.py`, replace the `record_type` status block (`:87–93`) with the helper. Resolve `domestic_status_code` from the joined domestic record the endpoint already loads (read the file — it exposes a `domestic`/`domestic_records` value); use `m.vn_grant_date` and the expiry it already uses (`m.expiry_date_141`):

```python
    from api._status import derive_status
    domestic_status_code = domestic.status_code if domestic else None  # `domestic` = the joined domestic_records row (adapt to the real variable)
    status_label, status_tone = derive_status(
        domestic_status_code, m.vn_grant_date, m.expiry_date_141, today=today
    )
```

> Adapt `domestic`/`domestic.status_code` to the endpoint's real variable for the joined domestic record. Keep the `opp_ends`/opposition logic above it unchanged.

- [ ] **Step 6: Gates + commit** — from `app/backend`: `../.venv/bin/ruff format api/_status.py api/routes/marks.py tests/test_status.py && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker && ../.venv/bin/pytest tests/test_status.py -q`. Then `git add app/backend/api/_status.py app/backend/api/routes/marks.py app/backend/tests/test_status.py && git commit -m "feat(status): derive_status single source of truth; use in mark-detail"`.

---

## Task 2: Compare backend — add `status_label`/`status_tone`

**Files:** Modify `app/backend/api/routes/compare.py`; Test `app/backend/tests/test_compare_status.py`.

- [ ] **Step 1: Write the failing test** — seed a domestic A-file mark enriched as granted (vn_grant_date set + domestic_records.status_code), assert the compare response carries the real status (NOT "Pending publication"):

```python
# tests/test_compare_status.py
import pytest

@pytest.mark.asyncio
async def test_compare_includes_real_status(client, seed_two_marks):
    ids = await seed_two_marks()  # one granted ("Cấp bằng", vn_grant_date set), one pending
    r = await client.post("/api/v1/compare", json={"ids": ids})
    marks = {m["id"]: m for m in r.json()["marks"]}
    granted = marks[ids[0]]
    assert granted["status_label"] == "Cấp bằng"
    assert granted["status_tone"] == "ok"
    pending = marks[ids[1]]
    assert pending["status_label"] == "Pending"
    assert pending["status_tone"] == "warn"
```

> Adapt `client`/`seed_two_marks` + request/response shape (`/api/v1/compare`, `ids`, `marks`) to the route's actual contract — read `compare.py` first.

- [ ] **Step 2: Run → fail** (KeyError 'status_label').

- [ ] **Step 3: Implement.** In `compare.py`:
  - Extend the per-mark output model (the entry inside `CompareResponse.marks`) with `status_label: str` and `status_tone: str`.
  - In the compare query, LEFT JOIN `DomesticRecord` on `application_number` to fetch `status_code` per mark (load it alongside the Trademark; `vn_grant_date` is already a Trademark column).
  - When building each mark entry, call `derive_status(domestic_status_code, mark.vn_grant_date, <expiry>, today=DEMO_TODAY)` and set the two fields. Use the same expiry field marks.py uses (`expiry_date_141`) and the same `DEMO_TODAY`.

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Gates + commit** (`ruff` + `mypy`, targeted pytest). `git add app/backend/api/routes/compare.py app/backend/tests/test_compare_status.py && git commit -m "feat(compare): real status_label/status_tone per mark via derive_status"`.

---

## Task 3: Frontend — render real compare status; drop the stub

**Files:** Modify `app/frontend/app/(app)/compare/page.tsx`, `app/frontend/lib/api.ts`.

- [ ] **Step 1:** In `lib/api.ts`, add to the compare-mark type: `status_label: string;` and `status_tone: "ok" | "warn" | "mute";` (match the existing compare-mark interface name).
- [ ] **Step 2:** In `compare/page.tsx`, replace the Status `CmpRow` body (`:112–122`) — drop the `isA` ternary:

```tsx
<CmpRow label="Status" n={N}>
  {data.marks.map((m) => (
    <span key={m.id} className="flex items-center gap-2">
      <PulseDot tone={m.status_tone} />
      {m.status_label}
    </span>
  ))}
</CmpRow>
```

(Confirm `PulseDot`'s `tone` accepts `"ok"|"warn"|"mute"` — it's used that way elsewhere on this page.)

- [ ] **Step 3: Verify** — `cd app/frontend && npx tsc --noEmit && pnpm lint` (NEVER `pnpm build` while `pnpm dev` is live). Browser-check `/compare?ids=...`: each mark shows its real status (granted marks → "Cấp bằng"/green, pending → "Pending"/amber), not "Pending publication" for everything.
- [ ] **Step 4: Commit** — `git add "app/frontend/app/(app)/compare/page.tsx" app/frontend/lib/api.ts && git commit -m "fix(compare): render real mark status, drop isA stub"`.

---

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest` (targeted pytest — sweep tests reset the live singleton). No migration in this feature.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.
- PR `fix(status): single-source mark status (faithful label + normalized tone); fix /compare`.

## Self-review

- **Spec coverage:** helper (Task 1 ✓); mark-detail rewired (Task 1 ✓); compare payload status fields + join (Task 2 ✓); frontend drops stub (Task 3 ✓); faithful label + normalized tone (helper logic ✓); no migration (✓). All mapped.
- **Type consistency:** `derive_status(status_code, vn_grant_date, expiry, *, today) -> (label, tone)` identical across Task 1 + 2; `status_label`/`status_tone` field names consistent across Task 2 (backend) + Task 3 (frontend type + render).
- **Placeholders:** helper given in full; mark-detail/compare wiring cites exact lines + flags the joined-domestic variable to adapt; frontend render block given in full.
