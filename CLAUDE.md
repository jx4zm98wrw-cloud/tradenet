# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python tool (`TM_csv_builder.py`) that extracts Vietnamese trademark gazette data from NOIP (IP Vietnam) PDF publications into per-PDF CSVs. Two gazette types in the same codebase: **A** (applications, section starts at `(210)`) and **B** (registrations, section starts at `(111)` or `(116)`, including Madrid international registrations). Type is inferred from the filename's first letter (case-insensitive).

## Run

```bash
python3 TM_csv_builder.py
```

Interactive prompt — `1` processes all PDFs in `input/`, `2` accepts comma-separated indices. No build, lint, or test harness.

Dependencies (manual install, no requirements.txt):
```
pdfplumber pandas numpy colorama tqdm
```

## Paths

Self-contained — `WORKING_DIR = Path(__file__).resolve().parent`. Inputs, outputs, logs, and data files all sit alongside `TM_csv_builder.py`:

- `input/` — source PDFs (filename prefix `A` / `B` selects gazette schema)
- `csv/` — one output CSV per processed PDF, UTF-8-with-BOM
- `log/processing.log` — rotating log (1 MB × 5)
- `cities_by_country.json` — `{ISO2: [city, ...]}`, ~10 MB, ~525K Latin-script city names (built from GeoNames; see "Data files" below)
- `cities_overrides.json` — manual `add`/`remove` patches applied on top of the GeoNames build (survives every rebuild)
- `company_suffixes.json` — ~500 curated company-indicator tokens (Vietnamese + international)

Missing data files don't crash the script — they log an error and degrade gracefully.

## Architecture

### Pipeline (`PDFProcessor`)

1. **`extract_text_from_pdf`** — pdfplumber page-by-page; each page goes through `_extract_page_text` (column-aware, below), then `add_breaks_before_markers` injects newlines so every WIPO INID marker (`(NNN)`) starts its own line. Output: `[(page_num, line), …]`.

2. **`_extract_page_text` (column-aware)** — Critical. The Madrid certificate section of B-files uses a **two-column layout**. Flat `extract_text()` interleaves left+right at each y-coordinate, corrupting markers like `(171) 10 năm` with right-column continuations of `(531)`/`(732)`. Detection: a page is treated as 2-column when **no word's bounding box crosses the page midpoint** (`crossing < 2`). For 2-column pages, the code:
   - Finds entry boundaries via `(111)`/`(116)` markers in the left column.
   - Within each entry's y-range, emits **left-column text, then right-column text**.
   - **Within each entry, switches back to single-column from `(511)` onward**, because the Nice-classification list spans the full page width even on 2-column pages. Splitting `(511)` at the midpoint would send trailing classes into `(740)` (this was a real bug, fixed).
   - Single-column pages and A-file pages fall through to `page.extract_text()`.

3. **`process_sections`** (generator) — state-machine over the line stream, yields one `dict` per trademark. Three mutually-exclusive accumulator flags (`accumulating_511`, `accumulating_531`, `accumulating_540`) collect multi-line fields. Section-start markers determine gazette type:
   - Filename starts with `b`/`B` → gazette `B`, start markers `(111)` or `(116)`.
   - Otherwise → gazette `A`, start marker `(210)`.

4. **Per-section enrichment** before yield:
   - **`compute_511_fields`** — extracts Nice classes. Two grammars: `Nhóm NN`-style (VN A-file), or bare numeric list `"05, 12, 41."` (Madrid B). Rejoins line-wrapped Vietnamese broken words via digraph + onset-aware regex passes (`công nghiệp` stays separate, `phẩ m;` rejoins to `phẩm;`).
   - **`extract_applicant_details`** — parses `(731)`/`(732)`. Multi-applicant numbered lists (`"1. NAME1 (CC) ADDR1 2. NAME2…"`) are reduced to **first applicant only**. Country code prefers the first valid ISO 3166-1 alpha-2 token from any `(XX)` in the text (handles `MEISHANG (GZ) … (CN)` correctly). City matcher uses pre-compiled per-country alternation regex (`CITY_PATTERNS`) with `(?<!\w)…(?!\w)` boundaries — pick the LATEST match (universal rule, valid after the cities JSON was cleaned of provinces/state-codes). **VN-only fallback**: if no city matched, capture the province name from `tỉnh X` at the address tail.
   - **`classify_applicant_type`** — priority chain:
     1. Strip leading `"N. "` enumerator
     2. `STRONG_COMPANY_SUFFIXES` (curated set, ~50 unambiguous tokens) → `Company`
     3. `TYPO_TOLERANT_COMPANY_PATTERNS` (regex stems like `corp[a-z]*`, `industri[a-z]*` — catches `CORPORTION` typo, Croatian `INDUSTRIJA`) → `Company`
     4. First token ∈ `VN_SURNAMES` → `Personal`
     5. Broader JSON `COMPANY_SUFFIXES` → `Company`
     6. Otherwise → `Personal` (no `Unknown` — applicants are always one or the other)

     All suffix matching uses `(?<!\w)…(?!\w)` lookarounds with `re.IGNORECASE` so suffixes ending in punctuation (`S.R.O.`, `Co.,Ltd`) and Turkish/Unicode case quirks (`İ` → `i̇`) work correctly.

   - **`add_date_fields`** — `Month`/`Year`/`DateCombined_441_450` derived from the **first** `(441)`/`(450)` matched in the PDF (`self.first_date`). Per-file reset in `process_file`.
   - **`validate_540_content`** — `(540)` purely-numeric → blank; Vienna-code-shaped → moved into `(531)`.

