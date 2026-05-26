"""Mark detail endpoints — single trademark plus its derived context.

`/api/marks/{id}` is the canonical detail URL the redesigned UI uses (the older
`/api/trademarks/{id}` stays for back-compat). Includes:
  - mark detail (with computed `oppositionEnds` + status flag)
  - procedural timeline (derived from filed/pub/reg dates)
  - applicant portfolio stats (real count from DB)
  - co-marks (same applicant)
  - similar marks landing this period (mocked similarity until PR #5)
  - raw INID markers (extra_markers JSONB passthrough)
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import RecordType, Trademark, get_session
from ..schemas import TrademarkOut
from .today import DEMO_TODAY, _opp_close_date

router = APIRouter(prefix="/api/v1/marks", tags=["marks"])


# ===== Mark detail with derived fields =====


class MarkDetailOut(BaseModel):
    mark: TrademarkOut
    oppositionEnds: date | None
    oppositionDaysLeft: int | None
    oppositionOpen: bool
    statusLabel: str  # "Examination pending" | "Active registration" | "Lapsed" | "Pending publication"
    statusTone: str  # "warn" | "ok" | "mute"
    # Goods-and-services text extracted from the (511) field. Kept off the
    # base TrademarkOut so it doesn't bloat list/search responses — average
    # 371 bytes / max 107 KB per row. Only the single-mark detail endpoint
    # surfaces it. Empty for Madrid rows where the gazette only printed a
    # bare class-number list.
    raw_511_text: str | None = None


@router.get("/{id}", response_model=MarkDetailOut)
async def get_mark(id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> MarkDetailOut:
    m = await session.get(Trademark, id)
    if m is None:
        raise HTTPException(404, "Mark not found")
    return _build_detail(m)


def _build_detail(m: Trademark) -> MarkDetailOut:
    today = DEMO_TODAY
    opp_ends, opp_left, opp_open = None, None, False
    if m.record_type == RecordType.A and m.publication_date_441:
        opp_ends = _opp_close_date(m.publication_date_441)
        opp_left = (opp_ends - today).days
        opp_open = opp_left > 0
    if m.record_type == RecordType.A:
        status_label, status_tone = ("Examination pending", "warn")
    elif m.expiry_date_141 and m.expiry_date_141 < today:
        status_label, status_tone = ("Lapsed", "mute")
    else:
        status_label, status_tone = ("Active registration", "ok")
    return MarkDetailOut(
        mark=TrademarkOut.model_validate(m),
        oppositionEnds=opp_ends,
        oppositionDaysLeft=opp_left,
        oppositionOpen=opp_open,
        statusLabel=status_label,
        statusTone=status_tone,
        raw_511_text=m.raw_511_text,
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
                    f"Filed at NOIP · App № {m.application_number or '—'}"
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
    rows = (
        (
            await session.execute(
                select(Trademark)
                .where(Trademark.applicant_name == m.applicant_name)
                .where(Trademark.id != m.id)
                .order_by(desc(Trademark.publication_date_441), desc(Trademark.year), Trademark.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        CoMark(
            id=r.id,
            name=r.mark_sample or r.application_number or r.certificate_number or "—",
            year=r.year,
            classes=r.nice_classes or [],
        )
        for r in rows
    ]


# ===== Similar marks (mocked similarity) =====


class SimilarMark(BaseModel):
    mark: TrademarkOut
    score: float


@router.get("/{id}/similar", response_model=list[SimilarMark])
async def similar_marks(
    id: uuid.UUID, limit: int = 4, session: AsyncSession = Depends(get_session)
) -> list[SimilarMark]:
    m = await session.get(Trademark, id)
    if m is None:
        return []
    # "Similar" = shares at least one Nice class + published within ±60 days. Mock score
    # is a per-id jitter; the real similarity engine swaps in here later.
    pub_range = []
    if m.publication_date_441:
        lo = m.publication_date_441 - timedelta(days=60)
        hi = m.publication_date_441 + timedelta(days=60)
        pub_range = [Trademark.publication_date_441.between(lo, hi)]

    q = select(Trademark).where(Trademark.id != m.id).where(Trademark.mark_sample.is_not(None))
    if m.nice_classes:
        q = q.where(Trademark.nice_classes.op("&&")(m.nice_classes))
    if pub_range:
        q = q.where(and_(*pub_range))
    q = q.order_by(desc(Trademark.publication_date_441), Trademark.id).limit(limit)

    rows = list((await session.execute(q)).scalars().all())
    out = []
    for r in rows:
        h = int(hashlib.md5(f"{m.id}{r.id}".encode()).hexdigest()[:8], 16)
        score = round(0.55 + (h % 350) / 1000.0, 2)
        out.append(SimilarMark(mark=TrademarkOut.model_validate(r), score=score))
    out.sort(key=lambda x: -x.score)
    return out


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
    base = select(func.count()).select_from(Trademark).where(Trademark.applicant_name == m.applicant_name)
    total = (await session.execute(base)).scalar_one()
    pending = (await session.execute(base.where(Trademark.record_type == RecordType.A))).scalar_one()
    active = (await session.execute(base.where(Trademark.record_type != RecordType.A))).scalar_one()
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
