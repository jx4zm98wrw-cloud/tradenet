# Similarity Engine Extraction (Track 0) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Full design: `docs/superpowers/specs/2026-06-25-similarity-engine-extraction-design.md` — read it before each task.

**Goal:** Extract the conflict-similarity engine from `api/similarity.py` into a standalone pure package `tm_similarity/` (stdlib + `jellyfish` only) and decouple it from the filesystem by precomputing the logo pHash into `trademarks.logo_phash`. Strictly behaviour-preserving — every score identical before/after.

**Architecture:** Pure package reads a `MarkFeatures` DTO (text + precomputed hex pHash + classes + vienna) and returns a `ScoreResult`. pHash is computed by an "indexer" (`api/_phash.py`, used by a backfill + the ingest worker) and stored; the engine only does integer Hamming on the stored hex. Old `api/similarity.py` and the new package coexist until the routes are switched, then the old module is deleted.

**Tech Stack:** Python 3, FastAPI + SQLAlchemy async (routes/worker), Alembic (migration), `jellyfish` (engine), Pillow + `imagehash` (indexer only), pytest.

---

## Reference points (read these first)

- `app/backend/api/similarity.py` — the source. Symbol map (exact lines):
  - phonetic block **63–231**: `_VN_LETTER_MAP`, `normalize_vn`, `_TOKEN_SPLIT`, `_tokens`, `_best_pair_jw`, `_token_jw`, `_PHONETIC_LENGTH_TOLERANCE`, `phonetic_similarity`.
  - visual block **234–331**: `VisualConfidence` (Literal), `VisualScore` (dataclass), `_phash_cache`, `_phash_for`, `visual_similarity`. **This block is replaced, not moved** (filesystem → hex).
  - overlap block **334–355**: `_jaccard`, `class_overlap`, `vienna_overlap`.
  - composite block **358–end**: `DEFAULT_WEIGHTS`, `resolve_weights`, `CompositeScore` (dataclass), `composite_score`.
- `app/backend/scripts/backfill_mark_name.py` — the backfill pattern to mirror: module-level `MARK_NAME_VERSION = 1`, `_CHUNK = 1000`, `async def backfill_*(session, *, ids=None) -> dict[str,int]` returning `{"scanned","updated","unchanged"}`, `_flush`, `_main()` using `os.environ["TM_DATABASE_URL"]` + `async_sessionmaker`.
- `app/backend/api/routes/compare.py:141` `_score_pair(anchor, other, w, image_root)` — calls `sim.phonetic_similarity`, `sim.visual_similarity(... image_root=...)`, `sim.class_overlap`, `sim.vienna_overlap`, `sim.composite_score`; returns `PairScore` (has `visualConfidence`).
- `app/backend/api/routes/marks.py:385-413` — `similar_marks` builds `m_text`/`r_text` and calls the same axis fns + `composite_score` with `image_root`.
- `app/backend/api/routes/search.py:97` — uses **only** `sim.phonetic_similarity`.
- `app/backend/api/routes/watchlists.py:24` — `from ..similarity import DEFAULT_WEIGHTS`.
- `app/backend/worker/ingest.py` — `_resolve_logo_path(section, image_subdir, image_root)` returns the relative logo path stored in `trademarks.logo_path`.
- `app/backend/pyproject.toml:13-15` — `[tool.setuptools.packages.find] include = ["api*","worker*","tm_extractor*","image_extractor*","scripts*"]`; `[tool.mypy]` at line 50.

**Standing constraints (every task):**
- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths only.
- Run from `app/backend` with the venv: `../.venv/bin/<tool>`.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic check && pytest`. Targeted pytest locally (sweep tests reset the live singleton).
- Branch off `main`; one migration in this plan (Task 3).

---

## Task 1: Freeze the golden behaviour baseline

**Files:** Create `app/backend/tests/_similarity_cases.py`, `app/backend/tests/fixtures/similarity_golden.json`.

- [ ] **Step 1: Write the shared case list.** Create `tests/_similarity_cases.py`:

```python
"""Shared input cases for the engine equivalence golden test (Track 0)."""

