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

from ..auth import User, require_user
from ..db.models import UserRole

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


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
