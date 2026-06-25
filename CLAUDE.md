# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ Active punch list — read first

**Enterprise audit completed 2026-05-29.** 28 confirmed P0/P1 findings, untouched.

- **Plan + remediation steps**: [`AUDIT_2026_05_29_PLAN.md`](AUDIT_2026_05_29_PLAN.md) (60KB)
- **Raw evidence per finding (incl. P2/P3)**: [`audit_2026_05_29.json`](audit_2026_05_29.json) (142KB)

Recommended next-session entry point: open the plan, pick PR A (authz lockdown — blocks production launch). PRs A/B/C are independent; D-I sequenced after.

## Overview

Project began as a single Python tool (`TM_csv_builder.py`) extracting Vietnamese trademark gazette data from IP VIETNAM PDF publications into per-PDF CSVs. It has since grown into a workbench: **FastAPI + Postgres + RQ worker + Next.js 15 frontend**, with the original CSV parser vendored into `app/backend/tm_extractor/` and a separate logo extractor wired in via the worker.

Two gazette types share the parsing pipeline: **A** (applications, section starts at `(210)`) and **B** (registrations, section starts at `(111)` or `(116)`, including Madrid international registrations). Type is inferred from the filename's first letter (case-insensitive).

## Project layout

```
claude_csvbuilder/
├── app/
│   ├── backend/                    Installable Python package `tm-backend`
│   │   ├── api/                    FastAPI app + SQLAlchemy models
│   │   │                           (incl. `_filename.py`: single source of truth
│   │   │                           for IP VIETNAM filename parsing, imported by both
│   │   │                           routes/gazettes.py and worker/ingest.py)
│   │   ├── worker/                 RQ jobs (ingest pipeline lives here)
│   │   ├── tm_extractor/           Vendored CSV parser (was TM_csv_builder.py)
│   │   ├── madrid_enrich/          WIPO Madrid Monitor enrichment package
│   │   │                           (client/parser/derive/store + enrich_one).
│   │   │                           Populates `madrid_records` (keyed by IRN,
│   │   │                           soft-joined to `trademarks.lineage_key`)
│   │   │                           with WIPO-fetched Madrid bibliographic data.
│   │   │                           Admin progress view: GET
│   │   │                           /api/v1/admin/madrid-enrichment →
│   │   │                           app/(app)/admin/madrid reports coverage
│   │   │                           (unique IRNs vs validated vs remaining),
│   │   │                           all derived live from the DB.
│   │   │                           Sweep is a controllable RQ job on the
│   │   │                           `madrid` queue; admin start/pause/resume/
│   │   │                           stop/tune at /api/v1/admin/madrid-sweep
│   │   │                           (worker must be running). "Fast mode"
│   │   │                           (self-contained `fast_mode/` package:
│   │   │                           rate-feedback controller + threaded
│   │   │                           per-thread-event-loop runner) is a higher-
│   │   │                           throughput sweep path that paces concurrency
│   │   │                           to WIPO's PUBLISHED X-RateLimit budget
│   │   │                           (Limit≈1000; X-RateLimit-Reset is unusable,
│   │   │                           so it paces off Remaining): step concurrency
│   │   │                           up while Remaining is healthy, down near a
│   │   │                           floor, pause on 429/Retry-After. Unlike
│   │   │                           domestic Dead mode it does NOT AIMD-probe for
│   │   │                           bans (WIPO hands you the limit) and does NOT
│   │   │                           auto-revert. The normal sweep delegates via
│   │   │                           one `if mode=='fast'` branch; toggled from
│   │   │                           /admin/madrid (mode/concurrency cols on
│   │   │                           madrid_sweep_control). client.fetch_raw
│   │   │                           surfaces X-RateLimit-Limit and raises
│   │   │                           WipoThrottledError on 429.
│   │   ├── domestic_enrich/        IP VIETNAM domestic enrichment package
│   │   │                           (idmap/client/parser/derive/store/enrich/backfill).
│   │   │                           Populates `domestic_records` (keyed by
│   │   │                           `application_number`, soft-joined to
│   │   │                           `trademarks.application_number`) with
│   │   │                           IP VIETNAM-fetched bibliographic data. Fetch client
│   │   │                           ships a committed Sectigo R36 CA bundle to fix
│   │   │                           IP VIETNAM's broken TLS chain and retries the flaky
│   │   │                           cluster. Admin progress view: GET
│   │   │                           /api/v1/admin/domestic-enrichment →
│   │   │                           app/(app)/admin/domestic reports coverage
│   │   │                           (unique appnos vs validated vs remaining),
│   │   │                           all derived live from the DB.
│   │   │                           Sweep is a controllable RQ job on the
│   │   │                           `domestic` queue; admin start/pause/resume/
│   │   │                           stop/tune at /api/v1/admin/domestic-sweep
│   │   │                           (worker must be running).
│   │   │                           Frontend surfacing COMPLETE (Plans A+B+C
│   │   │                           done): /admin/domestic ops panel (coverage
│   │   │                           stats + sweep start/pause/resume/stop/tune);
│   │   │                           mark API returns `domestic` field joined from
│   │   │                           `domestic_records`; `DomesticEnrichment`
│   │   │                           block on the mark detail page shows IP VIETNAM-
│   │   │                           authoritative applicant/address, goods &
│   │   │                           services (per-class, fed into GoodsServices),
│   │   │                           Vienna codes, colors, status, filing/
│   │   │                           publication/grant/expiry dates, and a
│   │   │                           `DomesticTimeline` prosecution timeline card.
│   │   │                           Mark-name fallback chain extended to also use
│   │   │                           `domestic.mark_text`. Domestic epic complete.
│   │   │                           "Dead mode" (self-contained `dead_mode/`
│   │   │                           package: AIMD controller + threads-fetch/
│   │   │                           coroutine-stores runner + safety valve) is a
│   │   │                           max-throughput adaptive-concurrency sweep
│   │   │                           path. The normal sweep delegates via one
│   │   │                           `if mode=='dead'` branch; toggled live from
│   │   │                           /admin/domestic (control row `mode`/
│   │   │                           `concurrency` cols). Auto-reverts to normal +
│   │   │                           pauses on sustained IP VIETNAM blocks.
│   │   │                           NOT-PUBLISHED handling: IP VIETNAM returns HTTP 200
│   │   │                           + a ~2,178-byte skeleton (no `product-form-
│   │   │                           label` marker) for app numbers it hasn't
│   │   │                           published a detail for yet — a DEFINITIVE
│   │   │                           negative, not flakiness. `client.fetch_raw`
│   │   │                           classifies this as `outcome="not_found"`
│   │   │                           (returns at once, no retry, not cached);
│   │   │                           `enrich.enrich_one` returns
│   │   │                           `EnrichOutcome.NOT_FOUND` and records the mark
│   │   │                           in the `domestic_not_found` negative-cache
│   │   │                           table (appno PK, vnid, first/last_checked_at,
│   │   │                           check_count). The sweep work-list EXCLUDES
│   │   │                           marks recorded not-published within a 30-day
│   │   │                           backoff window (`_NOT_FOUND_BACKOFF`), so it
│   │   │                           CONVERGES (records each empty mark once, then
│   │   │                           skips it; re-checks after the window as IP VIETNAM
│   │   │                           publishes). A not_found is NOT a failure — it
│   │   │                           does not increment `failed` or the
│   │   │                           consecutive-failure breaker streak (this
│   │   │                           de-wedges the front-of-list deadlock that
│   │   │                           froze the sweep at ~5,806 remaining); it bumps
│   │   │                           a separate `not_found` counter. The
│   │   │                           /domestic-enrichment endpoint splits
│   │   │                           `remaining` into `pending_publication` (in
│   │   │                           domestic_not_found, unvalidated),
│   │   │                           `unresolved` (fetchable backlog), and
│   │   │                           `malformed` (appno_to_vnid is None — the
│   │   │                           truncated `4-2024-1` class that can't map to
│   │   │                           an IP VIETNAM id; needs a manual appno fix),
│   │   │                           all shown on /admin/domestic with the
│   │   │                           malformed appnos listed (appno/applicant/
│   │   │                           gazette) for review. The sweep CONVERGES on
│   │   │                           malformed appnos: `_worklist` (and dead mode's
│   │   │                           todo) EXCLUDE them (`appno_to_vnid(a) is None`)
│   │   │                           the same way `recent_not_found` is excluded —
│   │   │                           knowable from the appno string alone, so no
│   │   │                           negative-cache is needed; they never reach
│   │   │                           enrich_one and stop wasting a chunk slot every
│   │   │                           pass. Defensively, if an UNMAPPABLE outcome
│   │   │                           still reaches run_chunk it is NOT counted as
│   │   │                           `ok`/`failed` and does not advance the breaker
│   │   │                           streak. Admin re-check control:
│   │   │                           POST /api/v1/admin/domestic-sweep/recheck-
│   │   │                           pending resets the not_found backoff on all
│   │   │                           unvalidated marks (timestamp reset, preserves
│   │   │                           check_count/first_seen_at) and kicks one
│   │   │                           normal-mode chunk if idle, re-probing pending
│   │   │                           marks now instead of waiting out the 30-day
│   │   │                           window — surfaced as a "Re-check pending (N)"
│   │   │                           button on /admin/domestic. Orphan negative-
│   │   │                           cache hygiene: a domestic_not_found row whose
│   │   │                           appno is no longer a current domestic-category
│   │   │                           trademark (re-ingested/re-categorized) inflates
│   │   │                           `pending_publication` above `remaining`.
│   │   │                           `store.reconcile_not_found` deletes those
│   │   │                           orphans (run via `python -m
│   │   │                           scripts.reconcile_domestic_not_found`),
│   │   │                           restoring the exact `pending + unresolved +
│   │   │                           malformed == remaining` bucket split.
│   │   ├── image_extractor/        Vendored logo extractor (was Final_TRADEMARK_image_extractor_refine.py)
│   │   ├── tm_similarity/          Standalone pure conflict-similarity engine
│   │   │                           (stdlib + jellyfish only; no FastAPI/
│   │   │                           SQLAlchemy/filesystem). Reads a
│   │   │                           `MarkFeatures` DTO (mark_text + precomputed
│   │   │                           `trademarks.logo_phash` hex + nice_classes +
│   │   │                           vienna_codes) → `ScoreResult` via `score()`.
│   │   │                           Axis-per-file (phonetic/visual/classes/
│   │   │                           composite) + features (DTOs) + `__init__`
│   │   │                           (public API, `SIMILARITY_VERSION`). The
│   │   │                           visual axis does pure integer Hamming on the
│   │   │                           stored hex pHash — the pHash is computed by
│   │   │                           `api/_phash.py` (the ONLY module importing
│   │   │                           Pillow/imagehash for similarity) at ingest
│   │   │                           (`worker/ingest.py`) and via the idempotent
│   │   │                           backfill `scripts/backfill_logo_phash.py`.
│   │   │                           **Re-run `scripts/backfill_logo_phash.py`
│   │   │                           after a fresh ingest** (same caveat as
│   │   │                           `mark_name` / `vn_grant_date`; note new
│   │   │                           ingests also self-populate it). Extracted
│   │   │                           from the former `api/similarity.py`
│   │   │                           (deleted) — strictly behaviour-preserving
│   │   │                           (golden test
│   │   │                           `tests/test_tm_similarity_engine.py`).
│   │   ├── alembic/                Migrations
│   │   ├── scripts/                One-off scripts (smoke_ingest.py;
│   │   │                           reconcile_domestic_not_found.py prunes orphan
│   │   │                           domestic_not_found rows)
│   │   ├── tests/                  pytest suite (httpx + ASGI)
│   │   ├── pyproject.toml          Lint, type-check, package config
│   │   ├── requirements.txt        Pinned runtime deps (includes pymupdf etc. for image_extractor)
│   │   └── Dockerfile              Multi-stage prod build (PYTHONPATH-based)
│   ├── frontend/                   Next.js 15 (App Router) + Tailwind 4
│   │                               In-product UI today. Marketing site
│   │                               (Landing/Pricing/Coverage/Docs/Login) ships
│   │                               into this same app as a `(marketing)/`
│   │                               Route Group — see
│   │                               design_handoff_tradenet_marketing/IMPLEMENTATION_PLAN.md
│   ├── docker-compose.yml          Local dev stack (postgres :5435, redis :6380,
│   │                               + dedicated RQ workers, one per queue:
│   │                               `worker-ingest`/`worker-madrid`/`worker-domestic`
│   │                               (isolated parallel throughput; share an
│   │                               `x-worker-base` anchor). run_worker reads
│   │                               `TM_WORKER_QUEUES` — unset = all queues)
│   └── README.md                   Setup + dev workflow
├── design_handoff_trademark_gazette/   In-app design reference (already implemented)
├── design_handoff_tradenet_marketing/  Marketing site design reference (planned)
│                                       README.md describes the design;
│                                       IMPLEMENTATION_PLAN.md captures the
│                                       architecture decision (Route Groups),
│                                       PR sequence (Landing → Pricing → Login
│                                       → Coverage → Docs), and CMS choice
│                                       (MDX-in-repo + TS config).
├── config_image_extractor.yaml     Runtime config for image_extractor (read by worker.ingest)
├── input/                          Source PDFs
├── csv/                            Legacy CSV outputs (still produced by tm_extractor for parity)
├── image/<year>/<pdf_stem>/        Extracted logo PNGs (served at /static/image/)
├── modified/<year>/<pdf_stem>/     Blank-page-stripped PDFs the extractor works on
├── image_link/<year>/              Per-PDF image-link CSVs from the extractor
├── log/                            Rotating processing log (1 MB × 5)
├── TM_csv_builder.py               Original standalone CSV builder (still runnable; kept for parity)
├── TM_csv_builder_legacy.py        Earlier snapshot of the standalone builder
├── cities_by_country.json          { ISO2: [city, …] } (~10 MB, ~525K names)
├── cities_overrides.json           Manual add/remove patches applied over the GeoNames build
└── company_suffixes.json           ~500 curated company-indicator tokens
```

