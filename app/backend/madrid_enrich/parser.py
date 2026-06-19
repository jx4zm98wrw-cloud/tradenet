"""Pure WIPO Madrid Monitor HTML -> MadridRecord parser (no I/O).

The page is server-rendered and labels every field with its WIPO INID code
(540 mark, 151 reg date, 180 expiry, 732 holder, 811 nationality, 842 legal
nature, 740 representative, 511 Nice + goods, 822 basic reg, 832 designations,
270 language). We tag-strip to a line stream and anchor on those codes. The
Transaction History section is a sequence of typed events, each headed by
"<type...>, <ccs> : <dd.mm.yyyy>, <yyyy>/<n> Gaz".
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
_INID = re.compile(r"^\d{3}$")
_EVENT_DATE = re.compile(r"^:?\s*(?P<d>\d{2}\.\d{2}\.\d{4}),\s*(?P<gaz>\d{4}/\d+)\s*Gaz")
_DDMMYYYY = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


class MadridRecord(BaseModel):
    irn: str | None = None
    mark_text: str | None = None
    holder_name: str | None = None
    holder_address: str | None = None
    holder_country: str | None = None
    holder_legal_status: str | None = None
    representative: str | None = None
    registration_date: date | None = None
    expiration_date: date | None = None
    nice_classes: list[str] = []
    goods_services: dict[str, str] = {}
    designated_countries: list[str] = []
    basic_registration: str | None = None
    language: str | None = None
    transaction_history: list[dict] = []
    designation_status: dict = {}
    raw: dict = {}


def _lines(html_src: str) -> list[str]:
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


def _ddmmyyyy(s: str) -> date | None:
    m = _DDMMYYYY.search(s or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _value_after(lines: list[str], i: int) -> str:
    """Join the value lines after a code+label pair until the next INID code."""
    vals = []
    j = i + 2  # skip code line (i) and its human label (i+1)
    while j < len(lines) and not _INID.match(lines[j]):
        if lines[j] == "Transaction History":
            break
        vals.append(lines[j])
        j += 1
    return " ".join(vals).strip()


def parse(html_src: str) -> MadridRecord:
    lines = _lines(html_src)
    rec = MadridRecord()

    # Split summary vs transaction history. The label appears once as a nav
    # header near the top and again as the real section heading; the real
    # section is the LAST occurrence.
    th_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "Transaction History":
            th_idx = i
            break
    summary = lines[:th_idx]

    for i, ln in enumerate(summary):
        if not _INID.match(ln):
            continue
        code, val = ln, _value_after(summary, i)
        if code == "151" and rec.registration_date is None:
            rec.registration_date = _ddmmyyyy(val)
        elif code == "180" and rec.expiration_date is None:
            rec.expiration_date = _ddmmyyyy(val)
        elif code == "732" and not rec.holder_name:
            # The holder NAME is the first value line; the following lines are the
            # street / postcode / city / country. The old "split at the first
            # digit" rule mashed the name together with the street (e.g.
            # "Société Jas Hennessy & Co. rue de la Richonne F-").
            first = summary[i + 2].strip() if i + 2 < len(summary) and not _INID.match(summary[i + 2]) else ""
            rec.holder_name = first.rstrip(",") or val
            # Address = the value with the name line removed.
            rest = val[len(first) :].strip() if first and val.startswith(first) else val
            rec.holder_address = rest or None
            # Holder country = the ISO code in the trailing "(CC)" of the address
            # (always present); 811/812 below are fallbacks.
            cc = re.search(r"\(([A-Za-z]{2})\)\s*$", val)
            if cc:
                rec.holder_country = cc.group(1).upper()
        elif code in ("811", "812") and not rec.holder_country:
            # 811 = holder nationality, 812 = country of establishment. Either is
            # an acceptable holder country; some records carry only one.
            rec.holder_country = val[:2].upper() if val else None
        elif code == "842" and not rec.holder_legal_status:
            rec.holder_legal_status = val
        elif code == "740" and not rec.representative:
            rec.representative = val
        elif code == "270" and not rec.language:
            rec.language = val
        elif code == "511" and not rec.nice_classes:
            # Drop the "NCL(10-2015)" Nice-edition token before reading the
            # actual class number, otherwise the edition year leaks in.
            cleaned = re.sub(r"NCL\([^)]*\)", " ", val)
            rec.nice_classes = re.findall(r"\b(\d{2})\b", cleaned)[:1]
        elif code == "822" and not rec.basic_registration:
            rec.basic_registration = val
        elif code == "832":
            for cc in re.findall(r"\b([A-Z]{2})\b", val):
                if cc not in rec.designated_countries:
                    rec.designated_countries.append(cc)

    # Authoritative Nice classes: the summary table's "Nice classes" cell holds
    # WIPO's clean comma-separated list (e.g. "21, 32, 33"). The INID 511 field
    # packs every class's goods text into one blob, so scraping it for class
    # numbers is lossy (we only ever caught the first). Prefer the cell,
    # normalized to the 2-digit zero-padded form used elsewhere. The 511
    # first-class read above remains a fallback when no cell is present.
    nice_cell = re.search(r'<td[^>]*class="[^"]*\bnice\b[^"]*"[^>]*>(.*?)</td>', html_src, re.S | re.I)
    if nice_cell:
        classes: list[str] = []
        for n in re.findall(r"\d{1,2}", re.sub(r"<[^>]+>", " ", nice_cell.group(1))):
            v = int(n)
            c = f"{v:02d}"
            if 1 <= v <= 45 and c not in classes:
                classes.append(c)
        if classes:
            rec.nice_classes = classes

    # Per-class goods & services full text. The first "BASICGS" goods list is the
    # basic registration; later <dl> blocks are subsequent-designation
    # limitations and must not override it. Within the basic list each Nice class
    # is a <dd nice="NN"> whose English term sits in <p class="…GSTERMEN" lang="EN">.
    basic_gs = re.search(r"<dl[^>]*\bBASICGS\b[^>]*>(.*?)</dl>", html_src, re.S | re.I)
    gs_scope = basic_gs.group(1) if basic_gs else html_src
    # WIPO publishes each Nice class's goods term as <p class="…gsterm…GSTERM<LANG>…"
    # nice="NN" lang="XX">. Collect every language, then prefer the English
    # translation but fall back to whatever WIPO provides: French-origin marks
    # (e.g. ROLEX's "ESPRIT D'ENTREPRISE") carry goods only as GSTERMFR/lang="FR".
    # Matching only GSTERMEN/lang="EN" silently dropped per-class detail for every
    # non-English-origin Madrid mark.
    by_class: dict[str, dict[str, str]] = {}
    for cls, lang, body in re.findall(
        r'<p[^>]*\bgsterm\b[^>]*nice="(\d+)"[^>]*lang="([A-Za-z]{2})"[^>]*>(.*?)</p>',
        gs_scope,
        re.S | re.I,
    ):
        text = _WS.sub(" ", _html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
        if text:
            by_class.setdefault(f"{int(cls):02d}", {})[lang.upper()] = text
    for c, langs in by_class.items():
        if c not in rec.goods_services:
            rec.goods_services[c] = langs.get("EN") or next(iter(langs.values()))

    # Mark text from the page title line "1266721- Clalen".
    for ln in lines[:30]:
        m = re.match(r"^\d{6,}\s*-\s*(.+)$", ln)
        if m:
            rec.mark_text = m.group(1).strip()
            break

    # Language (270) lives in the original-registration event, not the summary
    # block; read the first 270 anywhere in the document.
    if not rec.language:
        for i, ln in enumerate(lines):
            if ln == "270" and i + 2 < len(lines):
                # 270 is a single-line value ("English"); the next non-label
                # line begins the following event, so take just one line.
                rec.language = lines[i + 2].strip() or None
                if rec.language:
                    break

    rec.transaction_history = _parse_history(lines[th_idx:])
    # designated_countries is the UNION of all summary 832 blocks (above) plus
    # every transaction-history event's parties AND designations. Old Madrid
    # Agreement / Article 9sexies records carry the designated set (incl. VN) in
    # the International Registration event header / 9sexies designation lists,
    # not in a plain 832 designations sub-field — accruing parties too is what
    # catches them. A country appearing as an event party (grant/refusal/IR/
    # subsequent/renewal) or designation is, by definition, designated. Preserve
    # insertion order, de-dupe.
    for ev in rec.transaction_history:
        for cc in (ev.get("parties") or []) + (ev.get("designations") or []):
            if cc not in rec.designated_countries:
                rec.designated_countries.append(cc)
    rec.designation_status = _designation_status(rec.designated_countries, rec.transaction_history)
    rec.raw = {"line_count": len(lines)}
    return rec


def _designation_status(countries: list[str], history: list[dict]) -> dict:
    """Per-country protection status backing the status-by-jurisdiction UI.

    For each designated country, scan the transaction history for grant/refusal
    events naming it. Prefer the EARLIEST-dated grant/refusal (events sorted by
    ISO date), not document order. A designated country with neither event is
    pending.
    """
    events = sorted(history or [], key=lambda e: e.get("date") or "")
    out: dict = {}
    for cc in countries or []:
        status: dict = {"status": "pending", "date": None, "gazette": None}
        for ev in events:
            if cc not in (ev.get("parties") or []):
                continue
            t = (ev.get("type") or "").lower()
            if "grant of protection" in t:
                status = {
                    "status": "granted",
                    "date": ev.get("date"),
                    "gazette": ev.get("gazette"),
                }
                break
            if "refusal" in t:
                status = {
                    "status": "refused",
                    "date": ev.get("date"),
                    "gazette": ev.get("gazette"),
                }
                break
        out[cc] = status
    return out


def _parse_history(lines: list[str]) -> list[dict]:
    events: list[dict] = []
    i = 0
    while i < len(lines) - 1:
        head = lines[i]
        dm = None
        if i + 1 < len(lines):
            dm = _EVENT_DATE.match(lines[i + 1])
        if dm is None and i + 2 < len(lines):
            dm = _EVENT_DATE.match(lines[i + 2])
        if "," in head and dm and not _INID.match(head):
            typ = head.rstrip(" :")
            tail_ccs = re.findall(r"\b([A-Z]{2})\b", typ.split(",", 1)[1]) if "," in typ else []
            block_end = _next_event(lines, i + 1)
            block = lines[i:block_end]
            events.append(
                {
                    "type": typ,
                    "date": _iso(dm.group("d")),
                    "gazette": dm.group("gaz"),
                    "parties": _field(block, "833") or tail_ccs,
                    "designations": _field(block, "832"),
                }
            )
            i = block_end
        else:
            i += 1
    return events


def _next_event(lines: list[str], start: int) -> int:
    for j in range(start + 1, len(lines) - 1):
        is_head = "," in lines[j] and not _INID.match(lines[j])
        has_date = _EVENT_DATE.match(lines[j + 1]) or (j + 2 < len(lines) and _EVENT_DATE.match(lines[j + 2]))
        if is_head and has_date:
            return j
    return len(lines)


def _field(block: list[str], code: str) -> list[str]:
    for k, ln in enumerate(block):
        if ln == code and k + 2 < len(block):
            # Collect every continuation line from k+2 up to (but excluding) the
            # next 3-digit INID code, then findall across the joined text — multi-
            # country 832/833 values wrap onto several lines ("EG", "- IN", ...).
            vals = []
            j = k + 2
            while j < len(block) and not _INID.match(block[j]):
                vals.append(block[j])
                j += 1
            return re.findall(r"\b([A-Z]{2})\b", " ".join(vals))
    return []


def _iso(ddmmyyyy: str) -> str:
    m = _DDMMYYYY.search(ddmmyyyy or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ddmmyyyy