# (a_text, b_text)
PHONETIC_CASES = [
    ("Sulfani", "Sulfani"),
    ("Gemy", "KAVIN SAVING POWER"),
    ("VIET AGAROYAL", "VIET AGAROYAL GLOBAL"),
    ("Taseko", "Tabeko"),
    ("", "ABC"),
    ("CÔNG TY DƯỢC", "CÔNG TY DƯỢC PHẨM"),
]

# (a_codes, b_codes) — used for BOTH class_overlap and vienna_overlap
OVERLAP_CASES = [
    (["11"], ["11"]),
    (["11"], ["42"]),
    (["9", "42"], ["42"]),
    (["3"], ["3", "5"]),
    ([], ["1"]),
]

# (phonetic, visual, class_o, vienna_o, visual_confidence)
COMPOSITE_CASES = [
    (0.60, 0.63, 1.0, 0.0, "phash"),
    (0.14, 0.63, 1.0, 0.0, "phash"),
    (0.90, 0.90, 1.0, 1.0, "phash"),
    (0.49, 0.20, 1.0, 0.0, "typographic"),
    (0.16, 0.59, 1.0, 0.0, "phash"),
]
```

- [ ] **Step 2: Capture the baseline from the CURRENT engine.** Run this one-liner (writes the golden JSON from today's `api/similarity.py`):

```bash
cd app/backend && ../.venv/bin/python -c "
import json, pathlib
from api import similarity as s
from tests._similarity_cases import PHONETIC_CASES, OVERLAP_CASES, COMPOSITE_CASES
out = {
  'phonetic': [s.phonetic_similarity(a, b) for a, b in PHONETIC_CASES],
  'class':    [s.class_overlap(a, b) for a, b in OVERLAP_CASES],
  'vienna':   [s.vienna_overlap(a, b) for a, b in OVERLAP_CASES],
  'composite':[ (lambda cs: [cs.composite, cs.verdict, cs.verdict_tone])(
                  s.composite_score(p, v, c, vi, visual_confidence=vc))
                for p, v, c, vi, vc in COMPOSITE_CASES ],
}
pathlib.Path('tests/fixtures').mkdir(parents=True, exist_ok=True)
pathlib.Path('tests/fixtures/similarity_golden.json').write_text(json.dumps(out, indent=2, ensure_ascii=False))
print('wrote', out)
"
```

- [ ] **Step 3: Commit the baseline.**

```bash
cd app/backend
git add tests/_similarity_cases.py tests/fixtures/similarity_golden.json
git commit -m "test(similarity): freeze golden behaviour baseline before extraction"
```

---

## Task 2: Create the `tm_similarity/` package

**Files:** Create `app/backend/tm_similarity/{__init__.py,features.py,phonetic.py,visual.py,classes.py,composite.py}`, `app/backend/tests/test_tm_similarity_engine.py`; Modify `app/backend/pyproject.toml`.

- [ ] **Step 1: Move the pure axes verbatim.**
  - Create `tm_similarity/phonetic.py`: header `from __future__ import annotations`, `import re`, `import unicodedata`, `import jellyfish`, then **copy `api/similarity.py` lines 63–231 verbatim** (`_VN_LETTER_MAP` … `phonetic_similarity`).
  - Create `tm_similarity/classes.py`: header `from __future__ import annotations`, then **copy lines 334–355 verbatim** (`_jaccard`, `class_overlap`, `vienna_overlap`).
  - Create `tm_similarity/composite.py`: header `from __future__ import annotations`, `from dataclasses import dataclass`, `from typing import Literal`, `from .visual import VisualConfidence`, then **copy lines 358–end verbatim** (`DEFAULT_WEIGHTS`, `resolve_weights`, `CompositeScore`, `composite_score`).

- [ ] **Step 2: Write the new hex-based visual axis.** Create `tm_similarity/visual.py`:

```python
"""Visual similarity from a PRECOMPUTED hex pHash (no filesystem, no Pillow).

Track 0 keeps the exact 1 - HD/64 formula; recalibration is Track 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .phonetic import _token_jw, normalize_vn

VisualConfidence = Literal["phash", "typographic", "none"]


@dataclass(frozen=True)
class VisualScore:
    score: float
    confidence: VisualConfidence


def _hamming_hex(a: str, b: str) -> int:
    """Hamming distance between two 16-char hex pHashes (popcount of XOR)."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def visual_similarity(
    a_phash: str | None,
    b_phash: str | None,
    a_text: str | None,
    b_text: str | None,
) -> VisualScore:
    """pHash Hamming when both hashes exist; else typographic JW on the wordmark."""
    if a_phash and b_phash:
        hd = _hamming_hex(a_phash, b_phash)
        return VisualScore(round(max(0.0, 1.0 - hd / 64.0), 3), "phash")
    na, nb = normalize_vn(a_text), normalize_vn(b_text)
    if na and nb:
        return VisualScore(round(_token_jw(na, nb), 3), "typographic")
    return VisualScore(0.0, "none")
