"""Today / dashboard endpoints — digest + findings + opposition windows + watchlists.

Most of these are real (math, counts), but **findings** and **watchlists** are
mocked here until PR #5 ships the similarity engine + watchlist persistence.
The mock returns real marks (so the UI exercises real data flow) tagged with
fabricated similarity scores and watchlist attribution.
"""
from __future__ import annotations
import hashlib
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Gazette, GazetteStatus, RecordType, Trademark, Watchlist, get_session
from ..schemas import TrademarkOut


router = APIRouter(prefix="/api", tags=["today"])


# Vietnam Article 112: 5 months from publication date.
OPPOSITION_WINDOW_DAYS = 150


def _opp_close_date(pub: date) -> date:
    return pub + timedelta(days=OPPOSITION_WINDOW_DAYS)


def _days_left(pub: date, today: date) -> int:
    return (pub + timedelta(days=OPPOSITION_WINDOW_DAYS) - today).days


# Pretend "today" for the demo so the eyebrow + windows match the seeded gazette
# data (which is dated Q1-Q2 2026). When real-time data lands, swap to `date.today()`.
DEMO_TODAY = date(2026, 5, 19)


# ============================================================================
# Digest
# ============================================================================

class DigestOut(BaseModel):
    today: date
    totalNew: int
    activeWatchlists: int
    watchlistsWithFindings: int
    closingIn7Days: int
    closingIn14Days: int
    lastSyncAt: datetime


@router.get("/today/digest", response_model=DigestOut)
async def today_digest(session: AsyncSession = Depends(get_session)) -> DigestOut:
    today = DEMO_TODAY
    findings_total, watch_with_findings, n_watch = await _findings_summary(session)
    # Real opposition counts
    threshold = today - timedelta(days=OPPOSITION_WINDOW_DAYS)
    base = (
        select(func.count())
        .select_from(Trademark)
        .where(Trademark.record_type == RecordType.A)
        .where(Trademark.publication_date_441.is_not(None))
        .where(Trademark.publication_date_441 > threshold)
    )
    in14 = base.where(Trademark.publication_date_441 <= threshold + timedelta(days=14))
    in7 = base.where(Trademark.publication_date_441 <= threshold + timedelta(days=7))
    in14_count = (await session.execute(in14)).scalar_one()
    in7_count = (await session.execute(in7)).scalar_one()
    # Last gazette uploaded
    last = await session.execute(
        select(Gazette.uploaded_at).order_by(desc(Gazette.uploaded_at)).limit(1)
    )
    last_sync = last.scalar_one_or_none() or datetime.utcnow()
    return DigestOut(
        today=today,
        totalNew=findings_total,
        activeWatchlists=n_watch,
        watchlistsWithFindings=watch_with_findings,
        closingIn7Days=in7_count,
        closingIn14Days=in14_count,
        lastSyncAt=last_sync,
    )


# ============================================================================
# Findings (mocked, uses real marks)
# ============================================================================

class FindingOut(BaseModel):
    mark: TrademarkOut
    score: float
    watchId: str
    watchName: str
    reason: str


REASONS = [
    "Phonetic + class overlap", "Levenshtein 2 / class match",
    "Visual + class overlap", "Suffix match", "Identical root",
]


def _fake_score(seed: str, lo: float = 0.65, hi: float = 0.95) -> float:
    """Stable pseudo-random in [lo, hi] keyed on the mark id.
    Real similarity engine plugs in here later. """
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return round(lo + (hi - lo) * (h % 1000) / 1000.0, 2)


def _reason_for(mark_id: str) -> str:
    return REASONS[int(hashlib.md5(mark_id.encode()).hexdigest()[2:4], 16) % len(REASONS)]


