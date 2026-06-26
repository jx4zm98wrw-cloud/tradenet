# Confidence-aware visual weight (Track 3c) — Design

**Status:** Approved for planning · 2026-06-26

**Goal:** Make the visual axis weight depend on the **kind** of visual evidence: a genuine
perceptual-hash (pHash) match is independent evidence and should weigh more, while a
text-derived "typographic" visual is correlated with phonetic and should weigh as it does today.
This closes the one **permanent** recall gap left by Track 3b-2 — a nameless figurative-mark
look-alike (near-identical logo, no transcribed name) that dropped below the "Possible" flag
threshold under the v1.4 phonetic-protective reweight — **without disturbing sound-alike recall**.

## Why (program context)

The 5-axis engine scores sound (phonetic) · sight (visual) · meaning (semantic) · class · vienna.
Track 3b-2 reallocated weights to `{phonetic .35, visual .15, semantic .15, class .20, vienna .15}`
(funding the new semantic axis mostly out of visual, .25→.15). That reweight had a documented,
spec-accepted side effect: pairs whose only signal is visual lost flag strength. Two real-world
verdicts fell out of flagging:

- **LIPITOR/LIPITAR** (sound-alike, similar text): 0.521→0.425. **Transient** — its visual is
  *typographic* and the two names are lexically near-identical, so once `backfill_mark_embedding`
  populates the corpus, LaBSE gives it a real semantic score that lifts it back. Self-heals at
  rollout. **Not addressed here.**
- **Figurative twin** (nameless, near-identical logo, shared Vienna codes): 0.587→0.492.
  **Permanent** — the mark is nameless, so `mark_name` is NULL → `mark_embedding` is always NULL →
  semantic is always 0, and phonetic is always 0. Its *entire* conflict signal is a real pHash
  visual match (~0.95), carried by a single 0.15 weight while 0.50 of the mark-weight budget
  (`.35 phonetic + .15 semantic`) sits dead. That is the gap Track 3c fixes.

The root cause: the engine has **one** visual weight, but visual evidence comes in two
qualitatively different kinds. Track 1 already routes the visual *score* by confidence
(`"phash"` vs `"typographic"` vs `"none"`); Track 3c extends that routing to the *weight*.

## Current state (the seam we hook into)

`tm_similarity/visual.py:visual_similarity` returns `VisualScore(score, confidence)`.
`tm_similarity/__init__.py:score` passes `visual_confidence=vis.confidence` into
`composite_score`. Inside `composite_score` (`tm_similarity/composite.py`) the confidence is used
**only** to decide whether the visual score enters `mark_strength` (the conjunction guard). The
visual *weight* (`w["visual"]`, default 0.15) is applied flat, regardless of confidence.

So the confidence signal is **already at the decision point** — Track 3c needs no new plumbing,
no signature change, and no caller change.

## Resolution

### The change (one file: `tm_similarity/composite.py`)

Introduce a module constant and a confidence-gated, copy-on-write weight boost applied at the top
of `composite_score`, before the `mark_score` math:

```python
PHASH_VISUAL_BOOST = 2.0
"""A genuine perceptual (pHash) visual match is independent evidence; a
typographic visual is JW on the wordmark text, correlated with phonetic. Boost
the visual weight ONLY for pHash-confidence pairs, then renormalise the five
weights for this pair. Typographic / none are unchanged."""

w = weights or DEFAULT_WEIGHTS
if visual_confidence == "phash":
    w = dict(w)                       # copy: never mutate the caller's / module-global weights
    w["visual"] *= PHASH_VISUAL_BOOST
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}
```

Everything after this block — `mark_score`, `goods_score`, `mark_strength`, `goods_factor`, and
the verdict bands — is **byte-identical** to v1.4.

**Design properties (true by construction):**

- **The boost cannot perturb the conjunction guard.** `mark_strength` is `max` of the raw axis
  *scores* (`phonetic`, `semantic`, and `visual` when phash) — never of the weights. So a genuine
  pHash twin already has `mark_strength ≈ 0.95` and passes the guard; the boost only lifts the
  weighted composite *number* across the 0.50 Possible floor. Verdict-band thresholds are unchanged.
- **Copy-on-write is load-bearing.** When `weights is None`, `w` *is* the module-global
  `DEFAULT_WEIGHTS`; the `dict(w)` copy on the phash path prevents in-place mutation from poisoning
  every later score in the process. The non-phash path reads `w` without copying (safe).
- **Multiplier, not a fixed weight (decision A2).** The boost scales whatever base weight is in
  play — `DEFAULT_WEIGHTS` *or* a per-matter watchlist override resolved by `resolve_weights` —
  proportionally. A visual-heavy matter boosts more; a visual-light matter boosts less. The
  operator's chosen emphasis is respected, not clobbered. `resolve_weights` stays the untouched
  single source of truth for *base* weights; the boost is a separate, confidence-gated modifier.
- **pHash-only; typographic stays flat (refinement of the original framing).** Lowering the
  typographic visual weight would push sound-alike pairs (whose visual is typographic, e.g.
  LIPITOR/LIPITAR at visual 0.675) *further* below threshold pre-backfill — the opposite of the
  recall goal. The minor double-counting of typographic visual with phonetic is accepted; recall
  protection wins. Only `"phash"` is boosted; `"typographic"` and `"none"` are unchanged.
- **No gating threshold (YAGNI).** A *weak* pHash match (e.g. 0.25) times a boosted weight is
  still a small contribution → no spurious verdict change. The boost is on the weight, so low
  scores stay low. No minimum-score tunable is introduced.

