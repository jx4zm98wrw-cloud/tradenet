"""Text helpers: date reformatting, marker line-break injection, colored logging."""

from __future__ import annotations

import logging
import re

from colorama import Fore, Style

from .constants import TrademarkConstants


def reformat_date(date_str: str) -> str:
    try:
        date_str = date_str.replace(".", "/")
        day, month, year = date_str.split("/")
        day = day.zfill(2)
        month = month.zfill(2)
        return f"{month}/{day}/{year}"
    except (ValueError, AttributeError) as e:
        logging.warning(f"{Fore.YELLOW}Failed to reformat date '{date_str}': {e!s}{Style.RESET_ALL}")
        return date_str


class TextProcessor:
    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text.strip())

    @staticmethod
    def add_breaks_before_markers(text: str) -> str:
        for marker in TrademarkConstants.MARKER_CODES:
            if marker in text:
                text = text.replace(marker, f"\n{marker}")
        text = re.sub(r"\(531\)\s*([^\n]*?)\s*\(540\)", r"(531) \1\n(540)", text)
        return text

    @staticmethod
    def add_empty_breaks_before_sections(text: str) -> str:
        if not text:
            return ""
        sections = text.split("\n")
        result = []
        for section in sections:
            if any(marker in section for marker in TrademarkConstants.MARKER_CODES):
                result.extend(["", section])
            else:
                result.append(section)
        return "\n".join(result)


class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        log_color = self.LEVEL_COLORS.get(record.levelname, "")
        message = super().format(record)
        return f"{log_color}{message}{Style.RESET_ALL}"
