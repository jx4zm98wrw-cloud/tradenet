import datetime
from pathlib import Path

from domestic_enrich.derive import DomesticStatus, derive_status
from domestic_enrich.parser import DomesticRecord, parse

FIX = Path(__file__).parent.parent / "fixtures" / "domestic"


def test_numeric_code_maps_to_label():
    rec = DomesticRecord(status_code="1904", grant_date=None)
    st = derive_status(rec)
    assert isinstance(st, DomesticStatus)
    assert st.code == "1904"
    assert st.label
    assert st.is_granted is False


def test_granted_when_grant_date_present():
    rec = DomesticRecord(status_code="1904", grant_date=datetime.date(2025, 1, 1))
    assert derive_status(rec).is_granted is True


def test_granted_when_status_text_says_so():
    rec = DomesticRecord(status_code="Cấp bằng", grant_date=None)
    st = derive_status(rec)
    assert st.is_granted is True
    assert st.label == "Cấp bằng"


def test_unknown_numeric_code_keeps_code_as_label():
    rec = DomesticRecord(status_code="9999")
    st = derive_status(rec)
    assert st.code == "9999"
    assert st.label == "9999"


def test_derive_on_real_granted_fixture():
    rec = parse((FIX / "VN4202416348.html").read_text(encoding="utf-8"))
    assert derive_status(rec).is_granted is True
