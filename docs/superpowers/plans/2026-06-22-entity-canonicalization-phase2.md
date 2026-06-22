# Entity Canonicalization Phase 2 — Denormalized Clean Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Denormalize the resolved clean applicant/representative names onto `trademarks` (`*_clean` display + indexed `*_norm` grouping key) via an idempotent backfill, and switch the `/overview` **domestic** panels to a `GROUP BY *_norm` over the indexed columns — same numbers as Phase 1, faster path that scales at any DB size.

**Architecture:** Each mark already carries a deterministic key to its trusted record (`application_number → domestic_records`, `lineage_key=irn → madrid_records`). A re-runnable backfill resolves the best source per mark (NOIP → WIPO → gazette fallback), reusing the Phase-1 `norm()`/`strip_madrid_rep_address()` so the stored `*_norm` is byte-identical to what the dashboard groups by. Idempotency is recompute-and-compare (no per-row version column); `ENTITY_CLEAN_VERSION` documents the derivation logic. The `/overview` **domestic** applicant + representative panels move to `GROUP BY *_norm` (Postgres `mode() WITHIN GROUP` picks the display spelling); the **Madrid** panels stay on `madrid_records` (per-IRN) to keep their counts unchanged — a deliberate decision (see Design Notes).

**Tech Stack:** FastAPI · async SQLAlchemy 2 · Postgres · Alembic · pytest (pytest-asyncio + httpx ASGI).

---

## Design Notes (read before starting)

- **Madrid panels stay per-IRN.** Phase 1 counts Madrid applicant/representative panels by iterating `madrid_records` (one row per IRN, 4,439). Denormalizing onto `trademarks` would make grouping per-mark (6,735, incl. ~2,290 un-enriched marks + 6 IRNs mapping to 2 marks), changing the Madrid numbers. The user chose to **keep Madrid per-IRN**, so only the **domestic** panels (which already iterate `trademarks` per-mark in Phase 1) switch to the indexed columns. Domestic counts are therefore provably unchanged; Madrid keeps its existing source. The denormalized columns are still backfilled on **all** marks for future search/mark-detail consumers.
- **Precedence is safe via mutual exclusivity.** A domestic mark has no `irn`-matching `lineage_key`; a Madrid mark has no `application_number`. So `domestic OR madrid OR gazette` cannot cross-contaminate. The backfill additionally gates each candidate by `mark_category` to mirror Phase 1's per-category sourcing exactly.
- **No per-row version column.** The spec's migration lists exactly 4 columns. Idempotency comes from comparing the computed `(clean, norm)` tuple against the stored values and only `UPDATE`-ing changed rows. `ENTITY_CLEAN_VERSION` (in `_entity_norm.py`) is the derivation's logical version, surfaced in the backfill log; bump it after changing the derivation and the next run rewrites affected rows.
- **Tests must be sweep-safe.** The live `domestic`/`madrid` sweeps write rows continuously. Per the project memory `overview-tests-snapshot-not-endpoint-vs-recompute`, never compare an endpoint response against a *separately-recomputed* value across a request boundary — it races the sweep. All deterministic assertions here are scoped to synthetic FUTURE-year gazettes / explicit ids the sweep never touches.
- **Standing constraint:** NEVER `git add` the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). Stage every commit by explicit path.
- **Post-implementation corrections (Task 3).** The `bf_seed` fixture and `_flush` snippets below were corrected to match what was committed: seed `record_type` uses the regime-correct enum members (`RecordType.B_domestic` for the 4 domestic rows, `RecordType.B_madrid` for the 2 madrid rows — the enum has no `.B` member); and `_flush` targets the Core table (`update(Trademark.__table__)` / `Trademark.__table__.c.id`) because SQLAlchemy 2.0 rejects ORM bulk-UPDATE-by-PK with a non-`id` executemany param key (`b_id`).

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/api/_entity_norm.py` (modify) | Add `ENTITY_CLEAN_VERSION` + pure `resolve_applicant()` / `resolve_representative()` (NOIP→WIPO→gazette precedence; Madrid rep address-strip). Reuses existing `norm()` / `strip_madrid_rep_address()`. |
| `app/backend/api/db/models.py` (modify) | Add 4 columns to `Trademark` (`applicant_clean`, `applicant_norm`, `representative_clean`, `representative_norm`); `*_norm` get `index=True`. |
| `app/backend/alembic/versions/20260622_0023_entity_clean_columns.py` (create) | Add the 4 columns + 2 btree indexes; reversible downgrade. |
| `app/backend/scripts/backfill_entity_clean.py` (create) | Re-runnable idempotent backfill: resolve per-mark, `UPDATE` only changed rows, return `{scanned, updated, unchanged}`. |
| `app/backend/api/routes/gazettes.py` (modify) | Switch domestic applicant + representative panels to `GROUP BY *_norm` via a new `_top_entities_column()` SQL helper; Madrid panels unchanged. |
| `app/backend/tests/test_entity_norm.py` (modify) | Unit tests for `resolve_*` precedence / strip / blank / variant-collapse. |
| `app/backend/tests/test_entity_clean_backfill.py` (create) | DB tests: backfill populates per precedence, collapses variants, idempotent 2nd run; migration columns+indexes exist. |
| `app/backend/tests/test_gazettes_overview.py` (modify) | Seed the 4 columns on synthetic domestic marks; add deterministic test that the column `GROUP BY` path equals the Phase-1 join grouping over the seeded subset. |
| `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md` (modify) | Mark Phase 2 implemented. |
| `CLAUDE.md` (modify) | Document the new columns + backfill script. |

---

### Task 1: Pure resolver + version constant in `_entity_norm.py`

**Files:**
- Modify: `app/backend/api/_entity_norm.py`
- Test: `app/backend/tests/test_entity_norm.py`

- [ ] **Step 1: Write the failing tests**

Append to `app/backend/tests/test_entity_norm.py`:

```python
from api._entity_norm import (
    ENTITY_CLEAN_VERSION,
    resolve_applicant,
    resolve_representative,
)


