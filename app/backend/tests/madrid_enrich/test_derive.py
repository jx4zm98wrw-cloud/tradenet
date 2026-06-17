from datetime import date

from madrid_enrich.derive import VnStatus, derive_vn
from madrid_enrich.parser import MadridRecord


def _rec(**kw) -> MadridRecord:
    base = dict(designated_countries=["VN", "SG"], transaction_history=[])
    base.update(kw)
    return MadridRecord(**base)


def test_gazette_accepted_provisional_refusal_only_is_granted():
    # Gazette is authoritative: a provisional (interim) refusal with no grant
    # event must still resolve to "granted" (date per gazette = None).
    r = _rec(
        transaction_history=[
            {
                "type": "Provisional refusal of protection, VN",
                "date": "2018-01-10",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v == VnStatus(designated=True, status="granted", grant_date=None, refusal_date=None)


def test_gazette_accepted_with_grant_event_keeps_grant_date():
    r = _rec(
        transaction_history=[
            {
                "type": "Statement of grant of protection made under Rule 18ter(1), VN",
                "date": "2019-05-02",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v == VnStatus(designated=True, status="granted", grant_date=date(2019, 5, 2), refusal_date=None)


def test_non_gazette_provisional_refusal_with_reg_exp_is_pending():
    # WIPO fallback path: a bare provisional refusal is NOT terminal, and an
    # active registration (reg + exp present) is never refused -> pending.
    r = _rec(
        registration_date=date(2017, 6, 1),
        expiration_date=date(2027, 6, 1),
        transaction_history=[
            {
                "type": "Provisional refusal of protection, VN",
                "date": "2018-01-10",
                "parties": ["VN"],
            },
        ],
    )
    v = derive_vn(r, gazette_accepted=False)
    assert v.designated is True
    assert v.status == "pending"
    assert v.refusal_date is None


def test_non_gazette_final_refusal_is_refused():
    # WIPO fallback path: a FINAL refusal with no grant and no active
    # registration resolves to "refused".
    r = _rec(
        transaction_history=[
            {
                "type": "Confirmation of total provisional refusal, VN",
                "date": "2018-09-15",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=False)
    assert v.status == "refused" and v.refusal_date == date(2018, 9, 15)


def test_non_gazette_grant_is_granted():
    r = _rec(
        transaction_history=[
            {
                "type": "Statement of grant of protection, VN",
                "date": "2019-05-02",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=False)
    assert v.status == "granted" and v.grant_date == date(2019, 5, 2)


def test_non_gazette_not_designated():
    v = derive_vn(_rec(designated_countries=["SG"]), gazette_accepted=False)
    assert v.designated is False and v.status is None


def test_default_not_designated_without_vn_and_without_gazette_flag():
    # derive_vn's own default is gazette_accepted=False; without VN designation
    # and without the flag, the record is not designated.
    v = derive_vn(_rec(designated_countries=["SG"]))
    assert v.designated is False and v.status is None


def test_earliest_vn_grant_wins_regardless_of_document_order():
    # Two VN grants, the later one listed first in document order; the earlier
    # date must be chosen.
    r = _rec(
        transaction_history=[
            {"type": "Statement of grant of protection, VN", "date": "2021-08-01", "parties": ["VN"]},
            {"type": "Statement of grant of protection, VN", "date": "2019-05-02", "parties": ["VN"]},
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v.status == "granted" and v.grant_date == date(2019, 5, 2)
