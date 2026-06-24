# Similar Marks: sight-or-sound gate + mark_name scoring — Design

**Status:** Approved for planning · 2026-06-24

**Goal:** Stop the *"Similar marks landing this period"* card from surfacing same-class marks that share **no** text/visual resemblance with the subject mark. Make the card score on the **resolved `mark_name`** (finishing the #106 migration into the ranking layer) and gate on the similarity engine's own **conjunction verdict** (`!= "Low risk"`) instead of a bare `composite ≥ 0.30`.

## Problem

Live example — mark **"Gemy"** (`/marks/1658e936…`, applicant *Foshan Ailihua Sanitary Ware*, class 11, no Vienna codes, `mark_sample` ∅, `mark_name` = "Gemy"). The card showed **KAVIN SAVING**, **KAITA**, **Kastaler**, **LỘC TỔNG HUY** — all class 11, none phonetically/visually related. Their only commonality is the class.

Root causes in `app/backend/api/routes/marks.py` `similar_marks` (`/{id}/similar`):

1. **Figurative-anchor recall is a class+period screen.** `anchor_word = (m.mark_sample or "").strip()` (`:353`). "Gemy" has empty `mark_sample`, so it takes the `else` branch (`:375-384`): "40 rows sharing any Nice class within ±60 days." That pulls class-mates, exactly the weakness the docstring admits for crowded classes — even though "Gemy" *has* a resolved name.
2. **It scores on the applicant, not the mark.** `m_text = m.mark_sample or m.applicant_name` (`:386`) and `r_text = r.mark_sample or r.applicant_name` (`:398`). With `mark_sample` empty it compares **"Foshan Ailihua Sanitary Ware"** vs "KAVIN SAVING POWER…" — the same applicant-as-name bug #106 fixed for *display*, still alive in the **similarity engine** (a denormalized field only helps surfaces that read it; this one was never migrated).
3. **The only gate is `composite ≥ 0.30`** (`_SIMILAR_MIN_COMPOSITE`, `:412`). Class overlap (20% weight) + applicant-name phonetic noise clears 0.30 with zero real mark similarity. The conjunction rule the scorer already enforces for verdicts (`composite_score`, `similarity.py:434-444`: `Possible` requires `mark_strength ≥ 0.50 ∧ class ≥ 0.20 ∧ composite ≥ 0.50`) is **not applied** to this card.

## Resolution

Two coupled, migration-free changes in `marks.py:similar_marks`:

### A. Score on the resolved name, drop the applicant fallback
- `m_text = (m.mark_name or m.mark_sample or "").strip()` — and the same for each candidate `r_text = (r.mark_name or r.mark_sample or "").strip()`.
- This mirrors `markDisplay`'s resolution (`mark_name ?? mark_sample`) and **removes `applicant_name` from the scoring text** entirely. A figurative mark with no transcribed name anywhere → empty text → **no phantom phonetic signal** (the engine then relies on the visual/pHash axis alone, as it should).

### B. Recall by the resolved name; gate on the engine verdict
- **Recall anchor:** `anchor_word = (m.mark_name or m.mark_sample or "").strip()`. So a named-but-figurative mark like "Gemy" enters the **wordmark recall branch** (trigram/dmetaphone on candidates' `mark_sample`, index-backed) instead of the class screen. For "Gemy" this recalls genuine "Gem*"-type wordmarks (likely none this period → honest empty card), never class-mates. Truly nameless marks (`mark_name` NULL and `mark_sample` ∅) still fall to the class+period screen — correct, there is no text to recall by.
- **Gate:** replace `if cs.composite >= _SIMILAR_MIN_COMPOSITE` with `if cs.verdict != "Low risk"`. `composite_score` already returns `verdict ∈ {"Likely conflict","Possible conflict","Low risk"}`, where non-"Low risk" means it passed the conjunction guard (`mark_strength ≥ 0.50 ∧ class ≥ 0.20 ∧ composite ≥ 0.50`). So the card shows exactly the marks the engine itself calls a Possible/Likely conflict — the same rule Compare uses. Delete the now-unused `_SIMILAR_MIN_COMPOSITE` constant. The returned `score` stays `cs.composite`.

No new threshold constant is introduced: the gate reuses the verdict so the card and Compare can never disagree on what "conflict" means.

## Data flow

```
similar_marks(id):
  anchor = m.mark_name or m.mark_sample            # B: recall by resolved name
    → wordmark branch (named) | class+period screen (truly nameless)
  per candidate r:
    m_text = m.mark_name or m.mark_sample          # A: no applicant fallback
    r_text = r.mark_name or r.mark_sample
    cs = composite_score(phonetic, visual, class, vienna, …)
    keep iff cs.verdict != "Low risk"              # B: conjunction gate (reuses engine)
  sort by cs.composite desc, top `limit`
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `marks.py:similar_marks` | recall by `mark_name`; score on `mark_name`; gate on `verdict` | `Trademark.mark_name` (#106), `composite_score.verdict` |
| `composite_score` (unchanged) | composite + verdict (the conjunction rule, single source) | — |

No change to `similarity.py`, no migration (reuses the `mark_name` column from #106 and the existing `verdict`).

## Testing (targeted pytest only — sweep tests reset the live singleton)

Seed marks directly and call the route (mirror existing `similar_marks` tests):

- **Class-only, no resemblance → excluded.** Subject "Gemy" (class 11, `mark_sample` ∅, `mark_name` "Gemy"); candidate "KAVIN SAVING…" (class 11, different name, same period). Response is **empty** (verdict Low risk → dropped). This is the regression test for the reported bug.
- **Real phonetic match, same class → included.** Subject "Gemy"; candidate "Gemmy"/"Gemi" (class 11, same period) → returned, `score` > 0.
- **Applicant name no longer influences scoring.** Subject with `mark_sample` ∅, `mark_name` ∅ but a distinctive `applicant_name`; a candidate sharing class + a similar *applicant* but unrelated `mark_name` → **excluded** (applicant text is never read).
- **Figurative pair with a real visual match → included when a second signal is present.** Two no-name marks (`mark_name` ∅) with pHash-similar logos in the same class/period are returned **when they also share Vienna codes** (the norm — Vienna codes *are* the classification of a mark's figurative elements, so real visual twins almost always share them): the visual + vienna axes push the composite past the 0.50 floor → `Possible conflict`. A bare pHash resemblance with **no** shared Vienna code (and no name/sound) lands `composite ≈ 0.44` → `Low risk` → excluded; that is the intended precision boundary (a lone pHash match with no shared figurative classification is most likely a coincidence). Confirms dropping the applicant fallback doesn't kill genuine figurative matches. Covered by `test_composite_figurative_phash_visual_*` in `tests/test_similarity.py` (the verdict logic is exercised at the engine level; no logo fixtures needed).
- **Verdict-gate parity:** a candidate scoring `composite ≈ 0.4` from class+noise (old behaviour surfaced it) now has `verdict == "Low risk"` → excluded.

## Out of scope (v1)

- **No `gin_trgm` index on `mark_name`.** Candidate *recall* still matches against `mark_sample`'s existing trigram index; only the anchor *query string* and the *scoring* text switch to `mark_name`. Consequence: a candidate whose `mark_sample` is empty but `mark_name` is set is not recalled by trigram (it can still appear via the class+period screen when the subject is nameless). Adding a `mark_name` trigram index for symmetric recall is a separate follow-up — YAGNI until a real miss is observed.
- No change to the compare scorecard, the weights, or `composite_score` itself.
- No frontend change — the card already renders whatever `/{id}/similar` returns (including an empty list, which it must handle today).

## Constraints

- **No migration** (uses `trademarks.mark_name` from #106 + existing `verdict`). NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest` (targeted pytest locally).
- Stale-doc cleanup: drop the "mocked similarity until PR #5" comment at `marks.py:9` (the engine is real now).

## Decomposition (for the plan)

1. **Scoring text → `mark_name`** (change A): `m_text`/`r_text` resolve `mark_name or mark_sample`, no applicant fallback. Test: applicant text no longer influences results.
2. **Recall anchor + verdict gate** (change B): anchor `mark_name or mark_sample`; gate `verdict != "Low risk"`; delete `_SIMILAR_MIN_COMPOSITE`. Tests: class-only excluded, real phonetic/visual match included, verdict-gate parity. Stale-comment cleanup.
