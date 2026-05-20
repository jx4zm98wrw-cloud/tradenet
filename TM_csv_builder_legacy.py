"""
This script is used to build the CSV file from the PDF files.
Purpose of the Code

This Python program is designed to extract trademark information from PDF documents, specifically trademark gazettes or bulletins. 
It processes these documents, extracts structured data about trademarks, and outputs this information to CSV files for further analysis.

 Main Components and Functionality

 1. Project Structure

The code establishes a working directory structure with several subfolders:
- `input`: Where PDF files containing trademark information are stored
- `csv`: Where extracted data is saved as CSV files
- `log`: Where processing logs are stored

It also references external data files:
- `cities_by_country.json`: A mapping of cities to their respective countries
- `company_suffixes.json`: A list of common company suffixes used for entity classification

 2. Trademark Data Processing

The core functionality revolves around extracting and processing standardized trademark information. 
The code uses WIPO (World Intellectual Property Organization) standard codes, known as "INID codes" 
(Internationally agreed Numbers for the Identification of bibliographic Data), 
which are enclosed in parentheses like "(111)" or "(540)".

These codes represent specific pieces of information about a trademark:
- (111): Trademark registration certificate number
- (540): Trademark sample/representation
- (731)/(732): Applicant/trademark owner details
- (511): International classification of goods/services

And many others (the code handles 26 different information fields).

 3. PDF Text Extraction

The program uses the `pdfplumber` library to extract text from PDF files. It processes each page of a PDF, 
extracts the text, and performs initial cleaning and structuring before further analysis.

 4. Text Processing and Pattern Matching

The code employs extensive regular expression pattern matching to identify and extract trademark information. It's designed to handle:
- The specific format of trademark bulletins
- Multiple trademark entries in a single document
- Continuation of information across multiple lines
- Various date formats and standardization

 5. Entity Classification

The code attempts to classify trademark applicants by:
- Extracting country codes from applicant information
- Determining if the applicant is a company or individual
- Identifying cities associated with applicants
- Tracking whether applications are submitted via intellectual property agencies

 6. Parallel Processing

The code uses Python's `ThreadPoolExecutor` to process multiple PDF files concurrently, 
improving efficiency when dealing with multiple documents.

 7. User Interface

A simple command-line interface allows users to:
- View available PDF files in the input directory
- Choose to process all PDFs or select specific ones
- Monitor processing progress via console output and logs

 8. Logging and Error Handling

The code implements comprehensive logging with:
- Color-coded console output for different message types (info, warning, error)
- Rotating file logs for persistent record-keeping
- Exception handling to prevent crashes and report issues

 Process Flow

1. Initialization: The program sets up directories, loads reference data, and configures logging.
2. User Selection: The user selects which PDF files to process.
3. PDF Processing: For each selected PDF:
   - Text is extracted page by page
   - Lines are processed to identify trademark entries
   - Each line is analyzed to extract relevant information based on INID codes
   - Information is accumulated and structured into complete trademark records
4. Data Transformation: 
   - Dates are standardized to a consistent format
   - Applicant information is parsed to extract names, addresses, and country codes
   - Entity types are classified (company vs. individual)
   - Additional metadata like gazette type (A or B) is added
5. Output Generation: The structured data is converted to a Pandas DataFrame and saved as a CSV file with headers that describe the meaning of each column.

 Key Technical Aspects

 Regular Expression Usage
The code heavily relies on regular expressions to extract structured data from text. 
It uses both fixed patterns for well-defined fields and more flexible patterns for variable-format fields.

 State Machine Approach
The trademark extraction process works like a state machine, tracking which information field is currently being 
accumulated and switching between different accumulation modes as markers are encountered.

 Error Tolerance
The code is designed to handle imperfect input data, with various fallback mechanisms when expected patterns aren't found.

 Performance Optimization
The code includes performance monitoring and optimization techniques:
- Progress tracking with `tqdm`
- Timing of slow operations
- Warning for performance bottlenecks

 Specific Features

1. Date Standardization: Converts various date formats to MM/DD/YYYY format
2. Applicant Type Classification: Determines if an applicant is a company or individual based on name patterns
3. Gazette Type Recognition: Identifies if a document is type A or B (likely based on publication section)
4. Trademark Classification: Extracts Nice Classification codes for trademark categories
5. Multi-section Handling: Handles continued text across multiple lines
6. Agency Status: Tracks whether applications were submitted through an IP agency

This code represents a sophisticated document processing system specifically tailored for trademark documents,
with careful attention to the specialized format and structure of official trademark publications.
"""
"""
 Analysis of the PDF Trademark Processing Code

This Python code implements a sophisticated system for extracting and processing trademark information from PDF files. 
Here's a comprehensive analysis of what it does and how it works:

 Core Purpose

The code extracts structured trademark information from PDF documents, 
specifically focusing on trademark registration data marked with standardized codes (like "(111)" for registration numbers, 
"(540)" for trademark samples, etc.). After extraction, it processes and organizes this data into CSV files for further analysis.

 Main Components and Workflow

1. Directory Setup: The code establishes a working directory structure with input, CSV output, and log folders.

2. External Data Loading: The system loads supporting data from JSON files:
   - Cities organized by country codes
   - Company name suffixes for entity classification

3. PDF Processing Pipeline:
   - PDF text extraction using pdfplumber
   - Text cleaning and preprocessing
   - Identification of trademark sections using marker codes
   - Structured data extraction using regular expressions
   - Classification of applicant types (company vs. personal)
   - Output of processed data to CSV files

4. Multi-threading Support: The code allows for parallel processing of multiple PDF files, though the default is set to a single worker.

5. User Interface: A simple console interface lets users choose to process all PDFs or select specific ones from the input folder.

 Key Classes and Their Functions

 `TrademarkConstants`
Serves as a central repository for all reference data including:
- Marker codes and their descriptions (e.g., "(111)" for "Trademark registration certificate number")
- Regular expression patterns for extracting data
- CSV column definitions
- Country codes and their full names
- External data references for cities and company suffixes

 `TextProcessor`
Handles text manipulation tasks:
- Cleaning and normalizing extracted text
- Adding appropriate breaks before marker codes
- Formatting text for better parsing

 `PDFProcessor`
The central processing engine that:
1. Extracts raw text from PDFs
2. Processes the text into logical sections based on marker codes
3. Extracts relevant information using regular expressions
4. Parses complex fields like applicant information
5. Classifies entities and adds metadata
6. Creates CSV output with all processed information

 `UserInterface`
Provides a simple command-line interface for file selection.

 Special Features

1. Robust Error Handling: Comprehensive try-except blocks and logging throughout the code.

2. Colored Console Output: Uses colorama to provide color-coded console output for better visibility of different message types.

3. Detailed Logging: Maintains rotating log files with timestamps and severity levels.

4. Progress Tracking: Implements tqdm progress bars for visual feedback during lengthy operations.

5. Smart Data Extraction:
   - Date reformatting for consistency
   - Intelligent parsing of applicant information
   - Extraction of country codes and cities
   - Classification of applicant types (personal vs. company)
   - Group number identification and counting

6. Data Validation: Includes checks to ensure data integrity, like validating trademark sample fields.

 Requirements

To run this code, you would need:

1. Python Libraries:
   - pdfplumber: For PDF text extraction
   - pandas: For data manipulation and CSV creation
   - numpy: For numerical operations
   - colorama: For colored console output
   - tqdm: For progress bars
   - concurrent.futures: For parallel processing

2. External Data Files:
   - cities_by_country.json: Contains city names organized by country codes
   - company_suffixes.json: Contains common business entity suffixes for classification

3. Directory Structure:
   - An input folder containing PDF files to process
   - Output directories for CSV files and logs

 Processing Logic

The core of the system lies in how it processes PDF pages:

1. It first extracts all text from the PDF, adding appropriate line breaks.
2. It then iteratively processes the text line by line, identifying marker codes.
3. When it finds a start marker (like "(210)" for type A or "(111)"/"(116)" for type B), it begins a new trademark section.
4. It accumulates data for complex fields like trademark descriptions "(540)" and classifications "(511)" across multiple lines.
5. Once a complete section is processed, it extracts additional information like applicant details and computes metadata.
6. Finally, it outputs all sections as rows in a CSV file, with properly labeled columns.

 Design Patterns and Techniques

The code utilizes several effective design patterns:

1. Data Class Pattern: Using `@dataclass` for `MarkerConfig` objects
2. Singleton Pattern: For constants and configuration
3. Generator Pattern: For efficiently yielding trademark sections
4. Strategy Pattern: For text processing operations
5. Factory Method Pattern: For creating and configuring log handlers

 Strengths and Challenges

 Strengths:
- Comprehensive error handling and logging
- Modular design with clear separation of concerns
- Detailed progress reporting
- Intelligent data extraction and processing
- User-friendly interface with colored output

 Potential Challenges:
- The code is heavily dependent on specific PDF formatting
- Complex regex patterns may need maintenance as document formats evolve
- Memory usage could be high for large PDFs due to accumulation of all page texts
- Limited parallelism (default is single worker)

Overall, this is a sophisticated data extraction and processing system specifically designed for trademark registration documents, 
with robust error handling and a focus on data quality and user feedback.
"""
import os
import re
import logging
import logging.handlers
from dataclasses import dataclass
from typing import List, Dict, Optional, Generator, Tuple, Union, Set
import pandas as pd
import numpy as np
from pathlib import Path
import pdfplumber
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import time
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Define working directory and subfolders
WORKING_DIR = Path(__file__).resolve().parent
INPUT_FOLDER = WORKING_DIR / "input"
CSV_FOLDER = WORKING_DIR / "csv"
LOG_FOLDER = WORKING_DIR / "log"
CITIES_FILE = WORKING_DIR / "cities_by_country.json"
COMPANY_SUFFIXES_FILE = WORKING_DIR / "company_suffixes.json"

