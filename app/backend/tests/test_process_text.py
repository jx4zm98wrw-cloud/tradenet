"""Unit tests for Final_TRADEMARK_image_extractor_refine.PDFProcessor._process_text.

The hybrid line-offset table is the subtlest code in PR #2. The two bugs it
fixes are:
  - Original code placed every marker at the block's bbox top — wrong when a
    block spans many lines (e.g. (732) applicant + address + Vienna codes).
  - A naive per-line fix misses markers fitz splits across separate "line"
    objects at the same y (e.g. "(111)" on one line, "1746424" on the next).

These tests construct fake fitz.Page-like objects (no real PDFs) and assert
that insert_text is called at the correct line y.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Make the standalone extractor (lives at project root) importable.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Final_TRADEMARK_image_extractor_refine import (  # noqa: E402
    PDFProcessor,
    ProcessingPaths,
)


def _processor() -> PDFProcessor:
    paths = ProcessingPaths(
        working_dir=Path("/tmp"),
        input_dir=Path("/tmp"),
        image_dir=Path("/tmp"),
        modified_dir=Path("/tmp"),
        image_link_dir=Path("/tmp"),
    )
    return PDFProcessor(paths, {}, processing_mode="auto")


def _line(y: float, x: float, text: str) -> dict:
    """Build a fitz text_dict line: one span containing `text` at bbox (x, y)."""
    return {
        "bbox": [x, y, x + 100.0, y + 12.0],
        "spans": [{"text": text}],
    }


def _block(lines: list[dict], bbox_y: float = 0.0) -> dict:
    """Build a fitz text_dict block of type 0 (text)."""
    return {
        "type": 0,
        "bbox": [50.0, bbox_y, 550.0, bbox_y + 200.0],
        "lines": lines,
    }


def _page_with_blocks(blocks: list[dict]) -> MagicMock:
    page = MagicMock()
    page.get_text.return_value = {"blocks": blocks}
    return page


def test_marker_on_single_line_placed_at_line_y() -> None:
    """Block whose first line IS the marker: insert at line y == block bbox y."""
    page = _page_with_blocks([_block([_line(74.0, 65.0, "(111) 1746424")], bbox_y=74.0)])
    new_page = MagicMock()

    _processor()._process_text(page, new_page, r"\((?:210|116|111)\)\s*([0-9A-Za-z\-]+)")

    new_page.insert_text.assert_called_once()
    (pos, text) = new_page.insert_text.call_args[0]
    assert text == "(111) 1746424"
    assert pos == (65.0, 74.0)


def test_marker_split_across_lines_at_same_y() -> None:
    """Regression guard: fitz sometimes emits '(111)' and '1746424' as two
    'line' objects at the same y. The hybrid joiner must still produce one
    match at the correct y."""
    page = _page_with_blocks(
        [
            _block(
                [
                    _line(74.0, 65.0, "(111)"),
                    _line(74.0, 110.0, "1746424"),
                ],
                bbox_y=74.0,
            )
        ]
    )
    new_page = MagicMock()

    _processor()._process_text(page, new_page, r"\((?:210|116|111)\)\s*([0-9A-Za-z\-]+)")

    new_page.insert_text.assert_called_once()
    (pos, text) = new_page.insert_text.call_args[0]
    # The match starts at line 0 ("(111)"), so the marker is inserted at line 0's y.
    assert pos[1] == 74.0
    assert "1746424" in text


def test_marker_below_block_top_placed_at_line_y_not_block_top() -> None:
    """The PR #2 bug: a block with non-marker text at the top and the
    (111) marker far below. Markers must be placed at their actual line y,
    not at the block's bbox_y."""
    block = _block(
        [
            _line(194.0, 65.0, "Some applicant address line"),
            _line(220.0, 65.0, "More address text"),
            _line(337.0, 65.0, "(111) 1234567"),  # marker is here
            _line(365.0, 65.0, "More content below"),
        ],
        bbox_y=194.0,  # block top — old code would place marker here
    )
    page = _page_with_blocks([block])
    new_page = MagicMock()

    _processor()._process_text(page, new_page, r"\((?:210|116|111)\)\s*([0-9A-Za-z\-]+)")

    new_page.insert_text.assert_called_once()
    (pos, text) = new_page.insert_text.call_args[0]
    assert pos[1] == 337.0, "marker must be placed at its line y, not block top"
    assert text == "(111) 1234567"


def test_multiple_markers_in_same_block_resolve_to_their_own_lines() -> None:
    """Two markers in different lines of the same block should each be
    placed at their own line's y."""
    block = _block(
        [
            _line(100.0, 65.0, "(111) 1111111"),
            _line(150.0, 65.0, "(111) 2222222"),
        ],
        bbox_y=100.0,
    )
    page = _page_with_blocks([block])
    new_page = MagicMock()

    _processor()._process_text(page, new_page, r"\((?:210|116|111)\)\s*([0-9A-Za-z\-]+)")

    assert new_page.insert_text.call_count == 2
    calls = sorted(new_page.insert_text.call_args_list, key=lambda c: c[0][0][1])
    assert calls[0][0][0] == (65.0, 100.0)
    assert calls[0][0][1] == "(111) 1111111"
    assert calls[1][0][0] == (65.0, 150.0)
    assert calls[1][0][1] == "(111) 2222222"


def test_lines_with_no_match_are_skipped() -> None:
    """Lines whose text doesn't match the regex don't produce insert_text
    calls (and don't shift other markers' positions)."""
    block = _block(
        [
            _line(50.0, 65.0, "Header"),
            _line(74.0, 65.0, "(111) 1746424"),
            _line(120.0, 65.0, "Address"),
        ],
        bbox_y=50.0,
    )
    page = _page_with_blocks([block])
    new_page = MagicMock()

    _processor()._process_text(page, new_page, r"\((?:210|116|111)\)\s*([0-9A-Za-z\-]+)")

    new_page.insert_text.assert_called_once()
    (pos, _text) = new_page.insert_text.call_args[0]
    assert pos == (65.0, 74.0)


def test_non_text_blocks_ignored() -> None:
    """Image blocks (type != 0) must be ignored without errors."""
    blocks = [
        {"type": 1, "bbox": [0, 0, 100, 100], "lines": []},  # image block
        _block([_line(50.0, 65.0, "(210) 4-2025-1")], bbox_y=50.0),
    ]
    page = _page_with_blocks(blocks)
    new_page = MagicMock()

    _processor()._process_text(page, new_page, r"\((?:210|116|111)\)\s*([0-9A-Za-z\-]+)")

    new_page.insert_text.assert_called_once()
    assert new_page.insert_text.call_args[0][0] == (65.0, 50.0)