## Run

### Full dev stack (FastAPI + worker + frontend)

```bash
docker compose -f app/docker-compose.yml up -d            # postgres :5435, redis :6380
python3 -m venv app/.venv && source app/.venv/bin/activate
pip install -r app/backend/requirements-dev.txt
pip install -e app/backend                                # installs the `tm-backend` package
cd app/backend && alembic upgrade head
uvicorn api.main:app --reload --port 8000                 # backend
# in another terminal:
cd app/frontend && pnpm install && pnpm dev               # frontend on :3000
```

`pip install -e app/backend` puts `api`, `worker`, `tm_extractor`, `image_extractor`, and `scripts` on `sys.path`. The Docker image still uses `PYTHONPATH=/srv/backend` (frozen-build artifact, not a dev environment).

Smoke-test one PDF through the worker synchronously:
```bash
cd app/backend
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m scripts.smoke_ingest /abs/path/to/A_T2_2026.pdf
```

### Legacy single-script flow (CSV only, no DB/UI)

```bash
python3 TM_csv_builder.py
```

Interactive prompt — `1` processes all PDFs in `input/`, `2` accepts comma-separated indices. Dependencies (no requirements.txt): `pdfplumber pandas numpy colorama tqdm`.

Useful when you just want CSVs of the same gazette content without standing up the full stack.