# Ensure directories exist
for folder in [INPUT_FOLDER, CSV_FOLDER, LOG_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)

# Load external JSON files
def load_cities_by_country(file_path: Path) -> Dict[str, Set[str]]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            cities_dict = json.load(f)
        return {country: set(cities) for country, cities in cities_dict.items()}
    except Exception as e:
        logging.error(f"{Fore.RED}Failed to load cities from {file_path}: {str(e)}{Style.RESET_ALL}")
        return {}

def build_city_patterns(cities_by_country: Dict[str, Set[str]]) -> Dict[str, "re.Pattern"]:
    """Pre-compile one alternation regex per country. Cities listed longest-first so
    Python's leftmost-first alternation yields the longest match (e.g. "New York"
    beats "York" when both are present)."""
    patterns: Dict[str, "re.Pattern"] = {}
    for cc, cities in cities_by_country.items():
        if not cities: continue
        ordered = sorted(cities, key=len, reverse=True)
        alt = "|".join(re.escape(c) for c in ordered)
        patterns[cc] = re.compile(r'\b(?:' + alt + r')\b', re.IGNORECASE)
    return patterns

def load_company_suffixes(file_path: Path) -> Set[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            suffixes = json.load(f)
        return set(suffixes)
    except Exception as e:
        logging.error(f"{Fore.RED}Failed to load company suffixes from {file_path}: {str(e)}{Style.RESET_ALL}")
        return set()

# Date reformatting function
def reformat_date(date_str: str) -> str:
    try:
        date_str = date_str.replace('.', '/')
        day, month, year = date_str.split('/')
        day = day.zfill(2)
        month = month.zfill(2)
        return f"{month}/{day}/{year}"
    except (ValueError, AttributeError) as e:
        logging.warning(f"{Fore.YELLOW}Failed to reformat date '{date_str}': {str(e)}{Style.RESET_ALL}")
        return date_str

@dataclass(frozen=True)
class MarkerConfig:
    code: str
    description: str

class TrademarkConstants:
    MARKERS = [
        MarkerConfig('(111)', 'Trademark registration certificate number'),
        MarkerConfig('(116)', 'International registration number under Madrid Agreement'),
        MarkerConfig('(141)', 'Expiry date of the trademark'),
        MarkerConfig('(151)', 'Date of issuance/registration'),
        MarkerConfig('(156)', 'Date of renewal for international registration'),
        MarkerConfig('(176)', 'Period of validity for renewed international registration'),
        MarkerConfig('(171)', 'Period of validity'),
        MarkerConfig('(181)', 'Expiry date of trademark certificate'),
        MarkerConfig('(210)', 'Application number'),
        MarkerConfig('(220)', 'Application submission date'),
        MarkerConfig('(230)', 'Exhibition details'),
        MarkerConfig('(300)', 'Priority application details'),
        MarkerConfig('(441)', 'Publication date of application'),
        MarkerConfig('(450)', 'Publication date of certificate'),
        MarkerConfig('(510)', 'List of goods/services'),
        MarkerConfig('(511)', 'International classification (Nice)'),
        MarkerConfig('(531)', 'Classification of figurative elements (Vienna)'),
        MarkerConfig('(540)', 'Trademark sample'),
        MarkerConfig('(551)', 'Trademark status'),
        MarkerConfig('(591)', 'Protected colors'),
        MarkerConfig('(641)', 'Number of related application'),
        MarkerConfig('(731)', 'Applicant details'),
        MarkerConfig('(732)', 'Trademark owner details'),
        MarkerConfig('(740)', 'Industrial property representative'),
        MarkerConfig('(822)', 'Country of origin details'),
        MarkerConfig('(831)', 'Territorial expansion details')
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
        # "(531)": r"\(531\)\s*([\d\.\s,;A-Za-z]+)",  # Specific to Vienna codes
        "(531)": r"\(531\)\s*((?:[A-Z]?\d+(?:[\.\s]\d+)+(?:;\s*)?)+?)(?=\s*\(\d{3}\)|$)",  # Non-greedy + lookahead to stop at next marker
        "(540)": r"\(540\)\s*([^\d\.\s,].*)",  # Exclude numeric patterns
        "(551)": r"\(551\)\s*(.*)",
        "(591)": r"\(591\)\s*(.*)",
        "(641)": r"\(641\)\s*(.*)",
        "(731)": r"\(731\)\s*(.*)",
        "(732)": r"\(732\)\s*(.*)",
        "(740)": r"\(740\)\s*(.*)",
        "(822)": r"\(822\)\s*(.*)",
        "(831)": r"\(831\)\s*(.*)"
    }
    
    CSV_COLUMNS = [
        "(111)", "(116)", "(141)", "(151)", "(156)", "(176)", "(171)", "(181)",
        "(210)", "(220)", "(230)", "(300)", "(441)", "(450)", "(510)", "(511)",
        "(531)", "(540)", "(551)", "(591)", "(641)", "(731)", "(732)", "(740)",
        "(822)", "(831)", "Applicant Country Code", "Applicant City", "IPAgency",
        "Applicant Name", "Applicant Address",
        "Total Group", "Group Number", "Gazette",
        "Month", "Year", "DateCombined_441_450",
        "Applicant Type", "IPAgencyStatus"
    ]
    
    COUNTRY_CODES = {
        # A
        "AD": "Andorra",
        "AE": "United Arab Emirates",
        "AF": "Afghanistan",
        "AG": "Antigua and Barbuda",
        "AI": "Anguilla",
        "AL": "Albania",
        "AM": "Armenia",
        "AO": "Angola",
        "AQ": "Antarctica",
        "AR": "Argentina",
        "AS": "American Samoa",
        "AT": "Austria",
        "AU": "Australia",
        "AW": "Aruba",
        "AX": "Åland Islands",
        "AZ": "Azerbaijan",
        
        # B
        "BA": "Bosnia and Herzegovina",
        "BB": "Barbados",
        "BD": "Bangladesh",
        "BE": "Belgium",
        "BF": "Burkina Faso",
        "BG": "Bulgaria",
        "BH": "Bahrain",
        "BI": "Burundi",
        "BJ": "Benin",
        "BL": "Saint Barthélemy",
        "BM": "Bermuda",
        "BN": "Brunei Darussalam",
        "BO": "Bolivia",
        "BQ": "Bonaire, Sint Eustatius and Saba",
        "BR": "Brazil",
        "BS": "Bahamas",
        "BT": "Bhutan",
        "BV": "Bouvet Island",
        "BW": "Botswana",
        "BY": "Belarus",
        "BZ": "Belize",
        
        # C
        "CA": "Canada",
        "CC": "Cocos (Keeling) Islands",
        "CD": "Congo, Democratic Republic of the",
        "CF": "Central African Republic",
        "CG": "Congo",
        "CH": "Switzerland",
        "CI": "Côte d'Ivoire",
        "CK": "Cook Islands",
        "CL": "Chile",
        "CM": "Cameroon",
        "CN": "China",
        "CO": "Colombia",
        "CR": "Costa Rica",
        "CU": "Cuba",
        "CV": "Cabo Verde",
        "CW": "Curaçao",
        "CX": "Christmas Island",
        "CY": "Cyprus",
        "CZ": "Czechia",
        
        # D
        "DE": "Germany",
        "DJ": "Djibouti",
        "DK": "Denmark",
        "DM": "Dominica",
        "DO": "Dominican Republic",
        "DZ": "Algeria",
        
        # E
        "EC": "Ecuador",
        "EE": "Estonia",
        "EG": "Egypt",
        "EH": "Western Sahara",
        "ER": "Eritrea",
        "ES": "Spain",
        "ET": "Ethiopia",
        
        # F
        "FI": "Finland",
        "FJ": "Fiji",
        "FK": "Falkland Islands (Malvinas)",
        "FM": "Micronesia",
        "FO": "Faroe Islands",
        "FR": "France",
        
        # G
        "GA": "Gabon",
        "GB": "United Kingdom",
        "GD": "Grenada",
        "GE": "Georgia",
        "GF": "French Guiana",
        "GG": "Guernsey",
        "GH": "Ghana",
        "GI": "Gibraltar",
        "GL": "Greenland",
        "GM": "Gambia",
        "GN": "Guinea",
        "GP": "Guadeloupe",
        "GQ": "Equatorial Guinea",
        "GR": "Greece",
        "GS": "South Georgia and the South Sandwich Islands",
        "GT": "Guatemala",
        "GU": "Guam",
        "GW": "Guinea-Bissau",
        "GY": "Guyana",
        
        # H
        "HK": "Hong Kong",
        "HM": "Heard Island and McDonald Islands",
        "HN": "Honduras",
        "HR": "Croatia",
        "HT": "Haiti",
        "HU": "Hungary",
        
        # I
        "ID": "Indonesia",
        "IE": "Ireland",
        "IL": "Israel",
        "IM": "Isle of Man",
        "IN": "India",
        "IO": "British Indian Ocean Territory",
        "IQ": "Iraq",
        "IR": "Iran",
        "IS": "Iceland",
        "IT": "Italy",
        
        # J
        "JE": "Jersey",
        "JM": "Jamaica",
        "JO": "Jordan",
        "JP": "Japan",
        
        # K
        "KE": "Kenya",
        "KG": "Kyrgyzstan",
        "KH": "Cambodia",
        "KI": "Kiribati",
        "KM": "Comoros",
        "KN": "Saint Kitts and Nevis",
        "KP": "North Korea",
        "KR": "South Korea",
        "KW": "Kuwait",
        "KY": "Cayman Islands",
        "KZ": "Kazakhstan",
        
        # L
        "LA": "Laos",
        "LB": "Lebanon",
        "LC": "Saint Lucia",
        "LI": "Liechtenstein",
        "LK": "Sri Lanka",
        "LR": "Liberia",
        "LS": "Lesotho",
        "LT": "Lithuania",
        "LU": "Luxembourg",
        "LV": "Latvia",
        "LY": "Libya",
        
        # M
        "MA": "Morocco",
        "MC": "Monaco",
        "MD": "Moldova",
        "ME": "Montenegro",
        "MF": "Saint Martin (French part)",
        "MG": "Madagascar",
        "MH": "Marshall Islands",
        "MK": "North Macedonia",
        "ML": "Mali",
        "MM": "Myanmar",
        "MN": "Mongolia",
        "MO": "Macao",
        "MP": "Northern Mariana Islands",
        "MQ": "Martinique",
        "MR": "Mauritania",
        "MS": "Montserrat",
        "MT": "Malta",
        "MU": "Mauritius",
        "MV": "Maldives",
        "MW": "Malawi",
        "MX": "Mexico",
        "MY": "Malaysia",
        "MZ": "Mozambique",
        
        # N
        "NA": "Namibia",
        "NC": "New Caledonia",
        "NE": "Niger",
        "NF": "Norfolk Island",
        "NG": "Nigeria",
        "NI": "Nicaragua",
        "NL": "Netherlands",
        "NO": "Norway",
        "NP": "Nepal",
        "NR": "Nauru",
        "NU": "Niue",
        "NZ": "New Zealand",
        
        # O
        "OM": "Oman",
        
        # P
        "PA": "Panama",
        "PE": "Peru",
        "PF": "French Polynesia",
        "PG": "Papua New Guinea",
        "PH": "Philippines",
        "PK": "Pakistan",
        "PL": "Poland",
        "PM": "Saint Pierre and Miquelon",
        "PN": "Pitcairn",
        "PR": "Puerto Rico",
        "PS": "Palestine",
        "PT": "Portugal",
        "PW": "Palau",
        "PY": "Paraguay",
        
        # Q
        "QA": "Qatar",
        
        # R
        "RE": "Réunion",
        "RO": "Romania",
        "RS": "Serbia",
        "RU": "Russia",
        "RW": "Rwanda",
        
        # S
        "SA": "Saudi Arabia",
        "SB": "Solomon Islands",
        "SC": "Seychelles",
        "SD": "Sudan",
        "SE": "Sweden",
        "SG": "Singapore",
        "SH": "Saint Helena",
        "SI": "Slovenia",
        "SJ": "Svalbard and Jan Mayen",
        "SK": "Slovakia",
        "SL": "Sierra Leone",
        "SM": "San Marino",
        "SN": "Senegal",
        "SO": "Somalia",
        "SR": "Suriname",
        "SS": "South Sudan",
        "ST": "Sao Tome and Principe",
        "SV": "El Salvador",
        "SX": "Sint Maarten (Dutch part)",
        "SY": "Syria",
        "SZ": "Eswatini",
        
        # T
        "TC": "Turks and Caicos Islands",
        "TD": "Chad",
        "TF": "French Southern Territories",
        "TG": "Togo",
        "TH": "Thailand",
        "TJ": "Tajikistan",
        "TK": "Tokelau",
        "TL": "Timor-Leste",
        "TM": "Turkmenistan",
        "TN": "Tunisia",
        "TO": "Tonga",
        "TR": "Türkiye",
        "TT": "Trinidad and Tobago",
        "TV": "Tuvalu",
        "TW": "Taiwan",
        "TZ": "Tanzania",
        
        # U
        "UA": "Ukraine",
        "UG": "Uganda",
        "UM": "United States Minor Outlying Islands",
        "US": "United States",
        "UY": "Uruguay",
        "UZ": "Uzbekistan",
        
        # V
        "VA": "Vatican City",
        "VC": "Saint Vincent and the Grenadines",
        "VE": "Venezuela",
        "VG": "British Virgin Islands",
        "VI": "U.S. Virgin Islands",
        "VN": "Vietnam",
        "VU": "Vanuatu",
        
        # W
        "WF": "Wallis and Futuna",
        "WS": "Samoa",
        
        # Y
        "YE": "Yemen",
        "YT": "Mayotte",
        
        # Z
        "ZA": "South Africa",
        "ZM": "Zambia",
        "ZW": "Zimbabwe",
        
        # Alternative codes
        "UK": "United Kingdom"  # Alternative to GB
    }

    CITIES_BY_COUNTRY = load_cities_by_country(CITIES_FILE)
    CITY_PATTERNS = build_city_patterns(CITIES_BY_COUNTRY)
    COMPANY_SUFFIXES = load_company_suffixes(COMPANY_SUFFIXES_FILE)

    # Top Vietnamese surnames (covers ~98% of the VN population).
    # First-word match against this set is the strongest signal that an applicant
    # name is an individual rather than a company.
    VN_SURNAMES = frozenset({
        "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
        "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Mai", "Đinh", "Lương",
        "Vương", "Tô", "Tăng", "Châu", "Trịnh", "Đoàn", "Cao", "Đào", "Lâm",
        "Lưu", "Quách", "Tống", "Hà", "Hứa", "Khúc", "Kiều", "La", "Mã", "Nông",
        "Tạ", "Thái", "Triệu", "Văn", "Vi", "Bạch", "Chu", "Đàm", "Lại", "Nghiêm",
        "Phùng", "Trương", "Uông",
        # Added after audits revealed Vietnamese names landing in Unknown:
        "Đồng", "Quảng", "An", "Tiêu", "Sỹ", "Hứa", "Khổng", "Tôn", "Quang",
        "Diếp", "Sử", "Lèo", "Quản", "Nhâm", "Phí", "Lường", "Vì", "Đậu",
        "Viên", "Từ", "Ngụy", "Công", "Âu",
    })
    VN_SURNAMES_UPPER = frozenset(s.upper() for s in VN_SURNAMES)

    # Unambiguous high-confidence company tokens. Match against any of these wins
    # over VN-surname signal — handles edge cases like "NGUYỄN COMPANY LIMITED".
    # Word-boundary matched, so short tokens (LTD, AG, SA) are safe.
    STRONG_COMPANY_SUFFIXES = frozenset({
        "ltd", "ltd.", "limited", "llc", "l.l.c.", "inc", "inc.", "incorporated",
        "corp", "corp.", "corporation", "company", "co.,ltd", "co., ltd",
        "gmbh", "mbh", "s.a.", "sàrl", "sarl", "plc", "pty",
        "công ty", "tổng công ty", "doanh nghiệp", "tập đoàn", "xí nghiệp",
        "công ty cổ phần", "công ty tnhh", "công ty hợp danh", "tnhh",
        "trung tâm nghiên cứu", "viện",
        "ag", "ab", "spa", "srl", "b.v.", "n.v.", "kk", "k.k.", "oy", "aps",
        "anonim şirketi", "anonim sirketi",
    })
    # Typo-tolerant prefix stems — match the canonical stem plus any letters so
    # misspellings ("CORPORTION", "INCORPORATION") and foreign-language variants
    # ("INDUSTRIJA") still classify as Company. Each is bounded so partial matches
    # inside other words (e.g. "INCORPOREAL"-style) don't fire — the boundary
    # requires non-word char before/after.
    TYPO_TOLERANT_COMPANY_PATTERNS = (
        "corp[a-z]*",       # corp, corps, corporate, corporation, corportion
        "incorp[a-z]*",     # incorp, incorporated, incorporation
        "limit[a-z]*",      # limited, limitee (rare typo)
        "compan[a-z]*",     # company, companies, compnay (typo)
        "industri[a-z]*",   # industries, industrial, industrija (Croatian)
        "manufactur[a-z]*", # manufacturing, manufacture
        "enterpr[a-z]*",    # enterprise, enterprises
        "holdin[a-z]*",     # holdings, holding
    )

class TextProcessor:
    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text.strip())

    @staticmethod
    def add_breaks_before_markers(text: str) -> str:
        for marker in TrademarkConstants.MARKER_CODES:
            if marker in text:
                text = text.replace(marker, f'\n{marker}')
        # Ensure (531) and (540) are separated
        text = re.sub(r'\(531\)\s*([^\n]*?)\s*\(540\)', r'(531) \1\n(540)', text)
        return text

    @staticmethod
    def add_empty_breaks_before_sections(text: str) -> str:
        if not text:
            return ""
        sections = text.split('\n')
        result = []
        for section in sections:
            if any(marker in section for marker in TrademarkConstants.MARKER_CODES):
                result.extend(['', section])
            else:
                result.append(section)
        return '\n'.join(result)

