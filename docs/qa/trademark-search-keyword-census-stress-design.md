# Trademark Search — Census + Careful-Verification + Stress Design (refined)

Refinement of the "Keyword & Query Design" doc, rebased on the **real Tradenet system**
and the **measured corpus** (238,149 rows, sampled live). Supersedes the generic
keyword doc's scope header. Companion to
[`trademark-search-qa-plan-v2-tradenet.md`](trademark-search-qa-plan-v2-tradenet.md).

**Confirmed requests driving this version:**
1. **Full census** — exercise *every* mark (~238k), not a statistical sample.
2. **Careful per-result verification** — self-recall + appno lookup + count integrity + rank.
3. **Stress test** — 10 / 100 / 1000 concurrent connections, **against an unthrottled local
   instance** (measure the real ceiling, not the rate limiter).
4. Census runs with the **rate limit lifted locally** so 238k completes fast.

---

## 0. Corrected scope (measured, not assumed)

The generic doc's "5 searchable fields, all operators claimed, Madrid-heavy multi-script"
does **not** match our system. Ground truth from the live DB:

| Generic claim | Measured reality | Action |
|---|---|---|
| 5 free-text search fields (Mark, appno, **Nice, Legal status, Owner**) | `q` searches **mark_name + mark_sample + application/certificate/madrid number** only (`LIKE %q%`). Nice/owner are **facet filters**; "legal status" isn't a column (only `mark_status`, `ip_agency_status`, `vn_grant_date`) | Census = mark + IDs. Facets = **group F** (separate). Drop "legal-status field". |
| All operators claimed (wildcard, Boolean, …) | `q` has **no wildcard/Boolean parser**; real operators are **phonetic** (`mode=phonetic`), fuzzy (trigram), substring, diacritic-insensitive (phonetic only) | Test the real operators as S1; wildcard/Boolean = **exploratory (S3)**. |
| Oversample **CJK / Cyrillic** (Madrid) | CJK in mark_name: **3**; Cyrillic: **19**; in mark_sample: **0 / 5** | **`blocked` — no corpus.** Drop C-03/C-04. |
| Multi-script Madrid | Madrid is **~19k (8%)** and **romanized**; VN-diacritic marks: **52,259** | Keep VN-diacritic (C-01/C-02); Madrid tested by source-distinction, not native script. |
| ~200k records | **238,149** (domestic_application 119,355 · domestic_registration 99,799 · madrid_registration 10,620 · madrid_renewal 8,375) | Census target = 238,149. |
| Appno `4-YYYY-NNNNN` | **219,154** match (92%); `madrid_number` populated on **8,375**; `certificate_number` on 110,419 | Census IDs cover all three number columns. |

---

## 1. Census strategy (full coverage, not sampling)

**Goal:** prove the search behaves correctly for **every** mark, not a representative sample.
Sampling/Wilson-CI is replaced by **exhaustive iteration** over the 238,149 rows for the
per-mark *identity* checks (§2). Similarity / ranking / operator / adversarial groups remain
**targeted suites** (they have no per-mark 238k notion).

**Throughput model:** the search API rate-limits at ~20 rps (HTTP 429). For the census we
**lift the limit on the local test instance** (§6) and run at full concurrency, so one census
pass over 238k is ~20–40 min instead of 3+ hours. Every case is still flushed to JSONL and the
run is resumable (checkpoint = last application_number processed), so a 238k pass survives
interruption with zero loss.

**Iteration source:** stream the gold set straight from Postgres in `application_number` order
(stable, resumable cursor), not random sampling:
```sql
SELECT application_number, mark_name, mark_sample, madrid_number, certificate_number,
       mark_category, nice_classes
FROM trademarks ORDER BY application_number;   -- the census spine
```

## 2. Per-mark checks (the "careful verification", all four confirmed)

For **each** of the 238k marks, run and record:

| Check | Query | Pass condition | Severity if broken |
|---|---|---|---|
| **C1 self-recall** | `q = mark_name` (or `mark_sample` if name null), `mode=text`, `threshold=0` | the mark's `application_number` is in the result set | **S1** (missed mark) |
| **C2 appno lookup** | `q = application_number` (and `madrid_number` when present) | result set contains exactly that mark | **S1** |
| **C3 count integrity** | `q = mark_name` | `total == min(DB_count(q), TEXT_RECALL_CAP)`; paged ids have no dup/gap | **S1** (wrong counts) |
| **C4 rank / top-N** | same as C1, `sort=similarity` | exact mark ranks in top-N (configurable, default 5) | **S2** (ranking) |

"Careful" = on any failure, persist the **full raw response** (`evidence/<appno>.json`), the
query, the expected vs observed, and the bucket/score — so every one of the (expected few)
failures is auditable, not just counted. Honest oracle rules (already validated): owner-text in
`q` returning 0 is *correct* (mark-only box); a figurative mark with no name is **blocked**, not
failed; diacritic-insensitivity is expected only in `mode=phonetic`.

