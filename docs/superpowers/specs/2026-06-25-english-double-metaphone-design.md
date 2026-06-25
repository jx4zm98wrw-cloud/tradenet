# English Double Metaphone: non-VN phonetic encoder upgrade (Track 3a) — Design

**Status:** Approved for planning · 2026-06-25

**Goal:** Upgrade the conflict engine's **non-Vietnamese** phonetic encoder from single Metaphone to
**Double Metaphone**, so alternate-pronunciation foreign/English marks that single Metaphone
mis-encodes (e.g. **THOMAS vs TOMAS**, **CAESAR vs SEZAR**, **JOAQUIN vs WAKEEN**) score correctly on
the 30% phonetic sub-component. This is **Track 3a** — the close-out of the phonetic axis begun in
Track 2 (which routed Vietnamese pairs to a VN key and explicitly deferred Double Metaphone here).
Like Track 2 it is **schema-free** (pure code — no column, migration, backfill, or ingest wiring) and
**dependency-light** (a vendored pure-Python module — no new external dependency).

## Why (program context)

`phonetic_similarity` (`tm_similarity/phonetic.py`) blends **70% raw token Jaro-Winkler + 30%
phonetic-code JW**. After Track 2 the 30% component is language-routed: Vietnamese pairs use
`vn_phonetic_key`; everything else uses **single** English Metaphone (`jellyfish.metaphone`). Single
Metaphone emits **one** code and so picks **one** pronunciation for letters that have two valid ones
— `CH`=/k/ or /tʃ/, `C`=/k/ or /s/, `TH`=/θ/ or /t/, Spanish/Italian `J`/`GI`. When two marks spell
the *alternate* pronunciation, single Metaphone's codes diverge and the phonetic axis collapses.
**Double Metaphone** (Philips 2000) emits a `(primary, secondary)` pair capturing both pronunciations,
so the alternate matches.

### Prototype validation (2026-06-25, against the merged Track 2 engine + a reference Double Metaphone)

Measured phonetic-axis scores, single Metaphone (current `main`) vs Double Metaphone:

| Pair | single MP | Double MP | Mechanism |
|---|---|---|---|
| THOMAS / TOMAS | 0.898 | **0.965** | `TH` secondary code matches `TMS` exactly |
| CAESAR / SEZAR | 0.646 | **0.712** | `C` alternate `SSR` matches `SSR` exactly |
| JOAQUIN / WAKEEN | 0.611 | **0.678** | `J` secondary `AKN` matches `AKN` exactly |
| MACHARIA / MAKARIA | 0.918 | 0.918 | already caught (exact primary) |

**Every real win is an EXACT match via the second code** — high-confidence, not fuzzy. NIKE/ADIDAS
stays **0.0** (no spurious lift). The 4 wins lift the phonetic axis by ~0.07 each; modest by design
(the 70% raw-JW already carries spelling-similar marks — this closes the long-tail gap Track 2 named).

### The precision trade-off (documented, accepted)

Swapping encoders is not free: Double Metaphone can encode an unrelated **spelling-similar short**
pair to more JW-similar codes than single Metaphone did. Prototype: **APPLE/ORANGE** moved 0.404 →
0.563. The driver is **not** the second code — it is plain primary-vs-primary encoder variance
(DM `APL` vs `ARNJ` = 0.528 where single MP gave 0.0), on top of an **already-high 70% raw-JW of
0.578** (the spelling itself is what makes APPLE/ORANGE borderline, independent of any encoder).

This is **accepted, not mitigated in 3a**, because:
- It is a recall/precision trade — Double Metaphone raises recall on alternate-pronunciation matches
  at a small precision cost on adversarial spelling-similar pairs.
- The **70% raw-JW remains the dominant driver**; the encoder swap only moves the minority 30%.
- The engine's **verdict guards** are the safety net: a lone phonetic bump cannot become a verdict
  without `class_o ≥ 0.20` and `mark_strength ≥ 0.50` AND the goods-dampener
  (`composite.py:composite_score`). APPLE vs ORANGE with no goods overlap stays **Low risk**.
- A comparison-method redesign (exact-match gating, Jaro-without-Winkler on codes, primary-weighting)
  is **out of scope** — it would entangle a clean encoder swap with calibration of the comparison
  function, which belongs with the broader Track 3b precision work if it proves necessary.

Source: Lawrence Philips, "The Double Metaphone Search Algorithm," *C/C++ Users Journal* 18(6), 2000.
Reference behaviour cross-checked against the `metaphone` PyPI package's `doublemetaphone` (used at
design time only; NOT a runtime dependency).

