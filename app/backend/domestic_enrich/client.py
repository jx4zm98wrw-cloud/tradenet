"""Fetch NOIP WIPOPublish trademark detail HTML, with the TLS fix + retry.

Two NOIP obstacles are handled here (both verified live):
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

import requests

URL_TEMPLATE = "https://wipopublish.ipvietnam.gov.vn/wopublish-search/public/ajax/detail/trademarks?id={vnid}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_VALID_MARKER = "product-form-label"
_CA_BUNDLE = str(Path(__file__).with_name("noip_ca_bundle.pem"))
_MIN_DELAY_S = 1.0


@dataclass
class FetchResult:
    vnid: str
    html: str
    source_url: str
    from_cache: bool
    attempts: int = 0


def _is_valid(status_code: int, body: str) -> bool:
    return status_code == 200 and _VALID_MARKER in body


def fetch_raw(
    vnid: str,
    cache_dir: Path,
    *,
    session: requests.Session | object | None = None,
    use_cache: bool = True,
    max_attempts: int = 10,
    delay: float = 1.5,
) -> FetchResult:
    """Fetch one mark's detail HTML, retrying the flaky cluster. `vnid` is the
    NOIP id (`VN4202600774`). Raises RuntimeError if no valid body after
    `max_attempts`. `session` is injectable for tests (any object with a
    requests-style `.get`)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{vnid}.html"
    url = URL_TEMPLATE.format(vnid=vnid)

    if use_cache and path.exists():
        return FetchResult(vnid=vnid, html=path.read_text(encoding="utf-8"), source_url=url, from_cache=True)

    s = session if session is not None else requests.Session()
    last_status = None
    for attempt in range(1, max_attempts + 1):
        resp = s.get(url, headers={"User-Agent": _UA}, timeout=30, verify=_CA_BUNDLE)
        last_status = getattr(resp, "status_code", None)
        body = getattr(resp, "text", "")
        if _is_valid(last_status, body):
            path.write_text(body, encoding="utf-8")
            if delay:
                time.sleep(_MIN_DELAY_S)
            return FetchResult(vnid=vnid, html=body, source_url=url, from_cache=False, attempts=attempt)
        if delay and attempt < max_attempts:
            time.sleep(delay)
    raise RuntimeError(
        f"NOIP fetch failed for {vnid}: no valid body in {max_attempts} attempts (last status {last_status})"
    )
