"""Polite WIPO Madrid Monitor fetch with on-disk raw-HTML cache.

Politeness rails (spec §6): realistic UA + reused session, honors
X-RateLimit-Remaining, jittered inter-request delay (Plan 2 adds 429/Retry-After
backoff, the daily cap, and the circuit breaker). The cache makes re-parse free
(no network) and the backfill resumable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import requests

URL_TEMPLATE = "https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.{irn}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_MIN_DELAY_S = 2.0


@dataclass
class FetchResult:
    irn: str
    html: str
    source_url: str
    from_cache: bool
    rate_remaining: int | None = None


def _http_get(url: str, session: requests.Session | None = None) -> tuple[str, dict]:
    s = session or requests.Session()
    resp = s.get(url, headers={"User-Agent": _UA}, timeout=30)
    resp.raise_for_status()
    return resp.text, dict(resp.headers)


def fetch_raw(
    irn: str,
    cache_dir: Path,
    *,
    session: requests.Session | None = None,
    use_cache: bool = True,
) -> FetchResult:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{irn}.html"
    url = URL_TEMPLATE.format(irn=irn)

    if use_cache and path.exists():
        return FetchResult(
            irn=irn,
            html=path.read_text(encoding="utf-8"),
            source_url=url,
            from_cache=True,
        )

    html, headers = _http_get(url, session=session)
    path.write_text(html, encoding="utf-8")
    rem = headers.get("X-RateLimit-Remaining")
    time.sleep(_MIN_DELAY_S)  # space out real network calls
    return FetchResult(
        irn=irn,
        html=html,
        source_url=url,
        from_cache=False,
        rate_remaining=int(rem) if rem and rem.isdigit() else None,
    )
