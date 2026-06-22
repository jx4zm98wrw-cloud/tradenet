# Entity Canonicalization — Clean-DB Parties Layer (Design)

**Status:** Approved for planning · 2026-06-22 · supersedes the representative-only task `task_057fcd61`

**Goal:** Make the database *clean* at the entity level — every applicant and representative across `trademarks`, `domestic_records`, and `madrid_records` resolves to a single **canonical party**, anchored to the trusted sources (NOIP / WIPO) as ground truth, with gazette-OCR names reconciled *to* that truth. The clean layer serves the dashboard, search, mark detail, and future per-entity / portfolio features.

## Problem

Entity names exist in three places with three qualities:
- **Gazette OCR** (`trademarks.applicant_name`, `trademarks.ip_agency_raw_740`) — messy: punctuation, casing, whitespace, legal-prefix variance. The same firm fragments into many "distinct" values.
- **NOIP** (`domestic_records.applicant_name`, `.representative`) — authoritative, clean. Representatives: **558 distinct** (vs thousands of gazette variants); applicants authoritative.
- **WIPO** (`madrid_records.holder_name`, `.representative`) — authoritative; holders ~3,142 distinct; representatives ~2,410 but with a **glued trailing address** that must be stripped.

So any grouping/dedup/count on the raw fields is wrong. The current `/admin/gazettes` dashboard carries an `approximate` flag for exactly this reason.

## Ground truth & precedence

Per mark, the canonical name is taken from the **best available source**, in order:
1. **NOIP** (`domestic_records`) for domestic marks.
2. **WIPO** (`madrid_records`) for Madrid marks.
3. **Gazette** fields only as fallback (un-enriched marks), reconciled to the reference vocabulary.

NOIP + WIPO distinct sets form the **reference vocabulary** that gazette/residual names snap to. They are not blindly clustered — matching against a known-good dictionary is the safe, supervised approach.

## Architecture — a `parties` dimension table (FK model)

Chosen over canonical text columns for scale: at ~1–2M+ trademark rows, an integer `party_id` FK (4–8 B) beats duplicating a ~50-byte Vietnamese name on every row — smaller tables/indexes, faster integer `GROUP BY`/joins, and a merge repoints one row instead of thousands.

```
parties
  id            bigint PK
  kind          text   -- 'applicant' | 'representative'   (CHECK)
  canonical_name text  -- chosen human-readable display form
  match_key     text   -- normalized key used for matching/dedup
  source        text   -- 'noip' | 'wipo' | 'gazette'  (provenance of canonical_name)
  variant_count int    -- raw variants mapped here (audit)
  UNIQUE (kind, match_key)
  + indexes on (kind), (canonical_name)

party_alias            -- audit trail: every raw value and where it mapped
  id            bigint PK
  party_id      bigint FK -> parties
  raw_name      text
  raw_source    text   -- 'noip'|'wipo'|'gazette'
  method        text   -- 'exact'|'normalized'|'fuzzy'|'override'
  UNIQUE (raw_source, raw_name)

trademarks
  + applicant_party_id        bigint FK -> parties  (indexed)
  + representative_party_id   bigint FK -> parties  (indexed)
```

(Enrichment tables keep their authoritative text fields; the trademark FKs are the resolved canonical link. A later phase may add party_id to `domestic_records`/`madrid_records` if needed — out of scope for v1.)

## The canonicalization engine — `canonicalize/` package

A reusable, source-aware engine (no DB inside — pure functions + curated data):
- `normalize(raw, *, kind, source) -> str` (the **match_key**): NFC + Vietnamese diacritic normalize, casefold, collapse whitespace/punctuation, and **source-specific pre-clean**:
  - `wipo` + `representative`: strip the trailing glued address (cut at the first address token / digit run).
  - `gazette`: strip the legal-entity affix (`công ty (luật )?(tnhh|cổ phần|…)`), reusing `company_suffixes.json`.
  - `noip`: light normalize only (already near-canonical).
- `display(raw, ...) -> str`: the cleaned human-readable canonical_name.
- `match(key, kind, reference) -> party_id | None`: exact on `match_key`; else **conservative** fuzzy (token-set / trigram above a tuned threshold) — opt-in, logged, never silently merging below confidence.
- **Curated overrides** in `entity_overrides.json` (same pattern as `cities_overrides.json`): `{ "representative": { "<raw or key>": "<canonical>" }, "applicant": {...} }` — manual merges that survive every re-derive.

## Backfill / reconciliation pipeline (offline, idempotent)

Mirrors the existing domestic/Madrid re-derive pattern — re-runnable, no re-fetch:
1. **Seed `parties`** from the reference vocabulary: distinct NOIP names + WIPO names → `normalize` → upsert one party per `(kind, match_key)` with `source` = noip/wipo.
2. **Resolve each trademark**: pick best-source name (NOIP→WIPO→gazette) → `normalize` → `match` to a party (exact/override first, fuzzy second). Gazette-only residue with no match creates a new `gazette`-source party. Set `applicant_party_id` / `representative_party_id`; write a `party_alias` row.
3. **Audit report**: counts by `method`, new parties created, and a "low-confidence merges" list for review. Apply overrides → re-run.
A `canon_version` bump (like `parse_version`) lets the whole thing re-derive when the engine changes.

## Consumer migration (phased)

- **Dashboard**: replace the interim normalization with `GROUP BY party_id` (drop the `approximate` flag). Top-N panels become a **materialized summary** (top parties per kind × stream) refreshed on ingest → O(1) reads at any DB size.
- **Mark detail / search / portfolio** (later): use `party_id` for "all marks by this entity" — a cheap FK join.

## Decomposition — this is an epic; build in phases (each independently shippable + testable)

- **Phase 1 — Engine + schema + trusted-source backfill.** `canonicalize/` package + unit tests; `parties`/`party_alias` tables + migration + FK columns; seed parties from NOIP/WIPO and resolve the FK for enriched marks. Deliverable: parties populated from ground truth; enriched marks linked.
- **Phase 2 — Residual reconciliation + overrides + audit.** Snap gazette-only/un-enriched names to the reference (conservative matching), `entity_overrides.json`, and the audit report. Deliverable: every mark has both FKs; merges are reviewable.
- **Phase 3 — Consumer migration.** Dashboard materialized summaries on `party_id` (approximate flag removed); then search/detail/portfolio.

## Testing

- Engine (pure): the "Kim Mã" variants collapse to one key; WIPO-rep address strip; gazette legal-prefix strip; distinct firms stay distinct; overrides win.
- Backfill: NOIP/WIPO seed counts match distinct-source counts; precedence (NOIP>WIPO>gazette) honored; idempotent (second run is a no-op); a known variant set resolves to one party.
- Targeted pytest only (sweep tests reset the live `domestic_sweep_control` singleton).

## Non-goals (v1)

- No fuzzy clustering *without* a reference anchor (no unsupervised merging of OCR noise). No entity-merge UI (overrides JSON instead). No `party_id` on enrichment tables yet. No address/individual-person canonicalization (entities = company/firm names only). No change to extraction or `mark_category`.

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. This epic ADDS a migration (parties tables + FK columns) — `alembic check` will require it.
- Conservative + auditable: a wrong merge is worse than an honest duplicate. Default to *not* merging below confidence; log every decision to `party_alias`.