## Data files

Inputs and outputs live at the project root (alongside the legacy script, since the worker resolves `data_dir` to the project root via `api.settings.Settings.data_dir`). Missing data files don't crash either entrypoint — they log an error and degrade gracefully.

## Architecture

### Pipeline (`PDFProcessor`)

1. **`extract_text_from_pdf`** — pdfplumber page-by-page; each page goes through `_extract_page_text` (column-aware, below), then `add_breaks_before_markers` injects newlines so every WIPO INID marker (`(NNN)`) starts its own line. Output: `[(page_num, line), …]`. **Constant memory**: pdfplumber caches every parsed page (chars/rects/lines + the LRU text map) on the `Page` instance and keeps all `Page` objects alive for the whole `with pdfplumber.open(...)` block, so RSS grows ~linearly (~3.7 MB/page). Whether that OOM-kills the worker is a **memory-budget** threshold, not a fixed page count: the wall is roughly `(container RAM) ÷ ~3.7 MB/page` — ~1,900 pages at 8 GB, ~3,900 at 16 GB. This is why the 2026 batch (incl. 4,011-page `B_T4_2026`) ingested fine under a larger Docker VM, yet once the VM was ~8 GB the *smallest* big file, `A_T6_2026` (1,972 pp), crossed the wall (~page 1,855) and had to be split into `A_T6_1`/`A_T6_2`. The loop calls `page.close()` after each page's text is extracted (clears `cached_properties` + `get_textmap`'s LRU cache), holding peak RSS flat (~0.5 GB on the 3,845-page `A_T7_2025.pdf`, independent of page count or VM size). The flush runs only after extraction, so output is byte-identical.

