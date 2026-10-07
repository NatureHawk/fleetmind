"""The fleet's shared belief about the road network (a blackboard).

Planners never read the ground-truth :class:`Environment` directly; they search this model.
Traffic is published by a city traffic feed and is therefore known immediately. Road
closures caused by incidents are *not* known until an agent perceives them and reports
them over the fleet channel — so belief and truth can diverge, which is exactly what makes
on-line replanning necessary.

``WorldModel`` implements the :class:`~app.planning.planner_interface.SearchGraph` protocol.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.simulation.environment import (
    MAX_SPEED_FACTOR,
    REFERENCE_SPEED_MPS,
    TRAFFIC_ENERGY_FACTOR,
    Environment,
    TrafficLevel,
    travel_time,
)


class WorldModel:
    def __init__(self, env: Environment) -> None:
        self.env = env
        self.known_traffic: list[TrafficLevel] = [r.traffic for r in env.roads]
        self.known_blocked: set[int] = set()
        self.version = 0
        self._cost: list[float] = [r.travel_time for r in env.roads]
        self._positions = [(n.x, n.y) for n in env.nodes]
        # Lower bound on the cost of travelling one metre on any road: fastest road class,
        # free-flowing traffic. Heuristics scale straight-line distance by this.
        self.min_cost_per_meter = 1.0 / (REFERENCE_SPEED_MPS * MAX_SPEED_FACTOR)

    # SearchGraph protocol ----------------------------------------------------------------
    @property
    def node_count(self) -> int:
        return len(self._positions)

    def neighbors(self, node: int) -> list[tuple[int, float]]:
        blocked = self.known_blocked
        cost = self._cost
        return [(v, cost[rid]) for v, rid in self.env.adjacency[node] if rid not in blocked]

    def position(self, node: int) -> tuple[float, float]:
        return self._positions[node]

    def edge_cost(self, a: int, b: int) -> float:
        road = self.env.road_between(a, b)
        if road is None:
            raise KeyError(f"no road between {a} and {b}")
        return self._cost[road.id]

    # Route helpers -------------------------------------------------------------------------
    def road_cost(self, road_id: int) -> float:
        return self._cost[road_id]

    def is_blocked(self, road_id: int) -> bool:
        return road_id in self.known_blocked

    def path_roads(self, path: Sequence[int]) -> list[int]:
        roads = []
        for a, b in zip(path, path[1:]):
            road = self.env.road_between(a, b)
            if road is None:
                raise KeyError(f"path step {a}->{b} is not a road")
            roads.append(road.id)
        return roads

    def path_cost(self, path: Sequence[int]) -> float:
        return sum(self._cost[r] for r in self.path_roads(path))

    def roads_energy(self, road_ids: Sequence[int], rate_wh_per_m: float) -> float:
        roads = self.env.roads
        traffic = self.known_traffic
        return sum(roads[r].length * rate_wh_per_m * TRAFFIC_ENERGY_FACTOR[traffic[r]] for r in road_ids)

    def straight_line(self, a: int, b: int) -> float:
        (ax, ay), (bx, by) = self._positions[a], self._positions[b]
        return math.hypot(bx - ax, by - ay)

    # Belief updates ------------------------------------------------------------------------
    def update_traffic(self, road_id: int, level: TrafficLevel) -> bool:
        if self.known_traffic[road_id] == level:
            return False
        self.known_traffic[road_id] = level
        road = self.env.roads[road_id]
        self._cost[road_id] = travel_time(road.length, road.road_class, level)
        self.version += 1
        return True

    def mark_blocked(self, road_id: int, blocked: bool) -> bool:
        if (road_id in self.known_blocked) == blocked:
            return False
        if blocked:
            self.known_blocked.add(road_id)
        else:
            self.known_blocked.discard(road_id)
        self.version += 1
        return True

    def hidden_closures(self) -> list[int]:
        """Roads that are closed in reality but not yet known to the fleet."""
        return sorted(r for r in self.env.blocked_ids if r not in self.known_blocked)

    def has_hidden_closures(self) -> bool:
        known = self.known_blocked
        return any(r not in known for r in self.env.blocked_ids)
