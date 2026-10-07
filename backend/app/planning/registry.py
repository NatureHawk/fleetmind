"""Planner registry and algorithm catalogue (documentation surfaced in the UI)."""

from __future__ import annotations

from app.planning.astar import AStarPlanner
from app.planning.bfs import BFSPlanner
from app.planning.dfs import DFSPlanner
from app.planning.dijkstra import DijkstraPlanner
from app.planning.greedy import GreedyBestFirstPlanner
from app.planning.heuristics import get_heuristic
from app.planning.planner_interface import PathPlanner

ALGORITHM_KEYS = ("bfs", "dfs", "greedy", "dijkstra", "astar")


def create_planner(key: str, heuristic: str = "euclidean") -> PathPlanner:
    if key == "bfs":
        return BFSPlanner()
    if key == "dfs":
        return DFSPlanner()
    if key == "greedy":
        return GreedyBestFirstPlanner(get_heuristic(heuristic))
    if key == "dijkstra":
        return DijkstraPlanner()
    if key == "astar":
        return AStarPlanner(get_heuristic(heuristic))
    raise ValueError(f"unknown algorithm '{key}'; choose from {list(ALGORITHM_KEYS)}")


ALGORITHM_CATALOG: dict[str, dict] = {
    "bfs": {
        "key": "bfs",
        "name": "Breadth-First Search",
        "short": "BFS",
        "family": "uninformed",
        "frontier": "FIFO queue",
        "uses_cost": False,
        "uses_heuristic": False,
        "complete": True,
        "optimal": "Fewest roads only — ignores travel time",
        "time_complexity": "O(V + E)",
        "space_complexity": "O(V)",
        "purpose": "Explore the network level by level; returns the route with the fewest road segments.",
        "fleet_behaviour": "Ignores arterials and traffic, so robots take short-hop routes through slow local "
                           "streets and congested roads.",
        "performs_well": "Unweighted graphs, or when every road costs roughly the same.",
    },
    "dfs": {
        "key": "dfs",
        "name": "Depth-First Search",
        "short": "DFS",
        "family": "uninformed",
        "frontier": "LIFO stack",
        "uses_cost": False,
        "uses_heuristic": False,
        "complete": True,
        "optimal": "No",
        "time_complexity": "O(V + E)",
        "space_complexity": "O(V)",
        "purpose": "Commit to one branch and backtrack on dead ends; returns the first route it stumbles on.",
        "fleet_behaviour": "Produces long, winding routes. Robots drive far more, burn more energy and visit "
                           "chargers more often — a useful worst-case baseline.",
        "performs_well": "Reachability checks and deep, narrow search spaces where any path will do.",
    },
    "greedy": {
        "key": "greedy",
        "name": "Greedy Best-First Search",
        "short": "Greedy",
        "family": "informed",
        "frontier": "Priority queue on h(n)",
        "uses_cost": False,
        "uses_heuristic": True,
        "complete": True,
        "optimal": "No",
        "time_complexity": "O(E log V) worst case",
        "space_complexity": "O(V)",
        "purpose": "Always expand the node that appears closest to the goal by straight-line distance.",
        "fleet_behaviour": "Very few expansions and fast planning, but blind to traffic and road speed, so routes "
                           "head straight at the goal even through jams.",
        "performs_well": "Open graphs where the straight line is a good guide and planning time matters most.",
    },
    "dijkstra": {
        "key": "dijkstra",
        "name": "Dijkstra (Uniform-Cost Search)",
        "short": "Dijkstra",
        "family": "uninformed",
        "frontier": "Priority queue on g(n)",
        "uses_cost": True,
        "uses_heuristic": False,
        "complete": True,
        "optimal": "Yes (non-negative costs)",
        "time_complexity": "O((V + E) log V)",
        "space_complexity": "O(V)",
        "purpose": "Expand nodes in order of cheapest known travel time from the start.",
        "fleet_behaviour": "Optimal, traffic-aware routes; explores in every direction, so it expands many more "
                           "nodes than A*.",
        "performs_well": "Weighted graphs without a good heuristic, or one-to-many queries.",
    },
    "astar": {
        "key": "astar",
        "name": "A* Search",
        "short": "A*",
        "family": "informed",
        "frontier": "Priority queue on f(n) = g(n) + h(n)",
        "uses_cost": True,
        "uses_heuristic": True,
        "complete": True,
        "optimal": "Yes, with an admissible heuristic (Euclidean)",
        "time_complexity": "O((V + E) log V) worst case; far less with a good heuristic",
        "space_complexity": "O(V)",
        "purpose": "Find low-cost paths efficiently by combining cost so far with an admissible estimate of the "
                   "cost to go.",
        "fleet_behaviour": "Same optimal, traffic-aware routes as Dijkstra while expanding a fraction of the nodes "
                           "— the default planner for the fleet.",
        "performs_well": "Weighted spatial graphs with a meaningful distance heuristic.",
    },
}
