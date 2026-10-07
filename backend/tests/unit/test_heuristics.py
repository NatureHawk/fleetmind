from __future__ import annotations

import random

from app.planning.astar import AStarPlanner
from app.planning.dijkstra import DijkstraPlanner
from app.planning.heuristics import euclidean, manhattan
from tests.conftest import dijkstra_all


def test_euclidean_is_admissible_on_city(world):
    rng = random.Random(1)
    for _ in range(15):
        goal = rng.randrange(world.node_count)
        true = dijkstra_all(world, goal)  # undirected: distance to goal == distance from goal
        for node, cost in true.items():
            assert euclidean(world, node, goal) <= cost + 1e-9


def test_euclidean_is_consistent_on_city(world):
    rng = random.Random(2)
    for _ in range(10):
        goal = rng.randrange(world.node_count)
        for u in range(world.node_count):
            for v, c in world.neighbors(u):
                assert euclidean(world, u, goal) <= c + euclidean(world, v, goal) + 1e-9


def test_heuristics_stay_admissible_under_congestion(world):
    from app.simulation.environment import TrafficLevel
    for rid in range(0, len(world.env.roads), 3):
        world.update_traffic(rid, TrafficLevel.JAMMED)
    goal = 17
    for node, cost in dijkstra_all(world, goal).items():
        assert euclidean(world, node, goal) <= cost + 1e-9


def test_manhattan_is_admissible_on_axis_aligned_grid(grid_graph):
    goal = 63
    for node, cost in dijkstra_all(grid_graph, goal).items():
        assert manhattan(grid_graph, node, goal) <= cost + 1e-9
    res = AStarPlanner(manhattan).find_path(grid_graph, 0, 63)
    assert res.cost == 14


def test_manhattan_overestimates_on_irregular_city(world):
    """Documented limitation: diagonal roads make |dx|+|dy| exceed the true cost somewhere."""
    found = False
    for goal in range(0, world.node_count, 25):
        for node, cost in dijkstra_all(world, goal).items():
            if manhattan(world, node, goal) > cost + 1e-6:
                found = True
                break
        if found:
            break
    assert found


def test_astar_with_euclidean_beats_uninformed_search(world):
    a = AStarPlanner(euclidean).find_path(world, 5, 250)
    d = DijkstraPlanner().find_path(world, 5, 250)
    assert a.cost == d.cost
    assert a.nodes_explored < d.nodes_explored
