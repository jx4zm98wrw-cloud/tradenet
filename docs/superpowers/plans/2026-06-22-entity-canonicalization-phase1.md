# Entity Canonicalization — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/admin/gazettes` dashboard's applicant + representative metrics **exact** by reading the authoritative WIPO/NOIP names already in the DB (joined by each mark's deterministic identifier) and grouping by a trivial normalizer — then drop the now-untrue `approximate` flag.

**Architecture:** Every mark already carries a deterministic key to its trusted record (`trademarks.application_number → domestic_records`, `trademarks.lineage_key (=IRN) → madrid_records`). The clean name is a join away. A tiny `norm()` helper forms a **grouping key only** (NFC → casefold → collapse whitespace → trim) so case/whitespace variants of the *same trusted name* collapse — it never merges distinct names. WIPO representatives have a glued trailing address, cut deterministically at the first comma/digit before norming. No fuzzy matching, no new tables, no migration.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (async) + Postgres on the backend; Next.js 15 + React + TypeScript on the frontend. Tests: pytest + httpx ASGI. Spec: [`docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`](../specs/2026-06-22-entity-canonicalization-design.md).

---

## Standing constraints (read before every commit)

- **NEVER** `git add -A` / `git add .`. Stage by explicit path. The rename trio **`README.md`, `app/.env.example`, `app/backend/api/settings.py`** is dirty in the working tree from prior work and MUST NOT be committed by this plan.
- Run backend commands from `app/backend/` with the venv active (`source app/.venv/bin/activate`).
- Backend CI gates (all must pass): `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. Phase 1 has **no migration**, so `alembic check` must report no new operations.
- Frontend: `npx tsc --noEmit && pnpm lint`. **NEVER** `pnpm build` while a `pnpm dev` server is live (clobbers `.next`).
- Run **targeted** pytest files only (sweep tests reset the live `domestic_sweep_control` singleton).
- Ship as **two PRs**: PR 1 = backend (Tasks 1–4), PR 2 = frontend hint removal (Task 5). Branch both off `main`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/backend/api/_entity_norm.py` | **Create** | Pure helpers: `norm()` grouping key + `strip_madrid_rep_address()` deterministic address cut. ~25 lines, stdlib only. |
| `app/backend/tests/test_entity_norm.py` | **Create** | Unit tests for `norm()` and `strip_madrid_rep_address()`. |
| `app/backend/api/routes/gazettes.py` | **Modify** | Rewire the 4 applicant/representative aggregations in `gazette_overview` to read the trusted source + `GROUP BY norm`; delete the interim `_normalize_rep`/`_trim_madrid_rep` helpers; drop `approximate=True`. |
| `app/backend/api/schemas.py` | **Modify** | Remove the `approximate` field from `TopRepresentatives`. |
| `app/backend/tests/test_gazettes_overview.py` | **Modify** | Seed `domestic_records` variants; replace the approximate-flag test; add the hand-computed norm-grouping + distinctness tests. |
| `app/frontend/lib/api.ts` | **Modify** | Drop `approximate` from the `TopRepresentatives` type. |
| `app/frontend/components/admin/gazettes-dashboard.tsx` | **Modify** | Remove the `approximate` prop + the "approximate · names not yet fully canonicalized" hint and the now-unused `Pill` import if unused. |

---

## Task 1: `norm()` + `strip_madrid_rep_address()` helper (TDD)

**Files:**
- Create: `app/backend/api/_entity_norm.py`
- Test: `app/backend/tests/test_entity_norm.py`

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_entity_norm.py`:

```python
"""Unit tests for the entity grouping-key helpers (Phase 1)."""

from __future__ import annotations

import unicodedata

from api._entity_norm import norm, strip_madrid_rep_address


def test_norm_collapses_case() -> None:
    assert norm("CÔNG TY LUẬT TAGA") == norm("Công ty Luật TAGA")


def test_norm_collapses_internal_whitespace() -> None:
    assert norm("Công  ty   Luật\tTAGA") == norm("Công ty Luật TAGA")