def test_entity_clean_version_is_a_positive_int():
    assert isinstance(ENTITY_CLEAN_VERSION, int)
    assert ENTITY_CLEAN_VERSION >= 1


def test_resolve_applicant_precedence_noip_over_wipo_over_gazette():
    # NOIP (domestic) wins outright.
    assert resolve_applicant("NOIP Co", "WIPO Co", "Gazette Co")[0] == "NOIP Co"
    # WIPO wins when no NOIP.
    assert resolve_applicant(None, "WIPO Co", "Gazette Co")[0] == "WIPO Co"
    # Gazette is the last-resort fallback.
    assert resolve_applicant(None, None, "Gazette Co")[0] == "Gazette Co"
    # Nothing at all → (None, None).
    assert resolve_applicant(None, None, None) == (None, None)


def test_resolve_applicant_blank_strings_are_skipped():
    # Empty / whitespace-only trusted values fall through to the next source.
    assert resolve_applicant("", "WIPO Co", None)[0] == "WIPO Co"
    assert resolve_applicant("   ", None, "Gazette Co")[0] == "Gazette Co"
    assert resolve_applicant("  ", "", "  ") == (None, None)


def test_resolve_applicant_returns_clean_and_norm():
    from api._entity_norm import norm

    clean, key = resolve_applicant("  Công ty TAGA  ", None, None)
    assert clean == "Công ty TAGA"  # trimmed, spelling preserved
    assert key == norm("Công ty TAGA")


def test_resolve_applicant_variants_collapse_to_one_norm():
    _, a = resolve_applicant("Công ty Luật TAGA", None, None)
    _, b = resolve_applicant("CÔNG TY LUẬT TAGA", None, None)
    _, c = resolve_applicant("Công  ty   Luật   TAGA", None, None)
    assert a == b == c
    _, distinct = resolve_applicant("Distinct Firm XYZ", None, None)
    assert distinct != a


def test_resolve_representative_strips_madrid_glued_address_only_for_wipo():
    # WIPO representative carries a glued trailing address — stripped before norm.
    clean, _ = resolve_representative(None, "OVW REP ALPHA 123 Main St, Zürich", None)
    assert clean == "OVW REP ALPHA"
    # NOIP representative is taken verbatim (no address strip applied).
    clean, _ = resolve_representative("Công ty Luật TAGA 12 Pho X", None, None)
    assert clean == "Công ty Luật TAGA 12 Pho X"


