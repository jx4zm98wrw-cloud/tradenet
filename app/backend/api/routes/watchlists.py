"""Watchlist CRUD + findings.

A watchlist persists a saved SearchQuery and re-runs it against every new
gazette. `total_count` and `new_count` are cached aggregates updated on
create/update; in production a worker hook would also refresh them after each
ingest. For now they're refreshed on demand via re-run (PUT) or read fresh
on every GET findings call.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, optional_user, require_user
from ..db import RecordType, Trademark, Watchlist, get_session
from ..schemas import TrademarkOut
from ._filters import build_trademark_where
from .today import DEMO_TODAY

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


# ===== Saved query payload =====


class WatchQuery(BaseModel):
    """Mirrors the search filters. Stored as JSONB."""

    q: str | None = None
    mode: Literal["text", "phonetic", "image", "vienna"] = "text"
    threshold: float = 0.65
    country: str | None = None
    nice_class: list[str] | None = None
    nice_class_mode: Literal["any", "all"] = "any"
    record_type: str | None = None
    applicant_type: str | None = None
    ip_agency: str | None = None


class WatchlistOut(BaseModel):
    id: uuid.UUID
    name: str
    client: str | None
    matter: str | None
    query: WatchQuery
    queryDesc: str | None
    totalCount: int
    newCount: int
    createdAt: datetime
    updatedAt: datetime
    lastRunAt: datetime | None


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    client: str | None = None
    matter: str | None = None
    query: WatchQuery
    queryDesc: str | None = None


class WatchlistUpdate(BaseModel):
    name: str | None = None
    client: str | None = None
    matter: str | None = None
    query: WatchQuery | None = None
    queryDesc: str | None = None


# ===== Endpoints =====


@router.get("", response_model=list[WatchlistOut])
async def list_watchlists(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(optional_user),
) -> list[WatchlistOut]:
    # Scope to the caller's watchlists when authenticated. Pre-auth callers see
    # all (legacy behaviour); once auth is real, drop the `if` branch.
    stmt = select(Watchlist).order_by(desc(Watchlist.new_count), desc(Watchlist.updated_at))
    if user is not None:
        stmt = stmt.where((Watchlist.owner_id == user.id) | (Watchlist.owner_id.is_(None)))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_out(w) for w in rows]


@router.post("", response_model=WatchlistOut, status_code=201)
async def create_watchlist(
    body: WatchlistCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
) -> WatchlistOut:
    w = Watchlist(
        name=body.name,
        client=body.client,
        matter=body.matter,
        query=body.query.model_dump(),
        query_desc=body.queryDesc or _summarize_query(body.query),
        owner_id=user.id,
    )
    session.add(w)
    await session.flush()
    total, new = await _run_query(session, body.query)
    w.total_count = total
    w.new_count = new
    w.last_run_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(w)
    return _to_out(w)


@router.put("/{id}", response_model=WatchlistOut)
async def update_watchlist(
    id: uuid.UUID,
    body: WatchlistUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
) -> WatchlistOut:
    w = await session.get(Watchlist, id)
    if w is None:
        raise HTTPException(404, "Watchlist not found")
    _assert_owned(w, user)
    if body.name is not None:
        w.name = body.name
    if body.client is not None:
        w.client = body.client
    if body.matter is not None:
        w.matter = body.matter
    if body.query is not None:
        w.query = body.query.model_dump()
        total, new = await _run_query(session, body.query)
        w.total_count = total
        w.new_count = new
        w.last_run_at = datetime.now(UTC)
    if body.queryDesc is not None:
        w.query_desc = body.queryDesc
    await session.commit()
    await session.refresh(w)
    return _to_out(w)


@router.delete("/{id}", status_code=204)
async def delete_watchlist(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    w = await session.get(Watchlist, id)
    if w is None:
        raise HTTPException(404, "Watchlist not found")
    _assert_owned(w, user)
    await session.delete(w)
    await session.commit()


def _assert_owned(w: Watchlist, user: User) -> None:
    """403 if `user` doesn't own the watchlist (admins bypass)."""
    if user.is_admin:
        return
    if w.owner_id and w.owner_id != user.id:
        raise HTTPException(403, "You don't own this watchlist")


@router.get("/{id}/findings", response_model=list[TrademarkOut])
async def watchlist_findings(
    id: uuid.UUID,
    limit: int = 12,
    session: AsyncSession = Depends(get_session),
) -> list[TrademarkOut]:
    w = await session.get(Watchlist, id)
    if w is None:
        raise HTTPException(404, "Watchlist not found")
    where = _query_where(WatchQuery(**w.query))
    stmt = select(Trademark).order_by(desc(Trademark.publication_date_441), Trademark.id).limit(limit)
    if where:
        stmt = stmt.where(and_(*where))
    rows = (await session.execute(stmt)).scalars().all()
    return [TrademarkOut.model_validate(r) for r in rows]


# ===== Internals =====


def _query_where(q: WatchQuery):
    where = build_trademark_where(
        q=q.q,
        country=q.country,
        nice_class=q.nice_class if q.nice_class_mode == "all" else None,
        record_type=RecordType(q.record_type) if q.record_type else None,
        applicant_type=q.applicant_type,
        ip_agency=q.ip_agency,
    )
    if q.nice_class and q.nice_class_mode == "any":
        where.append(Trademark.nice_classes.op("&&")(q.nice_class))
    return where


async def _run_query(session: AsyncSession, q: WatchQuery) -> tuple[int, int]:
    """Returns (total_count, new_count). new = matches published in last 30 days."""
    where = _query_where(q)
    base = select(func.count()).select_from(Trademark)
    if where:
        base = base.where(and_(*where))
    total = (await session.execute(base)).scalar_one()
    new_cutoff = DEMO_TODAY - timedelta(days=30)
    new_stmt = base.where(Trademark.publication_date_441 >= new_cutoff)
    new = (await session.execute(new_stmt)).scalar_one()
    return total, new


def _to_out(w: Watchlist) -> WatchlistOut:
    return WatchlistOut(
        id=w.id,
        name=w.name,
        client=w.client,
        matter=w.matter,
        query=WatchQuery(**w.query),
        queryDesc=w.query_desc,
        totalCount=w.total_count,
        newCount=w.new_count,
        createdAt=w.created_at,
        updatedAt=w.updated_at,
        lastRunAt=w.last_run_at,
    )


def _summarize_query(q: WatchQuery) -> str:
    parts: list[str] = []
    if q.q:
        parts.append(f'"{q.q}" ({q.mode})')
    if q.nice_class:
        parts.append(f"Classes {','.join(q.nice_class)} ({q.nice_class_mode.upper()})")
    if q.country:
        parts.append(f"Country {q.country}")
    if q.applicant_type:
        parts.append(q.applicant_type)
    if q.record_type:
        parts.append(q.record_type)
    return " · ".join(parts) if parts else "All marks"
