from __future__ import annotations

import ast
import random
from pathlib import Path

import pytest

from app.planning.astar import AStarPlanner
from app.planning.bfs import BFSPlanner
from app.planning.dfs import DFSPlanner
from app.planning.dijkstra import DijkstraPlanner
from app.planning.greedy import GreedyBestFirstPlanner
from app.planning.heuristics import zero
from app.planning.registry import ALGORITHM_KEYS, create_planner
from tests.conftest import SimpleGraph, dijkstra_all

ALL = [BFSPlanner(), DFSPlanner(), GreedyBestFirstPlanner(), DijkstraPlanner(), AStarPlanner()]


def assert_valid_path(graph, path, start, goal):
    assert path[0] == start and path[-1] == goal
    for a, b in zip(path, path[1:]):
        assert any(v == b for v, _ in graph.neighbors(a)), f"{a}->{b} is not an edge"
    assert len(set(path)) == len(path), "path revisits a node"


@pytest.mark.parametrize("planner", ALL, ids=lambda p: p.key)
def test_every_planner_returns_a_valid_path(planner, diamond_graph):
    res = planner.find_path(diamond_graph, 0, 5)
    assert res.success
    assert_valid_path(diamond_graph, res.path, 0, 5)
    assert res.nodes_explored >= 1
    assert res.elapsed_ms >= 0
    assert res.cost == pytest.approx(sum(diamond_graph.edge_cost(a, b) for a, b in zip(res.path, res.path[1:])))


def test_bfs_finds_fewest_hops_not_cheapest(diamond_graph):
    res = BFSPlanner().find_path(diamond_graph, 0, 5)
    assert res.path == [0, 2, 5]
    assert res.cost == 30


@pytest.mark.parametrize("planner", [DijkstraPlanner(), AStarPlanner(zero)], ids=["dijkstra", "astar-zero"])
def test_cost_optimal_planners_find_cheapest_path(planner, diamond_graph):
    res = planner.find_path(diamond_graph, 0, 5)
    assert res.path == [0, 1, 3, 4, 5]
    assert res.cost == 5


def test_dfs_explores_depth_first(diamond_graph):
    res = DFSPlanner().find_path(diamond_graph, 0, 5)
    # Lowest-id unvisited neighbour first: 0 → 1 → 3 → 4 → 2 → 5. A long detour — DFS is not optimal.
    assert res.path == [0, 1, 3, 4, 2, 5]
    assert res.cost == 1 + 1 + 2 + 10 + 10


@pytest.mark.parametrize("planner", ALL, ids=lambda p: p.key)
def test_start_equals_goal(planner, diamond_graph):
    res = planner.find_path(diamond_graph, 3, 3)
    assert res.success and res.path == [3] and res.cost == 0


@pytest.mark.parametrize("planner", ALL, ids=lambda p: p.key)
def test_unreachable_goal_fails_cleanly(planner):
    g = SimpleGraph({0: (0, 0), 1: (1, 0), 2: (5, 5)}, [(0, 1, 1.0)])
    res = planner.find_path(g, 0, 2)
    assert not res.success and res.path == [] and res.cost == float("inf")
    assert res.nodes_explored == 2  # exhausted the reachable component


def test_astar_matches_dijkstra_and_explores_less_on_city(world):
    rng = random.Random(3)
    n = world.node_count
    astar, dijkstra = AStarPlanner(), DijkstraPlanner()
    total_a = total_d = 0
    for _ in range(150):
        s, t = rng.randrange(n), rng.randrange(n)
        a, d = astar.find_path(world, s, t), dijkstra.find_path(world, s, t)
        assert a.success and d.success
        assert a.cost == pytest.approx(d.cost, rel=1e-9)
        assert a.nodes_explored <= d.nodes_explored
        total_a += a.nodes_explored
        total_d += d.nodes_explored
    assert total_a < 0.75 * total_d


def test_dijkstra_cost_equals_reference_shortest_path(world):
    rng = random.Random(11)
    for _ in range(20):
        s = rng.randrange(world.node_count)
        ref = dijkstra_all(world, s)
        t = rng.randrange(world.node_count)
        assert DijkstraPlanner().find_path(world, s, t).cost == pytest.approx(ref[t])


def test_greedy_and_bfs_are_valid_but_not_better_than_optimal(world):
    rng = random.Random(5)
    for _ in range(60):
        s, t = rng.randrange(world.node_count), rng.randrange(world.node_count)
        best = DijkstraPlanner().find_path(world, s, t).cost
        for planner in (GreedyBestFirstPlanner(), BFSPlanner(), DFSPlanner()):
            res = planner.find_path(world, s, t)
            assert res.success
            assert_valid_path(world, res.path, s, t)
            assert res.cost >= best - 1e-9


def test_planners_respect_known_closures(world):
    path = AStarPlanner().find_path(world, 0, 200).path
    roads = world.path_roads(path)
    world.mark_blocked(roads[len(roads) // 2], True)
    for key in ALGORITHM_KEYS:
        res = create_planner(key).find_path(world, 0, 200)
        assert res.success
        assert roads[len(roads) // 2] not in world.path_roads(res.path)


def test_trace_records_every_expansion(world):
    for key in ALGORITHM_KEYS:
        res = create_planner(key).find_path(world, 3, 150, trace=True)
        assert res.trace is not None
        assert len(res.trace.steps) == res.nodes_explored
        assert res.trace.steps[-1][0] == 150


def test_algorithms_are_independent_modules():
    """No planner may delegate to another planner (e.g. a 'DFS' that secretly calls A*)."""
    planning = Path(__file__).resolve().parents[2] / "app" / "planning"
    modules = {"bfs", "dfs", "greedy", "dijkstra", "astar"}
    for name in modules:
        tree = ast.parse((planning / f"{name}.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.rsplit(".", 1)[-1])
        assert not (imported & (modules - {name})), f"{name}.py imports {imported & modules}"
