# Madrid WIPO Enrichment — Design Spec

**Date:** 2026-06-17
**Status:** Approved design, pending implementation plan
**Owner:** Tradenet

## 1. Overview

Enrich the Madrid trademark records in Tradenet with authoritative data fetched
from the **WIPO Madrid Monitor** detail endpoint:

```
https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.{IRN}
```

`{IRN}` is the WIPO International Registration Number — for our Madrid rows this
equals `trademarks.lineage_key` (= `COALESCE(application_number, certificate_number,
madrid_number)`, which for Madrid categories resolves to the IRN).

The endpoint returns the **complete WIPO record in one server-rendered HTML
response (~120 KB)**, structured by WIPO INID codes across three views (Summary /
Designation Status / Transaction History). One HTTP request per IRN yields every
bibliographic field, multilingual goods/services, the full designated-country
list, and the complete dated, per-country prosecution history (registration →
refusals → grants → subsequent designations → renewals → expiration).

### Why this is valuable
The NOIP gazette B-files only tell us a Madrid mark was *accepted* in Vietnam.
WIPO tells us, per jurisdiction: **whether VN is designated, exactly when
protection was granted (or refused), and the current expiration after renewals.**
For a Vietnam-focused trademark-watch product this is a qualitatively richer
dataset than the PDFs carry.

Reference sample used throughout: **IRN 1266721** ("Clalen", Interojo Inc., KR).
Its VN facts: designated at registration (2015-06-26), **granted in VN
2019-05-02** (Gaz 2019/16), **renewed 2025-02-27** extending expiration to
**2035-06-26**, no VN refusal.

## 2. Goals / Non-goals

**Goals**
- A separate `madrid_records` table keyed by IRN (hybrid: promoted typed columns
  + JSONB for nested/long-tail data).
- A WIPO fetch → parse → derive → upsert pipeline that is polite, idempotent,
  resumable, and offline-debuggable (raw HTML cached; parser pure).
- VN-derived fields as first-class, indexed columns.
- A **pilot backfill of 100 IRNs** to validate the parser at volume, then a full
  sweep over all ~4,439 distinct Madrid IRNs.
- Worker hook so future Madrid ingests auto-enrich.
- Surface the enrichment on the mark detail page + a "designated jurisdiction"
  search filter.
- A **WIPO-friendly refresh** strategy (staleness-prioritized, rate-limited,
  circuit-breaking) that keeps `vn_status` / `expiration_date` current without
  risking a block.

**Non-goals (this slice)**
- Fully normalized per-event / per-designation child tables (deferred; can be
  grafted on later from the stored JSONB if cross-mark event analytics is needed).
- Enriching non-Madrid (domestic) rows.
- Real-time / on-demand user-triggered fetches from the UI.

## 3. Data model — `madrid_records`

Primary key = `irn` (text). One row per IRN.

| Group | Column | Type | Source |
|---|---|---|---|
| Identity | `irn` | `text PK` | IRN |
| Holder | `holder_name` | `text` | 732 |
| | `holder_address` | `text` | 732 |
| | `holder_country` | `text` | 811 |
| | `holder_legal_status` | `text` | 842 |
| Mark/rep | `mark_text` | `text` | 540 |
| | `representative` | `text` | 740 |
| Dates | `registration_date` | `date` | 151 |
| | `expiration_date` | `date` | 180 (post-renewal value) |
| Coverage | `nice_classes` | `text[]` | 511 |
| | `designated_countries` | `text[]` | 832 ∪ subsequent designations |
| Basis/lang | `basic_registration` | `text` | 822 |
| | `language` | `text` | 270 |
| VN-derived | `vn_designated` | `bool` | derived |
| | `vn_status` | `text` | derived: `granted`/`refused`/`pending`, null if not designated |
| | `vn_grant_date` | `date` | derived |
| | `vn_refusal_date` | `date` | derived |
| Nested | `designation_status` | `jsonb` | per-country status |
| | `transaction_history` | `jsonb` | event log (typed events) |
| | `raw` | `jsonb` | full parsed record (never lose data) |
| Provenance | `source_url` | `text` | |
| | `fetched_at` | `timestamptz` | |
| | `content_hash` | `text` | sha256 of raw HTML — skip-unchanged |
| | `parse_version` | `int` | bump to force re-parse from cache |

**Indexes:** PK(`irn`); GIN(`designated_countries`); btree(`expiration_date`);
btree(`vn_status`); btree(`vn_grant_date`).

**Linkage:** soft join `trademarks.lineage_key = madrid_records.irn`. No hard FK —
enrichment lags ingest, and a missing `madrid_records` row simply means
"not yet enriched". Mirrors the existing generated-column / soft-link conventions.

`transaction_history` JSONB shape (one object per event):
```json
{ "type": "Statement of grant of protection (R.18ter(1))",
  "date": "2019-05-02", "gazette": "2019/16",
  "parties": ["VN"], "designations": null,
  "ib_receipt_date": "2019-03-01", "extra": { } }
```

