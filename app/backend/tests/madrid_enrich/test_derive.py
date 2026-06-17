from datetime import date

from madrid_enrich.derive import VnStatus, derive_vn
from madrid_enrich.parser import MadridRecord


def _rec(**kw) -> MadridRecord:
    base = dict(designated_countries=["VN", "SG"], transaction_history=[])
    base.update(kw)
    return MadridRecord(**base)


def test_granted():
    r = _rec(
        transaction_history=[
            {
                "type": "Statement of grant of protection made under Rule 18ter(1), VN",
                "date": "2019-05-02",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r)
    assert v == VnStatus(
        designated=True, status="granted", grant_date=date(2019, 5, 2), refusal_date=None
    )


def test_refused():
    r = _rec(
        transaction_history=[
            {
                "type": "Provisional refusal of protection, VN",
                "date": "2018-01-10",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r)
    assert v.status == "refused" and v.refusal_date == date(2018, 1, 10)


def test_pending_when_designated_no_event():
    assert derive_vn(_rec()).status == "pending"


def test_not_designated():
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
    v = derive_vn(r)
    assert v.status == "granted" and v.grant_date == date(2019, 5, 2)
