"""Route planning service used by the agents.

Wraps the active :class:`PathPlanner` strategy, plans on the fleet's shared world model,
publishes telemetry for every search and memoises results. The cache key includes the
world-model version, so any traffic or closure update automatically invalidates every
cached route — robots never reuse a plan computed on stale knowledge.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace

from app.core.event_bus import EventBus, Topics
from app.planning.planner_interface import PathPlanner, SearchResult
from app.planning.registry import create_planner
from app.simulation.world_model import WorldModel


@dataclass(slots=True)
class PlanRecord:
    t: float
    robot_id: str | None
    purpose: str
    result: SearchResult


class RouteService:
    def __init__(self, world: WorldModel, bus: EventBus, algorithm: str = "astar", heuristic: str = "euclidean",
                 cache_size: int = 2048) -> None:
        self.world = world
        self.bus = bus
        self.heuristic = heuristic
        self.planner: PathPlanner = create_planner(algorithm, heuristic)
        self._cache: OrderedDict[tuple, SearchResult] = OrderedDict()
        self._cache_size = cache_size
        self.cache_hits = 0
        self.now = 0.0

    @property
    def algorithm(self) -> str:
        return self.planner.key

    def set_algorithm(self, key: str, heuristic: str | None = None) -> None:
        self.heuristic = heuristic or self.heuristic
        self.planner = create_planner(key, self.heuristic)

    def plan(self, start: int, goal: int, *, robot_id: str | None = None, purpose: str = "route") -> SearchResult:
        key = (self.planner.key, self.heuristic, start, goal, self.world.version)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            self.cache_hits += 1
            result = replace(hit, cached=True, trace=None)
        else:
            result = self.planner.find_path(self.world, start, goal)
            self._cache[key] = result
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        self.bus.publish(Topics.PLAN_COMPLETED, PlanRecord(self.now, robot_id, purpose, result))
        return result

    def explore(self, start: int, goal: int, algorithm: str | None = None) -> SearchResult:
        """Run a traced search for the Algorithm Explorer (not recorded as fleet telemetry)."""
        planner = create_planner(algorithm or self.planner.key, self.heuristic)
        return planner.find_path(self.world, start, goal, trace=True)
