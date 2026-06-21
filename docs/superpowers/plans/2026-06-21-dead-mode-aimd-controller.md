# Dead Mode — AIMD Controller Implementation Plan (PR 1 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure, self-contained AIMD concurrency controller that "Dead mode" uses to self-tune the domestic sweep's concurrency toward NOIP's sustainable ceiling.

**Architecture:** A single new module `domestic_enrich/aimd.py` with no I/O — an `Outcome` enum, a `WindowStats` value object, a pure `next_concurrency()` decision function (additive-increase / multiplicative-decrease over a rolling window of fetch outcomes), and a `should_give_up()` helper for the sustained-block backstop. The dead-chunk runtime (PR 3) feeds it outcomes and acts on its decisions; this PR is just the brain, fully unit-tested.

**Tech Stack:** Python 3.13, `dataclasses`, `enum`, `pytest`. No DB, no network, no threads.

**Spec:** `docs/superpowers/specs/2026-06-21-domestic-dead-mode-design.md` (§"The AIMD controller", §"Safety valve & guardrails").

## Scope

This is **PR 1 of 5**. It delivers only the controller logic — a pure function library. Nothing imports it yet (PR 3 wires it into the dead-chunk). It is independently shippable and 100% unit-testable. Do **not** touch the schema, the worker, the routes, or the frontend in this PR.

## Standing constraints

- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path only.
- **GateGuard**: before the first Edit/Write per file and the first Bash, state the facts it asks for, then retry.
- Tests run from `app/backend/` with the project venv: `source ../.venv/bin/activate`. CI gates: `ruff check .`, `ruff format --check .`, `mypy api worker`, then pytest. **Note `mypy api worker` does NOT cover `domestic_enrich/` unless imported by `api`/`worker` — this PR adds no such import, so mypy won't check it here; still keep it type-clean for when PR 3 imports it.**

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/domestic_enrich/aimd.py` | The pure controller: `Outcome`, `WindowStats`, `Decision`, `next_concurrency()`, `should_give_up()`, tunable constants. |
| `app/backend/tests/domestic_enrich/test_aimd.py` | Full unit coverage of the decision rules + bounds + giveup. |

---

## Task 1: The AIMD controller module

**Files:**
- Create: `app/backend/domestic_enrich/aimd.py`
- Test: `app/backend/tests/domestic_enrich/test_aimd.py`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/domestic_enrich/test_aimd.py`:

```python
from domestic_enrich.aimd import (
    CEILING,
    FLOOR,
    START,
    Decision,
    Outcome,
    WindowStats,
    next_concurrency,
    should_give_up,
    stats_from,
)


def test_window_stats_rate_and_total():
    s = WindowStats(success=18, flaky=2, block=0)
    assert s.total == 20
    assert s.success_rate == 0.9
    # empty window has a defined (zero) rate, never divides by zero
    assert WindowStats(0, 0, 0).success_rate == 0.0


def test_stats_from_classifies_outcomes():
    s = stats_from([Outcome.SUCCESS, Outcome.SUCCESS, Outcome.FLAKY_FAIL, Outcome.BLOCK])
    assert (s.success, s.flaky, s.block) == (2, 1, 1)


def test_healthy_window_probes_up_by_one():
    # success_rate >= PROBE_THRESHOLD (0.95) and no block -> +1
    d = next_concurrency(3, WindowStats(success=20, flaky=0, block=0))
    assert d == Decision(concurrency=4, blocked=False)


def test_increase_is_clamped_to_ceiling():
    d = next_concurrency(CEILING, WindowStats(success=20, flaky=0, block=0))
    assert d.concurrency == CEILING
    assert d.blocked is False


def test_flaky_window_decreases_by_one():
    # no block, success_rate < DEGRADE_THRESHOLD (0.70) -> -1
    d = next_concurrency(4, WindowStats(success=12, flaky=8, block=0))  # 0.60
    assert d == Decision(concurrency=3, blocked=False)


def test_decrease_is_clamped_to_floor():
    d = next_concurrency(FLOOR, WindowStats(success=2, flaky=8, block=0))
    assert d.concurrency == FLOOR


def test_block_window_halves_and_flags_cooldown():
    d = next_concurrency(6, WindowStats(success=10, flaky=0, block=4))
    assert d == Decision(concurrency=3, blocked=True)  # 6 // 2 = 3, blocked flag set


def test_block_halving_never_below_floor():
    d = next_concurrency(1, WindowStats(success=0, flaky=0, block=1))
    assert d.concurrency == FLOOR
    assert d.blocked is True


def test_block_dominates_even_with_high_success_rate():
    # any block in the window overrides the probe-up rule
    d = next_concurrency(4, WindowStats(success=19, flaky=0, block=1))
    assert d.concurrency == 2
    assert d.blocked is True


def test_middling_window_holds():
    # no block, DEGRADE_THRESHOLD <= rate < PROBE_THRESHOLD -> hold
    d = next_concurrency(3, WindowStats(success=17, flaky=3, block=0))  # 0.85
    assert d == Decision(concurrency=3, blocked=False)


def test_should_give_up_after_threshold_consecutive_block_windows():
    assert should_give_up(2) is False
    assert should_give_up(3) is True
    assert should_give_up(5) is True


def test_start_is_within_bounds():
    assert FLOOR <= START <= CEILING
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd app/backend && source ../.venv/bin/activate && python -m pytest tests/domestic_enrich/test_aimd.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domestic_enrich.aimd'`

- [ ] **Step 3: Write the implementation**

`app/backend/domestic_enrich/aimd.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd app/backend && source ../.venv/bin/activate && python -m pytest tests/domestic_enrich/test_aimd.py -v`
Expected: PASS (all 12 tests)

- [ ] **Step 5: Lint + type-check the new module**

Run: `cd app/backend && source ../.venv/bin/activate && ruff format domestic_enrich/aimd.py tests/domestic_enrich/test_aimd.py && ruff check domestic_enrich/aimd.py tests/domestic_enrich/test_aimd.py && python -m mypy domestic_enrich/aimd.py`
Expected: `All checks passed!` and mypy `Success` (the module is pure + fully typed).

- [ ] **Step 6: Commit**

```bash
git add app/backend/domestic_enrich/aimd.py app/backend/tests/domestic_enrich/test_aimd.py
git commit -m "$(printf 'feat(dead-mode): AIMD concurrency controller (pure)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage** (against §"The AIMD controller" + §"Safety valve & guardrails"):
- Outcome classification (SUCCESS / FLAKY_FAIL / BLOCK) → `Outcome` + `stats_from`. ✅
- Window evaluation: block → halve+cooldown; flaky → −1; clean → +1; else hold → `next_concurrency`. ✅
- Bounds floor 1 / ceiling 6 / start 2; window 20; thresholds 0.70 / 0.95 → constants + clamping. ✅
- Sustained-block giveup (≥3) → `should_give_up`. ✅
- Deferred to later PRs (correctly out of scope here): the cooldown *duration*, the runtime that feeds windows, the `mode`/`concurrency` schema, the routes, the frontend. The controller exposes `blocked` and `should_give_up` so PR 3 can implement the cooldown + revert without changing this module.

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `Decision(concurrency, blocked)`, `WindowStats(success, flaky, block)`, `Outcome.{SUCCESS,FLAKY_FAIL,BLOCK}`, and the constant names (`FLOOR`/`CEILING`/`START`/`WINDOW_SIZE`/`PROBE_THRESHOLD`/`DEGRADE_THRESHOLD`/`BLOCK_GIVEUP`) are used identically in tests and implementation. These are the names PR 3 will import.
