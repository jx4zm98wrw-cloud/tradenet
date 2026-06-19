"""Goods & services extraction must handle any WIPO language, preferring EN.

Regression: the parser matched only GSTERMEN/lang="EN", so French-origin marks
(e.g. ROLEX's "ESPRIT D'ENTREPRISE", IRN 0643139) — whose BASICGS block carries
goods only as GSTERMFR/lang="FR" — got goods_services=NULL and the detail page
showed just a bare class list.
"""

from __future__ import annotations

from madrid_enrich.parser import parse

_FR_ONLY = """
<dl class="BASICGS">
  <dd nice="09">
    <p class="gsterm shown firstLanguage GSTERMFR originalLanguage" nice="09" lang="FR">
      Logiciels; appareils électroniques.
    </p>
  </dd>
</dl>
"""

_MULTILANG = """
<dl class="BASICGS">
  <dd nice="09">
    <p class="gsterm shown firstLanguage GSTERMFR originalLanguage" nice="09" lang="FR">Logiciels.</p>
    <p class="gsterm shown GSTERMEN" nice="09" lang="EN">Computer software.</p>
  </dd>
</dl>
"""


def test_french_only_goods_extracted():
    rec = parse(_FR_ONLY)
    assert "09" in rec.goods_services
    assert rec.goods_services["09"].startswith("Logiciels")


def test_english_preferred_when_multiple_languages():
    rec = parse(_MULTILANG)
    assert rec.goods_services["09"] == "Computer software."
