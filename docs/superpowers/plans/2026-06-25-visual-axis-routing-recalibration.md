# Visual Axis: specimen-routing + pHash floor recalibration (Track 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the conflict scorecard's Visual axis from inflating unrelated marks (the reported `/compare` 63%/59%) by (a) recalibrating the pHash→score curve so unrelated images score ~0, and (b) routing the visual axis by specimen type so rendered wordmark-strips don't contaminate it.

**Architecture:** Inside the extracted `tm_similarity/` package (Track 0). The curve change is a pure-math swap (`1 - hd/64` → `1 - hd/T`) extracted into a testable `_phash_score(hd)`. Routing is driven by a persisted `trademarks.logo_kind` column computed on the **indexer** side (`api/_phash.py`, Vienna-primary + cheap pixel backstop) and read by `visual_similarity` at score-time — keeping the engine filesystem-free. Behaviour intentionally changes; the Track 0 golden fixture is provably undisturbed (it never exercises the curve), and routing is permissive on unclassified (`NULL`) marks so there is no pre-backfill regression window.

**Tech Stack:** Python 3.11, SQLAlchemy 2 + Alembic, asyncpg/psycopg2, Pillow + imagehash (indexer only), pytest (httpx ASGI), jellyfish.

**Spec:** [`docs/superpowers/specs/2026-06-25-visual-axis-routing-recalibration-design.md`](../specs/2026-06-25-visual-axis-routing-recalibration-design.md)

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `app/backend/tm_similarity/visual.py` | Modify | `_phash_score(hd)` curve + `VISUAL_PHASH_THRESHOLD`; routing in `visual_similarity` (gains `a_kind`/`b_kind`) |
| `app/backend/tm_similarity/features.py` | Modify | `MarkFeatures` gains `logo_kind: str \| None = None` |
| `app/backend/tm_similarity/__init__.py` | Modify | bump `SIMILARITY_VERSION` `"1.0"→"1.1"`; pass `logo_kind` in `score()` |
| `app/backend/api/_phash.py` | Modify | `classify_logo_kind()` + `_pixel_backstop()` (Pillow; indexer side) |
| `app/backend/api/db/models.py` | Modify | `Trademark.logo_kind` column |
| `app/backend/alembic/versions/20260625_0030_trademarks_logo_kind.py` | Create | migration adding the column |
| `app/backend/scripts/backfill_logo_kind.py` | Create | idempotent backfill (mirrors `backfill_logo_phash.py`) |
| `app/backend/scripts/calibrate_phash_threshold.py` | Create | one-off Hamming-distribution measurement (calibration artifact) |
| `app/backend/worker/ingest.py` | Modify | `_logo_kind_for()` helper; set `trademark.logo_kind` on ingest |
| `app/backend/api/routes/marks.py` | Modify | build `MarkFeatures(logo_kind=...)` (2 sites) |
| `app/backend/api/routes/compare.py` | Modify | build `MarkFeatures(logo_kind=...)` (2 sites) |
| `app/backend/tests/test_tm_similarity_visual.py` | Create | curve + routing unit tests |
| `app/backend/tests/test_logo_kind_classifier.py` | Create | `classify_logo_kind` + `_pixel_backstop` unit tests |
| `app/backend/tests/test_backfill_logo_kind.py` | Create | backfill idempotency (DB) |
| `docs/superpowers/notes/2026-06-25-phash-hamming-calibration.md` | Create | committed measurement output |
| `CLAUDE.md` | Modify | docs sync |

**Branch:** work continues on `track1-visual-routing` (already created; the spec is committed there). Do NOT branch off `main` again. NEVER `git add` the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`) — `git add` explicit paths only.

**All commands run from `app/backend/`** unless stated. The dev DB is `postgresql+asyncpg://tm:tm@localhost:5435/tm` (sync: `postgresql+psycopg2://...`).

---

### Task 1: Recalibrate the pHash curve (isolated, no routing yet)

**Files:**
- Create: `app/backend/scripts/calibrate_phash_threshold.py`
- Create: `docs/superpowers/notes/2026-06-25-phash-hamming-calibration.md`
- Create: `app/backend/tests/test_tm_similarity_visual.py`
- Modify: `app/backend/tm_similarity/visual.py`

