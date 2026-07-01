"""Unit tests for the facet TTL cache decorator (`routes.facets._facet_cached`).

Pure decorator mechanics — no DB, no HTTP. Verifies same-signature hits, distinct
filter signatures miss independently, and expiry recomputes.
"""

from __future__ import annotations

import pytest

from api.routes import facets


@pytest.mark.asyncio
async def test_hit_miss_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    facets._facet_cache.clear()
    calls = {"n": 0}

    @facets._facet_cached("t")
    async def fn(*, filters: dict, limit: int | None = None) -> list:
        calls["n"] += 1
        return ["result", calls["n"]]

    # Same signature → computed once, second call is a cache hit (identical object).
    a = await fn(filters={"country": "VN"})
    b = await fn(filters={"country": "VN"})
    assert calls["n"] == 1
    assert a is b

    # Different filter signature → independent miss.
    await fn(filters={"country": "US"})
    assert calls["n"] == 2

    # Different limit → independent miss (limit is part of the key).
    await fn(filters={"country": "VN"}, limit=8)
    assert calls["n"] == 3

    # Expiry: from a clean cache, store with a past TTL so every entry is stale.
    monkeypatch.setattr(facets, "_FACET_TTL_S", -1.0)
    facets._facet_cache.clear()
    await fn(filters={"country": "VN"})  # stores an already-expired entry
    n_before = calls["n"]
    await fn(filters={"country": "VN"})  # stale → recompute (not a hit)
    assert calls["n"] == n_before + 1


@pytest.mark.asyncio
async def test_none_filter_values_do_not_split_the_key() -> None:
    facets._facet_cache.clear()
    calls = {"n": 0}

    @facets._facet_cached("t2")
    async def fn(*, filters: dict, limit: int | None = None) -> int:
        calls["n"] += 1
        return calls["n"]

    # Only non-None filter values form the signature, so these two are the SAME key.
    await fn(filters={"country": "VN", "applicant": None, "year": None})
    await fn(filters={"country": "VN"})
    assert calls["n"] == 1
