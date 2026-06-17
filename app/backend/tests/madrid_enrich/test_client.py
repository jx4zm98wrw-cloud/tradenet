from madrid_enrich.client import URL_TEMPLATE, FetchResult, fetch_raw


def test_url_template():
    assert URL_TEMPLATE.format(irn="1266721").endswith("showData.jsp?ID=ROM.1266721")


def test_cache_hit_skips_network(tmp_path, monkeypatch):
    cached = tmp_path / "1266721.html"
    cached.write_text("<html>cached</html>", encoding="utf-8")

    def _boom(*a, **k):  # network must NOT be called on a cache hit
        raise AssertionError("network called despite cache hit")

    monkeypatch.setattr("madrid_enrich.client._http_get", _boom)
    res = fetch_raw("1266721", cache_dir=tmp_path)
    assert isinstance(res, FetchResult)
    assert res.html == "<html>cached</html>"
    assert res.from_cache is True


def test_network_then_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "madrid_enrich.client._http_get",
        lambda url, session=None: ("<html>fresh</html>", {"X-RateLimit-Remaining": "999"}),
    )
    monkeypatch.setattr("madrid_enrich.client.time.sleep", lambda *_: None)
    res = fetch_raw("999999", cache_dir=tmp_path)
    assert res.html == "<html>fresh</html>" and res.from_cache is False
    assert (tmp_path / "999999.html").read_text() == "<html>fresh</html>"
