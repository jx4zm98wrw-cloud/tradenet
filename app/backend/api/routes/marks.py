"""Mark detail endpoints — single trademark plus its derived context.

`/api/marks/{id}` is the canonical detail URL the redesigned UI uses (the older
`/api/trademarks/{id}` stays for back-compat). Includes:
  - mark detail (with computed `oppositionEnds` + status flag)
  - procedural timeline (derived from filed/pub/reg dates)
  - applicant portfolio stats (real count from DB)
  - co-marks (same applicant)
  - similar marks landing this period
  - raw INID markers (extra_markers JSONB passthrough)
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tm_similarity import MarkFeatures, resolve_weights, score

from .._dedup import dedup_key_expr, representative_marks
from .._status import derive_status
from ..db import RecordType, Trademark, Watchlist, get_session
from ..db.models import DomesticRecord, MadridRecord
from ..schemas import DomesticEnrichmentOut, MadridEnrichmentOut, TrademarkOut
from .today import DEMO_TODAY, _opp_close_date

router = APIRouter(prefix="/api/v1/marks", tags=["marks"])


# ===== Mark detail with derived fields =====


class MarkDetailOut(BaseModel):
    mark: TrademarkOut
    oppositionEnds: date | None
    oppositionDaysLeft: int | None
    oppositionOpen: bool
    statusLabel: str  # IP VIETNAM-faithful label from derive_status: domestic status_code verbatim, else Granted/Lapsed/Pending
    statusTone: str  # "warn" | "ok" | "mute"
    # Goods-and-services text extracted from the (511) field. Kept off the
    # base TrademarkOut so it doesn't bloat list/search responses — average
    # 371 bytes / max 107 KB per row. Only the single-mark detail endpoint
    # surfaces it. Empty for Madrid rows where the gazette only printed a
    # bare class-number list.
    raw_511_text: str | None = None
    # WIPO Madrid enrichment, present only for Madrid marks that have a
    # madrid_records row (joined on lineage_key). None for domestic marks
    # and for Madrid marks not yet enriched — never fabricated.
    enrichment: MadridEnrichmentOut | None = None
    # IP VIETNAM domestic enrichment, present only for domestic marks that have a
    # domestic_records row (joined on application_number). None for Madrid
    # marks and for domestic marks not yet enriched — never fabricated.
    domestic: DomesticEnrichmentOut | None = None


@router.get("/{id}", response_model=MarkDetailOut)
async def get_mark(id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> MarkDetailOut:
    m = await session.get(Trademark, id)
    if m is None:
        raise HTTPException(404, "Mark not found")
    enrichment = None
    if m.lineage_key:
        rec = await session.get(MadridRecord, m.lineage_key)
        if rec is not None:
            enrichment = MadridEnrichmentOut.model_validate(rec)
    domestic = None
    if m.application_number:
        drec = await session.get(DomesticRecord, m.application_number)
        if drec is not None:
            domestic = DomesticEnrichmentOut.model_validate(drec)
    return _build_detail(m, enrichment, domestic)


def _build_detail(
    m: Trademark,
    enrichment: MadridEnrichmentOut | None = None,
    domestic: DomesticEnrichmentOut | None = None,
) -> MarkDetailOut:
    today = DEMO_TODAY
    opp_ends, opp_left, opp_open = None, None, False
    if m.record_type == RecordType.A and m.publication_date_441:
        opp_ends = _opp_close_date(m.publication_date_441)
        opp_left = (opp_ends - today).days
        opp_open = opp_left > 0
    domestic_status_code = domestic.status_code if domestic else None
    status_label, status_tone = derive_status(
        domestic_status_code, m.vn_grant_date, m.expiry_date_141, today=today
    )
    return MarkDetailOut(
        mark=TrademarkOut.model_validate(m),
        oppositionEnds=opp_ends,
        oppositionDaysLeft=opp_left,
        oppositionOpen=opp_open,
        statusLabel=status_label,
        statusTone=status_tone,
        raw_511_text=m.raw_511_text,
        enrichment=enrichment,
        domestic=domestic,
    )


# ===== Procedural timeline =====


class TimelineEvent(BaseModel):
    kind: str  # filed | formal | exam | published | opposition | registration | renewal
    date: date
    label: str
    body: str
    done: bool
    current: bool = False
    anchor: bool = False


@router.get("/{id}/timeline", response_model=list[TimelineEvent])
async def get_timeline(id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[TimelineEvent]:
    m = await session.get(Trademark, id)
    if m is None:
        raise HTTPException(404, "Mark not found")
    today = DEMO_TODAY
    events: list[TimelineEvent] = []

    # Pick the most reliable "filed" date we have. submission_date is real
    # (from the gazette's (220) field); the publication-derived fallback is a
    # synthetic estimate used only when (220) is absent.
    filed_observed = m.submission_date is not None
    filed = m.submission_date or (m.publication_date_441 and _months_before(m.publication_date_441, 8))
    if filed:
        events.append(
            TimelineEvent(
                kind="filed",
                date=filed,
                done=True,
                label="Application filed",
                body=(
                    f"Filed at IP VIETNAM · App № {m.application_number or '—'}"
                    if filed_observed
                    else "Filing date estimated from publication (8 months prior)."
                ),
            )
        )
        # Formal exam usually ~28 days later. We don't observe the formal-exam
        # event directly; the timeline shows it for context. The successful
        # outcome is implied only when later publication is recorded.
        formal = filed + timedelta(days=28)
        events.append(
            TimelineEvent(
                kind="formal",
                date=formal,
                done=formal <= today,
                label="Formal examination",
                body="Date estimated (~28 days after filing, Vietnam standard). Outcome not in gazette.",
            )
        )

    # Substantive exam — derive only if publication exists (i.e. application made it to publication).
    pub = m.publication_date_441 or m.publication_date_450
    if pub:
        exam = _months_before(pub, 3)
        events.append(
            TimelineEvent(
                kind="exam",
                date=exam,
                done=exam <= today,
                label="Substantive examination",
                body="Date estimated (~3 months before publication). Successful outcome implied by publication.",
            )
        )
        # The "Opposition window opens" copy is only meaningful for A-file
        # applications. B-file (registration / Madrid) publications don't
        # open an opposition window in the same sense.
        pub_body = (
            f"Published in gazette · App № {m.application_number or '—'}. Opposition window opens."
            if m.record_type == RecordType.A
            else "Published in gazette."
        )
        events.append(
            TimelineEvent(
                kind="published",
                date=pub,
                done=pub <= today,
                anchor=True,
                label="Published in gazette",
                body=pub_body,
            )
        )

    if m.record_type == RecordType.A and pub:
        closes = _opp_close_date(pub)
        is_current = closes >= today
        events.append(
            TimelineEvent(
                kind="opposition",
                date=closes,
                done=closes < today,
                current=is_current,
                label="Opposition window closes",
                body="5 months from publication (Vietnam Article 112).",
            )
        )
        events.append(
            TimelineEvent(
                kind="registration",
                date=pub + timedelta(days=300),
                done=False,
                label="Registration certificate (expected)",
                body="Estimated ~10 months after publication if no opposition is filed.",
            )
        )
    elif m.record_type != RecordType.A:
        if m.registration_date_151:
            events.append(
                TimelineEvent(
                    kind="registered",
                    date=m.registration_date_151,
                    done=True,
                    label="Registration certificate issued",
                    body=f"Cert № {m.certificate_number or '—'}. 10-year validity.",
                )
            )
        ex = m.expiry_date_141 or m.expiry_date_181
        if ex is not None:
            events.append(
                TimelineEvent(
                    kind="renewal",
                    date=ex,
                    done=ex < today,
                    label="First renewal due",
                    body="Renewable indefinitely in 10-year increments.",
                )
            )

    return events


def _months_before(d: date, months: int) -> date:
    m = d.month - months
    y = d.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, min(d.day, 28))


# ===== Co-marks (real, same applicant) =====


class CoMark(BaseModel):
    id: uuid.UUID
    name: str
    year: int | None
    classes: list[str]


@router.get("/{id}/co-marks", response_model=list[CoMark])
async def co_marks(
    id: uuid.UUID, limit: int = 6, session: AsyncSession = Depends(get_session)
) -> list[CoMark]:
    m = await session.get(Trademark, id)
    if m is None or not m.applicant_name:
        return []
    # One card per UNIQUE mark: exclude the anchor's ENTIRE dedup group (its
    # app+reg rows share an appno — filtering `id != m.id` alone would let the
    # anchor's other gazette row show as a co-mark of itself) and collapse the
    # rest via the deduped view so an app+reg mark yields a single card.
    anchor_key = m.application_number or m.lineage_key or str(m.id)
    rep = representative_marks([Trademark.applicant_name == m.applicant_name, dedup_key_expr() != anchor_key])
    rows = (
        (
            await session.execute(
                select(rep).order_by(desc(rep.publication_date_441), desc(rep.year), rep.id).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        CoMark(
            id=r.id,
            # Resolved display name — same chain as the rest of this file and the
            # frontend `markDisplay`: prefer the backfilled `mark_name`, fall back to
            # `mark_sample` (fresh-ingest rows with NULL mark_name), then the
            # figurative placeholder. NEVER the appno/cert number — that's an ID, not
            # a mark, and `mark_sample` is empty for ~172k domestic + all figurative
            # marks, so the old chain showed the appno for nearly every co-mark.
            name=r.mark_name or r.mark_sample or "(figurative mark)",
            year=r.year,
            classes=r.nice_classes or [],
        )
        for r in rows
    ]


# ===== Similar marks (real similarity engine) =====


class SimilarMark(BaseModel):
    mark: TrademarkOut
    score: float
    # Same provenance flag as compare.PairScore.visualConfidence so the
    # UI can warn when the visual signal is a typographic proxy.
    visualConfidence: str = "none"


# Candidate pool size before re-ranking with the real engine. The DB
# typically has hundreds of rows in a single class + ±60d window; we
# fetch up to this many, compute composite for each, then return the
# top `limit` the engine verdicts a conflict. Keeping this bounded means
# Compare pages stay fast even for popular classes.
_SIMILAR_CANDIDATE_POOL = 40

# Stage-1 recall cap for wordmark anchors: max candidates pulled by trigram /
# dmetaphone similarity before the composite rerank. Candidates are matched on
# their `mark_sample` (the trigram/dmetaphone index lives there); the anchor is
# the subject's resolved name (`mark_name` or `mark_sample`), which may differ —
# the asymmetry is intentional, there is no trigram index on `mark_name`. Ordered
# by trigram similarity so the genuinely-similar marks come first; bounded so the
# per-candidate pHash work stays fast.
_SIMILAR_RECALL_CAP = 50


@router.get("/{id}/similar", response_model=list[SimilarMark])
async def similar_marks(
    id: uuid.UUID,
    limit: int = 4,
    watchlist_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SimilarMark]:
    """Return marks similar to the given one, ranked by composite score.

    Two-stage retrieval (mirrors the search route):
      1. RECALL — for marks with a wordmark, pull candidates whose `mark_sample`
         is trigram- or Double-Metaphone-similar to this mark's resolved name
         (`mark_name` or `mark_sample`) (index-backed), scoped to the ±60-day
         "this period" window. This replaces the old "40 most-recent rows
         sharing any Nice class" screen, which — in a crowded class like 35
         (10k+ marks) — surfaced unrelated class-mates rather than genuinely
         confusable marks. Marks with no resolved name and no wordmark fall back
         to the class + period screen, since there is no text to recall by and
         no pHash index.
      2. RERANK — composite score (phonetic + visual + class + vienna) per
         candidate, drop marks the engine verdicts Low risk, sort descending,
         return top `limit`. An empty result is correct here: "no confusable
         marks landed this period".
    """
    m = await session.get(Trademark, id)
    if m is None:
        return []

    pub_range = []
    if m.publication_date_441:
        lo = m.publication_date_441 - timedelta(days=60)
        hi = m.publication_date_441 + timedelta(days=60)
        pub_range = [Trademark.publication_date_441.between(lo, hi)]

    anchor_word = (m.mark_name or m.mark_sample or "").strip()
    if anchor_word:
        # Stage 1: similarity recall on the wordmark — trigram `%` OR same
        # Double-Metaphone code, ordered by trigram similarity (index-backed).
        # Recall on BOTH mark_sample AND the resolved mark_name: ~172k domestic
        # marks have NULL mark_sample and carry their wordmark only in mark_name,
        # so a mark_sample-only recall (with a `mark_sample IS NOT NULL` gate)
        # silently ignored ~70% of the corpus — a phonetically identical prior
        # mark would never surface. NULL columns can't match the `%` / dmetaphone
        # arms, so no explicit not-null gate is needed. All four arms are
        # index-backed (lower(mark_sample)/lower(mark_name) GIN-trgm + dmetaphone
        # btrees).
        ql = anchor_word.lower()
        dmeta_q = func.dmetaphone(ql)
        recall = select(Trademark).where(
            Trademark.id != m.id,
            or_(
                func.lower(Trademark.mark_sample).op("%")(ql),
                func.lower(Trademark.mark_name).op("%")(ql),
                func.dmetaphone(func.lower(Trademark.mark_sample)) == dmeta_q,
                func.dmetaphone(func.lower(Trademark.mark_name)) == dmeta_q,
            ),
        )
        if pub_range:
            recall = recall.where(and_(*pub_range))
        recall = recall.order_by(
            func.greatest(
                func.similarity(func.lower(Trademark.mark_sample), ql),
                func.similarity(func.lower(Trademark.mark_name), ql),
            ).desc(),
            Trademark.id,
        ).limit(_SIMILAR_RECALL_CAP)
        await session.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.15"))
        candidates = list((await session.execute(recall)).scalars().all())
    else:
        # Figurative-only anchor (no wordmark): class + period screen is the best
        # cheap option absent a pHash index. Same behaviour as before.
        fq = select(Trademark).where(Trademark.id != m.id, Trademark.mark_sample.is_not(None))
        if m.nice_classes:
            fq = fq.where(Trademark.nice_classes.op("&&")(m.nice_classes))
        if pub_range:
            fq = fq.where(and_(*pub_range))
        fq = fq.order_by(desc(Trademark.publication_date_441), Trademark.id).limit(_SIMILAR_CANDIDATE_POOL)
        candidates = list((await session.execute(fq)).scalars().all())
    m_text = (m.mark_name or m.mark_sample or "").strip()

    # Per-matter weights: when a watchlist context is supplied, rank with that
    # matter's weight profile (e.g. pharma up-weights phonetic); else defaults.
    weights = None
    if watchlist_id is not None:
        wl = await session.get(Watchlist, watchlist_id)
        if wl is not None:
            weights = resolve_weights(wl.weights)

    m_feat = MarkFeatures(
        mark_text=m_text,
        logo_phash=m.logo_phash,
        nice_classes=m.nice_classes or [],
        vienna_codes=m.vienna_codes or [],
        logo_kind=m.logo_kind,
        mark_embedding=m.mark_embedding,
    )

    scored: list[tuple[Trademark, float, str]] = []
    for r in candidates:
        r_text = (r.mark_name or r.mark_sample or "").strip()
        result = score(
            m_feat,
            MarkFeatures(
                mark_text=r_text,
                logo_phash=r.logo_phash,
                nice_classes=r.nice_classes or [],
                vienna_codes=r.vienna_codes or [],
                logo_kind=r.logo_kind,
                mark_embedding=r.mark_embedding,
            ),
            weights=weights,
        )
        # Surface only marks the engine itself verdicts a Possible/Likely conflict
        # (its conjunction rule for Possible conflict: mark_strength >= 0.50 AND
        # class >= 0.20 AND composite >= 0.50; Likely conflict clears it too).
        # "Low risk" means class overlap alone — not a similar mark — so it is
        # excluded. Same rule Compare uses; single source of truth.
        if result.verdict != "Low risk":
            scored.append((r, result.composite, result.visual_confidence))

    scored.sort(key=lambda x: -x[1])

    return [
        SimilarMark(
            mark=TrademarkOut.model_validate(r),
            score=round(score, 3),
            visualConfidence=conf,
        )
        for r, score, conf in scored[:limit]
    ]


# ===== Applicant portfolio stats (mostly real) =====


class ApplicantStats(BaseModel):
    name: str
    activeMarks: int
    pending: int
    oppositionsFiled: int
    totalMarks: int


@router.get("/{id}/applicant-stats", response_model=ApplicantStats)
async def applicant_stats(id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> ApplicantStats:
    m = await session.get(Trademark, id)
    if m is None or not m.applicant_name:
        raise HTTPException(404, "Mark not found")
    # Count UNIQUE marks, not raw gazette rows: a domestic mark appears as BOTH
    # an application (A) row and a registration (B) row sharing an appno, so raw
    # counts double-count every granted mark — once as `active` (its reg row)
    # AND once as `pending` (its app row). The deduped view yields one
    # MOST-ADVANCED row per mark (certificate > granted > id), so classifying
    # that single survivor by record_type counts each mark exactly once: an
    # app+reg mark's survivor is its registration row → active, never pending.
    rep = representative_marks([Trademark.applicant_name == m.applicant_name])
    base = select(func.count()).select_from(rep)
    total = (await session.execute(base)).scalar_one()
    pending = (await session.execute(base.where(rep.record_type == RecordType.A))).scalar_one()
    active = (await session.execute(base.where(rep.record_type != RecordType.A))).scalar_one()
    # Oppositions filed is fake (no opposition data exists in our DB yet).
    return ApplicantStats(
        name=m.applicant_name,
        activeMarks=active,
        pending=pending,
        oppositionsFiled=0,
        totalMarks=total,
    )


# ===== Raw INID markers passthrough =====


class InidMarker(BaseModel):
    code: str
    label: str
    value: str | None


INID_LABELS = {
    "111": "Trademark registration certificate number",
    "116": "International registration number under Madrid Agreement",
    "141": "Expiry date of the trademark",
    "151": "Date of issuance/registration",
    "156": "Date of renewal for international registration",
    "171": "Period of validity",
    "176": "Period of validity for renewed international registration",
    "181": "Expiry date of trademark certificate",
    "210": "Application number",
    "220": "Application submission date",
    "300": "Priority application details",
    "441": "Publication date of application",
    "450": "Publication date of certificate",
    "511": "International classification (Nice)",
    "531": "Classification of figurative elements (Vienna)",
    "540": "Trademark sample",
    "551": "Trademark status",
    "591": "Protected colors",
    "641": "Number of related application",
    "731": "Applicant details",
    "732": "Trademark owner details",
    "740": "Industrial property representative",
    "822": "Country of origin details",
    "831": "Territorial expansion details",
}


@router.get("/{id}/inid-fields", response_model=list[InidMarker])
async def inid_fields(id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[InidMarker]:
    m = await session.get(Trademark, id)
    if m is None:
        raise HTTPException(404, "Mark not found")
    # Map the typed columns back to INID codes.
    fields = {
        "111": m.certificate_number,
        "116": m.madrid_number,
        "141": _iso(m.expiry_date_141),
        "151": _iso(m.registration_date_151),
        "156": _iso(m.renewal_date_156),
        "171": m.validity_171,
        "176": m.validity_176,
        "181": _iso(m.expiry_date_181),
        "210": m.application_number,
        "220": _iso(m.submission_date),
        "300": m.priority_300,
        "441": _iso(m.publication_date_441),
        "450": _iso(m.publication_date_450),
        "511": m.raw_511_text,
        "531": m.raw_531_text,
        "540": m.mark_sample,
        "551": m.mark_status,
        "591": m.protected_colors,
        "641": m.related_app_641,
        "731": m.applicant_raw_731,
        "732": m.owner_raw_732,
        "740": m.ip_agency_raw_740,
        "822": m.origin_822,
        "831": m.territory_831,
    }
    return [
        InidMarker(code=code, label=INID_LABELS.get(code, ""), value=v) for code, v in fields.items() if v
    ]


def _iso(d):
    return d.isoformat() if d else None
