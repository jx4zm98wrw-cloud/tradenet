"""Smoke tests — one per route group. Verify wiring + status codes + envelope shape.
Run async via httpx.AsyncClient so the asyncpg pool stays on a single event loop.
"""

from __future__ import annotations

from httpx import AsyncClient

# ---------- meta ----------


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_openapi_schema_present(client: AsyncClient) -> None:
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    assert "openapi" in r.json()


# ---------- gazettes ----------


async def test_list_gazettes_returns_list(authed_client: AsyncClient) -> None:
    """Listing is now admin-only — authed_client is an admin user."""
    r = await authed_client.get("/api/v1/gazettes")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body
    assert isinstance(body["items"], list)


async def test_list_gazettes_unauthenticated_returns_401(client: AsyncClient) -> None:
    """Defense-in-depth: anonymous clients can't enumerate the pipeline."""
    r = await client.get("/api/v1/gazettes")
    assert r.status_code == 401


async def test_list_gazettes_viewer_returns_403(viewer_client: AsyncClient) -> None:
    """A logged-in viewer is rejected (admin-only)."""
    r = await viewer_client.get("/api/v1/gazettes")
    assert r.status_code == 403


async def test_upload_rejects_non_pdf(authed_client: AsyncClient) -> None:
    files = {"file": ("plain.txt", b"not a pdf", "text/plain")}
    r = await authed_client.post("/api/v1/gazettes", files=files)
    assert r.status_code == 400


async def test_upload_unauthenticated_returns_401(client: AsyncClient) -> None:
    """Confirms the C1 hardening: gazette upload requires auth."""
    files = {"file": ("plain.txt", b"not a pdf", "text/plain")}
    r = await client.post("/api/v1/gazettes", files=files)
    assert r.status_code == 401


async def test_upload_viewer_returns_403(viewer_client: AsyncClient) -> None:
    """Viewer role can't trigger ingest (require_role(admin, editor))."""
    files = {"file": ("plain.txt", b"not a pdf", "text/plain")}
    r = await viewer_client.post("/api/v1/gazettes", files=files)
    assert r.status_code == 403


async def test_upload_editor_passes_role_check(editor_client: AsyncClient) -> None:
    """Editor passes role gate; non-PDF then 400s on the magic-byte check.
    The 400 here proves the request reached the body validation path,
    which only happens after the role check passes."""
    files = {"file": ("plain.txt", b"not a pdf", "text/plain")}
    r = await editor_client.post("/api/v1/gazettes", files=files)
    assert r.status_code == 400


# ---------- search + facets ----------


async def test_search_trademarks_smoke(client: AsyncClient) -> None:
    r = await client.get("/api/v1/search/trademarks", params={"q": "neur", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert {"items", "total", "limit", "offset"} <= body.keys()
    for item in body["items"]:
        assert {"mark", "score"} <= item.keys()
        assert 0.0 <= item["score"] <= 1.0


async def test_facets_cross_react(client: AsyncClient) -> None:
    g = await client.get("/api/v1/facets/nice-classes", params={"limit": 3})
    f = await client.get("/api/v1/facets/nice-classes", params={"limit": 3, "country": "VN"})
    assert g.status_code == 200 and f.status_code == 200
    for r in (g, f):
        for bucket in r.json():
            assert {"key", "count"} <= bucket.keys()


# ---------- today ----------


async def test_today_digest_shape(client: AsyncClient) -> None:
    r = await client.get("/api/v1/today/digest")
    assert r.status_code == 200
    body = r.json()
    for k in (
        "today",
        "totalNew",
        "activeWatchlists",
        "watchlistsWithFindings",
        "closingIn7Days",
        "closingIn14Days",
        "lastSyncAt",
    ):
        assert k in body


async def test_opposition_windows_returns_dates(client: AsyncClient) -> None:
    r = await client.get("/api/v1/opposition-windows", params={"status": "open", "limit": 3})
    assert r.status_code == 200
    for w in r.json():
        assert {"markId", "closesAt", "daysLeft", "status"} <= w.keys()


# ---------- compare ----------


async def test_compare_requires_two_marks(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/compare",
        json={"markIds": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert r.status_code == 422  # Pydantic min_length validation


# ---------- watchlists ----------


async def test_watchlists_crud(authed_client: AsyncClient) -> None:
    body = {
        "name": "TEST watchlist (smoke)",
        "client": "Test client",
        "matter": "T-1",
        "query": {"q": "zzz_nomatch", "mode": "text"},
    }
    created = await authed_client.post("/api/v1/watchlists", json=body)
    assert created.status_code == 201
    wl = created.json()
    assert wl["name"] == body["name"]
    wid = wl["id"]
    try:
        listed = await authed_client.get("/api/v1/watchlists")
        assert listed.status_code == 200
        assert any(w["id"] == wid for w in listed.json())
        f = await authed_client.get(f"/api/v1/watchlists/{wid}/findings")
        assert f.status_code == 200
        assert isinstance(f.json(), list)
    finally:
        d = await authed_client.delete(f"/api/v1/watchlists/{wid}")
        assert d.status_code == 204


# ---------- admin ----------


async def test_admin_check_requires_auth(client: AsyncClient) -> None:
    """Anonymous → 401 (no longer a hardcoded `true`)."""
    r = await client.get("/api/v1/admin/check")
    assert r.status_code == 401


async def test_admin_check_admin_returns_true(authed_client: AsyncClient) -> None:
    """Authed admin user → isAdmin=true with role=admin."""
    r = await authed_client.get("/api/v1/admin/check")
    assert r.status_code == 200
    body = r.json()
    assert body["isAdmin"] is True
    assert body["role"] == "admin"


async def test_admin_check_viewer_returns_false(viewer_client: AsyncClient) -> None:
    """Viewer is logged in but isAdmin=false (200, not 403 — frontend uses
    the response to redirect, not error)."""
    r = await viewer_client.get("/api/v1/admin/check")
    assert r.status_code == 200
    body = r.json()
    assert body["isAdmin"] is False
    assert body["role"] == "viewer"
