"""Heuristics for informed search (Greedy Best-First, A*).

Edge cost in FleetMind is travel time (s). A heuristic must therefore convert distance into
time. Multiplying straight-line distance by ``graph.min_cost_per_meter`` — the cost of a
metre on the fastest road class in free-flowing traffic — yields a value that can never
exceed the true remaining cost:

* **Euclidean** is *admissible and consistent* on FleetMind's irregular road graph, because
  every road is a straight segment and no road is cheaper per metre than the bound.
* **Manhattan** is admissible only on axis-aligned grids. On an irregular graph it can
  overestimate (a diagonal road is shorter than |dx|+|dy|), so A* may lose optimality.
  It is offered for experimentation and to demonstrate exactly that effect.
* **Zero** turns A* into Dijkstra and Greedy into an uninformed search (useful baseline).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.planning.planner_interface import SearchGraph

Heuristic = Callable[[SearchGraph, int, int], float]


def euclidean(graph: SearchGraph, node: int, goal: int) -> float:
    (x1, y1), (x2, y2) = graph.position(node), graph.position(goal)
    return math.hypot(x2 - x1, y2 - y1) * graph.min_cost_per_meter


def manhattan(graph: SearchGraph, node: int, goal: int) -> float:
    (x1, y1), (x2, y2) = graph.position(node), graph.position(goal)
    return (abs(x2 - x1) + abs(y2 - y1)) * graph.min_cost_per_meter


def zero(graph: SearchGraph, node: int, goal: int) -> float:
    return 0.0


HEURISTICS: dict[str, Heuristic] = {
    "euclidean": euclidean,
    "manhattan": manhattan,
    "zero": zero,
}

HEURISTIC_INFO = {
    "euclidean": "Straight-line distance × minimum cost per metre. Admissible and consistent here.",
    "manhattan": "|dx| + |dy| × minimum cost per metre. Admissible only on axis-aligned grids.",
    "zero": "h(n) = 0. A* degenerates to Dijkstra.",
}


def get_heuristic(name: str) -> Heuristic:
    try:
        return HEURISTICS[name]
    except KeyError as exc:
        raise ValueError(f"unknown heuristic '{name}'; choose from {sorted(HEURISTICS)}") from exc
