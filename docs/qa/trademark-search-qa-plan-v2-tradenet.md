# Tradenet Search — Self-Running QA Suite (v2, refined for our system)

> Refinement of the generic "Self-Running QA Suite (v2)" prompt to match the **actual
> Tradenet architecture** (FastAPI + Postgres + RQ worker + Next.js 15). The generic
> plan reads as if written for an unknown third-party vendor; several of its core
> assumptions are wrong for us. This document keeps the strong scaffolding (two human
> gates, adaptive Wilson-CI sampling, stratification, continuous checkpointing,
> time-budget orchestrator) and corrects everything system-specific. **Image search
> stays out of scope.**

---

## 0. What changed vs the generic plan (read first)

| Generic plan assumed | Tradenet reality | Consequence for the suite |
|---|---|---|
| Unknown vendor; discover the API | We **own** the API: `GET /api/v1/search/trademarks` returns a known `SearchResultsOut` | Gate-1 schema questions are **pre-answered** (§3). Phase-0 only *confirms*. |
| 3 independently-searchable fields with a `field` selector | One free-text `q` that **unions** `mark_sample`, `mark_name`, `application_number`, `certificate_number`, `madrid_number`. No `field=` param. | The `field` dimension does **not** exist for `q`. A-03 (Name-vs-Mark) can't be isolated via API — it's a findings report on the *unified* box. |
| Vendor "claims" wildcard, Boolean, phonetic, fuzzy, diacritic, CJK — broken claim = S1 | `q` is plain `lower(col) LIKE '%q%'`. **No wildcard/Boolean parser; no accent-folding.** Phonetic+fuzzy live in `mode=phonetic`; diacritic-insensitivity **only** in phonetic. | **Recalibrate severity (§5).** Don't auto-S1 operators we never claimed — first establish the *actual* claim surface, then test. |
| Nice class / owner / Vienna / agent / dates / status "not exposed" | All **exposed as sidebar facet params**: `applicant` (owner), `ip_agency` (agent), `nice_class`, `vienna_codes`, `vn_status`/`granted`, `grant_date_from/to`. | The plan's "field-scope gap" recommendation is largely **moot**. Decide whether facets are in scope (§ Decisions). |
| Build ground truth by harvesting the app | We have **direct Postgres access** to the same DB the API serves | Build ground truth from **SQL against `trademarks`**, never from the SUT (the generic "harvest from the app" is self-referential and weak). |
| 3–5h run | Local API over ~200k rows with GIN-trgm/dmetaphone indexes answers in <1s | Adaptive sampling will **converge in well under the budget**. Keep the budget as a *cap*; **do not pad with sleeps**. Honestly report "converged early," not "ran 4h." |

---

## 1. Fixed context (corrected)

- **Product:** Tradenet — Vietnam trademark-intelligence web-app (IP professionals).
- **Stack under test:** FastAPI backend (`/api/v1/*`) + Postgres (~200k `trademarks` rows: VN national gazette A/B + Madrid international designations to VN) + Next.js 15 frontend (`:3000`, proxies `/static`).
- **The search surface (the SUT for this suite):**
  - `GET /api/v1/search/trademarks` — **scored** search. Params: `q`, `mode` (`text|phonetic|image|vienna`), `threshold` (0–1), `sort` (`similarity|publication-desc|applicant-asc|class-count`), `limit`, `offset`, plus facet filters (`country`, `nice_class`, `vienna_codes`, `applicant`, `ip_agency`, `mark_category`, `record_type`, `vn_status`, `granted`, `grant_date_from/to`, …). Returns `SearchResultsOut`.
  - `GET /api/v1/trademarks` — plain filtered list (facets, no score) — use for plain-match / count cross-checks.
  - `GET /api/v1/facets/*` (e.g. `/facets/granted`) — authoritative aggregate counts for A-07.
