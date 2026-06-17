from datetime import date
from pathlib import Path

from madrid_enrich.parser import parse

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"


def _rec():
    return parse(FIXTURE.read_text(encoding="utf-8"))


def test_parses_bibliographic_scalars():
    r = _rec()
    assert r.mark_text == "Clalen"
    assert r.holder_name == "Interojo Inc."
    assert r.holder_country == "KR"
    assert "Corporation" in (r.holder_legal_status or "")
    assert "K IP & LAW FIRM" in (r.representative or "")
    assert r.language == "English"


def test_parses_dates_and_classes():
    r = _rec()
    assert r.registration_date == date(2015, 6, 26)
    assert r.expiration_date == date(2035, 6, 26)  # post-renewal value
    assert r.nice_classes == ["09"]


def test_effective_designated_countries_includes_vn_and_subsequent():
    r = _rec()
    # original IN/PH/SG/VN + subsequent EG/IR/RU (and MA/PK in the 832 set)
    for cc in ("VN", "IN", "PH", "SG", "EG", "IR", "RU"):
        assert cc in r.designated_countries


def test_transaction_history_has_vn_grant_and_renewal():
    r = _rec()
    types = [e["type"] for e in r.transaction_history]
    assert any("International Registration" in t for t in types)
    assert any("Renewal" in t for t in types)
    vn_grants = [
        e
        for e in r.transaction_history
        if "grant of protection" in e["type"].lower() and "VN" in (e.get("parties") or [])
    ]
    assert vn_grants and vn_grants[0]["date"] == "2019-05-02"


def test_designation_status_per_country():
    r = _rec()
    assert r.designation_status["VN"]["status"] == "granted"
    assert r.designation_status["VN"]["date"] == "2019-05-02"
    # IR is in designated_countries (subsequent designation) but has no
    # grant/refusal event of its own, so it is pending. (MA *does* have a grant
    # in this fixture, so the spec's example country was swapped for IR.)
    assert r.designation_status["IR"]["status"] == "pending"


def test_old_record_with_9sexies_designations_includes_vn():
    from madrid_enrich.parser import parse
    from pathlib import Path

    html = (Path(__file__).parent.parent / "fixtures" / "madrid" / "0183259.html").read_text(
        encoding="utf-8"
    )
    r = parse(html)
    assert "VN" in r.designated_countries
    from madrid_enrich.derive import derive_vn

    assert derive_vn(r).designated is True