```

> Confirm against `api/similarity.py:292-331` that the typographic fallback there is `_token_jw(normalize_vn(a_text), normalize_vn(b_text))` rounded to 3 — replicate exactly (adapt if the original differs).

- [ ] **Step 3: Write the DTOs.** Create `tm_similarity/features.py`:

```python
"""Pure data contracts for the similarity engine — no ORM, no IO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkFeatures:
    mark_text: str | None        # resolved name (mark_name ?? mark_sample); NEVER the applicant
    logo_phash: str | None       # 16-char hex pHash, precomputed; None = no usable logo
    nice_classes: list[str]      # same element type the routes pass from Trademark.nice_classes
    vienna_codes: list[str]


@dataclass(frozen=True)
class ScoreResult:
    composite: float
    verdict: str                 # "Likely conflict" | "Possible conflict" | "Low risk"
    verdict_tone: str            # "stamp" | "warn" | "ok"
    phonetic: float
    visual: float
    visual_confidence: str       # "phash" | "typographic" | "none"
    class_overlap: float
    vienna_overlap: float
```

- [ ] **Step 4: Write the public API.** Create `tm_similarity/__init__.py`:

```python
"""tm_similarity — standalone trademark conflict-similarity engine.

Pure: depends only on stdlib + jellyfish. Features in, ScoreResult out.
"""

from __future__ import annotations

from .classes import class_overlap, vienna_overlap
from .composite import DEFAULT_WEIGHTS, CompositeScore, composite_score, resolve_weights
from .features import MarkFeatures, ScoreResult
from .phonetic import normalize_vn, phonetic_similarity
from .visual import VisualConfidence, VisualScore, visual_similarity

SIMILARITY_VERSION = "1.0"

__all__ = [
    "SIMILARITY_VERSION", "score", "MarkFeatures", "ScoreResult",
    "phonetic_similarity", "visual_similarity", "class_overlap", "vienna_overlap",
    "composite_score", "CompositeScore", "resolve_weights", "DEFAULT_WEIGHTS",
    "normalize_vn", "VisualScore", "VisualConfidence",
]


def score(
    a: MarkFeatures, b: MarkFeatures, *, weights: dict[str, float] | None = None
) -> ScoreResult:
    """Score one pair of marks across all axes; assemble the full ScoreResult."""
    phon = phonetic_similarity(a.mark_text, b.mark_text)
    vis = visual_similarity(a.logo_phash, b.logo_phash, a.mark_text, b.mark_text)
    class_o = class_overlap(a.nice_classes, b.nice_classes)
    vienna_o = vienna_overlap(a.vienna_codes, b.vienna_codes)
    cs = composite_score(
        phon, vis.score, class_o, vienna_o, weights=weights, visual_confidence=vis.confidence
    )
    return ScoreResult(
        composite=cs.composite, verdict=cs.verdict, verdict_tone=cs.verdict_tone,
        phonetic=phon, visual=vis.score, visual_confidence=vis.confidence,
        class_overlap=class_o, vienna_overlap=vienna_o,
    )
```

- [ ] **Step 5: Register the package.** In `pyproject.toml:15`, add `"tm_similarity*"` to the `include` list:

```toml
include = ["api*", "worker*", "tm_extractor*", "image_extractor*", "scripts*", "tm_similarity*"]
```

Then re-install so it lands on `sys.path`: `cd app/backend && ../.venv/bin/pip install -e . -q`.

- [ ] **Step 6: Write the equivalence + visual tests.** Create `tests/test_tm_similarity_engine.py`:

```python
"""tm_similarity reproduces the frozen golden baseline; hex pHash == imagehash."""

from __future__ import annotations

import json
import pathlib

import imagehash
from PIL import Image

import tm_similarity as t
from tm_similarity.visual import _hamming_hex
from tests._similarity_cases import COMPOSITE_CASES, OVERLAP_CASES, PHONETIC_CASES

GOLDEN = json.loads(pathlib.Path("tests/fixtures/similarity_golden.json").read_text())


def test_phonetic_matches_golden():
    got = [t.phonetic_similarity(a, b) for a, b in PHONETIC_CASES]
    assert got == GOLDEN["phonetic"]


def test_class_and_vienna_match_golden():
    assert [t.class_overlap(a, b) for a, b in OVERLAP_CASES] == GOLDEN["class"]
    assert [t.vienna_overlap(a, b) for a, b in OVERLAP_CASES] == GOLDEN["vienna"]


def test_composite_matches_golden():
    got = [
        [(cs := t.composite_score(p, v, c, vi, visual_confidence=vc)).composite, cs.verdict, cs.verdict_tone]
        for p, v, c, vi, vc in COMPOSITE_CASES
    ]
    assert got == GOLDEN["composite"]


def test_hex_phash_equals_imagehash_hamming():
    a = Image.new("L", (32, 32), 0); a.putpixel((2, 2), 255)
    b = Image.new("L", (32, 32), 0); b.putpixel((29, 29), 255)
    ha, hb = imagehash.phash(a), imagehash.phash(b)
    assert _hamming_hex(str(ha), str(hb)) == (ha - hb)


def test_score_assembles_result():
    a = t.MarkFeatures(mark_text="Gemy", logo_phash=None, nice_classes=["11"], vienna_codes=[])
    b = t.MarkFeatures(mark_text="Gemy", logo_phash=None, nice_classes=["11"], vienna_codes=[])
    r = t.score(a, b)
    assert r.phonetic == t.phonetic_similarity("Gemy", "Gemy")
    assert r.verdict in {"Likely conflict", "Possible conflict", "Low risk"}
```

- [ ] **Step 7: Run → pass, gates, commit.**

```bash
cd app/backend
../.venv/bin/ruff format tm_similarity tests/test_tm_similarity_engine.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker tm_similarity
../.venv/bin/pytest tests/test_tm_similarity_engine.py -q
git add tm_similarity pyproject.toml tests/test_tm_similarity_engine.py
git commit -m "feat(tm_similarity): standalone pure engine package (hex pHash); golden-equivalent"
```

---

## Task 3: Feature-store schema + pHash indexer

**Files:** Create `app/backend/api/_phash.py`, an Alembic migration, `app/backend/tests/test_phash_indexer.py`; Modify `app/backend/api/db/models.py`.

- [ ] **Step 1: Write the failing indexer test.** Create `tests/test_phash_indexer.py`:

```python
"""api/_phash.compute_logo_phash returns a 16-hex string or None."""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image

from api._phash import compute_logo_phash


def test_compute_returns_hex(tmp_path: Path):
    p = tmp_path / "logo.png"
    img = Image.new("L", (32, 32), 0); img.putpixel((4, 4), 255)
    img.save(p)
    got = compute_logo_phash(p)
    assert got == str(imagehash.phash(Image.open(p)))
    assert len(got) == 16


def test_missing_file_returns_none(tmp_path: Path):
    assert compute_logo_phash(tmp_path / "nope.png") is None
```

- [ ] **Step 2: Run → fail** — `cd app/backend && ../.venv/bin/pytest tests/test_phash_indexer.py -q` → ImportError.

- [ ] **Step 3: Implement the indexer.** Create `api/_phash.py`:

```python
"""Logo pHash indexer — the ONLY place Pillow/imagehash touch similarity.

