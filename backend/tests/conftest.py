from __future__ import annotations

import math

import pytest

from app.simulation.engine import SimulationEngine
from app.simulation.generator import generate_city
from app.simulation.scenarios import ScenarioConfig
from app.simulation.world_model import WorldModel


class SimpleGraph:
    """A tiny explicit graph implementing the SearchGraph protocol (costs = given weights)."""

    def __init__(self, positions: dict[int, tuple[float, float]], edges: list[tuple[int, int, float]],
                 min_cost_per_meter: float = 0.0) -> None:
        self.positions = positions
        self.adj: dict[int, list[tuple[int, float]]] = {n: [] for n in positions}
        self.costs: dict[tuple[int, int], float] = {}
        for a, b, w in edges:
            self.adj[a].append((b, w))
            self.adj[b].append((a, w))
            self.costs[(a, b)] = self.costs[(b, a)] = w
        for lst in self.adj.values():
            lst.sort()
        self.min_cost_per_meter = min_cost_per_meter

    @property
    def node_count(self) -> int:
        return len(self.positions)

    def neighbors(self, node):
        return self.adj[node]

    def position(self, node):
        return self.positions[node]

    def edge_cost(self, a, b):
        return self.costs[(a, b)]


@pytest.fixture
def diamond_graph() -> SimpleGraph:
    """
        1 ─1─ 3
      1/        \\10
     0           5      cheapest 0-1-3-4-5 (cost 5), fewest hops 0-2-5 (2 hops, cost 30)
      20\\       /1
        2 ─10─ 4 ... and 3-4 (cost 2)
    """
    positions = {0: (0, 0), 1: (1, 1), 2: (1, -1), 3: (2, 1), 4: (2, -1), 5: (3, 0)}
    edges = [(0, 1, 1), (1, 3, 1), (3, 5, 10), (0, 2, 20), (2, 5, 10), (2, 4, 10), (3, 4, 2), (4, 5, 1)]
    return SimpleGraph(positions, edges)


@pytest.fixture
def grid_graph() -> SimpleGraph:
    """8×8 axis-aligned unit grid, unit costs (Manhattan is admissible here)."""
    n = 8
    pos = {r * n + c: (float(c), float(r)) for r in range(n) for c in range(n)}
    edges = []
    for r in range(n):
        for c in range(n):
            i = r * n + c
            if c + 1 < n:
                edges.append((i, i + 1, 1.0))
            if r + 1 < n:
                edges.append((i, i + n, 1.0))
    return SimpleGraph(pos, edges, min_cost_per_meter=1.0)


@pytest.fixture(scope="session")
def city():
    return generate_city(42173)


@pytest.fixture
def world(city) -> WorldModel:
    # Fresh belief over a shared (read-only in these tests) city.
    for r in city.roads:
        r.blocked = False
    city.blocked_ids.clear()
    return WorldModel(city)


def quiet_config(**overrides) -> ScenarioConfig:
    """A scenario with no random arrivals or incidents, for controlled tests."""
    base = dict(key="test", name="Test", seed=42173, robots=3, initial_orders=0, max_orders=0,
                order_rate_per_min=0.0, traffic_intensity=0.0, battery_min=0.9, battery_max=1.0)
    base.update(overrides)
    return ScenarioConfig(**base)


@pytest.fixture
def make_engine():
    def _make(**overrides) -> SimulationEngine:
        return SimulationEngine(quiet_config(**overrides))
    return _make


def dijkstra_all(graph, source: int) -> dict[int, float]:
    import heapq
    dist = {source: 0.0}
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        for v, w in graph.neighbors(u):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist
