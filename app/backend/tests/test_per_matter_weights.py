"""Per-matter similarity weights — resolve_weights helper + watchlist storage +
watchlist-scoped similar-marks ranking.

Unit tests pin the merge/normalise semantics; API tests round-trip weights
through the watchlist endpoints and confirm the similar-marks endpoint accepts
a watchlist context. API tests run against the dev DB via the authed_client
fixture and clean up after themselves.
"""

from __future__ import annotations

import pytest

from tm_similarity import DEFAULT_WEIGHTS, resolve_weights

# ----- resolve_weights (pure) -------------------------------------------------


def test_none_and_empty_return_defaults():
    assert resolve_weights(None) == DEFAULT_WEIGHTS
    assert resolve_weights({}) == DEFAULT_WEIGHTS


def test_full_override_normalises_to_one():
    w = resolve_weights({"phonetic": 1.0, "visual": 0.0, "semantic": 0.0, "class": 0.0, "vienna": 0.0})
    assert w["phonetic"] == pytest.approx(1.0)
    assert sum(w.values()) == pytest.approx(1.0)


def test_partial_override_merges_then_normalises():
    # phonetic overridden, the other three inherit defaults, all renormalised.
    w = resolve_weights({"phonetic": 0.8})
    assert sum(w.values()) == pytest.approx(1.0)
    # phonetic should dominate vs its 0.40 default share.
    assert w["phonetic"] > DEFAULT_WEIGHTS["phonetic"]


def test_unknown_keys_and_negatives_ignored():
    assert resolve_weights({"bogus": 5}) == DEFAULT_WEIGHTS
    assert resolve_weights({"phonetic": -1}) == DEFAULT_WEIGHTS


def test_all_zero_falls_back_to_defaults():
    assert resolve_weights({k: 0 for k in DEFAULT_WEIGHTS}) == DEFAULT_WEIGHTS


# ----- watchlist storage round-trip ------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_weights_roundtrip(authed_client):
    body = {
        "name": "Pharma matter (phonetic-heavy)",
        "query": {},
        "weights": {"phonetic": 0.7, "visual": 0.1, "class": 0.1, "vienna": 0.1},
    }
    r = await authed_client.post("/api/v1/watchlists", json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    wl_id = created["id"]
    try:
        assert created["weights"] == {"phonetic": 0.7, "visual": 0.1, "class": 0.1, "vienna": 0.1}
        # similar-marks accepts the watchlist context without error.
        got = await authed_client.get("/api/v1/search/trademarks", params={"limit": 1})
        items = got.json()["items"]
        if items:
            mid = items[0]["mark"]["id"]
            s = await authed_client.get(f"/api/v1/marks/{mid}/similar", params={"watchlist_id": wl_id})
            assert s.status_code == 200
    finally:
        await authed_client.delete(f"/api/v1/watchlists/{wl_id}")


@pytest.mark.asyncio
async def test_invalid_weights_rejected(authed_client):
    bad = {"name": "bad", "query": {}, "weights": {"phonetic": -1}}
    r = await authed_client.post("/api/v1/watchlists", json=bad)
    assert r.status_code == 400

    bad2 = {"name": "bad2", "query": {}, "weights": {"bogus": 0.5}}
    r2 = await authed_client.post("/api/v1/watchlists", json=bad2)
    assert r2.status_code == 400
