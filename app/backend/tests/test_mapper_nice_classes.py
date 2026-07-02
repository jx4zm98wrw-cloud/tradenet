"""Unit tests for the ingest mapper's Nice-class derivation (audit W1).

Pure-function tests (no DB). The mapper must derive `trademarks.nice_classes`
from the extractor's authoritative, already-parsed `Group Number` field — NOT
by re-harvesting incidental digits from the raw (511) goods prose. The output
must be zero-padded 2-digit strings (the standing convention across the
domestic/madrid enrichment tables) and equal to a deduped split of
`nice_group_number`.
"""

from __future__ import annotations

import uuid

from api.db.models import RecordType
from worker.mapper import _classes_from_group_number, section_to_trademark


def test_empty_group_number_yields_none() -> None:
    assert _classes_from_group_number(None) is None
    assert _classes_from_group_number("") is None
    assert _classes_from_group_number("   ") is None


def test_splits_padded_group_number() -> None:
    assert _classes_from_group_number("05,12,41") == ["05", "12", "41"]


def test_dedups_preserving_order() -> None:
    # The extractor does not dedup Group Number; the mapper must (40 corpus rows
    # had duplicate tokens).
    assert _classes_from_group_number("35,41,35,09") == ["35", "41", "09"]


def test_ignores_raw_511_goods_digits() -> None:
    # The W1 regression: raw (511) prose carries incidental digits ("3 chiều",
    # "10 kg") that the old blind scan turned into phantom classes. The mapper
    # now reads ONLY Group Number, so those digits never reach nice_classes.
    section = {
        "(511)": "Nhóm 01: Hóa chất 3 chiều dùng trong công nghiệp, 10 kg mỗi bao",
        "Group Number": "01",
    }
    tm = section_to_trademark(uuid.uuid4(), RecordType.A, section)
    assert tm.nice_classes == ["01"]  # not ["01", "3", "10"]


def test_drops_out_of_range_classes() -> None:
    # Some gazettes print an invalid "Nhóm 99"; the extractor's Nhóm grammar is
    # not range-validated so it reaches nice_group_number verbatim, but 99 is
    # not a real Nice class (1-45) and must not pollute the queryable array.
    assert _classes_from_group_number("99,03") == ["03"]
    assert _classes_from_group_number("99") is None


def test_pads_unpadded_tokens() -> None:
    # Enforce the canonical zero-padded 2-digit convention even if a token
    # arrives unpadded.
    assert _classes_from_group_number("5,12") == ["05", "12"]


def test_nice_classes_equals_split_of_group_number() -> None:
    # The invariant the repair backfill + audit check enforce corpus-wide.
    section = {"(511)": "irrelevant prose 7 8 9", "Group Number": "03,18,25"}
    tm = section_to_trademark(uuid.uuid4(), RecordType.A, section)
    assert tm.nice_classes == section["Group Number"].split(",")
