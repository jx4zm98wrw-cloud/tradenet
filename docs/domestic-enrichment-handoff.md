# Domestic Trademark Enrichment — Handoff Brief

**For a fresh session.** This is a *pre-brainstorm* brief: read it, then go through
`superpowers:brainstorming` → `writing-plans` → `subagent-driven-development`.
Do **not** start coding before the scope decision below (lazy vs sweep) is made.

## Goal

Build the **domestic (IP Vietnam / NOIP) analog of the Madrid (WIPO) enrichment
pipeline** we already shipped. Fetch authoritative bibliographic data for
domestic Vietnamese trademarks from IP Vietnam's WIPOPublish detail endpoint,
parse it, store it, and surface it on the mark detail page — exactly like the
Madrid enrichment, but for the `domestic_application` / `domestic_registration`
marks instead of Madrid ones.

## The source (verified)

- **Endpoint:** `https://wipopublish.ipvietnam.gov.vn/wopublish-search/public/ajax/detail/trademarks?id=VN4202618514`
- It returns **fully server-rendered HTML** with every INID field present. The
  live page "displays almost nothing" only because its client-side JS (slick
  carousel + accordion in `details.min.js`) fails to render it — **irrelevant to
  us**: we fetch the raw HTML and parse server-side, exactly like Madrid (where
  we ignored WIPO's JS too).
- **Flaky:** it intermittently returns *"Internal Server Error"*. Treat like
  WIPO's 403s — cache the good responses, retry, circuit-break. Reuse the Madrid
  sweep-control circuit-breaker pattern.
- **ID format:** `VN` + type-code `4` + year `2026` + serial `18514` =
  `VN4202618514`. Our `trademarks.application_number` is `4-2026-18514` (or
  `VN-4-2026-18514`). Mapping: strip the `VN`/dashes, recompose → `VN4202618514`.
  **Confirm the format for older marks** (pre-2010 serials, different type codes)
  before trusting the mapping universally.

### INID fields available in the HTML (parse map)

The biblio section is `<div class="product-form-label">(NNN) Label</div>` +
`<div class="product-form-details">value</div>` pairs. Present:
`(540)` logo (image URL `…/service/trademarks/application/<ID>/logo`), `(100)`
grant number + date, status code (e.g. `1903`), `(180)` expiry, `(200)` app no.
+ filing date, `(400)` publication no. + date, `(541)` mark text (with `(VI)`
language prefix), `(591)` colours, `(300)` priority, `(511)` Nice classes + **per-
class goods** (each in `<a class="external-link" rel="NN">` + a goods `<div>`),
`(531)` Vienna codes, `(730)` applicant name + address (in `#apnaDiv`), `(740)`
representative, `(550)` mark type (Combined/word/figurative), `(526)` disclaimer.
Plus a documents table and a **process timeline** table (`Tiến trình xử lý`:
event / date / status). A full sample HTML is in the chat that produced this
brief — capture a couple of real responses as parser fixtures.

## Architecture — mirror `madrid_enrich/` almost 1:1

| Madrid (existing) | Domestic (to build) |
|---|---|
| `app/backend/madrid_enrich/` (client/parser/derive/store/enrich/backfill) | `app/backend/domestic_enrich/` (same shape) |
| `madrid_records` table (keyed by `irn`) | `domestic_records` table (keyed by `application_number`) |
| soft-join `madrid_records.irn == trademarks.lineage_key` | soft-join `domestic_records.application_number == trademarks.application_number` |
| `worker/madrid_sweep.py` (RQ job) + `madrid_sweep_control` table | analog *if* a sweep is chosen (see scope decision) |
| `api/routes/madrid_sweep.py` (start/pause/resume/stop/config) | analog *if* a sweep |
| `api/routes/admin.py` `/madrid-enrichment` stats + `app/(app)/admin/madrid` | analog admin panel |
| detail rendering in `app/(app)/marks/[id]/page.tsx` (`MadridEnrichment`, goods, timeline) | extend the same page for domestic enrichment |
| cache dir `madrid_cache/` | `domestic_cache/` |
| `PARSE_VERSION` in `madrid_enrich/store.py` | own `PARSE_VERSION` in `domestic_enrich/store.py` |

Read the Madrid files first — the domestic build is a structural copy with a
different fetch URL and a different HTML parser.

## ⚠️ THE decision to make first: scale → lazy vs sweep

- **Madrid was 4,440 unique IRNs.** Domestic is **~42,300**
  (`domestic_application` 19,412 + `domestic_registration` 22,904) — **~10×**.
- At the polite ~16s/fetch we measured (plus NOIP flakiness), a full upfront
  sweep is **~190 hours**. Not an overnight job.
- So domestic should probably **not** be a full upfront sweep. Options to weigh in
  brainstorming:
  1. **Lazy / on-demand**: enrich a mark the first time someone opens its detail
     page (fetch → cache → store), so only viewed marks cost a fetch. Cheapest,
     instant value, no 190h sweep.
  2. **Prioritized background sweep**: recently-published first, capped per day.
  3. **Hybrid**: lazy on view + a slow low-priority background sweep.
- This decision changes the whole shape (do we even need a sweep + control panel,
  or just an on-view `enrich_one` + cache?). **Decide it before specing.**

## Other open questions for brainstorming

1. **Reuse vs parallel package**: the HTML formats are entirely different, so a
   parallel `domestic_enrich` package is cleanest — but the sweep/control/admin
   infrastructure *could* be generalised. Decide how much to share.
2. **Which fields to surface** on the detail page (mirror the Madrid enrichment
   panel, adapted to domestic INID).
3. **Goods text**: domestic gazette `(511)` is often already parsed into
   `trademarks.raw_511_text`; the NOIP endpoint gives cleaner per-class goods —
   decide precedence (likely NOIP-authoritative like WIPO was for Madrid).
4. **ID mapping** robustness across years/type-codes.
5. **VN status / dates**: domestic marks have their own status codes (e.g.
   `1903`) — map to human labels.

## Standing constraints (carry over — important)

- **NEVER commit the "rename trio"**: `README.md` (repo root), `app/.env.example`,
  `app/backend/api/settings.py`. They stay as uncommitted working-tree changes.
  Always `git add` by **explicit path**; never `git add -A`/`.`.
- **GateGuard** fact-forcing hook: before the first Edit/Write per file (and first
  Bash per session) it blocks once and asks for facts — state them, then retry.
- **Fetch-once / re-derive-offline** (saved memory rule): once a fetch sweep runs,
  don't stop it for parser fixes. Fetching is the only slow/irreversible phase
  (cache to `domestic_cache/`); parsing/deriving is replayable offline via a
  `PARSE_VERSION` bump (zero NOIP calls). Apply parser fixes, then one offline
  re-derive over the cache. (This is exactly how we fixed the Madrid French-goods
  bug in minutes with no WIPO calls.)
- Dev stack: Postgres `:5435`, Redis `:6380`; backend env
  `TM_DATABASE_URL[_SYNC]`, `TM_REDIS_URL`; the RQ worker runs as a compose
  service (`docker compose -f app/docker-compose.yml up -d worker`).

## Suggested first moves in the fresh session

1. Read this brief + skim `app/backend/madrid_enrich/` (parser.py, enrich.py,
   store.py, backfill.py) and `api/routes/madrid_sweep.py` to internalise the pattern.
2. `curl` the endpoint for 2–3 real domestic app numbers (from
   `select application_number from trademarks where mark_category like 'domestic_%' limit 5`),
   save the HTML as parser fixtures.
3. Brainstorm the **lazy-vs-sweep** scope decision (the gating choice).
4. Spec → plan → build, mirroring Madrid.

---

*Context:* this brief was produced at the end of a very large Madrid-enrichment
session. The Madrid pipeline (detail UI, admin panel, controllable sweep, worker
service, multilingual goods) is fully merged to `main`. Domestic enrichment is the
next, larger sibling.
