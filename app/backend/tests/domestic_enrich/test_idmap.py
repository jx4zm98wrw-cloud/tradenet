import pytest

from domestic_enrich.idmap import appno_to_vnid


@pytest.mark.parametrize(
    "appno, expected",
    [
        ("4-2026-18514", "VN4202618514"),
        ("4-2024-16348", "VN4202416348"),
        ("VN-4-2026-18514", "VN4202618514"),   # already-prefixed, dashed
        ("VN4202618514", "VN4202618514"),       # already canonical
        ("  4-2026-18514  ", "VN4202618514"),   # surrounding whitespace
    ],
)
def test_appno_to_vnid_maps_known_formats(appno, expected):
    assert appno_to_vnid(appno) == expected


@pytest.mark.parametrize("bad", ["", None, "   ", "garbage", "4--", "4-2026-"])
def test_appno_to_vnid_rejects_unmappable(bad):
    assert appno_to_vnid(bad) is None
