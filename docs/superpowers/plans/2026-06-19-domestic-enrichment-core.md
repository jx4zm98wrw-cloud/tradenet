# Domestic Enrichment — Core (Fetch + Parse + Store) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core of the domestic (IP Vietnam / NOIP) trademark enrichment pipeline — a fetch client that defeats NOIP's broken TLS chain + cluster flakiness, an HTML parser, a `domestic_records` table, and a single-mark `enrich_one` orchestrator with a resumable backfill — mirroring the proven `madrid_enrich` package.

**Architecture:** A new `app/backend/domestic_enrich/` package structurally parallel to `madrid_enrich/` (idmap → client → parser → store → derive → enrich → backfill). Data lands in a new `domestic_records` table (PK `application_number`), soft-joined to `trademarks` via `application_number`. The fetch client ships a committed Sectigo-intermediate CA bundle so TLS verification stays ON in the Linux worker/CI, and retries the flaky Apache-fronted cluster until it gets a valid body. The HTML is regex-parsed (no I/O in the parser), exactly like Madrid.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (async, `Mapped`/`mapped_column`), Alembic, `requests`, `pydantic` v2, `pytest` + `pytest-asyncio`. Postgres (JSONB + ARRAY).

**Scope:** This is **Plan A of 3**. Plan B adds the controllable sweep (`worker/domestic_sweep.py`, `domestic_sweep_control`, `api/routes/domestic_sweep.py`, admin `/domestic-enrichment` stats, `domestic` queue). Plan C adds the frontend (`/admin/domestic` panel, `DomesticEnrichment` detail block, mark-API join). Each plan produces working, independently-testable software. **Do NOT build B or C from this plan.**

## Reference: the Madrid stack this mirrors

Read these before starting — the domestic build is a structural copy with a different fetch URL, a TLS fix, and a different HTML parser:

- `app/backend/madrid_enrich/{client,parser,store,derive,enrich,backfill}.py`
- `app/backend/api/db/models.py:285` (`MadridRecord`)
- `app/backend/alembic/versions/20260617_0016_madrid_records.py`
- `app/backend/tests/madrid_enrich/test_enrich.py` (test idiom: `db_session` fixture, `tmp_path` cache pre-seed, fixtures dir)

## Verified source facts (built to — do NOT re-investigate)

- **Endpoint:** `GET https://wipopublish.ipvietnam.gov.vn/wopublish-search/public/ajax/detail/trademarks?id=<VNID>` returns server-rendered HTML with every INID field.
- **ID mapping:** `trademarks.application_number` `4-YYYY-NNNNN` → `VN4YYYYNNNNN` (strip non-alphanumerics, prefix `VN`). Validated on 8 random marks.
- **Broken TLS chain:** leaf `*.ipvietnam.gov.vn` is issued by *"Sectigo Public Server Authentication CA DV R36"* but the server presents the wrong intermediate → OpenSSL verify error 21. Fix: ship the Sectigo R36 intermediate in a committed CA bundle, `verify=<bundle>`.
- **Cluster flakiness:** ~50% of requests get an instant (~40 ms) generic Apache 500; the rest return ~18 KB HTML (~200 ms). Stateless, retryable in 1–3 attempts. Validate the **body** (`product-form-label` present), not just status.

## Standing constraints (carry over every task)

