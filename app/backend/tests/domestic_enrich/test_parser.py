from datetime import date
from pathlib import Path

from domestic_enrich.parser import DomesticRecord, has_unrendered_placeholder, parse

FIX = Path(__file__).parent.parent / "fixtures" / "domestic"


def test_has_unrendered_placeholder_flags_template_bindings():
    # A record parsed from an unrendered Angular template carries literal
    # `${...}` bindings in its field values — must be flagged.
    rec = DomesticRecord(mark_text="${mk-l} ${mk}", applicant_name="${repeating.template.ap}")
    assert has_unrendered_placeholder(rec) is True


def test_has_unrendered_placeholder_clears_real_record():
    # The real captured (rendered) fixture must NOT be flagged.
    assert has_unrendered_placeholder(_rec("VN4202600774")) is False


def test_has_unrendered_placeholder_flags_captured_unrendered_fixture():
    # End-to-end: parsing the real captured unrendered page must flag it.
    assert has_unrendered_placeholder(_rec("VN4202448776_unrendered")) is True


def _rec(vnid: str) -> DomesticRecord:
    return parse((FIX / f"{vnid}.html").read_text(encoding="utf-8"))


def test_parses_mark_text_and_type():
    rec = _rec("VN4202600774")
    assert rec.mark_text == "VTRAVEL"
    assert rec.mark_type == "Combined"


def test_parses_application_number():
    rec = _rec("VN4202600774")
    assert rec.application_number == "4-2026-00774"


def test_parses_applicant():
    rec = _rec("VN4202600774")
    assert rec.applicant_name == "Công ty TNHH thương mại du lịch Vtravel"
    assert rec.applicant_address
    assert "Hoàng Diệu" in rec.applicant_address


def test_parses_representative():
    rec = _rec("VN4202600774")
    assert rec.representative
    assert "Tâm Luật" in rec.representative


def test_parses_colors():
    rec = _rec("VN4202600774")
    assert rec.colors == "Nâu vàng nhạt, trắng."


def test_parses_nice_classes_zero_padded():
    rec = _rec("VN4202600774")
    assert rec.nice_classes == ["39"]
    assert all(len(c) == 2 and c.isdigit() for c in rec.nice_classes)


def test_parses_per_class_goods_keyed_by_class():
    rec = _rec("VN4202600774")
    assert rec.goods_services
    assert set(rec.goods_services).issubset(set(rec.nice_classes))
    assert "39" in rec.goods_services
    assert "du lịch" in rec.goods_services["39"]


def test_parses_vienna_codes():
    rec = _rec("VN4202600774")
    assert rec.vienna_codes == ["03.07.07", "03.07.16", "03.07.24"]


def test_parses_dates_and_status():
    rec = _rec("VN4202600774")
    assert rec.filing_date == date(2026, 1, 8)
    assert rec.status_code == "1904"


def test_parses_publication():
    rec = _rec("VN4202600774")
    assert rec.publication_no == "209693"
    assert rec.publication_date == date(2026, 4, 27)


def test_parses_logo_url():
    rec = _rec("VN4202600774")
    assert rec.logo_url
    assert rec.logo_url.endswith("/VN4202600774/logo?noLogo=true")


def test_parses_timeline():
    rec = _rec("VN4202600774")
    assert rec.timeline
    assert rec.timeline[0]["event"] == "Application Filing"
    assert rec.timeline[0]["date"] == "08.01.2026"


def test_grant_date_when_granted():
    rec = _rec("VN4202416348")
    assert rec.grant_date == date(2026, 2, 25)
    assert rec.status_code == "Cấp bằng"


def test_nice_classes_dedup_and_filtered_on_416348():
    rec = _rec("VN4202416348")
    # rel attrs include both "5" and "05"; must collapse to a single "05",
    # all 2-digit, all within 01-45, no duplicates.
    assert all(len(c) == 2 and c.isdigit() and 1 <= int(c) <= 45 for c in rec.nice_classes)
    assert len(rec.nice_classes) == len(set(rec.nice_classes))
    assert "05" in rec.nice_classes


def test_applicant_on_449975_is_personal():
    rec = _rec("VN4202449975")
    assert rec.applicant_name == "Trần Thị Phương Thảo"
    assert "Phú Thọ" in rec.applicant_address


def test_mark_text_on_all_fixtures():
    assert _rec("VN4202416348").mark_text == "ibest"
    assert _rec("VN4202449975").mark_text == "YED"


def test_parser_is_total_on_all_fixtures():
    for f in FIX.glob("VN*.html"):
        rec = parse(f.read_text(encoding="utf-8"))
        assert isinstance(rec, DomesticRecord)
        assert rec.mark_text