- **What `q` actually searches (single unified box):** `lower(mark_sample) LIKE %q%` OR `lower(mark_name) LIKE %q%` OR `ilike` on `application_number` / `certificate_number` / `madrid_number`. **Mark-only by design** (PR #119): `q` does **not** match `applicant_name` — applicant/class/agent filtering is via the facet params, not the box. Tests that type an owner name into `q` and expect a hit are **wrong by design**, not a defect.
- **Field mapping (the "3 fields"):** `trademark_name` → `mark.mark_name` (resolved display name); `mark` → `mark.mark_sample` (transcribed wordmark/specimen, may be NULL for figurative); `application_number` → `mark.application_number` (VN `4-YYYY-NNNNN`) / Madrid IRN → `mark.madrid_number` (`lineage_key = irn`).
- **Two retrieval "modes" (mapped to our params):** *ranked* = `sort=similarity`; *plain* = `sort=publication-desc` over the **same WHERE set**. Orthogonally, `mode` selects the matcher (`text` substring, `phonetic` engine, `vienna` code-coverage).
- **Text scoring is deterministic match-quality buckets (PR #124):** exact mark/ID `0.98` · name-contains-`q` `0.92` · token `0.78` · prefix `0.76` · else `0.60`. **No jitter.** `threshold` filters by bucket; for a text `q`, `total` is the **post-threshold** count. ⇒ recall/count tests must run at **`threshold=0`** (default is `0.4`, which already excludes the 0.78/0.76 buckets).
- **Out of scope:** image search; authn/z testing; the WIPO/IPVN ingest & enrichment pipelines.

## 2. Autonomy contract — two gates (unchanged shape)

GATE 1 (one consolidated batch, §3) → SMOKE GATE (5-min auto self-check) → autonomous run with adaptive sampling + continuous checkpointing → GATE 2 (final report approval). Degrade-don't-halt on non-fatal unknowns; only "no reachable target" is fatal.

## 3. Gate 1 — pre-filled, confirm-don't-ask

Because we own the system, the suite should **present these as defaults and ask only for confirmation + the genuinely-unknown items**, not interrogate from scratch:

**Known (suite asserts; human confirms):**
- Base URL: backend `http://localhost:8000` (API-level, preferred) / frontend `http://localhost:3000` (UI fallback). API is JSON/HTTP → **no Playwright needed for A–E except UI-only checks.**
- Schema mapping: result-list `items[]`; `trademark_name`=`items[].mark.mark_name`; `mark`=`items[].mark.mark_sample`; `application_number`=`items[].mark.application_number`; Madrid IRN=`items[].mark.madrid_number`; total=`total`; score=`items[].score`; ranked/plain toggle=`sort=similarity` vs `sort=publication-desc`; matcher=`mode`.
- Ground truth: built from **direct SQL** against the Postgres `trademarks` table (dev DSN `postgresql://tm:tm@localhost:5435/tm`), persisted as versioned `data/gold-set.yaml` — **not** harvested from the SUT.

**Genuinely unknown — ask:**
1. **Target env + auth posture.** Is the suite hitting **local dev** (above) or a deployed env? **Does `GET /api/v1/search/trademarks` require auth?** (Route has no per-route guard, but global/cookie auth ["sprint 1 C1"] may apply.) If auth is required, bootstrap a read-only user via `python -m scripts.create_user` + the `/login` flow (same as `app/frontend/tests/e2e/auth.setup.ts`) and supply the token/cookie.
2. **Permitted request rate / concurrency** for the chosen env (local: high; deployed: specify).
3. **Claimed-operator surface (drives §5 severity).** Which operators does Tradenet **actually market/claim**? The phonetic search box placeholder shows `NEUREX, NEUR*, *FAX` — **confirm whether `*` is parsed or decorative** (code path is plain `LIKE %q%`, so likely decorative). Anything *not* claimed is exploratory, **not** an S1 false-claim.
4. **Gold-set seed** (optional): any real marks + a VN appno + a Madrid IRN you want pinned; else the suite harvests ground truth from the DB.
5. **Scope toggle:** free-text `q` only (the "3 fields"), or **also** the sidebar facet filters (`applicant`/`nice_class`/`ip_agency`/`vienna_codes`/`granted`/…)? (See Decisions.)

## 4. Phase 0 — discovery & ground truth (corrected)

1. **Confirm**, don't reverse-engineer, the schema above against a live response. Wrap everything behind one `search(query, {mode, sort, threshold, page})` abstraction (no `field` arg — q is unified).
2. **Ground truth from the DB, never the SUT.** Generate `data/gold-set.yaml` from SQL: e.g. for an exact-name case, `SELECT application_number FROM trademarks WHERE lower(mark_name)=lower(:q)`; for count integrity, `SELECT count(*) … WHERE lower(mark_name) LIKE :pat OR …` mirroring `build_trademark_where`. Record the query + DSN + snapshot date. Missing ground truth ⇒ case `blocked`, never invented.
3. Bake in **known-correct behaviors** so the oracle doesn't false-flag them:
   - `q` is mark-only (owner in `q` → 0 results is **correct**).
   - text recall/count must use `threshold=0`; default `0.4` legitimately hides 0.78/0.76 buckets.
   - diacritic-insensitive matching is expected **only** in `mode=phonetic` (text `lower()` won't fold accents) — encode that as the *expected*, and test whether it *should* also work in text (a product question, not an auto-S1).
   - phonetic recall is two-stage capped at 1000 candidates → a sound-alike sharing **no** trigram with `q` is a **known** recall gap, not a fresh S1.
   - figurative marks have `mark_sample=NULL`/`mark_name=NULL` → unreachable by free text (reachable via facets/ID) — expected.

## 5. Severity model — recalibrated (the most important change)

The generic plan's "claimed-but-broken operator ⇒ S1" is dangerous here: `q` implements **none** of wildcard/Boolean/accent-folding as explicit operators, so a naïve run would emit a flood of bogus S1 "false-claim" defects for things we never claimed.

- **Step 0 (gate on §3-Q3):** establish the **actual claim surface** from the product UI/marketing/docs. Only operators Tradenet *claims* are eligible for **S1 (false-claim)** when broken.
- Operators present in the UI but **not** claimed (e.g. literal `*` if decorative) → **exploratory**: report as findings (S3) describing actual vs intuitive behavior, not S1.
- Confirmed claims that are real and worth hard-testing as S1-if-broken: **phonetic** (Latin + Vietnamese), **fuzzy** (trigram), **substring/contains**, and **diacritic-insensitive *in phonetic mode***.
- Keep the rest of the severity ladder: S1 = missed similar marks / wrong counts / **injection unsafety** / a genuinely-claimed-but-broken operator; S2 = functional bug w/ workaround or severe ranking error; S3 = ranking/UX/exploratory; S4 = cosmetic. No open S1 before "cleared for clearance use."

## 6. Test groups — mapped to our system (implement all, data-driven)

Same A–E structure; deltas only:
- **A (functional):** A-03 Name-vs-Mark is a **findings report on the unified `q`** (we can't field-isolate). A-05 VN appno `4-YYYY-NNNNN` exactly-1 via the `application_number` ilike path. A-07 count integrity = `total` (at `threshold=0`) == sum-of-pages == **DB count** == `/facets/*` where applicable.
- **B (operators):** gate each on the §5 claim surface. B-09 diacritic-insensitive: assert **phonetic** passes; record text-mode behavior as a product finding, not an auto-fail.
- **C (multilingual/Madrid):** CJK/Cyrillic — note the VN gazette transliterates to Latin, but Madrid `mark_name` (WIPO `mark_text`) may carry native script; trgm indexes are Unicode, so substring CJK *may* work — verify, don't assume. C-09 source distinction = `mark_category` (`domestic_*` vs `madrid_*`).
- **D (robustness/perf):** D-04 injection — backend is SQLAlchemy-parameterised (the only inlined value is the trusted `SET LOCAL pg_trgm.similarity_threshold` constant) → assert no 5xx / no leakage. D-07 latency p50/p95 for `mode=text` and `mode=phonetic` (phonetic is the heavier two-stage path). D-10 idempotency — scores are now deterministic (no jitter), so exact-equality is a valid oracle.
- **E (ranking):** map to `sort=similarity` vs `sort=publication-desc`; E-06 determinism is now strict (jitter removed).

## 7. Sampling, persistence, orchestrator, reporting

**Keep the generic plan's §4/§5/§6/§10 essentially as-is** — they are sound: stratified + sequential **Wilson-CI** sampling (95%, ±0.03, floor 200 / ceiling 1500 per group, fixed RNG seed), per-case `cases.jsonl` append + atomic `state.json` + `evidence/` + 15-min live `report.md`, token-bucket pacing + circuit-breaker + heartbeat, and the report layout (exec summary → metrics±CI dashboard → per-group tables → severity-sorted defects → A-03 findings → Recommended Final Approach). Two corrections:
- **Strata** = `source` (domestic/madrid, from `mark_category`) × `script class` (Latin / VN-diacritic / CJK / Cyrillic) × `mark-length bucket` × **matcher** (`text`/`phonetic`) — drop the non-existent `field` axis.
- **Time budget:** treat 4h default / 5h cap as a **ceiling**; expect early convergence on the local API and report "converged at n=… in …min," not a padded runtime.

## 8. Stack & placement (decided)

- **Python + `httpx` (async) + `pytest`** for the API-level suite — it matches the backend's existing test stack (`tests/` uses httpx+ASGI), can query the **same Postgres for ground truth** with `psycopg2`/SQLAlchemy, and needs no browser. **Playwright (the repo's existing TS e2e harness) only** for any UI-only assertion. (Rationale: API is clean JSON; ground truth needs DB access, which the Python stack already has.)
- **Repo placement:** new top-level `qa/` tree (own `pyproject`/venv or reuse `app/.venv`), isolated from `app/backend` so it never trips the backend CI gates. Artifacts under `qa/results/run-<ts>/`.
- **Guardrails:** read-only (GET + read-only SQL) — no writes/mutations. Secrets in `qa/.env` (+ `.env.example`); never commit creds. **Never commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths only. Fixed RNG seed; atomic durable writes; resume from `state.json`.

## Decisions — CONFIRMED (2026-06-27)

1. **Scope:** **`q` free-text first** (groups A–E). Sidebar facets are a **fast-follow group F**, not in the first run.
2. **Claim bar:** Tradenet positions itself as a **professional clearance tool for IP specialists (trademarks)**. That sets the S1 line: for a professional conflict-search tool, **missing a similar mark is the cardinal defect** → **phonetic, fuzzy, diacritic-insensitive, and substring recall are S1-if-broken** (table stakes for clearance). **Wildcard / Boolean are exploratory** (S3 findings) unless explicitly marketed — they are *not* implemented as parsed operators today.
3. **Target:** **local dev** (`http://localhost:8000` API, Postgres `:5435`). Confirm auth posture in the smoke gate; if the search endpoint is open in dev, run unauthenticated.

## Independence contract (hard requirement)

The suite is a **standalone, plug-in/plug-out module** with **zero coupling** to the app:
- Lives in a top-level `qa/` tree with its **own** `pyproject.toml` + venv; **never imports** `api`/`worker`/app code.
- Talks to the app **only over HTTP** (the public API) and to Postgres **read-only** (ground truth).
- **Never modifies** any app file, never runs app migrations, never trips app CI (it is outside `app/`).
- Deleting `qa/` leaves the app byte-for-byte unchanged. No app file references it.

Everything else (the autonomy contract, adaptive sampling, checkpointing, severity ladder, reporting) carries over from the generic v2 plan unchanged.
