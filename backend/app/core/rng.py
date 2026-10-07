"""Deterministic random streams.

Every stochastic subsystem (city layout, fleet, order arrivals, incidents) draws from its
own stream derived from the run seed. Streams are independent, so changing the number of
robots does not change the city or the order sequence — a prerequisite for fair A/B
experiments between algorithms.
"""

from __future__ import annotations

import random


class SeedStreams:
    def __init__(self, seed: int) -> None:
        self.seed = int(seed)

    def stream(self, name: str) -> random.Random:
        # String seeds are hashed with SHA-512 by CPython, so this is stable across
        # processes and independent of PYTHONHASHSEED.
        return random.Random(f"fleetmind:{self.seed}:{name}")
