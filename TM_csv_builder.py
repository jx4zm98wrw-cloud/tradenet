"""TM_csv_builder — Vietnamese trademark gazette PDF → CSV extractor.

This file is now a thin CLI wrapper. The library lives in
`app/backend/tm_extractor/`. The full monolithic version is preserved as
`TM_csv_builder_legacy.py` for byte-level reference.

Run:
    python3 TM_csv_builder.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app" / "backend"))

from tm_extractor.cli import run

if __name__ == "__main__":
    run(ROOT)