## 4. Components

New package `app/backend/madrid_enrich/` (sibling to `tm_extractor/`,
`image_extractor/`), following the vendored-pipeline pattern.

- **`client.py`** — `fetch_raw(irn) -> FetchResult(html, url, headers, status)`.
  Persistent `requests`/`httpx` session (reuses `JSESSIONID` cookie), realistic
  browser User-Agent, timeout, retry with exponential backoff. Reads
  `X-RateLimit-Remaining`; sleeps/slows as it drops. Disk-caches raw HTML to
  `madrid_cache/<irn>.html` so re-parse never re-fetches.
- **`parser.py`** — `parse(html) -> MadridRecord` (Pydantic/dataclass). PURE,
  no I/O. INID-anchored extraction (anchors on numeric codes
  540/151/180/732/811/842/740/511/822/832/527/450/270/581/833/862/891). Builds
  `transaction_history`, `designation_status`, the effective
  `designated_countries` set (original 832 ∪ subsequent-designation events), and
  multilingual goods/services into `raw`.
- **`derive.py`** — `derive_vn(record, *, gazette_accepted=False) -> VnStatus`.
  **Gazette-authoritative**: every IRN this pipeline enriches comes from VN's
  "Madrid accepted in VN" gazette section, so VN protection is already
  established. With `gazette_accepted=True` (the pipeline default) the record is
  always `granted`; WIPO is consulted only to supply the grant *date* and can
  never downgrade to `refused`/`pending`. Grant-date resolution (first hit wins):
  - explicit R.18ter grant event, party=VN → `vn_grant_date` = earliest such date
  - else **designation-date fallback** (only when VN has **no refusal event**,
    provisional or final): earliest VN *designation* event (`Subsequent
    designation, VN`, or the original `International Registration` event listing
    VN) → that date is the accurate commencement of protection. `Renewal` events
    are an upper bound only (protection predates them) and are **never** used;
    "Replacement … by an international registration" is excluded. If VN ever
    refused after designation, the designation date predates the real (later)
    grant, so it is **not** used — grant_date stays null.
  - else → `granted` with `vn_grant_date = null` (date unrecoverable from WIPO;
    typically Agreement-era marks whose only VN signal is a renewal, or marks
    whose VN designation drew a provisional refusal that the gazette later
    overrode on an unrecorded date)
  - not designated → `vn_designated=false`, `vn_status=null`
  - **WIPO-refined fallback** (callers without a gazette signal,
    `gazette_accepted=False`): grant wins; only a *final* refusal (not a bare
    provisional one) with no active registration → `refused`; otherwise `pending`.
- **`store.py`** — `upsert(record)` idempotent by IRN; if `content_hash`
  unchanged and `parse_version` current, skip write. Sets `fetched_at`.

### Integration points
- **`scripts/enrich_madrid.py`** — backfill CLI. `--limit 100` pilot mode;
  no-limit full sweep. Iterates distinct Madrid IRNs
  (`trademarks` where `mark_category IN ('madrid_registration','madrid_renewal')`),
  resumable (skips IRNs already fresh per TTL), throttled, structured progress +
  remaining-budget logging.
- **`worker/ingest.py`** — after a Madrid `Trademark` row is materialized,
  best-effort enrich its IRN (lazy import, failure → row stays un-enriched, never
  blocks ingest — same degradation pattern as `_run_image_extraction`).
- **`api/routes/marks.py`** — mark detail exposes the enrichment for Madrid marks;
  search gains a "designated jurisdiction" filter via a join on `lineage_key`.

## 5. Data flow

```
backfill / worker
   |- client.fetch_raw(irn) --> cache madrid_cache/<irn>.html
        |- parser.parse(html) --> derive.derive_vn() --> store.upsert()
```
- Re-runs skip unchanged records via `content_hash`.
- Parser improvements re-run from cached raw HTML with **zero WIPO requests**
  (bump `parse_version`).
- **Mark-name backfill**: `enrich_one` also writes the WIPO mark name into
  `trademarks.mark_sample` **only when the gazette transcribed no field-540**
  (common for Madrid 3-D/figurative marks, e.g. "Hennessy PARADIS"). It never
  overwrites a real gazette wordmark. This is the one place enrichment touches
  the `trademarks` table — it makes the real mark name show in search/detail
  (and become searchable) instead of an applicant-derived placeholder.

## 6. Fetch politeness & refresh cadence (WIPO-friendly by design)

### Always-on rails
- Throttle to **~1 request / 2–4 s with jitter** (never lockstep).
- Honor `X-RateLimit-Remaining` (limit is 1000/window) — slow as it drops.
- **Self-imposed daily cap** (default ≤300 refresh fetches/day) — far under WIPO's
  window limit.
- `429` / `Retry-After` → exponential backoff; repeated `429`/`403` →
  **circuit-break** (halt batch, log, surface alert) rather than push through.
- Realistic browser UA + reused session cookie.

