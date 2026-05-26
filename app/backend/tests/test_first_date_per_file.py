"""Regression test for the first_date cross-file leak (audit finding H7).

Before the fix, `PDFProcessor.first_date` was instance state — initialized
once in __init__, reset at the top of extract_records() and process_file()
but NOT inside process_sections() itself. A caller that invoked
process_sections() directly across multiple files inherited the FIRST file's
(441)/(450) publication date in every subsequent file's date columns.

The worker correctly went through extract_records(), so production was safe.
The bomb was latent: any future caller that touched process_sections()
directly (or any test that did) would silently corrupt date fields.

After the fix, first_date is a local variable inside process_sections() —
per-call state, no API change required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tm_extractor import ExtractorConfig, PDFProcessor


@pytest.fixture
def processor() -> PDFProcessor:
    """Real processor backed by the project's data files (cities + suffixes JSON)."""
    repo_root = Path(__file__).resolve().parents[3]
    config = ExtractorConfig.from_root(repo_root)
    return PDFProcessor(config)


def _minimal_a_section(date_str: str | None) -> list[tuple[int, str]]:
    """Synthetic page_lines for one A-file section, optionally with a (441) date.

    The line ordering mirrors what `extract_text_from_pdf` would emit after
    the column-aware extractor + marker line-breaker has done its work.
    """
    lines: list[tuple[int, str]] = [
        (1, "(210) 4-2025-00001"),
        (1, "(220) 01/01/2025"),
    ]
    if date_str is not None:
        lines.append((1, f"(441) {date_str}"))
    lines.append((1, "(540) HELLOMARK"))
    lines.append((1, "(731) Some Applicant CO., LTD (US) 100 Main St"))
    return lines


def test_first_date_does_not_leak_across_process_sections_calls(
    processor: PDFProcessor,
) -> None:
    """Call process_sections directly for two files. The second file has no
    (441)/(450) date — its sections must NOT inherit the first file's date.

    BUG (pre-fix): self.first_date persists across calls. File B's section
    gets file A's date in DateCombined_441_450.

    FIX: first_date is local to process_sections. File B starts fresh.
    """
    file_a_lines = _minimal_a_section("15/01/2025")
    file_b_lines = _minimal_a_section(None)

    sections_a = list(processor.process_sections(file_a_lines, Path("/tmp/A_first.pdf")))
    sections_b = list(processor.process_sections(file_b_lines, Path("/tmp/A_second.pdf")))

    # Sanity: each call produced exactly one section.
    assert len(sections_a) == 1, f"expected 1 section in file A, got {len(sections_a)}"
    assert len(sections_b) == 1, f"expected 1 section in file B, got {len(sections_b)}"

    # File A should carry its own date.
    assert sections_a[0]["DateCombined_441_450"], (
        f"file A should have a non-empty DateCombined_441_450, got "
        f"{sections_a[0]['DateCombined_441_450']!r}"
    )

    # File B has no (441)/(450) — the date field MUST be empty.
    # Pre-fix this assertion fails: file B inherits file A's date.
    assert sections_b[0]["DateCombined_441_450"] == "", (
        f"file B has no (441)/(450) marker; DateCombined_441_450 must be empty "
        f"but was {sections_b[0]['DateCombined_441_450']!r} — first_date leaked "
        f"from a previous process_sections() call"
    )
    assert sections_b[0]["Month"] == ""
    assert sections_b[0]["Year"] == ""
