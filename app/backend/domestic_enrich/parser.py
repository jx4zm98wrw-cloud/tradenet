"""Pure NOIP (IP Vietnam) trademark detail-page HTML -> DomesticRecord parser.

No I/O. Mirrors the structural approach of ``madrid_enrich.parser``: a
``_lines()`` helper tag-strips the page to a clean line stream, and a date
helper normalises NOIP's ``dd.mm.yyyy`` format. NOIP pages, unlike WIPO Madrid
Monitor, pair each field's INID label and value as *adjacent* divs::

    <div class="... product-form-label">(NNN) Label</div>
    <div class="... product-form-details">VALUE</div>

so field extraction anchors directly on the ``(NNN) Label</div>...details">``
markup. The "Tiến trình xử lý" (prosecution timeline) section is a table of
event / date / status rows.
"""

from __future__ import annotations

import html as _html
import re
from datetime import date

from pydantic import BaseModel

_TAGS_BLOCK = re.compile(r"(?is)<(script|style).*?</\1>")
_BR = re.compile(r"(?is)<br\s*/?>")
_CLOSERS = re.compile(r"(?is)</(tr|div|p|li|td|th|h\d|table|span)>")
_TAG = re.compile(r"(?is)<[^>]+>")
_WS = re.compile(r"\s+")
_DDMMYYYY = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


class DomesticRecord(BaseModel):
    application_number: str | None = None
    mark_text: str | None = None
    mark_type: str | None = None
    applicant_name: str | None = None
    applicant_address: str | None = None
    representative: str | None = None
    colors: str | None = None
    nice_classes: list[str] = []
    goods_services: dict[str, str] = {}
    vienna_codes: list[str] = []
    status_code: str | None = None
    filing_date: date | None = None
    publication_no: str | None = None
    publication_date: date | None = None
    grant_date: date | None = None
    expiry_date: date | None = None
    logo_url: str | None = None
    timeline: list[dict] = []
    raw: dict = {}


def _lines(html_src: str) -> list[str]:
    """Tag-strip ``html_src`` to a de-duped, whitespace-collapsed line stream."""
    t = _TAGS_BLOCK.sub(" ", html_src)
    t = _BR.sub("\n", t)
    t = _CLOSERS.sub("\n", t)
    t = _TAG.sub(" ", t)
    t = _html.unescape(t)
    out: list[str] = []
    for ln in t.splitlines():
        ln = _WS.sub(" ", ln).strip()
        if ln and (not out or out[-1] != ln):
            out.append(ln)
    return out