2. **`_extract_page_text` (column-aware)** — Critical. The Madrid certificate section of B-files uses a **two-column layout**. Flat `extract_text()` interleaves left+right at each y-coordinate, corrupting markers like `(171) 10 năm` with right-column continuations of `(531)`/`(732)`. Detection is a **ratio test**: a page falls back to single-column when more than ~10% of its words straddle the midpoint (`crossing > max(10, 0.10 * len(words))` in [processor.py](app/backend/tm_extractor/processor.py)). Real 2-column pages typically have a handful of crossers (long dates, Vienna codes spanning a frame, headers) — an absolute cutoff was too brittle. For 2-column pages, the code:
   - Finds entry boundaries via `(111)`/`(116)` markers in the left column.
   - Within each entry's y-range, emits **left-column text, then right-column text**.
   - **Within each entry, switches back to single-column from `(511)` onward**, because the Nice-classification list spans the full page width even on 2-column pages. Splitting `(511)` at the midpoint would send trailing classes into `(740)` (this was a real bug, fixed).
   - Single-column pages and A-file pages fall through to `page.extract_text()`.

3. **`process_sections`** (generator) — state-machine over the line stream, yields one `dict` per trademark. Three mutually-exclusive accumulator flags (`accumulating_511`, `accumulating_531`, `accumulating_540`) collect multi-line fields. Section-start markers determine gazette type:
   - Filename starts with `b`/`B` → gazette `B`, start markers `(111)` or `(116)`.
   - Otherwise → gazette `A`, start marker `(210)`.

