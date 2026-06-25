from __future__ import annotations


def _jaccard(a: list[str] | None, b: list[str] | None) -> float:
    """Standard Jaccard: size of intersection over size of union. Returns 0
    when either side is empty (no signal to compute against)."""
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def class_overlap(a: list[str] | None, b: list[str] | None) -> float:
    """Jaccard on Nice classification. Necessary-not-sufficient for confusion."""
    return _jaccard(a, b)


def vienna_overlap(a: list[str] | None, b: list[str] | None) -> float:
    """Jaccard on Vienna figurative codes. Independent visual signal from pHash:
    marks can share Vienna codes (both have circles) without their actual
    rendered logos being pHash-similar."""
    return _jaccard(a, b)