def _ddmmyyyy(s: str | None) -> date | None:
    m = _DDMMYYYY.search(s or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _clean(s: str) -> str:
    """Strip tags + entities from an HTML fragment to plain collapsed text."""
    return _WS.sub(" ", _html.unescape(_TAG.sub(" ", s))).strip()


def _details_after_label(html_src: str, code: str) -> str | None:
    """Return the raw HTML of the ``product-form-details`` div paired with the
    ``(code)`` label div. NOIP places the value div immediately after the label
    div, so we anchor on ``(code) ...</div>`` and capture the next
    ``product-form-details`` body (non-greedy, balanced enough for these pages)."""
    # Capture the details body from its opening tag up to the next field's
    # product-form-label, the closing of the detail-container, or end of input.
    # This spans the nested <div class="row"> wrappers that (511)/(531) use for
    # their per-class / per-code lists without needing balanced-div matching.
    m = re.search(
        r"\(" + re.escape(code) + r"\)[^<]*</div>\s*"
        r'<div[^>]*product-form-details[^>]*>(.*?)'
        r'(?=<div[^>]*product-form-label|</div></div></div>|\Z)',
        html_src,
        re.S | re.I,
    )
    return m.group(1) if m else None


def _strip_lang_prefix(s: str) -> str:
    """Drop a leading ``(VI)`` / ``(EN)`` language tag NOIP prepends to text."""
    return re.sub(r"^\s*\([A-Za-z]{2}\)\s*", "", s).strip()


def parse(html_src: str) -> DomesticRecord:
    rec = DomesticRecord()

    # --- Application number (also yields the VN<id> used by the logo URL). ---
    appno = re.search(r"VN\s*-?\s*(\d-\d{4}-\d{4,6})", html_src)
    if appno:
        rec.application_number = appno.group(1)

    # --- (541) mark text: "<b>(VI)</b> VTRAVEL <br/>..." -> "VTRAVEL". ---
    d541 = _details_after_label(html_src, "541")
    if d541:
        # Take the text up to the first <br/> (the (VI) line); the trailing
        # empty <b></b> is a second-language slot that is blank here.
        first = re.split(r"(?is)<br\s*/?>", d541)[0]
        txt = _strip_lang_prefix(_clean(first))
        if txt:
            rec.mark_text = txt

    # --- (550) mark type ("Combined" / "Hình"/"Chữ"). ---
    d550 = _details_after_label(html_src, "550")
    if d550:
        rec.mark_type = _clean(d550) or None

    # --- (591) colours. ---
    d591 = _details_after_label(html_src, "591")
    if d591:
        rec.colors = _clean(d591) or None

    # --- (730) applicant: "<b>(VI)</b> NAME   : ADDRESS". ---
    # The clean canonical name is also in onclick="getOtherApplicants('NAME')".
    name_attr = re.search(r"getOtherApplicants\('(.*?)'\)", html_src)
    d730 = _details_after_label(html_src, "730")
    if d730:
        txt = _strip_lang_prefix(_clean(d730))
        # Name and address are separated by " : ".
        if " : " in txt:
            nm, addr = txt.split(" : ", 1)
            rec.applicant_name = (name_attr.group(1).strip() if name_attr else nm.strip()) or None
            rec.applicant_address = addr.strip() or None
        else:
            rec.applicant_name = (name_attr.group(1).strip() if name_attr else txt) or None
    elif name_attr:
        rec.applicant_name = name_attr.group(1).strip() or None

    # --- (740) representative. ---
    d740 = _details_after_label(html_src, "740")
    if d740:
        rep = _strip_lang_prefix(_clean(d740))
        # Representative is "NAME : ADDRESS"; keep the name portion.
        rep_name = rep.split(" : ", 1)[0].strip() if " : " in rep else rep
        rec.representative = rep_name or None

    # --- (511) Nice classes + per-class goods. Each class is an
    # <a ... rel="NN" class="external-link"> wrapping a goods <div col-md-10>. ---
    d511 = _details_after_label(html_src, "511")
    if d511:
        classes: list[str] = []
        goods: dict[str, str] = {}
        for rel, body in re.findall(
            r'<a[^>]*\brel="(\d{1,2})"[^>]*class="[^"]*external-link[^"]*"[^>]*>(.*?)</a>',
            d511,
            re.S | re.I,
        ):
            v = int(rel)
            if not (1 <= v <= 45):
                continue
            c = f"{v:02d}"
            term = ""
            gm = re.search(r'<div[^>]*col-md-10[^>]*>(.*?)</div>', body, re.S | re.I)
            if gm:
                term = _clean(gm.group(1))
            if c not in classes:
                classes.append(c)
            if term and c not in goods:
                goods[c] = term
        rec.nice_classes = classes
        rec.goods_services = goods

    # --- (531) Vienna codes: ext-link-text spans like "03.07.07 (7)". ---
    d531 = _details_after_label(html_src, "531")
    if d531:
        codes: list[str] = []
        for span in re.findall(
            r'<span[^>]*ext-link-text[^>]*>(.*?)</span>', d531, re.S | re.I
        ):
            code = _clean(span)
            m = re.match(r"(\d{2}\.\d{2}\.\d{2})", code)
            if m and m.group(1) not in codes:
                codes.append(m.group(1))
        rec.vienna_codes = codes

    # --- (200) app no + filing date: details has
    # <span ...>VN -4-2026-00774</span><span>  08.01.2026</span>. ---
    d200 = _details_after_label(html_src, "200")
    if d200:
        rec.filing_date = _ddmmyyyy(_clean(d200))

    # --- (400) publication no + date. The details body holds an inner row
    # of col-md-4 cells: [pub_no, pub_date, ...]. ---
    d400 = _details_after_label(html_src, "400")
    if d400:
        cells = [_clean(c) for c in re.findall(r'<div[^>]*col-md-4[^>]*>(.*?)</div>', d400, re.S | re.I)]
        cells = [c for c in cells if c]
        if cells:
            rec.publication_no = cells[0] or None
        for c in cells:
            dt = _ddmmyyyy(c)
            if dt:
                rec.publication_date = dt
                break

    # --- (100) grant no + date (present only once granted). ---
    d100 = _details_after_label(html_src, "100")
    if d100:
        rec.grant_date = _ddmmyyyy(_clean(d100))

    # --- (180) expiry date. ---
    d180 = _details_after_label(html_src, "180")
    if d180:
        rec.expiry_date = _ddmmyyyy(_clean(d180))

    # --- Status: the "Trạng thái" row value (numeric code e.g. 1904, or a
    # Vietnamese phrase e.g. "Cấp bằng"). Not an INID-coded field. ---
    status = re.search(
        r'Tr[^<]*ng th[^<]*i</div>\s*<div[^>]*product-form-details[^>]*>(.*?)</div>',
        html_src,
        re.S | re.I,
    )
    if status:
        sv = _clean(status.group(1))
        if sv:
            rec.status_code = sv

    # --- Logo URL: .../service/trademarks/application/<VNid>/logo... ---
    logo = re.search(r"""['"]([^'"]*?/trademarks/application/[^'"]*?/logo[^'"]*)['"]""", html_src)
    if logo:
        rec.logo_url = logo.group(1)

    # --- Prosecution timeline ("Tiến trình xử lý"): rows of (event, date,
    # status) inside the events-section table. ---
    rec.timeline = _parse_timeline(html_src)

    rec.raw = {"line_count": len(_lines(html_src))}
    return rec


def _parse_timeline(html_src: str) -> list[dict]:
    sec = re.search(
        r'events-section(.*?)(?:description-section|claims-section|</body>)',
        html_src,
        re.S | re.I,
    )
    scope = sec.group(1) if sec else html_src
    out: list[dict] = []
    for row in re.findall(r"<tr>(.*?)</tr>", scope, re.S | re.I):
        cells = [_clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if len(cells) >= 2 and (cells[0] or cells[1]):
            out.append(
                {
                    "event": cells[0],
                    "date": cells[1] if len(cells) > 1 else "",
                    "status": cells[2] if len(cells) > 2 else "",
                }
            )
    return out