**Headline census metrics:** exact-recall %, appno-lookup %, count-integrity %, top-N rank %
— each a **true population rate over 238,149** (no CI needed; it's a census), with the failing
appno list attached per metric.

## 3. Targeted functional/operator suite (real capability only)

Run as focused sets (not census-scale):
- **Operators that exist** → S1 if broken: phonetic (Latin + the 52k VN-diacritic), fuzzy
  (typo/transposition/OCR), substring/contains, diacritic-insensitive (phonetic).
- **Operators that don't** → exploratory **S3 findings**, never S1: trailing/mid wildcard
  (`*`,`?`), Boolean AND/OR/NOT. Document actual vs intuitive behavior.
- **NFC vs NFD** (C-02) — paired equivalence over real VN-diacritic marks.
- **Source distinction** (C-09) — domestic vs Madrid via `mark_category`.

## 4. Confusing-similarity suite (the clearance core — keep + harden)

The genuinely valuable part of the original doc. Build `<query> → <expected similar mark>`
pairs along **textual** axes: phonetic, visual letter-swap (O↔0, l↔1, rn↔m, vv↔w),
truncation, addition/deletion, transposition, diacritic variance, spacing/joining.

**Two hardening requirements the original omitted:**
1. **Independent gold pairs.** Engine-derived perturbations (transform a real mark → variant
   → expect it back) are *circular* — they test the engine against its own transform. Add a
   **hand-curated set of known-confusable real pairs** (distinct real marks an examiner would
   call confusable) as the trustworthy oracle. Label each pair `synthetic` vs `curated`.
2. **Precision, not just recall.** For each similarity query, sample the **top-N returned** and
   score relevance (curated/heuristic), so the report shows **precision alongside recall** — a
   clearance tool that floods results scores high recall and is useless. Report F1.

Feeds B-06/07/08/09 (variant recall) and E-01/E-03 (variants rank *below* exact).

## 5. Ranking-probe suite (keep)

Single queries that yield exact + similar hits to expose order quality: exact-first (E-01),
prefix-vs-substring (E-02), exact-vs-fuzzy (E-03), tie-break shorter/closer (E-04), and
**ranked (`sort=similarity`) vs plain (`sort=publication-desc`) set-parity** (E-05: identical
set, order differs). Note the live finding: exact matches can sit among same-bucket ties
(tie-broken by id) and fall outside top-5 — E-01/E-04 quantify this.

## 6. Stress / load suite (NEW — 10/100/1000 conns, unthrottled local)

**Prerequisite — lift the limiter on the local test instance.** The ~20 rps cap (HTTP 429)
otherwise masks real capacity. Disable/raise the rate-limit middleware for the dedicated test
instance only (env/config toggle; do **not** change production defaults). Record the exact
toggle in the run metadata. This is the only app-side change the whole effort needs, and it is
test-environment-only.

**Design:** an async load generator (httpx + asyncio, or k6/vegeta) replays a fixed,
representative query mix (exact names, substrings, appno, phonetic, one ultra-broad single
char) at controlled concurrency levels **10 → 100 → 1000** simultaneous connections, each
level held for a steady-state window after warmup.

**Per level, measure:** achieved throughput (req/s), latency **p50 / p95 / p99 / max**, error
rate by class (timeout / 5xx / connection-reset), and CPU/mem of backend + Postgres if
observable. **Find the saturation point** — the concurrency where p95 crosses the SLO
(p95 < 3s typical, < 5s broad) or errors climb — and report it explicitly.

**Separately characterize the limiter** (informational): the same ramp against the *throttled*
API documents its 429 / Retry-After behavior under flood — useful for API consumers, but not
the capacity number.

**Caveat to state in the report:** unthrottled numbers are a *capacity ceiling*, not what a
client sees in production (which the limiter caps). Both are reported, clearly labelled.

## 7. Adversarial / boundary (keep)

empty/whitespace (D-01), 500+ char (D-02), special/control chars (D-03), injection-safety
(D-04 — backend is SQLAlchemy-parameterised; assert no 5xx / no leak), space-normalization
(D-05), ultra-broad single char (D-06 — stable, count caps at 1000), no-result (D-09),
idempotency/determinism (D-10 — strict equality, scores are jitter-free).

## 8. Query hygiene (keep)

Confirm operator grammar in Phase 0 before generating operator queries; store raw **and**
normalized forms (never silently strip diacritics/case before sending); URL/Unicode-encode and
verify the wire payload; seed reproducibly with provenance (which real `application_number`
each query derives from); one intent / one oracle / one case ID.

## 9. Explicitly blocked / dropped (no corpus or no capability)

- **CJK (C-03)** — 3 records. **Cyrillic (C-04)** — 19. Cannot stratify/oversample; `blocked`.
- **Wildcard / Boolean operators** — not parsed; exploratory S3, not S1 false-claims.
- **Legal-status-as-field (A-06)** — no such searchable column; covered (if needed) via the
  `granted`/`vn_grant_date` facet in group F (141,961 granted).
- **Nice / Owner as free-text fields** — they're facet params → **group F** (fast-follow),
  not part of the `q` census.

## 10. Run sequence

1. Smoke gate (connectivity, schema, DB read-only, one of each check).
2. **Lift local rate limit** (test instance) + record toggle.
3. **Census** over 238,149 (C1–C4), resumable, full evidence on failure → census metrics + failing-appno lists.
4. **Targeted suites** (operators, similarity+precision, ranking, adversarial).
5. **Stress ramp** 10/100/1000 unthrottled → throughput/latency/error/saturation; + limiter characterization.
6. Report: census population rates, similarity precision/recall/F1, ranking findings, stress
   curves + saturation point, verified-defects-by-severity, recommended final approach.