4. **Per-section enrichment** before yield:
   - **`compute_511_fields`** — extracts Nice classes. Two grammars: `Nhóm NN`-style (VN A-file), or bare numeric list `"05, 12, 41."` (Madrid B). Rejoins line-wrapped Vietnamese broken words via digraph + onset-aware regex passes (`công nghiệp` stays separate, `phẩ m;` rejoins to `phẩm;`).
   - **`extract_applicant_details`** — parses `(731)`/`(732)`. Multi-applicant numbered lists (`"1. NAME1 (CC) ADDR1 2. NAME2…"`) are reduced to **first applicant only**. Country code prefers the first valid ISO 3166-1 alpha-2 token from any `(XX)` in the text (handles `MEISHANG (GZ) … (CN)` correctly). City matcher uses pre-compiled per-country alternation regex (`CITY_PATTERNS`) with `\b` boundaries, run against the **parsed Applicant Address only** (not the full applicant text — Vietnamese name fragments like `Hồng Lĩnh` collide with real city names). Pick the LATEST match (universal rule, valid after the cities JSON was cleaned of provinces/state-codes). **VN-only fallback**: if no city matched, capture the province name from `tỉnh X` at the address tail.
   - **`classify_applicant_type`** — priority chain:
     1. Strip leading `"N. "` enumerator
     2. `STRONG_COMPANY_SUFFIXES` (curated set, ~50 unambiguous tokens) → `Company`
     3. `TYPO_TOLERANT_COMPANY_PATTERNS` (regex stems like `corp[a-z]*`, `industri[a-z]*` — catches `CORPORTION` typo, Croatian `INDUSTRIJA`) → `Company`
     4. First token ∈ `VN_SURNAMES` → `Personal`
     5. Broader JSON `COMPANY_SUFFIXES` → `Company`
     6. Otherwise → `Personal` (no `Unknown` — applicants are always one or the other)

     All suffix matching uses `(?<!\w)…(?!\w)` lookarounds with `re.IGNORECASE` so suffixes ending in punctuation (`S.R.O.`, `Co.,Ltd`) and Turkish/Unicode case quirks (`İ` → `i̇`) work correctly.

   - **`add_date_fields`** — `Month`/`Year`/`DateCombined_441_450` derived from the **first** `(441)`/`(450)` matched in the PDF (`self.first_date`). Per-file reset in `process_file`.
   - **`validate_540_content`** — `(540)` purely-numeric → blank; Vienna-code-shaped → moved into `(531)`.

