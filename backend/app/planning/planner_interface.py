"""Planner abstractions (Strategy pattern).

Every search algorithm implements :class:`PathPlanner` and operates on any object
satisfying :class:`SearchGraph`. In the simulator that graph is the fleet's
:class:`~app.simulation.world_model.WorldModel`; in tests it is a hand-built graph.

All planners report the same telemetry so they can be compared fairly:

* ``nodes_explored`` – nodes *expanded* (removed from the frontier and goal-tested)
* ``nodes_generated`` – nodes *added* to the frontier
* ``max_frontier`` – peak frontier size (memory proxy)
* ``elapsed_ms`` – wall-clock search time
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class SearchGraph(Protocol):
    @property
    def node_count(self) -> int: ...

    def neighbors(self, node: int) -> Sequence[tuple[int, float]]:
        """Traversable neighbours of ``node`` with the cost of the connecting edge."""
        ...

    def position(self, node: int) -> tuple[float, float]: ...

    def edge_cost(self, a: int, b: int) -> float: ...

    # A lower bound on cost per unit of straight-line distance (for heuristics).
    min_cost_per_meter: float


@dataclass(slots=True)
class SearchTrace:
    """Step-by-step record of a search, used by the Algorithm Explorer.

    ``steps[i] = (expanded_node, [nodes newly added to the frontier])``.
    """

    steps: list[tuple[int, list[int]]] = field(default_factory=list)

    def record(self, expanded: int, generated: list[int]) -> None:
        self.steps.append((expanded, generated))


@dataclass(slots=True)
class SearchResult:
    algorithm: str
    start: int
    goal: int
    path: list[int]
    cost: float
    success: bool
    nodes_explored: int
    nodes_generated: int
    max_frontier: int
    elapsed_ms: float
    trace: SearchTrace | None = None
    cached: bool = False

    @property
    def hops(self) -> int:
        return max(0, len(self.path) - 1)

    def as_dict(self, include_path: bool = True) -> dict:
        data = {
            "algorithm": self.algorithm,
            "start": self.start,
            "goal": self.goal,
            "cost": round(self.cost, 3),
            "success": self.success,
            "nodes_explored": self.nodes_explored,
            "nodes_generated": self.nodes_generated,
            "max_frontier": self.max_frontier,
            "elapsed_ms": round(self.elapsed_ms, 4),
            "hops": self.hops,
            "cached": self.cached,
        }
        if include_path:
            data["path"] = list(self.path)
        return data


class PathPlanner(Protocol):
    key: str
    name: str

    def find_path(self, graph: SearchGraph, start: int, goal: int, *, trace: bool = False) -> SearchResult:
        ...


def reconstruct(parent: dict[int, int | None], goal: int) -> list[int]:
    path = [goal]
    node = parent[goal]
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def path_cost(graph: SearchGraph, path: Sequence[int]) -> float:
    return sum(graph.edge_cost(a, b) for a, b in zip(path, path[1:]))
