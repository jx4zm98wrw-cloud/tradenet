import pytest

from domestic_enrich.client import FetchResult, fetch_raw

_GOOD = "<html><div class='product-form-label'>(541)</div>ok</html>"


class _Resp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
        self.headers = {}


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
