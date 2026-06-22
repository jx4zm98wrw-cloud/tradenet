# Clean Entity Names via Trusted-Source Join (Design)

**Status:** Approved for planning · 2026-06-22 (rev 2 — simplified) · supersedes the representative-only task `task_057fcd61`

**Goal:** Make applicant + representative names *clean* by using the authoritative WIPO/NOIP values that are **already in the database**, linked to each mark by its deterministic identifier — no fuzzy matching, no guessing.

## Key insight (why this is simple)

Every mark already carries a **deterministic key** to its trusted record, so we never have to *guess* which messy strings are the same firm:

| `mark_category` | Identifier | Trusted record (already in DB) |
|---|---|---|
| `domestic_application` | `application_number` | `domestic_records` (NOIP) |
| `domestic_registration` | `application_number` | `domestic_records` (NOIP) |
| `madrid_registration` | `IRN` (`trademarks.lineage_key`) | `madrid_records` (WIPO) |
| `madrid_renewal` | `IRN` (`trademarks.lineage_key`) | `madrid_records` (WIPO) |

So the clean applicant/representative for a mark is **a join away** — `trademarks.application_number = domestic_records.application_number`, or `trademarks.lineage_key = madrid_records.irn`. We take the trusted field; the messy gazette fields (`applicant_name`, `ip_agency_raw_740`) are pure fallback for the small un-enriched residual.

**Explicitly rejected (and why):** a `parties` dimension table, a fuzzy `match()` engine, reference-snap matching, and an overrides file. Those only exist to solve "which OCR variants are the same entity?" — a problem the identifier **already answers deterministically**. Building them would add risk (wrongly merging two real firms) and a copy of data to keep in sync, for no benefit. We do **not** build a third reference table either — `domestic_records` / `madrid_records` already *are* the trusted reference.

## The one thing the join doesn't give for free: clean *counts*

The join gives clean *names*, but the trusted sources still hold light spelling variants of the same entity — NOIP `CÔNG TY TNHH … TAGA` vs `Công ty TNHH … TAGA` (case), WIPO `L'OREAL` vs `L'Oréal`. For *grouping/counting* (the dashboard's "top entities"), apply a **trivial normalizer** to form a grouping key:

`norm(s) = NFC-normalize → casefold → collapse internal whitespace → trim`

That's a one-liner (`api/_entity_norm.py`, ~10 lines), **not** a fuzzy engine. It collapses case/whitespace variants; it never merges distinct names. (WIPO representatives additionally have a trailing glued address — strip at the first digit-run/address token before norming; that's a deterministic cut, not fuzzy.)

## Architecture

Two pieces, smallest-first:

### Phase 1 — Dashboard reads the trusted source (no schema change)

> **Status: implemented** (2026-06-22). `api/_entity_norm.py` (`norm()` + `strip_madrid_rep_address()`) added; the four `/overview` aggregations rewired to the trusted-source join + `norm` grouping; `approximate` flag removed from the schema, payload, and dashboard. No migration. Plan: [`docs/superpowers/plans/2026-06-22-entity-canonicalization-phase1.md`](../plans/2026-06-22-entity-canonicalization-phase1.md). Ships as branches `feat/entity-canon-phase1-backend` (backend) + `feat/entity-canon-phase1-frontend` (hint removal).

Change the `/overview` applicant + representative aggregations (PR #91) to **join the enrichment tables** and group by the normalized trusted name:
- Domestic applicant: `domestic_records.applicant_name` (joined by `application_number`).
- Domestic representative: `domestic_records.representative`.
- Madrid applicant: `madrid_records.holder_name` (already used).
- Madrid representative: `madrid_records.representative` (already used) — apply the address-strip + norm.
- Group by `norm(name)`, display the most-common raw form per key.

Result: domestic counts become **exact** (558 real reps, not OCR fragments); the `approximate` flag is **removed**. No migration. This is most of the value.

### Phase 2 — Denormalized clean columns (optional, for scale + reuse)

A re-runnable, idempotent backfill (mirrors the domestic/Madrid re-derive pattern) that writes the resolved clean values onto `trademarks` so search / mark-detail / future "all marks by firm" read a clean column without joining every time:

```
trademarks
  + applicant_clean        text   -- trusted display name (NOIP>WIPO>gazette fallback)
  + applicant_norm         text   -- norm(applicant_clean), indexed (grouping/filter key)
  + representative_clean    text
  + representative_norm     text   -- indexed
```

Backfill per mark: resolve best source by identifier (NOIP → WIPO → gazette fallback), set `*_clean` + `*_norm`. `entity_clean_version` bump re-derives when `norm` changes. The dashboard's Phase-1 join can then be swapped for a cheap `GROUP BY *_norm` over the indexed column (or a materialized summary) at any DB size.

## Residual handling

Marks with no enrichment record (un-enriched domestic — ~0% now; the small Madrid un-enriched slice): fall back to the normalized **gazette** value (or leave `*_clean` null). No fuzzy attempt.

## Deferred (noted, not built)

**Cross-source unification** — a firm that is both a domestic rep (NOIP spelling) and a Madrid rep (WIPO spelling) stays as two grouping keys. The dashboard splits Domestic | Madrid so it's invisible there; a *global* "all marks by this firm across both regimes" would need a manual cross-walk. Out of scope for v1.

## Decomposition

- **Phase 1** (small, no migration): `_entity_norm.py` + rewire the four `/overview` applicant/representative aggregations to join the trusted tables and group by `norm`. Drop the `approximate` flag. Update the dashboard's "approximate" hint.
- **Phase 2** (optional, one migration): `applicant_clean`/`norm` + `representative_clean`/`norm` columns + backfill + `entity_clean_version`; point consumers (dashboard, later search/detail) at the columns.

## Testing

- `norm()` (pure): case/whitespace/diacritic variants of one name collapse to one key; distinct names stay distinct; WIPO-rep address strip.
- Phase 1: `/overview` domestic counts equal a hand-computed `GROUP BY norm(domestic_records.representative)`; precedence (trusted over gazette) honored; un-enriched falls back.
- Phase 2: backfill is idempotent (second run no-op); `*_norm` indexed; a known variant set groups to one key.
- Targeted pytest only (sweep tests reset the live `domestic_sweep_control` singleton).

## Non-goals

No fuzzy/similarity matching. No `parties` table. No new reference table (use existing enrichment). No entity-merge UI. No address or individual-person canonicalization. No change to extraction or `mark_category`. No cross-source unification (v1).

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. Phase 1 = no migration; Phase 2 adds one (`alembic check` will require it).
- Trusted source wins over gazette, always. Grouping uses `norm`; never fuzzy-merge distinct names.
