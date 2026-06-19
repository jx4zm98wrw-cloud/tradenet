# Madrid Enrichment — Pipeline Core (Plan 1 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `madrid_records` table and a `fetch → parse → derive → store` pipeline that can enrich a single WIPO Madrid IRN, fully unit-tested offline against a saved fixture.

**Architecture:** A new `app/backend/madrid_enrich/` package (sibling to `tm_extractor/`) with four focused units — `client` (polite HTTP + raw-HTML disk cache), `parser` (pure, INID-anchored HTML → `MadridRecord`), `derive` (VN status from the record), `store` (idempotent upsert by IRN) — plus an `enrich_one(irn)` orchestrator. The ORM `MadridRecord` model lives in `api/db/models.py` next to `Trademark`; the join key is `madrid_records.irn = trademarks.lineage_key`.

**Tech Stack:** Python 3.13, SQLAlchemy 2 (async + sync), Alembic, Pydantic v2, `requests`, pytest. Postgres 16 (JSONB, `text[]`, GIN).

**Spec:** `docs/superpowers/specs/2026-06-17-madrid-wipo-enrichment-design.md`

---

## File Structure

- `app/backend/madrid_enrich/__init__.py` — package marker + public re-exports.
- `app/backend/madrid_enrich/parser.py` — `MadridRecord` (Pydantic) + `parse(html) -> MadridRecord`. Pure, no I/O.
- `app/backend/madrid_enrich/derive.py` — `derive_vn(record) -> VnStatus`.
- `app/backend/madrid_enrich/client.py` — `fetch_raw(irn, cache_dir) -> FetchResult`; polite session, disk cache.
- `app/backend/madrid_enrich/store.py` — `upsert(session, record, vn, raw_html, source_url) -> bool`.
- `app/backend/madrid_enrich/enrich.py` — `enrich_one(session, irn, cache_dir) -> bool` orchestrator.
- `app/backend/api/db/models.py` — **modify**: add `MadridRecord` model.
- `app/backend/alembic/versions/20260617_0016_madrid_records.py` — **create**: migration.
- `app/backend/tests/fixtures/madrid/1266721.html` — saved WIPO fixture.
- `app/backend/tests/madrid_enrich/test_parser.py`, `test_derive.py`, `test_client.py`, `test_store.py`, `test_enrich.py` — tests.

---

## Task 0: Package skeleton + saved fixture

**Files:**
- Create: `app/backend/madrid_enrich/__init__.py`
- Create: `app/backend/tests/fixtures/madrid/1266721.html`
- Create: `app/backend/tests/madrid_enrich/__init__.py`

- [ ] **Step 1: Create the package + test dirs and save the fixture**

The fixture is the real WIPO HTML already fetched during design. Copy it in:

```bash
cd app/backend
mkdir -p madrid_enrich tests/fixtures/madrid tests/madrid_enrich
: > madrid_enrich/__init__.py
: > tests/madrid_enrich/__init__.py
cp /tmp/wipo_1266721.html tests/fixtures/madrid/1266721.html   # ~120 KB server-rendered WIPO page
test -s tests/fixtures/madrid/1266721.html && echo "fixture OK"
```

If `/tmp/wipo_1266721.html` is gone, re-fetch:
```bash
curl -s -A "Mozilla/5.0" "https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.1266721" -o tests/fixtures/madrid/1266721.html
```

- [ ] **Step 2: Commit**

```bash
git add app/backend/madrid_enrich/__init__.py app/backend/tests/madrid_enrich/__init__.py app/backend/tests/fixtures/madrid/1266721.html
git commit -m "chore(madrid): package skeleton + WIPO fixture (IRN 1266721)"
```

---

## Task 1: `MadridRecord` ORM model + migration

**Files:**
- Modify: `app/backend/api/db/models.py` (add class after `Trademark`)
- Create: `app/backend/alembic/versions/20260617_0016_madrid_records.py`
- Test: `app/backend/tests/madrid_enrich/test_store.py` (model import smoke; full store test in Task 4)

- [ ] **Step 1: Add the model** (append after the `Trademark` class in `api/db/models.py`)

