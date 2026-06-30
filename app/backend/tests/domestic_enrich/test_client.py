from pathlib import Path

import pytest

from domestic_enrich.client import FetchResult, NoipBlockedError, fetch_raw

_GOOD = "<html><div class='product-form-label'>(541)</div>ok</html>"

# A real IP VIETNAM render-timing page: HTTP 200 WITH `product-form-label`, but the
# Angular data bindings (`${mk}`, `${repeating.template.ap}`, ...) were served
# before client-side interpolation, so the field values are literal `${...}`
# placeholders. It also contains the page's own JS guard string `indexOf("${")`
# — a bare `${` that must NOT be mistaken for an unrendered binding.
_UNRENDERED_FIXTURE = Path(__file__).parent.parent / "fixtures" / "domestic" / "VN4202448776_unrendered.html"


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


# A real IP VIETNAM 200-skeleton page: HTTP 200 but no `product-form-label` marker —
# IP VIETNAM has no published detail for this id yet. ~2,178 bytes live; shape is what
# matters here.
_SKELETON = "<html><body><div class='wopublish'>no detail</div></body></html>"


class _SkeletonTransport:
    """Always returns HTTP 200 with the not-published skeleton (no marker)."""

    def __init__(self):
        self.calls = 0

    def get(self, url, headers=None, timeout=None, verify=None):
        self.calls += 1
        return _Resp(200, _SKELETON)


def test_200_skeleton_classified_not_found_without_retry(tmp_path):
    # A 200-without-marker is a DEFINITIVE negative, not flaky: it must return
    # immediately as not_found — no retry loop, no RuntimeError — and must NOT be
    # written to the on-disk cache (it has to be re-checked after the backoff
    # window once IP VIETNAM publishes the detail).
    t = _SkeletonTransport()
    res = fetch_raw("VN4202611346", tmp_path, session=t, use_cache=False, max_attempts=10, delay=0.0)
    assert res.outcome == "not_found"
    assert res.from_cache is False
    assert res.attempts == 1
    assert t.calls == 1  # returned on the first attempt — no retries
    assert not (tmp_path / "VN4202611346.html").exists()  # skeleton not cached


def test_valid_body_has_ok_outcome(tmp_path):
    t = _FlakyTransport(fails_before_ok=0)
    res = fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False, delay=0.0)
    assert res.outcome == "ok"


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


class _UnrenderedThenGoodTransport:
    """Returns N unrendered Angular-template bodies (200 + marker but `${...}`
    bindings), then a real rendered detail page."""

    def __init__(self, unrendered_before_ok: int, unrendered_body: str):
        self.calls = 0
        self.unrendered_before_ok = unrendered_before_ok
        self.unrendered_body = unrendered_body

    def get(self, url, headers=None, timeout=None, verify=None):
        self.calls += 1
        if self.calls <= self.unrendered_before_ok:
            return _Resp(200, self.unrendered_body)
        return _Resp(200, _GOOD)


def test_unrendered_template_retried_then_succeeds(tmp_path):
    # A render-timing page (200 + product-form-label but un-interpolated `${...}`)
    # is TRANSIENT, not a real detail: it must be retried like a flaky 5xx, and
    # the unrendered body must NEVER be cached — only the rendered page is.
    body = _UNRENDERED_FIXTURE.read_text(encoding="utf-8")
    t = _UnrenderedThenGoodTransport(unrendered_before_ok=2, unrendered_body=body)
    res = fetch_raw("VN4202448776", tmp_path, session=t, use_cache=False, max_attempts=5, delay=0.0)
    assert res.outcome == "ok"
    assert "${" not in res.html  # the rendered page, not the template
    assert t.calls == 3
    assert (tmp_path / "VN4202448776.html").read_text(encoding="utf-8") == _GOOD


class _AlwaysUnrenderedTransport:
    def __init__(self, unrendered_body: str):
        self.calls = 0
        self.unrendered_body = unrendered_body

    def get(self, url, headers=None, timeout=None, verify=None):
        self.calls += 1
        return _Resp(200, self.unrendered_body)


def test_unrendered_template_gives_up_and_is_never_cached(tmp_path):
    # If the page never renders within max_attempts, fetch_raw raises (so the
    # sweep counts a retryable failure) and writes NOTHING to the on-disk cache.
    body = _UNRENDERED_FIXTURE.read_text(encoding="utf-8")
    t = _AlwaysUnrenderedTransport(body)
    with pytest.raises(RuntimeError):
        fetch_raw("VN4202448776", tmp_path, session=t, use_cache=False, max_attempts=3, delay=0.0)
    assert t.calls == 3  # retried, not returned on the first attempt
    assert not (tmp_path / "VN4202448776.html").exists()


def test_rendered_page_with_js_dollar_literal_not_flagged_unrendered(tmp_path):
    # A genuinely rendered page contains the page's own JS guard string
    # `indexOf("${")` — a bare `${` with no binding name. That must NOT be
    # misread as an unrendered template, or every real page would be rejected.
    rendered = (
        "<html><div class='product-form-label'>(541)</div>"
        "<div class='product-form-details'>VTRAVEL</div>"
        '<script>if (relText.indexOf("${") >= 0) {}</script></html>'
    )
    t = _UnrenderedThenGoodTransport(unrendered_before_ok=0, unrendered_body="")
    # Inline transport returning the rendered page on the first call.
    t.unrendered_body = rendered
    res = fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False, delay=0.0)
    assert res.outcome == "ok"
    assert t.calls == 1  # accepted immediately, no retry


def test_backoff_grows_then_caps_low():
    from domestic_enrich.client import _MAX_BACKOFF_S, _backoff_seconds

    # Early retries grow (catch transient blips fast)...
    assert _backoff_seconds(1, 1.5) == 1.5
    assert _backoff_seconds(2, 1.5) == 3.0
    assert _backoff_seconds(3, 1.5) == 6.0
    # ...then cap LOW so a many-retry flaky mark can't burn minutes.
    assert _backoff_seconds(10, 1.5) == _MAX_BACKOFF_S
    assert _MAX_BACKOFF_S <= 10
