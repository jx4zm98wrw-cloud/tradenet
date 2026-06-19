# Domestic Trademark Enrichment (Design)

**Status:** Approved for planning · 2026-06-19

**Goal:** Build the domestic (IP Vietnam / NOIP) analog of the Madrid (WIPO)
enrichment pipeline. Fetch authoritative bibliographic data for **all ~42,300
domestic Vietnamese trademarks** (`domestic_application` 19,412 +
`domestic_registration` 22,904) from IP Vietnam's WIPOPublish detail endpoint,
parse it, store it in `domestic_records`, and surface it on the mark detail page
— via a **controllable full sweep**, exactly mirroring the Madrid stack.

This is the largest single build of the trademark-enrichment effort: it recreates
the entire `madrid_enrich` stack (package + migration + sweep job + control
endpoints + admin panel + detail rendering + nav) for domestic marks.
**Recommended to implement in its own session off `main`.**

## The source — verified live (do not re-investigate; just build to it)

- **Endpoint:** `GET https://wipopublish.ipvietnam.gov.vn/wopublish-search/public/ajax/detail/trademarks?id=VN4202618514`
  — returns fully **server-rendered HTML** with every INID field. (The live page
  barely renders because its client JS fails; irrelevant — we parse the raw HTML.)
- **ID mapping:** our `trademarks.application_number` `4-YYYY-NNNNN` →
  `VN4YYYYNNNNN` (strip non-alphanumerics, prefix `VN`). Validated on 8 random
  marks. Guard older/odd formats before trusting universally.
- **Two real obstacles, both solved (see Fetch client):**
  1. **Broken TLS chain.** Leaf `*.ipvietnam.gov.vn` is issued by *"Sectigo
     Public Server Authentication CA DV R36"*, but the server presents the wrong
     intermediate -> OpenSSL `verify error 21 (unable to verify the first
     certificate)`. `curl`/browsers paper over it (OS trust + AIA); Python
     `certifi` hard-fails SSL. **This - not the server - is why naive Python
     fetches failed 100%.**
  2. **Cluster flakiness.** An Apache proxy fronts a Tomcat cluster with unhealthy
     nodes: ~50% of requests get an instant (~40ms) generic Apache `500`; the rest
     return the full ~18 KB HTML (~200ms) + a `JSESSIONID`. Stateless, fast,
     **retryable** - measured 1-3 attempts to success on random marks.

### INID parse map (fields present in the HTML)

Biblio section = `<div class="...product-form-label">(NNN) Label</div>` +
`<div class="...product-form-details">value</div>` pairs. A live sample
(`VN4202600774`, "VTRAVEL") yielded all of:
`(541)` mark text (`(VI)` lang prefix), `(550)` type (Combined/word/figurative),
`(591)` colours, status code (e.g. `1904`), `(200)` app no. + filing date, `(400)`
publication no. + date, `(100)` grant no. + date, `(180)` expiry, `(730)`
applicant **name + full address**, `(740)` representative **+ address**, `(511)`
Nice classes + **per-class goods text** (`<a class="external-link" rel="NN">` +
`<div class="col-md-10">goods</div>`), `(531)` Vienna codes, `(540)` logo URL
(`.../service/trademarks/application/<VNid>/logo`), `(300)` priority, `(526)`
disclaimer, and a **prosecution timeline** table (`Tien trinh xu ly`:
event / date / status).

## Architecture - parallel `domestic_enrich` stack (mirror Madrid 1:1)

Chosen over generalizing the Madrid machinery into a shared abstraction: the
Madrid stack works; duplicating the proven pattern avoids a risky refactor.
YAGNI on a generic enrichment framework until a 3rd source appears.

| Madrid (existing, copy from) | Domestic (build) |
|---|---|
| `app/backend/madrid_enrich/` (client/parser/derive/store/enrich/backfill) | `app/backend/domestic_enrich/` (same shape) |
| `madrid_records` (PK `irn`) | `domestic_records` (PK `application_number`) |
| join `madrid_records.irn == trademarks.lineage_key` | join `domestic_records.application_number == trademarks.application_number` |
| `worker/madrid_sweep.py` (RQ job) | `worker/domestic_sweep.py` (copy; new `domestic` queue) |
| `madrid_sweep_control` table | `domestic_sweep_control` table (copy) |
| `api/routes/madrid_sweep.py` (start/pause/resume/stop/config) | `api/routes/domestic_sweep.py` (copy) |
| `api/routes/admin.py` `/madrid-enrichment` stats + `app/(app)/admin/madrid` | `/domestic-enrichment` stats + `app/(app)/admin/domestic` |
| detail rendering in `marks/[id]/page.tsx` (`MadridEnrichment`) | `DomesticEnrichment` block on the same page |
| `madrid_cache/` | `domestic_cache/` |
| `PARSE_VERSION` in `madrid_enrich/store.py` | own `PARSE_VERSION` in `domestic_enrich/store.py` |
| `worker/run_worker.py` listens `ingest`,`madrid` | add `domestic` queue |

