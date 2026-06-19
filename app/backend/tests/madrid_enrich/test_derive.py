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


# --- Designation-date fallback (legacy records with no explicit VN grant) ----
# For gazette-accepted records that carry no "Grant of protection, VN" event,
# the date VN protection commenced is the VN *designation* event date: either
# a "Subsequent designation, VN" or the original "International Registration"
# event that lists VN among its parties. This is an accurate commencement date.
# A "Renewal" naming VN is only an upper bound (protection predates it) and must
# NOT be used as a grant date.


def test_gazette_accepted_subsequent_designation_fallback():
    r = _rec(
        transaction_history=[
            {"type": "Subsequent designation, VN", "date": "2017-05-04", "parties": ["VN"]},
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v == VnStatus(designated=True, status="granted", grant_date=date(2017, 5, 4), refusal_date=None)


def test_gazette_accepted_original_ir_designation_fallback():
    r = _rec(
        transaction_history=[
            {
                "type": "International Registration, AU, CN, JP, VN",
                "date": "2005-04-14",
                "parties": ["AU", "CN", "JP", "VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v.status == "granted" and v.grant_date == date(2005, 4, 14)


def test_designation_with_later_vn_refusal_stays_null():
    # Designation, then a (provisional) VN refusal: the designation date is NOT
    # the grant date -- the real grant came later (gazette overrode the refusal),
    # a date WIPO never recorded. Gazette-authoritative keeps status "granted",
    # but grant_date must be null rather than the pre-refusal designation date.
    r = _rec(
        transaction_history=[
            {"type": "International Registration, AU, VN", "date": "2015-05-28", "parties": ["AU", "VN"]},
            {
                "type": "Total provisional refusal of protection, VN",
                "date": "2016-06-30",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v.status == "granted" and v.grant_date is None


def test_gazette_accepted_renewal_only_stays_null():
    # VN appears only in a Renewal -> protection predates it, exact date is not
    # recoverable from WIPO. Grant date must stay None (accurate-only policy).
    r = _rec(
        transaction_history=[
            {
                "type": "Renewal, AG, AL, CN, VN, ZM",
                "date": "2015-03-26",
                "parties": ["AG", "AL", "CN", "VN", "ZM"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v.status == "granted" and v.grant_date is None


def test_explicit_grant_beats_designation_fallback():
    # When both a designation event and an explicit grant exist, the explicit
    # grant date wins (it is the truest signal).
    r = _rec(
        transaction_history=[
            {"type": "Subsequent designation, VN", "date": "2017-05-04", "parties": ["VN"]},
            {"type": "Statement of grant of protection, VN", "date": "2018-09-01", "parties": ["VN"]},
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v.grant_date == date(2018, 9, 1)


def test_replacement_event_is_not_a_designation():
    # "Replacement of national registration by an international registration"
    # contains the substring "international registration" but is NOT a VN
    # designation event -> must not be mistaken for a commencement date.
    r = _rec(
        transaction_history=[
            {
                "type": "Replacement of national registration by an international registration, VN",
                "date": "2003-01-09",
                "parties": ["VN"],
            },
        ]
    )
    v = derive_vn(r, gazette_accepted=True)
    assert v.status == "granted" and v.grant_date is None
