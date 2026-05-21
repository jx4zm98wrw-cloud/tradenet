"""WIPO INID markers, regex patterns, CSV column order."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkerConfig:
    code: str
    description: str


MARKERS = [
    MarkerConfig("(111)", "Trademark registration certificate number"),
    MarkerConfig("(116)", "International registration number under Madrid Agreement"),
    MarkerConfig("(141)", "Expiry date of the trademark"),
    MarkerConfig("(151)", "Date of issuance/registration"),
    MarkerConfig("(156)", "Date of renewal for international registration"),
    MarkerConfig("(176)", "Period of validity for renewed international registration"),
    MarkerConfig("(171)", "Period of validity"),
    MarkerConfig("(181)", "Expiry date of trademark certificate"),
    MarkerConfig("(210)", "Application number"),
    MarkerConfig("(220)", "Application submission date"),
    MarkerConfig("(230)", "Exhibition details"),
    MarkerConfig("(300)", "Priority application details"),
    MarkerConfig("(441)", "Publication date of application"),
    MarkerConfig("(450)", "Publication date of certificate"),
    MarkerConfig("(510)", "List of goods/services"),
    MarkerConfig("(511)", "International classification (Nice)"),
    MarkerConfig("(531)", "Classification of figurative elements (Vienna)"),
    MarkerConfig("(540)", "Trademark sample"),
    MarkerConfig("(551)", "Trademark status"),
    MarkerConfig("(591)", "Protected colors"),
    MarkerConfig("(641)", "Number of related application"),
    MarkerConfig("(731)", "Applicant details"),
    MarkerConfig("(732)", "Trademark owner details"),
    MarkerConfig("(740)", "Industrial property representative"),
    MarkerConfig("(822)", "Country of origin details"),
    MarkerConfig("(831)", "Territorial expansion details"),
]

MARKER_CODES = tuple(marker.code for marker in MARKERS)
MARKER_DESCRIPTIONS = {marker.code: marker.description for marker in MARKERS}

PATTERNS = {
    "(111)": r"\(111\)\s*(4-\d+)",
    "(116)": r"\(116\)\s*(\d+)",
    "(141)": r"\(141\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(151)": r"\(151\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(156)": r"\(156\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(176)": r"\(176\)\s*(10\s*n[ãa]m)",
    "(171)": r"\(171\)\s*(10\s*n[ãa]m)",
    "(181)": r"\(181\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(210)": r"\(210\)\s*(4-\d{4}-\d+)",
    "(220)": r"\(220\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(300)": r"\(300\)\s*(\S+\s+\d{2}/\d{2}/\d{4}\s+[A-Z]{2})",
    "(441)": r"\(441\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(450)": r"\(450\)\s*(\d{2}[./]\d{2}[./]\d{4})",
    "(511)": r"\(511\)\s*(.*)",
    "(531)": r"\(531\)\s*((?:[A-Z]?\d+(?:[\.\s]\d+)+(?:;\s*)?)+?)(?=\s*\(\d{3}\)|$)",
    "(540)": r"\(540\)\s*([^\d\.\s,].*)",
    "(551)": r"\(551\)\s*(.*)",
    "(591)": r"\(591\)\s*(.*)",
    "(641)": r"\(641\)\s*(.*)",
    "(731)": r"\(731\)\s*(.*)",
    "(732)": r"\(732\)\s*(.*)",
    "(740)": r"\(740\)\s*(.*)",
    "(822)": r"\(822\)\s*(.*)",
    "(831)": r"\(831\)\s*(.*)",
}

CSV_COLUMNS = [
    "(111)",
    "(116)",
    "(141)",
    "(151)",
    "(156)",
    "(176)",
    "(171)",
    "(181)",
    "(210)",
    "(220)",
    "(230)",
    "(300)",
    "(441)",
    "(450)",
    "(510)",
    "(511)",
    "(531)",
    "(540)",
    "(551)",
    "(591)",
    "(641)",
    "(731)",
    "(732)",
    "(740)",
    "(822)",
    "(831)",
    "Applicant Country Code",
    "Applicant City",
    "IPAgency",
    "Applicant Name",
    "Applicant Address",
    "Total Group",
    "Group Number",
    "Gazette",
    "Month",
    "Year",
    "DateCombined_441_450",
    "Applicant Type",
    "IPAgencyStatus",
]