async def _findings_for_watchlist(
    session: AsyncSession, w: Watchlist, per_list: int = 2,
) -> List[tuple[Trademark, Watchlist]]:
    """Re-execute a saved watchlist query and pull recent matches."""
    from .watchlists import _query_where, WatchQuery
    where = _query_where(WatchQuery(**w.query))
    where.append(Trademark.mark_sample.is_not(None))
    where.append(func.length(Trademark.mark_sample) <= 16)
    where.append(func.length(Trademark.mark_sample) >= 3)
    stmt = (
        select(Trademark)
        .where(*where)
        .order_by(desc(Trademark.publication_date_441), Trademark.id)
        .limit(per_list)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [(m, w) for m in rows]


async def _findings_summary(session: AsyncSession) -> tuple[int, int, int]:
    """Returns (total_findings, watchlists_with_findings, total_watchlists)."""
    watchlists = list((await session.execute(select(Watchlist))).scalars().all())
    found = 0
    with_findings = 0
    for w in watchlists:
        rows = await _findings_for_watchlist(session, w, per_list=3)
        if rows:
            with_findings += 1
            found += len(rows)
    return found, with_findings, len(watchlists)


@router.get("/findings", response_model=List[FindingOut])
async def findings(session: AsyncSession = Depends(get_session)) -> List[FindingOut]:
    """Findings = marks that match any watchlist's saved query, ranked by score."""
    watchlists = list((await session.execute(select(Watchlist))).scalars().all())
    out: List[FindingOut] = []
    seen_marks: set = set()
    for w in watchlists:
        rows = await _findings_for_watchlist(session, w, per_list=3)
        for m, wl in rows:
            if m.id in seen_marks:
                continue
            seen_marks.add(m.id)
            out.append(FindingOut(
                mark=TrademarkOut.model_validate(m),
                score=_fake_score(str(m.id)),
                watchId=str(wl.id),
                watchName=wl.name,
                reason=_reason_for(str(m.id)),
            ))
    out.sort(key=lambda f: -f.score)
    return out[:8]


# ============================================================================
# Opposition windows (real math)
# ============================================================================

class OppositionOut(BaseModel):
    markId: str
    markName: Optional[str]
    applicant: Optional[str]
    classes: List[str]
    closesAt: date
    daysLeft: int
    status: str  # open | closed
    watchId: Optional[str]
    watchName: Optional[str]
    publishedAt: Optional[date]


@router.get("/opposition-windows", response_model=List[OppositionOut])
async def opposition_windows(
    status: str = "open",
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> List[OppositionOut]:
    today = DEMO_TODAY
    threshold = today - timedelta(days=OPPOSITION_WINDOW_DAYS)
    q = (
        select(Trademark)
        .where(Trademark.record_type == RecordType.A)
        .where(Trademark.publication_date_441.is_not(None))
    )
    if status == "open":
        q = q.where(Trademark.publication_date_441 > threshold)
    else:
        q = q.where(Trademark.publication_date_441 <= threshold)
    q = q.order_by(Trademark.publication_date_441).limit(limit)
    marks = list((await session.execute(q)).scalars().all())

    out: List[OppositionOut] = []
    for m in marks:
        pub = m.publication_date_441
        if pub is None:
            continue
        closes = _opp_close_date(pub)
        dl = (closes - today).days
        out.append(OppositionOut(
            markId=str(m.id),
            markName=m.mark_sample or m.applicant_name,
            applicant=m.applicant_name,
            classes=m.nice_classes or [],
            closesAt=closes,
            daysLeft=dl,
            status="open" if dl > 0 else "closed",
            watchId=None,
            watchName=None,
            publishedAt=pub,
        ))
    out.sort(key=lambda o: o.daysLeft)
    return out


# ============================================================================
# Pipeline stats (real where available)
# ============================================================================

class PipelineStatsOut(BaseModel):
    totalTrademarks: int
    thisQuarter: int
    pagesOcred: int
    reviewQueue: int
    gazettesProcessed: int
    gazettesTotal: int
    latestGazetteName: Optional[str]
    latestGazetteRows: Optional[int]
    latestGazetteAt: Optional[datetime]


@router.get("/stats/pipeline", response_model=PipelineStatsOut)
async def pipeline_stats(session: AsyncSession = Depends(get_session)) -> PipelineStatsOut:
    total = (await session.execute(select(func.count()).select_from(Trademark))).scalar_one()
    q_start = date(DEMO_TODAY.year, ((DEMO_TODAY.month - 1) // 3) * 3 + 1, 1)
    this_q = (await session.execute(
        select(func.count()).select_from(Trademark)
        .where(Trademark.year == DEMO_TODAY.year)
        .where(Trademark.month >= q_start.month)
    )).scalar_one()
    gz_total = (await session.execute(select(func.count()).select_from(Gazette))).scalar_one()
    gz_done = (await session.execute(
        select(func.count()).select_from(Gazette).where(Gazette.status == GazetteStatus.completed)
    )).scalar_one()
    latest = (await session.execute(
        select(Gazette).order_by(desc(Gazette.uploaded_at)).limit(1)
    )).scalar_one_or_none()
    return PipelineStatsOut(
        totalTrademarks=total,
        thisQuarter=this_q,
        pagesOcred=11420,        # mocked — we don't OCR yet
        reviewQueue=14,          # mocked
        gazettesProcessed=gz_done,
        gazettesTotal=gz_total,
        latestGazetteName=latest.filename if latest else None,
        latestGazetteRows=latest.row_count if latest else None,
        latestGazetteAt=latest.uploaded_at if latest else None,
    )
