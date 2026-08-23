"""What each behaviour puts in a tag."""
import pytest

from s7sim.line import Line
from s7sim.tags import Counter, Running, Setpoint, StoppedFor, Temperature


@pytest.fixture
def line():
    return Line(mean_run_seconds=60, mean_stop_seconds=20, seed=1)


def test_a_counter_does_not_advance_while_the_line_is_stopped(line):
    """This is the whole reason a counter is tied to producing time: a total
    that keeps climbing through a stop hides the stop."""
    stop = line._stops[0]
    counter = Counter(per_minute=600)

    during = counter.value(line, stop.start + 1)
    later = counter.value(line, stop.end - 0.1)

    assert during == later


def test_a_counter_resumes_after_the_stop(line):
    stop = line._stops[0]
    counter = Counter(per_minute=600)

    assert counter.value(line, stop.end + 10) > counter.value(line, stop.start + 1)


def test_a_counter_follows_the_rate_it_was_given():
    line = Line(mean_run_seconds=10_000, mean_stop_seconds=1, seed=1)  # no stop in range
    counter = Counter(per_minute=600)

    assert counter.value(line, 60) == pytest.approx(600, abs=1)


def test_a_fraction_counts_a_share_of_the_same_production():
    line = Line(mean_run_seconds=10_000, mean_stop_seconds=1, seed=1)
    total = Counter(per_minute=1000)
    rejects = Counter(per_minute=1000, fraction=0.02)

    assert rejects.value(line, 600) == pytest.approx(total.value(line, 600) * 0.02, rel=0.02)


def test_a_counter_starts_where_it_was_told_to(line):
    assert Counter(per_minute=60, start=90_000).value(line, 0) == 90_000


def test_temperature_settles_towards_running_and_falls_during_a_stop(line):
    stop = line._stops[0]
    temp = Temperature(running=74, idle=20, tau=10, noise=0)

    climbing = temp.value(line, stop.start - 0.1)
    falling = temp.value(line, stop.start + 15)

    assert falling < climbing


def test_temperature_never_leaves_the_two_values_it_was_given(line):
    temp = Temperature(running=74, idle=20, tau=30, noise=0)

    values = [temp.value(line, t) for t in range(0, 900, 5)]

    assert min(values) >= 20 - 0.01
    assert max(values) <= 74 + 0.01


def test_the_noise_is_the_same_for_the_same_second(line):
    """Seeded on the tick, so two reads inside one second see the same wobble.

    The reading still moves between them, because the curve underneath is
    continuous: only the noise is quantised.
    """
    temp = Temperature(running=74, idle=20, noise=1.0, seed=3)

    assert temp._noise(42.1) == temp._noise(42.9)
    assert temp._noise(42.0) != temp._noise(43.0)


def test_the_same_moment_always_reads_the_same(line):
    temp = Temperature(running=74, idle=20, noise=1.0, seed=3)

    assert temp.value(line, 42.4) == temp.value(line, 42.4)


def test_a_setpoint_is_not_rewritten_by_the_simulator(line):
    """A tag the simulator keeps writing cannot be used to test writes."""
    assert Setpoint(value_=1500).writable is True
    assert Running().writable is False
    assert Counter().writable is False
    assert Temperature().writable is False
    assert StoppedFor().writable is False
