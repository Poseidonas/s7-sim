"""The line schedule. Reproducibility is the property that matters."""
import pytest

from s7sim.line import Line


def test_the_same_seed_gives_the_same_day():
    """A stop that cannot be reproduced cannot be used to test anything."""
    a = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=7)
    b = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=7)

    assert [(s.start, s.end) for s in a._stops] == [(s.start, s.end) for s in b._stops]


def test_a_different_seed_gives_a_different_day():
    a = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=1)
    b = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=2)

    assert a._stops[0].start != b._stops[0].start


def test_running_is_false_only_inside_a_stop():
    line = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=1)
    stop = line._stops[0]

    assert line.running(stop.start - 0.1) is True
    assert line.running(stop.start + 0.1) is False
    assert line.running(stop.end + 0.1) is True


def test_producing_time_excludes_every_stop():
    line = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=1)
    t = 600.0

    lost = sum(min(s.end, t) - s.start for s in line._stops if s.start < t)

    assert line.running_seconds(t) == pytest.approx(t - lost)


def test_producing_time_never_goes_backwards():
    line = Line(mean_run_seconds=30, mean_stop_seconds=10, seed=4)
    values = [line.running_seconds(t) for t in range(0, 600, 5)]

    assert values == sorted(values)


def test_the_current_stop_is_timed_from_its_start():
    line = Line(mean_run_seconds=60, mean_stop_seconds=20, seed=1)
    stop = line._stops[0]

    assert line.stopped_for(stop.start + 5) == pytest.approx(5)
    assert line.stopped_for(stop.end + 1) == 0.0


def test_the_mean_run_length_is_what_was_asked_for():
    """Loose bounds on purpose: this is checking the distribution is used at
    all, not re-testing the standard library."""
    line = Line(mean_run_seconds=300, mean_stop_seconds=60, seed=11)
    starts = [s.start for s in line._stops]
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    mean_gap = sum(gaps) / len(gaps)

    assert 240 < mean_gap < 480, mean_gap


@pytest.mark.parametrize("field", ["mean_run_seconds", "mean_stop_seconds"])
def test_a_non_positive_mean_is_rejected(field):
    with pytest.raises(ValueError, match=f"{field} must be positive"):
        Line(**{field: 0})