## Current state (what we're changing)

`tm_similarity/phonetic.py:phonetic_similarity` — the routed 30% component (post-Track-2):

```python
if is_vietnamese(a) and is_vietnamese(b):
    a_codes = [k for k in (vn_phonetic_key(tok) for tok in _tokens(na)) if k]   # VN — UNCHANGED
    b_codes = [k for k in (vn_phonetic_key(tok) for tok in _tokens(nb)) if k]
else:
    a_codes = [c for c in (jellyfish.metaphone(tok) for tok in _tokens(na)) if c]   # <-- single MP, CHANGED
    b_codes = [c for c in (jellyfish.metaphone(tok) for tok in _tokens(nb)) if c]
if not a_codes or not b_codes:
    return round(raw * length_factor, 3)
short, long = (a_codes, b_codes) if len(a_codes) <= len(b_codes) else (b_codes, a_codes)
phon = _best_pair_jw(short, long)
return round((0.7 * raw + 0.3 * phon) * length_factor, 3)
```

Only the **else (non-VN) branch** and its comparison change. The VN branch, the 70% raw-JW, and the
`length_factor` are byte-for-byte unchanged.

## Resolution

### 1. New vendored module `tm_similarity/double_metaphone.py` (stdlib only)

A pure-Python implementation of Philips' Double Metaphone, header-attributed to the published
algorithm (BSD/MIT-compatible reference). Public surface:

```python
def double_metaphone(word: str) -> tuple[str, str]: ...   # (primary, secondary); secondary "" if none
```

Sibling to `phonetic.py`; imported by it. No new external dependency — the package stays
**stdlib + jellyfish** (this module needs no third-party import; Jaro-Winkler on the resulting codes
still comes from `jellyfish`). Returns `("", "")` for empty/non-alphabetic input.

### 2. Comparison: best-pair JW over code-SETS (non-VN branch)

Each token yields a **code-set** — its 1–2 non-empty Double Metaphone codes. The similarity between
two tokens is the **maximum** Jaro-Winkler over the cross-product of their code-sets (so an alternate
pronunciation on either side can match). Best-pair across tokens, averaged over the longer list —
identical aggregation to the existing `_best_pair_jw`, only the per-pair score changes from
single-string JW to code-set max-JW.

```python
def _codeset(token: str) -> tuple[str, ...]:          # 1–2 non-empty DM codes, else ("",)
    return tuple(c for c in double_metaphone(token) if c) or ("",)

def _best_pair_codeset_jw(short, long) -> float:      # mirrors _best_pair_jw; per-pair = max cross-JW
    ...   # pair score = max(jw(x, y) for x in a_codes for y in b_codes)
```

### 3. Routing edit in `phonetic_similarity` (the only edit to `phonetic.py`)

```python
else:                                                 # non-VN — Double Metaphone
    a_sets = [_codeset(tok) for tok in _tokens(na)]
    b_sets = [_codeset(tok) for tok in _tokens(nb)]
    if not a_sets or not b_sets:
        return round(raw * length_factor, 3)
    short, long = (a_sets, b_sets) if len(a_sets) <= len(b_sets) else (b_sets, a_sets)
    phon = _best_pair_codeset_jw(short, long)
    return round((0.7 * raw + 0.3 * phon) * length_factor, 3)
```

The VN branch is untouched. (`jellyfish.metaphone` is removed from this function; `jellyfish` stays
imported for `jaro_winkler_similarity`.)

## Data flow