def test_resolve_representative_precedence():
    assert resolve_representative("NOIP Rep", "WIPO Rep 1 St", "Gaz Rep")[0] == "NOIP Rep"
    assert resolve_representative(None, "WIPO Rep 1 St", "Gaz Rep")[0] == "WIPO Rep"
    assert resolve_representative(None, None, "Gaz Rep")[0] == "Gaz Rep"
    assert resolve_representative(None, None, None) == (None, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd app/backend && python -m pytest tests/test_entity_norm.py -k "entity_clean_version or resolve_" -v`
Expected: FAIL — `ImportError: cannot import name 'ENTITY_CLEAN_VERSION'` (and `resolve_applicant` / `resolve_representative`).

- [ ] **Step 3: Implement the resolver + constant**

Append to `app/backend/api/_entity_norm.py` (after `strip_madrid_rep_address`):

```python
ENTITY_CLEAN_VERSION = 1
"""Logical version of the clean-name derivation in resolve_applicant /
resolve_representative. There is NO per-row version column — the backfill
(scripts/backfill_entity_clean.py) is idempotent by recompute-and-compare —
so this constant is a documentation/trigger marker: bump it after changing
the derivation and the next backfill run rewrites the affected rows. Surfaced
in the backfill log."""


def _clean_and_norm(raw: str | None) -> tuple[str | None, str | None]:
    """Trim `raw`, returning (clean_display, norm_key) or (None, None) when it
    is blank or norms to empty. `clean` keeps the original spelling for display;
    `norm_key` is the grouping key."""
    if not raw:
        return None, None
    clean = raw.strip()
    if not clean:
        return None, None
    key = norm(clean)
    if not key:
        return None, None
    return clean, key


def _first_nonblank(*vals: str | None) -> str | None:
    """First value that is non-None and not whitespace-only."""
    for v in vals:
        if v and v.strip():
            return v
    return None


def resolve_applicant(
    domestic: str | None, madrid: str | None, gazette: str | None
) -> tuple[str | None, str | None]:
    """Trusted display name + grouping key for an applicant.

    Precedence: NOIP (`domestic_records.applicant_name`) → WIPO
    (`madrid_records.holder_name`) → gazette fallback
    (`trademarks.applicant_name`). The callers gate `domestic`/`madrid` by
    `mark_category`, so at most one is set per mark.
    """
    return _clean_and_norm(_first_nonblank(domestic, madrid, gazette))


def resolve_representative(
    domestic: str | None, madrid: str | None, gazette: str | None
) -> tuple[str | None, str | None]:
    """Trusted display name + grouping key for a representative.

    Precedence NOIP (`domestic_records.representative`) → WIPO
    (`madrid_records.representative`) → gazette fallback
    (`trademarks.ip_agency_raw_740`). The WIPO value glues a trailing postal
    address onto the firm name; strip it (deterministic cut) before clean/norm.
    """
    if domestic and domestic.strip():
        return _clean_and_norm(domestic)
    if madrid and madrid.strip():
        return _clean_and_norm(strip_madrid_rep_address(madrid))
    return _clean_and_norm(gazette)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd app/backend && python -m pytest tests/test_entity_norm.py -v`
Expected: PASS (all existing + new tests).

- [ ] **Step 5: Lint + type-check this file**

Run: `cd app/backend && ruff check api/_entity_norm.py && ruff format --check api/_entity_norm.py && mypy api`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/api/_entity_norm.py app/backend/tests/test_entity_norm.py
git commit -m "feat(entity-canon): add clean-name resolver + ENTITY_CLEAN_VERSION (phase 2)"
```

---

### Task 2: Migration + model columns/indexes

**Files:**
- Modify: `app/backend/api/db/models.py` (in `class Trademark`, after the `ip_agency` block ~line 269)
- Create: `app/backend/alembic/versions/20260622_0023_entity_clean_columns.py`
- Test: `app/backend/tests/test_entity_clean_backfill.py`

- [ ] **Step 1: Add the 4 columns to the model**

In `app/backend/api/db/models.py`, immediately after the IP Agency block (the `ip_agency: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)` line), insert:

```python
    # Denormalized clean entity names (Phase 2 of entity canonicalization).
    # Resolved by scripts/backfill_entity_clean.py from the trusted source by
    # deterministic identifier (NOIP→WIPO→gazette). *_clean is the trusted
    # display name; *_norm is norm(*_clean) — the dashboard's GROUP BY key,
    # indexed so /overview groups at any DB size without a per-query join.
    applicant_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_norm: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    representative_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    representative_norm: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
```

`index=True` auto-names the indexes `ix_trademarks_applicant_norm` and `ix_trademarks_representative_norm` — the migration below uses those exact names so `alembic check` finds no drift.

- [ ] **Step 2: Write the migration**

Create `app/backend/alembic/versions/20260622_0023_entity_clean_columns.py`:

```python
"""Denormalized clean entity columns on trademarks (entity-canon phase 2).

Adds applicant_clean/applicant_norm + representative_clean/representative_norm,
btree-indexing the two *_norm grouping keys. Populated by
scripts/backfill_entity_clean.py.

Revision ID: 20260622_0023
Revises: 20260621_0022
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260622_0023"
down_revision: str | None = "20260621_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("applicant_clean", sa.Text(), nullable=True))
    op.add_column("trademarks", sa.Column("applicant_norm", sa.Text(), nullable=True))
    op.add_column("trademarks", sa.Column("representative_clean", sa.Text(), nullable=True))
    op.add_column("trademarks", sa.Column("representative_norm", sa.Text(), nullable=True))
    op.create_index("ix_trademarks_applicant_norm", "trademarks", ["applicant_norm"])
    op.create_index("ix_trademarks_representative_norm", "trademarks", ["representative_norm"])


def downgrade() -> None:
    op.drop_index("ix_trademarks_representative_norm", table_name="trademarks")
    op.drop_index("ix_trademarks_applicant_norm", table_name="trademarks")
    op.drop_column("trademarks", "representative_norm")
    op.drop_column("trademarks", "representative_clean")
    op.drop_column("trademarks", "applicant_norm")
    op.drop_column("trademarks", "applicant_clean")
```

- [ ] **Step 3: Apply the migration to the dev DB**

Run:
```bash
cd app/backend && \
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
alembic upgrade head
```
Expected: `Running upgrade 20260621_0022 -> 20260622_0023`.

- [ ] **Step 4: Verify downgrade reversibility, then re-upgrade (manual round-trip)**

Run:
```bash
cd app/backend && \
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm alembic downgrade -1 && \
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm alembic upgrade head
```
Expected: clean `20260622_0023 -> 20260621_0022` then `20260621_0022 -> 20260622_0023`, no errors. (Downgrade is exercised here as a manual round-trip rather than a destructive pytest, because the test suite runs against this same shared dev DB while the sweeps are writing — dropping columns mid-run would break them.)

- [ ] **Step 5: Verify no schema drift**

Run:
```bash
cd app/backend && \
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm alembic check
```
Expected: `No new upgrade operations detected.` (model and DB now agree).

- [ ] **Step 6: Write the migration-presence test**

Create `app/backend/tests/test_entity_clean_backfill.py` with this first test (more added in Task 3):

```python
"""Phase 2 entity-canon: migration presence + idempotent backfill.

Deterministic and sweep-safe: all DB writes use synthetic ids the live
domestic/madrid sweeps never touch, and the backfill is invoked scoped to
those ids.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import DomesticRecord, MadridRecord
from api.settings import get_settings


@pytest.mark.asyncio
async def test_clean_columns_and_norm_indexes_exist() -> None:
    """The migration added the 4 columns and btree-indexed the two *_norm keys."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        cols = set(
            (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='trademarks' AND column_name = ANY(:cols)"
                    ),
                    {
                        "cols": [
                            "applicant_clean",
                            "applicant_norm",
                            "representative_clean",
                            "representative_norm",
                        ]
                    },
                )
            )
            .scalars()
            .all()
        )
        idx = set(
            (
                await s.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE tablename='trademarks' AND indexname = ANY(:idx)"
                    ),
                    {"idx": ["ix_trademarks_applicant_norm", "ix_trademarks_representative_norm"]},
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert cols == {
        "applicant_clean",
        "applicant_norm",
        "representative_clean",
        "representative_norm",
    }
    assert idx == {"ix_trademarks_applicant_norm", "ix_trademarks_representative_norm"}
```

- [ ] **Step 7: Run the migration test**

Run: `cd app/backend && python -m pytest tests/test_entity_clean_backfill.py::test_clean_columns_and_norm_indexes_exist -v`
Expected: PASS.

- [ ] **Step 8: Lint + type-check + commit**

Run: `cd app/backend && ruff check . && ruff format --check . && mypy api`
Expected: clean.

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/api/db/models.py \
        app/backend/alembic/versions/20260622_0023_entity_clean_columns.py \
        app/backend/tests/test_entity_clean_backfill.py
git commit -m "feat(entity-canon): add denormalized clean entity columns + indexes (phase 2 migration)"
```

---

### Task 3: Idempotent backfill script

**Files:**
- Create: `app/backend/scripts/backfill_entity_clean.py`
- Test: `app/backend/tests/test_entity_clean_backfill.py` (add to the file from Task 2)

- [ ] **Step 1: Write the backfill script**

Create `app/backend/scripts/backfill_entity_clean.py`:

```python
"""Re-runnable, idempotent backfill of the denormalized clean entity columns.

Per trademark, resolves the trusted display name + grouping key for the
applicant and representative by deterministic identifier:
  NOIP   domestic_records  (joined by application_number)
  WIPO   madrid_records    (joined by lineage_key = irn)
  gazette fallback         (trademarks.applicant_name / ip_agency_raw_740)
Candidates are gated by mark_category so each mark draws only from its own
regime's trusted source (mirrors the Phase-1 /overview sourcing).

Reuses api._entity_norm so the stored *_norm is byte-identical to what the
dashboard groups by. Idempotent: only rows whose computed (clean, norm) differ
from the stored values are UPDATEd, so a second run is a no-op. Bump
ENTITY_CLEAN_VERSION (api/_entity_norm.py) after changing the derivation; the
next run then rewrites the affected rows.

No network. Run against the dev DB or inside any worker container:

    docker compose -f app/docker-compose.yml exec -T worker-domestic \
        python -m scripts.backfill_entity_clean
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._entity_norm import (
    ENTITY_CLEAN_VERSION,
    resolve_applicant,
    resolve_representative,
)
from api.db.models import DomesticRecord, MadridRecord, Trademark

log = logging.getLogger("entity.backfill")

_DOMESTIC = ("domestic_application", "domestic_registration")
_MADRID = ("madrid_registration", "madrid_renewal")
_CHUNK = 1000


async def backfill(session: AsyncSession, *, ids: Sequence[object] | None = None) -> dict[str, int]:
    """Resolve + write clean columns for every trademark (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    stmt = (
        select(
            Trademark.id,
            Trademark.mark_category,
            Trademark.applicant_clean,
            Trademark.applicant_norm,
            Trademark.representative_clean,
            Trademark.representative_norm,
            DomesticRecord.applicant_name.label("dom_app"),
            DomesticRecord.representative.label("dom_rep"),
            MadridRecord.holder_name.label("mad_app"),
            MadridRecord.representative.label("mad_rep"),
            Trademark.applicant_name.label("gaz_app"),
            Trademark.ip_agency_raw_740.label("gaz_rep"),
        )
        .select_from(Trademark)
        .outerjoin(
            DomesticRecord,
            DomesticRecord.application_number == Trademark.application_number,
        )
        .outerjoin(MadridRecord, MadridRecord.irn == Trademark.lineage_key)
    )
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        is_dom = row.mark_category in _DOMESTIC
        is_mad = row.mark_category in _MADRID
        app_clean, app_norm = resolve_applicant(
            row.dom_app if is_dom else None,
            row.mad_app if is_mad else None,
            row.gaz_app,
        )
        rep_clean, rep_norm = resolve_representative(
            row.dom_rep if is_dom else None,
            row.mad_rep if is_mad else None,
            row.gaz_rep,
        )
        if (app_clean, app_norm, rep_clean, rep_norm) == (
            row.applicant_clean,
            row.applicant_norm,
            row.representative_clean,
            row.representative_norm,
        ):
            stats["unchanged"] += 1
            continue
        pending.append(
            {
                "b_id": row.id,
                "applicant_clean": app_clean,
                "applicant_norm": app_norm,
                "representative_clean": rep_clean,
                "representative_norm": rep_norm,
            }
        )
        if len(pending) >= _CHUNK:
            await _flush(session, pending)
            stats["updated"] += len(pending)
            pending.clear()

    if pending:
        await _flush(session, pending)
        stats["updated"] += len(pending)
    return stats


async def _flush(session: AsyncSession, rows: list[dict[str, object]]) -> None:
    stmt = (
        update(Trademark.__table__)
        .where(Trademark.__table__.c.id == bindparam("b_id"))
        .values(
            applicant_clean=bindparam("applicant_clean"),
            applicant_norm=bindparam("applicant_norm"),
            representative_clean=bindparam("representative_clean"),
            representative_norm=bindparam("representative_norm"),
        )
    )
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling entity clean columns (ENTITY_CLEAN_VERSION=%d)", ENTITY_CLEAN_VERSION)
    async with sessionmaker() as session:
        stats = await backfill(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: Write the failing backfill tests**

Append to `app/backend/tests/test_entity_clean_backfill.py`:

```python
# Synthetic ids the live sweeps never touch.
_GZ = uuid.UUID("e2000000-0000-4000-8000-0000000000c1")
_IRN_A = "9300001"
_IRN_B = "9300002"
_APPNOS = ["BFAPP0", "BFAPP1", "BFAPP2", "BFAPP3"]  # 3 variants of one firm + 1 distinct
_TM_IDS = [uuid.UUID(f"e2000000-0000-4000-8000-00000000{i:04d}") for i in range(10, 16)]


@pytest_asyncio.fixture
async def bf_seed() -> AsyncIterator[list[uuid.UUID]]:
    """Seed: 4 domestic marks (3 NOIP-rep variants of one firm + 1 distinct),
    1 madrid mark with a WIPO record (glued-address rep), 1 un-enriched madrid
    mark (gazette fallback only)."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(delete(Trademark).where(Trademark.id.in_(_TM_IDS)))
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number.in_(_APPNOS)))
        await s.execute(delete(MadridRecord).where(MadridRecord.irn.in_([_IRN_A, _IRN_B])))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        s.add(
            Gazette(
                id=_GZ,
                filename="B_T1_2097.pdf",
                sha256="bf_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2097,
                issue_number=1,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # 4 domestic_registration marks (appno + cert) → join domestic_records.
        for i, appno in enumerate(_APPNOS):
            s.add(
                Trademark(
                    id=_TM_IDS[i],
                    gazette_id=_GZ,
                    record_type=RecordType.B_domestic,
                    application_number=appno,
                    certificate_number=f"BFCERT{i}",
                )
            )
        # 1 madrid_registration (cert only → lineage_key = cert = IRN_A), enriched.
        s.add(
            Trademark(
                id=_TM_IDS[4],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                certificate_number=_IRN_A,
            )
        )
        # 1 madrid_renewal (madrid_number only → lineage_key = IRN_B), UN-enriched;
        # falls back to its gazette (740) value.
        s.add(
            Trademark(
                id=_TM_IDS[5],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                madrid_number=_IRN_B,
                ip_agency_raw_740="Gazette Fallback Agency",
                applicant_name="Gazette Fallback Holder",
            )
        )
        # NOIP records: 3 case/whitespace variants of one rep firm + 1 distinct.
        s.add(DomesticRecord(application_number="BFAPP0", applicant_name="Acme Co", representative="Công ty Luật TAGA"))
        s.add(DomesticRecord(application_number="BFAPP1", applicant_name="Acme Co", representative="CÔNG TY LUẬT TAGA"))
        s.add(DomesticRecord(application_number="BFAPP2", applicant_name="Acme Co", representative="Công  ty   Luật   TAGA"))
        s.add(DomesticRecord(application_number="BFAPP3", applicant_name="Beta Co", representative="Distinct Firm XYZ"))
        # WIPO record for the enriched madrid mark (rep carries a glued address).
        s.add(
            MadridRecord(
                irn=_IRN_A,
                holder_name="WIPO Holder One",
                representative="WIPO Rep Alpha 12 Bahnhofstrasse, Zürich",
            )
        )
        await s.commit()
    await engine.dispose()
    yield list(_TM_IDS)
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_resolves_precedence_and_collapses_variants(bf_seed) -> None:
    from api._entity_norm import norm
    from scripts.backfill_entity_clean import backfill

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill(s, ids=bf_seed)
        assert stats["scanned"] == 6
        assert stats["updated"] == 6

        rows = (
            await s.execute(
                select(
                    Trademark.id,
                    Trademark.application_number,
                    Trademark.applicant_clean,
                    Trademark.applicant_norm,
                    Trademark.representative_clean,
                    Trademark.representative_norm,
                ).where(Trademark.id.in_(bf_seed))
            )
        ).all()
    await engine.dispose()

    by_appno = {r.application_number: r for r in rows if r.application_number}
    # NOIP applicant + rep used for domestic marks.
    assert by_appno["BFAPP0"].applicant_clean == "Acme Co"
    # The 3 rep variants collapse to ONE norm key; the 4th stays distinct.
    rep_norms = {by_appno[a].representative_norm for a in ("BFAPP0", "BFAPP1", "BFAPP2")}
    assert rep_norms == {norm("Công ty Luật TAGA")}
    assert by_appno["BFAPP3"].representative_norm == norm("Distinct Firm XYZ")
    assert by_appno["BFAPP3"].representative_norm != norm("Công ty Luật TAGA")

    # Enriched madrid mark → WIPO holder + address-stripped WIPO rep.
    madrid_enriched = next(r for r in rows if r.id == _TM_IDS[4])
    assert madrid_enriched.applicant_clean == "WIPO Holder One"
    assert madrid_enriched.representative_clean == "WIPO Rep Alpha"

    # Un-enriched madrid mark → gazette fallback.
    madrid_fallback = next(r for r in rows if r.id == _TM_IDS[5])
    assert madrid_fallback.applicant_clean == "Gazette Fallback Holder"
    assert madrid_fallback.representative_clean == "Gazette Fallback Agency"


@pytest.mark.asyncio
async def test_backfill_is_idempotent(bf_seed) -> None:
    from scripts.backfill_entity_clean import backfill

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        first = await backfill(s, ids=bf_seed)
        assert first["updated"] == 6
        # Second run over the same rows changes nothing.
        second = await backfill(s, ids=bf_seed)
        assert second["scanned"] == 6
        assert second["updated"] == 0
        assert second["unchanged"] == 6
    await engine.dispose()
```

- [ ] **Step 3: Run the backfill tests to verify they pass**

Run: `cd app/backend && python -m pytest tests/test_entity_clean_backfill.py -v`
Expected: PASS for all three tests (migration-presence + the two backfill tests).

- [ ] **Step 4: Run the real backfill against the dev DB; report rows updated**

Run:
```bash
cd app/backend && \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m scripts.backfill_entity_clean
```
Expected: a line like `DONE: {'scanned': <~50000>, 'updated': <N>, 'unchanged': <M>}`. **Record the `updated` count** to report to the user. Then run it a **second time** and confirm `updated` is ~0 (only rows the live sweep touched in between), proving idempotency on real data.

- [ ] **Step 5: Lint + type-check + commit**

Run: `cd app/backend && ruff check . && ruff format --check . && mypy api worker`
Expected: clean. (`scripts/` is not in the `mypy api worker` gate, matching the existing `rederive_madrid.py` precedent; still keep it ruff-clean.)

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/scripts/backfill_entity_clean.py app/backend/tests/test_entity_clean_backfill.py
git commit -m "feat(entity-canon): idempotent backfill for clean entity columns (phase 2)"
```

---

### Task 4: Switch `/overview` domestic panels to `GROUP BY *_norm`

**Files:**
- Modify: `app/backend/api/routes/gazettes.py` (add `_top_entities_column` helper ~after `_top_entities`; rewrite the domestic halves of the applicant + representative blocks ~lines 425-473)
- Test: `app/backend/tests/test_gazettes_overview.py`

- [ ] **Step 1: Add the SQL grouping helper**

In `app/backend/api/routes/gazettes.py`, after the `_top_entities` function (ends ~line 75), add:

```python
async def _top_entities_column(
    session: AsyncSession,
    norm_col,
    clean_col,
    *,
    categories: tuple[str, ...] | None = None,
    limit: int = 6,
) -> list[NamedCount]:
    """Top entities straight from the denormalized columns: GROUP BY the indexed
    `norm_col`, display the most-common `clean_col` spelling per key (Postgres
    `mode() WITHIN GROUP`), order by descending count then norm key. This is the
    Phase-2 fast path — same grouping as `_top_entities`, done in SQL over an
    indexed column instead of a per-request join.
    """
    stmt = (
        select(
            func.mode().within_group(clean_col).label("display"),
            func.count().label("n"),
        )
        .where(norm_col.is_not(None))
        .group_by(norm_col)
        .order_by(func.count().desc(), norm_col)
        .limit(limit)
    )
    if categories is not None:
        stmt = stmt.where(Trademark.mark_category.in_(categories))
    rows = (await session.execute(stmt)).all()
    return [NamedCount(name=row.display, n=row.n) for row in rows]
```

- [ ] **Step 2: Rewrite the domestic applicant + representative blocks**

In `gazette_overview`, replace the **Top applicants** and **Top representatives** blocks (currently ~lines 425-473) with:

```python
    # --- Top applicants -------------------------------------------------------
    # Domestic: GROUP BY the denormalized applicant_norm column (backfilled from
    # the trusted NOIP name → indexed, no per-request join). Same per-mark
    # counts as Phase 1's join path. Madrid stays per-IRN over madrid_records.
    mad_app_raws = (await session.execute(select(MadridRecord.holder_name))).scalars().all()
    top_applicants = TopApplicants(
        domestic=await _top_entities_column(
            session,
            Trademark.applicant_norm,
            Trademark.applicant_clean,
            categories=_DOMESTIC_CATEGORIES,
        ),
        madrid=_top_entities(mad_app_raws),
    )

    # --- Top representatives --------------------------------------------------
    # Domestic: GROUP BY representative_norm (backfilled trusted NOIP rep).
    # Madrid: trusted WIPO representative per-IRN (strip the glued address).
    mad_rep_raws = (await session.execute(select(MadridRecord.representative))).scalars().all()
    top_representatives = TopRepresentatives(
        domestic=await _top_entities_column(
            session,
            Trademark.representative_norm,
            Trademark.representative_clean,
            categories=_DOMESTIC_CATEGORIES,
        ),
        madrid=_top_entities(mad_rep_raws, pre=strip_madrid_rep_address),
    )
```

This removes the `dom_app_raws` / `dom_rep_raws` Phase-1 join queries entirely. After the edit, check whether `DomesticRecord` is still referenced in `routes/gazettes.py`; if ruff flags it as an unused import, remove `DomesticRecord` from the `from ..db.models import ...` line.

- [ ] **Step 3: Update the overview test seed to populate the clean columns**

In `app/backend/tests/test_gazettes_overview.py`, the synthetic domestic marks must carry `*_clean`/`*_norm` for the new column path to surface them. Replace the `_tm` helper (line ~60) with one that resolves the columns when a domestic rep/applicant is supplied:

```python
def _tm(gazette_id: uuid.UUID, *, rep: str | None = None, app: str | None = None, **ids: str) -> Trademark:
    from api._entity_norm import resolve_applicant, resolve_representative

    app_clean, app_norm = resolve_applicant(app, None, None)
    rep_clean, rep_norm = resolve_representative(rep, None, None)
    return Trademark(
        id=uuid.uuid4(),
        gazette_id=gazette_id,
        record_type=RecordType.A,
        applicant_clean=app_clean,
        applicant_norm=app_norm,
        representative_clean=rep_clean,
        representative_norm=rep_norm,
        **ids,
    )
```

Then in the seed body, attach the rep/applicant variants onto the domestic marks (the `DomesticRecord` rows stay for the legacy join tests). Change the 2098 application loop:

```python
        # 2098 A-file: 3 domestic_application carrying the 3 rep variants of one
        # firm (norm → 1 key) + applicant "TAGA Co".
        _rep_variants = ["Công ty Luật TAGA", "CÔNG TY LUẬT TAGA", "Công  ty   Luật   TAGA"]
        for i in range(_N_APP_2098):
            s.add(_tm(_GZ_A_2098, application_number=f"OVWAPP{i}", rep=_rep_variants[i], app="TAGA Co"))
```

and the 2099 domestic_registration loop:

```python
        # 2099 B-file: 2 domestic_registration carrying the distinct firm.
        for i in range(_N_DOMREG_2099):
            s.add(
                _tm(
                    _GZ_B_2099,
                    application_number=f"OVWREG{i}",
                    certificate_number=f"OVWREGC{i}",
                    rep="Distinct Firm XYZ",
                    app="XYZ Ltd",
                )
            )
```

(The three madrid `_tm(...)` calls keep their existing form — no rep/app kwargs.) Leave the existing `DomesticRecord(...)` seed rows as-is.

- [ ] **Step 4: Add the deterministic "same results, faster path" test**

Append to `app/backend/tests/test_gazettes_overview.py`:

```python
@pytest.mark.asyncio
async def test_domestic_panels_column_groupby_equals_phase1_join_over_seed() -> None:
    """Phase-2 column GROUP BY equals the Phase-1 join grouping over the SAME
    seeded subset — proving 'same results, faster path'. Scoped to the synthetic
    OVW* marks so it is immune to the live sweep (no cross-read race)."""
    from collections import Counter

    from sqlalchemy import func, select

    from api._entity_norm import norm

    appnos = ["OVWAPP0", "OVWAPP1", "OVWAPP2", "OVWREG0", "OVWREG1"]
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        # Phase-1 path: coalesce(domestic_records.representative, 740) + Python norm.
        phase1_raws = (
            (
                await s.execute(
                    select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                    .select_from(Trademark)
                    .outerjoin(
                        DomesticRecord,
                        DomesticRecord.application_number == Trademark.application_number,
                    )
                    .where(Trademark.application_number.in_(appnos))
                )
            )
            .scalars()
            .all()
        )
        # Phase-2 path: GROUP BY the denormalized representative_norm column.
        phase2 = (
            await s.execute(
                select(Trademark.representative_norm, func.count())
                .where(Trademark.application_number.in_(appnos))
                .where(Trademark.representative_norm.is_not(None))
                .group_by(Trademark.representative_norm)
            )
        ).all()
    await engine.dispose()

    phase1_counts = Counter(norm(r) for r in phase1_raws if r and r.strip())
    phase2_counts = {k: n for k, n in phase2}
    assert phase2_counts == dict(phase1_counts)
    # The 3 variants collapsed to one key (3 marks); the distinct firm kept (2).
    assert phase2_counts[norm("Công ty Luật TAGA")] == 3
    assert phase2_counts[norm("Distinct Firm XYZ")] == 2
```

- [ ] **Step 5: Run the overview tests**

Run: `cd app/backend && python -m pytest tests/test_gazettes_overview.py -v`
Expected: PASS. (The live-invariant tests `test_overview_domestic_reps_are_a_valid_norm_grouping` etc. still pass — the endpoint now reads `representative_norm`, so distinct-norm-keys is guaranteed by the GROUP BY; capped-6/sorted hold.)

- [ ] **Step 6: Confirm live dashboard numbers unchanged (manual snapshot check)**

Run (single-statement snapshot — both paths in one transaction, sweep-safe):
```bash
docker compose -f app/docker-compose.yml exec -T postgres psql -U tm -d tm -c "
WITH phase2 AS (
  SELECT representative_norm AS k, count(*) n FROM trademarks
  WHERE mark_category IN ('domestic_application','domestic_registration')
    AND representative_norm IS NOT NULL
  GROUP BY representative_norm ORDER BY n DESC, k LIMIT 6)
SELECT * FROM phase2;"
```
Compare the top-6 firm counts against the pre-change `/overview` domestic representatives (from a saved Phase-1 response or git history). Expected: identical top-6 firms + counts (the backfill must be current; re-run Task 3 Step 4 if the sweep has advanced materially).

- [ ] **Step 7: Lint + type-check + commit**

Run: `cd app/backend && ruff check . && ruff format --check . && mypy api worker`
Expected: clean. If mypy flags `func.mode().within_group(...)`, keep the helper params untyped at the SQLAlchemy boundary (the codebase does not annotate query expressions); add a narrow `# type: ignore[...]` only if mypy actually errors.

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/api/routes/gazettes.py app/backend/tests/test_gazettes_overview.py
git commit -m "feat(entity-canon): /overview domestic panels read indexed *_norm columns (phase 2)"
```

---

### Task 5: Docs sync + full verification

**Files:**
- Modify: `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Mark Phase 2 implemented in the spec**

In `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`, under `### Phase 2 — Denormalized clean columns (optional, for scale + reuse)`, add a status blockquote mirroring Phase 1's, right under the heading:

```markdown
> **Status: implemented** (2026-06-22). Migration `20260622_0023` adds the 4 columns + 2 btree indexes; `scripts/backfill_entity_clean.py` is the idempotent backfill (recompute-and-compare; `ENTITY_CLEAN_VERSION` in `api/_entity_norm.py`). `/overview` domestic applicant + representative panels now `GROUP BY *_norm` over the indexed columns (`mode() WITHIN GROUP` for display); Madrid panels stay per-IRN over `madrid_records` to keep their counts unchanged. Plan: [`docs/superpowers/plans/2026-06-22-entity-canonicalization-phase2.md`](../plans/2026-06-22-entity-canonicalization-phase2.md).
```

- [ ] **Step 2: Document the columns + script in CLAUDE.md**

In `CLAUDE.md`, add a concise note (e.g. at the end of the Architecture section, before "## Data files"):

```markdown
### Entity canonicalization (Phase 2)

`trademarks` carries denormalized `applicant_clean`/`applicant_norm` +
`representative_clean`/`representative_norm` (migration `20260622_0023`;
`*_norm` btree-indexed). Resolved per mark by deterministic identifier —
NOIP (`domestic_records`) → WIPO (`madrid_records`) → gazette fallback — by
`scripts/backfill_entity_clean.py` (re-runnable, idempotent via
recompute-and-compare; `ENTITY_CLEAN_VERSION` in `api/_entity_norm.py`).
`/overview` domestic applicant/representative panels `GROUP BY *_norm`;
Madrid panels stay per-IRN over `madrid_records` (counts unchanged from
Phase 1). See `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`.
```

- [ ] **Step 3: Full backend CI gate**

Run:
```bash
cd app/backend && \
ruff check . && \
ruff format --check . && \
mypy api worker && \
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm alembic check && \
python -m pytest tests/test_entity_norm.py tests/test_entity_clean_backfill.py tests/test_gazettes_overview.py -v
```
Expected: all clean / PASS. `alembic check` MUST say `No new upgrade operations detected.`

- [ ] **Step 4: Commit docs**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md CLAUDE.md
git commit -m "docs(entity-canon): mark phase 2 implemented; document clean columns + backfill"
```

- [ ] **Step 5: Push branch + open PR**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git push -u origin feat/entity-canon-phase2
gh pr create --base main --title "feat(entity-canon): Phase 2 — denormalized clean entity columns" \
  --body "$(cat <<'EOF'
Phase 2 of entity canonicalization. Denormalizes resolved clean applicant/representative names onto `trademarks` (`applicant_clean`/`_norm` + `representative_clean`/`_norm`; `*_norm` indexed), via an idempotent backfill (`scripts/backfill_entity_clean.py`). `/overview` domestic panels switch to `GROUP BY *_norm` over the indexed columns (same counts as Phase 1); Madrid panels stay per-IRN.

See `docs/superpowers/plans/2026-06-22-entity-canonicalization-phase2.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Verify the PR diff does NOT contain `README.md`, `app/.env.example`, or `app/backend/api/settings.py`:** run `git diff --name-only origin/main...HEAD` — the rename trio must be absent.

---

## Verification Summary (maps to task acceptance criteria)

| Requirement | Covered by |
|---|---|
| Migration adds 4 columns + 2 btree indexes | Task 2 Steps 1-2; test `test_clean_columns_and_norm_indexes_exist` |
| Migration applies + downgrades | Task 2 Step 3 (apply), Step 4 (downgrade round-trip), Step 5 (`alembic check`) |
| Re-runnable idempotent backfill + `entity_clean_version` | Task 1 (constant), Task 3 (script); test `test_backfill_is_idempotent` |
| Precedence NOIP > WIPO > gazette | Task 1 resolver; tests `test_resolve_*`, `test_backfill_resolves_precedence_and_collapses_variants` |
| Variant set collapses to one `*_norm` | Tests `test_resolve_applicant_variants_collapse_to_one_norm`, backfill + overview collapse asserts |
| `*_norm` indexed | Task 2 (migration + model `index=True`); test `test_clean_columns_and_norm_indexes_exist` |
| `/overview` domestic via `GROUP BY *_norm` | Task 4 Steps 1-2 |
| Dashboard numbers unchanged vs Phase 1 | Task 4 Step 4 (deterministic seed test) + Step 6 (live snapshot check); Madrid kept per-IRN by design |
| Run backfill against dev DB; report rows updated | Task 3 Step 4 |
| Frontend unaffected | No frontend changes — payload shape (`top_applicants`/`top_representatives`) unchanged |
| Never commit rename trio | Explicit `git add` paths throughout; Task 5 Step 5 verify |
