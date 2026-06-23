"""Rate-feedback concurrency controller for the Madrid sweep's "Fast mode".

Pure, no I/O. WIPO publishes its budget (X-RateLimit-Limit/Remaining), so unlike
the domestic AIMD controller we never probe for a ceiling — we pace to the given
one: step concurrency up while Remaining is healthy, down as it nears a floor,
and pause on an explicit 429/throttle. X-RateLimit-Reset is unusable (WIPO
returns a negative value), so we rely on Remaining recovering by observation.
"""

from __future__ import annotations

from dataclasses import dataclass

FLOOR = 1
CEILING = 6
START = 2

FLOOR_FRAC = 0.15  # keep Remaining above 15% of Limit
HEALTHY_FRAC = 0.50  # probe up only when Remaining >= 50% of Limit
FLOOR_ABS = 50  # absolute Remaining floor when Limit is unknown/tiny


@dataclass(frozen=True)
class RateWindow:
    """What WIPO reported over the last window of fetches."""

    remaining: int | None
    limit: int | None
    throttled: bool


@dataclass(frozen=True)
class Decision:
    concurrency: int
    paused: bool  # throttled -> caller sleeps Retry-After, then re-probes


def _remaining_floor(limit: int | None) -> int:
    if not limit:
        return FLOOR_ABS
    return max(FLOOR_ABS, int(FLOOR_FRAC * limit))


def next_concurrency(
    current: int,
    window: RateWindow,
    *,
    ceiling: int = CEILING,
    floor: int = FLOOR,
) -> Decision:
    """Decide the next concurrency from WIPO's last reported rate window.

    Priority: an explicit throttle parks paused (step down). Else, with a known
    Remaining: at/below the rate floor -> ease off; at/above the healthy band ->
    probe up; otherwise hold. Unknown Remaining -> hold. Clamped to [floor, ceiling].
    """
    if window.throttled:
        return Decision(concurrency=max(floor, current - 1), paused=True)
    if window.remaining is None:
        return Decision(concurrency=current, paused=False)
    if window.remaining <= _remaining_floor(window.limit):
        return Decision(concurrency=max(floor, current - 1), paused=False)
    if window.limit and window.remaining >= HEALTHY_FRAC * window.limit:
        return Decision(concurrency=min(ceiling, current + 1), paused=False)
    return Decision(concurrency=max(floor, min(ceiling, current)), paused=False)
