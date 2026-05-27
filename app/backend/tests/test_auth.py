"""Auth flow tests — login, refresh, logout, /me + token validation.

Covers the audit-C1 acceptance criteria:
  - Unauthenticated requests to protected endpoints return 401
  - Login with bad credentials returns 401 (generic message)
  - Login with good credentials returns access token + refresh cookie
  - /auth/me round-trips the access token correctly
  - Refresh produces a fresh access token; rotates the refresh cookie
  - Logout bumps token_version (invalidates all outstanding tokens)
  - An access token from before logout is rejected
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import hash_password
from api.db.models import User, UserRole
from api.settings import get_settings

_EMAIL = "auth-test-user@example.com"
_PASSWORD = "correct-horse-battery-staple"  # 30 chars, passes the min-length check


@pytest_asyncio.fixture(autouse=True)
async def seed_test_user() -> AsyncIterator[None]:
    """Fresh test user before every test; deleted after."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        await s.execute(delete(User).where(User.email == _EMAIL))
        await s.commit()
        s.add(
            User(
                id=uuid.uuid4(),
                email=_EMAIL,
                password_hash=hash_password(_PASSWORD),
                name="Auth Test",
                role=UserRole.editor,
                is_active=True,
                token_version=0,
            )
        )
        await s.commit()

    try:
        yield
    finally:
        async with Session() as s:
            await s.execute(delete(User).where(User.email == _EMAIL))
            await s.commit()
        await engine.dispose()


async def test_unauthenticated_me_returns_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_login_bad_password_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": _EMAIL, "password": "wrong-password-12345"})
    assert r.status_code == 401
    # Generic detail — don't leak whether the email exists
    assert "invalid" in r.json()["error"]["message"].lower()


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "any-password-1234"},
    )
    assert r.status_code == 401


async def test_login_success_returns_token_and_cookie(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accessToken"].count(".") == 2  # JWT = header.payload.sig
    assert body["user"]["email"] == _EMAIL
    assert body["user"]["role"] == "editor"
    # Refresh cookie set
    assert "tm_refresh" in r.cookies


async def test_me_with_bearer_returns_user(client: AsyncClient) -> None:
    login = await client.post("/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    token = login.json()["accessToken"]
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == _EMAIL


async def test_refresh_mints_new_access_token(client: AsyncClient) -> None:
    login = await client.post("/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    refresh_cookie = login.cookies.get("tm_refresh")
    assert refresh_cookie is not None

    r = await client.post("/api/v1/auth/refresh", cookies={"tm_refresh": refresh_cookie})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accessToken"] != login.json()["accessToken"]
    # Refresh cookie should be rotated
    assert r.cookies.get("tm_refresh") is not None


async def test_logout_bumps_token_version_revoking_existing_tokens(
    client: AsyncClient,
) -> None:
    login = await client.post("/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    token = login.json()["accessToken"]

    # Logout — bumps token_version. Cookie is part of the request via the
    # AsyncClient session.
    logout = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 204

    # The access token issued before logout must now be rejected.
    after = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401


async def test_bearer_token_missing_returns_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


async def test_inactive_user_cannot_login(client: AsyncClient) -> None:
    # Mark the seed user inactive
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        from sqlalchemy import update

        await s.execute(update(User).where(User.email == _EMAIL).values(is_active=False))
        await s.commit()
    await engine.dispose()

    r = await client.post("/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert r.status_code == 401