Computes the perceptual hash the pure tm_similarity engine consumes. Kept out
of tm_similarity so that package stays dependency-light (stdlib + jellyfish).
"""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image


def compute_logo_phash(image_path: Path) -> str | None:
    """Return the 16-char hex pHash of the image, or None if unreadable."""
    try:
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None
```

- [ ] **Step 4: Add the column.** In `api/db/models.py`, add to the `Trademark` model (next to `mark_name`):

```python
    logo_phash: Mapped[str | None] = mapped_column(Text, nullable=True)
```

(Ensure `Text` is imported in that module — it is used by other columns; reuse the existing import.)

- [ ] **Step 5: Generate + edit the migration.**

```bash
cd app/backend && ../.venv/bin/alembic revision -m "add trademarks.logo_phash"
```

Edit the new file in `app/backend/alembic/versions/` so `down_revision` points at the current head (verify with `../.venv/bin/alembic heads` — expected `20260624_0028`) and the body is:

```python
def upgrade() -> None:
    op.add_column("trademarks", sa.Column("logo_phash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "logo_phash")
```

- [ ] **Step 6: Apply + gates + commit.**

```bash
cd app/backend
../.venv/bin/alembic upgrade head && ../.venv/bin/alembic check
../.venv/bin/ruff format api/_phash.py tests/test_phash_indexer.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker tm_similarity
../.venv/bin/pytest tests/test_phash_indexer.py -q
git add api/_phash.py api/db/models.py alembic/versions/
git commit -m "feat(similarity): trademarks.logo_phash column + pHash indexer"
```

---

## Task 4: Backfill `trademarks.logo_phash`

**Files:** Create `app/backend/scripts/backfill_logo_phash.py`, `app/backend/tests/test_backfill_logo_phash.py`.

- [ ] **Step 1: Write the failing test.** Create `tests/test_backfill_logo_phash.py` (mirror `test_search_mark_name.py`'s seed fixture; seed one mark with a real PNG under `image_root`, one without a logo):

```python
"""backfill_logo_phash sets hex for marks with a readable logo; idempotent."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from scripts.backfill_logo_phash import backfill_logo_phash