5. **`create_csv`** — DataFrame, lowercases every string cell **except the `(540)` Trademark sample** column (wordmark case is meaningful), rename code columns to `"NNN <description>"`, write `utf-8-sig`. Column headers and non-string values (e.g., `Total Group` ints) are not lowercased. **Excel cell-limit handling**: `(511)` cells exceeding 32,767 characters (Excel's per-cell hard limit) are truncated in the CSV with a marker and the full text is dumped to a sidecar `<stem>_511_overflow.txt` keyed by registration number. Other columns never approach the limit. For B-files, `process_file` first partitions sections by `(116)` non-empty: domestic `(111)` rows go to `<stem>.csv`, Madrid `(116)` rows go to a parallel `<stem>_madrid.csv`. The two schemas don't overlap (every B row has exactly one of `(111)` / `(116)`), so the split is lossless and each output file is schema-clean.

### Concurrency

`ThreadPoolExecutor` is wired but `max_workers=1` is hardcoded in `main()`. Two reasons:
- pdfplumber isn't thread-safe.
- `self.first_date` lives on the `PDFProcessor` instance and is reset per file — concurrent execution would interleave reads/writes and corrupt date fields across PDFs.

### Worker + image extractor (web stack only)

`app/backend/worker/ingest.py:ingest_pdf` orchestrates one PDF through:
1. `_run_image_extraction` lazy-imports `image_extractor` (the vendored package re-exports `PDFProcessor as ImageExtractor` and `ProcessingPaths as ImagePaths` to avoid colliding with `tm_extractor.PDFProcessor`) and runs `_modify_pdf` (blank-page removal via PyMuPDF) → `_extract_images` (per-sector PNGs into `image/<year>/<stem>/`) → `_create_image_link_csv`. Failures degrade to `logo_path = NULL`; the CSV ingest still proceeds. `_save_page_images` detects when the clustering step has merged image rects across sector boundaries (rect contains additional marker label y-positions past the +20 best-tolerance band) and splits the merged image at each interior boundary, saving per-label crops — without this, adjacent-sector logos within `cluster_threshold=80px` of each other would collapse into a single PNG assigned to only the topmost sector. The import is kept lazy so worker boot doesn't pay the pymupdf/PIL/pdfplumber load cost, and so tests can monkey-patch `sys.modules["image_extractor"]` with a fake before the import runs.
2. The tm_extractor parser produces sections (same logic as the legacy script).
3. `mapper.section_to_trademark` materializes a `Trademark` row; `_resolve_logo_path(section, image_subdir, image_root)` probes `image/<year>/<stem>/<(210)>.png` → `<(111)>.png` → `<(116)>.png` in that order and stores the first hit's path **relative** in `trademarks.logo_path`. Madrid `(116)` lookups also try letter-suffix variants `<id>A.png` through `<id>Z.png` for WIPO modifications/renewals; `(210)` and `(111)` use exact match only.

All backend imports resolve through the editable install — there are no `sys.path.insert` calls in production code. FastAPI mounts `data_dir/image` at `/static/image/`; Next.js proxies `/static/*` to the backend. `markDisplay()` on the frontend prepends `/static/image/` to `logo_path` and feeds it to every `MarkSpecimen` call site.

### Entity canonicalization (Phase 2)

`trademarks` carries denormalized `applicant_clean`/`applicant_norm` +
`representative_clean`/`representative_norm` (migration `20260622_0023`;
`*_norm` btree-indexed). Resolved per mark by deterministic identifier —
IP VIETNAM (`domestic_records`) → WIPO (`madrid_records`) → gazette fallback — by
`scripts/backfill_entity_clean.py` (re-runnable, idempotent via
recompute-and-compare; `ENTITY_CLEAN_VERSION` in `api/_entity_norm.py`).
`/overview` domestic applicant/representative panels `GROUP BY *_norm`;
Madrid panels stay per-IRN over `madrid_records` (counts unchanged from
Phase 1). The ingest worker does NOT populate these columns, so marks from
gazettes ingested after the last backfill have `NULL *_norm` and are omitted
from the domestic panels (which filter `*_norm IS NOT NULL`) until the
backfill is re-run — re-run `scripts/backfill_entity_clean.py` after a fresh
ingest. See `docs/superpowers/specs/2026-06-22-entity-canonicalization-design.md`.

### Search grant-status filter

`trademarks.vn_grant_date` (nullable date, btree-indexed; migration
`20260624_0027`) is the **unified VN registration grant date**: resolved per
mark by identifier from the trusted source — domestic ← `domestic_records.grant_date`
(by `application_number`); Madrid ← `madrid_records.vn_grant_date` when
`vn_status='granted'` (by `lineage_key = irn`); else NULL. Written by
`scripts/backfill_vn_grant.py` (re-runnable, idempotent recompute-and-compare,
`VN_GRANT_VERSION`; same `ids=`-scoped/stats-dict shape as
`backfill_entity_clean`). The ingest worker does NOT populate it — **re-run the
backfill after a fresh ingest/enrichment.** The `/search` page reads it through
a clean `granted: bool` filter (`vn_grant_date IS NOT NULL`, indexed, no
per-query join) + a `GET /api/v1/facets/granted` count (~141,961 = domestic +
Madrid grants — note a domestic appno present as both an application and a
registration row is counted under each). `grant_date_from`/`grant_date_to` also
range over this column. This **replaced** the old Madrid-only "Granted in VN"
facet (`madrid_records.vn_status='granted'`, ~18,994, which silently dropped
~100k domestic grants) and dropped the universal-and-useless "Protected in VN"
facet. `vn_status` + `/api/v1/facets/vn-status` are retained for
`/api/v1/trademarks`. See
`docs/superpowers/specs/2026-06-24-search-grant-status-design.md`.

### Resolved mark name

`trademarks.mark_name` (nullable text, btree-indexed; migration
`20260624_0028`) is the **resolved display name** every surface reads, fixing
~172k domestic marks that previously showed the *applicant* as their name.
Resolved per mark from the trusted source: `mark_sample` (non-empty) →
domestic ← `domestic_records.mark_text` (by `application_number`) | Madrid ←
`madrid_records.mark_text` (by `lineage_key = irn`) → NULL (figurative, no
transcribed name anywhere — ~7.5k rows). Written by
`scripts/backfill_mark_name.py` (re-runnable, idempotent recompute-and-compare,
`MARK_NAME_VERSION`; same `ids=`-scoped/stats-dict shape as
`backfill_vn_grant`). The ingest worker does NOT populate it — **re-run the
backfill after a fresh ingest/enrichment.** Serialized on `TrademarkOut`, so
search/cmdk/compare/exports/watchlists/today all get it with no per-payload
join. The frontend `markDisplay` (`lib/mark-display.ts`) resolves the wordmark
as `markText ?? mark_name ?? mark_sample` and renders `"(figurative mark)"`
(never the applicant) when none exists. Display-only: search ranking still
matches `mark_sample`/`applicant_name` (`search.py`). See
`docs/superpowers/specs/2026-06-24-mark-name-resolution-design.md`.

### Visual axis routing (Track 1)

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
as logo_phash / mark_name / vn_grant_date). See
`docs/superpowers/specs/2026-06-25-visual-axis-routing-recalibration-design.md`.

