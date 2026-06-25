# VN Phonetic Axis: Vietnamese-aware phonetic key + language routing (Track 2) — Design

**Status:** Approved for planning · 2026-06-25

**Goal:** Make the conflict engine's **phonetic axis** catch Vietnamese aural confusion that the
current English-Metaphone component is blind to (e.g. **"GIA HƯNG" vs "DA HƯNG"**, **"TRANG" vs
"CHANG"**). Add a pure-stdlib Vietnamese phonetic key, routed in for VN-vs-VN comparisons by a
Vietnamese-ness detector, using **Northern-canonical** consonant mergers and an
onset–glide–nucleus–coda key, **toneless**. This is **Track 2** of the five-axis reliability
program; like Track 1 it is behaviour-changing (recall-oriented this time), but unlike Tracks 0/1
it is **schema-free** (pure code — no column, migration, backfill, or ingest wiring).

## Why (program context)

`phonetic_similarity` (`tm_similarity/phonetic.py`) blends **70% raw token Jaro-Winkler + 30%
English-Metaphone-encoded JW**. Metaphone is "English pronunciation only" (Wikipedia; Beider-Morse
2008) and mis-encodes Vietnamese sound-alikes, so genuinely confusable VN marks score low on the
30% component. Track 2 replaces *only that 30% component, and only when both marks read as
Vietnamese*, with a VN-aware key.

### Research validation (deep-research, 2026-06-25 — 19 sources, 25 claims adversarially verified)

Core decisions are corroborated by authoritative sources:

- **Northern mergers are textbook Hanoi phonology** — `d/gi/r → /z/`, `ch/tr → /tɕ/`, `s/x → /s/`,
  confirmed verbatim by **Kirby (2011), JIPA "Vietnamese (Hanoi Vietnamese)"** (peer-reviewed) and
  Wikipedia *Vietnamese phonology* (3-0 verification).
- **Onset–(glide)–nucleus–(coda)–tone** is the correct syllable model over a flat Soundex squash:
  Kirby — "a Vietnamese syllable consists of three obligatory elements: an onset, a tone and a
  vowel … optionally … an obstruent, nasal, or approximant coda," with **exactly eight coda
  segments** `/p t k m n ŋ j w/`. Formula **(C1)(w)V(G|C2)+T**.
- **Language-routing the phonetic axis is office-sanctioned/best-practice** — Beider-Morse
  determines language from spelling first, then applies language-specific rules; EUIPO assesses
  aural similarity per the relevant language's pronunciation; **IP Vietnam** (Circular 01/2007 amd.
  06/2016; Decree 65/2023/ND-CP; Circular 23/2023/TT-BKHCN) lists *pronunciation/reading* as an
  **independently-sufficient** confusing-similarity axis.
- **A dependency-free, rule-based VN G2P already exists** — `vPhon` (Kirby; pure-stdlib, Pham 2006
  rules) proves the stdlib-only constraint is feasible. We **reimplement the published phonological
  correspondences** (cite Kirby/Pham), and do **not** install heavy derivatives (`Viphoneme` pulls
  in C++ `vinorm` + `underthesea`).

Two points were **not** validated and shape scope:

- **Southern final-consonant mergers** (`-n/-ng`, `-t/-c`, `v/d`) were **refuted (0-3)** against the
  cited evidence → **Northern-only** is the right scope; Southern is explicitly out (would need
  fresh primary sourcing).
- **Toneless comparison is unvalidated** — flagged as the likeliest source of over-merging false
  positives. We proceed toneless by decision (it matches the existing diacritic-stripped pipeline,
  maximises cross-tone aural-confusion recall — `MA`/`MÁ`/`MÃ` *are* confusable — and the engine's
  conjunction guard filters phonetic-only matches lacking goods overlap). The calibration set (§
  Testing) is the early-warning if it over-merges.

Sources: Kirby 2011 (lel.ed.ac.uk/~jkirby/docs/kirby2011vietnamese.pdf); Wikipedia *Vietnamese
phonology*; `github.com/kirbyj/vPhon`; Beider-Morse (stevemorse.org/phonetics/bmpm2.htm); EUIPO
Guidelines 3.4.2 Phonetic comparison; IP Vietnam practitioner analyses (Lexology/KENFOX/WinterIP).

## Current state (what we're changing)

`tm_similarity/phonetic.py`:
- `normalize_vn(s)` — uppercase, collapse whitespace, **strip Vietnamese diacritics** (incl. tone).
  Already toneless. Unchanged.
- `_token_jw` / `_best_pair_jw` — best-pairing token Jaro-Winkler. Unchanged; reused for the VN key.
- `phonetic_similarity(a, b)` — `round((0.7*raw + 0.3*metaphone) * length_factor, 3)`. The **only**
  function changed: the `0.3*metaphone` term routes (below). Receives the **original** strings
  (before normalisation), so the detector can read diacritics.

