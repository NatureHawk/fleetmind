"""Breadth-First Search.

Uninformed, FIFO frontier. Finds the path with the *fewest roads*, ignoring road cost, so
on a weighted city graph it is complete but not cost-optimal. The returned ``cost`` is the
real travel time of that fewest-hops path.
"""

from __future__ import annotations

from collections import deque
from time import perf_counter

from app.planning.planner_interface import (
    SearchGraph,
    SearchResult,
    SearchTrace,
    path_cost,
    reconstruct,
)


class BFSPlanner:
    key = "bfs"
    name = "BFS"

    def find_path(self, graph: SearchGraph, start: int, goal: int, *, trace: bool = False) -> SearchResult:
        t0 = perf_counter()
        tr = SearchTrace() if trace else None
        parent: dict[int, int | None] = {start: None}
        frontier: deque[int] = deque([start])
        explored = generated = 0
        max_frontier = 1
        found = False

        while frontier:
            node = frontier.popleft()
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
                    frontier.append(nxt)
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