def test_norm_trims_outer_whitespace() -> None:
    assert norm("   ACME Co.  ") == "acme co."


def test_norm_nfc_normalizes_diacritics() -> None:
    # Same name as NFC (precomposed) vs NFD (decomposed base + combining accent).
    base = "L'Oréal"
    nfc = unicodedata.normalize("NFC", base)
    nfd = unicodedata.normalize("NFD", base)
    assert nfc != nfd  # different byte sequences...
    assert norm(nfc) == norm(nfd)  # ...but the same grouping key


def test_norm_keeps_distinct_names_distinct() -> None:
    # Trivial-variant collapse must NEVER merge two genuinely different firms.
    assert norm("Distinct Firm XYZ") != norm("Distinct Firm ABC")
    assert norm("Pham & Associates") != norm("Pham Associates")


def test_strip_madrid_rep_cuts_at_first_digit() -> None:
    # WIPO glues the firm name to its postal address; cut at the first digit run.
    assert strip_madrid_rep_address("OVW REP ALPHA 123 Main St, Zürich").strip() == "OVW REP ALPHA"


def test_strip_madrid_rep_cuts_at_first_comma() -> None:
    assert strip_madrid_rep_address("Smith & Partners, 5 High Road").strip() == "Smith & Partners"


def test_strip_madrid_rep_no_address_unchanged() -> None:
    assert strip_madrid_rep_address("Plain Firm Name").strip() == "Plain Firm Name"


def test_madrid_rep_address_variants_group_together() -> None:
    a = norm(strip_madrid_rep_address("OVW REP ALPHA 123 Main St, Zürich"))
    b = norm(strip_madrid_rep_address("OVW REP ALPHA 456 Other Rd, Bern"))
    assert a == b
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd app/backend && pytest tests/test_entity_norm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api._entity_norm'`.

- [ ] **Step 3: Write the implementation**

Create `app/backend/api/_entity_norm.py`:

```python
"""Entity-name grouping helpers (Phase 1 of entity canonicalization).

These form a *grouping key* so case/whitespace variants of the SAME trusted
WIPO/NOIP name collapse into one bucket for the dashboard's "top entities"
counts. They are deliberately NOT fuzzy matching — `norm()` never merges two
genuinely different names. See
docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md.
"""

from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")
# WIPO `representative` concatenates the firm name with its postal address.
# The address always begins at the first comma or digit-run; cut there. This is
# a deterministic boundary, not a fuzzy guess.
_MADRID_ADDR_RE = re.compile(r"[,]|\d")


def norm(s: str) -> str:
    """Grouping key: NFC-normalize → casefold → collapse internal whitespace → trim.

    Collapses trivial case/whitespace/diacritic-encoding variants of one name so
    they count as a single entity. It MUST NOT merge distinct names — it is not
    fuzzy matching.
    """
    s = unicodedata.normalize("NFC", s)
    s = s.casefold()
    s = _WS_RE.sub(" ", s)
    return s.strip()


def strip_madrid_rep_address(s: str) -> str:
    """Deterministically drop a WIPO representative's trailing glued address.

    Takes the text up to the first comma or digit-run. Apply BEFORE `norm()` so
    address-only differences (same firm, different office address) collapse.
    Returns the head verbatim (not normalized) so the caller can keep the raw
    firm spelling for display.
    """
    return _MADRID_ADDR_RE.split(s, maxsplit=1)[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd app/backend && pytest tests/test_entity_norm.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Lint + type-check the new module**

Run: `cd app/backend && ruff check api/_entity_norm.py tests/test_entity_norm.py && ruff format --check api/_entity_norm.py tests/test_entity_norm.py && mypy api`
Expected: all clean. (Run `ruff format api/_entity_norm.py tests/test_entity_norm.py` first if `--check` complains.)

- [ ] **Step 6: Commit**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/api/_entity_norm.py app/backend/tests/test_entity_norm.py
git commit -m "feat(entity-norm): add norm() grouping-key + madrid address-strip helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Rewire the four `/overview` aggregations + drop `approximate`

**Files:**
- Modify: `app/backend/api/routes/gazettes.py`
- Modify: `app/backend/api/schemas.py:108-114`

This task changes production code; its behavior is verified by Task 3's tests. Run Task 3's tests after this task to confirm green.

- [ ] **Step 1: Remove the `approximate` field from the schema**

In `app/backend/api/schemas.py`, replace the `TopRepresentatives` class (currently lines 108-114):

```python
class TopRepresentatives(BaseModel):
    domestic: list[NamedCount]
    madrid: list[NamedCount]
    # Interim metric — names are only prefix-stripped / address-trimmed, not
    # fully canonicalized (same firm still fragments into variants). Full
    # canonicalization is tracked in task_057fcd61.
    approximate: bool = True