## Data files

### `cities_by_country.json`

Built from GeoNames `cities500` (populated places, pop ≥500), Latin-script only (CJK / Cyrillic stripped — the gazette transcribes everything to Latin), with VN-specific enrichment:
- VN admin prefix stripping (`Thành phố Hồ Chí Minh` → `Hồ Chí Minh`)
- VN sub-city admin units dropped (`Quận Ba`, `Phường X`, `Xã Y` exclusions)
- Vietnamese diacritic normalization (`Ð` U+00D0 → `Đ` U+0110)
- HK + MO cities mirrored into the CN bucket because the gazette tags Hong Kong/Macao applicants with `(CN)`

To rebuild:
```bash
mkdir -p geonames_tmp
curl -sSfL -o geonames_tmp/cities500.zip https://download.geonames.org/export/dump/cities500.zip
unzip -o geonames_tmp/cities500.zip -d geonames_tmp/
python3 build_cities_json.py
```

Manual additions/removals (e.g., to fix a misclassified town) go in `cities_overrides.json` — they're layered on top of the GeoNames build and survive every rebuild. Shape:
```json
{ "add":    { "VN": ["Some Missing Town"] },
  "remove": { "GB": ["Street"] } }
```

### `company_suffixes.json`

~500 Latin-script tokens. Sorted, deduped (case-insensitive via NFC+casefold), mojibake-free. Includes English forms (LTD, INC, COMPANY, …), continental European (GMBH, S.A., SARL, SPA, S.R.O., Sp. z o.o., …), Vietnamese (CÔNG TY, TỔNG CÔNG TY, …), Russian transliterations (OBSHCHESTVO, OOO, …), Chinese pinyin (GONGSI, YOUXIAN), Japanese romanized (SHADANHOJIN, …), and institutional words (UNIVERSITY, INSTITUTE, BANK, FOUNDATION, …).

Curated `STRONG_COMPANY_SUFFIXES` and `TYPO_TOLERANT_COMPANY_PATTERNS` live in `app/backend/tm_extractor/constants/classifier.py` (barrel-exported through `tm_extractor/constants/__init__.py`) — these win over the VN-surname signal in classification.

## When changing extraction logic

- **Adding a marker**: append a `MarkerConfig` to `MARKERS`, regex to `PATTERNS`, code to `CSV_COLUMNS`. Markers absent from `PATTERNS` still match via the fallback branch in `extract_markers_from_line` but get no value transformations.
- **Date markers** (`141/151/156/181/220/441/450`): listed twice — in `extract_markers_from_line`'s reformatting branch (line ~926) and the fallback branch's date-validity guard (~1018). The guard rejects extraction artifacts like `(cid:31) MERGEFIELD …`.
- **`(531)` regex** is intentionally non-greedy with a lookahead to stop at the next marker; the older greedy version is preserved as a comment.
- **Column-aware extraction** is the single most fragile piece. If new gazette layouts emerge (e.g., 3-column, or `(511)` no longer full-width), revisit `_extract_page_text` first.

