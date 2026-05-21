"""Load and prepare reference data (cities, company suffixes)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from re import Pattern

from colorama import Fore, Style


def load_cities_by_country(file_path: Path) -> dict[str, set[str]]:
    try:
        with open(file_path, encoding="utf-8") as f:
            cities_dict = json.load(f)
        return {country: set(cities) for country, cities in cities_dict.items()}
    except Exception as e:
        logging.error(f"{Fore.RED}Failed to load cities from {file_path}: {e!s}{Style.RESET_ALL}")
        return {}


def build_city_patterns(cities_by_country: dict[str, set[str]]) -> dict[str, Pattern]:
    """Pre-compile one alternation regex per country. Cities listed longest-first so
    Python's leftmost-first alternation yields the longest match (e.g. "New York"
    beats "York" when both are present).
    """
    patterns: dict[str, Pattern] = {}
    for cc, cities in cities_by_country.items():
        if not cities:
            continue
        ordered = sorted(cities, key=len, reverse=True)
        alt = "|".join(re.escape(c) for c in ordered)
        patterns[cc] = re.compile(r"\b(?:" + alt + r")\b", re.IGNORECASE)
    return patterns


def load_company_suffixes(file_path: Path) -> set[str]:
    try:
        with open(file_path, encoding="utf-8") as f:
            suffixes = json.load(f)
        return set(suffixes)
    except Exception as e:
        logging.error(f"{Fore.RED}Failed to load company suffixes from {file_path}: {e!s}{Style.RESET_ALL}")
        return set()
