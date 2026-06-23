# app/backend/tests/madrid_enrich/test_client_throttle.py
from pathlib import Path

import pytest

from madrid_enrich.client import WipoThrottledError, fetch_raw


class _Resp:
    def __init__(self, status_code, text="<html>ok</html>", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status should not run for handled 429")


class _Session:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, headers=None, timeout=None):
        return self._resp


def test_429_raises_throttled_with_retry_after(tmp_path: Path):
    sess = _Session(_Resp(429, headers={"Retry-After": "12"}))
    with pytest.raises(WipoThrottledError) as ei:
        fetch_raw("123", tmp_path, session=sess, use_cache=False)
    assert ei.value.retry_after == 12.0


def test_200_surfaces_limit_and_remaining(tmp_path: Path):
    sess = _Session(_Resp(200, headers={"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "950"}))
    res = fetch_raw("124", tmp_path, session=sess, use_cache=False)
    assert res.rate_limit == 1000
    assert res.rate_remaining == 950