## Components

### 1. Fetch client (`domestic_enrich/client.py`)

- **TLS fix (portable, verification ON):** ship a CA bundle = `certifi` +
  the **Sectigo Public Server Authentication CA DV R36** intermediate (download
  from Sectigo's public CA repo, commit as `domestic_enrich/noip_ca_bundle.pem`),
  pass `verify=<bundle>`. Works in the Linux worker container/CI (deterministic).
  *Fallback:* `verify=False` + `urllib3.disable_warnings()` if the bundle proves
  fiddly - documented as a fallback only (read-only public data, no secrets sent).
- **Retry:** GET with up to ~10 attempts + short backoff (1-2s) + jitter until
  HTTP 200 **AND** body contains `product-form-label` (validate the body, not just
  status). Treat individual 500s as expected, not failures.
- **Cache:** write each success to `domestic_cache/<VNid>.html`; never re-fetch a
  cached id (fetch-once rule).

### 2. Parser (`domestic_enrich/parser.py`)

Regex-based (like Madrid), `parse(html) -> DomesticRecord`. Extract the INID
fields above. Capture 2-3 real fetched HTMLs as fixtures
(`tests/domestic_enrich/fixtures/`). Per-class goods keyed by zero-padded class.

### 3. Schema (Alembic migration)

- **`domestic_records`** (PK `application_number` text): `mark_text`,
  `applicant_name`, `applicant_address`, `representative`, `colors`,
  `nice_classes text[]`, `goods_services jsonb` (`{cls->text}`),
  `vienna_codes text[]`, `status_code`, `filing_date`, `publication_no`,
  `publication_date`, `grant_date`, `expiry_date`, `logo_url`,
  `timeline jsonb`, `raw text`, `content_hash`, `parse_version`,
  `fetched_at`, `updated_at`.
- **`domestic_sweep_control`** singleton - exact copy of `madrid_sweep_control`
  (status/cap/delay/jitter/chunk_size/processed/ok/failed/current/next/
  last_error/started_at/updated_at), renaming `*_irn` -> `*_appno`.

### 4. Sweep (`worker/domestic_sweep.py`)

Copy `madrid_sweep.py`: chunked self-re-enqueuing RQ job on the `domestic` queue,
cap/delay/jitter read each item, pause/stop honored per item, circuit breaker on
a **long** failure run (not individual 500s - those are expected). `JOB_TIMEOUT`
generous (chunk_size x per-item << timeout). Work-list = `iter_domestic_appnos()`
(distinct domestic `application_number`s) minus cached.

### 5. Control API + admin panel

`api/routes/domestic_sweep.py` (GET status + start/pause/resume/stop/config,
409-guarded) and a `/domestic-enrichment` stats endpoint. Frontend
`app/(app)/admin/domestic/page.tsx` mirrors `/admin/madrid` (progress bar, stat
cards, sweep-control card). Add a **"Domestic"** nav tab.

### 6. Detail page

`DomesticEnrichment` block on `marks/[id]/page.tsx` for domestic marks (applicant
address, representative, colours, per-class goods, Vienna, status, timeline).
**NOIP-authoritative** over the gazette parse (as WIPO was for Madrid): prefer
`domestic_records` goods/applicant when present.

## Error handling

- Bad sweep transition -> 409 (copy Madrid). Non-admin -> 403.
- Sustained NOIP outage (long 500 run) -> circuit-break -> `paused` + `last_error`.
- TLS failure at boot (bundle missing) -> fail fast with a clear message.
- Unmapped/odd application_number -> skip + log (don't crash the chunk).

## Testing

- **Parser:** fixtures from real fetched HTMLs -> assert all INID fields.
- **ID mapping:** unit tests (`4-2026-18514 -> VN4202618514`, odd formats).
- **Sweep:** state-machine + chunk tests (copy Madrid's, monkeypatch `enrich_one`).
- **Client:** retry logic with a stubbed flaky transport; body-validation.
- Endpoint tests for the control routes (start->running, 409s, 403).

## Non-goals

- No lazy/on-view enrichment (full sweep chosen).
- No generic multi-source enrichment framework (parallel stack; revisit on a 3rd source).
- Not fixing NOIP's server/TLS - we work around both client-side.

## Standing constraints (carry over)

- NEVER commit the rename trio (`README.md`, `app/.env.example`,
  `app/backend/api/settings.py`); `git add` by explicit path only.
- GateGuard fact-forcing hook (state facts on first Edit/Write per file + first Bash).
- Fetch-once / re-derive-offline: cache to `domestic_cache/`; parser fixes ->
  bump `PARSE_VERSION` -> one offline re-derive over the cache (zero NOIP calls).
- Worker runs as the compose `worker` service; add it to the `domestic` queue.

## Scale note

~42,300 marks x ~5s polite delay ~= **days** of fetching (longer with flakiness).
The cap/pause/resume controls (copied from Madrid) are exactly how an operator
runs it in capped batches. Cutover + re-derive flows mirror Madrid.
