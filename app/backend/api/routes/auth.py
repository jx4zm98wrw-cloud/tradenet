"""Auth endpoints — login, refresh, logout, me.

Flow
----
1. **POST /auth/login**
   Body: `{ "email": "...", "password": "..." }`
   On success: returns `{ accessToken, user }`, sets a `tm_refresh` httpOnly
   cookie with the refresh JWT.

2. **GET /auth/me**
   Header: `Authorization: Bearer <accessToken>`
   Returns the current `user` payload (id, email, name, role).

3. **POST /auth/refresh**
   Reads the `tm_refresh` cookie. Returns a fresh access token (and rotates
   the refresh cookie). Used by the frontend when the access token nears
   expiry.

4. **POST /auth/logout**
   Bumps `User.token_version` (invalidating ALL outstanding tokens), clears
   the refresh cookie. Use this on intentional logout AND on suspected
   compromise — there's no separate "logout all" endpoint.

CSRF
----
The refresh cookie is `SameSite=Lax` + `HttpOnly` + `Secure` (in
production). Lax allows the cookie on top-level GETs but blocks
cross-origin POSTs — combined with the `Authorization` header check
on every other endpoint, this protects against CSRF on state-changing
requests. The CORS allow_headers list (api/main.py) explicitly includes
`X-CSRF-Token` for future double-submit-cookie wiring if needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    User,
    decode_token,
    issue_access_token,
    issue_refresh_token,
    require_user,
    verify_password,
)
from ..db import get_session
from ..db.models import User as DBUser
from ..db.models import UserRole
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_REFRESH_COOKIE = "tm_refresh"
_REFRESH_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

# Real bcrypt hash for "_dummy_" (any literal — verify returns False, we
# discard the result). Computed once at module import so login timing is
# constant whether the user exists or not.
from ..auth import hash_password as _hash  # local import to avoid circular  # noqa: E402

_DUMMY_HASH = _hash("_dummy_unused_constant_time_padding_")


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class LoginIn(BaseModel):
    # Email validation is intentionally light: we strip + lowercase before
    # use, and don't gate creation on deliverability. The user creator (CLI)
    # decides who exists; this endpoint just checks credentials. Skipping
    # EmailStr keeps the email-validator dep out of the tree.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole

    @classmethod
    def from_db(cls, u: DBUser) -> UserOut:
        return cls(id=str(u.id), email=u.email, name=u.name, role=u.role)

    @classmethod
    def from_dep(cls, u: User) -> UserOut:
        return cls(id=u.id, email=u.email, name=u.name, role=u.role)


class LoginOut(BaseModel):
    accessToken: str
    user: UserOut


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Sets the refresh cookie with the audit-recommended flags. Secure flag
    is on only in production — local dev runs HTTP, so the browser would
    refuse to send a Secure cookie."""
    settings = get_settings()
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        max_age=_REFRESH_MAX_AGE,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/v1/auth",  # cookie only travels to auth endpoints
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(_REFRESH_COOKIE, path="/api/v1/auth")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginOut)
async def login(
    body: LoginIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LoginOut:
    """Verify email + password. Returns access token + sets refresh cookie."""
    # Lower-case the email before lookup — the DB doesn't use CITEXT and we
    # want "Alice@Example.com" and "alice@example.com" to refer to the same
    # account.
    email = body.email.strip().lower()
    user = (await session.execute(select(DBUser).where(DBUser.email == email))).scalar_one_or_none()

    # Generic 401 regardless of which check failed (don't leak which emails
    # exist). verify_password() returns False if user is None too via a dummy
    # hash — but we already short-circuit.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if user is None or not user.is_active:
        # Run a verify against a real bcrypt hash anyway so timing is
        # constant-ish whether or not the email exists. ~250 ms regardless.
        # (The hash is for the literal string "x" — verify will return
        # False; we discard the result.)
        verify_password(body.password, _DUMMY_HASH)
        raise invalid
    if not verify_password(body.password, user.password_hash):
        raise invalid

    access = issue_access_token(user)
    refresh = issue_refresh_token(user)
    _set_refresh_cookie(response, refresh)
    return LoginOut(accessToken=access, user=UserOut.from_db(user))


@router.post("/refresh", response_model=LoginOut)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LoginOut:
    """Trade a valid refresh cookie for a new access token. Rotates the
    refresh cookie too — every refresh produces a fresh refresh JWT, so a
    leaked refresh becomes useless after one use (token_version bump still
    works for instant revoke)."""
    cookie = request.cookies.get(_REFRESH_COOKIE)
    if cookie is None:
        raise HTTPException(status_code=401, detail="No refresh cookie")
    claims = decode_token(cookie, expected_typ="refresh")
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    import uuid as _uuid

    try:
        uid = _uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status_code=401, detail="Malformed refresh token") from e
    user = (await session.execute(select(DBUser).where(DBUser.id == uid))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if user.token_version != claims.get("tv"):
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    new_access = issue_access_token(user)
    new_refresh = issue_refresh_token(user)
    _set_refresh_cookie(response, new_refresh)
    return LoginOut(accessToken=new_access, user=UserOut.from_db(user))


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    me: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Bump token_version (invalidates all tokens) + clear refresh cookie."""
    import uuid as _uuid

    await session.execute(
        update(DBUser)
        .where(DBUser.id == _uuid.UUID(me.id))
        .values(token_version=DBUser.token_version + 1, updated_at=datetime.now(UTC))
    )
    await session.commit()
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_user)) -> UserOut:
    """Resolve the current user from the access token. Cheap — no DB hit
    (require_user already loaded + validated)."""
    return UserOut.from_dep(user)