```

with:

```python
class TopRepresentatives(BaseModel):
    # Counts are exact: names come from the trusted WIPO/NOIP source joined by
    # each mark's deterministic identifier, grouped by api._entity_norm.norm.
    domestic: list[NamedCount]
    madrid: list[NamedCount]
```

- [ ] **Step 2: Update imports in `routes/gazettes.py`**

In `app/backend/api/routes/gazettes.py`, change the `from ..db.models import MadridRecord, UserRole` line (line 16) to:

```python
from ..db.models import DomesticRecord, MadridRecord, UserRole
```

and add, immediately after the existing `from .._filename import parse_filename_meta` import (line 13):

```python
from .._entity_norm import norm, strip_madrid_rep_address
```

- [ ] **Step 3: Move the `collections` imports to the top of the file**

In `app/backend/api/routes/gazettes.py`, add these to the stdlib import block at the top (alongside `hashlib`/`uuid`/`pathlib`/`typing`, lines 3-7):

```python
from collections import Counter
from collections.abc import Callable, Iterable
```

- [ ] **Step 4: Delete the interim normalization helpers**

In `app/backend/api/routes/gazettes.py`, delete the now-superseded module-level helpers (currently lines 47-75) — the `_REP_PREFIX_RE`, `_WS_RE`, `_MADRID_REP_TRIM_RE` regexes and the `_normalize_rep` and `_trim_madrid_rep` functions. The exact block to remove:

```python
# Leading Vietnamese law-firm legal prefix, stripped before grouping domestic
# representatives. INTERIM (see TODO below).
_REP_PREFIX_RE = re.compile(r"^công ty (luật )?(tnhh|cổ phần) ")
_WS_RE = re.compile(r"\s+")
# First digit-run or comma — Madrid `representative` concatenates the firm name
# with its postal address; we trim at that boundary. INTERIM.
_MADRID_REP_TRIM_RE = re.compile(r"[,]|\d")


def _normalize_rep(raw: str) -> str:
    """INTERIM domestic-representative normalization: casefold, collapse
    whitespace, strip a leading `Công ty (Luật) TNHH|Cổ phần` legal prefix.

    TODO(task_057fcd61): full canonicalization — cluster near-duplicate firm
    variants (punctuation/casing/whitespace drift) to a stored canonical key.
    """
    s = _WS_RE.sub(" ", raw).strip().casefold()
    s = _REP_PREFIX_RE.sub("", s)
    return s.strip()


def _trim_madrid_rep(raw: str) -> str:
    """INTERIM Madrid-representative trim: take the firm name up to the first
    digit-run / address token, casefolded + whitespace-collapsed.

    TODO(task_057fcd61): full canonicalization.
    """
    head = _MADRID_REP_TRIM_RE.split(raw, maxsplit=1)[0]
    return _WS_RE.sub(" ", head).strip().casefold()
