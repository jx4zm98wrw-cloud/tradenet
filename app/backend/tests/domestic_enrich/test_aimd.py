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
    assert WindowStats(0, 0, 0).success_rate == 0.0


def test_stats_from_classifies_outcomes():
    s = stats_from([Outcome.SUCCESS, Outcome.SUCCESS, Outcome.FLAKY_FAIL, Outcome.BLOCK])
    assert (s.success, s.flaky, s.block) == (2, 1, 1)


def test_healthy_window_probes_up_by_one():
    d = next_concurrency(3, WindowStats(success=20, flaky=0, block=0))
    assert d == Decision(concurrency=4, blocked=False)


def test_increase_is_clamped_to_ceiling():
    d = next_concurrency(CEILING, WindowStats(success=20, flaky=0, block=0))
    assert d.concurrency == CEILING
    assert d.blocked is False


def test_flaky_window_decreases_by_one():
    d = next_concurrency(4, WindowStats(success=12, flaky=8, block=0))
    assert d == Decision(concurrency=3, blocked=False)


def test_decrease_is_clamped_to_floor():
    d = next_concurrency(FLOOR, WindowStats(success=2, flaky=8, block=0))
    assert d.concurrency == FLOOR


def test_block_window_halves_and_flags_cooldown():
    d = next_concurrency(6, WindowStats(success=10, flaky=0, block=4))
    assert d == Decision(concurrency=3, blocked=True)


def test_block_halving_never_below_floor():
    d = next_concurrency(1, WindowStats(success=0, flaky=0, block=1))
    assert d.concurrency == FLOOR
    assert d.blocked is True


def test_block_dominates_even_with_high_success_rate():
    d = next_concurrency(4, WindowStats(success=19, flaky=0, block=1))
    assert d.concurrency == 2
    assert d.blocked is True


def test_middling_window_holds():
    d = next_concurrency(3, WindowStats(success=17, flaky=3, block=0))
    assert d == Decision(concurrency=3, blocked=False)


def test_should_give_up_after_threshold_consecutive_block_windows():
    assert should_give_up(2) is False
    assert should_give_up(3) is True
    assert should_give_up(5) is True


def test_start_is_within_bounds():
    assert FLOOR <= START <= CEILING
