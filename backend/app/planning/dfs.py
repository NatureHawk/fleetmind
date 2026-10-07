"""Depth-First Search (graph search, iterative).

Uninformed, LIFO frontier. Dives along one branch until it dead-ends, then backtracks.
Complete on finite graphs (visited set prevents cycles) but neither hop- nor cost-optimal:
in a city it typically returns long, winding routes. Neighbours are pushed in reverse id
order so the lowest-id neighbour is explored first, making the result deterministic.
"""

from __future__ import annotations

from time import perf_counter

from app.planning.planner_interface import (
    SearchGraph,
    SearchResult,
    SearchTrace,
    path_cost,
    reconstruct,
)


class DFSPlanner:
    key = "dfs"
    name = "DFS"

    def find_path(self, graph: SearchGraph, start: int, goal: int, *, trace: bool = False) -> SearchResult:
        t0 = perf_counter()
        tr = SearchTrace() if trace else None
        parent: dict[int, int | None] = {}
        stack: list[tuple[int, int | None]] = [(start, None)]
        explored = generated = 0
        max_frontier = 1
        found = False

        while stack:
            node, via = stack.pop()
            if node in parent:
                continue  # already expanded through another branch
            parent[node] = via
            explored += 1
            if node == goal:
                found = True
                if tr:
                    tr.record(node, [])
                break
            added = []
            for nxt, _cost in reversed(graph.neighbors(node)):
                if nxt not in parent:
                    stack.append((nxt, node))
                    added.append(nxt)
            generated += len(added)
            if tr:
                tr.record(node, added)
            if len(stack) > max_frontier:
                max_frontier = len(stack)

        path = reconstruct(parent, goal) if found else []
        cost = path_cost(graph, path) if found else float("inf")
        return SearchResult(self.key, start, goal, path, cost, found, explored, generated, max_frontier,
                            (perf_counter() - t0) * 1000.0, tr)
