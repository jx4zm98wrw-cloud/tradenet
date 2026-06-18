# Madrid Standardization — WIPO-authoritative bibliographic data (Design)

**Status:** Draft for review · 2026-06-18

**Goal:** For Madrid marks, make the *bibliographic / international* facts come from the authoritative WIPO record (`madrid_records`) instead of the patchy gazette extraction — so dates, holder, classes, goods, designations, and the mark name are standardized and complete — **without** destroying gazette provenance or the gazette-authoritative VN determination.

## Core principle: two authorities, by field

- **WIPO is authoritative for bibliographic facts** (the international record): mark name, holder identity, registration/expiration/renewal dates, Nice classes, goods & services, designated jurisdictions.
- **The gazette is authoritative for the Vietnam determination**: `vn_status` stays **gazette-only** (the VN gazette is *why* each IRN is in our dataset; WIPO may show a provisional refusal the gazette overrode). Never source `vn_status` from WIPO.
- **Provenance is preserved**: the gazette original is always recoverable — every gazette value survives in `trademarks` (for the read-time path) and the full WIPO record survives in `madrid_records`/`raw`. Nothing is destructively lost.

## Apply mechanism: two paths, by use

| Path | For | How |
|---|---|---|
| **Backfill** WIPO → `trademarks` columns (in `enrich_one`, the one sanctioned place we touch `trademarks`) | Fields that must be **searchable / sortable / filterable / shown on list cards** | mark name (done), registration date, expiration date |
| **Read-time** (join `madrid_records` on `lineage_key`; prefer WIPO at the API/detail layer) | Display-only / large fields | holder name+address+country, full goods text (done on detail), designations, renewal history |

Backfill is **`wipo-preferred` for Madrid rows** (the standardization goal), not merely `wipo-when-null` — for the bibliographic fields below. Because the gazette original lives in `madrid_records` and `raw`, preferring WIPO in `trademarks` is reversible. (The earlier `mark_sample` backfill was `wipo-when-null`; this proposes upgrading the date/identity fields to `wipo-preferred` for Madrid rows specifically. **This is the key decision to confirm.**)

## Field-precedence table (Madrid rows only)

| `trademarks` field | Source | Notes |
|---|---|---|
| `mark_sample` | `madrid_records.mark_text` | already backfilled (when null); keep |
| `registration_date_151` | `madrid_records.registration_date` | WIPO IR registration date (180/151). Authoritative; gazette often year-only/missing for Madrid |
| `expiry_date_181` | `madrid_records.expiration_date` | WIPO (180) — reflects renewals; the canonical "runs through" date |
| `nice_classes` | `madrid_records.nice_classes` | WIPO full list; gazette Madrid list can be partial |
| `applicant_name` | gazette (keep) · WIPO via read-time | Don't overwrite the gazette applicant in-place; surface `holder_name` on the WIPO card (done). Revisit only if list cards must show the WIPO holder |
| goods text (`raw_511_text`) | read-time `goods_services` | already preferred on detail; keep |
| `applicant_country_code` | gazette (keep) · WIPO `holder_country` read-time | gazette uses VN's `(CC)`; WIPO has it too — align only if a mismatch audit shows gazette gaps |
| **`vn_status` / `vn_grant_date`** | **gazette-authoritative — DO NOT source from WIPO** | derived rule stays as-is |
| renewal date | read-time (`transaction_history` Renewal events) | no dedicated `trademarks` column; surface in the timeline (done) |

Dates are stored only when the gazette value is **absent or strictly less precise** than WIPO (e.g. gazette has a year, WIPO has a full date) — or, under `wipo-preferred`, whenever WIPO has a value and it differs. Either way the gazette original remains in `madrid_records`.

## Validation: gazette-vs-WIPO audit (do this first)

Before trusting the standardization, run a diff over the enriched set (in the spirit of `scripts/audit_fields.py`):
- count Madrid marks where `registration_date_151` is null/year-only but WIPO has a full date;
- count where gazette `expiry` ≠ WIPO `expiration_date` (and by how much — catches renewals the gazette missed);
- count where gazette `nice_classes` ⊊ WIPO `nice_classes`;
- count where the two **disagree** on a non-null value (the risky case — inspect a sample before choosing `wipo-preferred` vs `wipo-when-null`).

This *quantifies* the win and surfaces conflicts before any write. Runs on the 1,665 already-enriched today; re-runs on the full set after the sweep finishes.

## Process

1. ✅ Unique IRN list — `iter_madrid_irns()`.
2. ✅ Fetch → `madrid_records` — sweep (resuming in capped batches).
3. **Confirm the precedence table** (esp. `wipo-preferred` vs `wipo-when-null` for the date fields).
4. **Audit** gazette-vs-WIPO on the enriched set → confirm the win + inspect conflicts.
5. **Implement** — extend `enrich_one`'s backfill for the agreed date/identity columns; add read-time joins where needed; idempotent, only Madrid rows.
6. **Re-derive offline** (bump `parse_version`) to apply to all cached records — zero WIPO calls.
7. **Re-run the audit** to confirm the standardized state.

## Risks / caveats

- **Never source `vn_status` from WIPO** (gazette-authoritative).
- **Preserve gazette originals** — backfill is reversible because the original survives in `madrid_records`/`raw`; never `DELETE`/clobber without that safety net.
- **Date semantics**: WIPO `registration_date` = IR registration, *not* the VN grant date (`vn_grant_date`). Don't conflate.
- **WIPO drifts** (renewals): the refresh job (deferred Plan 4, staleness-prioritized) keeps `madrid_records` current; the backfill must re-apply when a record changes.
- **Only Madrid marks** (`mark_category IN ('madrid_registration','madrid_renewal')`); domestic VN marks stay gazette-only.