```

After deletion, `import re` (line 4) is no longer used anywhere in the file — remove it. Verify with `grep -n "re\.\|\bre\b" app/backend/api/routes/gazettes.py` → expect no `re.` usage remaining.

- [ ] **Step 5: Add a shared Python aggregator helper**

In `app/backend/api/routes/gazettes.py`, add this module-level helper just after the `_MAX_MISSING_LISTED` constant (~line 45, where the deleted helpers used to be):

```python
def _top_entities(
    raws: Iterable[str | None],
    *,
    pre: Callable[[str], str] | None = None,
    limit: int = 6,
) -> list[NamedCount]:
    """Group trusted names by `norm` key, count occurrences (one per mark), and
    return the top `limit` as NamedCount, displaying the most-common raw spelling
    per key. `pre` (e.g. strip_madrid_rep_address) runs before norm + display.
    Ordering is deterministic: by descending count, then norm key.
    """
    counts: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for raw in raws:
        if not raw:
            continue
        display_src = (pre(raw) if pre else raw).strip()
        if not display_src:
            continue
        key = norm(display_src)
        if not key:
            continue
        counts[key] += 1
        spellings.setdefault(key, Counter())[display_src] += 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [NamedCount(name=spellings[key].most_common(1)[0][0], n=n) for key, n in ordered]
```

- [ ] **Step 6: Rewire the Top applicants block**

In `gazette_overview`, replace the "Top applicants" block (currently lines 425-448) with a trusted-source join for domestic (LEFT JOIN `domestic_records`, coalesce to the gazette field as fallback) and the existing Madrid source, both grouped via `_top_entities`:

```python
    # --- Top applicants -------------------------------------------------------
    # Domestic: trusted NOIP applicant joined by application_number, gazette
    # field as fallback for the un-enriched residual. One row per mark.
    dom_app_raws = (
        (
            await session.execute(
                select(func.coalesce(DomesticRecord.applicant_name, Trademark.applicant_name))
                .select_from(Trademark)
                .outerjoin(
                    DomesticRecord,
                    DomesticRecord.application_number == Trademark.application_number,
                )
                .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            )
        )
        .scalars()
        .all()
    )
    # Madrid: trusted WIPO holder (one row per IRN — the existing source).
    mad_app_raws = (await session.execute(select(MadridRecord.holder_name))).scalars().all()
    top_applicants = TopApplicants(
        domestic=_top_entities(dom_app_raws),
        madrid=_top_entities(mad_app_raws),
    )
```

- [ ] **Step 7: Rewire the Top representatives block**

Replace the "Top representatives" block (currently lines 450-495) with trusted-source reads grouped via `_top_entities`; Madrid applies the address strip via `pre`:

```python
    # --- Top representatives (exact: trusted source + norm grouping) ----------
    # Domestic: trusted NOIP representative joined by application_number, gazette
    # (740) field as fallback. One row per mark.
    dom_rep_raws = (
        (
            await session.execute(
                select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                .select_from(Trademark)
                .outerjoin(
                    DomesticRecord,
                    DomesticRecord.application_number == Trademark.application_number,
                )
                .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            )
        )
        .scalars()
        .all()
    )
    # Madrid: trusted WIPO representative (strip the glued trailing address).
    mad_rep_raws = (await session.execute(select(MadridRecord.representative))).scalars().all()
    top_representatives = TopRepresentatives(
        domestic=_top_entities(dom_rep_raws),
        madrid=_top_entities(mad_rep_raws, pre=strip_madrid_rep_address),
    )
