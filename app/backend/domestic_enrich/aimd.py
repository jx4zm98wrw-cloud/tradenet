"""AIMD concurrency controller for the domestic sweep's "Dead mode".

Pure, no I/O. Models TCP congestion control: additive-increase while NOIP is
healthy (probe for more headroom), multiplicative-decrease the instant it pushes
back (a 403/429 block), and a mild decrease when the flaky-500 rate spikes
(treat congestion as a reason to ease off). The dead-chunk runtime (worker side)
feeds it one WindowStats per window of completed fetches and applies the
Decision; it never settles above what the single flaky cluster will sustain.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

# Concurrency bounds. CEILING is deliberately low: one flaky Apache/Tomcat
# cluster on a single IP won't sustain much parallelism before its 500-rate
# climbs. START is where each dead-mode run begins probing from.
FLOOR = 1
CEILING = 6
START = 2

# Evaluate the controller once per this many completed fetches.
WINDOW_SIZE = 20

# Probe up only when a window is this clean; ease off below the degrade line.
PROBE_THRESHOLD = 0.95
DEGRADE_THRESHOLD = 0.70

# After this many *consecutive* windows that still see blocks (even after
# backing off), give up dead mode: revert to normal + pause (the runaway stop).
BLOCK_GIVEUP = 3


class Outcome(Enum):
    """How a single fetch ended."""

    SUCCESS = "success"  # HTTP 200 + valid body
    FLAKY_FAIL = "flaky_fail"  # exhausted retries (flaky cluster) — RuntimeError
    BLOCK = "block"  # NoipBlockedError (403/429)


@dataclass(frozen=True)
class WindowStats:
    """Outcome tallies over one evaluation window."""

    success: int
    flaky: int
    block: int

    @property
    def total(self) -> int:
        return self.success + self.flaky + self.block

    @property
    def success_rate(self) -> float:
        return self.success / self.total if self.total else 0.0


@dataclass(frozen=True)
class Decision:
    """The controller's verdict for the next window."""

    concurrency: int  # next active-thread target
    blocked: bool  # window saw a block -> caller should cool down before probing


def stats_from(outcomes: Iterable[Outcome]) -> WindowStats:
    """Tally a sequence of Outcomes into a WindowStats."""
    success = flaky = block = 0
    for o in outcomes:
        if o is Outcome.SUCCESS:
            success += 1
        elif o is Outcome.FLAKY_FAIL:
            flaky += 1
        else:
            block += 1
    return WindowStats(success=success, flaky=flaky, block=block)


def next_concurrency(
    current: int,
    stats: WindowStats,
    *,
    ceiling: int = CEILING,
    floor: int = FLOOR,
) -> Decision:
    """Decide the next concurrency level from the last window's outcomes.

    Priority: a block dominates (multiplicative decrease + cooldown flag), else a
    flaky/degraded window eases off by one, else a clean window probes up by one,
    else hold. Always clamped to [floor, ceiling].
    """
    if stats.block > 0:
        return Decision(concurrency=max(floor, current // 2), blocked=True)
    if stats.success_rate < DEGRADE_THRESHOLD:
        return Decision(concurrency=max(floor, current - 1), blocked=False)
    if stats.success_rate >= PROBE_THRESHOLD:
        return Decision(concurrency=min(ceiling, current + 1), blocked=False)
    return Decision(concurrency=current, blocked=False)


def should_give_up(consecutive_block_windows: int) -> bool:
    """True when blocks have persisted long enough to abandon dead mode
    (revert to normal + pause). The runaway backstop."""
    return consecutive_block_windows >= BLOCK_GIVEUP