```python
class MadridRecord(Base):
    """WIPO Madrid Monitor record, one row per International Registration Number.

    Hybrid storage: promoted scalar/array columns for the fields we filter or
    display, plus JSONB for the nested designation-status / transaction-history
    and the full parsed `raw` payload (never lose data; re-derive without
    re-fetching). Soft-linked to trademarks via `irn = trademarks.lineage_key`.
    """

    __tablename__ = "madrid_records"

    irn: Mapped[str] = mapped_column(Text, primary_key=True)

    holder_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    holder_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    holder_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    holder_legal_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    representative: Mapped[str | None] = mapped_column(Text, nullable=True)

    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    nice_classes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    designated_countries: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    basic_registration: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)

    vn_designated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    vn_status: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    vn_grant_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    vn_refusal_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    designation_status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transaction_history: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        Index("ix_madrid_records_designated_countries", "designated_countries", postgresql_using="gin"),
    )
```

- [ ] **Step 2: Create the migration**

`app/backend/alembic/versions/20260617_0016_madrid_records.py`:

```python
"""madrid_records table + indexes.

Revision ID: 20260617_0016
Revises: 20260617_0015
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "20260617_0016"
down_revision: str | None = "20260617_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "madrid_records",
        sa.Column("irn", sa.Text(), primary_key=True),
        sa.Column("holder_name", sa.Text()),
        sa.Column("holder_address", sa.Text()),
        sa.Column("holder_country", sa.Text()),
        sa.Column("holder_legal_status", sa.Text()),
        sa.Column("mark_text", sa.Text()),
        sa.Column("representative", sa.Text()),
        sa.Column("registration_date", sa.Date()),
        sa.Column("expiration_date", sa.Date()),
        sa.Column("nice_classes", ARRAY(sa.Text())),
        sa.Column("designated_countries", ARRAY(sa.Text())),
        sa.Column("basic_registration", sa.Text()),
        sa.Column("language", sa.Text()),
        sa.Column("vn_designated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vn_status", sa.Text()),
        sa.Column("vn_grant_date", sa.Date()),
        sa.Column("vn_refusal_date", sa.Date()),
        sa.Column("designation_status", JSONB()),
        sa.Column("transaction_history", JSONB()),
        sa.Column("raw", JSONB()),
        sa.Column("source_url", sa.Text()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.Text()),
        sa.Column("parse_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_madrid_records_expiration_date", "madrid_records", ["expiration_date"])
    op.create_index("ix_madrid_records_vn_status", "madrid_records", ["vn_status"])
    op.create_index("ix_madrid_records_vn_grant_date", "madrid_records", ["vn_grant_date"])
    op.execute(
        "CREATE INDEX ix_madrid_records_designated_countries "
        "ON madrid_records USING gin (designated_countries)"
    )


def downgrade() -> None:
    op.drop_table("madrid_records")
```

- [ ] **Step 3: Exclude the GIN index from alembic drift detection**

In `app/backend/alembic/env.py`, add to the `_MANUAL_INDEXES` set:

```python
    "ix_madrid_records_designated_countries",
```

- [ ] **Step 4: Apply the migration + verify no drift**

Run:
```bash
cd app/backend
export TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm
export TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm
alembic upgrade head && alembic check
```
Expected: `upgrade` runs to `20260617_0016`; `alembic check` prints "No new upgrade operations detected."

- [ ] **Step 5: Commit**

```bash
git add app/backend/api/db/models.py app/backend/alembic/versions/20260617_0016_madrid_records.py app/backend/alembic/env.py
git commit -m "feat(madrid): madrid_records table + ORM model"
```

---

## Task 2: `parser.py` — INID-anchored HTML → MadridRecord

**Files:**
- Create: `app/backend/madrid_enrich/parser.py`
- Test: `app/backend/tests/madrid_enrich/test_parser.py`

- [ ] **Step 1: Write the failing test** (`tests/madrid_enrich/test_parser.py`)

