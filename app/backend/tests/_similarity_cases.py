"""Shared input cases for the engine equivalence golden test (Track 0)."""

# (a_text, b_text)
PHONETIC_CASES = [
    ("Sulfani", "Sulfani"),
    ("Gemy", "KAVIN SAVING POWER"),
    ("VIET AGAROYAL", "VIET AGAROYAL GLOBAL"),
    ("Taseko", "Tabeko"),
    ("", "ABC"),
    ("CÔNG TY DƯỢC", "CÔNG TY DƯỢC PHẨM"),
]

# (a_codes, b_codes) — used for BOTH class_overlap and vienna_overlap
OVERLAP_CASES = [
    (["11"], ["11"]),
    (["11"], ["42"]),
    (["9", "42"], ["42"]),
    (["3"], ["3", "5"]),
    ([], ["1"]),
]

# (phonetic, visual, semantic, class_o, vienna_o, visual_confidence)
COMPOSITE_CASES = [
    (0.60, 0.63, 0.00, 1.0, 0.0, "phash"),
    (0.14, 0.63, 0.00, 1.0, 0.0, "phash"),
    (0.90, 0.90, 0.00, 1.0, 1.0, "phash"),
    (0.49, 0.20, 0.00, 1.0, 0.0, "typographic"),
    (0.16, 0.59, 0.00, 1.0, 0.0, "phash"),
    (0.10, 0.10, 0.85, 1.0, 0.0, "typographic"),  # semantic-driven (translation equiv)
]
