# app/backend/tests/madrid_enrich/test_fast_controller.py
from madrid_enrich.fast_mode.controller import RateWindow, next_concurrency


def test_throttle_dominates_and_pauses():
    d = next_concurrency(4, RateWindow(remaining=900, limit=1000, throttled=True))
    assert d.paused is True
    assert d.concurrency == 3  # stepped down


def test_remaining_at_or_below_floor_steps_down():
    # floor = max(50, 0.15*1000)=150
    d = next_concurrency(4, RateWindow(remaining=120, limit=1000, throttled=False))
    assert d.paused is False
    assert d.concurrency == 3


def test_healthy_remaining_probes_up():
    d = next_concurrency(2, RateWindow(remaining=800, limit=1000, throttled=False))
    assert d.concurrency == 3
    assert d.paused is False


def test_midband_holds():
    # between floor (150) and healthy (500): hold
    d = next_concurrency(3, RateWindow(remaining=300, limit=1000, throttled=False))
    assert d.concurrency == 3


def test_unknown_remaining_holds():
    d = next_concurrency(3, RateWindow(remaining=None, limit=None, throttled=False))
    assert d.concurrency == 3


def test_clamps_to_ceiling_and_floor():
    assert next_concurrency(6, RateWindow(900, 1000, False)).concurrency == 6  # ceiling
    assert next_concurrency(1, RateWindow(10, 1000, False)).concurrency == 1  # floor


def test_hold_branch_clamps_out_of_bounds_current():
    # midband (hold) must still clamp: current=8 with default ceiling=6 -> 6
    d = next_concurrency(8, RateWindow(remaining=300, limit=1000, throttled=False))
    assert d.concurrency == 6
    assert d.paused is False


def test_healthy_at_exact_threshold_probes_up():
    # remaining == HEALTHY_FRAC*limit (500 of 1000) is healthy (>=) -> step up
    d = next_concurrency(2, RateWindow(remaining=500, limit=1000, throttled=False))
    assert d.concurrency == 3
