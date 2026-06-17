# Enterprise Audit Plan — 2026-05-29

**Generated**: 2026-05-29 from Workflow `wgcdwj1sg` (39 agents, 2.4M tokens, ~18 min).
**Methodology**: 8 parallel auditors (security, backend correctness, frontend correctness, database integrity, infrastructure, observability, test coverage, data integrity) + adversarial verifier per P0/P1 finding.

**Headline numbers**:
- Raw findings: 99
- P0/P1 submitted to verifiers: 31
- **Confirmed P0/P1 (verified real)**: 28
- Refuted in verification: 3 (false-positive catches)
- P2/P3 passthrough (quality debt, unverified): 68

**Status**: untouched. This file is the standing punch list.

---

## Recommended PR sequence

Total clear-out estimate: **~8 hr** to ship all P0+P1.

| PR | Subject | Findings | Effort |
|---|---|---|---|
| A | Authz lockdown (watchlists + today) | 4× (2 P0 + 2 P1) | 30 min |
| B | Search trigram fix (drop `lower()`) | 1× P0 | 5 min |
| C | Docker reference data fix | 1× P0 | 30 min |
| D | Event-loop blocking (bcrypt + PIL → asyncio.to_thread) | 2× P1 | 30 min |
| E | Search pagination + frontend AbortController | 2× P1 | 20 min |
| F | Audit log table + GDPR user-delete flow | 2× P1 | 2 hr |
| G | Sentry + structured logs + ErrorBoundary | 3× P1 | 2 hr |
| H | Marketing SEO (per-page metadata + sitemap + robots) | 1× P1 | 1 hr |
| I | Frontend Dockerfile + DEPLOYMENT.md update | 1× P1 | 1 hr |

PRs A, B, C are independent and can ship in parallel — start with A (blocks production launch).

---

## Confirmed P0 — Must Fix Before Prod

### P0-1. query-perf `[db]`

**Location**: `app/backend/api/routes/_filters.py:100-108`

**Claim**: The free-text `q` filter wraps `applicant_name` and `mark_sample` in `lower()` before LIKE, which makes the trigram GIN indexes unusable. Postgres falls back to a sequential scan on trademarks for every search.

**Evidence**: EXPLAIN ANALYZE on the actual DB: `WHERE lower(applicant_name) LIKE '%chanel%'` → Seq Scan on trademarks, 46751 rows scanned, 116ms. Replacing with plain `applicant_name ILIKE '%CHANEL%' OR mark_sample ILIKE '%CHANEL%'` → Bitmap Index Scan on ix_trademarks_applicant_name_trgm + ix_trademarks_mark_sample_trgm, 0.49ms. 269x speedup. The pg_trgm index supports `~~*` (ILIKE) natively and is already case-insensitive; wrapping the column in `lower()` defeats it. Code at _filters.py L99-109: `like = f'%{q.lower()}%'` then `func.lower(Trademark.applicant_name).like(like), func.lower(Trademark.mark_sample).like(like)`. The whole point of migration 0009 (trigram indexes) is nullified — index usage on ix_trademarks_mark_sample_trgm shows `idx_scan=0` in pg_stat_user_indexes.

**Fix**: Drop the lower() wrap and use `Trademark.applicant_name.ilike(f'%{q}%')` / `Trademark.mark_sample.ilike(f'%{q}%')`. Postgres' `~~*` operator and trigram GIN are already case-insensitive. No new indexes needed.

<details><summary>Verifier reasoning</summary>