## Known residual issues

These are PDF-source-level artifacts that no parser can fix without external data:

- **12 B rows have a Madrid registration number in `(732)`** (was ~14), e.g. `"(732) 1529250 (DE) Jack Wolfskin …"` — the IP VIETNAM PDF itself transcribed a previous-registration cross-reference into the (732) line. Detected by `scripts/audit_fields.check_madrid_number_in_applicant`.
- **0 B rows have only an address fragment in `(732)`** (was ~7) — cleared. The CLAUDE.md baseline was inflated by an over-eager detection regex; the tightened pattern (`scripts/audit_fields.check_address_fragment_in_applicant`) finds none post-reset.
- **31 VN rows have no `Applicant City`** — both the city matcher and the `tỉnh X` province fallback found nothing. Mostly truncated addresses.
- **7 B rows have neither a logo PNG nor `(540)` text** (CARMEDA, ALLM, CASTROL, TOPPAN HOLDINGS, TOPGOLF CALLAWAY, EGIS, TOTO). The gazette page has no figurative-element metadata at all — no Vienna `(531)`, no protected colors `(591)`, no transcribed wordmark. Unrecoverable without re-OCRing the original IP VIETNAM PDF pages.

Combined-mark coverage (logo OR `(540)`): **99.985%** across 46,758 rows over 8 gazettes (4 A-files at 100.00%, B-files 99.92-100%). Applicant-data residuals are separate from mark-display residuals and add ~0.1% more rows with degraded fields.

### Audit tooling

Two scripts under `app/backend/scripts/` exist for periodic data-quality
re-audit (e.g., after extractor changes or a fresh ingest):

- **`audit_logos.py`** — PyMuPDF ground-truth scan that walks each input
  PDF, counts image XObjects per INID section using the same nearest-marker-
  above mapping the extractor's saver uses, and flags any section where the
  PDF has an image but the DB row has `logo_path = NULL`. Tunable threshold
  via `AUDIT_MIN_IMAGE_PX` env var (default 50 px; drop to 20 for stricter).
- **`audit_fields.py`** — eight automated checks codifying the residual
  patterns above (Madrid# in applicant, address fragment in applicant,
  VN missing city, NEITHER (540) nor logo, B-domestic missing (151),
  invalid Nice classes, marker leakage in (540), year/month vs pub date).
  Each check reports count vs documented baseline + delta — delta > 0
  flags a regression.

A full reset + re-audit ran 2026-05-27 — surfaced and fixed a real
`MIN_SLICE_PX = 20` regression in the image extractor that was
dropping small-raster logos (e.g., gazette wordmark strips at 100×12-18 px).
Recovered 21 lost logos across A_T3/A_T4/B_T2/B_T3/B_T4. The 7
unrecoverable NEITHER cases above match the documented list exactly.

## Marketing site (planned, not yet implemented)

The public marketing site (Landing / Pricing / Coverage / Docs / Login) ships
into the **same `app/frontend/` Next.js codebase** as a `(marketing)/`
Route Group, alongside an `(app)/` group for the existing authenticated
pages. Same tokens, same Tailwind 4 config, same CI gates — one app, two
layouts.

**Design reference:** `design_handoff_tradenet_marketing/` — open
`Tradenet - Marketing.html` via a local HTTP server (`python3 -m http.server 8765`)
and click through the top nav to see all five routes.

**Plan of record:** [`design_handoff_tradenet_marketing/IMPLEMENTATION_PLAN.md`](design_handoff_tradenet_marketing/IMPLEMENTATION_PLAN.md)
— architecture decision (Route Groups in the existing Next.js app), CMS
choice (MDX-in-repo + TS config, no external service), open-question
resolutions, and the PR sequence:

  - **PR 0** — Token reconciliation (`--container`, `--radius-lg`,
    `--radius-xl`, `--shadow-lg`)
  - **PR 1** — Landing (`/`)
  - **PR 2** — Pricing (`/pricing`)
  - **PR 3** — Login two-pane (`/login`, replaces current simple form)
  - **PR 4** — Coverage (`/coverage`)
  - **PR 5** — Docs (`/docs/<slug>`) with `@next/mdx`

Total estimated effort ~20 hours across 5 independently-mergeable PRs.
A future session should start by re-reading the IMPLEMENTATION_PLAN
end-to-end, then branching off `main` to start PR 0.
