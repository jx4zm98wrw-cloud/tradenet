"""Unit tests for `api._applicant_note.strip_registry_note`.

Pure-function tests (no DB): every stripped case is a real IP VIETNAM processing
note observed in the corpus; every spared case is a legitimate leading token that
must NOT be treated as a note.
"""

from __future__ import annotations

import pytest

from api._applicant_note import strip_registry_note

# (input, expected) — leading registry notes that MUST be stripped.
_STRIP_CASES = [
    (
        "(Nhận GCN tại Cục - 0948 456 705)Công ty cổ phần Tập đoàn VGREEN",
        "Công ty cổ phần Tập đoàn VGREEN",
    ),
    # Uppercase gazette variant (no space before the name).
    (
        "(NHẬN GCN TẠI CỤC - 0948 456 705)CÔNG TY CỔ PHẦN TẬP ĐOÀN VGREEN",
        "CÔNG TY CỔ PHẦN TẬP ĐOÀN VGREEN",
    ),
    ("(nhận gcn tại vp2)ABC Co.", "ABC Co."),
    ("(gửi vb vp 2) Some Company Ltd", "Some Company Ltd"),
    ("(nhận gcn tại đ/c khác)Foo", "Foo"),
    ("(có ý kiến người thứ 3)Nguyễn Văn A", "Nguyễn Văn A"),
    ("(ghép cv giục cấp gcn)Bar JSC", "Bar JSC"),
    ("(nhận vbbh tại vp2)Baz", "Baz"),
    ("(có ý kiến loại trừ)Qux", "Qux"),
    # Two leading notes chained.
    ("(nhận gcn tại cục - 0912 345 678)(có ý kiến người thứ 3)RealName", "RealName"),
]

# Inputs that must be returned UNCHANGED (no leading registry note).
_SPARE_CASES = [
    "Công ty cổ phần Tập đoàn VGREEN",  # already clean
    "(INC) Global Holdings",  # legitimate leading suffix — not a note
    "(US) Widget Corporation",  # ISO country code — not a note
    "Nguyễn Văn A",
    "ACME (Vietnam) Co., Ltd",  # parenthetical is mid-string, never touched
]


@pytest.mark.parametrize("raw,expected", _STRIP_CASES)
def test_strips_registry_note(raw: str, expected: str) -> None:
    assert strip_registry_note(raw) == expected


@pytest.mark.parametrize("raw", _SPARE_CASES)
def test_spares_non_notes(raw: str) -> None:
    assert strip_registry_note(raw) == raw


def test_none_and_blank_passthrough() -> None:
    assert strip_registry_note(None) is None
    assert strip_registry_note("") == ""


def test_never_blanks_out_the_whole_name() -> None:
    # A pathological all-note string keeps the original rather than returning "".
    only_note = "(nhận gcn tại cục - 0948 456 705)"
    assert strip_registry_note(only_note) == only_note