def parse_applicant_field(applicant_text: str) -> Tuple[List[str], List[str]]:
    applicant_names = []
    applicant_addresses = []
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
            # Trim any trailing "N. ..." overflow if the previous regex left one
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

class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }
    def format(self, record):
        log_color = self.LEVEL_COLORS.get(record.levelname, '')
        message = super().format(record)
        return f"{log_color}{message}{Style.RESET_ALL}"

class PDFProcessor:
    def __init__(self, input_dir: Path, output_csv_dir: Path):
        self.input_dir = input_dir
        self.output_csv_dir = output_csv_dir
        self.setup_logging()
        self.text_processor = TextProcessor()
        self.first_date: Optional[str] = None

    def setup_logging(self):
        log_file = LOG_FOLDER / 'processing.log'
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.basicConfig(
            level=logging.INFO,
            handlers=[console_handler, file_handler]
        )
        self.logger = logging.getLogger('PDFProcessor')

    def _extract_page_text(self, page) -> str:
        """Extract page text, handling the 2-column layout used by the Madrid-
        registration section of B (entries with (111)/(151)/(171)/(181) schema).
        Flat extract_text() interleaves left and right columns at each y, polluting
        single-value markers like (171) and (540). Per-entry column-aware extraction
        keeps the columns separate: emit all of left first, then all of right, within
        each entry's y-range.
        """
        words = page.extract_words()
        if not words or len(words) < 30:
            return page.extract_text() or ""
        midx = page.width / 2
        # In 2-column pages no word crosses the page midpoint (clean gutter).
        # In 1-column pages text flows across mid, so many words straddle it.
        crossing = sum(1 for w in words if w['x0'] < midx and (w['x0'] + w['width']) > midx)
        if crossing > 2:
            return page.extract_text() or ""
        # 2-column path — find (111) and (116) markers in the left column as entry starts
        entry_starts = sorted(
            w['top'] for w in words
            if w['text'] in ("(111)", "(116)") and w['x0'] < midx
        )
        if not entry_starts:
            return page.extract_text() or ""
        if entry_starts[0] > 30:
            entry_starts.insert(0, 0)
        entry_starts.append(page.height + 1)
        def words_to_text(ws):
            if not ws: return ""
            ws = sorted(ws, key=lambda w: (round(w['top'] / 3) * 3, w['x0']))
            lines: List[str] = []
            cur: List[dict] = []
            cur_y = ws[0]['top']
            for w in ws:
                if abs(w['top'] - cur_y) > 3:
                    lines.append(" ".join(x['text'] for x in cur))
                    cur = []
                    cur_y = w['top']
                cur.append(w)
            if cur:
                lines.append(" ".join(x['text'] for x in cur))
            return "\n".join(lines)
        chunks: List[str] = []
        for i in range(len(entry_starts) - 1):
            y0, y1 = entry_starts[i], entry_starts[i + 1]
            entry_words = [w for w in words if y0 <= w['top'] < y1]
            # (511) Nice class list spans the FULL page width, not just the left column.
            # Splitting it at midpoint sends the trailing classes to the right column,
            # corrupting (740) content. Above (511): 2-column layout. From (511) onward
            # (within this entry): single-column, words sorted by y then x.
            y_511 = min(
                (w['top'] for w in entry_words if w['text'] == "(511)" and w['x0'] < midx),
                default=None,
            )
            if y_511 is None:
                top_words = entry_words
                bot_words = []
            else:
                top_words = [w for w in entry_words if w['top'] < y_511 - 2]
                bot_words = [w for w in entry_words if w['top'] >= y_511 - 2]
            left = [w for w in top_words if w['x0'] < midx]
            right = [w for w in top_words if w['x0'] >= midx]
            t_left = words_to_text(left)
            t_right = words_to_text(right)
            t_bot = words_to_text(bot_words)
            parts = [p for p in (t_left, t_right, t_bot) if p]
            chunks.append("\n".join(parts))
        return "\n".join(chunks)

    def extract_text_from_pdf(self, pdf_path: Path) -> List[Tuple[int, str]]:
        if not pdf_path.exists():
            raise FileNotFoundError(f"{Fore.RED}PDF file not found: {pdf_path}{Style.RESET_ALL}")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page_texts = []
                start_time = time.time()
                self.logger.info(f"{Fore.YELLOW}Starting text extraction from {pdf_path.name}, pages: {len(pdf.pages)}{Style.RESET_ALL}")
                for page_num, page in enumerate(tqdm(pdf.pages, desc=f"{Fore.YELLOW}Extracting pages from {pdf_path.name}{Style.RESET_ALL}"), 1):
                    page_text = self._extract_page_text(page)
                    page_text = self.text_processor.clean_text(page_text)
                    if page_text:
                        processed_text = self.text_processor.add_breaks_before_markers(
                            self.text_processor.add_empty_breaks_before_sections(page_text)
                        )
                        for line in processed_text.split('\n'):
                            if line.strip():
                                page_texts.append((page_num, line.strip()))
                if not page_texts:
                    self.logger.warning(f"{Fore.YELLOW}No text extracted from {pdf_path.name}{Style.RESET_ALL}")
                    raise ValueError(f"No text could be extracted from {pdf_path}")
                self.logger.info(f"{Fore.GREEN}Extracted {len(page_texts)} lines in {time.time() - start_time:.2f}s{Style.RESET_ALL}")
                return page_texts
        except Exception as e:
            self.logger.error(f"{Fore.RED}Error processing PDF {pdf_path}: {str(e)}{Style.RESET_ALL}")
            raise

    def process_sections(self, page_lines: List[Tuple[int, str]], pdf_path: Path) -> Generator[Dict[str, Union[str, int]], None, None]:
        current_section: Dict[str, Union[str, int]] = {}
        section_count = 0
        is_b_pdf = pdf_path.name.lower().startswith('b')
        gazette = "B" if is_b_pdf else "A"
        last_section_start: Optional[str] = None
        accumulating_511 = False
        accumulating_531 = False
        accumulating_540 = False
        max_iterations = len(page_lines)
        iteration_count = 0
        
        i = 0
        start_time = time.time()
        self.logger.info(f"{Fore.YELLOW}Starting section processing, lines: {len(page_lines)}{Style.RESET_ALL}")
        
        def extract_markers_from_line(line: str) -> Dict[str, Union[str, int]]:
            markers_found: Dict[str, Union[str, int]] = {}
            remaining_line = line.strip()
            line_start_time = time.time()
            for key, pattern in TrademarkConstants.PATTERNS.items():
                try:
                    match = re.match(pattern, remaining_line)
                    if match:
                        cleaned_value = self.text_processor.clean_text(match.group(1))
                        if key in ["(141)", "(151)", "(156)", "(181)", "(220)", "(441)", "(450)"]:
                            cleaned_value = reformat_date(cleaned_value)
                            if key in ["(441)", "(450)"] and self.first_date is None:
                                self.first_date = cleaned_value
                        elif key == "(300)":
                            parts = cleaned_value.split()
                            if len(parts) >= 3 and re.match(r"\d{2}/\d{2}/\d{4}", parts[-2]):
                                parts[-2] = reformat_date(parts[-2])
                                cleaned_value = " ".join(parts)
                        elif key in ["(171)", "(176)"]:
                            cleaned_value = cleaned_value.replace("n¨m", "nam")
                        # Ensure (540) is always a string
                        if key == "(540)":
                            cleaned_value = str(cleaned_value)
                            if cleaned_value.isdigit():
                                self.logger.warning(f"{Fore.YELLOW}(540) assigned numeric value: {cleaned_value}{Style.RESET_ALL}")
                                cleaned_value = ""
                        markers_found[key] = cleaned_value
                        break
                    elif key in TrademarkConstants.MARKER_CODES and remaining_line.startswith(key):
                        next_marker_positions = [remaining_line.find(m, len(key)) for m in TrademarkConstants.MARKER_CODES
                                                if m != key and m in remaining_line and remaining_line.find(m) > 0]
                        next_marker_idx = min(next_marker_positions) if next_marker_positions else len(remaining_line)
                        value = remaining_line[len(key):next_marker_idx].strip()
                        value = re.sub(r"\\mathrm{~[A-Za-z]}|\$", "", str(value)).strip()
                        cleaned_value = self.text_processor.clean_text(value)
                        # For date markers, reject anything that isn't a date — guards
                        # against Word merge-field artifacts like "(cid:31) MERGEFIELD…"
                        # bleeding into (441)/(450) when the PDF was a template render.
                        if key in {"(141)","(151)","(156)","(181)","(220)","(441)","(450)"}:
                            if not re.match(r'\d{2}[./]\d{2}[./]\d{4}', cleaned_value):
                                cleaned_value = ""
                        # Ensure (540) is always a string
                        if key == "(540)":
                            cleaned_value = str(cleaned_value)
                            if cleaned_value.isdigit():
                                self.logger.warning(f"{Fore.YELLOW}(540) assigned numeric value: {cleaned_value}{Style.RESET_ALL}")
                                cleaned_value = ""
                        markers_found[key] = cleaned_value
                        break
                except Exception as e:
                    self.logger.warning(f"{Fore.YELLOW}Regex error for {key} on line: {remaining_line[:50]}...: {str(e)}{Style.RESET_ALL}")
            if time.time() - line_start_time > 1:
                self.logger.warning(f"{Fore.YELLOW}Slow regex on line: {remaining_line[:50]}... ({time.time() - line_start_time:.2f}s){Style.RESET_ALL}")
            return markers_found

        def compute_511_fields(section: Dict[str, Union[str, int]]) -> None:
            if "(511)" not in section:
                return
            text = str(section["(511)"]).strip()
            # PDF line wraps mid-word leave artifacts like "phẩ m;" or "thuốc d ược".
            # Three passes handle the directional ambiguity safely:
            #  1) Vietnamese final digraphs split across the wrap ("dịc h", "khôn g") —
            #     forced-join even when a next word follows.
            #  2) Trailing single-consonant orphan — only when punctuation/EOL follows
            #     ("phẩ m;" → "phẩm;"). Refuses to fire on letter-after-space to avoid
            #     wrongly joining real word pairs like "công nghiệp" → "côngnghiệp".
            #  3) Leading single-consonant orphan ("thuốc d ược") — attach to next word,
            #     but skip if next letter starts a Vietnamese onset digraph (next word
            #     already has a valid onset, so orphan would belong to prev word).
            VN_ONSET = "ph|ch|kh|th|tr|gh|ng|nh|qu"
            for a, b in (('c','h'),('n','g'),('n','h'),('p','h'),
                         ('t','h'),('t','r'),('k','h'),('g','h')):
                text = re.sub(rf'({a}) ({b})(?=[\s.,;:!?\)\]/]|$)', r'\1\2', text)
            text = re.sub(
                r'([^\W\d_]) ([bcdđfghjklmnpqrstvwxz])(?=\s*[.,;:!?\)\]/]|\s*$)',
                r'\1\2', text)
            text = re.sub(
                rf'(^|[\s.,;:!?\(\[/])([bcdđfghjklmnpqrstvwxz]) ((?!{VN_ONSET})[^\W\d_])',
                r'\1\2\3', text)
            section["(511)"] = text
            # Form 1: "Nhóm N" or "Nhóm NN" — VN A-file applications enumerate classes
            # by name with the goods/services description.
            nh_classes = re.findall(r"Nh[ãó]m\s+(\d{1,2})", text)
            if nh_classes:
                groups = [c.zfill(2) for c in nh_classes]
            elif re.fullmatch(r'\s*\d{1,2}(?:\s*[,;\s\.]\s*\d{1,2})*\s*\.?\s*', text):
                # Form 2: bare numeric list — Madrid B entries write "(511) 05." or
                # "(511) 09, 12, 41". Restrict to a fullmatch so free text containing
                # incidental digits ("see page 12") doesn't get harvested.
                groups = [t.zfill(2) for t in re.findall(r'\d{1,2}', text) if 1 <= int(t) <= 45]
            else:
                groups = []
            section["Total Group"] = len(groups)
            section["Group Number"] = ",".join(groups)

        def classify_applicant_type(name: str) -> str:
            if not name:
                return ""
            # Strip leading "N. " enumerator prefix sometimes left by (731) parsing
            # ("1. NGUYỄN MỘNG GIANG" → "NGUYỄN MỘNG GIANG").
            stripped = re.sub(r'^\s*\d+\.\s*', "", name).strip()
            if not stripped:
                return ""
            # Use re.IGNORECASE on the original text instead of .lower() — Turkish
            # dotted I (U+0130) lowercases to "i̇" (i + combining dot) which would
            # otherwise break "şirketi" matches in Turkish company names.
            # Use (?<!\w)...(?!\w) rather than \b...\b because \b requires a
            # word↔non-word transition. For suffixes ending in punctuation
            # ("S.R.O.", "Co.,Ltd"), \b at the end fails: the final char is
            # non-word, so there is no \b between it and end-of-string.
            def _has(s: str) -> bool:
                return bool(re.search(
                    r'(?<!\w)' + re.escape(s) + r'(?!\w)', stripped, re.IGNORECASE
                ))
            # 1) High-confidence company tokens override everything (handles rare
            #    surname-prefixed company names like "NGUYỄN COMPANY LIMITED").
            for s in TrademarkConstants.STRONG_COMPANY_SUFFIXES:
                if _has(s):
                    return "Company"
            # 1b) Typo-tolerant prefix patterns — catches "CORPORTION", "INDUSTRIJA",
            #     "INCORPORATION" etc. where exact-string matching would miss.
            for pat in TrademarkConstants.TYPO_TOLERANT_COMPANY_PATTERNS:
                if re.search(rf'(?<!\w){pat}(?!\w)', stripped, re.IGNORECASE):
                    return "Company"
            # 2) First-token Vietnamese surname → Personal. Runs BEFORE the broader
            #    JSON suffix list, otherwise institutional words from VN gazette
            #    vocabulary (Tỉnh, Trường, Văn, …) would wrongly tag personal names.
            tokens = stripped.split()
            if tokens and tokens[0].upper() in TrademarkConstants.VN_SURNAMES_UPPER:
                return "Personal"
            # 3) Broader (lower-confidence) suffix match.
            for suffix in TrademarkConstants.COMPANY_SUFFIXES:
                s = suffix.strip()
                if s and _has(s):
                    return "Company"
            # 4) Fallback: with no company indicator and no VN-surname signal, the
            #    applicant is overwhelmingly an individual (foreign Pinyin/romanized
            #    personal names with no usable detection signal). Trademark applicants
            #    are always Company or Personal — never Unknown — so default Personal.
            return "Personal"

        def extract_applicant_details(section: Dict[str, Union[str, int]]) -> None:
            applicant_text = str(section.get("(731)", "") or section.get("(732)", ""))
            if applicant_text:
                names, addresses = parse_applicant_field(applicant_text)
                section["Applicant Name"] = ", ".join(names) if names else ""
                section["Applicant Address"] = ", ".join(addresses) if addresses else ""
                # Single type per row, derived from the first applicant.
                section["Applicant Type"] = classify_applicant_type(names[0]) if names else ""
                # Scan all (XX) tokens and prefer the first valid ISO code; otherwise
                # "MEISHANG (GZ) COSMETICS CO., LTD. (CN)" picks (GZ) which is invalid.
                paren_codes = re.findall(r'\(([A-Z]{2})\)', applicant_text)
                valid_code = next((c for c in paren_codes if c in TrademarkConstants.COUNTRY_CODES), None)
                if valid_code:
                    section["Applicant Country Code"] = valid_code
                elif paren_codes:
                    section["Applicant Country Code"] = "Unknown"
                else:
                    country_name = re.sub(r'^\d+\.\s*', '', applicant_text).strip()
                    country_code = next((code for code, name in TrademarkConstants.COUNTRY_CODES.items() if name.lower() in country_name.lower()), None)
                    section["Applicant Country Code"] = country_code or "Unknown"
                section["Applicant City"] = ""
                cc = section["Applicant Country Code"]
                # For multi-applicant rows (e.g. "1. NAME1 ... 2. NAME2 ..."), we
                # already truncated the parsed name/address to the FIRST applicant
                # via parse_applicant_field — apply the same truncation here so the
                # city matcher doesn't pick up a city from the SECOND applicant.
                first_applicant_text = re.sub(r'\s+\d+\.\s+.*$', '', applicant_text, flags=re.DOTALL)
                pat = TrademarkConstants.CITY_PATTERNS.get(cc) if cc != "Unknown" else None
                if pat is not None:
                    # One combined alternation regex per country; cities listed longest-first so
                    # Python's leftmost-first alternation gives the longest match. With cleaned
                    # data (no provinces / sub-city units), the city sits at the address tail —
                    # take the LATEST match.
                    last = None
                    for m in pat.finditer(first_applicant_text):
                        last = m
                    if last is not None:
                        section["Applicant City"] = last.group(0)
                # VN fallback: rural communes/villages aren't in cities500; if no
                # city matched, fall back to the "tỉnh <Province>" province name
                # which always appears at the address tail in VN gazette format.
                if section["Applicant City"] == "" and cc == "VN":
                    m_tinh = re.search(r'tỉnh\s+([^,]+)', first_applicant_text, re.IGNORECASE)
                    if m_tinh:
                        section["Applicant City"] = m_tinh.group(1).strip().rstrip('.').strip()
            if "(740)" in section:
                ip_agency_text = str(section["(740)"]).strip()
                # Require ≥3 chars inside parens — skips 2-letter Italian region
                # codes like "(MI)", "(MO)", "(UD)", "(BO)", "(VR)" that appear at
                # the END of European agent addresses and were polluting IPAgency.
                ip_agency_match = re.search(r'\(([^)]{3,})\)', ip_agency_text)
                if ip_agency_match:
                    # VN agents: "Firm Name (FIRM_ABBR)" — keep the parenthesized short form.
                    section["IPAgency"] = ip_agency_match.group(1).strip()
                else:
                    # Madrid agents: "[Title?] Firm Name <street# / Unit / Suite / No.> …".
                    # Strip leading person titles, then cut at first address marker.
                    txt = re.sub(r'^(?:Madame|Mme\.?|Monsieur|M\.|Mr\.?|Mrs\.?|Ms\.?|Mlle\.?|Dr\.?|Prof\.?)\s+',
                                 "", ip_agency_text, flags=re.IGNORECASE)
                    parts = re.split(
                        r'\s+(?=\d|Unit\s|Room\s|Suite\s|Apt\.|Apartment\s|Floor\s|Bldg\.?\s|Building\s|No\.\s)',
                        txt, maxsplit=1, flags=re.IGNORECASE,
                    )
                    section["IPAgency"] = parts[0].strip().rstrip(",")
            if "Applicant Type" not in section:
                section["Applicant Type"] = ""

        def add_date_fields(section: Dict[str, Union[str, int]]) -> None:
            if self.first_date and isinstance(self.first_date, str):
                month, day, year = self.first_date.split('/')
                section["Month"] = month
                section["Year"] = year
                section["DateCombined_441_450"] = self.first_date
            else:
                section["Month"] = ""
                section["Year"] = ""
                section["DateCombined_441_450"] = ""

        def validate_540_content(section: Dict[str, Union[str, int]]) -> None:
            if "(540)" in section:
                value = str(section["(540)"])
                if value.isdigit():
                    self.logger.warning(f"{Fore.YELLOW}(540) contains numeric value: {value}. Resetting to empty string.{Style.RESET_ALL}")
                    section["(540)"] = ""
                elif re.match(r'^\d+\.\d+\.\d+', value):
                    self.logger.warning(f"{Fore.YELLOW}Possible (531) content in (540): {value[:50]}. Moving to (531).{Style.RESET_ALL}")
                    # Ensure the existing value is a string before concatenation
                    section["(531)"] = str(section.get("(531)", "")) + " " + value if section.get("(531)") else value
                    section["(540)"] = ""

        while i < len(page_lines):
            if iteration_count >= max_iterations:
                self.logger.error(f"{Fore.RED}Max iterations {max_iterations} reached at line {i}, breaking{Style.RESET_ALL}")
                break
            iteration_count += 1
            if iteration_count % 1000 == 0:
                self.logger.info(f"{Fore.YELLOW}Progress: iteration {iteration_count}, line {i}/{len(page_lines)}, section keys: {list(current_section.keys())}{Style.RESET_ALL}")
            
            page_num, line = page_lines[i]
            
            if not line:
                if current_section and (accumulating_511 or accumulating_531 or accumulating_540):
                    if accumulating_511:
                        current_section["(511)"] = str(current_section.get("(511)", "")) + " "
                    elif accumulating_531:
                        current_section["(531)"] = str(current_section.get("(531)", "")) + " "
                    elif accumulating_540:
                        current_section["(540)"] = str(current_section.get("(540)", "")) + " "
                i += 1
                continue
            
            markers = extract_markers_from_line(line)
            
            if markers:
                section_start_markers = ["(210)"] if not is_b_pdf else ["(111)", "(116)"]
                start_marker = next((m for m in section_start_markers if m in markers), None)
                
                if start_marker and current_section:
                    compute_511_fields(current_section)
                    extract_applicant_details(current_section)
                    current_section["Gazette"] = gazette
                    add_date_fields(current_section)
                    validate_540_content(current_section)  # Validate (540) before yielding
                    yield current_section
                    section_count += 1
                    current_section = markers
                    last_section_start = start_marker
                    accumulating_511 = False
                    accumulating_531 = False
                    accumulating_540 = False
                
                elif "(511)" in markers and not (accumulating_531 or accumulating_540):
                    accumulating_511 = True
                    accumulating_531 = False
                    accumulating_540 = False
                    current_section["(511)"] = str(markers["(511)"])
                
                elif "(531)" in markers and not accumulating_540:
                    accumulating_531 = True
                    accumulating_511 = False
                    accumulating_540 = False
                    current_section["(531)"] = str(markers["(531)"])
                
                elif "(540)" in markers:
                    accumulating_540 = True
                    accumulating_511 = False
                    accumulating_531 = False
                    current_section["(540)"] = str(markers["(540)"])
                
                else:
                    accumulating_511 = False
                    accumulating_531 = False
                    accumulating_540 = False
                    current_section.update(markers)
            
            elif current_section:
                if accumulating_511:
                    current_section["(511)"] = str(current_section.get("(511)", "")) + " " + self.text_processor.clean_text(line)
                elif accumulating_531:
                    current_section["(531)"] = str(current_section.get("(531)", "")) + " " + self.text_processor.clean_text(line)
                elif accumulating_540:
                    current_section["(540)"] = str(current_section.get("(540)", "")) + " " + self.text_processor.clean_text(line)
                else:
                    current_marker = list(current_section.keys())[-1]
                    if not any(line.strip().startswith(m) for m in TrademarkConstants.MARKER_CODES if m != current_marker):
                        current_section[current_marker] = str(current_section[current_marker]) + " " + self.text_processor.clean_text(line)
            
            i += 1
        
        if current_section:
            compute_511_fields(current_section)
            extract_applicant_details(current_section)
            current_section["Gazette"] = gazette
            add_date_fields(current_section)
            validate_540_content(current_section)  # Validate (540) for final section
            yield current_section
            section_count += 1
            self.logger.info(f"{Fore.GREEN}Final section yielded, count: {section_count}{Style.RESET_ALL}")
        
        self.logger.info(f"{Fore.GREEN}Processed {section_count} trademarks in {time.time() - start_time:.2f}s{Style.RESET_ALL}")

    def create_csv(self, sections: List[Dict[str, Union[str, int]]], filename: str) -> None:
        try:
            columns = TrademarkConstants.CSV_COLUMNS
            df = pd.DataFrame(sections)
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            df["IPAgencyStatus"] = df["(740)"].apply(lambda x: "Via Agency" if pd.notna(x) and str(x).strip() else "No")
            df = df[columns]
            # Lowercase every cell value EXCEPT (540) trademark sample, where
            # original wordmark casing carries meaning ("MAYBELLINE LIFTER" vs.
            # "Maybelline lifter"). Column headers are untouched (set below
            # via rename). Non-string values (ints like Total Group) skipped.
            for col in df.columns:
                if col == "(540)":
                    continue
                df[col] = df[col].apply(lambda v: v.lower() if isinstance(v, str) else v)
            # Excel's per-cell character limit is 32,767. For (511) cells that
            # exceed it, truncate in the CSV and dump the full text to a sidecar
            # .txt file keyed by registration number. Other columns are never
            # close to the limit so we only check (511).
            EXCEL_LIMIT = 32767
            SAFE_LIMIT = 32500  # leaves headroom for the truncation marker
            overflow: List[Tuple[str, str]] = []
            sidecar_name = f"{filename}_511_overflow.txt"
            for idx in df.index:
                val = df.at[idx, "(511)"]
                if isinstance(val, str) and len(val) > EXCEL_LIMIT:
                    key = (str(df.at[idx, "(111)"]).strip() or
                           str(df.at[idx, "(116)"]).strip() or
                           str(df.at[idx, "(210)"]).strip() or f"row_{idx}")
                    overflow.append((key, val))
                    marker = f" … [truncated at {SAFE_LIMIT} chars; full text in {sidecar_name}]"
                    df.at[idx, "(511)"] = val[:SAFE_LIMIT] + marker
            rename_dict = {col: f"{col[1:-1]} {TrademarkConstants.MARKER_DESCRIPTIONS[col]}" if col in TrademarkConstants.MARKER_DESCRIPTIONS else col for col in columns}
            df = df.rename(columns=rename_dict)
            output_path = self.output_csv_dir / f"{filename}.csv"
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            if overflow:
                sidecar_path = self.output_csv_dir / sidecar_name
                with sidecar_path.open("w", encoding="utf-8") as sf:
                    for key, full_text in overflow:
                        sf.write(f"=== {key} ===\n{full_text}\n\n")
                self.logger.info(f"{Fore.GREEN}Saved {len(overflow)} overflow (511) entries to {sidecar_path}{Style.RESET_ALL}")
            self.logger.info(f"{Fore.GREEN}Saved {len(sections)} trademarks to {output_path}{Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to create CSV {filename}: {str(e)}{Style.RESET_ALL}")
            raise

    def process_file(self, pdf_path: Path) -> None:
        try:
            self.logger.info(f"{Fore.YELLOW}Processing: {pdf_path.name}{Style.RESET_ALL}")
            self.first_date = None
            page_texts = self.extract_text_from_pdf(pdf_path)
            sections = list(self.process_sections(page_texts, pdf_path))
            # B-file Madrid (116) entries have a different schema than domestic
            # (111) registrations — split them into a parallel "<stem>_madrid.csv"
            # so each output file is schema-clean for downstream analysis.
            if pdf_path.name.lower().startswith('b'):
                domestic = [s for s in sections if not str(s.get("(116)", "")).strip()]
                madrid = [s for s in sections if str(s.get("(116)", "")).strip()]
                self.create_csv(domestic, pdf_path.stem)
                if madrid:
                    self.create_csv(madrid, pdf_path.stem + "_madrid")
                self.logger.info(
                    f"{Fore.GREEN}Successfully processed {len(sections)} trademarks "
                    f"({len(domestic)} domestic + {len(madrid)} Madrid){Style.RESET_ALL}"
                )
            else:
                self.create_csv(sections, pdf_path.stem)
                self.logger.info(f"{Fore.GREEN}Successfully processed {len(sections)} trademarks{Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to process {pdf_path.name}: {str(e)}{Style.RESET_ALL}")
            raise

    def process_files_parallel(self, pdf_files: List[Path], max_workers: int = 1) -> None:
        failed_files = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(self.process_file, pdf): pdf for pdf in pdf_files}
            for future in tqdm(as_completed(future_to_file), total=len(pdf_files), desc=f"{Fore.YELLOW}Processing PDFs{Style.RESET_ALL}"):
                pdf_file = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"{Fore.RED}Failed to process {pdf_file.name}: {str(e)}{Style.RESET_ALL}")
                    failed_files.append(pdf_file)
        if failed_files:
            self.logger.warning(f"{Fore.YELLOW}Failed to process {len(failed_files)} files: {[f.name for f in failed_files]}{Style.RESET_ALL}")

