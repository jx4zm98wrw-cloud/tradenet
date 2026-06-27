"""Async search client — httpx-based, schema-driven, used by the census and
stress harnesses where throughput matters.

Mirrors the sync ``SearchClient`` in ``tnqa/__init__.py`` (same field mapping,
same 429/503 backoff honoring ``Retry-After``) but is fully ``async`` so a single
event loop can hold many in-flight connections. Read-only: GET requests only.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from . import Config


@dataclass
class AsyncResponse:
    status: int
    total: int
    items: list[dict]
    scores: list
    latency_s: float
    error: str | None = None
    error_class: str | None = None  # timeout | conn_reset | http_5xx | http_4xx | 429
    raw: dict | None = None


def _classify(status: int, exc: Exception | None) -> str | None:
    if exc is not None:
        name = type(exc).__name__.lower()
        if "timeout" in name:
            return "timeout"
        return "conn_reset"
    if status == 429:
        return "429"
    if status >= 500:
        return "http_5xx"
    if status >= 400:
        return "http_4xx"
    return None


class AsyncSearchClient:
    """One shared ``httpx.AsyncClient`` with a bounded connection pool. Build via
    ``async with AsyncSearchClient(cfg, base_url, ...) as client``."""

    def __init__(
        self,
        cfg: Config,
        base_url: str | None = None,
        *,
        max_connections: int = 1100,
        timeout_s: float = 30.0,
        retry_429: bool = True,
        max_retries: int = 6,
    ):
        self.cfg = cfg
        self.s = cfg.schema
        self.base_url = (base_url or cfg.base_url).rstrip("/")
        self.retry_429 = retry_429
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections)
        headers = {"Accept": "application/json"}
        if cfg.auth_token:
            headers["Authorization"] = f"Bearer {cfg.auth_token}"
        self._client = httpx.AsyncClient(
            limits=limits, timeout=httpx.Timeout(timeout_s), headers=headers
        )

    async def __aenter__(self) -> AsyncSearchClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _params(self, q, mode, ranked, threshold, page, limit, extra) -> dict:
        params = {
            self.s["mode_param"]: mode,
            self.s["sort_param"]: self.s["ranked_sort"] if ranked else self.s["plain_sort"],
            self.s["threshold_param"]: threshold,
            "limit": limit,
            "offset": page * limit,
        }
        if q is not None:
            params["q"] = q
        if extra:
            params.update(extra)
        return params

    async def search(
        self,
        q: str | None,
        *,
        mode: str = "text",
        ranked: bool = True,
        threshold: float = 0.0,
        page: int = 0,
        limit: int = 50,
        extra: dict | None = None,
        keep_raw: bool = False,
    ) -> AsyncResponse:
        url = f"{self.base_url}{self.s['search_path']}"
        params = self._params(q, mode, ranked, threshold, page, limit, extra)
        backoff = 0.5
        t0 = time.perf_counter()
        last_status = 0
        for attempt in range(self.max_retries):
            try:
                resp = await self._client.get(url, params=params)
            except Exception as e:  # network-class error
                return AsyncResponse(
                    0, 0, [], [], time.perf_counter() - t0,
                    error=repr(e), error_class=_classify(0, e),
                )
            last_status = resp.status_code
            if resp.status_code == 200:
                body = resp.json()
                items = body.get(self.s["items"], [])
                return AsyncResponse(
                    status=200,
                    total=int(body.get(self.s["total"], len(items))),
                    items=items,
                    scores=[it.get(self.s["score"]) for it in items],
                    latency_s=time.perf_counter() - t0,
                    raw=body if keep_raw else None,
                )
            if resp.status_code in (429, 503) and self.retry_429 and attempt < self.max_retries - 1:
                try:
                    wait = float(resp.headers.get("Retry-After", "") or backoff)
                except (TypeError, ValueError):
                    wait = backoff
                await asyncio.sleep(min(wait, 30))
                backoff *= 2
                continue
            # Non-retryable (or retries off): return the error response.
            return AsyncResponse(
                resp.status_code, 0, [], [], time.perf_counter() - t0,
                error=f"HTTP {resp.status_code}", error_class=_classify(resp.status_code, None),
            )
        return AsyncResponse(
            last_status or 429, 0, [], [], time.perf_counter() - t0,
            error=f"HTTP {last_status} (retries exhausted)",
            error_class=_classify(last_status or 429, None),
        )

    # --- schema-driven field access (mirrors the sync client) ---
    def _dig(self, item: dict, dotted: str):
        cur = item
        for part in dotted.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur

    def appno_of(self, item: dict) -> str | None:
        return self._dig(item, self.s["application_number"])

    def appnos(self, items: list[dict]) -> list[str]:
        return [a for a in (self.appno_of(it) for it in items) if a]

    def id_of(self, item: dict) -> str | None:
        """The always-present record id (Madrid rows can have NULL application_number,
        so dedup/gap integrity must key on id, not appno)."""
        v = self._dig(item, "mark.id")
        return str(v) if v is not None else None

    def ids(self, items: list[dict]) -> list[str]:
        return [i for i in (self.id_of(it) for it in items) if i]