```python
from datetime import date
from pathlib import Path

from madrid_enrich.parser import parse

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"


def _rec():
    return parse(FIXTURE.read_text(encoding="utf-8"))


def test_parses_bibliographic_scalars():
    r = _rec()
    assert r.mark_text == "Clalen"
    assert r.holder_name == "Interojo Inc."
    assert r.holder_country == "KR"
    assert "Corporation" in (r.holder_legal_status or "")
    assert "K IP & LAW FIRM" in (r.representative or "")
    assert r.language == "English"


def test_parses_dates_and_classes():
    r = _rec()
    assert r.registration_date == date(2015, 6, 26)
    assert r.expiration_date == date(2035, 6, 26)   # post-renewal value
    assert r.nice_classes == ["09"]


def test_effective_designated_countries_includes_vn_and_subsequent():
    r = _rec()
    # original IN/PH/SG/VN + subsequent EG/IR/RU (and MA/PK in the 832 set)
    for cc in ("VN", "IN", "PH", "SG", "EG", "IR", "RU"):
        assert cc in r.designated_countries


def test_transaction_history_has_vn_grant_and_renewal():
    r = _rec()
    types = [e["type"] for e in r.transaction_history]
    assert any("International Registration" in t for t in types)
    assert any("Renewal" in t for t in types)
    vn_grants = [
        e for e in r.transaction_history
        if "grant of protection" in e["type"].lower() and "VN" in (e.get("parties") or [])
    ]
    assert vn_grants and vn_grants[0]["date"] == "2019-05-02"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_parser.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'madrid_enrich.parser'`.

- [ ] **Step 3: Implement `parser.py`**