class UserInterface:
    @staticmethod
    def get_pdf_selection(pdf_files: List[Path]) -> List[Path]:
        if not pdf_files:
            logging.warning(f"{Fore.YELLOW}No PDF files found in the input directory.{Style.RESET_ALL}")
            return []
        print(f"\n{Fore.BLUE}Available PDFs:{Style.RESET_ALL}")
        for i, pdf in enumerate(pdf_files, 1):
            print(f"{Fore.BLUE}{i}. {pdf.name}{Style.RESET_ALL}")
        print(f"\n{Fore.BLUE}Options:{Style.RESET_ALL}")
        print(f"{Fore.BLUE}1. Process all PDFs{Style.RESET_ALL}")
        print(f"{Fore.BLUE}2. Select specific PDFs{Style.RESET_ALL}")
        while True:
            try:
                choice = input(f"\n{Fore.BLUE}Enter choice (1 or 2): {Style.RESET_ALL}").strip()
                if choice == '1':
                    return pdf_files
                elif choice == '2':
                    indices_input = input(f"{Fore.BLUE}Enter PDF numbers (comma-separated, e.g., 1,2,3): {Style.RESET_ALL}").strip()
                    if not indices_input:
                        print(f"{Fore.YELLOW}No input provided. Please try again.{Style.RESET_ALL}")
                        continue
                    selected_indices: Set[int] = set()
                    for i in indices_input.split(','):
                        i = i.strip()
                        if not i.isdigit():
                            print(f"{Fore.RED}Invalid input '{i}': Please enter valid numbers.{Style.RESET_ALL}")
                            break
                        index = int(i) - 1
                        if 0 <= index < len(pdf_files):
                            selected_indices.add(index)
                        else:
                            print(f"{Fore.RED}Index {i} is out of range. Please try again.{Style.RESET_ALL}")
                            break
                    else:
                        if not selected_indices:
                            print(f"{Fore.YELLOW}No valid selections made. Please try again.{Style.RESET_ALL}")
                            continue
                        return [pdf_files[i] for i in sorted(selected_indices)]
                else:
                    print(f"{Fore.RED}Invalid choice. Please enter 1 or 2.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Error: {str(e)}. Please try again.{Style.RESET_ALL}")

def main():
    try:
        pdf_files = sorted(INPUT_FOLDER.glob('*.pdf'))
        if not pdf_files:
            logging.error(f"{Fore.RED}No PDF files found in the input directory.{Style.RESET_ALL}")
            return
        selected_files = UserInterface.get_pdf_selection(pdf_files)
        if not selected_files:
            logging.warning(f"{Fore.YELLOW}No files selected for processing.{Style.RESET_ALL}")
            return
        processor = PDFProcessor(INPUT_FOLDER, CSV_FOLDER)
        processor.process_files_parallel(selected_files, max_workers=1)
        logging.info(f"{Fore.GREEN}Processing completed successfully.{Style.RESET_ALL}")
    except Exception as e:
        logging.error(f"{Fore.RED}Application error: {str(e)}{Style.RESET_ALL}")
        raise

if __name__ == "__main__":
    main()