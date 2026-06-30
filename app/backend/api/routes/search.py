"""Scored search — extends /api/trademarks with a similarity score per result.

Per-mode scoring:
  - text:     match-quality bucket vs the resolved wordmark (exact 0.98 /
              substring 0.92 / token 0.78 / prefix 0.76) — a literal search, so
              the score is deterministic (no jitter) and the threshold filters by
              bucket; `total` is the post-threshold count, like phonetic.
  - phonetic: REAL Jaro-Winkler + Metaphone via tm_similarity. NEUROFAX
              correctly surfaces NEUREX (both encode NRKS-family).
  - vienna:   REAL Jaccard overlap of the user's selected figurative codes
              against the mark's stored vienna_codes — a row sharing 3/3
              codes outranks one sharing 1/3.
  - image:    placeholder 0.78 until uploaded-image pHash lands (need the
              upload pipeline + a hash of the source bytes first).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tm_similarity import phonetic_similarity

from .._dedup import dedup_key_expr, representative_marks
from ..db import RecordType, Trademark, get_session
from ..schemas import TrademarkOut
from ._filters import build_trademark_where, normalize_vienna_code, vienna_code_match

router = APIRouter(prefix="/api/v1/search", tags=["search"])

SearchMode = Literal["text", "phonetic", "image", "vienna"]

# Phonetic search is a two-stage retrieval: a cheap pg_trgm `%` candidate recall
# in Postgres (stage 1), then a precise rerank by tm_similarity (stage 2). This
# is the recall cap — the max candidates pulled from the DB before reranking.
# Generous so the trigram net surfaces sound-alikes the engine will score high
# (NEUREX/NEUROFAX share the "neu"/"eur" trigrams), bounded so the Python
# rerank stays fast. Marks whose true phonetic match shares no trigram with the
# query are the known recall gap; widening it is a Metaphone-key-index follow-up.
PHONETIC_RECALL_CAP = 1000

# Text mode is a similarity search too (the threshold filters by match-quality
# bucket), so its "how many match" count is post-threshold — which means scoring
# every WHERE-match, not just a pagination window. Cap it the same way phonetic is
# capped: a real brand query matches far fewer than this; a pathological 1-char
# query is bounded.
TEXT_RECALL_CAP = 1000

# Widen pg_trgm's `%` operator below its 0.3 default: recall should be permissive
# (the reranker decides), and short brand names often sit at 0.15–0.30 similarity
# even when clearly sound-alike.
_PHONETIC_TRGM_THRESHOLD = 0.15


class ScoredMark(BaseModel):
    mark: TrademarkOut
    score: float


class SearchResultsOut(BaseModel):
    items: list[ScoredMark]
    total: int
    limit: int
    offset: int


def _jitter(seed: str, lo: float = -0.04, hi: float = 0.04) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return lo + (hi - lo) * (h % 1000) / 1000.0


# ---- Query-time result dedup -------------------------------------------------
# The `trademarks` table holds ONE ROW PER GAZETTE APPEARANCE, so a single mark
# can surface twice: a domestic mark appears as an A-file application row (has a
# publication date) AND a B-file registration row (has the certificate); a Madrid
# mark appears as a registration row AND a renewal row. Both rows are real and
# carry distinct data, so we never delete/merge them in the DB — instead we
# collapse them in the search RESULT SET so a single mark renders one card and
# `total` counts unique marks. This is query-time only: it works automatically
# for future ingests with nothing to re-run.


def _dedup_key(m: Trademark) -> str:
    """Group rows that represent the SAME mark.

    Domestic application + registration rows share an `application_number`;
    Madrid registration + renewal rows share a `lineage_key` (the IRN, NULL
    appno). Figurative / no-id rows fall back to the row `id`, so distinct
    no-id marks never collapse together.
    """
    return m.application_number or m.lineage_key or str(m.id)


def _dedup_pref(m: Trademark) -> tuple[bool, bool, str]:
    """Preference rank within a dedup group — the max wins.

    Keep the most-advanced/complete record so the surviving card shows the
    registered status: a registration (certificate present) beats a bare
    application, then a granted row beats an ungranted one, with the row `id`
    as a stable, deterministic final tiebreak.
    """
    return (bool(m.certificate_number), m.vn_grant_date is not None, str(m.id))


def _dedup_marks(rows: list[Trademark]) -> list[Trademark]:
    """Reduce rows to one per `_dedup_key`, keeping the preferred row per group.

    First-seen key order is preserved (deterministic given the upstream SQL
    ORDER BY); callers re-sort by score afterwards regardless.
    """
    best: dict[str, Trademark] = {}
    for m in rows:
        k = _dedup_key(m)
        cur = best.get(k)
        if cur is None or _dedup_pref(m) > _dedup_pref(cur):
            best[k] = m
    return list(best.values())


def _score(
    mark: Trademark,
    q: str | None,
    mode: SearchMode,
    has_vienna: bool = False,
    vienna_query: list[str] | None = None,
) -> float:
    """Per-mark similarity score in [0, 1] for the active search mode.

    When the user hasn't supplied a similarity *target* — no text query in
    text/phonetic mode, no codes in Vienna mode — the threshold slider is
    conceptually irrelevant (nothing to be "similar" to). Return 1.0 so the
    row passes regardless of where the slider sits; otherwise filter-only
    searches (country=GB&nice_class=41&...) silently return zero rows
    even though the header reports a non-zero filter-match count.
    """
    # Filter-only search: no target supplied → similarity threshold doesn't apply.
    if mode in ("text", "phonetic") and not q:
        return 1.0
    if mode == "vienna" and not has_vienna:
        return 1.0

    if mode == "phonetic" and q:
        # Real engine: Jaro-Winkler on diacritic-normalised raw text blended
        # with JW on Metaphone codes. Compare against the resolved mark name
        # (mark_sample → mark_name); a mark with no transcribed name scores ~0
        # (nothing to sound like). No jitter — the real signal carries its own
        # ordering.
        target = mark.mark_sample or mark.mark_name or ""
        return round(phonetic_similarity(q, target), 3)

    if mode == "vienna" and vienna_query:
        # Coverage score: fraction of the user's requested codes that the
        # mark satisfies, respecting parent → child prefix expansion
        # ("5.7" matches "5.7.1"). Plain Jaccard wouldn't work — the DB
        # stores leaf codes, so set equality between "5.7" (parent) and
        # "5.7.1" (leaf) is 0 even though the SQL pre-filter matched.
        #
        # The SQL pre-filter already ensured at least one code overlaps;
        # this just ranks how completely the request is satisfied so
        # 3-of-3 beats 1-of-3.
        mark_codes = mark.vienna_codes or []
        if not mark_codes:
            return 0.0
        satisfied = sum(
            1 for req in vienna_query if any(c == req or c.startswith(req + ".") for c in mark_codes)
        )
        return round(satisfied / len(vienna_query), 3)

    if mode == "image":
        # Placeholder. The uploaded-image pipeline isn't wired yet — when it
        # lands, this branch will pHash the uploaded bytes once and call
        # tm_similarity.visual_similarity() per row against logo_phash.
        return round(min(0.999, 0.78 + _jitter(str(mark.id))), 2)

    # mode == "text" — substring-strength heuristic. Text mode is a literal
    # search, not a similarity search; the score expresses how cleanly the
    # query matched the wordmark or applicant string, not how phonetically
    # close they are.
    base = 0.6
    if q:
        ql = q.lower()
        wordmark = (mark.mark_sample or mark.mark_name or "").lower()
        bag = " ".join(
            t
            for t in (
                (mark.mark_sample or "").lower(),
                (mark.mark_name or "").lower(),
            )
            if t
        )
        # ID/number fields are matched by build_trademark_where too (application
        # / certificate / madrid number). A query that hits one is an identifier
        # lookup, not a fuzzy name match — score it as strong as a wordmark hit
        # so the similarity threshold never filters an exact registration-number
        # search out of the results (the row matched the WHERE but otherwise
        # scored ~0.6 and got dropped, producing "1 match" + "No matches").
        ids = [
            (mark.application_number or "").lower(),
            (mark.certificate_number or "").lower(),
            (mark.madrid_number or "").lower(),
        ]
        if wordmark == ql or ql in ids:
            base = 0.98
        elif ql in wordmark or any(i and ql in i for i in ids):
            base = 0.92
        elif ql in bag:
            base = 0.78
        elif wordmark[:3] == ql[:3]:
            base = 0.76
    # No jitter: text mode is a literal search, so the score IS the match-quality
    # bucket (exact 0.98 / substring 0.92 / token 0.78 / prefix 0.76 / 0.60).
    # This keeps the threshold deterministic — equally-relevant matches share a
    # bucket and never straddle the slider by random ±0.04 noise.
    return round(base, 2)


@router.get("/trademarks", response_model=SearchResultsOut)
async def search_trademarks(
    q: str | None = Query(None),
    mode: SearchMode = Query("text"),
    threshold: float = Query(0.4, ge=0, le=1, description="Minimum similarity"),
    country: str | None = Query(None, min_length=2, max_length=2),
    nice_class: list[str] | None = Query(None),
    nice_class_mode: Literal["any", "all"] = Query("any"),
    vienna_codes: list[str] | None = Query(None),
    vienna_codes_mode: Literal["any", "all"] = Query("any"),
    record_type: RecordType | None = None,
    mark_category: str | None = Query(None),
    applicant_type: str | None = Query(None),
    applicant: str | None = Query(None),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    gazette_id: uuid.UUID | None = None,
    ip_agency: str | None = Query(None),
    designated_country: str | None = Query(None),
    granted: bool | None = Query(None),
    grant_date_from: date | None = Query(None),
    grant_date_to: date | None = Query(None),
    sort: Literal["similarity", "publication-desc", "applicant-asc", "class-count"] = "similarity",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> SearchResultsOut:
    # Normalize Vienna codes to the stored representation (DB stores `4.3.3`
    # not `04.03.03`). Codes that don't pass shape validation are dropped
    # silently — better than 0 results from a typo'd code segment.
    norm_vienna: list[str] | None = None
    if vienna_codes:
        norm_vienna = [c for c in (normalize_vienna_code(v) for v in vienna_codes) if c]
        # Vienna mode skips the text `q` field — codes ARE the query.
        if mode == "vienna":
            q = None

    # The shared WHERE builder uses ALL semantics for array contains.
    # For ANY semantics we run a separate where with array overlap.
    # Phonetic mode does NOT want the literal `ILIKE %q%` filter — NEUROFAX must
    # be reachable from a "NEUREX" query even though it doesn't contain that
    # substring. Recall is handled by the pg_trgm `%` operator below instead.
    where = build_trademark_where(
        q=q,
        exclude="q" if mode == "phonetic" else None,
        country=country,
        nice_class=nice_class if nice_class_mode == "all" else None,
        vienna_codes=norm_vienna if vienna_codes_mode == "all" else None,
        record_type=record_type,
        mark_category=mark_category,
        applicant_type=applicant_type,
        applicant=applicant,
        year=year,
        month=month,
        gazette_id=gazette_id,
        ip_agency=ip_agency,
        designated_country=designated_country,
        granted=granted,
        grant_date_from=grant_date_from,
        grant_date_to=grant_date_to,
    )
    if nice_class and nice_class_mode == "any":
        where.append(Trademark.nice_classes.op("&&")(nice_class))
    if norm_vienna and vienna_codes_mode == "any":
        # ANY semantics with parent-code expansion: a request for `5.7`
        # should match any `5.7.x`. OR together each code's match clause
        # (each is exact-or-prefix per vienna_code_match).
        where.append(or_(*[vienna_code_match(c) for c in norm_vienna]))

    has_vienna = bool(norm_vienna)

    # ---- Phonetic: two-stage retrieval ------------------------------------
    # Stage 1 (recall, in Postgres): pg_trgm `%` over BOTH phonetic-target
    # columns, ordered by best trigram similarity, capped at PHONETIC_RECALL_CAP.
    # Stage 2 (rerank, in Python): the real Jaro-Winkler + Metaphone engine.
    # This replaces the old path that only scored a date-ordered ~100-row window
    # and therefore could never surface the global top conflicts.
    if mode == "phonetic" and q:
        ql = q.lower()
        # Recall = trigram-similar OR same Double-Metaphone code. The dmetaphone
        # equality path catches sound-alikes that share no trigram with the query
        # but encode to the same phonemes (the pure-trigram recall gap). The
        # mark_sample arms are index-backed (GIN trgm + btree dmetaphone from
        # migrations 0012/0013); the mark_name arms get their matching GIN-trgm +
        # dmetaphone indexes from migration 0032. The Python engine reranks the
        # union precisely. Owner text (applicant_name) is intentionally NOT a
        # recall arm — the box matches the mark, not its owner.
        dmeta_q = func.dmetaphone(ql)
        recall_clauses = [
            *where,
            or_(
                func.lower(Trademark.mark_sample).op("%")(ql),
                func.lower(Trademark.mark_name).op("%")(ql),
                func.dmetaphone(func.lower(Trademark.mark_sample)) == dmeta_q,
                func.dmetaphone(func.lower(Trademark.mark_name)) == dmeta_q,
            ),
        ]
        # Best trigram similarity across the mark-name columns (mark_sample /
        # mark_name). A NULL column yields NULL similarity, which greatest()
        # skips — so a mark with no mark_sample still ranks on mark_name.
        trgm_rank = func.greatest(
            func.similarity(func.lower(Trademark.mark_sample), ql),
            func.similarity(func.lower(Trademark.mark_name), ql),
        )
        recall_stmt = (
            select(Trademark)
            .where(and_(*recall_clauses))
            .order_by(trgm_rank.desc(), Trademark.id)
            .limit(PHONETIC_RECALL_CAP)
        )
        # Widen the `%` threshold for this statement only. SET LOCAL is scoped
        # to the surrounding transaction and resets automatically; the value is
        # a trusted module constant, not user input, so inlining it is safe.
        await session.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {_PHONETIC_TRGM_THRESHOLD}"))
        candidates = list((await session.execute(recall_stmt)).scalars().all())
        # Collapse application/registration (and Madrid registration/renewal) row
        # pairs into one result BEFORE reranking, so a single mark recalled via
        # both its gazette rows reranks and pages as one card. total is len(scored)
        # below, so it stays consistent with the deduped item count.
        candidates = _dedup_marks(candidates)

        scored = [(m, _score(m, q, mode)) for m in candidates]
        scored = [(m, s) for (m, s) in scored if s >= threshold]
        if sort == "publication-desc":
            scored.sort(key=lambda x: x[0].publication_date_441 or date.min, reverse=True)
        elif sort == "applicant-asc":
            scored.sort(key=lambda x: (x[0].applicant_name is None, (x[0].applicant_name or "")))
        elif sort == "class-count":
            scored.sort(key=lambda x: -len(x[0].nice_classes or []))
        else:
            scored.sort(key=lambda x: (-x[1], str(x[0].id)))
        # total reflects candidates passing the threshold within the recall cap,
        # not the full filter-match count — the honest "how many similar marks"
        # number for a similarity search.
        total = len(scored)
        page = scored[offset : offset + limit]
        return SearchResultsOut(
            items=[ScoredMark(mark=TrademarkOut.model_validate(m), score=s) for m, s in page],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ---- All other modes: filter in SQL, score the over-fetch window -------
    # A text query is a similarity search: like phonetic, the honest "how many
    # match" count is post-threshold, not the raw WHERE count — otherwise the
    # header/footer claim more marks than the grid renders once the threshold
    # filters any out. So text scores ALL (capped) matches and reports the
    # survivors, deduping application/registration row pairs in Python
    # (_dedup_marks below — the #129 text/phonetic path).
    #
    # Filter-only / vienna / image have no `q` target (every score is 1.0 or a
    # coverage fraction), so they paginate the SQL window directly. There the
    # row pairs must be collapsed in SQL — via the DISTINCT-ON `representative_
    # marks` view — so BOTH the rows AND the count are deduped: one card per
    # mark, total = unique-mark count (was double-counting app+reg rows). The
    # view keeps the most-advanced row, mirroring _dedup_pref.
    is_text_query = mode == "text" and bool(q)
    base: Any = Trademark if is_text_query else representative_marks(where)
    stmt = select(base)
    # The deduped view already carries `where` inside its subquery; only the raw
    # text path applies it to the outer select.
    if is_text_query and where:
        stmt = stmt.where(and_(*where))

    if sort == "publication-desc":
        stmt = stmt.order_by(base.publication_date_441.desc().nulls_last(), base.id)
    elif sort == "applicant-asc":
        stmt = stmt.order_by(base.applicant_name.asc().nulls_last(), base.id)
    elif sort == "class-count":
        stmt = stmt.order_by(func.cardinality(base.nice_classes).desc().nulls_last(), base.id)
    else:
        # similarity sort without a phonetic target (filter-only / vienna /
        # image): scores are 1.0 or a coverage fraction; date order is stable.
        stmt = stmt.order_by(base.publication_date_441.desc().nulls_last(), base.id)

    fetch_limit = TEXT_RECALL_CAP if is_text_query else max(limit + offset, limit) * 2
    rows = list((await session.execute(stmt.limit(fetch_limit))).scalars().all())

    # Text/phonetic collapse the recall window in Python (cheap; the #129 path).
    if is_text_query:
        rows = _dedup_marks(rows)

    scored = [(m, _score(m, q, mode, has_vienna=has_vienna, vienna_query=norm_vienna)) for m in rows]
    scored = [(m, s) for (m, s) in scored if s >= threshold]
    if sort == "similarity":
        scored.sort(key=lambda x: (-x[1], str(x[0].id)))

    if is_text_query:
        total = len(scored)
    else:
        # COUNT(DISTINCT dedup_key) over the WHERE == the number of rows the
        # DISTINCT-ON view yields == unique marks; a single aggregate, so the
        # count scales without materialising the deduped set.
        cnt_stmt = select(func.count(func.distinct(dedup_key_expr()))).select_from(Trademark)
        if where:
            cnt_stmt = cnt_stmt.where(and_(*where))
        total = (await session.execute(cnt_stmt)).scalar_one()

    page = scored[offset : offset + limit]
    return SearchResultsOut(
        items=[ScoredMark(mark=TrademarkOut.model_validate(m), score=s) for m, s in page],
        total=total,
        limit=limit,
        offset=offset,
    )
