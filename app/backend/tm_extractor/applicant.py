"""Applicant (731/732) text parsing — split name vs address, first-applicant-only."""
from __future__ import annotations
import logging
import re
from typing import List, Tuple

from colorama import Fore, Style


def parse_applicant_field(applicant_text: str) -> Tuple[List[str], List[str]]:
    applicant_names: List[str] = []
    applicant_addresses: List[str] = []
    if not applicant_text:
        return applicant_names, applicant_addresses
    # Numbered multi-applicant lists "1. NAME1 (CC1) ADDR1 2. NAME2 (CC2) ADDR2".
    # Keep only the first applicant — single row, single applicant by design.
    applicant_text = applicant_text.strip()
    m_num = re.match(r'^\s*1\.\s*(.*?)(?=\s+\d+\.\s|$)', applicant_text, re.DOTALL)
    if m_num:
        applicant_text = m_num.group(1).strip()
    try:
        match = re.match(r'(.+?)\s*\(([A-Z]{2})\)\s*(.+)', applicant_text)
        if match:
            name, _, address = match.groups()
            address = re.split(r'\s+\d+\.\s', address, maxsplit=1)[0]
            applicant_names.append(name.strip())
            applicant_addresses.append(address.strip())
        else:
            applicants = re.split(r'\d+\.\s|\n', applicant_text)
            for applicant in applicants:
                applicant = applicant.strip()
                if not applicant:
                    continue
                parts = applicant.split(',', 1)
                if len(parts) == 2:
                    name, address = parts
                    applicant_names.append(name.strip())
                    applicant_addresses.append(address.strip())
                else:
                    applicant_names.append(applicant.strip())
                    applicant_addresses.append("")
    except Exception as e:
        logging.warning(f"{Fore.YELLOW}Failed to parse applicant text '{applicant_text}': {str(e)}{Style.RESET_ALL}")
        applicant_names.append(applicant_text.strip())
        applicant_addresses.append("")
    return applicant_names, applicant_addresses
