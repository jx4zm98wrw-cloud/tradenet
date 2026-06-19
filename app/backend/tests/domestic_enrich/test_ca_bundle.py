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
