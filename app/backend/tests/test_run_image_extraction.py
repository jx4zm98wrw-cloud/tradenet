"""Unit tests for worker.ingest._run_image_extraction's fail-soft contract.

The function MUST return None (not raise) for every known degrade path so
ingest_pdf continues writing trademark rows with logo_path=NULL. A single
bad PDF must not fail the whole ingest job.

After the audit, the function also distinguishes:
  - WARNING-worthy degrades (missing year, missing config file, extractor
    package not importable)
  - ERROR-worthy crashes (unexpected import error, extractor raised
    mid-PDF) — these must log at ERROR with exc_info.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

import pytest

from api.db.models import GazetteType
from worker.ingest import _run_image_extraction


def _install_fake_extractor(monkeypatch: pytest.MonkeyPatch, modify_pdf_impl=None) -> None:
    """Inject a fake `image_extractor` module into sys.modules.

    The worker does a lazy `from image_extractor import ImageExtractor, ImagePaths`
    inside _run_image_extraction, so by the time the import runs the fake is
    already swapped in. monkeypatch auto-reverts after the test so the real
    extractor (or any other test's stub) is untouched.
    """
    fake = types.ModuleType("image_extractor")

    class _ImageExtractor:
        def __init__(self, *a, **k):
            pass

        def _modify_pdf(self, *a, **k):
            if modify_pdf_impl is not None:
                return modify_pdf_impl(*a, **k)
            return None

        def _extract_images(self, *a, **k):
            pass

        def _create_image_link_csv(self, *a, **k):
            pass

    class _ImagePaths:
        def __init__(self, **k):
            pass

    fake.ImageExtractor = _ImageExtractor  # type: ignore[attr-defined]
    fake.ImagePaths = _ImagePaths  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "image_extractor", fake)


def test_missing_year_returns_none_with_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with caplog.at_level(logging.WARNING, logger="worker.ingest"):
        out = _run_image_extraction(
            pdf_path=pdf,
            output_stem="x",
            year=None,
            gazette_type=GazetteType.A,
            data_dir=tmp_path,
        )

    assert out is None
    assert any("no issue_year" in r.getMessage() for r in caplog.records)
    # Known degrade path → no ERROR-level logs.
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


def test_missing_config_returns_none_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No config_image_extractor.yaml in data_dir → degrade gracefully."""
    _install_fake_extractor(monkeypatch)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with caplog.at_level(logging.WARNING, logger="worker.ingest"):
        out = _run_image_extraction(
            pdf_path=pdf,
            output_stem="x",
            year=2026,
            gazette_type=GazetteType.A,
            data_dir=tmp_path,  # no config_image_extractor.yaml here
        )

    assert out is None
    assert any(
        "Missing" in r.getMessage() and "config_image_extractor.yaml" in r.getMessage()
        for r in caplog.records
    )
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


def test_extractor_raises_mid_pdf_logs_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extractor crashes inside _modify_pdf. Audit requires:
    - return None (so ingest_pdf continues)
    - log at ERROR (not WARNING)
    - include exc_info / stack trace
    """

    def _boom(*a, **k):
        raise RuntimeError("extractor crash on page 47")

    _install_fake_extractor(monkeypatch, modify_pdf_impl=_boom)
    (tmp_path / "config_image_extractor.yaml").write_text("{}")
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with caplog.at_level(logging.WARNING, logger="worker.ingest"):
        out = _run_image_extraction(
            pdf_path=pdf,
            output_stem="x",
            year=2026,
            gazette_type=GazetteType.A,
            data_dir=tmp_path,
        )

    assert out is None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "an extractor crash must surface as ERROR, not WARNING"
    assert any("failed mid-PDF" in r.getMessage() for r in errors)
    # exc_info must be attached so the operator gets a traceback.
    assert any(r.exc_info is not None for r in errors)
