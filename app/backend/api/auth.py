"""Authentication scaffolding.

Production auth isn't wired yet (no user table, no IdP). What's here is the
**dependency surface** every route should use, so when real auth lands it's a
single-function swap — call sites don't change.

Currently:
- `get_current_user()`   — returns a stub `User` regardless of request
- `require_user()`       — same, but explicit "this route needs a logged-in user"
- `require_admin()`      — same, but checks `is_admin` (always True for stub)
- `optional_user()`      — returns None if no auth (for public endpoints that
                           personalise when present)

Swap-in plan:
1. Add `users` + `sessions` tables (Alembic migration)
2. Replace `_resolve_user()` to read session cookie / Bearer token
3. Wire `Settings.secret_key` to whichever issuer (JWT, signed cookie, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    is_admin: bool


# Singleton stub user. When real auth lands, _resolve_user() returns either
# a real User (from cookie/JWT) or None.
_STUB_USER = User(
    id="00000000-0000-0000-0000-000000000001",
    email="francis@example.com",
    name="Francis Lam",
    is_admin=True,
)


async def _resolve_user(request: Request) -> User | None:
    """The seam where real auth plugs in. Today: everyone is the stub user."""
    return _STUB_USER


async def optional_user(request: Request) -> User | None:
    """Yields the current user if authenticated, None otherwise. Use on routes
    that personalise output but stay readable to anonymous clients (e.g. /search).
    """
    return await _resolve_user(request)


async def require_user(request: Request) -> User:
    """Yields the current user; 401 if no one is authenticated. Use on routes
    that mutate or expose private data (POST /watchlists, etc.)."""
    user = await _resolve_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    """Yields the current user only if they're an admin; 403 otherwise."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user
