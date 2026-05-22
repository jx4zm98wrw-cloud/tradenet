"""Unit tests for worker.ingest._resolve_logo_path.

Covers the priority chain, the (116)-only suffix fallback, and the
identifier allowlist — three behaviors that have each shipped a bug in
this codepath. The function is pure (filesystem only) so the test
materializes a tiny image_root tree under tmp_path.
"""

from __future__ import annotations

from pathlib import Path

from worker.ingest import _resolve_logo_path


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_a_file_resolves_by_210(tmp_path: Path) -> None:
    """A-file row with only (210): resolver finds the matching PNG."""
    subdir = "2026/A_T1_2026"
    _touch(tmp_path / subdir / "4-2025-57333.png")
    out = _resolve_logo_path({"(210)": "4-2025-57333"}, subdir, tmp_path)
    assert out == f"{subdir}/4-2025-57333.png"


def test_b_file_domestic_resolves_by_111(tmp_path: Path) -> None:
    """Regression guard for PR #2: a B-domestic row with only (111) MUST
    resolve. The original resolver skipped (111) entirely, dropping every
    domestic B mark."""
    subdir = "2026/B_T1_2026"
    _touch(tmp_path / subdir / "1233608.png")
    out = _resolve_logo_path({"(111)": "1233608"}, subdir, tmp_path)
    assert out == f"{subdir}/1233608.png"


def test_madrid_resolves_by_116(tmp_path: Path) -> None:
    """Madrid international registration resolves via (116)."""
    subdir = "2026/B_T1_2026"
    _touch(tmp_path / subdir / "1232415.png")
    out = _resolve_logo_path({"(116)": "1232415"}, subdir, tmp_path)
    assert out == f"{subdir}/1232415.png"


def test_priority_order_210_wins_over_111(tmp_path: Path) -> None:
    """When a row has all three markers and PNGs exist for each, (210) wins."""
    subdir = "2026/X"
    _touch(tmp_path / subdir / "4-2025-99999.png")  # (210)
    _touch(tmp_path / subdir / "1234567.png")  # (111)
    _touch(tmp_path / subdir / "0987654.png")  # (116)
    out = _resolve_logo_path(
        {"(210)": "4-2025-99999", "(111)": "1234567", "(116)": "0987654"},
        subdir,
        tmp_path,
    )
    assert out == f"{subdir}/4-2025-99999.png"


def test_madrid_letter_suffix_variant(tmp_path: Path) -> None:
    """WIPO Madrid modifications publish suffix variants: base ID 0181946
    matches 0181946A.png on disk."""
    subdir = "2026/B_T1_2026"
    _touch(tmp_path / subdir / "0181946A.png")  # NOT 0181946.png
    out = _resolve_logo_path({"(116)": "0181946"}, subdir, tmp_path)
    assert out == f"{subdir}/0181946A.png"


def test_suffix_fallback_only_for_madrid(tmp_path: Path) -> None:
    """An A-file (210)=1234 must NOT match an unrelated 1234A.png that
    happens to live in the same directory. The suffix fallback is a
    Madrid convention; misapplying it to (210) or (111) would assign the
    wrong PNG to the row."""
    subdir = "2026/A_T1_2026"
    _touch(tmp_path / subdir / "4-2025-99999A.png")  # would be wrong match
    out = _resolve_logo_path({"(210)": "4-2025-99999"}, subdir, tmp_path)
    assert out is None

    _touch(tmp_path / subdir / "1234567B.png")
    out = _resolve_logo_path({"(111)": "1234567"}, subdir, tmp_path)
    assert out is None


def test_no_png_returns_none(tmp_path: Path) -> None:
    subdir = "2026/A_T1_2026"
    (tmp_path / subdir).mkdir(parents=True)
    out = _resolve_logo_path({"(210)": "4-2025-57333"}, subdir, tmp_path)
    assert out is None


def test_empty_and_whitespace_identifier_falls_through(tmp_path: Path) -> None:
    subdir = "2026/X"
    _touch(tmp_path / subdir / "9999.png")
    # (210) is whitespace, (111) is empty → resolver must fall through to (116).
    out = _resolve_logo_path(
        {"(210)": "   ", "(111)": "", "(116)": "9999"},
        subdir,
        tmp_path,
    )
    assert out == f"{subdir}/9999.png"


def test_path_traversal_identifier_rejected(tmp_path: Path) -> None:
    """A crafted PDF with `../../etc/passwd`-style content in a marker
    must NOT be used as a filesystem path. Even if the file existed,
    the allowlist rejects the identifier before any filesystem touch."""
    subdir = "2026/X"
    # Create a file that the malicious resolver could find IF unchecked.
    _touch(tmp_path / "evil.png")
    out = _resolve_logo_path({"(210)": "../evil"}, subdir, tmp_path)
    assert out is None

    out = _resolve_logo_path({"(210)": "id/with/slashes"}, subdir, tmp_path)
    assert out is None

    out = _resolve_logo_path({"(210)": "id with spaces"}, subdir, tmp_path)
    assert out is None


def test_no_matching_marker_returns_none(tmp_path: Path) -> None:
    """Section dict with markers we don't look up returns None cleanly."""
    out = _resolve_logo_path({"(540)": "some wordmark"}, "subdir", tmp_path)
    assert out is None