5. **`create_csv`** — DataFrame, lowercases every string cell **except the `(540)` Trademark sample** column (wordmark case is meaningful), rename code columns to `"NNN <description>"`, write `utf-8-sig`. Column headers and non-string values (e.g., `Total Group` ints) are not lowercased. **Excel cell-limit handling**: `(511)` cells exceeding 32,767 characters (Excel's per-cell hard limit) are truncated in the CSV with a marker and the full text is dumped to a sidecar `<stem>_511_overflow.txt` keyed by registration number. Other columns never approach the limit. For B-files, `process_file` first partitions sections by `(116)` non-empty: domestic `(111)` rows go to `<stem>.csv`, Madrid `(116)` rows go to a parallel `<stem>_madrid.csv`. The two schemas don't overlap (every B row has exactly one of `(111)` / `(116)`), so the split is lossless and each output file is schema-clean.

### Concurrency

`ThreadPoolExecutor` is wired but `max_workers=1` is hardcoded in `main()`. Two reasons:
- pdfplumber isn't thread-safe.
- `self.first_date` lives on the `PDFProcessor` instance and is reset per file — concurrent execution would interleave reads/writes and corrupt date fields across PDFs.

## Data files

### `cities_by_country.json`

Built from GeoNames `cities500` (populated places, pop ≥500), Latin-script only (CJK / Cyrillic stripped — the gazette transcribes everything to Latin), with VN-specific enrichment:
- VN admin prefix stripping (`Thành phố Hồ Chí Minh` → `Hồ Chí Minh`)
- VN sub-city admin units dropped (`Quận Ba`, `Phường X`, `Xã Y` exclusions)
- Vietnamese diacritic normalization (`Ð` U+00D0 → `Đ` U+0110)
- HK + MO cities mirrored into the CN bucket because the gazette tags Hong Kong/Macao applicants with `(CN)`

To rebuild:
```bash
mkdir -p geonames_tmp
curl -sSfL -o geonames_tmp/cities500.zip https://download.geonames.org/export/dump/cities500.zip
unzip -o geonames_tmp/cities500.zip -d geonames_tmp/
python3 build_cities_json.py
```

Manual additions/removals (e.g., to fix a misclassified town) go in `cities_overrides.json` — they're layered on top of the GeoNames build and survive every rebuild. Shape:
```json
{ "add":    { "VN": ["Some Missing Town"] },
  "remove": { "GB": ["Street"] } }
```

### `company_suffixes.json`

~500 Latin-script tokens. Sorted, deduped (case-insensitive via NFC+casefold), mojibake-free. Includes English forms (LTD, INC, COMPANY, …), continental European (GMBH, S.A., SARL, SPA, S.R.O., Sp. z o.o., …), Vietnamese (CÔNG TY, TỔNG CÔNG TY, …), Russian transliterations (OBSHCHESTVO, OOO, …), Chinese pinyin (GONGSI, YOUXIAN), Japanese romanized (SHADANHOJIN, …), and institutional words (UNIVERSITY, INSTITUTE, BANK, FOUNDATION, …).

Curated `STRONG_COMPANY_SUFFIXES` and `TYPO_TOLERANT_COMPANY_PATTERNS` live inline in `TM_csv_builder.py` — these win over the VN-surname signal in classification.

## When changing extraction logic

- **Adding a marker**: append a `MarkerConfig` to `MARKERS`, regex to `PATTERNS`, code to `CSV_COLUMNS`. Markers absent from `PATTERNS` still match via the fallback branch in `extract_markers_from_line` but get no value transformations.
- **Date markers** (`141/151/156/181/220/441/450`): listed twice — in `extract_markers_from_line`'s reformatting branch (line ~926) and the fallback branch's date-validity guard (~1018). The guard rejects extraction artifacts like `(cid:31) MERGEFIELD …`.
- **`(531)` regex** is intentionally non-greedy with a lookahead to stop at the next marker; the older greedy version is preserved as a comment.
- **Column-aware extraction** is the single most fragile piece. If new gazette layouts emerge (e.g., 3-column, or `(511)` no longer full-width), revisit `_extract_page_text` first.

## Known residual issues

These are PDF-source-level artifacts that no parser can fix without external data:

- **~14 B rows have a Madrid registration number in `(732)`**, e.g. `"(732) 1529250 (DE) Jack Wolfskin …"` — the NOIP PDF itself transcribed a previous-registration cross-reference into the (732) line.
- **~7 B rows have only an address fragment in `(732)`** (e.g., `"503-ho, Gasan Hanwha BizMetro 2nd, …"`) — the company name simply isn't in the PDF text layer (likely rasterized image area).
- **~18 VN rows have no `Applicant City`** — both the city matcher and the `tỉnh X` province fallback found nothing. Mostly truncated addresses.

Total residual error rate: ~0.05% of rows across all files.
