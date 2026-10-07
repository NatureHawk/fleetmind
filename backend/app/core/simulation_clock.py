"""Fixed-timestep simulation clock and wall-clock pacing.

The engine only advances in whole ticks of ``dt`` simulated seconds. The pacer converts
elapsed wall time × speed multiplier into a number of ticks to run, so rendering FPS and
server load never change simulation outcomes — only how fast they are reached.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimulationClock:
    dt: float = 0.5
    tick: int = 0

    @property
    def time(self) -> float:
        return self.tick * self.dt

    def advance(self) -> float:
        self.tick += 1
        return self.time


class FixedStepPacer:
    def __init__(self, ticks_per_second: float, max_steps_per_frame: int = 400) -> None:
        self.ticks_per_second = ticks_per_second
        self.max_steps_per_frame = max_steps_per_frame
        self._accumulator = 0.0

    def steps_due(self, wall_elapsed: float, speed: float) -> int:
        self._accumulator += max(0.0, wall_elapsed) * self.ticks_per_second * speed
        steps = int(self._accumulator)
        self._accumulator -= steps
        if steps > self.max_steps_per_frame:
            # The host fell behind (e.g. a GC pause). Drop the backlog instead of
            # spiralling; the simulation simply runs slower than requested for a frame.
            steps = self.max_steps_per_frame
            self._accumulator = 0.0
        return steps

    def reset(self) -> None:
        self._accumulator = 0.0
