import pytest

from domestic_enrich.client import FetchResult, NoipBlockedError, fetch_raw

_GOOD = "<html><div class='product-form-label'>(541)</div>ok</html>"


class _Resp:
    def __init__(self, status_code, text, headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _FlakyTransport:
    """Returns N Apache-500-style bodies, then a valid one."""

    def __init__(self, fails_before_ok: int):
        self.calls = 0
        self.fails_before_ok = fails_before_ok

    def get(self, url, headers=None, timeout=None, verify=None):
        self.calls += 1
        if self.calls <= self.fails_before_ok:
            return _Resp(500, "Internal Server Error")
        return _Resp(200, _GOOD)


def test_retries_until_valid_body(tmp_path):
    t = _FlakyTransport(fails_before_ok=2)
    res = fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False, max_attempts=5, delay=0.0)
    assert isinstance(res, FetchResult)
    assert res.from_cache is False
    assert "product-form-label" in res.html
    assert t.calls == 3


def test_gives_up_after_max_attempts(tmp_path):
    t = _FlakyTransport(fails_before_ok=99)
    with pytest.raises(RuntimeError):
        fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False, max_attempts=3, delay=0.0)
    assert t.calls == 3


def test_uses_cache_without_network(tmp_path):
    (tmp_path / "VN4202600774.html").write_text(_GOOD, encoding="utf-8")
    t = _FlakyTransport(fails_before_ok=99)
    res = fetch_raw("VN4202600774", tmp_path, session=t, use_cache=True)
    assert res.from_cache is True
    assert t.calls == 0


class _BlockTransport:
    """Always returns a block/rate-limit status (403/429)."""

    def __init__(self, status: int, headers=None):
        self.status = status
        self.headers = headers
        self.calls = 0

    def get(self, url, headers=None, timeout=None, verify=None):
        self.calls += 1
        return _Resp(self.status, "Forbidden", headers=self.headers)


@pytest.mark.parametrize("status", [403, 429])
def test_block_status_raises_immediately_without_retry(tmp_path, status):
    # A block is NOT the retryable flaky-500: it must raise on the FIRST attempt
    # so the sweep pauses instead of hammering 10x and escalating to a ban.
    t = _BlockTransport(status)
    with pytest.raises(NoipBlockedError) as ei:
        fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False, max_attempts=10, delay=0.0)
    assert ei.value.status == status
    assert t.calls == 1  # exactly one request — no retries


def test_block_429_parses_retry_after(tmp_path):
    t = _BlockTransport(429, headers={"Retry-After": "120"})
    with pytest.raises(NoipBlockedError) as ei:
        fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False, delay=0.0)
    assert ei.value.retry_after == 120.0


def test_backoff_grows_then_caps_low():
    from domestic_enrich.client import _MAX_BACKOFF_S, _backoff_seconds

    # Early retries grow (catch transient blips fast)...
    assert _backoff_seconds(1, 1.5) == 1.5
    assert _backoff_seconds(2, 1.5) == 3.0
    assert _backoff_seconds(3, 1.5) == 6.0
    # ...then cap LOW so a many-retry flaky mark can't burn minutes.
    assert _backoff_seconds(10, 1.5) == _MAX_BACKOFF_S
    assert _MAX_BACKOFF_S <= 10
