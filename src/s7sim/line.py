"""The behaviour of a production line, as a function of elapsed time.

The line is a pure function rather than a loop that mutates state: given the
seed and a number of seconds, it always reports the same thing. That makes a
stop reproducible, which is the whole point of simulating one.
"""
from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stop:
    """One stoppage, in seconds from the start of the run."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Line:
    """A line that runs, stops and runs again.

    Run and stop lengths are drawn from an exponential distribution, which is
    what a plant sees when failures are independent of how long the machine has
    been up. The draws come from a seeded generator, so the same seed gives the
    same day.
    """

    mean_run_seconds: float = 720.0
    mean_stop_seconds: float = 180.0
    seed: int = 1
    #: How far ahead the schedule is generated, in seconds.
    horizon: float = 24 * 3600.0

    _stops: list[Stop] = field(default_factory=list, repr=False)
    _starts: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.mean_run_seconds <= 0:
            raise ValueError("mean_run_seconds must be positive")
        if self.mean_stop_seconds <= 0:
            raise ValueError("mean_stop_seconds must be positive")
        self._build()

    def _build(self) -> None:
        rng = random.Random(self.seed)
        t = 0.0
        while t < self.horizon:
            t += rng.expovariate(1.0 / self.mean_run_seconds)
            stop_end = t + rng.expovariate(1.0 / self.mean_stop_seconds)
            self._stops.append(Stop(t, stop_end))
            t = stop_end
        self._starts = [s.start for s in self._stops]

    def running(self, t: float) -> bool:
        """True when the line is producing at elapsed time ``t``."""
        stop = self._stop_at(t)
        return stop is None

    def _stop_at(self, t: float) -> Stop | None:
        i = bisect.bisect_right(self._starts, t) - 1
        if i < 0:
            return None
        stop = self._stops[i]
        return stop if t < stop.end else None

    def stopped_for(self, t: float) -> float:
        """Seconds the current stop has lasted, or 0 while running."""
        stop = self._stop_at(t)
        return t - stop.start if stop else 0.0

    def running_seconds(self, t: float) -> float:
        """Total producing time up to ``t``. This is what a counter follows."""
        total = t
        for stop in self._stops:
            if stop.start >= t:
                break
            total -= min(stop.end, t) - stop.start
        return total

    def stops_before(self, t: float) -> list[Stop]:
        return [s for s in self._stops if s.start < t]
