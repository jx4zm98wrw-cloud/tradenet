"""Authentication: bcrypt password hashing + HS256 JWT bearer tokens.

The dependency surface is unchanged from the previous stub — `require_user`
and `require_admin` are still the entry points every protected route uses —
but the resolver now decodes a Bearer token instead of returning a hardcoded
stub user.

Token model
-----------
Two-token flow:
  - **Access token** (15 min) carries `sub` (user id), `role`, and a `tv`
    (token_version) claim. Sent as `Authorization: Bearer <jwt>` on each
    API request. Short-lived to limit replay damage.
  - **Refresh token** (7 days) lives in an httpOnly + Secure + SameSite=Lax
    cookie. Used only against `POST /auth/refresh` to mint a new access
    token. Carries the same claims plus a `typ: refresh` discriminator so
    a leaked access token can't be used to mint refreshes.

Both tokens are HS256-signed with `Settings.secret_key` (we hard-enforced
non-default in C3). `tv` claim implements revocation: incrementing
`User.token_version` server-side invalidates every issued token instantly
(used on logout-all, password change, suspected compromise).

Security notes
--------------
- Bcrypt cost factor 12 — ~250 ms per verify on modern hardware. Slow
  enough to deter offline attacks, fast enough that login UX is fine.
- `Authentication required` on protected routes returns 401 with a
  generic message (don't leak which header was wrong).
- `_resolve_user` returns `None` for any token problem — handlers
  upgrade to 401/403 as appropriate. This keeps the failure modes
  consistent regardless of which token check failed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .db.models import User as DBUser
from .db.models import UserRole
from .settings import get_settings

# ---------------------------------------------------------------------------
# Password hashing — bcrypt directly (skip passlib because passlib 1.7.4 is
# incompatible with bcrypt>=4.0; pinning passlib older would just push the
# CVE-hygiene problem onto bcrypt instead. Using bcrypt directly is 5 lines.)
# ---------------------------------------------------------------------------

# bcrypt rounds: 12 is the modern default (~250 ms per hash on commodity
# hardware). Production deployments on faster hardware should bump this
# until verify takes ~250 ms.
_BCRYPT_ROUNDS = 12

# Bcrypt truncates inputs at 72 bytes (algorithmic limit). Truncate ourselves
# rather than letting bcrypt raise, so a paste of a 100-char password just
# uses the first 72 bytes instead of erroring out. Users entering long
# passwords still get a usable account.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage. ~250 ms per call."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    pwd_bytes = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pwd_bytes, salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verify. Returns False on any error (bad hash format,
    None, etc.) — never raises, so callers can use a single failure path."""
    try:
        pwd_bytes = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pwd_bytes, hashed.encode("ascii"))
    except (ValueError, TypeError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# JWT token issuance + decode
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"
_ACCESS_TTL = timedelta(minutes=15)
_REFRESH_TTL = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(UTC)


def issue_access_token(user: DBUser) -> str:
    """Mint a 15-minute access token. Carries sub/role/tv claims so the
    middleware can authorize without a DB round-trip on every request.
    `jti` is a UUID4 — ensures every issued token is unique even within
    the same second (needed for refresh-rotation correctness and as a
    foundation for any future blacklist/revocation feature)."""
    now = _now()
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "tv": user.token_version,
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + _ACCESS_TTL).timestamp()),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=_ALGORITHM)


def issue_refresh_token(user: DBUser) -> str:
    """Mint a 7-day refresh token. Stored in an httpOnly cookie by the
    `/auth/login` endpoint; sent back only to `/auth/refresh`. `jti` UUID
    makes each refresh rotation produce a distinct token (defends against
    refresh-replay if leaked)."""
    now = _now()
    payload = {
        "sub": str(user.id),
        "tv": user.token_version,
        "typ": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + _REFRESH_TTL).timestamp()),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=_ALGORITHM)


def decode_token(token: str, expected_typ: Literal["access", "refresh"]) -> dict | None:
    """Decode + validate signature + expiry + token type. Returns the
    claims dict or None on any failure (don't leak which check failed)."""
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        return None
    if claims.get("typ") != expected_typ:
        return None
    return claims


# ---------------------------------------------------------------------------
# User-facing dependency surface (unchanged signatures from the stub)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    """Lightweight projection passed to route handlers. Built from the DB
    User in `_resolve_user`. Has only the fields routes actually need —
    keeps the dependency cheap and avoids holding a session-bound ORM
    object across request boundaries."""

    id: str
    email: str
    name: str
    role: UserRole

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin


def _extract_bearer(request: Request) -> str | None:
    """Pull the access token from the `Authorization: Bearer <jwt>` header."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


async def _resolve_user(request: Request, session: AsyncSession) -> User | None:
    """Decode the Bearer access token, load the user, return None if any
    step fails (invalid signature, expired token, missing user, disabled
    user, stale token_version)."""
    token = _extract_bearer(request)
    if token is None:
        return None
    claims = decode_token(token, expected_typ="access")
    if claims is None:
        return None
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    db_user = (await session.execute(select(DBUser).where(DBUser.id == user_id))).scalar_one_or_none()
    if db_user is None or not db_user.is_active:
        return None
    # Revocation check: refresh-token-version on the user record must be
    # >= the version baked into the token. Mismatch = token issued before
    # a logout-all or password change.
    if db_user.token_version != claims.get("tv"):
        return None
    return User(
        id=str(db_user.id),
        email=db_user.email,
        name=db_user.name,
        role=db_user.role,
    )


async def optional_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
    """Yields the current user if authenticated, None otherwise. Use on routes
    that personalise output but stay readable to anonymous clients."""
    return await _resolve_user(request, session)


async def require_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    """Yields the current user; 401 if no one is authenticated. Use on routes
    that mutate or expose private data."""
    user = await _resolve_user(request, session)
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


def require_role(*allowed: UserRole):
    """Factory for role-checked deps. e.g. `Depends(require_role(UserRole.admin,
    UserRole.editor))` on a route requires either admin OR editor.

    Use this when a route should accept multiple roles (e.g. an "upload PDF"
    endpoint that admins and editors can both call). `require_user` /
    `require_admin` cover the common cases."""

    async def _check(user: User = Depends(require_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {[r.value for r in allowed]}",
            )
        return user

    return _check
