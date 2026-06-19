"""Admin check — role-aware, used by the frontend to gate /admin/* pages.

Returns 200 with `isAdmin` reflecting the logged-in user's actual role.
Non-admins get `isAdmin: false` (so the page can redirect them to "/")
rather than a 403 — the response is a routing signal, not an auth gate.
The real auth gate is on the underlying admin endpoints themselves
(`require_admin` on `/gazettes` listing, etc.) — defense in depth.

Returns 401 if no one is logged in (handled by `require_user`).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, require_admin, require_user
from ..db import Trademark, get_session
from ..db.models import DomesticRecord, MadridRecord, UserRole

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Madrid mark categories — must match madrid_enrich.backfill.iter_madrid_irns so
# the panel's denominator equals the sweep's work-list.
_MADRID_CATEGORIES = ("madrid_registration", "madrid_renewal")

# Domestic mark categories — must match domestic_sweep's work-list.
_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")


class AdminCheck(BaseModel):
    isAdmin: bool
    role: UserRole
    reason: str


@router.get("/check", response_model=AdminCheck)
async def check(user: User = Depends(require_user)) -> AdminCheck:
    if user.is_admin:
        return AdminCheck(isAdmin=True, role=user.role, reason="admin role")
    return AdminCheck(
        isAdmin=False,
        role=user.role,
        reason=f"role={user.role.value}; admin required",
    )


class MadridEnrichmentStats(BaseModel):
    unique_irns: int
    validated: int
    remaining: int
    pct_complete: float  # 0.0–1.0
    vn_granted: int
    by_category: dict[str, int]


@router.get("/madrid-enrichment", response_model=MadridEnrichmentStats)
async def madrid_enrichment(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MadridEnrichmentStats:
    """Live Madrid-enrichment coverage, derived from the DB at request time.

    unique_irns = distinct Madrid lineage_keys (= the sweep's work-list);
    validated = madrid_records rows (the durable outcome, not the cache);
    remaining = unique - validated.
    """
    # unique_irns is the TRUE distinct lineage_key count across BOTH Madrid
    # categories — identical to madrid_enrich.backfill.iter_madrid_irns(), so the
    # panel's denominator equals the sweep's work-list (the whole point of the
    # panel). Do NOT define it as sum(by_category): a handful of keys carry both
    # a registration and a later renewal row, and those must be counted once.
    unique_irns = (
        await session.execute(
            select(func.count(distinct(Trademark.lineage_key)))
            .where(Trademark.mark_category.in_(_MADRID_CATEGORIES))
            .where(Trademark.lineage_key.is_not(None))
        )
    ).scalar_one()
    # Per-category distinct lineage_keys, for the registration/renewal breakdown.
    # Cross-category overlap means sum(by_category) >= unique_irns (the overlap is
    # deduped in unique_irns but counted in each bucket it appears in).
    cat_rows = (
        await session.execute(
            select(Trademark.mark_category, func.count(distinct(Trademark.lineage_key)))
            .where(Trademark.mark_category.in_(_MADRID_CATEGORIES))
            .where(Trademark.lineage_key.is_not(None))
            .group_by(Trademark.mark_category)
        )
    ).all()
    by_category = {c: n for c, n in cat_rows}
    for c in _MADRID_CATEGORIES:
        by_category.setdefault(c, 0)
    validated = (await session.execute(select(func.count()).select_from(MadridRecord))).scalar_one()
    vn_granted = (
        await session.execute(
            select(func.count()).select_from(MadridRecord).where(MadridRecord.vn_status == "granted")
        )
    ).scalar_one()
    return MadridEnrichmentStats(
        unique_irns=unique_irns,
        validated=validated,
        remaining=max(unique_irns - validated, 0),
        pct_complete=(validated / unique_irns) if unique_irns else 0.0,
        vn_granted=vn_granted,
        by_category=by_category,
    )


class DomesticEnrichmentStats(BaseModel):
    unique_appnos: int
    validated: int
    remaining: int
    pct_complete: float  # 0.0–1.0
    granted: int
    by_category: dict[str, int]


@router.get("/domestic-enrichment", response_model=DomesticEnrichmentStats)
async def domestic_enrichment(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticEnrichmentStats:
    """Live domestic-enrichment coverage, derived from the DB at request time.

    unique_appnos = distinct domestic application_numbers (= the sweep work-list);
    validated = domestic_records rows; remaining = unique - validated.
    """
    unique_appnos = (
        await session.execute(
            select(func.count(distinct(Trademark.application_number)))
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.application_number.is_not(None))
        )
    ).scalar_one()
    cat_rows = (
        await session.execute(
            select(Trademark.mark_category, func.count(distinct(Trademark.application_number)))
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.application_number.is_not(None))
            .group_by(Trademark.mark_category)
        )
    ).all()
    by_category = {c: n for c, n in cat_rows}
    for c in _DOMESTIC_CATEGORIES:
        by_category.setdefault(c, 0)
    validated = (await session.execute(select(func.count()).select_from(DomesticRecord))).scalar_one()
    granted = (
        await session.execute(
            select(func.count()).select_from(DomesticRecord).where(DomesticRecord.grant_date.is_not(None))
        )
    ).scalar_one()
    return DomesticEnrichmentStats(
        unique_appnos=unique_appnos,
        validated=validated,
        remaining=max(unique_appnos - validated, 0),
        pct_complete=(validated / unique_appnos) if unique_appnos else 0.0,
        granted=granted,
        by_category=by_category,
    )
