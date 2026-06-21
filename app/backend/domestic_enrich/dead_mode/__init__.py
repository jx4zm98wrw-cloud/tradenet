"""Domestic sweep "Dead mode" — self-contained adaptive max-throughput package.

The normal sweep (worker.domestic_sweep) delegates to this package via a single
`if mode == 'dead'` branch; nothing here imports back into worker.domestic_sweep
(one-way dependency, no cycle). Public surface: the mode constants, the AIMD
controller, and run_chunk() (added with the runner in PR 3).
"""

from domestic_enrich.dead_mode.controller import (
    Decision,
    Outcome,
    WindowStats,
    next_concurrency,
    should_give_up,
    stats_from,
)
from domestic_enrich.dead_mode.runner import run_chunk

DEAD = "dead"
NORMAL = "normal"

__all__ = [
    "DEAD",
    "NORMAL",
    "Decision",
    "Outcome",
    "WindowStats",
    "next_concurrency",
    "run_chunk",
    "should_give_up",
    "stats_from",
]
