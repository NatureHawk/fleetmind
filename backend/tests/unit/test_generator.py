from __future__ import annotations

from collections import deque

from app.simulation.environment import NodeKind, RoadClass
from app.simulation.generator import generate_city


def _segments_cross(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    return (orient(p1, p2, p3) * orient(p1, p2, p4) < 0) and (orient(p3, p4, p1) * orient(p3, p4, p2) < 0)


def test_same_seed_same_city():
    a, b = generate_city(1234), generate_city(1234)
    assert a.fingerprint() == b.fingerprint()
    assert [(n.x, n.y, n.kind) for n in a.nodes] == [(n.x, n.y, n.kind) for n in b.nodes]


def test_different_seed_different_city():
    assert generate_city(1).fingerprint() != generate_city(2).fingerprint()


def test_city_is_connected(city):
    seen = {0}
    queue = deque([0])
    while queue:
        u = queue.popleft()
        for v, _ in city.adjacency[u]:
            if v not in seen:
                seen.add(v)
                queue.append(v)
    assert len(seen) == len(city.nodes)


def test_roads_do_not_cross(city):
    pos = [n.pos for n in city.nodes]
    roads = city.roads
    for i, r in enumerate(roads):
        for s in roads[i + 1:]:
            if len({r.a, r.b, s.a, s.b}) < 4:
                continue
            assert not _segments_cross(pos[r.a], pos[r.b], pos[s.a], pos[s.b]), f"{r.name} crosses {s.name}"


def test_city_has_points_of_interest_and_hierarchy(city):
    kinds = {k: len(city.nodes_of_kind(k)) for k in NodeKind}
    assert kinds[NodeKind.WAREHOUSE] == 5
    assert kinds[NodeKind.CHARGER] == 5
    assert kinds[NodeKind.CUSTOMER] == 46
    assert kinds[NodeKind.INTERSECTION] > 150
    classes = {r.road_class for r in city.roads}
    assert classes == {RoadClass.ARTERIAL, RoadClass.COLLECTOR, RoadClass.LOCAL}
    assert all(city.degree(n.id) >= 2 for n in city.nodes_of_kind(NodeKind.WAREHOUSE))


def test_not_a_grid(city):
    """Irregular network: many distinct road bearings, varied degree."""
    import math
    bearings = {round(math.degrees(math.atan2(city.nodes[r.b].y - city.nodes[r.a].y,
                                              city.nodes[r.b].x - city.nodes[r.a].x)) % 180 / 5) for r in city.roads}
    assert len(bearings) > 25
    assert len({city.degree(n.id) for n in city.nodes}) >= 4


def test_blocks_follow_euler_formula(city):
    assert len(city.faces) == len(city.roads) - len(city.nodes) + 1