- [ ] **Step 1: Write the calibration measurement script**

Create `app/backend/scripts/calibrate_phash_threshold.py`:

```python
"""One-off: measure the Hamming-distance distribution of real logo pHash pairs.

Confirms the unrelated baseline (~32 of 64 bits) that motivates the recalibrated
visual curve. Read-only. Run against the dev DB:

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.calibrate_phash_threshold
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db.models import Trademark
from tm_similarity.visual import _hamming_hex

_SAMPLE = 6000  # random pHash-bearing rows; consecutive pairs → ~3000 random pairs


async def _main() -> None:
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        stmt = (
            select(Trademark.logo_phash)
            .where(Trademark.logo_phash.is_not(None))
            .order_by(Trademark.id)  # deterministic; "random enough" across gazettes
            .limit(_SAMPLE)
        )
        hashes = [r[0] for r in (await s.execute(stmt)).all()]
    await engine.dispose()

    hist: Counter[int] = Counter()
    for a, b in zip(hashes[::2], hashes[1::2]):
        hist[_hamming_hex(a, b)] += 1
    total = sum(hist.values())
    print(f"pairs={total}")
    cum = 0
    for hd in range(0, 65):
        cum += hist.get(hd, 0)
        if hist.get(hd, 0) or hd in (5, 10, 16, 32):
            print(f"hd={hd:2d}  n={hist.get(hd,0):5d}  cum%={100*cum/total:5.1f}")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: Run the measurement and capture the artifact**

Run: `TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm python -m scripts.calibrate_phash_threshold | tee /tmp/phash_hist.txt`
Expected: a histogram peaking around `hd = 28–34` (the unrelated baseline), with only a small fraction of pairs at `hd ≤ 10`. Paste the output into `docs/superpowers/notes/2026-06-25-phash-hamming-calibration.md` with a one-paragraph reading:

```markdown
# pHash Hamming-distance calibration (Track 1)

Measured over real `trademarks.logo_phash` pairs to set `VISUAL_PHASH_THRESHOLD`.

<paste histogram here>

**Reading:** the distribution peaks at hd≈<mode> — confirming unrelated images
differ in ~half the 64 bits, which the old `1 - hd/64` curve mapped to ~0.50.
`hd ≤ 10` covers only ~<x>% of pairs (the genuine-similarity tail). We set
`VISUAL_PHASH_THRESHOLD = 10`: any pair past hd=10 scores 0. (Literature: hd≤5
near-duplicate, hd≤10 visually similar.)
```

If the mode comes out materially below ~24 (unexpected — would mean specimens are globally self-similar), keep `T = 10` but note it; the classifier (Task 2+) handles the wordmark-strip self-similarity that would cause that.

- [ ] **Step 3: Write the failing curve unit tests**

Create `app/backend/tests/test_tm_similarity_visual.py`:

```python
"""Track 1: recalibrated pHash curve + specimen-type routing."""

from __future__ import annotations

from tm_similarity.visual import VISUAL_PHASH_THRESHOLD, _phash_score


def test_phash_score_identical_is_one():
    assert _phash_score(0) == 1.0


def test_phash_score_at_threshold_is_zero():
    assert _phash_score(VISUAL_PHASH_THRESHOLD) == 0.0


def test_phash_score_unrelated_baseline_is_zero():
    # ~half the bits differ → unrelated → must floor at 0, not 0.50
    assert _phash_score(32) == 0.0


def test_phash_score_is_monotonic_non_increasing():
    vals = [_phash_score(hd) for hd in range(0, 65)]
    assert all(b <= a for a, b in zip(vals, vals[1:]))


def test_phash_score_threshold_is_ten():
    assert VISUAL_PHASH_THRESHOLD == 10
```

- [ ] **Step 4: Run the curve tests to verify they fail**

Run: `python -m pytest tests/test_tm_similarity_visual.py -q`
Expected: FAIL — `ImportError: cannot import name 'VISUAL_PHASH_THRESHOLD'` / `_phash_score`.

- [ ] **Step 5: Implement the curve in `visual.py`**

In `app/backend/tm_similarity/visual.py`, add the constant + pure curve and call it from the pHash branch. Update the module docstring (it currently says "Track 0 keeps the exact 1 - HD/64 formula; recalibration is Track 1.").

Add, near the top after imports:

```python
VISUAL_PHASH_THRESHOLD = 10
"""Hamming distance at/after which two 64-bit pHashes score 0 visual.

Two *random* pHashes differ in ~32 of 64 bits, so the old `1 - hd/64` floored
unrelated images at 0.50. Calibrated to 10 (see
docs/superpowers/notes/2026-06-25-phash-hamming-calibration.md): only genuinely
close hashes score; everything past the unrelated baseline maps to 0."""


