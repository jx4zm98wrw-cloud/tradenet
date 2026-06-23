"""Fetch IP VIETNAM WIPOPublish trademark detail HTML, with the TLS fix + retry.

Two IP VIETNAM obstacles are handled here (both verified live):
  1. Broken TLS chain — the server omits the Sectigo R36 intermediate, so we
     pass our committed bundle (certifi roots + that intermediate) as `verify`.
     Verification stays ON (deterministic in the Linux worker/CI).
  2. Cluster flakiness — an Apache proxy fronts unhealthy Tomcat nodes; ~50% of
     requests get an instant generic 500. We retry until HTTP 200 AND the body
     looks like a real detail page (`product-form-label` present), then cache.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

URL_TEMPLATE = "https://wipopublish.ipvietnam.gov.vn/wopublish-search/public/ajax/detail/trademarks?id={vnid}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_VALID_MARKER = "product-form-label"
_CA_BUNDLE = str(Path(__file__).with_name("noip_ca_bundle.pem"))
_MIN_DELAY_S = 1.0
# Statuses that mean "stop", not "retry": 403 = forbidden/blocked, 429 = rate
# limited. Retrying these 10x at a fixed interval is exactly how a soft throttle
# escalates into a hard IP ban, so we raise NoipBlockedError instead — the sweep
# pauses immediately and a human decides when to resume. 5xx stays retryable
# (the flaky-cluster case we built the retry loop for).
_BLOCK_STATUSES = frozenset({403, 429})
# Cap the flaky-5xx retry backoff LOW. IP VIETNAM's ~50% 500s are random cluster
# flakiness, not rate-limiting, so waiting longer doesn't improve the next
# attempt's odds — it just stalls the sweep (a 60s cap produced ~286s/mark
# tails, ~doubling wall-clock). Genuine rate-limit signals are handled
# separately and DO back off fully (Retry-After header; 403/429 → stop).
_MAX_BACKOFF_S = 8.0


class NoipBlockedError(RuntimeError):
    """IP VIETNAM returned a block/rate-limit status (403/429). Distinct from the
    retryable flaky-cluster 5xx: the caller should STOP and pause, not retry."""

    def __init__(self, vnid: str, status: int, retry_after: float | None = None) -> None:
        self.status = status
        self.retry_after = retry_after
        suffix = f" (Retry-After {retry_after:.0f}s)" if retry_after else ""
        super().__init__(f"IP VIETNAM blocked fetch for {vnid}: HTTP {status}{suffix}")


@dataclass
class FetchResult:
    vnid: str
    html: str
    source_url: str
    from_cache: bool
    attempts: int = 0
    # "ok"        — HTTP 200 with a real detail page (`product-form-label`).
    # "not_found" — HTTP 200 but a skeleton page (marker absent): IP VIETNAM has no
    #               published detail for this id yet. A definitive negative, not
    #               flakiness, so the caller records + skips it instead of
    #               retrying to exhaustion. The skeleton is NOT cached to disk.
    outcome: Literal["ok", "not_found"] = "ok"


def _is_valid(status_code: int, body: str) -> bool:
    return status_code == 200 and _VALID_MARKER in body


def _backoff_seconds(attempt: int, base: float) -> float:
    """Exponential backoff for a retryable flaky 5xx, capped at _MAX_BACKOFF_S.
    The cap is deliberately low: the 500s are random flakiness, not rate-limiting,
    so a long wait is pure stall (genuine throttling comes via Retry-After/403/429
    and is handled by the caller)."""
    return min(base * (2 ** (attempt - 1)), _MAX_BACKOFF_S)


def _retry_after_seconds(resp: object) -> float | None:
    """Parse a `Retry-After` header in seconds form. HTTP-date form is rare here
    and ignored (caller falls back to its own backoff)."""
    raw = getattr(resp, "headers", {}).get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def fetch_raw(
    vnid: str,
    cache_dir: Path,
    *,
    session: requests.Session | None = None,
    use_cache: bool = True,
    max_attempts: int = 10,
    delay: float = 1.5,
) -> FetchResult:
    """Fetch one mark's detail HTML, retrying the flaky cluster. `vnid` is the
    IP VIETNAM id (`VN4202600774`). Raises RuntimeError if no valid body after
    `max_attempts`. `session` is injectable for tests (any object with a
    requests-style `.get`)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{vnid}.html"
    url = URL_TEMPLATE.format(vnid=vnid)

    if use_cache and path.exists():
        return FetchResult(vnid=vnid, html=path.read_text(encoding="utf-8"), source_url=url, from_cache=True)

    s = session if session is not None else requests.Session()
    last_status: int | None = None
    for attempt in range(1, max_attempts + 1):
        resp = s.get(url, headers={"User-Agent": _UA}, timeout=30, verify=_CA_BUNDLE)
        last_status = resp.status_code
        body = resp.text
        if _is_valid(last_status, body):
            path.write_text(body, encoding="utf-8")
            if delay:
                time.sleep(_MIN_DELAY_S)
            return FetchResult(vnid=vnid, html=body, source_url=url, from_cache=False, attempts=attempt)
        # HTTP 200 but no detail marker = IP VIETNAM has no published detail for this id
        # yet (the ~2,178-byte skeleton page). This is a DEFINITIVE negative,
        # stable across attempts — not the flaky-cluster 500. Return it at once so
        # the caller records + skips it; do NOT retry (pointless) and do NOT write
        # the skeleton to cache (it must re-check after the backoff window).
        if last_status == 200:
            return FetchResult(
                vnid=vnid,
                html=body,
                source_url=url,
                from_cache=False,
                attempts=attempt,
                outcome="not_found",
            )
        # A block / rate-limit is NOT retryable — raise so the sweep pauses
        # immediately instead of hammering and escalating to a hard ban.
        if last_status in _BLOCK_STATUSES:
            raise NoipBlockedError(vnid, last_status, _retry_after_seconds(resp))
        # Otherwise it's the flaky-cluster 5xx: back off (honor Retry-After if
        # present, else a low-capped exponential) and retry.
        if delay and attempt < max_attempts:
            wait = _retry_after_seconds(resp)
            if wait is None:
                wait = _backoff_seconds(attempt, delay)
            time.sleep(wait)
    raise RuntimeError(
        f"IP VIETNAM fetch failed for {vnid}: no valid body in {max_attempts} attempts (last status {last_status})"
    )