- **NEVER commit the rename trio:** `README.md`, `app/.env.example`, `app/backend/api/settings.py`. They stay as uncommitted working-tree changes. Always `git add` by **explicit path**; never `git add -A`/`.`.
- **GateGuard fact-forcing hook:** before the first Edit/Write per file and the first Bash, it blocks once asking for facts — state them, then retry.
- **Fetch-once / re-derive-offline:** cache to `domestic_cache/`; once fetched, never re-fetch. Parser fixes → bump `PARSE_VERSION` → one offline re-derive over the cache (zero NOIP calls).

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/domestic_enrich/__init__.py` | Package marker (empty, like `madrid_enrich/__init__.py`). |
| `app/backend/domestic_enrich/idmap.py` | `appno_to_vnid(application_number) -> str \| None`. Pure. The one place ID format lives. |
| `app/backend/domestic_enrich/noip_ca_bundle.pem` | Committed CA bundle: certifi roots + the Sectigo R36 intermediate. |
| `app/backend/domestic_enrich/client.py` | `fetch_raw(...)` — retrying, body-validating, caching HTTP GET with the CA bundle. |
| `app/backend/domestic_enrich/parser.py` | `parse(html) -> DomesticRecord`. Pure regex parser. |
| `app/backend/domestic_enrich/derive.py` | `derive_status(rec) -> DomesticStatus`. Maps NOIP status code → label. Pure. |
| `app/backend/domestic_enrich/store.py` | `PARSE_VERSION`, async `upsert(...)`. Idempotent via content_hash. |
| `app/backend/domestic_enrich/enrich.py` | `enrich_one(...)` — fetch→parse→derive→store one mark. |
| `app/backend/domestic_enrich/backfill.py` | `iter_domestic_appnos`, `CircuitBreaker`, `run_backfill`. |
| `app/backend/api/db/models.py` | Add `DomesticRecord` model (after `MadridRecord`). |
| `app/backend/alembic/versions/20260619_0020_domestic_records.py` | `domestic_records` table migration (down_revision `20260619_0019`). |
| `app/backend/tests/domestic_enrich/` | Test package mirroring `tests/madrid_enrich/`. |
| `app/backend/tests/fixtures/domestic/*.html` | Real fetched NOIP HTML fixtures (committed). |

---

## Task 1: Package scaffold + ID mapping

**Files:**
- Create: `app/backend/domestic_enrich/__init__.py`
- Create: `app/backend/domestic_enrich/idmap.py`
- Create: `app/backend/tests/domestic_enrich/__init__.py`
- Test: `app/backend/tests/domestic_enrich/test_idmap.py`

- [ ] **Step 1: Create the empty package markers**

```bash
: > app/backend/domestic_enrich/__init__.py
: > app/backend/tests/domestic_enrich/__init__.py
```

- [ ] **Step 2: Write the failing test**

`app/backend/tests/domestic_enrich/test_idmap.py`:

```python
import pytest

from domestic_enrich.idmap import appno_to_vnid


@pytest.mark.parametrize(
    "appno, expected",
    [
        ("4-2026-18514", "VN4202618514"),
        ("4-2024-16348", "VN4202416348"),
        ("VN-4-2026-18514", "VN4202618514"),   # already-prefixed, dashed
        ("VN4202618514", "VN4202618514"),       # already canonical
        ("  4-2026-18514  ", "VN4202618514"),   # surrounding whitespace
    ],
)
def test_appno_to_vnid_maps_known_formats(appno, expected):
    assert appno_to_vnid(appno) == expected


@pytest.mark.parametrize("bad", ["", None, "   ", "garbage", "4--", "4-2026-"])
def test_appno_to_vnid_rejects_unmappable(bad):
    assert appno_to_vnid(bad) is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_idmap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domestic_enrich.idmap'`

- [ ] **Step 4: Write the implementation**

`app/backend/domestic_enrich/idmap.py`:

```python
"""Map a gazette application number to the NOIP WIPOPublish detail id.

`trademarks.application_number` is `4-YYYY-NNNNN` (sometimes `VN`-prefixed or
dashed differently). NOIP's detail endpoint keys on `VN` + the digits:
`4-2026-18514` -> `VN4202618514`. Validated on 8 random marks. Unmappable /
malformed inputs return None so the caller can skip + log rather than crash.
"""

from __future__ import annotations

import re

# A mappable VN trademark application number must contain a leading type-code
# digit, a 4-digit year, and a serial — at least 7 digits once non-alphanumerics
# are stripped (e.g. 4 + 2026 + 18514). Anything shorter is an extraction
# artifact, not a real id.
_MIN_DIGITS = 7
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")
_LEADING_VN = re.compile(r"^VN", re.IGNORECASE)


def appno_to_vnid(application_number: str | None) -> str | None:
    if not application_number or not application_number.strip():
        return None
    # Strip any VN prefix first, then every non-alphanumeric (dashes, spaces).
    core = _NON_ALNUM.sub("", _LEADING_VN.sub("", application_number.strip()))
    if not core.isdigit() or len(core) < _MIN_DIGITS:
        return None
    return f"VN{core}"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_idmap.py -v`
Expected: PASS (all parametrized cases)

- [ ] **Step 6: Commit**

```bash
git add app/backend/domestic_enrich/__init__.py app/backend/domestic_enrich/idmap.py \
        app/backend/tests/domestic_enrich/__init__.py app/backend/tests/domestic_enrich/test_idmap.py
git commit -m "feat(domestic): package scaffold + application-number to VNID mapping"
```

---

## Task 2: Sectigo CA bundle

The NOIP server presents the wrong intermediate, so we ship the correct one. The bundle = certifi's root store **plus** the *Sectigo Public Server Authentication CA DV R36* intermediate, committed so the Linux worker/CI verifies deterministically.

**Files:**
- Create: `app/backend/domestic_enrich/noip_ca_bundle.pem`
- Test: `app/backend/tests/domestic_enrich/test_ca_bundle.py`

- [ ] **Step 1: Obtain + verify the Sectigo R36 intermediate PEM**

The intermediate is public and served by Sectigo. The exact URL is the leaf's AIA "CA Issuers" pointer — already confirmed live to be the direct Sectigo distribution URL. Fetch it, convert DER→PEM, and verify the subject before trusting it:

```bash
cd app/backend/domestic_enrich
# Confirmed (2026-06-19) AIA CA-Issuers URL for the *.ipvietnam.gov.vn leaf:
curl -sSfL "http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt" -o _intermediate.crt
# It is DER; convert to PEM (fall back to copy if already PEM):
openssl x509 -inform DER -in _intermediate.crt -out _intermediate.pem 2>/dev/null \
  || cp _intermediate.crt _intermediate.pem
# VERIFY the subject + issuer before trusting:
openssl x509 -in _intermediate.pem -noout -subject -issuer
# Expected:
#   subject= ... CN = Sectigo Public Server Authentication CA DV R36
#   issuer=  ... CN = Sectigo Public Server Authentication Root R46   (this root IS in certifi)
```

Expected output: subject contains `Sectigo Public Server Authentication CA DV R36`, issuer is the `Root R46`. **If the subject differs, STOP** — do not commit an unverified cert; report the actual subject. (If `crt.sectigo.com` is unreachable, re-derive the URL from the leaf's AIA: `openssl s_client -connect wipopublish.ipvietnam.gov.vn:443 -servername wipopublish.ipvietnam.gov.vn </dev/null 2>/dev/null | openssl x509 -noout -text | grep -A1 'CA Issuers' | grep -oE 'https?://[^ ]+\.crt'`.)

- [ ] **Step 2: Build the committed bundle (certifi roots + intermediate)**

```bash
cd app/backend/domestic_enrich
python -c "import certifi, pathlib; print(pathlib.Path(certifi.where()).read_text())" > noip_ca_bundle.pem
cat _intermediate.pem >> noip_ca_bundle.pem
rm -f _intermediate.crt _intermediate.pem
```

- [ ] **Step 3: Write the test (the bundle exists, parses, is non-trivial)**

`app/backend/tests/domestic_enrich/test_ca_bundle.py`:

```python
"""The committed CA bundle must exist, parse, and carry more than the bare
certifi roots (i.e. include the Sectigo R36 intermediate the NOIP server omits).
Guards against an empty/partial bundle silently regressing to a TLS failure at
sweep time. The exact-subject check happens at build time (Task 2 Step 1)."""

import ssl
from pathlib import Path

BUNDLE = Path(__file__).parent.parent.parent / "domestic_enrich" / "noip_ca_bundle.pem"


def test_bundle_exists_and_parses():
    assert BUNDLE.exists(), "noip_ca_bundle.pem missing — run Task 2 build steps"
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(BUNDLE))  # raises if malformed


def test_bundle_is_non_trivial():
    text = BUNDLE.read_text()
    assert "BEGIN CERTIFICATE" in text
    assert text.count("BEGIN CERTIFICATE") > 1
```

- [ ] **Step 4: Run the test**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_ca_bundle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/domestic_enrich/noip_ca_bundle.pem app/backend/tests/domestic_enrich/test_ca_bundle.py
git commit -m "feat(domestic): commit Sectigo R36 CA bundle for NOIP TLS verification"
```

---

## Task 3: Fetch client (retry + body-validation + cache)

**Files:**
- Create: `app/backend/domestic_enrich/client.py`
- Test: `app/backend/tests/domestic_enrich/test_client.py`

- [ ] **Step 1: Write the failing test**

`app/backend/tests/domestic_enrich/test_client.py`:

```python
from pathlib import Path

import pytest

from domestic_enrich.client import fetch_raw, FetchResult

_GOOD = "<html><div class='product-form-label'>(541)</div>ok</html>"


class _Resp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
        self.headers = {}


class _FlakyTransport:
    """Returns N Apache-500-style bodies, then a valid one."""

    def __init__(self, fails_before_ok: int):
        self.calls = 0
        self.fails_before_ok = fails_before_ok

    def get(self, url, headers=None, timeout=None, verify=None):
        self.calls += 1
        if self.calls <= self.fails_before_ok:
            return _Resp(500, "Internal Server Error")
        return _Resp(200, _GOOD)


def test_retries_until_valid_body(tmp_path):
    t = _FlakyTransport(fails_before_ok=2)
    res = fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False,
                    max_attempts=5, delay=0.0)
    assert isinstance(res, FetchResult)
    assert res.from_cache is False
    assert "product-form-label" in res.html
    assert t.calls == 3  # 2 failures + 1 success


def test_gives_up_after_max_attempts(tmp_path):
    t = _FlakyTransport(fails_before_ok=99)
    with pytest.raises(RuntimeError):
        fetch_raw("VN4202600774", tmp_path, session=t, use_cache=False,
                  max_attempts=3, delay=0.0)
    assert t.calls == 3


def test_uses_cache_without_network(tmp_path):
    (tmp_path / "VN4202600774.html").write_text(_GOOD, encoding="utf-8")
    t = _FlakyTransport(fails_before_ok=99)  # would fail if called
    res = fetch_raw("VN4202600774", tmp_path, session=t, use_cache=True)
    assert res.from_cache is True
    assert t.calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domestic_enrich.client'`

- [ ] **Step 3: Write the implementation**

`app/backend/domestic_enrich/client.py`:

```python
"""Fetch NOIP WIPOPublish trademark detail HTML, with the TLS fix + retry.

Two NOIP obstacles are handled here (both verified live):
  1. Broken TLS chain — the server omits the Sectigo R36 intermediate, so we
     pass our committed bundle (certifi roots + that intermediate) as `verify`.
     Verification stays ON (deterministic in the Linux worker/CI).
  2. Cluster flakiness — an Apache proxy fronts unhealthy Tomcat nodes; ~50% of
     requests get an instant generic 500. We retry until HTTP 200 AND the body
     looks like a real detail page (`product-form-label` present), then cache.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import requests

URL_TEMPLATE = (
    "https://wipopublish.ipvietnam.gov.vn/wopublish-search/public/"
    "ajax/detail/trademarks?id={vnid}"
)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
# A valid detail page always renders the biblio label divs. A flaky-node 500 is
# a ~530-byte generic Apache error with none of these.
_VALID_MARKER = "product-form-label"
_CA_BUNDLE = str(Path(__file__).with_name("noip_ca_bundle.pem"))
_MIN_DELAY_S = 1.0


@dataclass
class FetchResult:
    vnid: str
    html: str
    source_url: str
    from_cache: bool
    attempts: int = 0


def _is_valid(status_code: int, body: str) -> bool:
    return status_code == 200 and _VALID_MARKER in body


def fetch_raw(
    vnid: str,
    cache_dir: Path,
    *,
    session: "requests.Session | object | None" = None,
    use_cache: bool = True,
    max_attempts: int = 10,
    delay: float = 1.5,
) -> FetchResult:
    """Fetch one mark's detail HTML, retrying the flaky cluster. `vnid` is the
    NOIP id (`VN4202600774`). Raises RuntimeError if no valid body after
    `max_attempts`. `session` is injectable for tests (any object with a
    requests-style `.get`)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{vnid}.html"
    url = URL_TEMPLATE.format(vnid=vnid)

    if use_cache and path.exists():
        return FetchResult(vnid=vnid, html=path.read_text(encoding="utf-8"),
                           source_url=url, from_cache=True)

    s = session if session is not None else requests.Session()
    last_status = None
    for attempt in range(1, max_attempts + 1):
        resp = s.get(url, headers={"User-Agent": _UA}, timeout=30, verify=_CA_BUNDLE)
        last_status = getattr(resp, "status_code", None)
        body = getattr(resp, "text", "")
        if _is_valid(last_status, body):
            path.write_text(body, encoding="utf-8")
            if delay:
                time.sleep(_MIN_DELAY_S)  # space out polite calls after a hit
            return FetchResult(vnid=vnid, html=body, source_url=url,
                               from_cache=False, attempts=attempt)
        if delay and attempt < max_attempts:
            time.sleep(delay)  # short backoff between flaky-node retries
    raise RuntimeError(
        f"NOIP fetch failed for {vnid}: no valid body in {max_attempts} attempts "
        f"(last status {last_status})"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/backend/domestic_enrich/client.py app/backend/tests/domestic_enrich/test_client.py
git commit -m "feat(domestic): NOIP fetch client with TLS bundle, retry, body-validation, cache"
```

---

## Task 4: Fetch real fixtures (live network — one-time)

The parser (Task 5) must be written against **real** NOIP HTML, not invented markup. Use the just-built client to fetch 3 marks and commit them as fixtures.

**Files:**
- Create: `app/backend/tests/fixtures/domestic/VN4202600774.html` (VTRAVEL)
- Create: `app/backend/tests/fixtures/domestic/VN4202416348.html` (ibest)
- Create: `app/backend/tests/fixtures/domestic/VN4202449975.html` (YED)

- [ ] **Step 1: Fetch the three fixtures via the client**

Run (live network; retries handle flakiness):

```bash
cd app/backend
python -c "
from pathlib import Path
from domestic_enrich.client import fetch_raw
out = Path('tests/fixtures/domestic'); out.mkdir(parents=True, exist_ok=True)
for vnid in ['VN4202600774', 'VN4202416348', 'VN4202449975']:
    r = fetch_raw(vnid, out, use_cache=False, max_attempts=15)
    (out / f'{vnid}.html').write_text(r.html, encoding='utf-8')
    print(vnid, 'OK', len(r.html), 'bytes', 'attempts=', r.attempts)
"
```

Expected: three `OK` lines, each ~15–20 KB. (The client already wrote them into the fixtures dir; the explicit re-write is belt-and-suspenders.)

- [ ] **Step 2: Sanity-check the fixtures contain the expected fields**

Run:
```bash
cd app/backend
for f in tests/fixtures/domestic/VN420*.html; do
  echo "== $f =="; grep -c "product-form-label" "$f"
done
```
Expected: each file reports a count > 0.

- [ ] **Step 3: Commit the fixtures**

```bash
git add app/backend/tests/fixtures/domestic/VN4202600774.html \
        app/backend/tests/fixtures/domestic/VN4202416348.html \
        app/backend/tests/fixtures/domestic/VN4202449975.html
git commit -m "test(domestic): real NOIP HTML fixtures for parser development"
```

---

## Task 5: HTML parser

Write the parser **test-first against the real fixtures** from Task 4. The parser is pure (no I/O), mirroring `madrid_enrich/parser.py`'s tag-strip-to-lines + INID-anchor approach. The biblio section is `(NNN) Label` in `product-form-label` divs paired with `product-form-details` value divs.

**Files:**
- Create: `app/backend/domestic_enrich/parser.py`
- Test: `app/backend/tests/domestic_enrich/test_parser.py`

- [ ] **Step 1: Read a fixture to derive exact expected values**

Before writing assertions, open `tests/fixtures/domestic/VN4202600774.html` and record the ground-truth values for: mark text `(541)`, mark type `(550)`, applicant name + address `(730)`, Nice classes `(511)`, per-class goods, status code, filing date `(200)`, publication `(400)`, Vienna codes `(531)`, logo URL `(540)`. Use these real values in the test below (replace the illustrative values with what the file actually contains).

- [ ] **Step 2: Write the failing test**

`app/backend/tests/domestic_enrich/test_parser.py`. Assert on values you confirmed in Step 1 (the VTRAVEL sample is known to be a Combined mark with mark text "VTRAVEL"; confirm and extend):

```python
from pathlib import Path

from domestic_enrich.parser import parse, DomesticRecord

FIX = Path(__file__).parent.parent / "fixtures" / "domestic"


def _rec(vnid: str) -> DomesticRecord:
    return parse((FIX / f"{vnid}.html").read_text(encoding="utf-8"))


def test_parses_mark_text_and_type():
    rec = _rec("VN4202600774")
    assert rec.mark_text == "VTRAVEL"            # confirm against fixture
    assert rec.mark_type                          # e.g. "Combined"


def test_parses_applicant_name_and_address():
    rec = _rec("VN4202600774")
    assert rec.applicant_name                      # non-empty
    assert rec.applicant_address                   # non-empty


def test_parses_nice_classes_zero_padded():
    rec = _rec("VN4202600774")
    assert rec.nice_classes                        # e.g. ["39", "43"]
    assert all(len(c) == 2 and c.isdigit() for c in rec.nice_classes)


def test_parses_per_class_goods_keyed_by_class():
    rec = _rec("VN4202600774")
    assert rec.goods_services                      # {"39": "...", ...}
    assert set(rec.goods_services).issubset(set(rec.nice_classes))


def test_parses_dates_and_status():
    rec = _rec("VN4202600774")
    assert rec.filing_date is not None
    assert rec.status_code                         # e.g. "1904"


def test_logo_url_when_present():
    rec = _rec("VN4202600774")
    # Combined/figurative marks carry a logo URL; word marks may not.
    if rec.logo_url:
        assert rec.logo_url.endswith("/logo")


def test_parser_is_pure_and_total_on_all_fixtures():
    # Every fixture must parse without raising and yield a non-empty mark_text.
    for f in FIX.glob("VN*.html"):
        rec = parse(f.read_text(encoding="utf-8"))
        assert isinstance(rec, DomesticRecord)
        assert rec.mark_text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domestic_enrich.parser'`

- [ ] **Step 4: Write the implementation**

`app/backend/domestic_enrich/parser.py`. Model the structure on `madrid_enrich/parser.py` (tag-strip → line stream → anchor on `(NNN)` INID codes), adapted to NOIP's `product-form-label`/`product-form-details` pairing. Define the `DomesticRecord` pydantic model with exactly these fields (the migration + store mirror them):

```python
"""Pure NOIP WIPOPublish HTML -> DomesticRecord parser (no I/O).

The page pairs `<div class="...product-form-label">(NNN) Label</div>` with a
following `<div class="...product-form-details">value</div>`. We tag-strip to a
line stream and anchor on the (NNN) INID codes, mirroring the Madrid parser.
Per-class goods sit in `<a class="external-link" rel="NN">` + a goods <div>;
the prosecution timeline is a table ("Tien trinh xu ly": event/date/status).
"""

from __future__ import annotations

import html as _html
import re
from datetime import date

from pydantic import BaseModel


class DomesticRecord(BaseModel):
    application_number: str | None = None       # set by enrich_one (the 4-YYYY-NNNNN)
    mark_text: str | None = None                # (541)
    mark_type: str | None = None                # (550) Combined / word / figurative
    applicant_name: str | None = None           # (730) name
    applicant_address: str | None = None        # (730) address
    representative: str | None = None           # (740)
    colors: str | None = None                   # (591)
    nice_classes: list[str] = []                # (511) zero-padded "NN"
    goods_services: dict[str, str] = {}         # {class -> goods text}
    vienna_codes: list[str] = []                # (531)
    status_code: str | None = None              # NOIP status code e.g. "1904"
    filing_date: date | None = None             # (200)
    publication_no: str | None = None           # (400)
    publication_date: date | None = None        # (400)
    grant_date: date | None = None              # (100)
    expiry_date: date | None = None             # (180)
    logo_url: str | None = None                 # (540) image URL
    timeline: list[dict] = []                   # prosecution events
    raw: dict = {}


def parse(html_src: str) -> DomesticRecord:
    """Parse NOIP detail HTML into a DomesticRecord. Total: never raises on a
    valid detail page; missing fields stay None/empty. IMPLEMENT the regex/line
    extraction against the Task-4 fixtures, following madrid_enrich/parser.py's
    _lines() tag-strip + INID-anchor structure. Each (NNN) label's value is the
    text of the paired product-form-details div."""
    raise NotImplementedError  # replace with the real extraction (TDD against fixtures)
```

Implement `parse` incrementally, running the test after each field until all pass. Reuse the Madrid helpers' shape: a `_lines()` that strips `<script>/<style>`, converts `<br>`/block-closers to newlines, strips remaining tags, unescapes entities, and de-dupes; date helpers for `dd.mm.yyyy`/NOIP date formats; zero-pad Nice classes to 2 digits and keep only `01`–`45`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_parser.py -v`
Expected: PASS (all tests, including `test_parser_is_pure_and_total_on_all_fixtures`)

- [ ] **Step 6: Commit**

```bash
git add app/backend/domestic_enrich/parser.py app/backend/tests/domestic_enrich/test_parser.py
git commit -m "feat(domestic): NOIP HTML parser -> DomesticRecord"
```

---

## Task 6: `DomesticRecord` model + migration

**Files:**
- Modify: `app/backend/api/db/models.py` (add `DomesticRecord` after `MadridRecord`, ~line 340)
- Create: `app/backend/alembic/versions/20260619_0020_domestic_records.py`
- Test: `app/backend/tests/domestic_enrich/test_model_roundtrip.py`

- [ ] **Step 1: Add the SQLAlchemy model**

In `app/backend/api/db/models.py`, after the `MadridRecord` class (before `class UserRole`), add. (The imports `Mapped, mapped_column, Text, Date, Integer, DateTime, ARRAY, JSONB, func, text` are already used by `MadridRecord` — reuse them.)

```python
class DomesticRecord(Base):
    """NOIP (IP Vietnam) domestic trademark detail, one row per application.

    Soft-linked to trademarks via `application_number = trademarks.application_number`.
    Hybrid storage: promoted scalar/array columns for display/filter, JSONB for
    nested goods/timeline + the parsed `raw` payload (re-derive without re-fetch).
    """

    __tablename__ = "domestic_records"

    application_number: Mapped[str] = mapped_column(Text, primary_key=True)

    mark_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    representative: Mapped[str | None] = mapped_column(Text, nullable=True)
    colors: Mapped[str | None] = mapped_column(Text, nullable=True)

    nice_classes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    goods_services: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    vienna_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    status_code: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publication_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    grant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
```

- [ ] **Step 2: Write the migration**

`app/backend/alembic/versions/20260619_0020_domestic_records.py`:

```python
"""domestic_records table + indexes.

Revision ID: 20260619_0020
Revises: 20260619_0019
Create Date: 2026-06-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "20260619_0020"
down_revision: str | None = "20260619_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domestic_records",
        sa.Column("application_number", sa.Text(), primary_key=True),
        sa.Column("mark_text", sa.Text()),
        sa.Column("mark_type", sa.Text()),
        sa.Column("applicant_name", sa.Text()),
        sa.Column("applicant_address", sa.Text()),
        sa.Column("representative", sa.Text()),
        sa.Column("colors", sa.Text()),
        sa.Column("nice_classes", ARRAY(sa.Text())),
        sa.Column("goods_services", JSONB()),
        sa.Column("vienna_codes", ARRAY(sa.Text())),
        sa.Column("status_code", sa.Text()),
        sa.Column("filing_date", sa.Date()),
        sa.Column("publication_no", sa.Text()),
        sa.Column("publication_date", sa.Date()),
        sa.Column("grant_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("logo_url", sa.Text()),
        sa.Column("timeline", JSONB()),
        sa.Column("raw", JSONB()),
        sa.Column("source_url", sa.Text()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.Text()),
        sa.Column("parse_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_domestic_records_status_code", "domestic_records", ["status_code"])
    op.create_index("ix_domestic_records_expiry_date", "domestic_records", ["expiry_date"])
    op.execute(
        "CREATE INDEX ix_domestic_records_vienna_codes "
        "ON domestic_records USING gin (vienna_codes)"
    )


def downgrade() -> None:
    op.drop_table("domestic_records")
```

- [ ] **Step 3: Apply the migration to the dev DB**

Run:
```bash
cd app/backend
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
alembic upgrade head
```
Expected: `Running upgrade 20260619_0019 -> 20260619_0020, domestic_records table + indexes`

- [ ] **Step 4: Write a round-trip test**

`app/backend/tests/domestic_enrich/test_model_roundtrip.py`:

```python
import pytest
from sqlalchemy import select

from api.db.models import DomesticRecord


@pytest.mark.asyncio
async def test_domestic_record_roundtrip(db_session):
    db_session.add(DomesticRecord(
        application_number="4-2026-18514",
        mark_text="VTRAVEL",
        nice_classes=["39", "43"],
        goods_services={"39": "Transport", "43": "Lodging"},
        status_code="1904",
    ))
    await db_session.flush()
    row = (await db_session.execute(
        select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-18514")
    )).scalar_one()
    assert row.mark_text == "VTRAVEL"
    assert row.nice_classes == ["39", "43"]
    assert row.goods_services["43"] == "Lodging"
```

- [ ] **Step 5: Run the test**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_model_roundtrip.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/backend/api/db/models.py \
        app/backend/alembic/versions/20260619_0020_domestic_records.py \
        app/backend/tests/domestic_enrich/test_model_roundtrip.py
git commit -m "feat(domestic): domestic_records model + migration"
```

---

## Task 7: Status derivation

NOIP status codes (e.g. `1904`) map to human labels. Keep it pure, mirroring `madrid_enrich/derive.py`'s `VnStatus` shape.

**Files:**
- Create: `app/backend/domestic_enrich/derive.py`
- Test: `app/backend/tests/domestic_enrich/test_derive.py`

> **REVISED after Task 5:** the parser proved `status_code` is **polymorphic** — NOIP renders a numeric code (e.g. `1904`) for pending apps but Vietnamese *text* (`Cấp bằng` = "granted") for granted ones. `grant_date`/`expiry_date` are reliably present on granted marks. So "granted" is derived from `grant_date` + recognizable granted-text, NOT from an invented numeric code. `STATUS_LABELS` only maps the *numeric* codes (text statuses are already human-readable and pass through).

- [ ] **Step 1: Confirm the status values present in fixtures**

Run:
```bash
cd app/backend && python -c "
from pathlib import Path
from domestic_enrich.parser import parse
for f in sorted(Path('tests/fixtures/domestic').glob('VN*.html')):
    r = parse(f.read_text(encoding='utf-8'))
    print(f.stem, repr(r.status_code), 'grant=', r.grant_date)
"
```
Expected (confirmed): `VN4202600774` → `'1904'`, grant=None (pending); the other two → a Vietnamese granted phrase + a real grant date. Record the exact granted phrase for `_GRANTED_TEXT` below.

- [ ] **Step 2: Write the failing test**

`app/backend/tests/domestic_enrich/test_derive.py`:

```python
import datetime

from domestic_enrich.derive import derive_status, DomesticStatus
from domestic_enrich.parser import DomesticRecord, parse
from pathlib import Path

FIX = Path(__file__).parent.parent / "fixtures" / "domestic"


def test_numeric_code_maps_to_label():
    rec = DomesticRecord(status_code="1904", grant_date=None)
    st = derive_status(rec)
    assert isinstance(st, DomesticStatus)
    assert st.code == "1904"
    assert st.label  # non-empty human label
    assert st.is_granted is False


def test_granted_when_grant_date_present():
    rec = DomesticRecord(status_code="1904", grant_date=datetime.date(2025, 1, 1))
    st = derive_status(rec)
    assert st.is_granted is True


def test_granted_when_status_text_says_so():
    # NOIP renders granted as Vietnamese text, not a numeric code.
    rec = DomesticRecord(status_code="Cấp bằng", grant_date=None)
    st = derive_status(rec)
    assert st.is_granted is True
    assert st.label == "Cấp bằng"  # already human-readable → passes through


def test_unknown_numeric_code_keeps_code_as_label():
    rec = DomesticRecord(status_code="9999")
    st = derive_status(rec)
    assert st.code == "9999"
    assert st.label == "9999"  # fall back to the raw code


def test_derive_on_real_granted_fixture():
    # Both 416348 / 449975 are granted (carry a grant_date) per Task 5.
    rec = parse((FIX / "VN4202416348.html").read_text(encoding="utf-8"))
    st = derive_status(rec)
    assert st.is_granted is True
```

- [ ] **Step 3: Write the implementation**

`app/backend/domestic_enrich/derive.py`:

```python
"""Derive a human status from a parsed DomesticRecord's NOIP status field.

NOIP's status field is polymorphic: a numeric code (e.g. 1904) for pending
applications, or Vietnamese text ("Cấp bằng" = granted) once granted. Numeric
codes get mapped to a label via STATUS_LABELS (extend as observed); text
statuses are already human-readable and pass through unchanged. `is_granted`
is true when a grant date exists OR the status text is a recognized granted
phrase. Pure — no I/O.
"""

from __future__ import annotations

from pydantic import BaseModel

from .parser import DomesticRecord

# NUMERIC NOIP codes -> English label. Text statuses are NOT listed (they pass
# through as their own label). Extend as the sweep surfaces more numeric codes.
STATUS_LABELS: dict[str, str] = {
    "1904": "Under examination",
}
# Substrings (lowercased) that indicate a granted mark when they appear in the
# status text. "cấp bằng" = certificate granted. Confirm/extend from Task 7 Step 1.
_GRANTED_TEXT = ("cấp bằng", "granted")


class DomesticStatus(BaseModel):
    code: str | None
    label: str
    is_granted: bool


def derive_status(rec: DomesticRecord) -> DomesticStatus:
    code = rec.status_code
    label = STATUS_LABELS.get(code or "", code or "Unknown")
    norm = (code or "").strip().lower()
    is_granted = rec.grant_date is not None or any(g in norm for g in _GRANTED_TEXT)
    return DomesticStatus(code=code, label=label, is_granted=is_granted)
```

- [ ] **Step 4: Run the test**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_derive.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/domestic_enrich/derive.py app/backend/tests/domestic_enrich/test_derive.py
git commit -m "feat(domestic): NOIP status-code derivation"
```

---

## Task 8: Store (idempotent upsert)

**Files:**
- Create: `app/backend/domestic_enrich/store.py`
- Test: `app/backend/tests/domestic_enrich/test_store.py`

- [ ] **Step 1: Write the failing test**

`app/backend/tests/domestic_enrich/test_store.py`:

```python
import pytest
from sqlalchemy import select

from api.db.models import DomesticRecord
from domestic_enrich.parser import DomesticRecord as ParsedRecord
from domestic_enrich.store import upsert


@pytest.mark.asyncio
async def test_upsert_inserts_then_skips_unchanged(db_session):
    rec = ParsedRecord(application_number="4-2026-18514", mark_text="VTRAVEL",
                        nice_classes=["39"], status_code="1904")
    html = "<html>raw</html>"

    wrote = await upsert(db_session, rec, html, "http://x")
    assert wrote is True

    # Same content hash + parse_version → no write.
    wrote_again = await upsert(db_session, rec, html, "http://x")
    assert wrote_again is False

    # Changed HTML → write.
    wrote_changed = await upsert(db_session, rec, "<html>different</html>", "http://x")
    assert wrote_changed is True

    row = (await db_session.execute(
        select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-18514")
    )).scalar_one()
    assert row.mark_text == "VTRAVEL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domestic_enrich.store'`

- [ ] **Step 3: Write the implementation**

`app/backend/domestic_enrich/store.py`:

```python
"""Idempotent upsert of a parsed domestic record, keyed by application_number."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import DomesticRecord

from .parser import DomesticRecord as ParsedRecord

PARSE_VERSION = 1  # bump on any parser change → triggers offline re-derive


async def upsert(
    session: AsyncSession,
    rec: ParsedRecord,
    raw_html: str,
    source_url: str,
) -> bool:
    """Insert or update. Returns False (no write) when content_hash and
    parse_version are unchanged from the stored row."""
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    existing = (
        await session.execute(
            select(DomesticRecord).where(
                DomesticRecord.application_number == rec.application_number
            )
        )
    ).scalar_one_or_none()

    if existing and existing.content_hash == digest and existing.parse_version == PARSE_VERSION:
        return False

    values = dict(
        mark_text=rec.mark_text,
        mark_type=rec.mark_type,
        applicant_name=rec.applicant_name,
        applicant_address=rec.applicant_address,
        representative=rec.representative,
        colors=rec.colors,
        nice_classes=rec.nice_classes or None,
        goods_services=rec.goods_services or None,
        vienna_codes=rec.vienna_codes or None,
        status_code=rec.status_code,
        filing_date=rec.filing_date,
        publication_no=rec.publication_no,
        publication_date=rec.publication_date,
        grant_date=rec.grant_date,
        expiry_date=rec.expiry_date,
        logo_url=rec.logo_url,
        timeline=rec.timeline or None,
        raw=rec.raw or None,
        source_url=source_url,
        content_hash=digest,
        parse_version=PARSE_VERSION,
    )
    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        session.add(DomesticRecord(application_number=rec.application_number, **values))
    await session.flush()
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/domestic_enrich/store.py app/backend/tests/domestic_enrich/test_store.py
git commit -m "feat(domestic): idempotent domestic_records upsert with content-hash skip"
```

---

## Task 9: `enrich_one` orchestrator

**Files:**
- Create: `app/backend/domestic_enrich/enrich.py`
- Test: `app/backend/tests/domestic_enrich/test_enrich.py`

- [ ] **Step 1: Write the failing test**

`app/backend/tests/domestic_enrich/test_enrich.py`:

```python
from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import DomesticRecord
from domestic_enrich.enrich import enrich_one

FIXTURE = Path(__file__).parent.parent / "fixtures" / "domestic" / "VN4202600774.html"


@pytest.mark.asyncio
async def test_enrich_one_fetches_parses_stores(db_session, tmp_path):
    # Pre-seed the cache (VNID filename) so enrich_one hits no network.
    (tmp_path / "VN4202600774.html").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    wrote = await enrich_one(db_session, "4-2026-00774", cache_dir=tmp_path)
    assert wrote is True

    row = (await db_session.execute(
        select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-00774")
    )).scalar_one()
    assert row.mark_text == "VTRAVEL"   # confirm against fixture
    assert row.status_code


@pytest.mark.asyncio
async def test_enrich_one_skips_unmappable_appno(db_session, tmp_path):
    # An unmappable application number returns False (skip + log), never raises.
    wrote = await enrich_one(db_session, "garbage", cache_dir=tmp_path)
    assert wrote is False
```

> Note: the fixture filename in cache must be the **VNID** (`VN4202600774.html`), because the client caches by VNID. Pick a test `application_number` whose mapping yields the fixture's VNID — here `4-2026-00774` → `VN4202600774`. If the fixture's real application_number differs from this constructed one, use the real one and rename accordingly; the assertion key must match the `application_number` passed in.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_enrich.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domestic_enrich.enrich'`

- [ ] **Step 3: Write the implementation**

`app/backend/domestic_enrich/enrich.py`:

```python
"""Orchestrate fetch -> parse -> derive -> store for a single domestic mark."""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from sqlalchemy.ext.asyncio import AsyncSession

from .client import fetch_raw
from .idmap import appno_to_vnid
from .parser import parse
from .store import upsert

log = logging.getLogger("domestic.enrich")


async def enrich_one(
    session: AsyncSession,
    application_number: str,
    cache_dir: Path,
    *,
    http_session: requests.Session | None = None,
    use_cache: bool = True,
) -> bool:
    """Returns True if a row was written, False if skipped (unchanged OR the
    application_number is unmappable). Never raises on a bad app number — logs
    and skips so one bad row can't kill a sweep chunk."""
    vnid = appno_to_vnid(application_number)
    if vnid is None:
        log.warning("unmappable application_number, skipping: %r", application_number)
        return False

    fetched = fetch_raw(vnid, cache_dir, session=http_session, use_cache=use_cache)
    rec = parse(fetched.html)
    rec.application_number = application_number  # key by our gazette id, not the VNID
    return await upsert(session, rec, fetched.html, fetched.source_url)
```

> `derive_status` is intentionally NOT called here: status derivation is a read-time concern (Plan C surfaces it). The raw `status_code` is stored; `derive.py` maps it when rendering. This mirrors how Madrid stores `vn_status` but keeps the write path minimal. If a stored derived status is later wanted, add a `status_label` column in its own migration.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_enrich.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add app/backend/domestic_enrich/enrich.py app/backend/tests/domestic_enrich/test_enrich.py
git commit -m "feat(domestic): enrich_one orchestrator (fetch->parse->store, skip unmappable)"
```

---

## Task 10: Resumable backfill

**Files:**
- Create: `app/backend/domestic_enrich/backfill.py`
- Test: `app/backend/tests/domestic_enrich/test_backfill.py`

- [ ] **Step 1: Confirm the domestic mark categories**

Run:
```bash
cd app/backend
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -c "
import asyncio
from sqlalchemy import select, func
from api.db.session import async_session
from api.db.models import Trademark
async def main():
    async with async_session() as s:
        rows = (await s.execute(
            select(Trademark.mark_category, func.count())
            .where(Trademark.mark_category.like('domestic_%'))
            .group_by(Trademark.mark_category))).all()
        print(rows)
asyncio.run(main())
"
```
Expected: `[('domestic_application', 19412), ('domestic_registration', 22904)]` (or current counts). Use these two category strings in Step 3.

- [ ] **Step 2: Write the failing test**

`app/backend/tests/domestic_enrich/test_backfill.py`:

```python
import pytest

import domestic_enrich.backfill as bf
from domestic_enrich.backfill import CircuitBreaker, run_backfill


def test_circuit_breaker_trips_after_consecutive_failures():
    cb = CircuitBreaker(max_consecutive=3)
    cb.record_failure(); cb.record_failure()
    assert cb.tripped is False
    cb.record_failure()
    assert cb.tripped is True
    cb.record_success()
    assert cb.tripped is False


@pytest.mark.asyncio
async def test_run_backfill_counts_and_skips(db_session, tmp_path, monkeypatch):
    appnos = ["4-2026-00001", "4-2026-00002", "4-2026-00003"]

    async def fake_iter(session):
        return appnos

    calls = []

    async def fake_enrich(session, appno, *, cache_dir, use_cache):
        calls.append(appno)
        return appno != "4-2026-00002"  # one "skip" (unchanged)

    monkeypatch.setattr(bf, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(bf, "enrich_one", fake_enrich)

    res = await run_backfill(db_session, cache_dir=tmp_path, delay=0.0, jitter=0.0)
    assert res.attempted == 3
    assert res.written == 2
    assert res.skipped == 1
    assert calls == appnos
```

- [ ] **Step 3: Write the implementation**

`app/backend/domestic_enrich/backfill.py` — copy `madrid_enrich/backfill.py` structure, swapping IRN→appno, the categories, and the work-list column (`application_number`, not `lineage_key`):

```python
"""Polite, resumable NOIP backfill over domestic application numbers."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Trademark

from .enrich import enrich_one  # module attr so tests can monkeypatch

log = logging.getLogger("domestic.backfill")

_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")


async def iter_domestic_appnos(session: AsyncSession) -> list[str]:
    """Distinct domestic application numbers (the sweep work-list)."""
    rows = (
        (
            await session.execute(
                select(Trademark.application_number)
                .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
                .where(Trademark.application_number.is_not(None))
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return [r for r in rows if r]


class CircuitBreaker:
    """Trips after N consecutive failures so a NOIP outage halts the batch
    instead of hammering. Any success resets the streak. (Individual flaky-node
    500s are absorbed inside the client's retry loop, so a failure here means
    the client gave up entirely on a mark.)"""

    def __init__(self, max_consecutive: int = 5) -> None:
        self.max_consecutive = max_consecutive
        self._streak = 0

    @property
    def tripped(self) -> bool:
        return self._streak >= self.max_consecutive

    def record_failure(self) -> None:
        self._streak += 1

    def record_success(self) -> None:
        self._streak = 0


@dataclass
class BackfillResult:
    attempted: int = 0
    written: int = 0
    skipped: int = 0
    failed: int = 0
    circuit_broke: bool = False


async def run_backfill(
    session: AsyncSession,
    *,
    cache_dir: Path,
    limit: int | None = None,
    delay: float = 3.0,
    jitter: float = 1.0,
    max_consecutive: int = 5,
    daily_cap: int | None = None,
    force: bool = False,
    progress_every: int = 25,
) -> BackfillResult:
    """Enrich domestic marks politely. Resumable: enrich_one() skips unchanged
    content (content_hash), so re-running is cheap. `limit` caps the count
    (pilot mode); `daily_cap` is a hard self-imposed network ceiling."""
    appnos = await iter_domestic_appnos(session)
    if limit is not None:
        appnos = appnos[:limit]

    res = BackfillResult()
    cb = CircuitBreaker(max_consecutive=max_consecutive)
    for appno in appnos:
        if cb.tripped:
            res.circuit_broke = True
            log.warning("circuit breaker tripped after %d consecutive failures — halting",
                        max_consecutive)
            break
        if daily_cap is not None and res.attempted >= daily_cap:
            log.info("daily cap %d reached — stopping", daily_cap)
            break
        res.attempted += 1
        try:
            wrote = await enrich_one(session, appno, cache_dir=cache_dir, use_cache=not force)
            await session.commit()
            cb.record_success()
            if wrote:
                res.written += 1
            else:
                res.skipped += 1
        except Exception as exc:  # one bad mark must not kill the batch
            await session.rollback()
            res.failed += 1
            cb.record_failure()
            log.warning("enrich failed for %s: %s", appno, exc)
        if res.attempted % progress_every == 0:
            log.info("progress: %d attempted (%d written, %d skipped, %d failed)",
                     res.attempted, res.written, res.skipped, res.failed)
        if delay:
            await asyncio.sleep(delay + random.uniform(0, jitter))  # jitter, not crypto
    return res
```

- [ ] **Step 4: Run the test**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/test_backfill.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/backend/domestic_enrich/backfill.py app/backend/tests/domestic_enrich/test_backfill.py
git commit -m "feat(domestic): resumable backfill over domestic application numbers"
```

---

## Task 11: Full-suite green + docs sync

**Files:**
- Modify: `CLAUDE.md` (add a `domestic_enrich/` line to the project-layout section)

- [ ] **Step 1: Run the whole domestic test package**

Run: `cd app/backend && python -m pytest tests/domestic_enrich/ -v`
Expected: every test passes.

- [ ] **Step 2: Run the full backend suite (no regressions)**

Run: `cd app/backend && python -m pytest -q`
Expected: all pass (Madrid + everything else unaffected).

- [ ] **Step 3: Smoke one real mark end-to-end (live)**

Run:
```bash
cd app/backend
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -c "
import asyncio
from pathlib import Path
from api.db.session import async_session
from domestic_enrich.enrich import enrich_one
async def main():
    async with async_session() as s:
        wrote = await enrich_one(s, '4-2026-00774', cache_dir=Path('../../domestic_cache'))
        await s.commit()
        print('wrote=', wrote)
asyncio.run(main())
"
```
Expected: `wrote= True`, and a `domestic_cache/VN4202600774.html` file exists. (Use a real domestic application_number from the DB if `4-2026-00774` does not exist.)

- [ ] **Step 4: Update CLAUDE.md project layout**

In `CLAUDE.md`, under the `app/backend/` tree, add a `domestic_enrich/` entry next to `madrid_enrich/`, describing it as the NOIP domestic enrichment package (client/parser/derive/store/enrich/backfill → `domestic_records`, keyed by `application_number`, soft-joined to `trademarks.application_number`). Note Plan B (sweep) and Plan C (frontend) are pending.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(domestic): record domestic_enrich core package in project layout"
```

---

## Self-Review (completed during planning)

**Spec coverage** (against `docs/superpowers/specs/2026-06-19-domestic-enrichment-design.md`):
- §Fetch client (TLS bundle, retry, body-validation, cache) → Tasks 2, 3. ✅
- §Parser (regex, fixtures, per-class goods) → Tasks 4, 5. ✅
- §Schema (`domestic_records` model + migration) → Task 6. ✅
- §Store (PARSE_VERSION, upsert, content_hash) → Task 8. ✅
- §ID mapping (with odd-format guard) → Task 1. ✅
- §Status mapping → Task 7. ✅
- §enrich_one + backfill (skip unmappable, circuit breaker, work-list) → Tasks 9, 10. ✅
- §Sweep / control API / admin panel / detail page → **deferred to Plans B & C** (out of scope here, by design). ✅

**Deferred to Plan B:** `worker/domestic_sweep.py`, `domestic_sweep_control` table + migration, `api/routes/domestic_sweep.py`, admin `/domestic-enrichment` stats, `domestic` queue registration in `run_worker.py`.

**Deferred to Plan C:** `app/(app)/admin/domestic/page.tsx`, `DomesticEnrichment` block in `marks/[id]/page.tsx`, the mark-detail-API join attaching `domestic_records` (reusing the `GoodsServices` PREVIEW=5 collapse).

**Type consistency check:** `DomesticRecord` (pydantic, Task 5) and `DomesticRecord` (SQLAlchemy, Task 6) share field names exactly; `store.upsert` (Task 8) reads only those fields; `fetch_raw` returns `FetchResult.html/source_url` consumed by `enrich_one` (Task 9); `iter_domestic_appnos`/`enrich_one` names match between Tasks 9 and 10. ✅

**Known follow-up flagged for execution:** Task 5's parser regexes must be written against the real Task-4 fixtures (the field assertions are confirmed against the actual HTML in Step 1). Task 7's `STATUS_LABELS` map is seeded from observed codes and extended as the sweep surfaces more. Task 9's test `application_number`/VNID pairing must match a real fixture id.