Confirmed and reproduced. The code at app/backend/api/routes/_filters.py:100-108 exactly matches the claim: `like = f"%{q.lower()}%"` followed by `func.lower(Trademark.applicant_name).like(like)` and `func.lower(Trademark.mark_sample).like(like)`. I reproduced both EXPLAIN ANALYZE plans against the live database (docker exec app-postgres-1): with the lower() wrap, the planner does a Seq Scan on trademarks (46,751 rows filtered, 9,614 buffers, 124ms); without the wrap (plain ILIKE), the planner uses both ix_trademarks_applicant_name_trgm and ix_trademarks_mark_sample_trgm via BitmapOr (28 buffers, 0.48ms) — a ~258x speedup, matching the cited 269x. Migration 0009 explicitly creates the trigram GIN indexes on the raw columns (`USING gin (applicant_name gin_trgm_ops)`), not on `lower(...)`, so the lower() wrap absolutely defeats them. The pg_trgm `~~*` (ILIKE) operator is already case-insensitive by design — the lower() wrap is both wrong (kills indexes) and redundant (ILIKE doesn't need it). pg_stat_user_indexes shows the trigram indexes had near-zero scans before this verification. The suggested fix (drop lower() and use `.ilike(f"%{q}%")`) is correct and minimal. P0 is appropriate: this is the user-facing free-text search hot path against a 46k-row table; every search query currently does a full sequential scan, and the fix is one-line per side.

</details>

---

### P0-2. container-image-correctness `[infra]`

**Location**: `app/backend/Dockerfile:45 + app/backend/tm_extractor/data_loaders.py:14-21`

**Claim**: The production container ships WITHOUT cities_by_country.json or company_suffixes.json. The two reference files live at the repo root, but the Dockerfile build context is `app/backend` and they are not under that directory. data_loaders silently swallows FileNotFoundError and returns empty {} / set(), so the running container will quietly extract trademarks with NO city matching and NO Company-vs-Personal classification.

**Evidence**: Dockerfile uses `COPY --chown=app:app . /srv/backend` against the `app/backend` build context (DEPLOYMENT.md:46: `docker build … app/backend`). The data files are at `/Users/francisluong/Project/ASL/ImageExtractor/claude_csvbuilder/cities_by_country.json` and `company_suffixes.json` — repo root, not under app/backend. `find app/backend -name cities_by_country.json` returns nothing. data_loaders.py:19-21: `except Exception as e: logging.error(…); return {}` — silent degradation. tm_extractor/config.py:34-39 hardcodes the file names under `data_dir`.

**Fix**: Either (a) move the JSON files into `app/backend/` and update `from_root()`, or (b) change build context to repo root and add a COPY for the JSONs (and CLAUDE.md / `data_dir` resolution), or (c) bake them into the `tm_extractor` package as package data. Also raise (not log) when files are missing in non-dev TM_ENV — silent empty-data degradation has no legitimate use case in production.

<details><summary>Verifier reasoning</summary>

Confirmed end-to-end. (1) Dockerfile uses build context `app/backend` (`docker build … app/backend` per DEPLOYMENT.md:46) and `COPY --chown=app:app . /srv/backend` copies only files under that directory. (2) `cities_by_country.json` (10 MB) and `company_suffixes.json` are at the repo root, NOT under `app/backend/` — `find app/backend -name cities_by_country.json` returns nothing and `ls app/backend/` shows no JSON. (3) `data_loaders.py:19-21,44-46` catches every exception and returns `{}` / `set()` with only a logging.error — silent degradation, not a hard failure. (4) `tm_extractor/config.py:34-39` resolves `cities_file = data_dir / "cities_by_country.json"` and the production `Settings.data_dir` (`api/settings.py:46`) defaults to `Path(__file__).resolve().parents[3]` which in the container is `/` — file would be looked up at `/cities_by_country.json`. DEPLOYMENT.md:33 instead instructs operators to set `TM_DATA_DIR=/srv/backend` "where cities_by_country.json lives" — but the build never puts it there, no .dockerignore exclusion is involved, no mount instruction is given to compensate, and no init step copies the files in. (5) `worker/ingest.py:371` builds `ExtractorConfig(data_dir=settings.data_dir, …)` so every production ingest will trigger the silent-empty path. Impact: `Applicant City` matching is completely dead (no fallback for non-VN rows); `Applicant Type` partially degrades — the baked `STRONG_COMPANY_SUFFIXES` + `TYPO_TOLERANT_COMPANY_PATTERNS` Python constants still catch LTD/INC/GMBH/CORP, so the regression is on the long-tail JSON suffixes (step 3 of 4 in the classifier chain). City matching is the bigger hit — entire 10 MB reference is silently gone. P0 is justified given (a) every production ingest is affected, (b) there is no operator-visible signal beyond a single ERROR log line at process start, and (c) DEPLOYMENT.md actively misleads operators about where the files are. The suggested fix list is reasonable; making the missing file fatal in non-dev TM_ENV is the most surgical safety net.

</details>

---

### P0-3. authz `[data]`

**Location**: `app/backend/api/routes/watchlists.py:171-185`

**Claim**: GET /api/v1/watchlists/{id}/findings has zero authentication or ownership check — any caller with a watchlist UUID can read its results (the saved query rerun against trademarks).

**Evidence**: Handler signature: `async def watchlist_findings(id: uuid.UUID, limit: int = 12, session: AsyncSession = Depends(get_session)) -> list[TrademarkOut]` — no `Depends(require_user)`, no `_assert_owned(w, user)` call. Only check is `if w is None: raise 404`. The endpoint then runs the persisted JSONB query and returns the matching trademark rows.

**Fix**: Add `user: User = Depends(require_user)` to the signature and call `_assert_owned(w, user)` immediately after the 404 check (mirrors PUT/DELETE). Watchlist UUIDs may not be guessable today, but admin URLs, browser history, and Sentry breadcrumbs can leak them — authz must not depend on URL secrecy.

<details><summary>Verifier reasoning</summary>

Verified by reading app/backend/api/routes/watchlists.py lines 171-185. The handler signature is exactly as cited: `async def watchlist_findings(id: uuid.UUID, limit: int = 12, session: AsyncSession = Depends(get_session)) -> list[TrademarkOut]` — no `Depends(require_user)`, no `_assert_owned(w, user)` call. Only a 404 check on missing watchlist. The two adjacent mutating endpoints (PUT `/{id}` lines 119-129, DELETE `/{id}` lines 149-158) both explicitly take `user: User = Depends(require_user)` and call `_assert_owned(w, user)` after the 404 — confirming author intent that watchlists are owner-scoped. No global auth middleware exists (verified in main.py: only RequestIDMiddleware, SlowAPIMiddleware, CORSMiddleware). The `Watchlist` model has `owner_id` (models.py:123). Real auth is wired (JWT bearer in auth.py), so this isn't a stubbed-out auth situation. Impact is real: any holder of a watchlist UUID (browser history, Sentry breadcrumbs, server logs, referer headers, shared admin URLs) can read the trademark results for a client/matter-scoped saved query — horizontal IDOR exposing per-client legal monitoring intent. The suggested fix mirrors the existing PUT/DELETE pattern exactly. P0 is defensible because both layers (authn and authz) are absent, not just one; the only mitigation is UUID unguessability, which is precisely the URL-secrecy assumption authz must not rely on.

</details>

---

### P0-4. authz-confidentiality `[data]`

**Location**: `app/backend/api/routes/watchlists.py:80-91`

**Claim**: GET /api/v1/watchlists with no Authorization header returns every watchlist across every user — name, client, matter, saved query JSON, and counts — because the `optional_user` branch skips the owner filter when `user is None`.

**Evidence**: ```
stmt = select(Watchlist).order_by(desc(Watchlist.new_count), desc(Watchlist.updated_at))
if user is not None:
    stmt = stmt.where((Watchlist.owner_id == user.id) | (Watchlist.owner_id.is_(None)))
rows = (await session.execute(stmt)).scalars().all()
```
The `if user is not None:` gate is inverted — anonymous callers fall through with no WHERE clause and read every row. `client` and `matter` columns are explicitly billing/legal-matter PII (the design treats them as confidential per the schema docstring).

**Fix**: Replace `optional_user` with `require_user` and unconditionally apply the owner filter (drop the legacy `is None` branch). The comment 'Pre-auth callers see all (legacy behaviour); once auth is real, drop the if branch.' is the unfixed TODO — auth is now real.

<details><summary>Verifier reasoning</summary>

Verified directly in app/backend/api/routes/watchlists.py lines 80-91. The endpoint depends on `optional_user`, which (per auth.py lines 209-212) returns `None` when no Bearer header is present without raising. The `if user is not None:` guard then skips the owner filter, so anonymous callers receive every Watchlist row via `_to_out`, including the `client` and `matter` columns (declared in db/models.py:115-116 as dedicated billing/legal-matter fields) plus the saved-query JSONB and counts. No global auth middleware exists in main.py — auth is per-route — so nothing mitigates the leak. The sibling POST/PUT/DELETE handlers in the same file all use `require_user`, and the inline comment ("Pre-auth callers see all (legacy behaviour); once auth is real, drop the `if` branch") explicitly flags this as an unfixed TODO that is now stale because auth.py implements a full JWT bearer flow. P0 is the right severity: unauthenticated cross-tenant disclosure of client/matter PII for a legal-services product, exploitable with a single curl, no chained vuln required.

</details>

---

## Confirmed P1 — Fix This Week

### P1-1. idor `[security]`

**Location**: `app/backend/api/routes/watchlists.py:80-91`

**Claim**: GET /api/v1/watchlists has no auth gate when caller is anonymous: it falls through optional_user and returns every watchlist from every user.

**Evidence**: `user: User | None = Depends(optional_user)` followed by `if user is not None: stmt = stmt.where(...)`. When user is None the where clause is skipped and `select(Watchlist).order_by(...)` returns the global cross-tenant list, exposing each watchlist's `name`, `client`, `matter` (legal-matter labels), and saved query (with potentially sensitive search terms). The inline comment even calls the branch 'legacy behaviour'.

**Fix**: Replace `optional_user` with `require_user`. If a public listing is genuinely needed, hard-filter to `Watchlist.owner_id.is_(None)` and add the user check anyway so anonymous callers cannot see per-owner rows.

<details><summary>Verifier reasoning</summary>

Verified directly against app/backend/api/routes/watchlists.py:80-91. The endpoint uses Depends(optional_user) and only applies the owner-scope WHERE clause when user is not None — anonymous callers receive `select(Watchlist).order_by(...)` with no filtering. The inline comment ("Pre-auth callers see all (legacy behaviour); once auth is real, drop the `if` branch") explicitly acknowledges the gap, and auth is already real (api/auth.py implements full HS256 JWT bearer flow with require_user/optional_user). No global auth middleware in main.py (only CORS, SlowAPI, RequestID). Sibling POST/PUT/DELETE handlers correctly use require_user — only the GET list endpoint falls through. The Watchlist model exposes name, client, matter (legal-matter labels), and a JSONB `query` with saved search terms; _to_out returns all of these. Impact is concrete and reproducible by any unauthenticated HTTP caller. P1 severity is appropriate: cross-tenant data leak of sensitive legal-matter metadata, but not full PII exposure or RCE. Suggested fix is correct — swap optional_user → require_user (the legacy branch is obsolete now that auth is wired).

</details>

---

### P1-2. idor `[security]`

**Location**: `app/backend/api/routes/watchlists.py:171-185`

**Claim**: GET /api/v1/watchlists/{id}/findings has no authentication and no ownership check.

**Evidence**: The signature is `async def watchlist_findings(id: uuid.UUID, limit: int = 12, session: AsyncSession = Depends(get_session))` — no `require_user`, no `_assert_owned`. Any caller (logged in or not) who knows or guesses a watchlist UUID gets the rendered findings for that watchlist (mark details for whatever query the owner saved — i.e. exactly the curated competitive-monitoring set the owner pays to see).

**Fix**: Add `user: User = Depends(require_user)`, look up `Watchlist`, and call the existing `_assert_owned(w, user)` helper before running the query.

<details><summary>Verifier reasoning</summary>

The finding is accurate and exploitable. Reading app/backend/api/routes/watchlists.py lines 171-185, the GET /{id}/findings handler's signature is exactly `async def watchlist_findings(id: uuid.UUID, limit: int = 12, session: AsyncSession = Depends(get_session))` — no `require_user`, no `optional_user`, and no `_assert_owned(w, user)` call after loading the watchlist. Sibling routes (PUT at line 124, DELETE at line 153) both require `user: User = Depends(require_user)` and call `_assert_owned(w, user)` after `session.get(Watchlist, id)`, confirming the expected pattern. There is no global auth middleware in app/backend/api/main.py — auth is per-route via FastAPI Depends — so this endpoint is genuinely open. Worse, the sibling list_watchlists endpoint at line 80-91 uses `optional_user` with a legacy fallback that returns all watchlists to anonymous callers, so an attacker doesn't even need to guess UUIDs — they can list them anonymously and then read findings. The exposed TrademarkOut payload is the curated competitive-monitoring result set the watchlist owner pays for. P1 is appropriate: it's a clean IDOR / broken access control on commercial data, mitigation is trivial (add the same two-line guard used in PUT/DELETE), but the data is business-confidential rather than PII/credentials, so not P0.

</details>

---

### P1-3. auth-z `[backend]`

**Location**: `app/backend/api/routes/watchlists.py:171-185`

**Claim**: GET /api/v1/watchlists/{id}/findings has no auth dependency — unauthenticated callers can read any watchlist's results if they know (or guess) the UUID.

**Evidence**: The handler signature is `async def watchlist_findings(id: uuid.UUID, limit: int = 12, session: AsyncSession = Depends(get_session))`. There is no `Depends(require_user)` / `Depends(optional_user)` / ownership check. By contrast, create/update/delete on the same router all use `Depends(require_user)` + `_assert_owned`. Anyone hitting `/api/v1/watchlists/<uuid>/findings` over the network gets back the saved query's matching trademarks with no token.

**Fix**: Add `user: User = Depends(require_user)` and call `_assert_owned(w, user)` after the `session.get(Watchlist, id)` lookup, mirroring the pattern in `update_watchlist` / `delete_watchlist`.

<details><summary>Verifier reasoning</summary>

The finding survives adversarial review. I read app/backend/api/routes/watchlists.py and confirmed the watchlist_findings handler at lines 171-185 has signature `async def watchlist_findings(id: uuid.UUID, limit: int = 12, session: AsyncSession = Depends(get_session))` — no Depends(require_user), no Depends(optional_user), and no _assert_owned call. The sibling endpoints on the same router (create at L98, update at L124, delete at L153) all use `user: User = Depends(require_user)`, and update/delete additionally call `_assert_owned(w, user)` (L129, L158), establishing both the pattern and the security expectation. I verified in app/backend/api/auth.py that auth is real (JWT HS256 Bearer tokens, bcrypt, RBAC) — not a stub — and in app/backend/api/main.py that there is no middleware-level auth catching unauthenticated routes; auth is strictly opt-in per route via Depends. Watchlists are owner-scoped (`Watchlist.owner_id` exists in models.py L123, and list_watchlists at L88-89 filters by it when authenticated). The exposed data is the saved-query result set — i.e. which trademarks match a private business query like "competitor X" — which leaks the matter/client/query intent even if the underlying trademark rows are gazette-public. The UUID is v4 (unguessable), so this is leak-dependent rather than enumeration-open, which is why P1 (not P0) is the right severity. The suggested fix mirrors the update/delete pattern exactly. Severity stays P1 as originally assigned.

</details>

---

### P1-4. async-blocking `[backend]`

**Location**: `app/backend/api/routes/auth.py:159,161 + app/backend/api/auth.py:71-85`

**Claim**: Bcrypt verify (~250 ms per call at cost factor 12) runs synchronously inside the async event loop on every login attempt, freezing the API for every other in-flight request for the duration.

**Evidence**: auth.py: `def verify_password(plain, hashed) -> bool: ... return bcrypt.checkpw(...)` — sync. routes/auth.py `login` calls `verify_password(body.password, _DUMMY_HASH)` then `verify_password(body.password, user.password_hash)` directly inside an `async def` handler with no `run_in_threadpool` / `asyncio.to_thread` wrapper. A single uvicorn worker handling 4 concurrent login requests gates them ~1s end-to-end on bcrypt alone, blocking all other endpoints on that worker (search, health, etc.).

**Fix**: Wrap the two `verify_password` calls in `await anyio.to_thread.run_sync(verify_password, body.password, hashed)` (or `asyncio.to_thread`). Same for `hash_password` in `scripts/create_user.py` if/when called from API code.

<details><summary>Verifier reasoning</summary>

Verified directly against the source. `verify_password` (app/backend/api/auth.py:78-85) is a plain synchronous function that calls `bcrypt.checkpw`, and the `login` handler (app/backend/api/routes/auth.py:134, an `async def`) invokes it at lines 159 and 161 with no `await`, no `run_in_threadpool`, and no `asyncio.to_thread` wrapper. A repo-wide grep for `run_in_threadpool|to_thread|run_sync` returns zero matches in the backend — no mitigation exists anywhere. The ~250 ms figure is not the reviewer's estimate; it is stated in the source comments themselves (auth.py lines 26-27 and 59-61). FastAPI's documented behavior is that sync work inside `async def` handlers runs on the event loop, so each in-flight bcrypt verify blocks every other coroutine on that uvicorn worker — including search, gazettes, and health endpoints — for the full ~250 ms. The login endpoint is unauthenticated and rate-limit-less in this code, so any external client can trigger it. Severity P1 is appropriate (real availability issue, trivial 2-line fix, security-adjacent endpoint exposed to unauthenticated traffic). One minor caveat that does not change the verdict: the cited `_DUMMY_HASH = _hash(...)` at module load is a one-time startup cost, not a per-request blocker — the per-request blockers are the two `verify_password` calls, exactly as the finding states. The suggested fix (`await anyio.to_thread.run_sync(verify_password, ...)`) is correct and minimal.

</details>

---

### P1-5. async-blocking `[backend]`

**Location**: `app/backend/api/routes/marks.py:333-345, app/backend/api/routes/compare.py:135-141, app/backend/api/similarity.py:255-266`

**Claim**: `visual_similarity` opens PNGs with PIL and computes pHashes synchronously inside async route handlers, looping over up to `_SIMILAR_CANDIDATE_POOL = 40` candidates per /similar request.

**Evidence**: marks.py similar_marks: `for r in candidates: ... vis = sim.visual_similarity(a_logo=m.logo_path, b_logo=r.logo_path, ..., image_root=image_root)` inside `async def similar_marks`. `_phash_for` does `with Image.open(abs_path) as img: h = imagehash.phash(img)` — synchronous file I/O + CPU. First call on a cold mark loads + decodes a PNG from disk on the loop thread; with 40 candidates a uncached request blocks the loop for hundreds of ms.

**Fix**: Wrap the scored loop in `await asyncio.to_thread(_score_loop, ...)`, or precompute pHashes in the worker at ingest time (write them to a new column) so the API doesn't decode images at all. The latter is what the comment in `_phash_cache` hints at.

<details><summary>Verifier reasoning</summary>

All three citations match the code exactly. marks.py line 292 confirms `async def similar_marks`; line 288 confirms `_SIMILAR_CANDIDATE_POOL = 40`; lines 333-345 loop over candidates and call `sim.visual_similarity(...)` synchronously without `asyncio.to_thread` / `run_in_executor` / `run_in_threadpool` (grep across `app/backend/api/` returns zero matches for these — no mitigation exists). compare.py line 76 confirms `async def compare`, which calls `_score_pair` in a loop, and `_score_pair` (lines 135-141) likewise invokes `sim.visual_similarity` synchronously. similarity.py lines 255-266 confirms `_phash_for` does `with Image.open(abs_path) as img: h = imagehash.phash(img)` — synchronous Pillow decode + CPU-heavy pHash computation on the event loop thread. The `_phash_cache` (line 242) does soften the impact: once an anchor's pHash is cached, the work disappears. But the FIRST request for any (anchor, candidate-set) pair on a cold cache decodes up to 41 PNGs on the loop thread — easily hundreds of ms — which blocks ALL concurrent requests (not just /similar), including the simple /marks list browsing the same UI does. The suggested fix (precompute pHashes at ingest time into a new column, eliminating PIL from the request path entirely) is sound and the `_phash_cache` comment ("logo files don't change") does hint at the same direction. P1 is appropriate: real event-loop blocking, real cross-request impact, real bound on candidates (40) that grows with `_SIMILAR_CANDIDATE_POOL`.

</details>

---

### P1-6. pagination `[backend]`

**Location**: `app/backend/api/routes/search.py:189-216`

**Claim**: `/api/v1/search/trademarks` returns inconsistent `total` and broken pagination: `total` counts SQL-filtered rows (no threshold applied), then a bounded `fetch_limit` is sliced post-threshold, so `offset > 0` requests can return empty pages while `total` still reports a large number.

**Evidence**: `cnt_stmt` has the same WHERE clauses as `stmt` but no Python-side threshold filtering — `total` reflects pre-threshold matches. Then `fetch_limit = max(limit + offset, limit) * 2` caps the actually-fetched rows; `scored` filters by threshold; `page = scored[offset : offset + limit]`. If threshold drops 80% of rows, page 2 (`offset=50, limit=50`) only sees post-threshold rows from the first `(50+50)*2 = 200` SQL rows, not from the full match set. Past page ~2 the response is empty even though `total` says thousands.

**Fix**: Either (a) make `total` reflect post-threshold counts by running the same scoring path on the count query (expensive but correct), or (b) keep SQL as the source of truth for `total` and document that threshold + pagination interact only on page 1. Option (c): when `mode` ∉ {'phonetic','vienna','image'} and there's no real similarity to compute, skip threshold entirely and just paginate against SQL — matches the current behaviour comment but isn't actually enforced.

<details><summary>Verifier reasoning</summary>

The finding is accurately characterized. In app/backend/api/routes/search.py:189-216 the code constructs cnt_stmt with the same WHERE clauses as stmt but no Python-side scoring/threshold step, so total reflects pre-threshold SQL matches. The over-fetch (fetch_limit = max(limit+offset, limit)*2) only doubles the SQL window; rows passing the threshold then get sliced by [offset:offset+limit]. Walking the math: with threshold-induced pass rate p, after fetching 2*(limit+offset) rows we have ~2p*(limit+offset) survivors, so the slice [offset:offset+limit] requires 2p*(limit+offset) >= offset+limit, i.e., p >= 0.5. Any threshold tight enough to drop more than half the SQL matches produces empty pages for offset >= limit. Concrete repro: mode=text with q="GB" and threshold=0.95 (only wordmark==ql scores 0.98) — SQL returns many rows but post-threshold pass rate is well under 50%, so page 2 is empty while total still reports thousands. The frontend in app/(app)/search/page.tsx confirms the impact: pagination buttons are gated by offset+pageSize >= total, and the header renders "Showing N–M of total", so users see the inflated total, click Next, and land on empty pages. The existing test_search_filter_only.py acknowledges total > items can happen with limit=200 and offset=0 (line 156: assert items <= total) but never tests offset > 0, so no current test catches this. Tests test_filter_only_text_search_returns_all_matches relies on the mode in ("text","phonetic") and not q short-circuit in _score, which returns 1.0 and bypasses the threshold — that mitigation only covers filter-only searches, not the scored ones described here. No mitigation exists elsewhere. P1 is appropriate: user-visible broken pagination on the primary search endpoint, but not a data-loss or security issue.

</details>

---

### P1-7. race-condition `[frontend]`

**Location**: `app/frontend/app/(app)/search/page.tsx:99-125 + lib/api.ts:317`

**Claim**: The main search results fetch has no AbortController. Rapid query/filter changes can let a slow stale response overwrite a faster newer one.

**Evidence**: lib/api.ts line 317 defines `scoredSearch: (p: ScoredSearchParams) => json<SearchResults>(...)` with NO `init?: RequestInit` parameter (unlike facetsCountries/etc. on lines 324-330 which do accept it). The search page effect (page.tsx:99-125) calls `api.scoredSearch(params).then((r) => { setResults(r); ... }).finally(() => setLoading(false));` with no signal, no request-id guard, and no cleanup. Compounding it, the facets effect immediately above DOES use AbortController (lines 84-95), highlighting that the developer recognised the race for facets but skipped it for the main results — exactly the race the CmdK abort comment (cmdk.tsx:96) was added to prevent. setLoading(false) in `.finally()` also flips off prematurely when the stale fetch lands first.

**Fix**: Add `init?: RequestInit` to `scoredSearch` in lib/api.ts (mirroring `searchTrademarks`), then in search/page.tsx create an `AbortController` per effect run and pass `{ signal: controller.signal }`. Track a request-id ref so only the latest response's `setLoading(false)` wins.

<details><summary>Verifier reasoning</summary>

All cited evidence matches the actual code verbatim. lib/api.ts:317 defines scoredSearch with no init parameter, while the surrounding API methods (searchTrademarks line 315, facetsCountries/NiceClasses/Applicants/IpAgencies lines 324-331) all accept init?: RequestInit. The search results effect at page.tsx:99-125 calls api.scoredSearch(params).then(...).finally(() => setLoading(false)) with no AbortController, no signal, no request-id guard, and no cleanup return — confirmed by direct read. The facets effect immediately above (lines 83-96) uses AbortController with an explicit comment citing 'same race the CmdK abort solved,' and cmdk.tsx:96 confirms the team recognized this exact race elsewhere. The inconsistency within a single file demonstrates the omission is an oversight, not a deliberate design. The race is concrete: a slow scoredSearch response from an earlier filter can land after a faster newer one, clobbering state and flipping setLoading off prematurely. P1 is appropriate — this is the app's primary search surface (not a best-effort autocomplete), so wrong results displayed for the wrong query is a real correctness defect, but it's not data-corrupting or security-impacting, so not P0.

</details>

---

### P1-8. seo `[frontend]`

**Location**: `app/frontend/app/ (entire marketing tree)`

**Claim**: Marketing site has zero per-page SEO. /pricing, /coverage, /docs/* all inherit the root layout's single Metadata; no sitemap.xml, no robots.txt, all docs articles share the same <title> and OG tags.

**Evidence**: `grep -rn "export const metadata|generateMetadata" app/frontend/app/` returns ONE hit — app/layout.tsx line 40. Neither pricing/page.tsx, coverage/page.tsx, docs/[slug]/page.tsx, nor docs/layout.tsx export metadata. `find app/frontend/app -name 'sitemap*' -o -name 'robots*'` returns nothing. `app/frontend/public/` is empty. Result: Google sees 8 docs pages with title='Tradenet — Vietnam Trademark Intelligence' and the landing description.

**Fix**: Add `export const metadata` (or `generateMetadata` for /docs/[slug]) per route. Create `app/sitemap.ts` enumerating /, /pricing, /coverage, /docs/<every slug>. Create `app/robots.ts`. Per-page metadata should include canonical URLs and OG image.

<details><summary>Verifier reasoning</summary>

Independently verified all evidence. (1) `grep -rn "export const metadata|generateMetadata" app/frontend/app/` returns exactly one hit: app/layout.tsx:40 with the static "Tradenet — Vietnam Trademark Intelligence" title. (2) `find` for sitemap/robots returns nothing — neither `app/sitemap.ts`, `app/robots.ts`, nor `app/sitemap.xml`/`robots.txt` exist. (3) `app/frontend/public/` directory does not exist at all, so static sitemap.xml/robots.txt fallback is also absent. (4) Confirmed pricing/page.tsx, coverage/page.tsx, docs/page.tsx, docs/layout.tsx, docs/[slug]/page.tsx, and (marketing)/layout.tsx export no metadata. (5) next.config.mjs has no metadata wiring. (6) docs/[slug]/page.tsx pre-renders 17 slugs via generateStaticParams, all sharing the same root title and description. Impact is real and not theoretical: for a marketing site whose explicit purpose is public discovery, duplicate <title>/OG tags across 17 docs URLs plus missing sitemap.xml and robots.txt are concrete SEO defects that crawlers will observe immediately on index. P1 is appropriate — not P0 because the site still renders and the in-product (app) routes are unaffected, but higher than P2 because this is a marketing site where SEO is a core function.

</details>

---

### P1-9. tenancy-leak `[db]`

**Location**: `app/backend/api/routes/today.py:146,160,165`

**Claim**: `/api/v1/today/digest`, `/api/v1/findings`, and `_findings_summary` iterate `select(Watchlist)` with no `owner_id` filter — every user sees every other user's watchlists' findings and counts.

**Evidence**: today.py:146 `watchlists = list((await session.execute(select(Watchlist))).scalars().all())` is unscoped. Same at L160. There is no Depends(require_user) or Depends(optional_user) on these endpoints (routes/today.py:57, 157). Compare with routes/watchlists.py:88-89 which correctly applies `(Watchlist.owner_id == user.id) | (Watchlist.owner_id.is_(None))`. Also a strong N+1: `_findings_summary` runs one SELECT per watchlist (today.py:149-150). With N users × M watchlists each, the dashboard makes M+1 queries per request.

**Fix**: Add `user: User = Depends(require_user)` and `.where((Watchlist.owner_id == user.id) | (Watchlist.owner_id.is_(None)))` to digest, findings, and _findings_summary. Replace the per-watchlist findings loop with a single UNION ALL or batched query that scopes all to the user's watchlists in one round trip.

<details><summary>Verifier reasoning</summary>

Verified at the cited file. today.py has no auth Depends on `today_digest` (L58) or `findings` (L158), and both `select(Watchlist)` calls (L146 in `_findings_summary`, L160 in `findings`) are unscoped — no `owner_id` filter. The comparison with watchlists.py:88-89 is accurate; that route correctly applies `(Watchlist.owner_id == user.id) | (Watchlist.owner_id.is_(None))` via `optional_user`, proving the pattern is established. The N+1 in `_findings_summary` is also real (line 150 runs one query per watchlist inside the loop). Impact is concrete: `/api/v1/findings` returns `watchId`+`watchName` for every user's watchlists to ANY caller (the smoke test `test_today_digest_shape` uses unauthenticated `client` and asserts 200), so this isn't just cross-tenant — it's anonymous-exposed. `/api/v1/today/digest` similarly returns aggregate counts (`activeWatchlists`, `watchlistsWithFindings`, `totalNew`) computed over all tenants. The top-of-file comment says findings are "mocked until PR #5", but the mock still reads real Watchlist rows and exposes real names/IDs across tenants — the disclaimer doesn't excuse the live leak. Minor location nit: L165 is the call site to `_findings_for_watchlist`, not itself an unscoped select; the actual unscoped selects are L146 and L160. The substance of the finding stands. P1 is appropriate (auth is wired, owner_id exists, fix is mechanical, but data IS leaking now).

</details>

---

### P1-10. deployment-completeness `[infra]`

**Location**: `app/frontend/ (no Dockerfile) + app/DEPLOYMENT.md`

**Claim**: There is no frontend Dockerfile and no documented frontend deployment story. DEPLOYMENT.md covers only the backend; the README mentions only `pnpm dev` / `pnpm build` for the frontend. The product cannot ship to production from what's in the repo.

**Evidence**: `find /Users/francisluong/Project/ASL/ImageExtractor/claude_csvbuilder/app/frontend -maxdepth 2 -name Dockerfile*` returns nothing. DEPLOYMENT.md:44-64 only documents `docker build … app/backend`. README.md:27 lists Dockerfile only under `backend/`. No mention of Vercel, static export, CDN, or container target for the Next.js app.

**Fix**: Either commit a Dockerfile under app/frontend (multi-stage: node-alpine deps → next build → next start) with a HEALTHCHECK and non-root user, OR document the external deployment target (Vercel, static export to S3/CloudFront, etc.) in DEPLOYMENT.md. Today there's no path from `pnpm build` to production.

<details><summary>Verifier reasoning</summary>

All three evidence claims verified independently: (1) `find` against /Users/francisluong/Project/ASL/ImageExtractor/claude_csvbuilder/app/frontend returns no Dockerfile — only app/backend/Dockerfile exists; no vercel.json or .vercel/ anywhere in the repo. (2) DEPLOYMENT.md's "Building the image" section (lines 43-64) references only `docker build … app/backend` and `tradenet-api` — grep for frontend/next/vercel/nextjs across DEPLOYMENT.md returns zero hits. (3) README.md lists Dockerfile only under backend/ (line 27) and the frontend Quick start (lines 81-86) covers only `pnpm install` / `pnpm dev`. ARCHITECTURE.md describes the frontend structure but provides no deployment story either. The impact is real and concrete: an operator following DEPLOYMENT.md as written cannot deploy the Next.js app — there is no container target, no managed-platform config, and no documented runbook step that takes `pnpm build` to a running production process. P1 is appropriate because this gap blocks shipping the product end-to-end, even though the backend half is well-documented.</reason>
<parameter name="severity_adjusted">P1

</details>

---

### P1-11. error-tracking `[observability]`

**Location**: `app/backend/worker/run_worker.py:23, app/backend/worker/ingest.py:24`

**Claim**: Worker process never initializes Sentry, so every ingest exception (the most likely source of real-world bugs) is invisible to the error tracker.

**Evidence**: `run_worker.py:main()` only calls `logging.basicConfig(level=logging.INFO, ...)`. There is no `sentry_sdk.init(...)` anywhere in `app/backend/worker/`. `grep -rn 'sentry_sdk' app/backend` returns only the two hits in `api/main.py`. So when `ingest.py:428` runs `logger.exception('Ingest failed for gazette %s', gazette_id)`, the traceback goes to stderr only — Sentry's DSN configuration is loaded into Settings but never consumed by the worker. The API gets Sentry; the heavy-lifting subsystem that fails the most (PDF parsing, image extraction crashes, DB session timeouts) does not.

**Fix**: Add `_init_sentry()` (or factor it out of `api/main.py`) and call it from `worker/run_worker.py:main()` before `worker.work()`. Use `sentry_sdk.integrations.rq.RqIntegration` so RQ job failures get tagged with job_id/queue. Same DSN, same env tag — operators get one inbox covering both processes.

<details><summary>Verifier reasoning</summary>

Verified independently. `app/backend/worker/run_worker.py:23` only configures logging — no `sentry_sdk.init(...)` anywhere in `app/backend/worker/`. `grep -rn 'sentry' app/backend` confirms Sentry SDK is only imported/initialized in `api/main.py:14,42-50`, invoked from the FastAPI `lifespan` hook (line 58) which never runs in the worker process. The dependency `sentry-sdk[fastapi]==2.60.0` is in `requirements.txt` and `Settings.sentry_dsn` exists (settings.py:60), so the operator is paying for Sentry but only getting API coverage. Meanwhile the worker is where the heaviest failure-prone work happens (PDF parsing via pdfplumber, image extraction via PyMuPDF, batched DB writes, advisory locks). The exception handler at ingest.py:427-455 uses `logger.exception(...)` and re-raises — without Sentry init in the worker, the traceback goes to stderr only. The suggested fix (factor `_init_sentry` out of `api/main.py` and call it from `run_worker.py:main()` before `worker.work()`, with `RqIntegration`) is correct and minimal. The only nuance worth noting: failures aren't completely invisible — `gazette.error_message` captures up to 4000 chars of the exception string into the DB, stderr logs are written, and RQ's failed-job registry holds the traceback. So the gap is observability/inbox-unification, not pure data loss. P1 stands as defensible (error-tracking blind spot in the heaviest subsystem is a real operability issue).

</details>

---

### P1-12. structured-logging `[observability]`

**Location**: `app/backend/worker/run_worker.py:23`

**Claim**: Worker bypasses the structlog pipeline used by the API, so logs are not JSON in prod and lose the request_id correlation that links API uploads to the jobs they enqueue.

**Evidence**: `run_worker.py` calls `logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')` instead of `from api.logging_config import configure_logging; configure_logging(get_settings().env)`. Meanwhile `api/logging_config.py:20` carefully wires structlog → JSON-in-prod and routes stdlib `logging.*` through the same renderer. Result: a single ingest run that an operator wants to trace produces JSON lines from the API process (`{level:'info', request_id:'abc123', event:'gazette uploaded'}`) and plain text lines from the worker (`2026-05-29 12:00:00 INFO worker.ingest Ingested 837 rows from B_T2_2026.pdf`) — the worker line has no request_id field, so log-aggregator joins by correlation ID silently drop the worker half of the story.

**Fix**: Replace `logging.basicConfig(...)` with `configure_logging(get_settings().env)`. Persist the API's request_id by passing it through `Queue.enqueue(..., meta={'request_id': req_id})` and binding it via `structlog.contextvars.bind_contextvars` inside the job. This makes 'find every log line for the upload that failed' a single Loki/Datadog query.

<details><summary>Verifier reasoning</summary>

The finding is accurate and verifiable from the code. `app/backend/worker/run_worker.py:23` calls `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")` — a plain stdlib formatter — while `api/main.py:55-57` calls `configure_logging(get_settings().env)`, which sets up structlog with a `JSONRenderer` in prod/staging and routes stdlib logging through the same pipeline (`api/logging_config.py:35-54`). The worker's `ingest.py` uses `logger = logging.getLogger("worker.ingest")` and emits lines like "Ingested %s rows from %s" — those would render as JSON if the worker booted with `configure_logging`, but as plain text under `basicConfig`. The impact claim about request_id is also correct: `RequestIDMiddleware` (api/errors.py:29) binds the request_id via `bind_request_context` (structlog contextvars), but `routes/gazettes.py:152` enqueues the job with `Queue.enqueue("worker.ingest.ingest_pdf", str(g.id), ...)` — no `meta={"request_id": ...}` is passed, and the worker job doesn't pull or bind one. So a single ingest flow does produce mismatched log formats and no shared correlation ID, breaking the cross-process trace the suggested fix describes. The fix as proposed (call configure_logging + thread request_id through meta + bind_contextvars in the job) is correct and minimal. P1 severity is reasonable for an observability/operability gap of this scope in a system that already invested in structured logging for the other half of the pipeline; it's not a correctness bug, so not P0, but it actively negates the value of the existing request_id infrastructure for the worker side of every upload.

</details>

---

### P1-13. frontend-error-tracking `[observability]`

**Location**: `app/frontend/app/ (no error.tsx, no global-error.tsx, no Sentry)`

**Claim**: Frontend unhandled exceptions are completely invisible to operators — there is no error tracker, no global ErrorBoundary, and no Next.js `error.tsx` or `global-error.tsx` route.

**Evidence**: `find app/frontend/app -name 'error.tsx' -o -name 'global-error.tsx'` returns empty. `app/frontend/package.json` has no `@sentry/nextjs`, no logging or error-tracking dependency at all. `grep -rn 'ErrorBoundary\|useErrorBoundary' app/frontend/app app/frontend/components` returns nothing. `lib/api.ts:json()` throws on any non-OK response (line 143) but no caller catches it into a reporter — the error lands in React's default uncaught handler, which in prod-mode Next.js silently swallows it after rendering a generic '500' page. A user who hits a P0 frontend bug has zero way to escalate it except a screenshot.

**Fix**: Add `app/(app)/error.tsx` and `app/global-error.tsx` per Next.js 15 conventions; install `@sentry/nextjs`, run `npx @sentry/wizard@latest -i nextjs`, configure with the same DSN the backend uses (different `tag.service`). At minimum, an in-house `lib/error-report.ts` that does `fetch('/api/v1/client-errors', { method: 'POST', body: ... })` would be better than nothing.

<details><summary>Verifier reasoning</summary>

Verified independently. Filesystem walk of /Users/francisluong/Project/ASL/ImageExtractor/claude_csvbuilder/app/frontend/app/ confirms no error.tsx, no global-error.tsx, no not-found.tsx exist anywhere — neither in (app), (marketing), or login route groups. package.json has zero error-tracking dependencies (no @sentry/nextjs, no datadog, no bugsnag, no rollbar — only opentelemetry shows up as a transitive in pnpm-lock). Grep finds no ErrorBoundary class, no componentDidCatch, no useErrorBoundary, no window.onerror, no unhandledrejection listener, and no /api/v1/client-errors POST anywhere in app/components/lib or the backend api/ tree. lib/api.ts json() at line 138-144 does throw on non-OK responses as cited, but no top-level catch transports those to telemetry. The (app)/layout.tsx wraps AuthProvider + CmdKProvider + TopNav with no error boundary above or below. The impact is slightly softened by Next.js 15's built-in default error page (users see a generic error, not literal silence), but the operator-visibility claim stands: a P0 frontend bug produces no log line, no stack trace, no user-reportable trace ID. P1 is defensible for a product shipping authenticated revenue surfaces (Today digest, Watchlists, opposition windows) where a broken render directly degrades the value proposition. The suggested fix is sensible and Next.js-idiomatic.

</details>

---

### P1-14. audit-trail `[data]`

**Location**: `app/backend/api/db/models.py (no AuditLog table), app/SECURITY.md:73-75`

**Claim**: There is no append-only audit log for any sensitive action — gazette upload/reprocess, watchlist create/update/delete, user create/role change, mark enrichment runs. Forensic 'who saw what mark when' is impossible.

**Evidence**: Grep for `audit_log|AuditLog|audit_event` across `app/backend/` returns zero hits in code (only in docstrings and migration comments). `gazettes.uploaded_by` is a single nullable VARCHAR(255) — no FK to users, no timestamp of role change, no per-row history. SECURITY.md:74 explicitly says 'No append-only audit table for sensitive actions … logs aren't tamper-evident.' Structured logs go to stderr but no retention or signing is configured.

**Fix**: Add an `audit_events` table (id, actor_id, action, resource_type, resource_id, payload JSONB, created_at) and a thin `record_event(...)` helper invoked from each mutating route + the enrichment scripts. Keep it append-only by revoking UPDATE/DELETE at the role level. Required for any GDPR Article 30 record of processing.

<details><summary>Verifier reasoning</summary>

The finding is real and independently verifiable. (1) `app/backend/api/db/models.py` defines Gazette, Watchlist, Trademark, User, TmNameIndex — there is no AuditLog/audit_event table. (2) No migration in `app/backend/alembic/versions/` creates one (0001-0011 cover trademarks, watchlists, indexes, logo_path, users, tm_name_index — nothing audit). (3) `grep` for `audit_log|AuditLog|audit_event|AuditEvent` across the backend returns zero hits (the `scripts/audit_logos.py` matches are a logo-quality script, unrelated). (4) `Gazette.uploaded_by` is exactly as described: `String(255), nullable=True` set once at upload — no FK, no per-row history, no timestamp on role change in the User model. (5) `routes/watchlists.py:149-160` `delete_watchlist` performs `await session.delete(w); await session.commit()` with zero audit write — no `record_event`, no log-to-table call. Same pattern in the gazettes upload route (`uploaded_by=user.id` written to the row, but no separate immutable event). (6) `SECURITY.md:73-75` explicitly admits the gap, matching the cited evidence verbatim. Severity adjustment: the original P1 is appropriate. SECURITY.md still calls auth "the biggest gap" but `auth.py` is now real bcrypt+JWT — meaning the system IS moving toward production use, which makes the audit-log gap more load-bearing, not less. For a trademark gazette tool that processes PII-bearing applicant data (named individuals — flagged in SECURITY.md:82-85), the lack of forensic "who deleted whose watchlist when" / "who reprocessed gazette X" is a real compliance and incident-response gap. P1 (high but not P0 emergency) is the right call: no immediate exploitability, but unfixable retroactively once incidents happen.

</details>

---

### P1-15. gdpr `[data]`

**Location**: `app/backend/api/routes/auth.py (no DELETE), scripts/create_user.py (no companion delete script)`

**Claim**: There is no user-account deletion or right-to-erasure flow. No API endpoint, no CLI. The only way to remove a user is manual SQL — and doing so orphans `gazettes.uploaded_by` and `watchlists.owner_id`, which are bare VARCHARs with no FK constraint.

**Evidence**: `scripts/create_user.py` exists; no `delete_user.py`. Searching routes returns no DELETE /users/* endpoint. Schema: `gazettes.uploaded_by Mapped[str | None] = mapped_column(String(255), nullable=True)` and `watchlists.owner_id Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)` — neither has a `ForeignKey('users.id')`. Combined with finding #2, an orphaned watchlist (owner_id pointing to a now-deleted user UUID) becomes readable by anonymous callers via the unauth list path.

**Fix**: Add (a) a soft-delete column on users (`deactivated_at`), (b) an admin endpoint `DELETE /api/v1/users/{id}` that purges/anonymises watchlists owned by that user and nulls `gazettes.uploaded_by`, (c) FK constraints with `ON DELETE SET NULL` so the schema enforces the invariant. Document the retention policy and PII inventory required for GDPR Article 30.

<details><summary>Verifier reasoning</summary>

The core claims are independently verifiable. I confirmed: (1) `auth.py` exposes only login/refresh/logout/me — no DELETE /users/{id} or self-delete endpoint; grepping all routes turns up only one DELETE handler (`/watchlists/{id}`). (2) `scripts/` contains `create_user.py` but no companion `delete_user.py` or any module containing `delete_user`/`erasure`. (3) `models.py` line 92 defines `uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)` and line 123 defines `owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)` — neither uses `ForeignKey("users.id", …)`, while sibling columns like `gazette_id` clearly do (`ForeignKey("gazettes.id", ondelete="CASCADE")`). (4) Therefore a manual SQL `DELETE FROM users WHERE id=…` truly does orphan these fields with no DB-level guard. A partial mitigation exists — `User.is_active` is honored by login (auth.py:154) and refresh (auth.py:194), so soft-deactivation is available — but it's not exposed via any API/CLI and does not satisfy GDPR Article 17 erasure (PII in `users.email`, `users.name`, `password_hash` remains). One sub-claim is weak: the "becomes readable by anonymous callers via the unauth list path" framing is real but not orphan-specific — `watchlists.py:80` already returns ALL watchlists to anonymous callers regardless of owner_id, so orphaning doesn't materially worsen that exposure. That's a finding-#2 concern, not unique to erasure. Severity P1 is defensible for a product with a public marketing/pricing page (implying it may onboard external users) but the impact paragraph slightly overstates the cross-finding interaction. The underlying gap — no erasure mechanism at all, no FK constraints to enforce referential integrity on manual deletes — is genuine and warrants the suggested fix.

</details>

---

## Refuted P0/P1 (false positives caught by verifier)

These were originally flagged at P0/P1 but the verifier found counter-evidence. They are *not* punch-list items; recorded here for completeness so we don't re-discover them.

### R-1. `[P0]` data-integrity — refuted
- **Original location**: `app/backend/api/db/models.py:123, app/backend/api/routes/watchlists.py:106`
- **Original claim**: Watchlist.owner_id stores a stringified user UUID in `String(255)` with no foreign key to `users.id`. When a user is deleted (or `users` is rebuilt), watchlists become orphaned and `_assert_owned` will allow nobody (or, worse, an attacker who creates a user whose row gets the recycled UUID — defended only by UUID collision impossibility).
- **Why refuted**: The structural observation is accurate — `Watchlist.owner_id` (models.py:123) and `Gazette.uploaded_by` (models.py:92) are `String(255)` with no FK to `users.id`, and `routes/watchlists.py:106` stores `owner_id=user.id` (a stringified UUID). However the claimed impact does not hold: (1) There is NO user-delete endpoint in the entire backend — `grep router.delete` returns only the watchlist delete route. So orphaning via normal app use cannot occur. (2) Even if a user were deleted by direct DB manipulation, the `_assert_owned` check at line 167 (`if w.owner_id and w.owner_id != user.id`) would correctly 403 every other user because `w.owner_id` is still a non-null stringified UUID that matches nobody — i.e., "allow nobody" is the safe-failure behavior, not a vulnerability. The finding's "allow nobody (or worse...)" framing inverts the actual semantics: the orphan stays locked, it doesn't open up. (3) The "attacker creates a user with recycled UUID" vector requires a UUIDv4 collision (cryptographically impossible) AND the attacker would need to choose their own UUID, which `User.id` defaults via server-side `uuid.uuid4()` (models.py:275) — attackers can't pick it via the auth registration path. The finding itself concedes "defended only by UUID collision impossibility," which is in fact a complete defense for any real-world adversary. Adding the FK is reasonable schema hygiene (defense-in-depth, prevents typo'd manual inserts, enables ON DELETE SET NULL semantics for future delete endpoints), but it is P3 at most — not a P0 data-integrity issue with material risk to existing users or production data.

### R-2. `[P1]` missing-index — refuted
- **Original location**: `app/backend/api/db/models.py:185,189; app/backend/api/routes/_filters.py:141-144`
- **Original claim**: submission_date and registration_date_151 are queried in WHERE/range filters but neither has an index. Both queries seq-scan trademarks.
- **Why refuted**: Partially refuted. The registration_date_151 half is real: app/backend/api/routes/_filters.py:141-144 wires grant_date_from/to to Trademark.registration_date_151 with no backing index (verified across all 11 alembic migrations — only ix_trademarks_* indexes exist on gazette_id, record_type, application/certificate/madrid numbers, country_code, city, applicant_type, applicant_name, ip_agency, month, year). However, the submission_date half is fabricated: a repo-wide grep finds zero WHERE clauses on Trademark.submission_date. Every use in app/backend/api/routes/ (marks.py:106-107, 444) is an attribute read on an already PK-fetched row, never a filter. The finding's cited EXPLAIN against `WHERE submission_date >= ...` is a synthetic query not issued anywhere in the application. The "timeline/today routes also hit these dates" claim is also wrong — today.py and search.py filter and order on publication_date_441, not submission_date or registration_date_151 (publication_date_441 is itself unindexed, but that's a different finding the author didn't raise). Additionally, the cited 12.8ms/20.8ms EXPLAIN numbers don't justify P1 today — they're sub-30ms and not user-perceptible. The scaling argument to 750k rows is plausible but speculative (no booked timeline for 16x growth). At best this should be a P2/P3 single-column finding on registration_date_151 alone, with the submission_date claim dropped entirely. Because the finding bundles a real issue with a fabricated one and uses synthetic EXPLAIN evidence for a query that doesn't exist, the evidence fails adversarial review as written.

### R-3. `[P1]` data-pipeline-coverage — refuted
- **Original location**: `app/backend/scripts/load_tm_name_index.py + app/backend/scripts/enrich_mark_samples.py`
- **Original claim**: PR #48's wordmark backfill landed two production scripts that mutate ~42k trademark rows, yet there are no pytest assertions on either loader or enrichment behavior. The script is the canonical mechanism to remediate ~100% of A-record mark_sample NULLs, but neither dry-run output, idempotency, nor the JOIN logic is verified.
- **Why refuted**: The evidence is factually accurate — both scripts exist with the cited behaviors (BOM-strip via utf-8-sig, %y date parsing, ON CONFLICT DO UPDATE, 5000-row batches, skip counters, `(mark_sample IS NULL OR = '')` guard), and grepping app/backend/tests/ returns zero matches for either script name. However, the P1 severity and the framing as a data-pipeline-coverage risk do not survive scrutiny. (1) The same pattern holds for every script in app/backend/scripts/ — backfill_logo_paths, audit_logos, audit_fields, audit_enrichment, enrich_from_per_pdf_csvs, smoke_ingest, create_user all lack pytest coverage. The absence of tests for these new scripts is consistent with project convention, not a regression introduced by PR #48. (2) These are one-shot operator-run remediation scripts, not request-path code; both default to --dry-run (rollback) and require an explicit --execute flag. (3) A dedicated audit_enrichment.py script (151 lines, also in the PR) provides 10-row DB↔CSV spot-checking plus a coverage-gap report — a direct functional mitigation that the finding did not credit. (4) The cited harm ("inverting the guard would overwrite real (540) data") is purely hypothetical — there is no evidence of a typo in the current code, and dry-run + audit_enrichment.py would catch such a regression at run time. (5) PR #48 was already executed and verified live (per the commit message: /search?q=MARVIS, Today digest opposition windows), with documented residual coverage figures that match the audit script's output. Adding tests would be a reasonable maintainability improvement (P3), but characterizing this as a P1 data-pipeline risk overstates the actual exposure given the operator-controlled invocation, dry-run default, and existing audit tooling.

## P2 — quality debt (unverified, 48 items)

These are unverified by the workflow's verifier phase (cost decision). Treat as backlog candidates. Full evidence in `audit_2026_05_29.json` under `passthrough_p2`.

Categories with highest count:
- **data-integrity**: 4
- **wasted-index**: 3
- **a11y**: 2
- **auth**: 1
- **csp**: 1
- **rate-limit-bypass**: 1
- **brute-force**: 1
- **async-blocking**: 1
- **data-quality**: 1
- **datetime-naive**: 1
- **audit-baselines**: 1
- **ssr-stability**: 1
- **react-hydration**: 1
- **auth-ux**: 1
- **csv-parser**: 1

## P3 — nice-to-have (unverified, 20 items)

See `audit_2026_05_29.json` under `passthrough_p3`.

---

## How this plan was generated

Run from the repo root:

```
Workflow → tradenet-enterprise-audit (39 agents, ~18 min)
├── Phase 1 Audit: 8 parallel dimension auditors
├── Phase 2 Verify: 31 parallel verifiers (one per P0/P1 finding)
└── Phase 3 Synthesize: final ranked report
```

Each finding's full evidence + verifier reasoning is in `audit_2026_05_29.json`.

To re-run a similar audit in the future, the workflow script lives in the session's transcript dir (linked in the workflow result).