```
phonetic_similarity(a, b):
  raw            = best-pair JW on diacritic-stripped tokens               # 70%, unchanged
  if is_vietnamese(a) and is_vietnamese(b):
      code       = best-pair JW on vn_phonetic_key(token)                  # 30%, VN route (Track 2)
  else:
      code       = best-pair (max cross-JW) on double_metaphone(token)     # 30%, non-VN route (Track 3a)
  return (0.7*raw + 0.3*code) * length_factor
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `double_metaphone.py:double_metaphone` | (primary, secondary) DM codes for a word | stdlib only |
| `phonetic.py:_codeset` / `_best_pair_codeset_jw` | code-set extraction + max-cross-JW best-pair | `double_metaphone`, `jellyfish` |
| `phonetic.py:phonetic_similarity` | route the non-VN 30% to DM; blend unchanged | above + `vn_phonetic` (VN branch) |
| `__init__.py` | bump `SIMILARITY_VERSION` `"1.2"→"1.3"`; export `double_metaphone` | — |

`composite.py`, `visual.py`, `classes.py`, `features.py`, `vn_phonetic.py` — unchanged. No
route-adapter change (`marks.py`/`compare.py`/`search.py` call `phonetic_similarity` via `score()`/
rerank).

## Versioning

- `SIMILARITY_VERSION`: `"1.2" → "1.3"` (non-VN phonetic scoring semantics change).
- No schema version / backfill (pure code).

## Behaviour change & testing (targeted pytest only — sweep tests reset the live singleton)

Frozen-axis discipline (same as Tracks 1/2): visual / class / vienna golden values stay
**byte-identical**; only **non-VN-routed** phonetic values are intentionally regenerated.

1. **Vendored-module unit tests:** `double_metaphone(word)` returns the expected `(primary, secondary)`
   for a reference table, asserted against the implementation's verified outputs captured at build
   time, covering the ambiguous clusters `TH`, `C`/`CC`, `CH`, `SCH`, `X`, `GN`/`KN`/`WR` silent
   onsets, Spanish/Italian `J`/`GI`. Include empty/non-alphabetic → `("", "")`.
2. **Calibration set (committed artifact + regression guard):**
   - DM lifts (assert ≥ floor, and assert strictly greater than the single-Metaphone score):
     `THOMAS`/`TOMAS` (~0.965), `CAESAR`/`SEZAR` (~0.712), `JOAQUIN`/`WAKEEN` (~0.678).
   - No over-merge (assert < ceiling): a realistic non-confusable English pair `NIKE`/`ADIDAS`
     (stays ~0.0). **Not** APPLE/ORANGE — that pair's score is driven by the 70% raw-JW, not the
     encoder, so it is not a clean encoder-precision guard.
3. **Routing test:** a non-VN pair uses Double Metaphone (assert a known alternate-pronunciation
   pair scores higher than under single Metaphone); a VN pair still routes to the VN key (unchanged
   score — e.g. `TRANG`/`CHANG` identical to its Track-2 value).
4. **Golden update:** regenerate the non-VN phonetic values in `tests/_similarity_cases.py`
   `PHONETIC_CASES`. Prototype shows the **only** change is `Gemy`/`KAVIN SAVING POWER`
   `0.0 → 0.019` (golden index 1); the VN-routed `Taseko/Tabeko` (0.911) and `CÔNG TY DƯỢC` (0.67)
   and the unchanged `Sulfani` (1.0) / `VIET AGAROYAL` (0.556) stay put. Assert class / vienna /
   composite golden rows are unchanged.
5. **Search rerank:** `test_search_phonetic_two_stage.py` stays green; if a non-VN query's ranking
   shifts to the new (intended) order, update the expectation explicitly, not silently.

## Out of scope (Track 3a)

- **No weight change** to the 70/30 blend or `DEFAULT_WEIGHTS`/`composite_score` (that is Track 3b's
  5-axis weight-reallocation scope). `composite.py` untouched.
- **No semantic / conceptual axis** (Track 3b) — no embeddings, no 5th axis, no IO, no new schema.
- **No VN encoder change** (Track 2 owns the VN branch).
- **No comparison-method redesign** (exact-match gating / Jaro-without-Winkler / primary-weighting).
  The max-cross-product JW mirrors the existing single-MP machinery; revisit only if 3b's precision
  work shows the accepted trade-off is too costly.
- **No new external dependency** (vendored pure-Python module); **no schema / migration / backfill /
  ingest** — pure code.
- No frontend change.

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- `tm_similarity` stays dependency-light (stdlib + `jellyfish`); `double_metaphone.py` is stdlib-only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic
  check && pytest` (targeted pytest locally; run BOTH `ruff check` and `ruff format --check` — they
  are separate gates).
- Frontend unaffected. Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **`double_metaphone.py`**: vendor the pure-Python Double Metaphone (attributed); unit tests
   against a verified reference table (ambiguous clusters + empty input).
2. **Comparison helpers + routing**: add `_codeset` / `_best_pair_codeset_jw`; swap the non-VN branch
   to Double Metaphone; remove `jellyfish.metaphone` from `phonetic_similarity`; bump
   `SIMILARITY_VERSION` to `"1.3"`; export `double_metaphone`; routing test.
3. **Calibration set + golden update**: commit the labelled non-VN confusion set (DM lifts +
   NIKE/ADIDAS guard); regenerate the one changed `PHONETIC_CASES` value (`Gemy` 0.0→0.019); assert
   frozen axes unchanged; keep search two-stage green.
4. **Docs sync**: CLAUDE.md (extend the phonetic-axis note — non-VN now Double Metaphone, version 1.3,
   the accepted precision trade-off).