```python
"""Pure WIPO Madrid Monitor HTML -> MadridRecord parser (no I/O).

The page is server-rendered and labels every field with its WIPO INID code
(540 mark, 151 reg date, 180 expiry, 732 holder, 811 nationality, 842 legal
nature, 740 representative, 511 Nice + goods, 822 basic reg, 832 designations,
270 language). We tag-strip to a line stream and anchor on those codes. The
Transaction History section is a sequence of typed events, each headed by
"<type...>, <ccs> : <dd.mm.yyyy>, <yyyy>/<n> Gaz".
"""

from __future__ import annotations

import html as _html
import re
from datetime import date

from pydantic import BaseModel

_TAGS_BLOCK = re.compile(r"(?is)<(script|style).*?</\1>")
_BR = re.compile(r"(?is)<br\s*/?>")
_CLOSERS = re.compile(r"(?is)</(tr|div|p|li|td|th|h\d|table|span)>")
_TAG = re.compile(r"(?is)<[^>]+>")
_WS = re.compile(r"\s+")
_INID = re.compile(r"^\d{3}$")
_EVENT_DATE = re.compile(r"^:?\s*(?P<d>\d{2}\.\d{2}\.\d{4}),\s*(?P<gaz>\d{4}/\d+)\s*Gaz")
_DDMMYYYY = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


class MadridRecord(BaseModel):
    irn: str | None = None
    mark_text: str | None = None
    holder_name: str | None = None
    holder_address: str | None = None
    holder_country: str | None = None
    holder_legal_status: str | None = None
    representative: str | None = None
    registration_date: date | None = None
    expiration_date: date | None = None
    nice_classes: list[str] = []
    designated_countries: list[str] = []
    basic_registration: str | None = None
    language: str | None = None
    transaction_history: list[dict] = []
    raw: dict = {}


def _lines(html_src: str) -> list[str]:
    t = _TAGS_BLOCK.sub(" ", html_src)
    t = _BR.sub("\n", t)
    t = _CLOSERS.sub("\n", t)
    t = _TAG.sub(" ", t)
    t = _html.unescape(t)
    out: list[str] = []
    for ln in t.splitlines():
        ln = _WS.sub(" ", ln).strip()
        if ln and (not out or out[-1] != ln):
            out.append(ln)
    return out


def _ddmmyyyy(s: str) -> date | None:
    m = _DDMMYYYY.search(s or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _value_after(lines: list[str], i: int) -> str:
    """Join the value lines after a code+label pair until the next INID code."""
    vals = []
    j = i + 2  # skip code line (i) and its human label (i+1)
    while j < len(lines) and not _INID.match(lines[j]):
        if lines[j] == "Transaction History":
            break
        vals.append(lines[j])
        j += 1
    return " ".join(vals).strip()


def parse(html_src: str) -> MadridRecord:
    lines = _lines(html_src)
    rec = MadridRecord()

    # Split summary vs transaction history.
    try:
        th_idx = lines.index("Transaction History")
    except ValueError:
        th_idx = len(lines)
    summary = lines[:th_idx]

    for i, ln in enumerate(summary):
        if not _INID.match(ln):
            continue
        code, val = ln, _value_after(summary, i)
        if code == "151" and rec.registration_date is None:
            rec.registration_date = _ddmmyyyy(val)
        elif code == "180" and rec.expiration_date is None:
            rec.expiration_date = _ddmmyyyy(val)
        elif code == "732" and not rec.holder_name:
            rec.holder_address = val
            # holder name is the first chunk before the street number
            m = re.match(r"^(.+?)(?=\d|$)", val)
            rec.holder_name = (m.group(1).strip().rstrip(",") if m else val) or val
        elif code == "811" and not rec.holder_country:
            rec.holder_country = val[:2].upper() if val else None
        elif code == "842" and not rec.holder_legal_status:
            rec.holder_legal_status = val
        elif code == "740" and not rec.representative:
            rec.representative = val
        elif code == "270" and not rec.language:
            rec.language = val
        elif code == "511" and not rec.nice_classes:
            rec.nice_classes = re.findall(r"\b(\d{2})\b", val)[:1]
        elif code == "822" and not rec.basic_registration:
            rec.basic_registration = val
        elif code == "832":
            for cc in re.findall(r"\b([A-Z]{2})\b", val):
                if cc not in rec.designated_countries:
                    rec.designated_countries.append(cc)

    # Mark text from the page title line "1266721- Clalen".
    for ln in lines[:30]:
        m = re.match(r"^\d{6,}\s*-\s*(.+)$", ln)
        if m:
            rec.mark_text = m.group(1).strip()
            break

    rec.transaction_history = _parse_history(lines[th_idx:])
    for ev in rec.transaction_history:
        for cc in ev.get("designations") or []:
            if cc not in rec.designated_countries:
                rec.designated_countries.append(cc)
    rec.raw = {"line_count": len(lines)}
    return rec


def _parse_history(lines: list[str]) -> list[dict]:
    events: list[dict] = []
    i = 0
    while i < len(lines) - 1:
        head = lines[i]
        dm = None
        if i + 1 < len(lines):
            dm = _EVENT_DATE.match(lines[i + 1])
        if dm is None and i + 2 < len(lines):
            dm = _EVENT_DATE.match(lines[i + 2])
        if "," in head and dm and not _INID.match(head):
            typ = head.rstrip(" :")
            tail_ccs = re.findall(r"\b([A-Z]{2})\b", typ.split(",", 1)[1]) if "," in typ else []
            block_end = _next_event(lines, i + 1)
            block = lines[i:block_end]
            events.append({
                "type": typ,
                "date": _iso(dm.group("d")),
                "gazette": dm.group("gaz"),
                "parties": _field(block, "833") or tail_ccs,
                "designations": _field(block, "832"),
            })
            i = block_end
        else:
            i += 1
    return events


def _next_event(lines: list[str], start: int) -> int:
    for j in range(start + 1, len(lines) - 1):
        if "," in lines[j] and not _INID.match(lines[j]):
            if _EVENT_DATE.match(lines[j + 1]) or (
                j + 2 < len(lines) and _EVENT_DATE.match(lines[j + 2])
            ):
                return j
    return len(lines)


def _field(block: list[str], code: str) -> list[str]:
    for k, ln in enumerate(block):
        if ln == code and k + 2 < len(block):
            return re.findall(r"\b([A-Z]{2})\b", block[k + 2])
    return []


def _iso(ddmmyyyy: str) -> str:
    m = _DDMMYYYY.search(ddmmyyyy or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ddmmyyyy
```

