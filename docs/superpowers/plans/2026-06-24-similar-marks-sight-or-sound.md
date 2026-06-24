# Similar Marks: sight-or-sound gate + mark_name scoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Full design: `docs/superpowers/specs/2026-06-24-similar-marks-sight-or-sound-design.md` — read it before each task.

**Goal:** Stop the "Similar marks landing this period" card from surfacing same-class marks with no text/visual resemblance, by scoring on the resolved `mark_name` (not `applicant_name`) and gating on the similarity engine's own conjunction verdict (`!= "Low risk"`) instead of a bare `composite ≥ 0.30`.

**Architecture:** Two coupled, migration-free changes inside one function — `app/backend/api/routes/marks.py:similar_marks` (`/{id}/similar`). (A) the anchor + per-candidate scoring text resolve `mark_name or mark_sample` (drop the `applicant_name` fallback); (B) the keep-condition becomes `cs.verdict != "Low risk"`, reusing the conjunction rule already inside `api/similarity.py:composite_score`. No schema change (reuses `trademarks.mark_name` from PR #106 and the existing `verdict`).

**Tech Stack:** FastAPI + SQLAlchemy async (backend); pytest (httpx ASGI). Postgres trigram/dmetaphone recall.

---

## Reference points (read these first)

- `app/backend/api/routes/marks.py:290-422` — the whole `similar_marks` endpoint. Key lines to change:
  - `:9` — stale comment `"(mocked similarity until PR #5)"` (delete; the engine is real).
  - `:305` — `_SIMILAR_MIN_COMPOSITE = 0.30` (delete after Task 2).
  - `:353` — `anchor_word = (m.mark_sample or "").strip()` (→ `mark_name or mark_sample`).
  - `:386` — `m_text = m.mark_sample or m.applicant_name` (→ `mark_name or mark_sample`).
  - `:398` — `r_text = r.mark_sample or r.applicant_name` (→ `mark_name or mark_sample`).
  - `:409-413` — `cs = sim.composite_score(...)` then `if cs.composite >= _SIMILAR_MIN_COMPOSITE: scored.append(...)` (→ gate on `cs.verdict`).
- `app/backend/api/similarity.py:395-399` — `CompositeScore` dataclass: fields `composite: float`, `verdict: Literal["Likely conflict","Possible conflict","Low risk"]`, `verdict_tone`. The gate reads `.verdict`.
- `app/backend/tests/test_search_mark_name.py` — the seeding template (Gazette + Trademark, `async_sessionmaker`, autouse fixture with teardown `delete(...).where(gazette_id == _GZ)`). Copy its structure exactly.
- `app/backend/api/db/__init__.py` exports `Gazette, GazetteStatus, GazetteType, RecordType, Trademark` (used by the test imports).

**Standing constraints (apply to every task):**
- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. Run targeted pytest locally (full sweep tests reset the live `domestic_sweep_control` singleton).
- No migration in this feature.
- Run all commands from `app/backend` using the venv: `../.venv/bin/<tool>`.

---

## Task 1: Score on `mark_name`, drop the applicant fallback (change A)

**Files:**
- Modify: `app/backend/api/routes/marks.py:386,398`
- Test: `app/backend/tests/test_similar_marks_name_scoring.py` (create)

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_similar_marks_name_scoring.py`:

```python
"""similar_marks scores on the resolved mark_name, never the applicant name."""

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
from api.settings import get_settings

_GZ = uuid.UUID("e1000000-0000-4000-8000-0000000000a1")
_SUBJECT = uuid.UUID("e1000000-0000-4000-8000-0000000000a2")
_CANDIDATE = uuid.UUID("e1000000-0000-4000-8000-0000000000a3")


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="A_TEST_similar_name.pdf",
                sha256="similar_name_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Subject: figurative (no mark_sample) with a resolved name "Gemy".
        # Its APPLICANT is phonetically identical to the candidate's wordmark —
        # the old code (m_text = applicant) would score them as a match.
        s.add(
            Trademark(
                id=_SUBJECT,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="SN-2099-1",
                mark_sample=None,
                mark_name="Gemy",
                applicant_name="FOSHAN AILIHUA SANITARY WARE",
                nice_classes=[11],
                publication_date_441=date(2099, 1, 1),
            )
        )
        # Candidate wordmark phonetically close to the subject's APPLICANT, not
        # its name. Must NOT be surfaced once we stop scoring the applicant.
        s.add(
            Trademark(
                id=_CANDIDATE,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="SN-2099-2",
                mark_sample="FOSHAN AILIHUA SANITARY WORKS",
                mark_name="FOSHAN AILIHUA SANITARY WORKS",
                applicant_name="SOME OTHER CO",
                nice_classes=[11],
                publication_date_441=date(2099, 1, 1),
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_similar_does_not_score_applicant_name(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_SUBJECT}/similar", params={"limit": 4})
    assert r.status_code == 200
    appnos = {item["mark"]["application_number"] for item in r.json()}
    # The candidate only "matches" via the subject's applicant text, which is no
    # longer scored, so it must not appear.
    assert "SN-2099-2" not in appnos
```

- [ ] **Step 2: Run → fail**

Run: `cd app/backend && ../.venv/bin/pytest tests/test_similar_marks_name_scoring.py -q`
Expected: FAIL — under current code the subject's `m_text` falls back to `applicant_name` ("FOSHAN AILIHUA SANITARY WARE"), matches the candidate wordmark, and `SN-2099-2` is returned.

- [ ] **Step 3: Implement change A**

In `app/backend/api/routes/marks.py`, change the subject text line (currently `:386`):

```python
    m_text = (m.mark_name or m.mark_sample or "").strip()
```

and the per-candidate text line inside the `for r in candidates:` loop (currently `:398`):

```python
        r_text = (r.mark_name or r.mark_sample or "").strip()
```

(Drop `applicant_name` from both. Leave everything else in the loop unchanged.)

- [ ] **Step 4: Run → pass**

Run: `cd app/backend && ../.venv/bin/pytest tests/test_similar_marks_name_scoring.py -q`
Expected: PASS — subject `m_text` is now "Gemy"; it does not match the candidate wordmark, so `SN-2099-2` is absent.

- [ ] **Step 5: Gates + commit**

```bash
cd app/backend
../.venv/bin/ruff format api/routes/marks.py tests/test_similar_marks_name_scoring.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker
../.venv/bin/pytest tests/test_similar_marks_name_scoring.py -q
git add api/routes/marks.py tests/test_similar_marks_name_scoring.py
git commit -m "fix(similar): score on mark_name, drop applicant-name fallback"
```

---

## Task 2: Recall by `mark_name` + verdict gate (change B)

**Files:**
- Modify: `app/backend/api/routes/marks.py:9,305,353,409-413`
- Test: `app/backend/tests/test_similar_marks_verdict_gate.py` (create)

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_similar_marks_verdict_gate.py`:

```python
"""similar_marks recalls by mark_name and gates on the engine conjunction verdict."""

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
from api.settings import get_settings

_GZ = uuid.UUID("e2000000-0000-4000-8000-0000000000b1")
_SUBJECT = uuid.UUID("e2000000-0000-4000-8000-0000000000b2")   # "Gemy", class 11
_CLASSMATE = uuid.UUID("e2000000-0000-4000-8000-0000000000b3")  # unrelated name, class 11
_NEAR_SAME = uuid.UUID("e2000000-0000-4000-8000-0000000000b4")  # "Gemmy", class 11
_NEAR_DIFF = uuid.UUID("e2000000-0000-4000-8000-0000000000b5")  # "Gemmy", class 42


def _tm(tid: uuid.UUID, appno: str, sample: str | None, name: str, classes: list[int]) -> Trademark:
    return Trademark(
        id=tid,
        gazette_id=_GZ,
        record_type=RecordType.A,
        application_number=appno,
        mark_sample=sample,
        mark_name=name,
        applicant_name="APPLICANT " + appno,
        nice_classes=classes,
        publication_date_441=date(2099, 1, 1),
    )


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="A_TEST_verdict_gate.pdf",
                sha256="verdict_gate_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        s.add(_tm(_SUBJECT, "VG-1", None, "Gemy", [11]))
        s.add(_tm(_CLASSMATE, "VG-2", "KAVIN SAVING POWER", "KAVIN SAVING POWER", [11]))
        s.add(_tm(_NEAR_SAME, "VG-3", "Gemmy", "Gemmy", [11]))
        s.add(_tm(_NEAR_DIFF, "VG-4", "Gemmy", "Gemmy", [42]))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


async def _appnos(client: AsyncClient) -> set[str]:
    r = await client.get(f"/api/v1/marks/{_SUBJECT}/similar", params={"limit": 10})
    assert r.status_code == 200
    return {item["mark"]["application_number"] for item in r.json()}


@pytest.mark.asyncio
async def test_class_only_classmate_excluded(client: AsyncClient) -> None:
    # The reported Gemy bug: a same-class wordmark with no name resemblance.
    assert "VG-2" not in await _appnos(client)


@pytest.mark.asyncio
async def test_real_name_match_same_class_included(client: AsyncClient) -> None:
    # "Gemmy" in the same class — real sight-or-sound + related goods → shown.
    assert "VG-3" in await _appnos(client)


@pytest.mark.asyncio
async def test_name_match_but_class_mismatch_excluded(client: AsyncClient) -> None:
    # Same name "Gemmy" but a non-overlapping class → verdict "Low risk" → dropped.
    assert "VG-4" not in await _appnos(client)
```

- [ ] **Step 2: Run → fail**

Run: `cd app/backend && ../.venv/bin/pytest tests/test_similar_marks_verdict_gate.py -q`
Expected: FAIL — with the current code the subject "Gemy" (empty `mark_sample`) uses the class+period screen, so `VG-2` (class-mate) is recalled and clears `composite ≥ 0.30` → `test_class_only_classmate_excluded` fails; `VG-4` (name match, different class) clears 0.30 on name alone → `test_name_match_but_class_mismatch_excluded` fails.

- [ ] **Step 3: Implement change B**

In `app/backend/api/routes/marks.py`:

(a) Update the recall anchor (currently `:353`):

```python
    anchor_word = (m.mark_name or m.mark_sample or "").strip()
```

(b) Replace the keep-condition. The current block (around `:409-413`) is:

```python
        cs = sim.composite_score(
            phon, vis.score, class_o, vienna_o, weights=weights, visual_confidence=vis.confidence
        )
        if cs.composite >= _SIMILAR_MIN_COMPOSITE:
            scored.append((r, cs.composite, vis.confidence))
```

Change the `if` to gate on the engine verdict (the conjunction rule):

```python
        cs = sim.composite_score(
            phon, vis.score, class_o, vienna_o, weights=weights, visual_confidence=vis.confidence
        )
        # Surface only marks the engine itself verdicts a Possible/Likely conflict
        # (its conjunction rule: mark_strength >= 0.50 AND class >= 0.20 AND
        # composite >= 0.50). "Low risk" means class overlap alone — not a similar
        # mark — so it is excluded. Same rule Compare uses; single source of truth.
        if cs.verdict != "Low risk":
            scored.append((r, cs.composite, vis.confidence))
```

(c) Delete the now-unused constant block (currently `:301-305`, the comment + `_SIMILAR_MIN_COMPOSITE = 0.30`).

(d) Delete the stale comment fragment at `:9` (`"(mocked similarity until PR #5)"`) — read the surrounding module docstring/comment and remove just that parenthetical, since the real engine now backs this endpoint.

- [ ] **Step 4: Run → pass**

Run: `cd app/backend && ../.venv/bin/pytest tests/test_similar_marks_verdict_gate.py tests/test_similar_marks_name_scoring.py -q`
Expected: PASS — `VG-2` and `VG-4` excluded, `VG-3` included; Task 1's test still green.

- [ ] **Step 5: Guard against regressions in the wider similarity suite**

Run: `cd app/backend && ../.venv/bin/pytest tests/test_similarity.py tests/test_per_matter_weights.py tests/test_search_phonetic_two_stage.py -q`
Expected: PASS (no references to `_SIMILAR_MIN_COMPOSITE` outside `marks.py`; if any test imported it, update that test to the verdict gate). If a test fails because it asserted the old 0.30 behaviour, read it and adjust the assertion to the conjunction verdict — do not re-add the constant.

- [ ] **Step 6: Gates + commit**

```bash
cd app/backend
../.venv/bin/ruff format api/routes/marks.py tests/test_similar_marks_verdict_gate.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker && ../.venv/bin/alembic check
../.venv/bin/pytest tests/test_similar_marks_verdict_gate.py tests/test_similar_marks_name_scoring.py -q
git add api/routes/marks.py tests/test_similar_marks_verdict_gate.py
git commit -m "fix(similar): recall by mark_name + gate on conjunction verdict (drop composite>=0.30)"
```

---

## Task 3: Manual verification + docs sync

**Files:**
- Modify: `CLAUDE.md` (only if it documents the similar-marks threshold — search first)

- [ ] **Step 1: Verify the reported case live.** With the API running (host uvicorn on :8000) and the frontend on :3000, open `/marks/1658e936-0124-474a-8918-6e53d8a38f71` ("Gemy") and scroll to "Similar marks landing this period". Expected: the card no longer lists KAVIN SAVING / KAITA / Kastaler / LỘC TỔNG HUY — it shows real look-/sound-alikes or an empty state. (Do NOT `pnpm build` while `pnpm dev` is live; no frontend code change is needed — the card already handles an empty list.)

- [ ] **Step 2: Docs sync.** Search the repo for any doc that states the old behaviour:

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
grep -rniE "_SIMILAR_MIN_COMPOSITE|0\.30|similar marks" CLAUDE.md docs/ README.md app/backend/README.md 2>/dev/null
```

If a hit describes the `composite ≥ 0.30` threshold or the class-screen recall as current behaviour, update it to: "the card recalls by `mark_name` and surfaces only engine Possible/Likely-conflict verdicts (the sight-or-sound conjunction rule)". If no hit, note "no doc references the threshold" and proceed.

- [ ] **Step 3: Commit any doc change** (explicit paths; never the trio):

```bash
git add CLAUDE.md   # only the files actually changed
git commit -m "docs(similar): describe mark_name recall + conjunction-verdict gate"
```

(Skip the commit if Step 2 found nothing to change.)

---

## Self-review

- **Spec coverage:** change A — scoring text → `mark_name`, drop applicant (Task 1 ✓); change B — recall anchor → `mark_name` + verdict gate + delete `_SIMILAR_MIN_COMPOSITE` (Task 2 ✓); stale `:9` comment cleanup (Task 2 Step 3d ✓); the 5 spec test cases map to: class-only excluded (Task 2 `test_class_only_classmate_excluded`), real phonetic match included (Task 2 `test_real_name_match_same_class_included`), applicant not scored (Task 1 `test_similar_does_not_score_applicant_name`), verdict-gate parity / class-mismatch (Task 2 `test_name_match_but_class_mismatch_excluded`); the figurative-visual-match case is out of unit scope (needs logo fixtures) and is covered by the live check in Task 3 Step 1. No migration (✓). Out-of-scope `gin_trgm` index correctly omitted.
- **Placeholder scan:** every step has concrete code/commands; no TBD/TODO.
- **Type consistency:** `cs.verdict` (str) compared to `"Low risk"` matches `CompositeScore.verdict` (`api/similarity.py:398`); `m_text`/`r_text` stay `str`; `composite_score` call args unchanged from current code; test imports (`Gazette, GazetteStatus, GazetteType, RecordType, Trademark`) match `test_search_mark_name.py`.