```

Note: `distinct` (imported on line 10) is still used by `list_gazettes` (~line 282), so keep that import.

- [ ] **Step 8: Type-check + lint**

Run: `cd app/backend && ruff format api/routes/gazettes.py api/schemas.py && ruff check api && mypy api worker`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/api/routes/gazettes.py app/backend/api/schemas.py
git commit -m "feat(gazettes): exact applicant/representative metrics via trusted-source join

Read NOIP domestic_records / WIPO madrid_records (joined by each mark's
deterministic id) and GROUP BY norm() instead of messy gazette OCR fields.
Drop the now-untrue 'approximate' flag from top_representatives.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Overview endpoint tests (seed + norm-grouping + distinctness)

**Files:**
- Modify: `app/backend/tests/test_gazettes_overview.py`

- [ ] **Step 1: Import `DomesticRecord` + add seeded-name constants**

In `app/backend/tests/test_gazettes_overview.py`, change the model import (line 32) to:

```python
from api.db.models import DomesticRecord, MadridRecord
```

Add these constants near the other seed constants (~line 49, after `_N_MADRENEW_2099`):

```python
# Domestic representative seed: three case/whitespace variants of ONE firm
# (norm → 1 key, 3 marks) plus a genuinely distinct firm (1 key, 2 marks).
_REP_FIRM_A = "Công ty Luật TAGA"
_REP_FIRM_B = "Distinct Firm XYZ"

# mark_category values that count as "domestic" (mirrors routes/gazettes.py).
_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")
```

- [ ] **Step 2: Extend the autouse fixture — clean up + seed domestic_records**

In the `_cleanup` helper inside the `seed` fixture (~line 61), add a delete for the seeded domestic_records (the existing trademarks use application_numbers `OVWAPP0..2` and `OVWREG0..1`). Add as the first statement in `_cleanup`:

```python
        await s.execute(
            delete(DomesticRecord).where(
                DomesticRecord.application_number.in_(
                    ["OVWAPP0", "OVWAPP1", "OVWAPP2", "OVWREG0", "OVWREG1"]
                )
            )
        )
```

Then, after the two `MadridRecord` adds and before `await s.commit()` (~line 133), seed the domestic_records:

```python
        # Domestic enrichment rows joined by application_number. The three
        # OVWAPP* reps are case/whitespace variants of ONE firm (norm → 1 key,
        # 3 marks); the two OVWREG* reps are a second, distinct firm (2 marks).
        s.add(DomesticRecord(application_number="OVWAPP0", applicant_name="TAGA Co", representative="Công ty Luật TAGA"))
        s.add(DomesticRecord(application_number="OVWAPP1", applicant_name="TAGA Co", representative="CÔNG TY LUẬT TAGA"))
        s.add(DomesticRecord(application_number="OVWAPP2", applicant_name="TAGA Co", representative="Công  ty   Luật   TAGA"))
        s.add(DomesticRecord(application_number="OVWREG0", applicant_name="XYZ Ltd", representative="Distinct Firm XYZ"))
        s.add(DomesticRecord(application_number="OVWREG1", applicant_name="XYZ Ltd", representative="Distinct Firm XYZ"))
```

- [ ] **Step 3: Replace the approximate-flag test with a no-approximate-key test**

Replace `test_overview_representatives_approximate_flag` (currently lines 247-255) with:

```python
@pytest.mark.asyncio
async def test_overview_representatives_no_approximate_flag(authed_client: AsyncClient) -> None:
    """Counts are now exact (trusted source + norm), so the `approximate` flag
    is gone from the payload entirely."""
    r = await authed_client.get("/api/v1/gazettes/overview")
    d = r.json()
    reps = d["top_representatives"]
    assert "approximate" not in reps
    assert "domestic" in reps and "madrid" in reps
    assert isinstance(reps["domestic"], list)
    assert isinstance(reps["madrid"], list)
    # Ranking contract: capped at 6, sorted by descending count.
    for side in ("domestic", "madrid"):
        ns = [row["n"] for row in reps[side]]
        assert len(ns) <= 6
        assert ns == sorted(ns, reverse=True)
