from datetime import date
from pathlib import Path

from madrid_enrich.parser import parse

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"
MULTICLASS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1248225.html"
# IRN 0295028 (Johnson & Johnson). Its real WIPO transaction history carries both
# the parser-gap cases: IR-wide "global" events with no country tag (representative
# / holder / ownership changes) and multi-country Renewal events listing VN.
GLOBAL_TX_FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "0295028.html"


def _rec():
    return parse(FIXTURE.read_text(encoding="utf-8"))


def test_parses_all_nice_classes_multiclass():
    # IRN 1248225 (Hennessy PARADIS) covers Nice 21/32/33. The INID 511 field
    # packs all three classes' goods text into one blob, so the parser must read
    # the authoritative "Nice classes" summary cell, not just the first class.
    r = parse(MULTICLASS_FIXTURE.read_text(encoding="utf-8"))
    assert r.nice_classes == ["21", "32", "33"]


def test_holder_country_from_812_and_address_tail():
    # This holder carries no (811) nationality field — only (812) "FR" and the
    # "(FR)" tail in the (732) address. Country must still resolve to FR, and the
    # address must be just the postal lines (no holder name).
    r = parse(MULTICLASS_FIXTURE.read_text(encoding="utf-8"))
    assert r.holder_country == "FR"
    assert r.holder_address == "rue de la Richonne F-16100 Cognac (FR)"


def test_holder_name_is_clean_not_mashed_with_address():
    # The (732) block lists the holder name on the first line, then the address
    # on following lines. The name must be just the name — not name + street
    # ("Société Jas Hennessy & Co. rue de la Richonne F-").
    r = parse(MULTICLASS_FIXTURE.read_text(encoding="utf-8"))
    assert r.holder_name == "Société Jas Hennessy & Co."
    assert "rue de la Richonne" in (r.holder_address or "")


def test_parses_per_class_goods_services():
    # Full per-class goods text comes from the basic (BASICGS) goods list; later
    # blocks are subsequent-designation limitations and must not override it.
    r = parse(MULTICLASS_FIXTURE.read_text(encoding="utf-8"))
    assert set(r.goods_services) == {"21", "32", "33"}
    assert r.goods_services["33"] == "Alcoholic beverages (except beers); alcoholic cocktails."
    assert r.goods_services["21"].startswith("Utensils and containers for household")


def test_parses_bibliographic_scalars():
    r = _rec()
    assert r.mark_text == "Clalen"
    assert r.holder_name == "Interojo Inc."
    assert r.holder_country == "KR"
    assert "Corporation" in (r.holder_legal_status or "")
    assert "K IP & LAW FIRM" in (r.representative or "")
    assert r.language == "English"


def test_parses_dates_and_classes():
    r = _rec()
    assert r.registration_date == date(2015, 6, 26)
    assert r.expiration_date == date(2035, 6, 26)  # post-renewal value
    assert r.nice_classes == ["09"]


def test_effective_designated_countries_includes_vn_and_subsequent():
    r = _rec()
    # original IN/PH/SG/VN + subsequent EG/IR/RU (and MA/PK in the 832 set)
    for cc in ("VN", "IN", "PH", "SG", "EG", "IR", "RU"):
        assert cc in r.designated_countries


def test_transaction_history_has_vn_grant_and_renewal():
    r = _rec()
    types = [e["type"] for e in r.transaction_history]
    assert any("International Registration" in t for t in types)
    assert any("Renewal" in t for t in types)
    vn_grants = [
        e
        for e in r.transaction_history
        if "grant of protection" in e["type"].lower() and "VN" in (e.get("parties") or [])
    ]
    assert vn_grants and vn_grants[0]["date"] == "2019-05-02"


def test_designation_status_per_country():
    r = _rec()
    assert r.designation_status["VN"]["status"] == "granted"
    assert r.designation_status["VN"]["date"] == "2019-05-02"
    # IR is in designated_countries (subsequent designation) but has no
    # grant/refusal event of its own, so it is pending. (MA *does* have a grant
    # in this fixture, so the spec's example country was swapped for IR.)
    assert r.designation_status["IR"]["status"] == "pending"


def test_transaction_history_captures_global_representative_events():
    # GAP 1: IR-wide "global" events have no country/party list, so their type
    # line carries no comma and the parser used to drop them. IRN 0295028's real
    # history has representative-related global events (appointment/renunciation,
    # name/address change) that must now appear in transaction_history. These
    # events legitimately have empty parties/designations — we must NOT invent
    # country tags for them.
    r = parse(GLOBAL_TX_FIXTURE.read_text(encoding="utf-8"))
    rep = [
        e
        for e in r.transaction_history
        if "representative" in e["type"].lower()
        and ("renunciation" in e["type"].lower() or "name or address" in e["type"].lower())
    ]
    assert rep, "expected a representative renunciation/change global event"
    # The WIPO-documented appointment/renunciation of representative dates.
    dates = {e["date"] for e in rep}
    assert "2008-03-31" in dates
    assert "2022-01-26" in dates
    # Global events carry no party/designation country tags.
    for e in rep:
        assert e["parties"] == []
        assert e["designations"] == []


def test_renewal_parties_parsed_from_type_country_list():
    # GAP 2: a Renewal event lists its renewed designations in the TYPE string's
    # trailing country list ("Renewal, …, VN"); the block's 833 field is the
    # holder's origin office (e.g. BX) and must not be used as parties. Every
    # Renewal naming VN must therefore have VN in parties.
    r = parse(GLOBAL_TX_FIXTURE.read_text(encoding="utf-8"))
    renewals = [e for e in r.transaction_history if e["type"].startswith("Renewal")]
    assert renewals
    vn_renewals = [e for e in renewals if "VN" in e["type"]]
    assert vn_renewals, "fixture should contain a 'Renewal, …, VN' event"
    for e in vn_renewals:
        assert "VN" in (e["parties"] or []), f"VN missing from renewal parties on {e['date']}"
        # 'BX' (holder origin office) must not leak in as the sole party.
        assert e["parties"] != ["BX"]


def test_old_record_with_9sexies_designations_includes_vn():
    from pathlib import Path

    from madrid_enrich.parser import parse

    html = (Path(__file__).parent.parent / "fixtures" / "madrid" / "0183259.html").read_text(encoding="utf-8")
    r = parse(html)
    assert "VN" in r.designated_countries
    from madrid_enrich.derive import derive_vn

    assert derive_vn(r).designated is True