def _phash_score(hd: int) -> float:
    """Recalibrated Hamming→similarity: linear to VISUAL_PHASH_THRESHOLD, then 0."""
    return round(max(0.0, 1.0 - hd / VISUAL_PHASH_THRESHOLD), 3)
```

Change the pHash branch in `visual_similarity` from:

```python
    if a_phash and b_phash:
        hd = _hamming_hex(a_phash, b_phash)
        return VisualScore(round(max(0.0, 1.0 - hd / 64.0), 3), "phash")
```

to:

```python
    if a_phash and b_phash:
        return VisualScore(_phash_score(_hamming_hex(a_phash, b_phash)), "phash")
```

(Signature stays 4-arg in this task; routing is Task 6.)

- [ ] **Step 6: Run curve tests + the full engine golden test**

Run: `python -m pytest tests/test_tm_similarity_visual.py tests/test_tm_similarity_engine.py -q`
Expected: PASS. The Track 0 golden test stays green — it feeds `composite_score` fixed visual inputs and never exercises the curve, proving the recalibration is isolated.

- [ ] **Step 7: Commit**

```bash
git add tm_similarity/visual.py tests/test_tm_similarity_visual.py scripts/calibrate_phash_threshold.py ../../docs/superpowers/notes/2026-06-25-phash-hamming-calibration.md
git commit -m "feat(similarity): recalibrate pHash curve (1-hd/T, T=10) + calibration artifact"
```

---

### Task 2: Specimen classifier (`classify_logo_kind` + pixel backstop)

**Files:**
- Modify: `app/backend/api/_phash.py`
- Create: `app/backend/tests/test_logo_kind_classifier.py`

- [ ] **Step 1: Write the failing classifier tests**

Create `app/backend/tests/test_logo_kind_classifier.py`:

```python
"""Track 1: specimen-type classifier (Vienna-primary, pixel backstop)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from api._phash import _pixel_backstop, classify_logo_kind


def test_vienna_present_is_figurative_without_touching_image():
    # No file at this path — Vienna branch must short-circuit before any open().
    assert classify_logo_kind(["26.4.18"], None) == "figurative"


def test_no_vienna_no_image_is_none():
    assert classify_logo_kind([], None) is None


def test_wide_sparse_strip_is_wordmark(tmp_path):
    p = tmp_path / "strip.png"
    img = Image.new("L", (600, 80), 255)  # wide, short, white
    d = ImageDraw.Draw(img)
    d.text((10, 30), "ACME BRAND", fill=0)  # thin dark text → sparse ink
    img.save(p)
    assert _pixel_backstop(p) == "wordmark"


def test_square_dense_device_is_figurative(tmp_path):
    p = tmp_path / "device.png"
    img = Image.new("L", (200, 200), 255)
    d = ImageDraw.Draw(img)
    d.ellipse((20, 20, 180, 180), fill=0)  # big solid blob → dense ink, square
    img.save(p)
    assert _pixel_backstop(p) == "figurative"


def test_unreadable_image_fails_to_figurative(tmp_path):
    p = tmp_path / "broken.png"
    p.write_bytes(b"not a png")
    assert _pixel_backstop(p) == "figurative"


def test_classify_no_vienna_routes_to_backstop(tmp_path):
    p = tmp_path / "strip.png"
    img = Image.new("L", (600, 80), 255)
    ImageDraw.Draw(img).text((10, 30), "ACME BRAND", fill=0)
    img.save(p)
    assert classify_logo_kind([], p) == "wordmark"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_logo_kind_classifier.py -q`
Expected: FAIL — `ImportError: cannot import name 'classify_logo_kind'`.

- [ ] **Step 3: Implement the classifier in `api/_phash.py`**

Append to `app/backend/api/_phash.py` (it already imports `Path`, `imagehash`, `from PIL import Image`):

```python
# Specimen-routing thresholds (provisional; see calibration note). A wordmark
# strip is wide, short, and sparse — mostly white with a thin band of text.
_AR_MIN = 3.0      # width / height
_INK_MAX = 0.20    # fraction of dark (text) pixels
_DARK_CUTOFF = 128  # luminance below this counts as "ink"


def classify_logo_kind(vienna_codes: list[str], image_path: Path | None) -> str | None:
    """Specimen kind for visual-axis routing: 'figurative' | 'wordmark' | None.

    Vienna (531) codes mean the mark HAS a figurative element → 'figurative'
    (the cheap, dominant signal; no pixel I/O). With no Vienna codes we look at
    the PNG. No image at all → None (nothing to route).
    """
    if vienna_codes:
        return "figurative"
    if image_path is None:
        return None
    return _pixel_backstop(image_path)


def _pixel_backstop(image_path: Path) -> str:
    """Wide+short+sparse PNG → 'wordmark'; otherwise 'figurative'. Fail-soft.

    Unreadable/corrupt images return 'figurative' so a bad read never silently
    suppresses a real logo (matches compute_logo_phash's fail-soft posture)."""
    try:
        with Image.open(image_path) as im:
            g = im.convert("L")
            w, h = g.size
            if w == 0 or h == 0:
                return "figurative"
            aspect = w / h
            dark = sum(g.histogram()[:_DARK_CUTOFF])
            ink = dark / (w * h)
    except Exception:
        return "figurative"
    if aspect >= _AR_MIN and ink <= _INK_MAX:
        return "wordmark"
    return "figurative"
```

- [ ] **Step 4: Run classifier tests to verify pass**

Run: `python -m pytest tests/test_logo_kind_classifier.py -q`
Expected: PASS (6 tests). If `test_wide_sparse_strip_is_wordmark` or the dense case is borderline, tune `_AR_MIN`/`_INK_MAX` so the synthetic strip (aspect 7.5, ink ≪0.20) classifies wordmark and the ellipse (aspect 1.0) classifies figurative — do not loosen so far that the ellipse flips.

- [ ] **Step 5: Commit**

```bash
git add api/_phash.py tests/test_logo_kind_classifier.py
git commit -m "feat(similarity): logo_kind classifier — Vienna-primary + pixel backstop"
```

---

### Task 3: Schema — `trademarks.logo_kind` column + migration

**Files:**
- Create: `app/backend/alembic/versions/20260625_0030_trademarks_logo_kind.py`
- Modify: `app/backend/api/db/models.py` (after the `logo_phash` column, ~line 266)

- [ ] **Step 1: Write the migration**

Create `app/backend/alembic/versions/20260625_0030_trademarks_logo_kind.py`:

```python
"""trademarks logo_kind

Revision ID: 20260625_0030
Revises: 20260625_0029
Create Date: 2026-06-25 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_0030"
down_revision: Union[str, None] = "20260625_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("logo_kind", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "logo_kind")
```

- [ ] **Step 2: Add the model column**

In `app/backend/api/db/models.py`, immediately after the `logo_phash` `mapped_column(...)` block (~line 266-268), add:

```python
    logo_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    """'figurative' | 'wordmark' | NULL — specimen routing for the visual axis (Track 1)."""
```

(`Text` is already imported — `logo_path` uses it.)

- [ ] **Step 3: Apply + verify the migration**

Run: `alembic upgrade head`
Expected: `Running upgrade 20260625_0029 -> 20260625_0030`.

Run: `alembic check`
Expected: `No new upgrade operations detected.` (model and migration agree).

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/20260625_0030_trademarks_logo_kind.py api/db/models.py
git commit -m "feat(similarity): trademarks.logo_kind column + migration"
```

---

### Task 4: Backfill — `scripts/backfill_logo_kind.py`

**Files:**
- Create: `app/backend/scripts/backfill_logo_kind.py`
- Create: `app/backend/tests/test_backfill_logo_kind.py`

- [ ] **Step 1: Write the failing backfill test**

Create `app/backend/tests/test_backfill_logo_kind.py`. It seeds Vienna-coded marks (so classification is 'figurative' via the Vienna branch — no PNG files needed) and asserts idempotency:

```python
"""Track 1: backfill_logo_kind is correct and idempotent."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from scripts.backfill_logo_kind import backfill_logo_kind

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000d1")
_FIG = uuid.UUID("e0000000-0000-4000-8000-0000000000d2")
_NOLOGO = uuid.UUID("e0000000-0000-4000-8000-0000000000d3")


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
                id=_GZ, filename="B_TEST_logo_kind.pdf", sha256="lk_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B, issue_year=2099, storage_path="/dev/null",
                size_bytes=0, status=GazetteStatus.completed,
            )
        )
        # Has a logo_path AND Vienna codes → classifier returns 'figurative'
        # via the Vienna branch without opening any file.
        s.add(
            Trademark(
                id=_FIG, gazette_id=_GZ, record_type=RecordType.B_domestic,
                application_number="LK-2099-1", logo_path="2099/x/fig.png",
                vienna_codes=["26.4.18"],
            )
        )
        # No logo at all → excluded from the work-list → logo_kind stays NULL.
        s.add(
            Trademark(
                id=_NOLOGO, gazette_id=_GZ, record_type=RecordType.B_domestic,
                application_number="LK-2099-2", logo_path=None, vienna_codes=["26.4.18"],
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
async def test_backfill_sets_kind_and_is_idempotent() -> None:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        first = await backfill_logo_kind(s, ids=[_FIG, _NOLOGO])
        assert first["updated"] == 1  # only _FIG (has a logo_path)
        kind = (await s.execute(select(Trademark.logo_kind).where(Trademark.id == _FIG))).scalar_one()
        assert kind == "figurative"
        nolar = (await s.execute(select(Trademark.logo_kind).where(Trademark.id == _NOLOGO))).scalar_one()
        assert nolar is None
        second = await backfill_logo_kind(s, ids=[_FIG, _NOLOGO])
        assert second["updated"] == 0 and second["unchanged"] == 1
    await engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_backfill_logo_kind.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_logo_kind'`.

- [ ] **Step 3: Implement the backfill (mirror `backfill_logo_phash.py`)**

Create `app/backend/scripts/backfill_logo_kind.py`:

```python
"""Backfill trademarks.logo_kind from Vienna codes + logo PNGs. Idempotent.

Mirrors backfill_logo_phash.py. For each trademark with a logo_path, classify
the specimen (Vienna-primary, pixel backstop) and store the kind. Marks with no
logo stay NULL (the visual axis routes to typographic anyway). Re-run after a
fresh ingest. Bump LOGO_KIND_VERSION if the classification rule changes.

    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
        python -m scripts.backfill_logo_kind
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._phash import classify_logo_kind
from api.db.models import Trademark
from api.settings import get_settings

log = logging.getLogger("logo_kind.backfill")

LOGO_KIND_VERSION = 1
_CHUNK = 1000


async def backfill_logo_kind(
    session: AsyncSession, *, ids: Sequence[object] | None = None
) -> dict[str, int]:
    """Classify + write logo_kind for every trademark with a logo (or just `ids`).

    Returns {"scanned": int, "updated": int, "unchanged": int}.
    """
    image_root = get_settings().data_dir / "image"
    stmt = select(
        Trademark.id,
        Trademark.logo_path,
        Trademark.vienna_codes,
        Trademark.logo_kind,
    ).where(Trademark.logo_path.is_not(None))
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))

    rows = (await session.execute(stmt)).all()
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    pending: list[dict[str, object]] = []

    for row in rows:
        stats["scanned"] += 1
        want = classify_logo_kind(row.vienna_codes or [], image_root / row.logo_path)
        if want == row.logo_kind:
            stats["unchanged"] += 1
            continue
        pending.append({"b_id": row.id, "logo_kind": want})
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
    stmt = update(tbl).where(tbl.c.id == bindparam("b_id")).values(logo_kind=bindparam("logo_kind"))
    await session.execute(stmt, rows)
    await session.commit()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.logo_kind (LOGO_KIND_VERSION=%d)", LOGO_KIND_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_logo_kind(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run the backfill test to verify pass**

Run: `python -m pytest tests/test_backfill_logo_kind.py -q`
Expected: PASS (1 test).

- [ ] **Step 5: Run the real backfill on the dev DB**

Run: `TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm python -m scripts.backfill_logo_kind`
Expected: prints `{'scanned': N, 'updated': N, 'unchanged': 0}` on first run (N = marks with a logo). A second run prints `updated: 0` — confirm idempotency once.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_logo_kind.py tests/test_backfill_logo_kind.py
git commit -m "feat(similarity): idempotent backfill_logo_kind"
```

---

### Task 5: Ingest wiring — populate `logo_kind` on new rows

**Files:**
- Modify: `app/backend/worker/ingest.py` (near `_phash_for_logo` ~244-253 and the set site ~419)

- [ ] **Step 1: Write the failing helper test**

Append to `app/backend/tests/test_logo_kind_classifier.py`:

```python
def test_logo_kind_for_helper_none_path_is_none(tmp_path):
    from worker.ingest import _logo_kind_for

    assert _logo_kind_for([], tmp_path, None) is None


def test_logo_kind_for_helper_vienna_is_figurative(tmp_path):
    from worker.ingest import _logo_kind_for

    # Vienna present → 'figurative' without needing the file to exist.
    assert _logo_kind_for(["26.4"], tmp_path, "missing.png") == "figurative"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_logo_kind_classifier.py -q`
Expected: FAIL — `ImportError: cannot import name '_logo_kind_for'`.

- [ ] **Step 3: Add the helper + set site in `worker/ingest.py`**

After `_phash_for_logo` (~line 253), add a sibling helper:

```python
def _logo_kind_for(vienna_codes: list[str], image_root: Path, logo_path: str | None) -> str | None:
    """Classify the specimen for visual-axis routing. None when there is no logo."""
    if logo_path is None:
        return None
    # Lazy import: api._phash pulls in Pillow. Keep worker boot cheap and let
    # tests monkey-patch before first use (same pattern as _phash_for_logo).
    from api._phash import classify_logo_kind

    return classify_logo_kind(vienna_codes, image_root / logo_path)
```

At the set site (~line 419), right after `trademark.logo_phash = _phash_for_logo(...)`, add:

```python
            trademark.logo_kind = _logo_kind_for(trademark.vienna_codes or [], image_root, logo_path)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_logo_kind_classifier.py -q`
Expected: PASS (8 tests total).

- [ ] **Step 5: Commit**

```bash
git add worker/ingest.py tests/test_logo_kind_classifier.py
git commit -m "feat(ingest): populate trademarks.logo_kind on new rows"
```

---

### Task 6: Route the visual axis by kind (the behaviour change)

**Files:**
- Modify: `app/backend/tm_similarity/features.py` (`MarkFeatures` gains `logo_kind`)
- Modify: `app/backend/tm_similarity/visual.py` (`visual_similarity` signature + routing)
- Modify: `app/backend/tm_similarity/__init__.py` (`score()` threads `logo_kind`; bump `SIMILARITY_VERSION`)
- Modify: `app/backend/api/routes/marks.py` (2 `MarkFeatures` sites)
- Modify: `app/backend/api/routes/compare.py` (2 `MarkFeatures` sites)
- Modify: `app/backend/tests/test_tm_similarity_visual.py` (add routing + regression tests)

- [ ] **Step 1: Write the failing routing + regression tests**

Append to `app/backend/tests/test_tm_similarity_visual.py`:

```python
import tm_similarity as t
from tm_similarity.visual import visual_similarity


def test_both_figurative_uses_phash():
    vs = visual_similarity("ffffffffffffffff", "ffffffffffffffff", "figurative", "figurative", None, None)
    assert vs.confidence == "phash" and vs.score == 1.0


def test_wordmark_side_routes_to_typographic():
    vs = visual_similarity("ffffffffffffffff", "0000000000000000", "wordmark", "figurative", "ACME", "ACMI")
    assert vs.confidence == "typographic"


def test_missing_phash_routes_to_typographic():
    vs = visual_similarity(None, "ffffffffffffffff", "figurative", "figurative", "ACME", "ACMI")
    assert vs.confidence == "typographic"


def test_unclassified_none_is_permissive_uses_phash():
    # NULL kind (pre-backfill) must NOT go dark — behaves like today (phash).
    vs = visual_similarity("ffffffffffffffff", "fffffffffffffffe", None, None, None, None)
    assert vs.confidence == "phash"


def test_no_text_no_phash_is_none():
    vs = visual_similarity(None, None, "wordmark", "wordmark", "", "")
    assert vs.confidence == "none" and vs.score == 0.0


def test_regression_unrelated_phash_pair_is_low_risk():
    # The reported /compare 63/59 bug: unrelated figurative logos (hd~32) used to
    # score ~0.59 visual and slip past the gate. Now visual≈0 → Low risk.
    a = t.MarkFeatures(mark_text=None, logo_phash="ffffffffffffffff", logo_kind="figurative",
                       nice_classes=["3"], vienna_codes=["1.1"])
    b = t.MarkFeatures(mark_text=None, logo_phash="00000000ffffffff", logo_kind="figurative",
                       nice_classes=["3"], vienna_codes=["2.2"])
    r = t.score(a, b)
    assert r.visual == 0.0
    assert r.verdict == "Low risk"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_tm_similarity_visual.py -q`
Expected: FAIL — `visual_similarity()` takes 4 args / `MarkFeatures` has no `logo_kind`.

- [ ] **Step 3: Add `logo_kind` to `MarkFeatures`**

In `app/backend/tm_similarity/features.py`, add the field (with a default so existing constructions stay valid):

```python
@dataclass(frozen=True)
class MarkFeatures:
    mark_text: str | None  # resolved name (mark_name ?? mark_sample); NEVER the applicant
    logo_phash: str | None  # 16-char hex pHash, precomputed; None = no usable logo
    nice_classes: list[str]  # same element type the routes pass from Trademark.nice_classes
    vienna_codes: list[str]
    logo_kind: str | None = None  # 'figurative' | 'wordmark' | None — specimen routing (Track 1)
```

- [ ] **Step 4: Change `visual_similarity` signature + routing**

In `app/backend/tm_similarity/visual.py`, replace `visual_similarity` with the kind-aware version:

```python
def visual_similarity(
    a_phash: str | None,
    b_phash: str | None,
    a_kind: str | None,
    b_kind: str | None,
    a_text: str | None,
    b_text: str | None,
) -> VisualScore:
    """Route by specimen kind. Recalibrated pHash only when BOTH specimens are
    genuine figurative devices (neither explicitly a wordmark-strip) and both
    hashes exist; otherwise typographic JW on the wordmark text.

    `None` kind (unclassified / pre-backfill) is treated permissively — only an
    explicit 'wordmark' suppresses the pHash path, so the axis never goes dark
    before the backfill runs.
    """
    a_word = a_kind == "wordmark"
    b_word = b_kind == "wordmark"
    if a_phash and b_phash and not a_word and not b_word:
        return VisualScore(_phash_score(_hamming_hex(a_phash, b_phash)), "phash")
    na, nb = normalize_vn(a_text), normalize_vn(b_text)
    if na and nb:
        return VisualScore(round(_token_jw(na, nb), 3), "typographic")
    return VisualScore(0.0, "none")
```

- [ ] **Step 5: Thread `logo_kind` through `score()` + bump the version**

In `app/backend/tm_similarity/__init__.py`, change the `visual_similarity` call in `score()`:

```python
    vis = visual_similarity(
        a.logo_phash, b.logo_phash, a.logo_kind, b.logo_kind, a.mark_text, b.mark_text
    )
```

and bump:

```python
SIMILARITY_VERSION = "1.1"
```

- [ ] **Step 6: Build `MarkFeatures(logo_kind=...)` in the two route adapters**

In `app/backend/api/routes/marks.py`, add `logo_kind=m.logo_kind` to the `m_feat` `MarkFeatures(...)` (~394) and `logo_kind=r.logo_kind` to the candidate `MarkFeatures(...)` (~406).

In `app/backend/api/routes/compare.py`, add `logo_kind=anchor.logo_kind` to the anchor `MarkFeatures(...)` (~159) and `logo_kind=other.logo_kind` to the other `MarkFeatures(...)` (~165).

(`search.py` builds no `MarkFeatures` — its `image` mode is an unwired placeholder — so it needs no change.)

- [ ] **Step 7: Run the full affected test set**

Run: `python -m pytest tests/test_tm_similarity_visual.py tests/test_tm_similarity_engine.py tests/test_logo_kind_classifier.py -q`
Expected: PASS.

Run the route + any similar-marks/compare tests that exercise the engine:
`python -m pytest tests/ -q -k "similar or compare or marks or similarity or mark_name"`
Expected: PASS. The Track 0 golden test stays green (curve + routing don't touch the fixed-input composite cases). If a pre-existing route test asserted an old inflated visual percentage on an unrelated pair, update it to the new (low) value — that is the intended behaviour change, not a regression.

- [ ] **Step 8: Commit**

```bash
git add tm_similarity/features.py tm_similarity/visual.py tm_similarity/__init__.py api/routes/marks.py api/routes/compare.py tests/test_tm_similarity_visual.py
git commit -m "feat(similarity): route visual axis by specimen kind; bump SIMILARITY_VERSION 1.1"
```

---

### Task 7: Gates + docs sync

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full backend gate locally**

Run (from `app/backend/`):
```bash
ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check
```
Expected: all clean. Fix any ruff/mypy findings in the files this branch touched (e.g. add return types, drop unused imports). Then:

Run: `python -m pytest tests/ -q -k "similarity or visual or logo_kind or compare or similar or mark_name"`
Expected: PASS.

- [ ] **Step 2: Update `CLAUDE.md`**

In the similarity-engine section (the Track 0 / `tm_similarity` notes), add a short paragraph:

```markdown
**Track 1 (visual axis):** the visual sub-score is now specimen-routed. A new
`trademarks.logo_kind` column ('figurative' | 'wordmark' | NULL), computed by
`api/_phash.py:classify_logo_kind` (Vienna-(531)-primary, cheap pixel backstop
for no-Vienna marks) and populated by `scripts/backfill_logo_kind.py`
(LOGO_KIND_VERSION) + the ingest worker. `tm_similarity.visual_similarity`
compares perceptual hashes (recalibrated `1 - hd/VISUAL_PHASH_THRESHOLD`, T=10 —
unrelated images now score ~0, not ~0.50) ONLY when both specimens are genuine
figurative devices; a wordmark-strip (or NULL pre-backfill is permissive) routes
to typographic JW so rendered text can't inflate the visual axis. SIMILARITY_VERSION
is 1.1. **Re-run `scripts/backfill_logo_kind.py` after a fresh ingest** (same caveat
as logo_phash / mark_name / vn_grant_date).
```

- [ ] **Step 3: Commit**

```bash
git add ../../CLAUDE.md
git commit -m "docs: document Track 1 visual-axis routing + recalibration"
```

- [ ] **Step 4: Final whole-branch review**

Run: `git log --oneline track1-visual-routing ^main` — expect 7 feature commits + the spec + this plan.
Confirm the rename trio is still unstaged: `git status -sb` shows `M README.md`, `M app/.env.example`, `M app/backend/api/settings.py` and nothing else uncommitted.

---

## Self-Review

**Spec coverage:** §1 classifier → Task 2; `logo_kind` column → Task 3; backfill → Task 4; ingest → Task 5; §2 routing → Task 6; §3 curve → Task 1; §4 versioning (`SIMILARITY_VERSION` 1.1 Task 6, `LOGO_KIND_VERSION` Task 4); §5 testing → calibration artifact (T1), curve tests (T1), classifier tests (T2), routing tests (T6), regression test (T6), golden-stays-green (T1/T6), backfill test (T4), route integration (T6/T7); §6 docs → Task 7. **Refinement vs spec:** routing is permissive on `NULL` kind (no pre-backfill dark window) — documented in Task 6 Step 4; the spec's intent (suppress *wordmark*) is preserved. **Scope correction:** `search.py` is a no-op (unwired placeholder), so it is excluded — narrower than the spec's "marks/compare/search".

**Placeholder scan:** none — every code step shows full code; no "TBD"/"handle errors"/"similar to Task N".

**Type consistency:** `classify_logo_kind(list[str], Path | None) -> str | None`, `_pixel_backstop(Path) -> str`, `_logo_kind_for(list[str], Path, str | None) -> str | None`, `_phash_score(int) -> float`, `VISUAL_PHASH_THRESHOLD: int = 10`, `MarkFeatures.logo_kind: str | None = None`, `visual_similarity(a_phash, b_phash, a_kind, b_kind, a_text, b_text)` — names and signatures match across Tasks 1-7.