_GZ = uuid.UUID("e3000000-0000-4000-8000-0000000000d1")
_WITH = uuid.UUID("e3000000-0000-4000-8000-0000000000d2")
_WITHOUT = uuid.UUID("e3000000-0000-4000-8000-0000000000d3")
_REL = "2099/test_phash/logo.png"


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    p = get_settings().data_dir / "image" / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", (32, 32), 0); img.putpixel((6, 6), 255); img.save(p)
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(Gazette(id=_GZ, filename="A_TEST_phash.pdf", sha256="phash_" + uuid.uuid4().hex,
                      gazette_type=GazetteType.A, issue_year=2099, storage_path="/dev/null",
                      size_bytes=0, status=GazetteStatus.completed))
        s.add(Trademark(id=_WITH, gazette_id=_GZ, record_type=RecordType.A,
                        application_number="PH-1", logo_path=_REL, publication_date_441=date(2099, 1, 1)))
        s.add(Trademark(id=_WITHOUT, gazette_id=_GZ, record_type=RecordType.A,
                        application_number="PH-2", logo_path=None, publication_date_441=date(2099, 1, 1)))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()
    p.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_backfill_sets_and_is_idempotent():
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill_logo_phash(s, ids=[_WITH, _WITHOUT])
        assert stats["updated"] == 1
        with_row = (await s.execute(select(Trademark).where(Trademark.id == _WITH))).scalar_one()
        without_row = (await s.execute(select(Trademark).where(Trademark.id == _WITHOUT))).scalar_one()
        assert with_row.logo_phash and len(with_row.logo_phash) == 16
        assert without_row.logo_phash is None
    async with Session() as s:
        stats2 = await backfill_logo_phash(s, ids=[_WITH, _WITHOUT])
        assert stats2["updated"] == 0  # idempotent
    await engine.dispose()
