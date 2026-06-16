"""Two-stage phonetic retrieval (pg_trgm recall → engine rerank).

These guard the P0 fix in routes/search.py: phonetic "sort by similarity" must
rank the *whole* corpus, not a publication-date-ordered over-fetch window. The
assertions are written to survive data churn — they check behavioural
invariants, not specific mark names.

Run against the dev DB (conftest seeds nothing); they assume the standard
gazette corpus is loaded. A phonetic query for a common stem is expected to
return matches; if your local DB is empty these will be skipped, not failed.
"""

from __future__ import annotations

import pytest


def _name(mark: dict) -> str:
    return (mark.get("mark_sample") or mark.get("applicant_name") or "").lower()


@pytest.mark.asyncio
async def test_phonetic_results_are_sorted_by_score_desc(authed_client):
    r = await authed_client.get(
        "/api/v1/search/trademarks",
        params={"mode": "phonetic", "q": "BONLIV", "threshold": 0.45, "sort": "similarity", "limit": 25},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("no corpus loaded in this DB")
    scores = [it["score"] for it in items]
    assert scores == sorted(scores, reverse=True), "results must be ranked by score descending"


@pytest.mark.asyncio
async def test_phonetic_recall_goes_beyond_substring(authed_client):
    """The whole point of stage 1: surface sound-alikes that do NOT contain the
    literal query. The old ILIKE-only path could never return these."""
    q = "BONLIV"
    r = await authed_client.get(
        "/api/v1/search/trademarks",
        params={"mode": "phonetic", "q": q, "threshold": 0.45, "sort": "similarity", "limit": 50},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("no corpus loaded in this DB")
    non_substring = [it for it in items if q.lower() not in _name(it["mark"])]
    assert non_substring, "phonetic recall must surface at least one non-substring sound-alike"


@pytest.mark.asyncio
async def test_phonetic_respects_threshold(authed_client):
    r = await authed_client.get(
        "/api/v1/search/trademarks",
        params={"mode": "phonetic", "q": "BONLIV", "threshold": 0.6, "sort": "similarity", "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    for it in body["items"]:
        assert it["score"] >= 0.6
    # total counts threshold-passing candidates, so it can't be below the page size.
    assert body["total"] >= len(body["items"])


@pytest.mark.asyncio
async def test_phonetic_gibberish_recalls_tiny_set(authed_client):
    """Gibberish must recall at most a handful of coincidental matches — NOT the
    whole (date-ordered) table. The old path returned a full over-fetch window
    regardless of the query; the new path's trigram recall is selective."""
    r = await authed_client.get(
        "/api/v1/search/trademarks",
        params={"mode": "phonetic", "q": "ZZZQXWVK", "threshold": 0.45, "sort": "similarity", "limit": 200},
    )
    assert r.status_code == 200
    # Far below the ~46k corpus and below any plausible real sound-alike cluster.
    assert r.json()["total"] < 50
