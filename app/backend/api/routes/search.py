"""Scored search — extends /api/trademarks with a similarity score per result.

Per-mode scoring:
  - text:     substring strength against wordmark / applicant (mock — text
              mode is a literal-match search, not a similarity search).
  - phonetic: REAL Jaro-Winkler + Metaphone via api.similarity. NEUROFAX
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
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import similarity as sim
from ..db import RecordType, Trademark, get_session
from ..schemas import TrademarkOut
from ._filters import build_trademark_where, normalize_vienna_code, vienna_code_match

router = APIRouter(prefix="/api/v1/search", tags=["search"])

SearchMode = Literal["text", "phonetic", "image", "vienna"]


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
        # with JW on Metaphone codes. Compare against the wordmark first,
        # fall back to applicant_name only when there's literally no
        # wordmark (most A-files lack mark_sample but have applicants).
        # No jitter — the real signal carries its own ordering.
        target = mark.mark_sample or mark.applicant_name
        return round(sim.phonetic_similarity(q, target), 3)

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
        # sim.visual_similarity() per row against logo_path.
        return round(min(0.999, 0.78 + _jitter(str(mark.id))), 2)

    # mode == "text" — substring-strength heuristic. Text mode is a literal
    # search, not a similarity search; the score expresses how cleanly the
    # query matched the wordmark or applicant string, not how phonetically
    # close they are.
    base = 0.6
    if q:
        ql = q.lower()
        wordmark = (mark.mark_sample or "").lower()
        bag = wordmark + " " + (mark.applicant_name or "").lower()
        if wordmark == ql:
            base = 0.98
        elif ql in wordmark:
            base = 0.92
        elif ql in bag:
            base = 0.78
        elif wordmark[:3] == ql[:3]:
            base = 0.76
    s = base + _jitter(str(mark.id))
    return round(max(0.0, min(0.999, s)), 2)


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
    applicant_type: str | None = Query(None),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    gazette_id: uuid.UUID | None = None,
    ip_agency: str | None = Query(None),
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
    where = build_trademark_where(
        q=q,
        country=country,
        nice_class=nice_class if nice_class_mode == "all" else None,
        vienna_codes=norm_vienna if vienna_codes_mode == "all" else None,
        record_type=record_type,
        applicant_type=applicant_type,
        year=year,
        month=month,
        gazette_id=gazette_id,
        ip_agency=ip_agency,
    )
    if nice_class and nice_class_mode == "any":
        where.append(Trademark.nice_classes.op("&&")(nice_class))
    if norm_vienna and vienna_codes_mode == "any":
        # ANY semantics with parent-code expansion: a request for `5.7`
        # should match any `5.7.x`. OR together each code's match clause
        # (each is exact-or-prefix per vienna_code_match).
        where.append(or_(*[vienna_code_match(c) for c in norm_vienna]))

    stmt = select(Trademark)
    cnt_stmt = select(func.count()).select_from(Trademark)
    if where:
        stmt = stmt.where(and_(*where))
        cnt_stmt = cnt_stmt.where(and_(*where))

    if sort == "publication-desc":
        stmt = stmt.order_by(Trademark.publication_date_441.desc().nulls_last(), Trademark.id)
    elif sort == "applicant-asc":
        stmt = stmt.order_by(Trademark.applicant_name.asc().nulls_last(), Trademark.id)
    elif sort == "class-count":
        stmt = stmt.order_by(func.cardinality(Trademark.nice_classes).desc().nulls_last(), Trademark.id)
    else:
        # similarity: fetch then sort in Python (mock scores).
        stmt = stmt.order_by(Trademark.publication_date_441.desc().nulls_last(), Trademark.id)

    # Over-fetch so we can post-filter by threshold without ruining pagination.
    fetch_limit = max(limit + offset, limit) * 2
    rows = list((await session.execute(stmt.limit(fetch_limit))).scalars().all())
    total = (await session.execute(cnt_stmt)).scalar_one()

    has_vienna = bool(norm_vienna)
    scored = [(m, _score(m, q, mode, has_vienna=has_vienna, vienna_query=norm_vienna)) for m in rows]
    scored = [(m, s) for (m, s) in scored if s >= threshold]
    if sort == "similarity":
        scored.sort(key=lambda x: (-x[1], str(x[0].id)))

    page = scored[offset : offset + limit]
    return SearchResultsOut(
        items=[ScoredMark(mark=TrademarkOut.model_validate(m), score=s) for m, s in page],
        total=total,
        limit=limit,
        offset=offset,
    )
