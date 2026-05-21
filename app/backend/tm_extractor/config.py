"""Configuration for the trademark extractor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractorConfig:
    """Paths the extractor reads from / writes to.

    `data_dir` must contain `cities_by_country.json`, `company_suffixes.json`, and
    optionally `cities_overrides.json`. The other directories are created on demand.
    """

    data_dir: Path
    input_dir: Path
    output_dir: Path
    log_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> ExtractorConfig:
        """Build config from a single project root that contains all subfolders."""
        root = Path(root).resolve()
        return cls(
            data_dir=root,
            input_dir=root / "input",
            output_dir=root / "csv",
            log_dir=root / "log",
        )

    @property
    def cities_file(self) -> Path:
        return self.data_dir / "cities_by_country.json"

    @property
    def company_suffixes_file(self) -> Path:
        return self.data_dir / "company_suffixes.json"

    def ensure_dirs(self) -> None:
        for d in (self.input_dir, self.output_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)