### Behavioral impact (boost = 2.0 → visual 0.15 → ~0.26 effective after renorm)

| Pair | confidence | v1.4 | v1.5 | Verdict change |
|---|---|---|---|---|
| Figurative twin (vis 0.95, vienna 1.0, class 1.0) | phash | 0.492 Low | ~0.55 | **Low → Possible** (the fix) |
| pHash + weak phonetic (existing guard test) | phash | 0.522 Possible | ~0.578 | unchanged (Possible) |
| All-strong (phon 1.0, vis 0.8) | phash | 0.745 Likely | ~0.752 | unchanged (Likely) |
| MONTINIS/MONTANIS | typographic | 0.669 | 0.669 | untouched |
| LIPITOR/LIPITAR | typographic | 0.425 | 0.425 | untouched (recall protected) |

Only pHash pairs move; every typographic / none pair is exactly as v1.4. That isolation is the
point of the design.

## Components & boundaries

| Unit | Responsibility | Change |
|---|---|---|
| `tm_similarity/composite.py` | `PHASH_VISUAL_BOOST` + confidence-gated weight boost/renorm | the only behavioral change |
| `tm_similarity/__init__.py` | `SIMILARITY_VERSION` | `1.4` → `1.5` |

`resolve_weights`, `composite_score`'s **signature**, `visual.py`, `score()`, the API routes
(`marks.py`, `compare.py`), the DB schema, the worker, and the frontend are all **untouched**.
`composite_score` already receives `visual_confidence`, so routes pass it unchanged.

## Versioning

- `SIMILARITY_VERSION = "1.5"` (engine behaviour changes for pHash pairs).
- No data-derivation version (`PHASH_VERSION` etc.) changes — no stored data is recomputed.

## Testing (targeted pytest only — sweep tests reset the live singleton)

1. **Scenario flip:** the v1.4 figurative-twin test (`..._now_low_after_reweight`) is renamed and
   now asserts **"Possible conflict"** with the recomputed composite (~0.552). This is the headline
   behavioural change.
2. **Sound-alike regression guards:** explicit assertions that LIPITOR/LIPITAR stays **0.425 / Low**
   and MONTINIS/MONTANIS stays **0.669 / Possible** — both typographic, both must be byte-identical
   to v1.4. This proves Track 3c did not touch sound-alike recall.
3. **Other pHash scenarios unchanged in verdict:** the existing pHash guard test and the all-strong
   Likely test keep their verdicts (composite numbers rise slightly; update the inline arithmetic
   comments / any asserted composite value).
4. **Per-matter compose:** a watchlist with a custom (e.g. visual-light) weight set still receives a
   *proportional* phash boost — the multiplier composes with `resolve_weights` output, not just
   `DEFAULT_WEIGHTS`.
5. **Golden regen:** regenerate only the pHash-confidence entries in `tests/fixtures/similarity_golden.json`
   / `COMPOSITE_CASES`; typographic / none goldens stay byte-identical.
6. **Version-pin tests (explicitly in scope — do not let targeted pytest miss them):**
   `tests/test_double_metaphone.py::test_version_and_export` and
   `tests/test_vn_phonetic_routing.py::test_version_bumped` pin `SIMILARITY_VERSION` and must move
   `1.4` → `1.5`. These are the exact files a targeted run missed during the 3b-2 CI pass; the plan
   must name them so the full-suite CI gate is not the first thing to catch them.

The 470 MB LaBSE model never runs in CI (semantic is irrelevant to this track — the boosted pairs
are figurative/nameless with semantic 0 anyway).

## Out of scope (3c)

- **No verdict-threshold recalibration** (the 0.50 / 0.70 bands stay). The figurative twin re-flags
  via the weight boost lifting its *composite*, not by lowering a band. A global threshold drop
  would broaden flagging corpus-wide and remains a separate, measured exercise if recall regresses.
- **No typographic down-weighting** — would regress sound-alike recall (see above).
- **No new visual-confidence kinds, no pHash-score recalibration** (Track 1's `VISUAL_PHASH_THRESHOLD`
  is unchanged).
- **No schema / migration / ingest / route / frontend change** — engine-only, schema-free.
- **No LIPITOR-class fix** — that drop is transient and self-heals once `backfill_mark_embedding`
  runs; the rollout gate (run `backfill_mark_name` → `backfill_mark_embedding` before enabling 1.4+)
  already covers it.

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- `tm_similarity` stays stdlib + `jellyfish` only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic
  check && pytest` (run BOTH ruff gates; targeted pytest locally).
- Frontend unaffected. Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **`composite.py`**: add `PHASH_VISUAL_BOOST` + the confidence-gated copy-on-write boost/renorm
   block; verdict/`mark_strength`/dampener untouched. Unit tests: figurative-twin flip to Possible,
   pHash guard/all-strong verdicts stable, copy-on-write does not mutate `DEFAULT_WEIGHTS`,
   per-matter custom weights boosted proportionally.
2. **Sound-alike regression guards**: assert LIPITOR (0.425/Low) and MONTINIS (0.669/Possible) are
   byte-identical to v1.4.
3. **Goldens + version**: regenerate pHash golden entries; bump `SIMILARITY_VERSION` to `1.5`;
   update the two version-pin tests (`test_double_metaphone`, `test_vn_phonetic_routing`).
4. **Docs**: CLAUDE.md visual-axis section gains a Track 3c "confidence-aware visual weight" note
   (pHash visual weight boosted ×2 then renormalised; `SIMILARITY_VERSION` 1.5); update the
   Track 3c memory item from "queued" to "done".
