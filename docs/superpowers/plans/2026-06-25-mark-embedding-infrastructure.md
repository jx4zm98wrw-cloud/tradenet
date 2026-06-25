# Mark Embedding Infrastructure (Track 3b-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the feature store for a future semantic axis — compute a multilingual LaBSE embedding of each mark's resolved wordmark and store it per mark via an idempotent backfill — with zero scoring change.

**Architecture:** `api/_embed.py` is the only module importing the model; it exposes `compute_mark_embedding(text, *, encoder=None) -> bytes | None` (L2-normalised 768 float32) with a dependency-injected encoder seam so tests never load the 470 MB model. A nullable `bytea` `trademarks.mark_embedding` column stores the vector. `scripts/backfill_mark_embedding.py` (idempotent, `EMBED_VERSION`) populates it from `mark_name`. **Backfill-only** — no `worker/ingest.py` change (its source `mark_name` is itself backfill-derived). The engine, composite, routes, and frontend are untouched.

**Tech Stack:** Python 3, SQLAlchemy/Alembic, `numpy` (already a dep), `sentence-transformers`/LaBSE (new, backfill-only), pytest.

**Spec:** [`docs/superpowers/specs/2026-06-25-mark-embedding-infrastructure-design.md`](../specs/2026-06-25-mark-embedding-infrastructure-design.md)

**Branch:** `track3b1-mark-embedding` (already checked out; spec already committed here).

---

## Pre-flight (read once, do not skip)

- **Working directory for all commands:** `app/backend`. Activate the venv in the SAME bash call: `cd app/backend && source /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet/app/.venv/bin/activate && <cmd>`.
- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` **explicit paths only** — never `git add -A`/`.`/`-u`.
- **Targeted pytest only** — never the full suite (it resets the live `domestic_sweep_control` singleton). Name the specific test file/node.
- **The 470 MB LaBSE model must NOT run in normal CI.** Every unit test injects a fake encoder; only the ONE marked integration test (Task 1, Step 5) loads real LaBSE and is skipped unless `TM_RUN_MODEL_TESTS=1`.
- The DB-backed tests use a live Postgres (`get_settings().database_url`) and follow the existing `tests/test_backfill_logo_phash.py` seed/teardown pattern exactly.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tm_similarity/...` | **untouched** | engine does not change in 3b-1 |
| `api/_embed.py` | **Create** | `compute_mark_embedding(text, *, encoder=None) -> bytes \| None`; DI encoder seam; lazy cached LaBSE. The only model importer. |
| `api/db/models.py` | Modify | add `mark_embedding: Mapped[bytes \| None]` (`LargeBinary`, nullable) to `Trademark` |
| `alembic/versions/<new>.py` | **Create** | add/drop the nullable `bytea` column, chained off head `20260625_0030` |
| `scripts/backfill_mark_embedding.py` | **Create** | idempotent corpus backfill from `mark_name`; `EMBED_VERSION` |
| `tests/test_embed.py` | **Create** | `compute_mark_embedding` units (fake encoder) + marked real-model test + column assertion |
| `tests/test_backfill_mark_embedding.py` | **Create** | backfill units (fake encoder): counts, idempotency, scoping, NULL-`mark_name` skip |
| `requirements.txt` | Modify | add `sentence-transformers` (backfill-only use) |
| `CLAUDE.md` | Modify | new `mark_embedding` feature-store entry + backfill caveat + 3b-1/3b-2 split note |

---

## Task 1: `api/_embed.py` — the embedding module (DI encoder seam)

**Files:**
- Create: `api/_embed.py`
- Test: `tests/test_embed.py`

`compute_mark_embedding` embeds the resolved wordmark and returns L2-normalised 768 float32 as bytes. The `encoder` parameter is the testability seam: default `None` lazy-loads the cached real LaBSE; tests pass a deterministic fake so no model loads.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_embed.py`:

```python
"""compute_mark_embedding: shape, normalisation, None-handling (fake encoder)."""

from __future__ import annotations

import numpy as np

from api._embed import compute_mark_embedding

_DIM = 768