Consumers: the engine (`score()` → compare/similar) **and** `search.py` phonetic-mode rerank — both
call `phonetic_similarity`, so the change ripples to search ranking automatically.

## Resolution

### 1. New pure module `tm_similarity/vn_phonetic.py` (stdlib only — `re`)

```python
def is_vietnamese(text: str | None) -> bool: ...
def vn_phonetic_key(token: str) -> str: ...
```

Sibling to `phonetic.py`; imported by it. No new dependency (the package stays stdlib + jellyfish;
this module needs only `re`).

### 2. `is_vietnamese(text)` — language detector (on the ORIGINAL, diacritic-bearing text)

Two signals, OR'd:
1. **Diacritics** — contains any Vietnamese-specific letter/tone mark (`ă â ê ô ơ ư đ` or a tonal
   accent on a vowel) → Vietnamese. Strong and cheap.
2. **Phonotactic fallback** (for toneless VN like "GIA HUNG") — every whitespace token parses as a
   valid Vietnamese syllable `(onset)? + vowel-cluster + (final-coda)?` drawn from the VN
   inventories. "MAYBELLINE" fails (`L` is not a legal VN coda); "GIA"/"HUNG" pass.

Empty/blank → `False`.

### 3. `vn_phonetic_key(token)` — the key (toneless)

Operate on the normalised (diacritic-stripped, uppercased) token. Greedy-parse **(C1)(w)V(G|C2)**
and emit canonical phoneme codes:

- **Onset** (longest-match first: `NGH > NG > GH > GI > CH > TR > TH > KH > PH > QU > C > K > Q > G > D > R > S > X > …`), canonicalised with **Northern merges**:
  - `/k/` ← `c, k, q`; `/z/` ← `d, gi, r`; `/tɕ/` ← `ch, tr`; `/s/` ← `s, x`;
    `/ŋ/` ← `ng, ngh`; `/f/` ← `ph`; plus distinct codes for `nh, kh, th, g/gh, b, l, m, n, p, t, v,
    h, đ`. Each phoneme → a stable single-char code (collision-free internal alphabet).
- **Medial on-glide** `/w/` — present in `QU-` and `o/u` before a main vowel (`OA`, `OE`, `UY`, `UÂ`…).
- **Nucleus** — the diacritic-stripped vowel letters (`A E I O U`; `Y`→`I`).
- **Coda** from the **8-segment set** `/p t k m n ŋ j w/`: final `c/ch → /k/`, `ng → /ŋ/`, `nh →`
  its palatal code, `i/y → /j/` off-glide, `o/u → /w/` off-glide, plus `p t m n`.

Examples (canonical codes shown schematically): `GIA, DA, RA → Z·A` (all `/z/`+`A`); `TRANG, CHANG
→ tɕ·A·ŋ`; `QUANG → k·w·A·ŋ`; `MAI → m·A·j`. Comparison: **best-pair JW on the keys** of each token
(same machinery as the Metaphone path — graded, handles multi-word marks).

### 4. Routing in `phonetic_similarity` (the only edit to `phonetic.py`)

```python
na, nb = normalize_vn(a), normalize_vn(b)
if not na or not nb: return 0.0
raw = _token_jw(na, nb)
length_factor = ...                                   # unchanged

if is_vietnamese(a) and is_vietnamese(b):             # pair-level route (originals, with diacritics)
    keys_a = [vn_phonetic_key(t) for t in _tokens(na)]
    keys_b = [vn_phonetic_key(t) for t in _tokens(nb)]
    code_jw = _best_pair_jw(short, long)              # on VN keys
else:
    code_jw = _best_pair_jw(metaphone_codes...)       # current English path, unchanged

return round((0.7*raw + 0.3*code_jw) * length_factor, 3)
```

Pair-level (both VN) keeps the two compared keys in the **same phonetic space** — mirrors Track 1's
"both figurative" gate. The 70% raw-JW and length dampener are byte-for-byte unchanged.

## Data flow

