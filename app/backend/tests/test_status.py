from datetime import date

from api._status import derive_status

T = date(2026, 6, 24)


def test_enriched_status_code_verbatim_with_grant():
    assert derive_status("Cấp bằng", date(2024, 12, 9), None, today=T) == ("Cấp bằng", "ok")


def test_enriched_status_code_no_grant_warn():
    assert derive_status("Đang giải quyết", None, None, today=T) == ("Đang giải quyết", "warn")


def test_unenriched_granted():
    assert derive_status(None, date(2023, 1, 2), None, today=T) == ("Granted", "ok")


def test_expired_lapsed():
    assert derive_status(None, None, date(2020, 1, 1), today=T) == ("Lapsed", "mute")


def test_pending_default():
    assert derive_status(None, None, None, today=T) == ("Pending", "warn")


def test_empty_status_code_falls_back():
    assert derive_status("", None, None, today=T) == ("Pending", "warn")