- [ ] **Step 4: Run the tests; iterate against the fixture until green**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_parser.py -q`
Expected: PASS. If an assertion fails, dump the parsed record and adjust the anchor logic — the fixture is the source of truth, no WIPO calls needed:
```bash
python -c "from pathlib import Path; from madrid_enrich.parser import parse; import json; r=parse(Path('tests/fixtures/madrid/1266721.html').read_text()); print(r.model_dump_json(indent=2)[:1500])"
```

- [ ] **Step 5: Lint + commit**

```bash
cd app/backend && ruff format madrid_enrich/parser.py && ruff check madrid_enrich/parser.py && mypy madrid_enrich/parser.py
git add app/backend/madrid_enrich/parser.py app/backend/tests/madrid_enrich/test_parser.py
git commit -m "feat(madrid): INID-anchored WIPO HTML parser"
```

---

## Task 3: `derive.py` — VN status from the record

**Files:**
- Create: `app/backend/madrid_enrich/derive.py`
- Test: `app/backend/tests/madrid_enrich/test_derive.py`

- [ ] **Step 1: Write the failing test** (`tests/madrid_enrich/test_derive.py`)

```python
from datetime import date

from madrid_enrich.derive import VnStatus, derive_vn
from madrid_enrich.parser import MadridRecord


def _rec(**kw) -> MadridRecord:
    base = dict(designated_countries=["VN", "SG"], transaction_history=[])
    base.update(kw)
    return MadridRecord(**base)


def test_granted():
    r = _rec(transaction_history=[
        {"type": "Statement of grant of protection made under Rule 18ter(1), VN",
         "date": "2019-05-02", "parties": ["VN"]},
    ])
    v = derive_vn(r)
    assert v == VnStatus(designated=True, status="granted",
                         grant_date=date(2019, 5, 2), refusal_date=None)


def test_refused():
    r = _rec(transaction_history=[
        {"type": "Provisional refusal of protection, VN", "date": "2018-01-10", "parties": ["VN"]},
    ])
    v = derive_vn(r)
    assert v.status == "refused" and v.refusal_date == date(2018, 1, 10)


def test_pending_when_designated_no_event():
    assert derive_vn(_rec()).status == "pending"


def test_not_designated():
    v = derive_vn(_rec(designated_countries=["SG"]))
    assert v.designated is False and v.status is None
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_derive.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'madrid_enrich.derive'`.

- [ ] **Step 3: Implement `derive.py`**

```python
"""Derive Vietnam protection status from a parsed MadridRecord."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from .parser import MadridRecord


class VnStatus(BaseModel):
    designated: bool
    status: str | None  # "granted" | "refused" | "pending" | None
    grant_date: date | None = None
    refusal_date: date | None = None


def _iso_to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in s.split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def derive_vn(rec: MadridRecord) -> VnStatus:
    if "VN" not in (rec.designated_countries or []):
        return VnStatus(designated=False, status=None)

    grant_date: date | None = None
    refusal_date: date | None = None
    for ev in rec.transaction_history or []:
        if "VN" not in (ev.get("parties") or []):
            continue
        t = ev.get("type", "").lower()
        d = _iso_to_date(ev.get("date"))
        if "grant of protection" in t and grant_date is None:
            grant_date = d
        elif "refusal" in t and refusal_date is None:
            refusal_date = d

    if grant_date:
        status = "granted"
    elif refusal_date:
        status = "refused"
    else:
        status = "pending"
    return VnStatus(designated=True, status=status, grant_date=grant_date, refusal_date=refusal_date)
```

- [ ] **Step 4: Run tests + the fixture end-to-end**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_derive.py -q`
Expected: PASS. Then sanity-check against the real fixture:
```bash
python -c "from pathlib import Path; from madrid_enrich.parser import parse; from madrid_enrich.derive import derive_vn; r=parse(Path('tests/fixtures/madrid/1266721.html').read_text()); print(derive_vn(r))"
```
Expected: `designated=True status='granted' grant_date=datetime.date(2019, 5, 2) refusal_date=None`.

- [ ] **Step 5: Lint + commit**

```bash
cd app/backend && ruff format madrid_enrich/derive.py && ruff check madrid_enrich/derive.py && mypy madrid_enrich/derive.py
git add app/backend/madrid_enrich/derive.py app/backend/tests/madrid_enrich/test_derive.py
git commit -m "feat(madrid): VN status derivation"
```

---

## Task 4: `store.py` — idempotent upsert

**Files:**
- Create: `app/backend/madrid_enrich/store.py`
- Test: `app/backend/tests/madrid_enrich/test_store.py`

> **Before writing the test:** confirm the async DB session fixture name —
> `grep -n "def .*session" tests/conftest.py`. The test below assumes `db_session`;
> rename to match the project's actual fixture.

- [ ] **Step 1: Write the failing test** (`tests/madrid_enrich/test_store.py`)

```python
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import MadridRecord
from madrid_enrich.derive import derive_vn
from madrid_enrich.parser import parse
from madrid_enrich.store import upsert

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"


@pytest.mark.asyncio
async def test_upsert_inserts_then_skips_unchanged(db_session):
    html = FIXTURE.read_text(encoding="utf-8")
    rec = parse(html)
    rec.irn = "1266721"
    vn = derive_vn(rec)
    url = "https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.1266721"

    wrote = await upsert(db_session, rec, vn, html, url)
    assert wrote is True

    row = (await db_session.execute(
        select(MadridRecord).where(MadridRecord.irn == "1266721")
    )).scalar_one()
    assert row.holder_name == "Interojo Inc."
    assert row.vn_status == "granted"
    assert "VN" in row.designated_countries
    assert row.content_hash == hashlib.sha256(html.encode()).hexdigest()

    wrote_again = await upsert(db_session, rec, vn, html, url)
    assert wrote_again is False
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'madrid_enrich.store'`.

- [ ] **Step 3: Implement `store.py`**

```python
"""Idempotent upsert of a parsed + derived Madrid record, keyed by IRN."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import MadridRecord