```

- [ ] **Step 2: Run → fail** (ImportError).

- [ ] **Step 3: Implement the backfill** (mirror `scripts/backfill_mark_name.py`). Create `scripts/backfill_logo_phash.py`:

```python
"""Backfill trademarks.logo_phash from extracted logo PNGs. Idempotent.

Mirrors backfill_mark_name.py. Re-run after a fresh ingest (the ingest worker
also populates it for new rows). Bump PHASH_VERSION if the hash changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._phash import compute_logo_phash
from api.db import Trademark
from api.settings import get_settings

log = logging.getLogger("backfill_logo_phash")
PHASH_VERSION = 1
_CHUNK = 1000


async def backfill_logo_phash(
    session: AsyncSession, *, ids: Sequence[object] | None = None
) -> dict[str, int]:
    image_root = get_settings().data_dir / "image"
    stmt = select(Trademark).where(Trademark.logo_path.is_not(None))
    if ids is not None:
        stmt = stmt.where(Trademark.id.in_(ids))
    stats = {"scanned": 0, "updated": 0, "unchanged": 0}
    result = await session.stream_scalars(stmt)
    async for mark in result:
        stats["scanned"] += 1
        new = compute_logo_phash(image_root / mark.logo_path)
        if new == mark.logo_phash:
            stats["unchanged"] += 1
            continue
        mark.logo_phash = new
        stats["updated"] += 1
        if stats["updated"] % _CHUNK == 0:
            await session.commit()
    await session.commit()
    return stats


async def _main() -> None:
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("backfilling trademarks.logo_phash (PHASH_VERSION=%d)", PHASH_VERSION)
    async with sessionmaker() as session:
        stats = await backfill_logo_phash(session)
    await engine.dispose()
    log.info("DONE: %s", stats)
    print(stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
```

> If `backfill_mark_name.py` uses a plain `execute`/`scalars` loop rather than `stream_scalars`, match its exact iteration style instead (read it first). Keep the `{"scanned","updated","unchanged"}` contract.

- [ ] **Step 4: Run → pass** — `../.venv/bin/pytest tests/test_backfill_logo_phash.py -q`.

- [ ] **Step 5: Gates + commit + run the real backfill.**

```bash
cd app/backend
../.venv/bin/ruff format scripts/backfill_logo_phash.py tests/test_backfill_logo_phash.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker tm_similarity
../.venv/bin/pytest tests/test_backfill_logo_phash.py -q
git add scripts/backfill_logo_phash.py tests/test_backfill_logo_phash.py
git commit -m "feat(similarity): idempotent backfill_logo_phash"
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm ../.venv/bin/python -m scripts.backfill_logo_phash
```

---

## Task 5: Populate pHash on ingest

**Files:** Modify `app/backend/worker/ingest.py`; Test `app/backend/tests/test_ingest_phash.py`.

- [ ] **Step 1: Read `worker/ingest.py`** around `_resolve_logo_path` and the `mapper.section_to_trademark` call to find where the `Trademark` row gets its `logo_path` set (the point to also set `logo_phash`).

- [ ] **Step 2: Write the failing test.** Create `tests/test_ingest_phash.py` — unit-test the helper that derives pHash from a resolved logo path:

```python
"""Ingest sets logo_phash from the resolved logo PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from worker.ingest import _phash_for_logo  # small helper added in Step 3


