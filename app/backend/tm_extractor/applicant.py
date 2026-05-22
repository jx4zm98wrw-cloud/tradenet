"""Applicant (731/732) text parsing — split name vs address, first-applicant-only."""

from __future__ import annotations

import logging
import re

from colorama import Fore, Style

from .constants import TrademarkConstants


def parse_applicant_field(applicant_text: str) -> tuple[list[str], list[str]]:
    applicant_names: list[str] = []
    applicant_addresses: list[str] = []
    if not applicant_text:
        return applicant_names, applicant_addresses
    # Numbered multi-applicant lists "1. NAME1 (CC1) ADDR1 2. NAME2 (CC2) ADDR2".
    # Keep only the first applicant — single row, single applicant by design.
    applicant_text = applicant_text.strip()
    m_num = re.match(r"^\s*1\.\s*(.*?)(?=\s+\d+\.\s|$)", applicant_text, re.DOTALL)
    if m_num:
        applicant_text = m_num.group(1).strip()
    try:
        # Split name vs address at the first VALID ISO 3166-1 alpha-2 code.
        # Matching the first parenthesized "(XX)" catches city abbreviations
        # like (GZ) Guangzhou or (MI) Milan embedded in company names,
        # truncating the name and leaking it into the address. Mirror the
        # valid-code filter that processor.extract_applicant_details uses
        # for the country-code field so both fields stay consistent.
        valid_match = next(
            (
                m
                for m in re.finditer(r"\(([A-Z]{2})\)", applicant_text)
                if m.group(1) in TrademarkConstants.COUNTRY_CODES
            ),
            None,
        )
        if valid_match:
            name = applicant_text[: valid_match.start()].rstrip()
            address = applicant_text[valid_match.end() :].lstrip()
            address = re.split(r"\s+\d+\.\s", address, maxsplit=1)[0]
            applicant_names.append(name)
            applicant_addresses.append(address.strip())
        else:
            applicants = re.split(r"\d+\.\s|\n", applicant_text)
            for applicant in applicants:
                applicant = applicant.strip()
                if not applicant:
                    continue
                parts = applicant.split(",", 1)
                if len(parts) == 2:
                    name, address = parts
                    applicant_names.append(name.strip())
                    applicant_addresses.append(address.strip())
                else:
                    applicant_names.append(applicant.strip())
                    applicant_addresses.append("")
    except Exception as e:
        logging.warning(
            f"{Fore.YELLOW}Failed to parse applicant text '{applicant_text}': {e!s}{Style.RESET_ALL}"
        )
        applicant_names.append(applicant_text.strip())
        applicant_addresses.append("")
    return applicant_names, applicant_addresses
