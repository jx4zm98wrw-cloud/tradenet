"""PDFProcessor — main extraction class.

Reads PDFs from `config.input_dir`, writes CSVs to `config.output_dir`. Loads
cities and company suffixes from `config.data_dir` at construction time.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from re import Pattern

import pandas as pd
import pdfplumber
from colorama import Fore, Style
from tqdm import tqdm

from .applicant import parse_applicant_field
from .config import ExtractorConfig
from .constants import TrademarkConstants
from .data_loaders import build_city_patterns, load_cities_by_country, load_company_suffixes
from .text_processor import ColoredFormatter, TextProcessor, reformat_date


class PDFProcessor:
    def __init__(self, config: ExtractorConfig):
        self.config = config
        self.config.ensure_dirs()
        # Backward-compat aliases for code paths that referenced these by name.
        self.input_dir = config.input_dir
        self.output_csv_dir = config.output_dir
        self.setup_logging()
        self.text_processor = TextProcessor()
        # Reference data — loaded once per processor instance.
        self.cities_by_country: dict[str, set[str]] = load_cities_by_country(config.cities_file)
        self.city_patterns: dict[str, Pattern] = build_city_patterns(self.cities_by_country)
        self.company_suffixes: set[str] = load_company_suffixes(config.company_suffixes_file)

    def setup_logging(self):
        log_file = self.config.log_dir / "processing.log"
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColoredFormatter("%(asctime)s - %(levelname)s - %(message)s"))
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file), maxBytes=1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
        self.logger = logging.getLogger("PDFProcessor")

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
        # Some 2-column B-pages have a handful of crossers (long dates, Vienna
        # codes spanning a frame, headers), so use a ratio test, not an absolute
        # cutoff: >10% of words crossing mid → real single-column page.
        crossing = sum(1 for w in words if w["x0"] < midx and (w["x0"] + w["width"]) > midx)
        if crossing > max(10, 0.10 * len(words)):
            return page.extract_text() or ""
        # 2-column path — find (111) and (116) markers in the left column as entry starts
        entry_starts = sorted(w["top"] for w in words if w["text"] in ("(111)", "(116)") and w["x0"] < midx)
        if not entry_starts:
            return page.extract_text() or ""
        if entry_starts[0] > 30:
            entry_starts.insert(0, 0)
        entry_starts.append(page.height + 1)

        def words_to_text(ws):
            if not ws:
                return ""
            ws = sorted(ws, key=lambda w: (round(w["top"] / 3) * 3, w["x0"]))
            lines: list[str] = []
            cur: list[dict] = []
            cur_y = ws[0]["top"]
            for w in ws:
                if abs(w["top"] - cur_y) > 3:
                    lines.append(" ".join(x["text"] for x in cur))
                    cur = []
                    cur_y = w["top"]
                cur.append(w)
            if cur:
                lines.append(" ".join(x["text"] for x in cur))
            return "\n".join(lines)

        chunks: list[str] = []
        for i in range(len(entry_starts) - 1):
            y0, y1 = entry_starts[i], entry_starts[i + 1]
            entry_words = [w for w in words if y0 <= w["top"] < y1]
            # (511) Nice class list spans the FULL page width, not just the left column.
            # Splitting it at midpoint sends the trailing classes to the right column,
            # corrupting (740) content. Above (511): 2-column layout. From (511) onward
            # (within this entry): single-column, words sorted by y then x.
            y_511 = min(
                (w["top"] for w in entry_words if w["text"] == "(511)" and w["x0"] < midx),
                default=None,
            )
            if y_511 is None:
                top_words = entry_words
                bot_words = []
            else:
                top_words = [w for w in entry_words if w["top"] < y_511 - 2]
                bot_words = [w for w in entry_words if w["top"] >= y_511 - 2]
            left = [w for w in top_words if w["x0"] < midx]
            right = [w for w in top_words if w["x0"] >= midx]
            t_left = words_to_text(left)
            t_right = words_to_text(right)
            t_bot = words_to_text(bot_words)
            parts = [p for p in (t_left, t_right, t_bot) if p]
            chunks.append("\n".join(parts))
        return "\n".join(chunks)

    def extract_text_from_pdf(self, pdf_path: Path) -> list[tuple[int, str]]:
        if not pdf_path.exists():
            raise FileNotFoundError(f"{Fore.RED}PDF file not found: {pdf_path}{Style.RESET_ALL}")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page_texts = []
                start_time = time.time()
                self.logger.info(
                    f"{Fore.YELLOW}Starting text extraction from {pdf_path.name}, pages: {len(pdf.pages)}{Style.RESET_ALL}"
                )
                for page_num, page in enumerate(
                    tqdm(
                        pdf.pages, desc=f"{Fore.YELLOW}Extracting pages from {pdf_path.name}{Style.RESET_ALL}"
                    ),
                    1,
                ):
                    page_text = self._extract_page_text(page)
                    page_text = self.text_processor.clean_text(page_text)
                    if page_text:
                        processed_text = self.text_processor.add_breaks_before_markers(
                            self.text_processor.add_empty_breaks_before_sections(page_text)
                        )
                        for line in processed_text.split("\n"):
                            if line.strip():
                                page_texts.append((page_num, line.strip()))
                if not page_texts:
                    self.logger.warning(
                        f"{Fore.YELLOW}No text extracted from {pdf_path.name}{Style.RESET_ALL}"
                    )
                    raise ValueError(f"No text could be extracted from {pdf_path}")
                self.logger.info(
                    f"{Fore.GREEN}Extracted {len(page_texts)} lines in {time.time() - start_time:.2f}s{Style.RESET_ALL}"
                )
                return page_texts
        except Exception as e:
            self.logger.error(f"{Fore.RED}Error processing PDF {pdf_path}: {e!s}{Style.RESET_ALL}")
            raise

    def process_sections(
        self,
        page_lines: list[tuple[int, str]],
        pdf_path: Path,
        gazette_type: str | None = None,
    ) -> Generator[dict[str, str | int], None, None]:
        """Yield section dicts. `gazette_type` ("A"|"B") overrides the filename-based
        inference — required when the file has been renamed (e.g. stored under a
        hashed name by the upload pipeline) and the leading letter no longer matches.
        """
        current_section: dict[str, str | int] = {}
        section_count = 0
        if gazette_type in ("A", "B"):
            gazette = gazette_type
            is_b_pdf = gazette == "B"
        else:
            is_b_pdf = pdf_path.name.lower().startswith("b")
            gazette = "B" if is_b_pdf else "A"
        last_section_start: str | None = None
        accumulating_511 = False
        accumulating_531 = False
        accumulating_540 = False
        max_iterations = len(page_lines)
        iteration_count = 0
        # Per-call state: the first (441)/(450) marker seen in this PDF.
        # Used by add_date_fields below to populate Month/Year/DateCombined_441_450.
        # Local (not self.) so concurrent or back-to-back calls to process_sections
        # on the same PDFProcessor don't leak dates across files.
        first_date: str | None = None

        i = 0
        start_time = time.time()
        self.logger.info(
            f"{Fore.YELLOW}Starting section processing, lines: {len(page_lines)}{Style.RESET_ALL}"
        )

        def extract_markers_from_line(line: str) -> dict[str, str | int]:
            nonlocal first_date  # may be reassigned below on first (441)/(450)
            markers_found: dict[str, str | int] = {}
            remaining_line = line.strip()
            line_start_time = time.time()
            for key, pattern in TrademarkConstants.PATTERNS.items():
                try:
                    match = re.match(pattern, remaining_line)
                    if match:
                        cleaned_value = self.text_processor.clean_text(match.group(1))
                        if key in ["(141)", "(151)", "(156)", "(181)", "(220)", "(441)", "(450)"]:
                            cleaned_value = reformat_date(cleaned_value)
                            if key in ["(441)", "(450)"] and first_date is None:
                                first_date = cleaned_value
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
                                self.logger.warning(
                                    f"{Fore.YELLOW}(540) assigned numeric value: {cleaned_value}{Style.RESET_ALL}"
                                )
                                cleaned_value = ""
                        markers_found[key] = cleaned_value
                        break
                    elif key in TrademarkConstants.MARKER_CODES and remaining_line.startswith(key):
                        next_marker_positions = [
                            remaining_line.find(m, len(key))
                            for m in TrademarkConstants.MARKER_CODES
                            if m != key and m in remaining_line and remaining_line.find(m) > 0
                        ]
                        next_marker_idx = (
                            min(next_marker_positions) if next_marker_positions else len(remaining_line)
                        )
                        value = remaining_line[len(key) : next_marker_idx].strip()
                        value = re.sub(r"\\mathrm{~[A-Za-z]}|\$", "", str(value)).strip()
                        cleaned_value = self.text_processor.clean_text(value)
                        # For date markers, reject anything that isn't a date — guards
                        # against Word merge-field artifacts like "(cid:31) MERGEFIELD…"
                        # bleeding into (441)/(450) when the PDF was a template render.
                        if key in {"(141)", "(151)", "(156)", "(181)", "(220)", "(441)", "(450)"}:
                            if not re.match(r"\d{2}[./]\d{2}[./]\d{4}", cleaned_value):
                                cleaned_value = ""
                        # Ensure (540) is always a string
                        if key == "(540)":
                            cleaned_value = str(cleaned_value)
                            if cleaned_value.isdigit():
                                self.logger.warning(
                                    f"{Fore.YELLOW}(540) assigned numeric value: {cleaned_value}{Style.RESET_ALL}"
                                )
                                cleaned_value = ""
                        markers_found[key] = cleaned_value
                        break
                except Exception as e:
                    self.logger.warning(
                        f"{Fore.YELLOW}Regex error for {key} on line: {remaining_line[:50]}...: {e!s}{Style.RESET_ALL}"
                    )
            if time.time() - line_start_time > 1:
                self.logger.warning(
                    f"{Fore.YELLOW}Slow regex on line: {remaining_line[:50]}... ({time.time() - line_start_time:.2f}s){Style.RESET_ALL}"
                )
            return markers_found

        def compute_511_fields(section: dict[str, str | int]) -> None:
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
            for a, b in (
                ("c", "h"),
                ("n", "g"),
                ("n", "h"),
                ("p", "h"),
                ("t", "h"),
                ("t", "r"),
                ("k", "h"),
                ("g", "h"),
            ):
                text = re.sub(rf"({a}) ({b})(?=[\s.,;:!?\)\]/]|$)", r"\1\2", text)
            text = re.sub(r"([^\W\d_]) ([bcdđfghjklmnpqrstvwxz])(?=\s*[.,;:!?\)\]/]|\s*$)", r"\1\2", text)
            text = re.sub(
                rf"(^|[\s.,;:!?\(\[/])([bcdđfghjklmnpqrstvwxz]) ((?!{VN_ONSET})[^\W\d_])", r"\1\2\3", text
            )
            section["(511)"] = text
            # Form 1: "Nhóm N" or "Nhóm NN" — VN A-file applications enumerate classes
            # by name with the goods/services description.
            nh_classes = re.findall(r"Nh[ãó]m\s+(\d{1,2})", text)
            if nh_classes:
                groups = [c.zfill(2) for c in nh_classes]
            elif re.fullmatch(r"\s*\d{1,2}(?:\s*[,;\s\.]\s*\d{1,2})*\s*\.?\s*", text):
                # Form 2: bare numeric list — Madrid B entries write "(511) 05." or
                # "(511) 09, 12, 41". Restrict to a fullmatch so free text containing
                # incidental digits ("see page 12") doesn't get harvested.
                groups = [t.zfill(2) for t in re.findall(r"\d{1,2}", text) if 1 <= int(t) <= 45]
            else:
                groups = []
            section["Total Group"] = len(groups)
            section["Group Number"] = ",".join(groups)

        def classify_applicant_type(name: str) -> str:
            if not name:
                return ""
            # Strip leading "N. " enumerator prefix sometimes left by (731) parsing
            # ("1. NGUYỄN MỘNG GIANG" → "NGUYỄN MỘNG GIANG").
            stripped = re.sub(r"^\s*\d+\.\s*", "", name).strip()
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
                return bool(re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", stripped, re.IGNORECASE))

            # 1) High-confidence company tokens override everything (handles rare
            #    surname-prefixed company names like "NGUYỄN COMPANY LIMITED").
            for s in TrademarkConstants.STRONG_COMPANY_SUFFIXES:
                if _has(s):
                    return "Company"
            # 1b) Typo-tolerant prefix patterns — catches "CORPORTION", "INDUSTRIJA",
            #     "INCORPORATION" etc. where exact-string matching would miss.
            for pat in TrademarkConstants.TYPO_TOLERANT_COMPANY_PATTERNS:
                if re.search(rf"(?<!\w){pat}(?!\w)", stripped, re.IGNORECASE):
                    return "Company"
            # 2) First-token Vietnamese surname → Personal. Runs BEFORE the broader
            #    JSON suffix list, otherwise institutional words from VN gazette
            #    vocabulary (Tỉnh, Trường, Văn, …) would wrongly tag personal names.
            tokens = stripped.split()
            if tokens and tokens[0].upper() in TrademarkConstants.VN_SURNAMES_UPPER:
                return "Personal"
            # 3) Broader (lower-confidence) suffix match.
            for suffix in self.company_suffixes:
                s = suffix.strip()
                if s and _has(s):
                    return "Company"
            # 4) Fallback: with no company indicator and no VN-surname signal, the
            #    applicant is overwhelmingly an individual (foreign Pinyin/romanized
            #    personal names with no usable detection signal). Trademark applicants
            #    are always Company or Personal — never Unknown — so default Personal.
            return "Personal"

        def extract_applicant_details(section: dict[str, str | int]) -> None:
            applicant_text = str(section.get("(731)", "") or section.get("(732)", ""))
            if applicant_text:
                names, addresses = parse_applicant_field(applicant_text)
                section["Applicant Name"] = ", ".join(names) if names else ""
                section["Applicant Address"] = ", ".join(addresses) if addresses else ""
                # Single type per row, derived from the first applicant.
                section["Applicant Type"] = classify_applicant_type(names[0]) if names else ""
                # Scan all (XX) tokens and prefer the first valid ISO code; otherwise
                # "MEISHANG (GZ) COSMETICS CO., LTD. (CN)" picks (GZ) which is invalid.
                paren_codes = re.findall(r"\(([A-Z]{2})\)", applicant_text)
                valid_code = next((c for c in paren_codes if c in TrademarkConstants.COUNTRY_CODES), None)
                if valid_code:
                    section["Applicant Country Code"] = valid_code
                elif paren_codes:
                    section["Applicant Country Code"] = "Unknown"
                else:
                    country_name = re.sub(r"^\d+\.\s*", "", applicant_text).strip()
                    country_code = next(
                        (
                            code
                            for code, name in TrademarkConstants.COUNTRY_CODES.items()
                            if name.lower() in country_name.lower()
                        ),
                        None,
                    )
                    section["Applicant Country Code"] = country_code or "Unknown"
                section["Applicant City"] = ""
                cc = section["Applicant Country Code"]
                # Match cities only inside the parsed address. Searching the
                # whole applicant text catches personal-name tokens that
                # collide with city names — e.g. "Hồng Lĩnh" is both a city
                # in Hà Tĩnh province AND a common Vietnamese middle name,
                # and would otherwise be picked up from "NGUYỄN THỊ HỒNG
                # LĨNH (VN) ...". parse_applicant_field already truncates
                # to the first applicant, so the multi-applicant defense
                # the old code did via regex is no longer needed here.
                address_text = str(section.get("Applicant Address", ""))
                pat = self.city_patterns.get(cc) if cc != "Unknown" else None
                if pat is not None and address_text:
                    # One combined alternation regex per country; cities listed longest-first so
                    # Python's leftmost-first alternation gives the longest match. With cleaned
                    # data (no provinces / sub-city units), the city sits at the address tail —
                    # take the LATEST match.
                    last = None
                    for m in pat.finditer(address_text):
                        last = m
                    if last is not None:
                        section["Applicant City"] = last.group(0)
                # VN fallback: rural communes/villages aren't in cities500; if no
                # city matched, fall back to the "tỉnh <Province>" province name
                # which always appears at the address tail in VN gazette format.
                if section["Applicant City"] == "" and cc == "VN":
                    m_tinh = re.search(r"tỉnh\s+([^,]+)", address_text, re.IGNORECASE)
                    if m_tinh:
                        section["Applicant City"] = m_tinh.group(1).strip().rstrip(".").strip()
            if "(740)" in section:
                ip_agency_text = str(section["(740)"]).strip()
                # Require ≥3 chars inside parens — skips 2-letter Italian region
                # codes like "(MI)", "(MO)", "(UD)", "(BO)", "(VR)" that appear at
                # the END of European agent addresses and were polluting IPAgency.
                ip_agency_match = re.search(r"\(([^)]{3,})\)", ip_agency_text)
                if ip_agency_match:
                    # VN agents: "Firm Name (FIRM_ABBR)" — keep the parenthesized short form.
                    section["IPAgency"] = ip_agency_match.group(1).strip()
                else:
                    # Madrid agents: "[Title?] Firm Name <street# / Unit / Suite / No.> …".
                    # Strip leading person titles, then cut at first address marker.
                    txt = re.sub(
                        r"^(?:Madame|Mme\.?|Monsieur|M\.|Mr\.?|Mrs\.?|Ms\.?|Mlle\.?|Dr\.?|Prof\.?)\s+",
                        "",
                        ip_agency_text,
                        flags=re.IGNORECASE,
                    )
                    parts = re.split(
                        r"\s+(?=\d|Unit\s|Room\s|Suite\s|Apt\.|Apartment\s|Floor\s|Bldg\.?\s|Building\s|No\.\s)",
                        txt,
                        maxsplit=1,
                        flags=re.IGNORECASE,
                    )
                    section["IPAgency"] = parts[0].strip().rstrip(",")
            if "Applicant Type" not in section:
                section["Applicant Type"] = ""

        def add_date_fields(section: dict[str, str | int]) -> None:
            if first_date and isinstance(first_date, str):
                month, day, year = first_date.split("/")
                section["Month"] = month
                section["Year"] = year
                section["DateCombined_441_450"] = first_date
            else:
                section["Month"] = ""
                section["Year"] = ""
                section["DateCombined_441_450"] = ""

        def validate_540_content(section: dict[str, str | int]) -> None:
            if "(540)" in section:
                value = str(section["(540)"])
                if value.isdigit():
                    self.logger.warning(
                        f"{Fore.YELLOW}(540) contains numeric value: {value}. Resetting to empty string.{Style.RESET_ALL}"
                    )
                    section["(540)"] = ""
                elif re.match(r"^\d+\.\d+\.\d+", value):
                    self.logger.warning(
                        f"{Fore.YELLOW}Possible (531) content in (540): {value[:50]}. Moving to (531).{Style.RESET_ALL}"
                    )
                    # Ensure the existing value is a string before concatenation
                    section["(531)"] = (
                        str(section.get("(531)", "")) + " " + value if section.get("(531)") else value
                    )
                    section["(540)"] = ""

        while i < len(page_lines):
            if iteration_count >= max_iterations:
                self.logger.error(
                    f"{Fore.RED}Max iterations {max_iterations} reached at line {i}, breaking{Style.RESET_ALL}"
                )
                break
            iteration_count += 1
            if iteration_count % 1000 == 0:
                self.logger.info(
                    f"{Fore.YELLOW}Progress: iteration {iteration_count}, line {i}/{len(page_lines)}, section keys: {list(current_section.keys())}{Style.RESET_ALL}"
                )

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
                    current_section["(511)"] = (
                        str(current_section.get("(511)", "")) + " " + self.text_processor.clean_text(line)
                    )
                elif accumulating_531:
                    current_section["(531)"] = (
                        str(current_section.get("(531)", "")) + " " + self.text_processor.clean_text(line)
                    )
                elif accumulating_540:
                    current_section["(540)"] = (
                        str(current_section.get("(540)", "")) + " " + self.text_processor.clean_text(line)
                    )
                else:
                    current_marker = list(current_section.keys())[-1]
                    if not any(
                        line.strip().startswith(m)
                        for m in TrademarkConstants.MARKER_CODES
                        if m != current_marker
                    ):
                        current_section[current_marker] = (
                            str(current_section[current_marker]) + " " + self.text_processor.clean_text(line)
                        )

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

        self.logger.info(
            f"{Fore.GREEN}Processed {section_count} trademarks in {time.time() - start_time:.2f}s{Style.RESET_ALL}"
        )

    def create_csv(self, sections: list[dict[str, str | int]], filename: str) -> None:
        try:
            columns = TrademarkConstants.CSV_COLUMNS
            df = pd.DataFrame(sections)
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            df["IPAgencyStatus"] = df["(740)"].apply(
                lambda x: "Via Agency" if pd.notna(x) and str(x).strip() else "No"
            )
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
            overflow: list[tuple[str, str]] = []
            sidecar_name = f"{filename}_511_overflow.txt"
            for idx in df.index:
                val = df.at[idx, "(511)"]
                if isinstance(val, str) and len(val) > EXCEL_LIMIT:
                    key = (
                        str(df.at[idx, "(111)"]).strip()
                        or str(df.at[idx, "(116)"]).strip()
                        or str(df.at[idx, "(210)"]).strip()
                        or f"row_{idx}"
                    )
                    overflow.append((key, val))
                    marker = f" … [truncated at {SAFE_LIMIT} chars; full text in {sidecar_name}]"
                    df.at[idx, "(511)"] = val[:SAFE_LIMIT] + marker
            rename_dict = {
                col: f"{col[1:-1]} {TrademarkConstants.MARKER_DESCRIPTIONS[col]}"
                if col in TrademarkConstants.MARKER_DESCRIPTIONS
                else col
                for col in columns
            }
            df = df.rename(columns=rename_dict)
            output_path = self.output_csv_dir / f"{filename}.csv"
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
            if overflow:
                sidecar_path = self.output_csv_dir / sidecar_name
                with sidecar_path.open("w", encoding="utf-8") as sf:
                    for key, full_text in overflow:
                        sf.write(f"=== {key} ===\n{full_text}\n\n")
                self.logger.info(
                    f"{Fore.GREEN}Saved {len(overflow)} overflow (511) entries to {sidecar_path}{Style.RESET_ALL}"
                )
            self.logger.info(
                f"{Fore.GREEN}Saved {len(sections)} trademarks to {output_path}{Style.RESET_ALL}"
            )
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to create CSV {filename}: {e!s}{Style.RESET_ALL}")
            raise

    def extract_records(
        self,
        pdf_path: Path,
        gazette_type: str | None = None,
    ) -> Generator[dict[str, str | int], None, None]:
        """Yield enriched section dicts for a PDF — same data CSV writes, no I/O.
        For DB ingestion or any consumer that doesn't need the CSV form.

        Callers that have renamed the file (e.g. uploaded under a hashed storage
        path) must pass `gazette_type` explicitly; otherwise the filename's first
        letter is used.
        """
        page_texts = self.extract_text_from_pdf(pdf_path)
        yield from self.process_sections(page_texts, pdf_path, gazette_type=gazette_type)

    def process_file(self, pdf_path: Path) -> None:
        try:
            self.logger.info(f"{Fore.YELLOW}Processing: {pdf_path.name}{Style.RESET_ALL}")
            page_texts = self.extract_text_from_pdf(pdf_path)
            sections = list(self.process_sections(page_texts, pdf_path))
            # B-file Madrid (116) entries have a different schema than domestic
            # (111) registrations — split them into a parallel "<stem>_madrid.csv"
            # so each output file is schema-clean for downstream analysis.
            if pdf_path.name.lower().startswith("b"):
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
                self.logger.info(
                    f"{Fore.GREEN}Successfully processed {len(sections)} trademarks{Style.RESET_ALL}"
                )
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to process {pdf_path.name}: {e!s}{Style.RESET_ALL}")
            raise

    def process_files_parallel(self, pdf_files: list[Path], max_workers: int = 1) -> None:
        failed_files = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(self.process_file, pdf): pdf for pdf in pdf_files}
            for future in tqdm(
                as_completed(future_to_file),
                total=len(pdf_files),
                desc=f"{Fore.YELLOW}Processing PDFs{Style.RESET_ALL}",
            ):
                pdf_file = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"{Fore.RED}Failed to process {pdf_file.name}: {e!s}{Style.RESET_ALL}")
                    failed_files.append(pdf_file)
        if failed_files:
            self.logger.warning(
                f"{Fore.YELLOW}Failed to process {len(failed_files)} files: {[f.name for f in failed_files]}{Style.RESET_ALL}"
            )