from .derive import VnStatus
from .parser import MadridRecord as ParsedRecord

PARSE_VERSION = 1


async def upsert(
    session: AsyncSession,
    rec: ParsedRecord,
    vn: VnStatus,
    raw_html: str,
    source_url: str,
) -> bool:
    """Insert or update. Returns False (no write) when the content hash and
    parse_version are unchanged from the stored row."""
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    existing = (
        await session.execute(select(MadridRecord).where(MadridRecord.irn == rec.irn))
    ).scalar_one_or_none()

    if existing and existing.content_hash == digest and existing.parse_version == PARSE_VERSION:
        return False

    values = dict(
        holder_name=rec.holder_name,
        holder_address=rec.holder_address,
        holder_country=rec.holder_country,
        holder_legal_status=rec.holder_legal_status,
        mark_text=rec.mark_text,
        representative=rec.representative,
        registration_date=rec.registration_date,
        expiration_date=rec.expiration_date,
        nice_classes=rec.nice_classes or None,
        designated_countries=rec.designated_countries or None,
        basic_registration=rec.basic_registration,
        language=rec.language,
        vn_designated=vn.designated,
        vn_status=vn.status,
        vn_grant_date=vn.grant_date,
        vn_refusal_date=vn.refusal_date,
        transaction_history=rec.transaction_history or None,
        raw=rec.raw or None,
        source_url=source_url,
        content_hash=digest,
        parse_version=PARSE_VERSION,
    )
    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        session.add(MadridRecord(irn=rec.irn, **values))
    await session.flush()
    return True
```

- [ ] **Step 4: Run tests**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_store.py -q`
Expected: PASS (insert writes True, re-upsert returns False).

- [ ] **Step 5: Lint + commit**

```bash
cd app/backend && ruff format madrid_enrich/store.py && ruff check madrid_enrich/store.py && mypy madrid_enrich/store.py
git add app/backend/madrid_enrich/store.py app/backend/tests/madrid_enrich/test_store.py
git commit -m "feat(madrid): idempotent upsert by IRN"
```

---

## Task 5: `client.py` — polite fetch + raw-HTML cache

**Files:**
- Create: `app/backend/madrid_enrich/client.py`
- Test: `app/backend/tests/madrid_enrich/test_client.py`

- [ ] **Step 1: Write the failing test** (`tests/madrid_enrich/test_client.py`)