### Refresh strategy — staleness-prioritized, never a blanket cron sweep
New IRNs are enriched **once** on ingest (worker hook), so the refresh job only
touches the small stale subset. Each record carries `fetched_at`; a low-volume
job picks the most-stale records whose age exceeds a **status-aware TTL**:

| Record state | TTL | Rationale |
|---|---|---|
| `vn_status = pending` | 30 days | catch the VN grant promptly |
| `expiration_date` within ~18 months | 30 days | catch renewals (the 2025→2035 case) |
| granted + far from expiry | 180–365 days | stable, rarely changes |
| unchanged across K refreshes (`content_hash`) | adaptive backoff (lengthen TTL) | quiet records get quieter |

Steady state: a few hundred polite, spaced requests/day against records that
actually moved — comfortably within limits, circuit breaker as backstop.

## 7. Pilot → full sweep

1. **Pilot: 100 IRNs** (`enrich_madrid.py --limit 100`). Validate the parser at
   volume: assert no parse exceptions, spot-check field coverage + VN derivation,
   confirm rate-limit headers behave as expected and the throttle holds.
2. Review pilot output (coverage %, any unparsed sections, rate-limit budget
   consumed). Fix parser gaps against any failing fixtures (offline, from cache).
3. **Full sweep** over all ~4,439 distinct Madrid IRNs, throttled + resumable.

## 8. UI / search surfacing

Validated against an interactive HTML mockup (real IRN 1266721 data) before
implementation. Decisions locked from that review:

- **Provenance tags** — every WIPO-derived value wears a small `WIPO` badge to
  keep the two data lineages legible on one page (gazette-extracted vs
  WIPO-fetched). A Madrid mark with no record shows gazette fields only +
  `Source → ○ not enriched` — never fabricated data.
- **Mark detail** (Madrid marks only), top → bottom:
  - **Status pill** "Active · protected in VN" + a **🇻🇳 VN banner** (granted
    date · refusal · renewed · runs-through) as the headline.
  - **Claims row** gains WIPO fields: `Expiration (180)` and `Granted in VN`.
  - **"WIPO Madrid record" card** — holder/address/legal-nature/representative,
    registered, expiration (+ `renewed` badge), basic registration, language,
    and **designated jurisdictions** as flag chips (VN highlighted + GRANTED).
  - **Prosecution timeline (Vietnam-scoped, full-width)** — only events where VN
    is a party (IR designation → VN provisional refusal → grant → renewal), each
    label stripped of its trailing member-country list so it reads as a clean VN
    action. VN status itself is conveyed by the headline banner, so there is no
    separate status card; a WIPO provisional refusal the gazette later overrode
    is visible as its own timeline event. (Tradenet is a Vietnam product; other
    jurisdictions are noise here — the full set still appears as flag chips above.)
    The gazette "Procedural timeline" is hidden for Madrid marks (it has no
    procedural dates; this WIPO timeline supersedes it) and shown for domestic marks.
  - **Goods & services** (511, full per-class text from the WIPO fetch
    `goods_services`, keyed by Nice class; falls back to the gazette (511) text
    for VN-domestic files).
- **Sidebar**: `Source` gains a `● enriched` indicator; a new **Renewal watch**
  widget (next renewal due = expiration 180, “≈ N years · last renewed YYYY”).
- **Search**: a **"Designated jurisdiction"** filter (covers VN / covers country X)
  implemented as a join `trademarks → madrid_records` on `lineage_key`
  (`designated_countries` GIN-indexed). Optional `vn_status` filter.

Mockup reference: `/tmp/madrid_demo/full.html` (throwaway; not committed).

## 9. Testing

- **Parser**: pure unit tests against the saved `1266721.html` fixture — assert
  every INID field, the effective designation set, and the full VN timeline
  (incl. the 2025 renewal extending expiration to 2035).
- **Derive**: table-driven tests for granted / refused / pending / not-designated.
- **Client**: mocked HTTP; assert throttle, 429 backoff, circuit-break, cache hit.
- **Store**: upsert idempotency + content_hash skip.
- **API**: mark-detail enrichment payload; designated-jurisdiction filter returns
  the right Madrid rows.

## 10. Rollout

1. Alembic migration: `madrid_records` + indexes (`alembic check` excludes any
   expression indexes via the existing `env.py` hook if needed).
2. `madrid_enrich/` package + unit tests.
3. Backfill script; run pilot 100 → review → full sweep.
4. Worker hook.
5. API + frontend surfacing.
6. Refresh job (scheduled, status-aware TTL, capped + circuit-broken).
7. Docs: update `app/README.md` (endpoints + the new pipeline), `CLAUDE.md`
   (project layout: new `madrid_enrich/` package + `madrid_records` table).

## 11. Open questions

- Scheduler mechanism for the refresh job (RQ scheduled job vs cron vs a manual
  CLI invoked periodically) — decide at implementation time; the TTL/politeness
  logic is scheduler-agnostic.
- Exact daily cap + delay constants — start conservative (≤300/day, 2–4 s), tune
  from the pilot's observed rate-limit headers.