def test_phash_for_logo(tmp_path: Path):
    rel = "x/logo.png"
    (tmp_path / "x").mkdir()
    img = Image.new("L", (32, 32), 0); img.putpixel((7, 7), 255)
    img.save(tmp_path / rel)
    assert _phash_for_logo(tmp_path, rel) is not None
    assert _phash_for_logo(tmp_path, None) is None
```

- [ ] **Step 3: Implement.** In `worker/ingest.py`, add the helper and call it where `logo_path` is assigned:

```python
from api._phash import compute_logo_phash


def _phash_for_logo(image_root, logo_path: str | None) -> str | None:
    return compute_logo_phash(image_root / logo_path) if logo_path else None
```

Then, where the mapper produces the `Trademark` and `logo_path` is resolved, set `trademark.logo_phash = _phash_for_logo(image_root, trademark.logo_path)` (use the same `image_root` the ingest already resolves). Keep it inside the existing per-section flow; a failure to compute degrades to `None` (already handled by `compute_logo_phash`).

- [ ] **Step 4: Run → pass** — `../.venv/bin/pytest tests/test_ingest_phash.py -q`.

- [ ] **Step 5: Gates + commit.**

```bash
cd app/backend
../.venv/bin/ruff format worker/ingest.py tests/test_ingest_phash.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker tm_similarity
../.venv/bin/pytest tests/test_ingest_phash.py -q
git add worker/ingest.py tests/test_ingest_phash.py
git commit -m "feat(ingest): populate trademarks.logo_phash for new rows"
```

---

## Task 6: Switch routes to the package; delete the old module

**Files:** Modify `app/backend/api/routes/{marks.py,compare.py,search.py,watchlists.py}`; Delete `app/backend/api/similarity.py`.

- [ ] **Step 1: compare.py.** Replace `from .. import similarity as sim` (`:27`) with `from tm_similarity import MarkFeatures, resolve_weights, score`. Rewrite `_score_pair` to build two `MarkFeatures` and call `score()`:
  - `mark_text` = the same text the function builds today (`a_text`/`o_text`) — keep that resolution.
  - `logo_phash` = `anchor.logo_phash` / `other.logo_phash` (the new column).
  - `nice_classes`/`vienna_codes` = `anchor.nice_classes`/`anchor.vienna_codes` etc.
  - Map `ScoreResult` fields onto `PairScore` (composite, verdict/tone, phonetic, visual, `visualConfidence` = `result.visual_confidence`, class, vienna). Drop the `image_root` parameter and its `get_settings().data_dir / "image"` line (`:116`).

- [ ] **Step 2: marks.py.** Replace `from .. import similarity as sim` (`:23`) with `from tm_similarity import MarkFeatures, resolve_weights, score`. In `similar_marks`, drop `image_root` (`:385`); build `MarkFeatures` for `m` and each candidate `r` (using the existing `m_text`/`r_text` resolution + `.logo_phash`); call `score(...)`; read `result.composite`/`result.visual_confidence` where the code used `cs.composite`/`vis.confidence`. Keep the `verdict != "Low risk"` gate (from PR #108) using `result.verdict`.

- [ ] **Step 3: search.py.** Replace `from .. import similarity as sim` (`:27`) with `from tm_similarity import phonetic_similarity`; change `:97` to `round(phonetic_similarity(q, target), 3)`.

- [ ] **Step 4: watchlists.py.** Change `:24` to `from tm_similarity import DEFAULT_WEIGHTS`.

- [ ] **Step 5: Delete the old module + verify no stragglers.**

```bash
cd app/backend
git rm api/similarity.py
grep -rnE "api\.similarity|from \.\. import similarity|from \.similarity|import similarity as sim" api worker tests scripts || echo "no stale references"
```

Fix any remaining reference the grep finds (e.g. a test importing `api.similarity` — repoint to `tm_similarity`). Note: the Task-1 capture one-liner imported `api.similarity` but was a one-shot (not committed as a script), so there is nothing to update there.

- [ ] **Step 6: Full gate + commit.**

```bash
cd app/backend
../.venv/bin/ruff format api/routes/marks.py api/routes/compare.py api/routes/search.py api/routes/watchlists.py
../.venv/bin/ruff check . && ../.venv/bin/mypy api worker tm_similarity && ../.venv/bin/alembic check
../.venv/bin/pytest tests/test_tm_similarity_engine.py tests/test_phash_indexer.py tests/test_backfill_logo_phash.py tests/test_ingest_phash.py -q
../.venv/bin/pytest tests/test_compare_status.py tests/test_search_mark_name.py tests/test_per_matter_weights.py -q   # route-level regression
git add api/routes/marks.py api/routes/compare.py api/routes/search.py api/routes/watchlists.py
git rm api/similarity.py
git commit -m "refactor(similarity): route engine through tm_similarity; remove api/similarity.py"
```

---

## Task 7: Docs sync

**Files:** Modify `CLAUDE.md`.

- [ ] **Step 1:** Add to the project-layout section (near the other vendored packages) a `tm_similarity/` entry: "standalone pure conflict-similarity engine (stdlib + jellyfish); reads `MarkFeatures` (incl. precomputed `trademarks.logo_phash`) → `ScoreResult`. pHash computed by `api/_phash.py` at ingest/backfill (`scripts/backfill_logo_phash.py`) — **re-run the backfill after a fresh ingest** (same caveat as `mark_name`)."
- [ ] **Step 2:** Commit: `git add CLAUDE.md && git commit -m "docs: document tm_similarity engine extraction + logo_phash feature-store"`.

---

## Self-review

- **Spec coverage:** package + DTOs + API/version (Task 2 ✓); hex visual, no filesystem (Task 2 Step 2 ✓); `api/_phash.py` indexer (Task 3 ✓); `logo_phash` migration (Task 3 ✓); idempotent backfill (Task 4 ✓); ingest wiring (Task 5 ✓); route adapters + delete old module (Task 6 ✓); pyproject + mypy target (Task 2 Step 5 / gates ✓); golden behaviour-preservation + pHash parity (Task 1 + Task 2 Step 6 ✓); docs (Task 7 ✓). All spec sections mapped.
- **Placeholder scan:** every code step has full code or an exact verbatim line-range to move; commands have expected outcomes. The two "confirm against the original" notes (visual fallback, backfill iteration style) are verification guards, not missing content.
- **Type consistency:** `MarkFeatures(mark_text, logo_phash, nice_classes, vienna_codes)` and `ScoreResult(...)` identical across Task 2 (def), Task 2 Step 6 (test), Task 6 (adapters); `score()` signature `score(a, b, *, weights=None) -> ScoreResult` consistent; `compute_logo_phash(Path) -> str | None` consistent across Tasks 3/4/5; `_hamming_hex` defined in `visual.py` and used in the Task 2 test; `visual_similarity(a_phash, b_phash, a_text, b_text)` 4-arg form consistent (no more `image_root`).
- **Behaviour-preservation risk:** the only non-verbatim logic is `visual.py`; its equivalence to the old filesystem path is pinned by `test_hex_phash_equals_imagehash_hamming` (Task 2) — `1 - hd/64` and rounding are copied exactly. Golden JSON pins the pure axes + composite.
