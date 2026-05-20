"""tm_extractor — Vietnamese trademark gazette PDF extraction library.

Usage:
    from tm_extractor import ExtractorConfig, PDFProcessor

    cfg = ExtractorConfig.from_root(Path("/path/to/project"))
    processor = PDFProcessor(cfg)
    processor.process_file(Path("input/A_T1.pdf"))
"""
from .config import ExtractorConfig
from .constants import TrademarkConstants
from .processor import PDFProcessor

__all__ = ["ExtractorConfig", "PDFProcessor", "TrademarkConstants"]
