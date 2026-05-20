"""Admin check — stubbed until auth lands.

The /admin/* frontend routes call this to decide whether to render. Right now
it always returns isAdmin=true; once a real user model exists, this will inspect
the session/JWT and return false for daily users.
"""
from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminCheck(BaseModel):
    isAdmin: bool
    reason: str


@router.get("/check", response_model=AdminCheck)
async def check() -> AdminCheck:
    # TODO: replace with real auth check (role lookup on the current user).
    return AdminCheck(isAdmin=True, reason="auth not implemented; defaulting to admin")