```
phonetic_similarity(a_original, b_original):
  raw            = best-pair JW on diacritic-stripped tokens          # 70%, unchanged
  if is_vietnamese(a) and is_vietnamese(b):
      code       = best-pair JW on vn_phonetic_key(token)             # 30%, VN route
  else:
      code       = best-pair JW on metaphone(token)                   # 30%, English route (current)
  return (0.7*raw + 0.3*code) * length_factor
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `vn_phonetic.py:is_vietnamese` | detect VN-ness from original text | stdlib `re` |
| `vn_phonetic.py:vn_phonetic_key` | onset–glide–nucleus–coda key, Northern merges, toneless | stdlib `re` |
| `phonetic.py:phonetic_similarity` | route the 30% component; blend unchanged | `vn_phonetic`, `jellyfish` |
| `__init__.py` | bump `SIMILARITY_VERSION` `"1.1"→"1.2"`; export `is_vietnamese`, `vn_phonetic_key` | — |

`composite.py`, `visual.py`, `classes.py`, `features.py` — unchanged. No route-adapter change
(`marks.py`/`compare.py`/`search.py` already call `phonetic_similarity` via `score()` /rerank).

## Versioning

- `SIMILARITY_VERSION`: `"1.1" → "1.2"` (phonetic scoring semantics change for VN pairs).
- No schema version / backfill (pure code).

## Behaviour change & testing (targeted pytest only — sweep tests reset the live singleton)

Frozen-axis discipline (same as Track 1): visual / class / vienna golden values stay **byte-
identical**; only the **phonetic** values for **VN-routed** pairs are intentionally regenerated.

1. **Confusion calibration set (committed artifact + regression guard):** a small labelled set of VN
   pairs asserting the engine now scores them as intended:
   - High phonetic (should be flagged): `GIA HƯNG`/`DA HƯNG`, `TRANG`/`CHANG`, and the IP-Vietnam
     short-mark cases `LAKA`/`LACCA`, `MEKO`/`MECO`.
   - Low phonetic (must NOT over-merge): a segmentally-distinct VN pair (e.g. `BAO LONG`/`MINH
     QUAN`). This pair is the toneless-over-merge early-warning the research called for.
2. **`is_vietnamese` unit tests:** diacritic-bearing → True; toneless valid-syllable (`GIA HUNG`) →
   True; foreign (`MAYBELLINE`) → False; empty → False. Document the detector's known coarseness:
   some foreign words parse as VN-syllabic (e.g. `SAMSUNG`); a mis-route only swaps the *30%*
   component's encoder and `raw` JW (70%) dominates, so the harm of a false-positive route is low.
3. **`vn_phonetic_key` unit tests:** `GIA`=`DA`=`RA` (same key); `TRANG`=`CHANG`; `QU` medial glide;
   `MAI` off-glide `/j/` coda; `c/k/q` → same onset code; `ng/ngh` → same.
4. **Routing test:** a VN-vs-VN pair uses the VN key (assert a known VN sound-alike scores higher
   than it did under Metaphone); a VN-vs-foreign pair falls to the Metaphone path (unchanged score).
5. **Golden update:** regenerate the phonetic values for the VN-routed cases in
   `tests/_similarity_cases.py` `PHONETIC_CASES` (e.g. the `CÔNG TY DƯỢC` pairs now route VN);
   assert the visual / class / vienna / composite-with-fixed-inputs golden rows are unchanged.
6. **Search rerank:** `test_search_phonetic_two_stage.py` stays green; if a VN query's ranking
   shifts, update the expectation to the new (intended) order, not silently.

## Out of scope (Track 2)

- **No Southern dialect mergers** (refuted by the evidence; would need primary sourcing).
- **No tone modelling** (toneless by decision; first lever to revisit if the calibration set shows
  over-merging — but not built now, YAGNI).
- **No weight change** to the 70/30 blend or `DEFAULT_WEIGHTS` (the blend is internal calibration;
  the research did not corroborate a specific split, and changing it is Track 3's weight-reallocation
  scope). `DEFAULT_WEIGHTS` and `composite_score` untouched.
- **No schema / migration / backfill / ingest** — pure code.
- **No new dependency**; no copying of `vPhon`/GPL code (reimplement cited facts).
- **No English/non-VN encoder change.** The `else` branch keeps single English Metaphone for all
  non-Vietnamese marks (English, French, German, pinyin, romaji). Upgrading it to **Double
  Metaphone** (jellyfish has only single Metaphone; would need a small vendored pure-Python module)
  is a known, lower-urgency improvement — the 70% raw-JW already carries spelling-similar foreign
  marks, so Metaphone's long-tail gap is smaller than the VN gap was — and is **deferred to Track 3**
  alongside the broader multilingual/semantic work (decided 2026-06-25).
- No semantic/conceptual axis (Track 3); no frontend change.

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- `tm_similarity` stays dependency-light (stdlib + `jellyfish`); `vn_phonetic.py` uses only `re`.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker tm_similarity && alembic
  check && pytest` (targeted pytest locally).
- Frontend unaffected. Never `pnpm build` while `pnpm dev` is live.

## Decomposition (for the plan)

1. **`vn_phonetic.py` — `vn_phonetic_key`**: onset/glide/nucleus/coda parse + Northern merge tables
   (cited from Kirby/Pham); unit tests (merge equivalences, glide/coda).
2. **`vn_phonetic.py` — `is_vietnamese`**: diacritic + phonotactic detector; unit tests.
3. **Route `phonetic_similarity`**: branch the 30% component; export the new fns; bump
   `SIMILARITY_VERSION` to `"1.2"`; routing test.
4. **Calibration set + golden update**: commit the labelled VN confusion set; regenerate VN-routed
   `PHONETIC_CASES`; assert frozen axes unchanged; keep search two-stage green.
5. **Docs sync**: CLAUDE.md (the phonetic-axis note + the research-cited Northern/toneless scope).
