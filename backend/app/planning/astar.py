"""A* search.

Informed and cost-aware: the frontier is ordered by f(n) = g(n) + h(n). With an admissible
heuristic the returned path is optimal; with a consistent one (Euclidean here) no node is
expanded twice, so A* expands a subset of what Dijkstra expands.

Closed nodes are *re-opened* when a cheaper path to them is found. That never happens with
a consistent heuristic but keeps the implementation correct for merely admissible ones.
Ties on f are broken toward larger g (deeper nodes), which reduces expansions on plateaus.
"""

from __future__ import annotations

import heapq
from itertools import count
from time import perf_counter

from app.planning.heuristics import Heuristic, euclidean
from app.planning.planner_interface import SearchGraph, SearchResult, SearchTrace, reconstruct


class AStarPlanner:
    key = "astar"
    name = "A*"

    def __init__(self, heuristic: Heuristic = euclidean) -> None:
        self.heuristic = heuristic

    def find_path(self, graph: SearchGraph, start: int, goal: int, *, trace: bool = False) -> SearchResult:
        t0 = perf_counter()
        tr = SearchTrace() if trace else None
        h = self.heuristic
        tie = count()
        g: dict[int, float] = {start: 0.0}
        parent: dict[int, int | None] = {start: None}
        closed: dict[int, float] = {}
        frontier: list[tuple[float, float, int, int]] = [(h(graph, start, goal), 0.0, next(tie), start)]
        explored = generated = 0
        max_frontier = 1
        found = False

        while frontier:
            _f, neg_g, _, node = heapq.heappop(frontier)
            cost = -neg_g
            if cost > g[node]:
                continue  # stale entry, a cheaper route to this node was queued later
            if node in closed and closed[node] <= cost:
                continue
            closed[node] = cost
            explored += 1
            if node == goal:
                found = True
                if tr:
                    tr.record(node, [])
                break
            added = []
            for nxt, edge in graph.neighbors(node):
                new_cost = cost + edge
                if new_cost < g.get(nxt, float("inf")):
                    if nxt not in g:
                        added.append(nxt)
                    g[nxt] = new_cost
                    parent[nxt] = node
                    heapq.heappush(frontier, (new_cost + h(graph, nxt, goal), -new_cost, next(tie), nxt))
            generated += len(added)
            if tr:
                tr.record(node, added)
            if len(frontier) > max_frontier:
                max_frontier = len(frontier)

        path = reconstruct(parent, goal) if found else []
        return SearchResult(self.key, start, goal, path, g[goal] if found else float("inf"), found, explored,
                            generated, max_frontier, (perf_counter() - t0) * 1000.0, tr)