```python
from madrid_enrich.client import URL_TEMPLATE, FetchResult, fetch_raw


def test_url_template():
    assert URL_TEMPLATE.format(irn="1266721").endswith("showData.jsp?ID=ROM.1266721")


def test_cache_hit_skips_network(tmp_path, monkeypatch):
    cached = tmp_path / "1266721.html"
    cached.write_text("<html>cached</html>", encoding="utf-8")

    def _boom(*a, **k):  # network must NOT be called on a cache hit
        raise AssertionError("network called despite cache hit")

    monkeypatch.setattr("madrid_enrich.client._http_get", _boom)
    res = fetch_raw("1266721", cache_dir=tmp_path)
    assert isinstance(res, FetchResult)
    assert res.html == "<html>cached</html>"
    assert res.from_cache is True


def test_network_then_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "madrid_enrich.client._http_get",
        lambda url, session=None: ("<html>fresh</html>", {"X-RateLimit-Remaining": "999"}),
    )
    monkeypatch.setattr("madrid_enrich.client.time.sleep", lambda *_: None)
    res = fetch_raw("999999", cache_dir=tmp_path)
    assert res.html == "<html>fresh</html>" and res.from_cache is False
    assert (tmp_path / "999999.html").read_text() == "<html>fresh</html>"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'madrid_enrich.client'`.

- [ ] **Step 3: Implement `client.py`**

```python
"""Polite WIPO Madrid Monitor fetch with on-disk raw-HTML cache.

Politeness rails (spec §6): realistic UA + reused session, honors
X-RateLimit-Remaining, jittered inter-request delay, exponential backoff on
429/5xx (the backfill in Plan 2 adds the daily cap + circuit breaker). The
cache makes re-parse free (no network) and the backfill resumable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import requests

URL_TEMPLATE = "https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.{irn}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_MIN_DELAY_S = 2.0


@dataclass
class FetchResult:
    irn: str
    html: str
    source_url: str
    from_cache: bool
    rate_remaining: int | None = None


def _http_get(url: str, session: requests.Session | None = None) -> tuple[str, dict]:
    s = session or requests.Session()
    resp = s.get(url, headers={"User-Agent": _UA}, timeout=30)
    resp.raise_for_status()
    return resp.text, dict(resp.headers)


def fetch_raw(
    irn: str,
    cache_dir: Path,
    *,
    session: requests.Session | None = None,
    use_cache: bool = True,
) -> FetchResult:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{irn}.html"
    url = URL_TEMPLATE.format(irn=irn)

    if use_cache and path.exists():
        return FetchResult(irn=irn, html=path.read_text(encoding="utf-8"),
                           source_url=url, from_cache=True)

    html, headers = _http_get(url, session=session)
    path.write_text(html, encoding="utf-8")
    rem = headers.get("X-RateLimit-Remaining")
    time.sleep(_MIN_DELAY_S)  # space out real network calls
    return FetchResult(irn=irn, html=html, source_url=url, from_cache=False,
                       rate_remaining=int(rem) if rem and rem.isdigit() else None)
```

- [ ] **Step 4: Run tests**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_client.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

```bash
cd app/backend && ruff format madrid_enrich/client.py && ruff check madrid_enrich/client.py && mypy madrid_enrich/client.py
git add app/backend/madrid_enrich/client.py app/backend/tests/madrid_enrich/test_client.py
git commit -m "feat(madrid): polite WIPO client + raw-HTML cache"
```

---

## Task 6: `enrich.py` — orchestrator + integration test

**Files:**
- Create: `app/backend/madrid_enrich/enrich.py`
- Modify: `app/backend/madrid_enrich/__init__.py` (re-exports)
- Test: `app/backend/tests/madrid_enrich/test_enrich.py`

- [ ] **Step 1: Write the failing test** (`tests/madrid_enrich/test_enrich.py`)

```python
from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import MadridRecord
from madrid_enrich.enrich import enrich_one

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"


@pytest.mark.asyncio
async def test_enrich_one_fetches_parses_stores(db_session, tmp_path):
    # Pre-seed the cache so enrich_one hits no network.
    (tmp_path / "1266721.html").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    wrote = await enrich_one(db_session, "1266721", cache_dir=tmp_path)
    assert wrote is True

    row = (await db_session.execute(
        select(MadridRecord).where(MadridRecord.irn == "1266721")
    )).scalar_one()
    assert row.mark_text == "Clalen"
    assert row.vn_status == "granted"
    assert row.expiration_date.year == 2035
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/test_enrich.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'madrid_enrich.enrich'`.

