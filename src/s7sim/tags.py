"""Turning the state of a line into the value a tag holds.

Each behaviour is a function of elapsed time, for the same reason the line is:
a value that cannot be reproduced cannot be used to test anything.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from .line import Line


@dataclass
class Behaviour:
    """What a tag does. Subclasses answer for one elapsed time."""

    def value(self, line: Line, t: float) -> Any:
        raise NotImplementedError

    @property
    def writable(self) -> bool:
        """True when the simulator leaves the tag alone after starting it.

        A tag the simulator keeps writing cannot be used to test writes: the
        next tick would undo whatever the client sent.
        """
        return False


@dataclass
class Running(Behaviour):
    """True while the line is producing."""

    def value(self, line: Line, t: float) -> bool:
        return line.running(t)


@dataclass
class Counter(Behaviour):
    """A production counter, advancing only while the line runs."""

    per_minute: float = 60.0
    fraction: float = 1.0
    start: int = 0

    def value(self, line: Line, t: float) -> int:
        produced = line.running_seconds(t) * self.per_minute / 60.0
        return self.start + int(produced * self.fraction)


@dataclass
class StoppedFor(Behaviour):
    """Seconds the current stop has lasted. Zero while running."""

    def value(self, line: Line, t: float) -> float:
        return round(line.stopped_for(t), 1)


@dataclass
class Temperature(Behaviour):
    """Approaches one value while running and another while stopped.

    A first-order lag rather than a step, because a motor that jumps from 22 to
    74 degrees between two reads is the kind of signal that makes a monitoring
    system look like it works when it does not.
    """

    running: float = 70.0
    idle: float = 20.0
    tau: float = 120.0
    noise: float = 0.4
    seed: int = 0

    def value(self, line: Line, t: float) -> float:
        return round(self._settled(line, t) + self._noise(t), 2)

    def _settled(self, line: Line, t: float) -> float:
        """Integrate the lag across every state change up to t."""
        temp = self.idle
        clock = 0.0
        for stop in line.stops_before(t):
            temp = self._approach(temp, self.running, min(stop.start, t) - clock)
            clock = min(stop.start, t)
            if clock >= t:
                return temp
            temp = self._approach(temp, self.idle, min(stop.end, t) - clock)
            clock = min(stop.end, t)
            if clock >= t:
                return temp
        return self._approach(temp, self.running, t - clock)

    def _approach(self, start: float, target: float, seconds: float) -> float:
        if seconds <= 0:
            return start
        return target + (start - target) * math.exp(-seconds / self.tau)

    def _noise(self, t: float) -> float:
        if not self.noise:
            return 0.0
        # Seeded on the tick so the same second always reads the same.
        return random.Random(f"{self.seed}:{int(t)}").uniform(-self.noise, self.noise)


@dataclass
class Setpoint(Behaviour):
    """A value the simulator writes once and then leaves to the client."""

    value_: float = 0.0

    def value(self, line: Line, t: float) -> Any:
        return self.value_

    @property
    def writable(self) -> bool:
        return True


BEHAVIOURS = {
    "running": Running,
    "counter": Counter,
    "stopped_for": StoppedFor,
    "temperature": Temperature,
    "setpoint": Setpoint,
}
