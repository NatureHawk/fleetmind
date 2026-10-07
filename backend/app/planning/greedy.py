"""Greedy Best-First Search.

Informed, priority queue ordered by the heuristic h(n) only — always expands the node that
*looks* closest to the goal. Usually explores very few nodes and is fast, but ignores the
cost already paid, so it is not optimal: it can be lured down a slow road that points
toward the goal.
"""

from __future__ import annotations

import heapq
from itertools import count
from time import perf_counter

from app.planning.heuristics import Heuristic, euclidean
from app.planning.planner_interface import (
    SearchGraph,
    SearchResult,
    SearchTrace,
    path_cost,
    reconstruct,
)


class GreedyBestFirstPlanner:
    key = "greedy"
    name = "Greedy Best-First"

    def __init__(self, heuristic: Heuristic = euclidean) -> None:
        self.heuristic = heuristic

    def find_path(self, graph: SearchGraph, start: int, goal: int, *, trace: bool = False) -> SearchResult:
        t0 = perf_counter()
        tr = SearchTrace() if trace else None
        h = self.heuristic
        tie = count()
        parent: dict[int, int | None] = {start: None}
        closed: set[int] = set()
        frontier: list[tuple[float, int, int]] = [(h(graph, start, goal), next(tie), start)]
        explored = generated = 0
        max_frontier = 1
        found = False

        while frontier:
            _, _, node = heapq.heappop(frontier)
            if node in closed:
                continue
            closed.add(node)
            explored += 1
            if node == goal:
                found = True
                if tr:
                    tr.record(node, [])
                break
            added = []
            for nxt, _cost in graph.neighbors(node):
                if nxt not in parent:
                    parent[nxt] = node
                    heapq.heappush(frontier, (h(graph, nxt, goal), next(tie), nxt))
                    added.append(nxt)
            generated += len(added)
            if tr:
                tr.record(node, added)
            if len(frontier) > max_frontier:
                max_frontier = len(frontier)

        path = reconstruct(parent, goal) if found else []
        cost = path_cost(graph, path) if found else float("inf")
        return SearchResult(self.key, start, goal, path, cost, found, explored, generated, max_frontier,
                            (perf_counter() - t0) * 1000.0, tr)
