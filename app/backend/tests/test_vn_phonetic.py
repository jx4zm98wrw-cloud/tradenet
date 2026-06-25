"""Unit tests for the Vietnamese phonetic key + language detector (Track 2)."""

from __future__ import annotations

from tm_similarity.vn_phonetic import vn_phonetic_key


def test_northern_z_merger_gia_d_r():
    # d / gi / r all merge to /z/ in Hanoi phonology (Kirby 2011).
    assert vn_phonetic_key("GIA") == vn_phonetic_key("DA") == vn_phonetic_key("RA")


def test_northern_affricate_merger_ch_tr():
    # ch / tr both /tɕ/.
    assert vn_phonetic_key("TRANG") == vn_phonetic_key("CHANG")


def test_northern_sibilant_merger_s_x():
    assert vn_phonetic_key("SA") == vn_phonetic_key("XA")


def test_velar_onset_merger_c_k_q():
    assert vn_phonetic_key("CA") == vn_phonetic_key("KA") == vn_phonetic_key("QA")


def test_qu_medial_glide():
    # QU- carries the /w/ on-glide: QUANG keeps a glide slot CANG lacks.
    assert vn_phonetic_key("QUANG") != vn_phonetic_key("CANG")
    assert "w" in vn_phonetic_key("QUANG")


def test_offglide_coda_i_becomes_j():
    # MAI / MAY share the /j/ off-glide coda.
    assert vn_phonetic_key("MAI") == vn_phonetic_key("MAY")
    assert vn_phonetic_key("MAI").endswith("j")


def test_final_consonant_codas():
    # ng -> /ŋ/=q ; c/ch -> /k/ codas.
    assert vn_phonetic_key("TRANG").endswith("q")
    assert vn_phonetic_key("AC").endswith("k")
    assert vn_phonetic_key("ACH").endswith("k")


def test_multi_syllable_token():
    # LAKA parses as two syllables la.ka (maximal onset).
    assert vn_phonetic_key("LAKA") == "laka"
    # LACCA splits the cluster: lac.ca.
    assert vn_phonetic_key("LACCA") == "lakka"


def test_empty_and_nonalpha():
    assert vn_phonetic_key("") == ""
    assert vn_phonetic_key("123") == ""