```

- [ ] **Step 4: Add the distinctness + merge test (deterministic, seeded subset)**

Append to `app/backend/tests/test_gazettes_overview.py`:

```python
@pytest.mark.asyncio
async def test_domestic_reps_merge_variants_and_keep_distinct_firms_distinct() -> None:
    """The trusted-source join + norm grouping collapses case/whitespace variants
    of ONE firm into a single key (3 marks) while keeping a genuinely different
    firm separate (2 marks). Asserted on the seeded subset so it's immune to live
    data — it exercises the exact query + norm the endpoint uses."""
    from sqlalchemy import func, select

    from api._entity_norm import norm

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    appnos = ["OVWAPP0", "OVWAPP1", "OVWAPP2", "OVWREG0", "OVWREG1"]
    async with Session() as s:
        raws = (
            (
                await s.execute(
                    select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                    .select_from(Trademark)
                    .outerjoin(
                        DomesticRecord,
                        DomesticRecord.application_number == Trademark.application_number,
                    )
                    .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
                    .where(Trademark.application_number.in_(appnos))
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()

    grouped: dict[str, int] = {}
    for raw in raws:
        grouped[norm(raw)] = grouped.get(norm(raw), 0) + 1

    assert grouped[norm(_REP_FIRM_A)] == 3  # three variants merged
    assert grouped[norm(_REP_FIRM_B)] == 2  # distinct firm kept separate
    assert norm(_REP_FIRM_A) != norm(_REP_FIRM_B)
    assert len(grouped) == 2
```

- [ ] **Step 5: Add the endpoint-equals-hand-computed test**

Append to `app/backend/tests/test_gazettes_overview.py`:

```python
@pytest.mark.asyncio
async def test_overview_domestic_reps_equal_hand_computed_norm_grouping(
    authed_client: AsyncClient,
) -> None:
    """The endpoint's domestic representative top-6 equals a hand-computed
    `GROUP BY norm(coalesce(domestic_records.representative, ip_agency_raw_740))`
    over the domestic-category marks. Recomputed immediately after the call to
    bound any concurrent sweep writes; compared by norm key so display
    tie-breaking can't cause spurious failures."""
    from collections import Counter

    from sqlalchemy import func, select

    from api._entity_norm import norm

    r = await authed_client.get("/api/v1/gazettes/overview")
    assert r.status_code == 200
    endpoint = r.json()["top_representatives"]["domestic"]

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        raws = (
            (
                await s.execute(
                    select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                    .select_from(Trademark)
                    .outerjoin(
                        DomesticRecord,
                        DomesticRecord.application_number == Trademark.application_number,
                    )
                    .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()

    counts: Counter[str] = Counter()
    for raw in raws:
        if not raw or not raw.strip():
            continue
        key = norm(raw)
        if key:
            counts[key] += 1
    expected = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]

    # Map the endpoint's display names back to norm keys for an apples-to-apples
    # comparison of (key, count) in the production ordering.
    got = [(norm(row["name"]), row["n"]) for row in endpoint]
    assert got == expected
```

- [ ] **Step 6: Run the overview tests**

Run: `cd app/backend && pytest tests/test_gazettes_overview.py -v`
Expected: PASS (all tests, including the renamed no-approximate test and the two new ones).

- [ ] **Step 7: Lint + format the test changes**

Run: `cd app/backend && ruff format tests/test_gazettes_overview.py && ruff check tests/test_gazettes_overview.py`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add app/backend/tests/test_gazettes_overview.py
git commit -m "test(gazettes): assert exact domestic rep counts via norm grouping; drop approximate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Backend verification gates + PR 1

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend gate suite**

Run from `app/backend/` (venv active):

```bash
cd app/backend
ruff check . && ruff format --check . && mypy api worker && alembic check
```

Expected: ruff clean; mypy clean; **`alembic check` reports no new upgrade operations** (Phase 1 has no migration — if it demands a revision, a model/column was changed by mistake; investigate, do not autogenerate).

- [ ] **Step 2: Run the targeted tests**

Run: `cd app/backend && pytest tests/test_entity_norm.py tests/test_gazettes_overview.py -v`
Expected: PASS. (Do NOT run the sweep tests — they reset the live `domestic_sweep_control` singleton.)

- [ ] **Step 3: Confirm the rename trio is NOT staged and check the commits**

Run: `cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet && git status --short && git log --oneline -3`
Expected: `README.md`, `app/.env.example`, `app/backend/api/settings.py` still show as unstaged `M` (never committed). The three feature commits from Tasks 1-3 are present.

- [ ] **Step 4: Open PR 1 (backend)**

If the three commits are on `main` locally, create the branch from current HEAD (it captures them); verify the rename trio is in none of them first with `git show --stat HEAD~2..HEAD | grep -E "README.md|.env.example|settings.py"` → expect no output.

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git checkout -b feat/entity-canon-phase1-backend
git push -u origin feat/entity-canon-phase1-backend
gh pr create --base main --title "feat: exact applicant/representative dashboard metrics (entity canon Phase 1 backend)" --body "$(cat <<'EOF'
## What

Phase 1 of entity-name cleanup (no migration). Rewires the four
`/api/v1/gazettes/overview` applicant/representative aggregations to read the
**trusted** WIPO/NOIP names already in the DB — joined by each mark's
deterministic identifier — and `GROUP BY norm()` (NFC → casefold → collapse
whitespace → trim). Drops the now-untrue `approximate` flag.

- New `api/_entity_norm.py`: `norm()` grouping key + `strip_madrid_rep_address()`.
- Domestic applicant/rep ← `domestic_records` (join by `application_number`),
  gazette field as fallback for the un-enriched residual.
- Madrid applicant ← `madrid_records.holder_name`; Madrid rep ←
  `madrid_records.representative` (address-stripped).
- Removed the interim `_normalize_rep`/`_trim_madrid_rep` hacks.

Spec: `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`.

## Tests

- `tests/test_entity_norm.py` — norm collapses case/whitespace/diacritics,
  keeps distinct names distinct, Madrid address strip.
- `tests/test_gazettes_overview.py` — endpoint domestic rep counts equal a
  hand-computed `GROUP BY norm(...)`; variants merge, distinct firms stay
  distinct; `approximate` key removed.

Frontend hint removal ships as a follow-up PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Task 5: Frontend hint removal + PR 2

**Files:**
- Modify: `app/frontend/lib/api.ts:156-163`
- Modify: `app/frontend/components/admin/gazettes-dashboard.tsx`

- [ ] **Step 1: Drop `approximate` from the API type**

In `app/frontend/lib/api.ts`, replace the `TopRepresentatives` type (lines 156-163):

```typescript
export type TopRepresentatives = {
  domestic: NamedCount[];
  madrid: NamedCount[];
  /** Interim — names are only prefix-stripped / address-trimmed, not fully
   *  canonicalized (same firm still fragments). Full canonicalization is
   *  tracked in task_057fcd61. */
  approximate: boolean;
};
```

with:

```typescript
export type TopRepresentatives = {
  // Counts are exact — trusted WIPO/NOIP source grouped by a normalized key.
  domestic: NamedCount[];
  madrid: NamedCount[];
};
```

- [ ] **Step 2: Remove the `approximate` prop from the dashboard call site**

In `app/frontend/components/admin/gazettes-dashboard.tsx`, the "Top representatives" `TopPanel` (lines 160-165) currently passes `approximate`. Replace:

```tsx
        <TopPanel
          title="Top representatives"
          domestic={data.top_representatives.domestic}
          madrid={data.top_representatives.madrid}
          approximate={data.top_representatives.approximate}
        />
```

with:

```tsx
        <TopPanel
          title="Top representatives"
          domestic={data.top_representatives.domestic}
          madrid={data.top_representatives.madrid}
        />
```

- [ ] **Step 3: Remove the `approximate` prop + hint from `TopPanel`**

In the same file, update the `TopPanel` component signature/props (lines 360-374) to drop `approximate`:

```tsx
function TopPanel({
  title,
  domestic,
  madrid,
}: {
  title: string;
  domestic: NamedCount[];
  madrid: NamedCount[];
}) {
  const [tab, setTab] = React.useState<"domestic" | "madrid">("domestic");
  const rows = tab === "domestic" ? domestic : madrid;
  const barColor = tab === "domestic" ? COLOR.domestic_registrations : COLOR.madrid_registrations;
  const max = Math.max(...rows.map((r) => r.n), 1);
```

and delete the approximate hint block (lines 391-398):

```tsx
        {approximate && (
          <p className="text-[10.5px] text-mute mb-2">
            <Pill tone="mute" size="sm">
              approximate
            </Pill>{" "}
            names not yet fully canonicalized
          </p>
        )}
```

- [ ] **Step 4: Drop the now-unused `Pill` import if unused**

Run: `grep -n "Pill" app/frontend/components/admin/gazettes-dashboard.tsx`
If the only remaining match is the import line (line 29), remove `Pill` from that import:

```tsx
import { Card, SegmentedControl } from "@/components/ui";
```

(If `Pill` is used elsewhere in the file, leave the import as-is.)

- [ ] **Step 5: Type-check + lint the frontend**

Run: `cd app/frontend && npx tsc --noEmit && pnpm lint`
Expected: clean. **Do NOT run `pnpm build`** if a `pnpm dev` server is live.

- [ ] **Step 6: Commit + open PR 2**

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git checkout main && git checkout -b feat/entity-canon-phase1-frontend
git add app/frontend/lib/api.ts app/frontend/components/admin/gazettes-dashboard.tsx
git commit -m "feat(admin): drop 'approximate' hint from Top representatives (counts now exact)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push -u origin feat/entity-canon-phase1-frontend
gh pr create --base main --title "feat: drop 'approximate' representative hint (entity canon Phase 1 frontend)" --body "$(cat <<'EOF'
## What

Follow-up to the backend Phase 1 PR. The dashboard's representative counts are
now exact (trusted WIPO/NOIP source grouped by a normalized key), so the
"approximate · names not yet fully canonicalized" hint and the `approximate`
type field are removed.

Depends on the backend PR (which removes `approximate` from the API payload).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Docs-sync pass

- [ ] **Step 1: Mark Phase 1 as implemented in the spec**

In `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`, add a one-line status note under the "Phase 1" heading (e.g. "**Status: implemented** — see PRs `feat/entity-canon-phase1-backend` + `-frontend`."). Commit on the backend branch (or a small standalone docs commit):

```bash
cd /Users/francisluong/Project/ASL/ClaudeDesktop/Tradenet
git add docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md docs/superpowers/plans/2026-06-22-entity-canonicalization-phase1.md
git commit -m "docs(spec): mark entity-canon Phase 1 implemented; add Phase 1 plan

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 2: Confirm no stale `approximate` doc claims remain**

Run: `grep -rn "approximate\|not yet fully canonicalized\|task_057fcd61" app/ README.md CLAUDE.md 2>/dev/null`
Expected: no code or code-doc still claims the representative metric is approximate or references the superseded `task_057fcd61` TODO. Fix any stale prose found (the CLAUDE.md does not currently mention it; the spec/plan references are expected).

---

## Self-Review checklist (verified at authoring time)

- **Spec coverage:** `_entity_norm.py` ✔ (Task 1); four aggregations rewired to trusted source + norm ✔ (Task 2 Steps 6-7); domestic join by `application_number` ✔; Madrid holder kept ✔; Madrid rep address-strip+norm ✔; precedence trusted-over-gazette via `coalesce` ✔; un-enriched falls back to gazette field ✔; `approximate` removed from payload+schema+frontend ✔ (Tasks 2/5); hand-computed norm-grouping test + distinctness test ✔ (Task 3); no migration → `alembic check` clean ✔ (Task 4); rename trio never staged ✔.
- **Placeholders:** none — every code step shows full code.
- **Type consistency:** `norm`/`strip_madrid_rep_address` signatures identical across Tasks 1-3; `_top_entities` defined once (Task 2 Step 5) and used in Steps 6-7; `NamedCount` shape unchanged; `TopRepresentatives` loses only `approximate`, consistently in schema (Task 2), API type (Task 5), and component (Task 5); `_DOMESTIC_CATEGORIES` defined in both the route and the test module.
