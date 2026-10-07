"""Dijkstra's algorithm (uniform-cost search).

Uninformed but cost-aware: the priority queue is ordered by g(n), the cheapest known cost
from the start. With non-negative edge costs the first time the goal is expanded its cost
is optimal. It expands every node cheaper than the goal, in all directions, so it explores
more of the city than A*.
"""

from __future__ import annotations

import heapq
from itertools import count
from time import perf_counter

from app.planning.planner_interface import SearchGraph, SearchResult, SearchTrace, reconstruct


class DijkstraPlanner:
    key = "dijkstra"
    name = "Dijkstra"

    def find_path(self, graph: SearchGraph, start: int, goal: int, *, trace: bool = False) -> SearchResult:
        t0 = perf_counter()
        tr = SearchTrace() if trace else None
        tie = count()
        g: dict[int, float] = {start: 0.0}
        parent: dict[int, int | None] = {start: None}
        closed: set[int] = set()
        frontier: list[tuple[float, int, int]] = [(0.0, next(tie), start)]
        explored = generated = 0
        max_frontier = 1
        found = False

        while frontier:
            cost, _, node = heapq.heappop(frontier)
            if node in closed:
                continue  # stale queue entry
            closed.add(node)
            explored += 1
            if node == goal:
                found = True
                if tr:
                    tr.record(node, [])
                break
            added = []
            for nxt, edge in graph.neighbors(node):
                if nxt in closed:
                    continue
                new_cost = cost + edge
                if new_cost < g.get(nxt, float("inf")):
                    if nxt not in g:
                        added.append(nxt)
                    g[nxt] = new_cost
                    parent[nxt] = node
                    heapq.heappush(frontier, (new_cost, next(tie), nxt))
            generated += len(added)
            if tr:
                tr.record(node, added)
            if len(frontier) > max_frontier:
                max_frontier = len(frontier)

        path = reconstruct(parent, goal) if found else []
        return SearchResult(self.key, start, goal, path, g[goal] if found else float("inf"), found, explored,
                            generated, max_frontier, (perf_counter() - t0) * 1000.0, tr)