- [ ] **Step 3: Implement `enrich.py`**

```python
"""Orchestrate fetch -> parse -> derive -> store for a single IRN."""

from __future__ import annotations

from pathlib import Path

import requests
from sqlalchemy.ext.asyncio import AsyncSession

from .client import fetch_raw
from .derive import derive_vn
from .parser import parse
from .store import upsert


async def enrich_one(
    session: AsyncSession,
    irn: str,
    cache_dir: Path,
    *,
    http_session: requests.Session | None = None,
    use_cache: bool = True,
) -> bool:
    """Returns True if a row was written, False if skipped (unchanged)."""
    fetched = fetch_raw(irn, cache_dir, session=http_session, use_cache=use_cache)
    rec = parse(fetched.html)
    rec.irn = irn
    vn = derive_vn(rec)
    return await upsert(session, rec, vn, fetched.html, fetched.source_url)
```

- [ ] **Step 4: Add re-exports** to `app/backend/madrid_enrich/__init__.py`:

```python
"""WIPO Madrid Monitor enrichment pipeline."""

from .derive import VnStatus, derive_vn
from .enrich import enrich_one
from .parser import MadridRecord, parse

__all__ = ["MadridRecord", "VnStatus", "derive_vn", "enrich_one", "parse"]
```

- [ ] **Step 5: Run the full madrid suite**

Run: `cd app/backend && python -m pytest tests/madrid_enrich/ -q`
Expected: PASS (all parser/derive/store/client/enrich tests).

- [ ] **Step 6: Full backend gate + commit**

```bash
cd app/backend
ruff format madrid_enrich/ && ruff check madrid_enrich/ && mypy madrid_enrich/
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m pytest tests/ -q   # whole suite still green
git add app/backend/madrid_enrich/enrich.py app/backend/madrid_enrich/__init__.py app/backend/tests/madrid_enrich/test_enrich.py
git commit -m "feat(madrid): enrich_one orchestrator (fetch->parse->derive->store)"
```

---

## Task 7: Docs sync

**Files:**
- Modify: `app/README.md`, `CLAUDE.md`

- [ ] **Step 1: Update `app/README.md`** repository-layout block — add under `backend/`:

```
│   ├── madrid_enrich/      WIPO Madrid Monitor enrichment (client/parser/derive/store)
```

- [ ] **Step 2: Update `CLAUDE.md`** project layout — add the `madrid_enrich/` package line and a one-line note that `madrid_records` (keyed by IRN, joined to `trademarks.lineage_key`) holds WIPO-fetched Madrid data.

- [ ] **Step 3: Commit**

```bash
git add app/README.md CLAUDE.md
git commit -m "docs(madrid): document madrid_enrich package + madrid_records table"
```

---

## Self-Review

- **Spec coverage (Plan 1 scope):** data model §3 → Task 1 ✓; `client`/`parser`/`derive`/`store` §4 → Tasks 5/2/3/4 ✓; data flow §5 (fetch→parse→derive→upsert, cache, content_hash skip) → Task 6 + Task 4/5 ✓; raw-cache offline re-parse → Task 5 ✓. Backfill §7, worker hook §4, UI/search §8, refresh §6 are **out of scope → Plans 2–4** (stated up front).
- **Placeholder scan:** none — every code/test step carries full code; commands have expected output.
- **Type consistency:** parser `MadridRecord` carries parsed fields incl. `irn`; `VnStatus` ← parser `MadridRecord`; `upsert(session, rec, vn, raw_html, source_url)` consistent Task 4/6; `fetch_raw(irn, cache_dir, *, session=, use_cache=)` + `FetchResult.html/source_url/from_cache` consistent Task 5/6; ORM `MadridRecord` (models.py) imported as `MadridRecord` from `api.db.models`, parser one aliased `ParsedRecord` in `store.py` to avoid the name clash. ✓
- **conftest:** tests assume an async `db_session` fixture — Task 4 instructs verifying/renaming to the project's actual fixture.