def _fake_encoder(texts: list[str]) -> np.ndarray:
    # Deterministic, NOT unit-norm (so the function's own L2-normalise is exercised).
    base = np.zeros((len(texts), _DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        base[i, 0] = float(len(t))
        base[i, 1] = 3.0
    return base


def test_returns_768_float32_bytes():
    b = compute_mark_embedding("APPLE", encoder=_fake_encoder)
    assert isinstance(b, bytes)
    assert len(b) == _DIM * 4  # 768 float32


def test_round_trips_and_is_l2_normalised():
    b = compute_mark_embedding("APPLE", encoder=_fake_encoder)
    v = np.frombuffer(b, dtype=np.float32)
    assert v.shape == (_DIM,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5


def test_none_and_blank_return_none():
    assert compute_mark_embedding(None, encoder=_fake_encoder) is None
    assert compute_mark_embedding("", encoder=_fake_encoder) is None
    assert compute_mark_embedding("   ", encoder=_fake_encoder) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_embed.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'api._embed'`.

- [ ] **Step 3: Implement `api/_embed.py`**

```python
"""Mark embedding for the semantic feature store (Track 3b-1).

The ONLY module importing the embedding model. Mirrors api/_phash.py (the only
Pillow importer): the heavy dependency is lazy-loaded and cached here, off the
import path of the API routes and the pure tm_similarity engine — which read the
stored bytes, never the model. Produces an L2-normalised 768-dim LaBSE vector as
float32 bytes so a future cosine is a plain dot product.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

Encoder = Callable[[list[str]], "NDArray[np.float32]"]

_DIM = 768
_MODEL_NAME = "sentence-transformers/LaBSE"
_model = None  # cached SentenceTransformer singleton (lazy)


def _default_encoder(texts: list[str]) -> "NDArray[np.float32]":
    """Lazy-load + cache LaBSE; encode to unit-norm float32 vectors."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # heavy; imported on first real use only

        _model = SentenceTransformer(_MODEL_NAME)
    return _model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)


def compute_mark_embedding(text: str | None, *, encoder: Encoder | None = None) -> bytes | None:
    """Return the mark's L2-normalised 768-float32 embedding as bytes, or None.

    `text` is the resolved wordmark (`trademarks.mark_name`). None/blank → None
    (figurative marks with no transcribed name carry no embedding, like a no-logo
    mark carries no logo_phash). `encoder` is the DI seam: default loads the cached
    real LaBSE; tests pass a fake so no model is loaded. The output round-trips via
    `numpy.frombuffer(buf, dtype=numpy.float32)`.
    """
    if not text or not text.strip():
        return None
    enc = encoder or _default_encoder
    vec = np.asarray(enc([text])[0], dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec = (vec / norm).astype(np.float32)
    return vec.tobytes()
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_embed.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Add the marked real-model integration test (skipped in CI)**

Append to `tests/test_embed.py`:

```python
import os

import pytest


@pytest.mark.skipif(
    os.environ.get("TM_RUN_MODEL_TESTS") != "1",
    reason="loads the 470MB LaBSE model; opt-in via TM_RUN_MODEL_TESTS=1",
)
def test_real_labse_cross_lingual_ordering():
    # Translation equivalents must be closer than unrelated concepts.
    def cos(a: str, b: str) -> float:
        va = np.frombuffer(compute_mark_embedding(a), dtype=np.float32)
        vb = np.frombuffer(compute_mark_embedding(b), dtype=np.float32)
        return float(va @ vb)  # both unit-norm -> dot == cosine

    assert cos("APPLE", "TÁO") > cos("APPLE", "CHAIR")
    assert cos("RED BULL", "BÒ ĐỎ") > cos("RED BULL", "TABLE")
```

- [ ] **Step 6: Run the marked test once locally to confirm the model + signal (optional, slow)**

Run: `TM_RUN_MODEL_TESTS=1 pytest tests/test_embed.py::test_real_labse_cross_lingual_ordering -q`
Expected: PASS (downloads LaBSE on first run, ~470 MB; asserts translation pairs out-rank unrelated). If the model is unavailable in the worktree, skip this step — normal CI does not run it.

- [ ] **Step 7: Commit**

```bash
git add app/backend/api/_embed.py app/backend/tests/test_embed.py
git commit -m "feat(embed): compute_mark_embedding — LaBSE feature store with DI encoder seam"
```

---

## Task 2: `trademarks.mark_embedding` column + migration

**Files:**
- Modify: `api/db/models.py` (add the column near `logo_phash`)
- Create: `alembic/versions/<auto>_trademarks_mark_embedding.py`
- Test: `tests/test_embed.py` (append a column-presence assertion)

- [ ] **Step 1: Write the failing column assertion**

Append to `tests/test_embed.py`:

```python
from api.db import Trademark


def test_trademark_has_mark_embedding_column():
    col = Trademark.__table__.c.mark_embedding
    assert col.nullable is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_embed.py::test_trademark_has_mark_embedding_column -q`
Expected: FAIL with `KeyError: 'mark_embedding'`.

- [ ] **Step 3: Add the column to `api/db/models.py`**

Ensure `LargeBinary` is imported from `sqlalchemy` (add it to the existing `from sqlalchemy import (...)` block at the top of the file). Then, immediately after the `logo_phash` column on `Trademark`, add:

```python
    mark_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    """L2-normalised 768-float32 LaBSE embedding of mark_name, as bytea. Populated
    by scripts/backfill_mark_embedding.py (backfill-only; see Track 3b-1)."""
```

- [ ] **Step 4: Create the Alembic migration**

Scaffold a migration chained off the current head (`20260625_0030_trademarks_logo_kind`) — `alembic revision` auto-sets `down_revision` to head and names the file per the repo template:

```bash
alembic revision -m "trademarks_mark_embedding"
```

Edit the generated file's `upgrade`/`downgrade` to:

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("mark_embedding", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "mark_embedding")
```

Do NOT touch any other table. Confirm `down_revision` points to the prior head (the `revision` value inside `20260625_0030_trademarks_logo_kind.py`).

- [ ] **Step 5: Apply the migration and verify the column test passes**

Run:
```bash
alembic upgrade head
pytest tests/test_embed.py::test_trademark_has_mark_embedding_column -q
alembic check
```
Expected: upgrade succeeds; column test PASSES; `alembic check` reports no pending changes (model and migrations agree).

- [ ] **Step 6: Verify the migration round-trips**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: both succeed cleanly (the column drops then re-adds).

- [ ] **Step 7: Commit**

```bash
git add app/backend/api/db/models.py app/backend/alembic/versions/*trademarks_mark_embedding*.py app/backend/tests/test_embed.py
git commit -m "feat(db): add nullable bytea trademarks.mark_embedding + migration"
```

---

## Task 3: `scripts/backfill_mark_embedding.py` — idempotent corpus backfill

**Files:**
- Create: `scripts/backfill_mark_embedding.py`
- Test: `tests/test_backfill_mark_embedding.py`

Mirrors `scripts/backfill_logo_phash.py` exactly, but sources `mark_name` (not `logo_path`), writes `mark_embedding` (not `logo_phash`), and threads the DI `encoder` through to `compute_mark_embedding` so tests run without the model.

- [ ] **Step 1: Write the failing backfill test**

Create `tests/test_backfill_mark_embedding.py`:

```python
"""backfill_mark_embedding sets bytea for marks with a mark_name; idempotent."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from scripts.backfill_mark_embedding import backfill_mark_embedding

_GZ = uuid.UUID("e3000000-0000-4000-8000-0000000000e1")
_WITH = uuid.UUID("e3000000-0000-4000-8000-0000000000e2")
_WITHOUT = uuid.UUID("e3000000-0000-4000-8000-0000000000e3")
_DIM = 768


def _fake_encoder(texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), _DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        out[i, 0] = float(abs(hash(t)) % 97 + 1)  # deterministic, non-zero
    return out


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
                filename="A_TEST_embed.pdf",
                sha256="embed_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        s.add(
            Trademark(
                id=_WITH,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="EM-1",
                mark_name="APPLE",
                publication_date_441=date(2099, 1, 1),
            )
        )
        s.add(
            Trademark(
                id=_WITHOUT,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="EM-2",
                mark_name=None,  # not yet name-backfilled -> no embedding
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
async def test_backfill_sets_idempotent_and_skips_null_name():
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill_mark_embedding(s, ids=[_WITH, _WITHOUT], encoder=_fake_encoder)
        assert stats["updated"] == 1  # only the mark_name row
        with_row = (await s.execute(select(Trademark).where(Trademark.id == _WITH))).scalar_one()
        without_row = (await s.execute(select(Trademark).where(Trademark.id == _WITHOUT))).scalar_one()
        assert with_row.mark_embedding is not None and len(with_row.mark_embedding) == _DIM * 4
        assert without_row.mark_embedding is None  # NULL mark_name -> not scanned
    async with Session() as s:
        stats2 = await backfill_mark_embedding(s, ids=[_WITH, _WITHOUT], encoder=_fake_encoder)
        assert stats2["updated"] == 0  # idempotent
        assert stats2["unchanged"] == 1
    await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_backfill_mark_embedding.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.backfill_mark_embedding'`.

- [ ] **Step 3: Implement `scripts/backfill_mark_embedding.py`**

```python
"""Backfill trademarks.mark_embedding from mark_name. Idempotent.

Mirrors backfill_logo_phash.py. For each trademark with a non-NULL mark_name,
compute the LaBSE embedding and store the bytea. Marks with no mark_name stay
NULL (the future semantic axis falls back to no-signal). BACKFILL-ONLY: the
ingest worker does NOT set mark_embedding (its source mark_name is itself
backfill-derived) — run this AFTER backfill_mark_name, and re-run after a fresh
ingest. Bump EMBED_VERSION if the model or normalisation changes.

No network beyond the one-time model download. Run against the dev DB or any
worker container:

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.backfill_mark_embedding
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._embed import Encoder, compute_mark_embedding
from api.db.models import Trademark

log = logging.getLogger("mark_embedding.backfill")

EMBED_VERSION = 1
_CHUNK = 1000


async def backfill_mark_embedding(
    session: AsyncSession, *, ids: Sequence[object] | None = None, encoder: Encoder | None = None
) -> dict[str, int]:
    """Resolve + write mark_embedding for every trademark with a mark_name (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}. `encoder` is passed
    through to compute_mark_embedding (tests inject a fake; production uses LaBSE).
    """
    stmt = select(
        Trademark.id,
        Trademark.mark_name,
        Trademark.mark_embedding,
    ).where(Trademark.mark_name.is_not(None))
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        want = compute_mark_embedding(row.mark_name, encoder=encoder)
        if want == row.mark_embedding:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "mark_embedding": want})
        if len(pending) >= _CHUNK:
            await _flush(session, pending)
            stats["updated"] += len(pending)
            pending.clear()

    if pending:
        await _flush(session, pending)
        stats["updated"] += len(pending)
    return stats


async def _flush(session: AsyncSession, rows: list[dict[str, object]]) -> None:
    tbl = Trademark.__table__
    stmt = (
        update(tbl).where(tbl.c.id == bindparam("b_id")).values(mark_embedding=bindparam("mark_embedding"))
    )
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.mark_embedding (EMBED_VERSION=%d)", EMBED_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_mark_embedding(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_backfill_mark_embedding.py -q`
Expected: PASS (sets bytea for the `mark_name` row, skips the NULL-name row, idempotent on rerun).

- [ ] **Step 5: Commit**

```bash
git add app/backend/scripts/backfill_mark_embedding.py app/backend/tests/test_backfill_mark_embedding.py
git commit -m "feat(embed): idempotent backfill_mark_embedding from mark_name (EMBED_VERSION=1)"
```

---

## Task 4: Dependency + CI gates + docs sync

**Files:**
- Modify: `requirements.txt`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add a pinned `sentence-transformers` entry with a comment noting backfill-only use. Find the latest stable version and pin it (e.g. `sentence-transformers==<latest>`), placed near the other ML/data deps (after `numpy`). Add a one-line comment above it:

```
# Multilingual mark embeddings (LaBSE) — used ONLY by api/_embed.py on the
# backfill path (scripts/backfill_mark_embedding.py). Not imported by the API
# routes or tm_similarity. Pulls in torch; grows the worker image (accepted).
sentence-transformers==<latest-stable>
```

Then install into the venv: `pip install -r requirements.txt` (downloads torch — large; one-time).

- [ ] **Step 2: Run the CI gates over the changed surface**

Run (from `app/backend`, venv active):
```bash
ruff check api/_embed.py scripts/backfill_mark_embedding.py tests/test_embed.py tests/test_backfill_mark_embedding.py
ruff format --check api/_embed.py scripts/backfill_mark_embedding.py tests/test_embed.py tests/test_backfill_mark_embedding.py
mypy api worker
alembic check
```
Expected: all clean. Run BOTH `ruff check` AND `ruff format --check` (separate gates — a Track 2 failure came from skipping format). If mypy flags the lazy `sentence_transformers` import (no stubs), a scoped `# type: ignore[import-untyped]` on that import line is acceptable.

- [ ] **Step 3: Run the full 3b-1 test surface (targeted, model-free)**

Run: `pytest tests/test_embed.py tests/test_backfill_mark_embedding.py -q`
Expected: PASS (the marked real-model test is auto-skipped without `TM_RUN_MODEL_TESTS=1`).

- [ ] **Step 4: Docs sync — add the feature-store entry to `CLAUDE.md`**

In `CLAUDE.md`, after the "### Resolved mark name" subsection (the `mark_name` feature-store description), add a new subsection:

```markdown
### Mark embedding feature store (Track 3b-1)

`trademarks.mark_embedding` (nullable `bytea`, no index; migration
`20260625_00NN`) stores an **L2-normalised 768-float32 LaBSE embedding** of the
resolved `mark_name`, computed by `api/_embed.py:compute_mark_embedding` (the
ONLY module importing `sentence-transformers`/LaBSE — lazy-loaded + cached, off
the API-route and `tm_similarity` import paths, mirroring `_phash.py`). Written
by `scripts/backfill_mark_embedding.py` (re-runnable, idempotent
recompute-and-compare, `EMBED_VERSION`; `ids=`-scoped, same shape as
`backfill_logo_phash`). **Backfill-only** — the ingest worker does NOT populate
it (its source `mark_name` is itself backfill-derived): **run it after
`backfill_mark_name`, and re-run after a fresh ingest** (same caveat as
`mark_name`/`vn_grant_date`/entity-clean). The feature store has **no scoring
effect yet** — it is consumed by Track 3b-2 (the semantic axis + 5-axis weight
reallocation), which reads the stored vector into `MarkFeatures` and does pure
cosine. `sentence-transformers` is a backfill-only dependency (pulls in torch;
grows the worker image — accepted). See
`docs/superpowers/specs/2026-06-25-mark-embedding-infrastructure-design.md`.
```

Replace `00NN` with the actual migration number generated in Task 2.

- [ ] **Step 5: Commit**

```bash
git add app/backend/requirements.txt CLAUDE.md
git commit -m "deps+docs: sentence-transformers (backfill-only) + mark_embedding feature-store note"
```

---

## Self-Review (completed at plan-authoring time)

**Spec coverage** — every spec section maps to a task:
- §1 `api/_embed.py` (DI seam, lazy cached LaBSE, normalised bytes, None-handling) → Task 1.
- §2 `bytea` column + migration (nullable, no index) → Task 2.
- §3 `backfill_mark_embedding.py` (`EMBED_VERSION`, idempotent, non-NULL-`mark_name` scope, `ids=`, stats) → Task 3.
- §Lifecycle (backfill-only, no ingest change, chains after `backfill_mark_name`) → respected: no `worker/ingest.py` task; backfill scopes `mark_name IS NOT NULL`; NULL-name skip tested (Task 3).
- §Testing 1–5 (compute units, backfill units, NULL-name skip, marked real-model ordering, migration round-trip) → Tasks 1/2/3.
- §Out-of-scope (no scoring change, no pgvector, no model in API/engine, no goods embedding, no ingest change) → respected: no `tm_similarity`/`composite.py`/`MarkFeatures`/route/frontend/ingest files touched.
- §Deps + docs → Task 4.

**Placeholder scan** — only intentional fill-ins the implementer resolves from the environment: the pinned `sentence-transformers` version (latest stable) and the generated migration number (`00NN`/`<auto>`). All code, signatures, and test values are concrete.

**Type/name consistency** — `compute_mark_embedding(text, *, encoder=None) -> bytes | None`, `Encoder` type alias, and `backfill_mark_embedding(session, *, ids=None, encoder=None) -> dict[str,int]` are consistent across Tasks 1/3. `_DIM=768`, `_CHUNK=1000`, `EMBED_VERSION=1`, `LargeBinary`/`bytea`, and the `mark_embedding` column name match across model/migration/backfill/tests. Backfill test mirrors `test_backfill_logo_phash.py` (verified seed/teardown shape). No real LaBSE values are asserted anywhere except the opt-in marked test (the design's intent — the model is not run in CI).
