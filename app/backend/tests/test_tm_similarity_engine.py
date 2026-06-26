"""tm_similarity reproduces the frozen golden baseline; hex pHash == imagehash."""

from __future__ import annotations

import json
import pathlib

import imagehash
from PIL import Image

import tm_similarity as t
from tests._similarity_cases import COMPOSITE_CASES, OVERLAP_CASES, PHONETIC_CASES
from tm_similarity.visual import _hamming_hex

GOLDEN = json.loads(pathlib.Path("tests/fixtures/similarity_golden.json").read_text())


def test_phonetic_matches_golden():
    got = [t.phonetic_similarity(a, b) for a, b in PHONETIC_CASES]
    assert got == GOLDEN["phonetic"]


def test_class_and_vienna_match_golden():
    assert [t.class_overlap(a, b) for a, b in OVERLAP_CASES] == GOLDEN["class"]
    assert [t.vienna_overlap(a, b) for a, b in OVERLAP_CASES] == GOLDEN["vienna"]


def test_composite_matches_golden():
    got = [
        [
            (cs := t.composite_score(p, v, s, c, vi, visual_confidence=vc)).composite,
            cs.verdict,
            cs.verdict_tone,
        ]
        for p, v, s, c, vi, vc in COMPOSITE_CASES
    ]
    assert got == GOLDEN["composite"]


def test_hex_phash_equals_imagehash_hamming():
    a = Image.new("L", (32, 32), 0)
    a.putpixel((2, 2), 255)
    b = Image.new("L", (32, 32), 0)
    b.putpixel((29, 29), 255)
    ha, hb = imagehash.phash(a), imagehash.phash(b)
    assert _hamming_hex(str(ha), str(hb)) == (ha - hb)


def test_score_assembles_result():
    a = t.MarkFeatures(mark_text="Gemy", logo_phash=None, nice_classes=["11"], vienna_codes=[])
    b = t.MarkFeatures(mark_text="Gemy", logo_phash=None, nice_classes=["11"], vienna_codes=[])
    r = t.score(a, b)
    assert r.phonetic == t.phonetic_similarity("Gemy", "Gemy")
    assert r.semantic == 0.0  # no embeddings -> no semantic signal
    assert r.verdict in {"Likely conflict", "Possible conflict", "Low risk"}
