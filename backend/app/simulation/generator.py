"""Deterministic procedural generation of a logistics district.

Pipeline
--------
1. **Zone layout** — weighted Voronoi seeds with low-frequency noise produce irregular
   industrial, commercial, residential and energy districts.
2. **Intersections** — variable-radius Poisson-disk sampling. Industrial districts get large
   blocks, the commercial core is dense.
3. **Roads** — the Gabriel graph of the intersections. It is planar (no crossing roads),
   connected and contains the minimum spanning tree.
4. **Pruning** — remove roads that meet at very acute angles and a random fraction of the
   rest (never disconnecting the network, never creating dead ends) to form city blocks.
5. **Road hierarchy** — arterials follow near-straight corridors across the city; collectors
   link distant neighbourhoods; everything else is a local street.
6. **Points of interest** — warehouses in industrial zones, chargers spread over the city,
   customers in residential/commercial zones (farthest-point sampling for even coverage).
7. **Blocks** — bounded faces of the planar graph, used by the renderer.

The same ``seed`` always yields the same city.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import deque
from dataclasses import dataclass

from app.core.geometry import centroid, distance, point_line_distance, signed_area
from app.simulation.environment import (
    District,
    Environment,
    Face,
    Node,
    NodeKind,
    Road,
    RoadClass,
    Zone,
)


@dataclass(frozen=True)
class CityParams:
    width: float = 3200.0
    height: float = 2000.0
    spacing: float = 102.0
    warehouses: int = 5
    chargers: int = 5
    customers: int = 46
    prune_fraction: float = 0.34
    margin: float = 70.0


ZONE_SPACING = {
    Zone.INDUSTRIAL: 1.32,
    Zone.ENERGY: 1.15,
    Zone.COMMERCIAL: 0.82,
    Zone.RESIDENTIAL: 0.95,
}

DISTRICT_NAMES = {
    Zone.INDUSTRIAL: ["Foundry Yards", "Dockside Works", "Kiln Row", "Ironbridge", "Cargo Flats"],
    Zone.COMMERCIAL: ["Exchange Quarter", "Market Cross", "Central Arcade"],
    Zone.RESIDENTIAL: ["Elm Heights", "Larkfield", "Southmere", "Willow Park", "Northgate", "Ashby Green"],
    Zone.ENERGY: ["Grid Hub", "Voltage Yard"],
}


@dataclass
class _ZoneSeed:
    x: float
    y: float
    zone: Zone
    weight: float
    name: str
    phase: float


class _Layout:
    def __init__(self, rng: random.Random, p: CityParams) -> None:
        W, H = p.width, p.height
        flip = rng.random() < 0.5

        def X(f: float) -> float:
            return (1.0 - f if flip else f) * W

        ind = rng.sample(DISTRICT_NAMES[Zone.INDUSTRIAL], 2)
        res = rng.sample(DISTRICT_NAMES[Zone.RESIDENTIAL], 4)
        com = rng.choice(DISTRICT_NAMES[Zone.COMMERCIAL])
        eng = rng.choice(DISTRICT_NAMES[Zone.ENERGY])
        u = rng.uniform
        self.seeds = [
            _ZoneSeed(X(u(0.08, 0.15)), H * u(0.2, 0.38), Zone.INDUSTRIAL, 1.0, ind[0], u(0, 6.28)),
            _ZoneSeed(X(u(0.1, 0.18)), H * u(0.64, 0.82), Zone.INDUSTRIAL, 1.0, ind[1], u(0, 6.28)),
            _ZoneSeed(X(u(0.33, 0.39)), H * u(0.58, 0.78), Zone.ENERGY, 0.55, eng, u(0, 6.28)),
            _ZoneSeed(X(u(0.5, 0.57)), H * u(0.4, 0.55), Zone.COMMERCIAL, 0.9, com, u(0, 6.28)),
            _ZoneSeed(X(u(0.78, 0.88)), H * u(0.18, 0.33), Zone.RESIDENTIAL, 1.0, res[0], u(0, 6.28)),
            _ZoneSeed(X(u(0.8, 0.9)), H * u(0.66, 0.82), Zone.RESIDENTIAL, 1.0, res[1], u(0, 6.28)),
            _ZoneSeed(X(u(0.48, 0.6)), H * u(0.06, 0.16), Zone.RESIDENTIAL, 0.85, res[2], u(0, 6.28)),
            _ZoneSeed(X(u(0.55, 0.66)), H * u(0.84, 0.94), Zone.RESIDENTIAL, 0.85, res[3], u(0, 6.28)),
        ]
        self.freq = [(u(0.0016, 0.0032), u(0.0016, 0.0032)) for _ in range(3)]

    def seed_index(self, x: float, y: float) -> int:
        best, best_d = 0, math.inf
        for i, s in enumerate(self.seeds):
            fx, fy = self.freq[i % 3]
            wobble = math.sin(x * fx + s.phase) + math.cos(y * fy - s.phase)
            d = math.hypot(x - s.x, y - s.y) / s.weight + 70.0 * wobble
            if d < best_d:
                best, best_d = i, d
        return best

    def zone_at(self, x: float, y: float) -> Zone:
        return self.seeds[self.seed_index(x, y)].zone


# ---------------------------------------------------------------------------------------
# Intersections


def _poisson_disk(rng: random.Random, p: CityParams, layout: _Layout) -> list[tuple[float, float]]:
    r_min = p.spacing * min(ZONE_SPACING.values())
    r_max = p.spacing * max(ZONE_SPACING.values())
    cell = r_min / math.sqrt(2)
    reach = int(math.ceil(r_max / cell))
    grid: dict[tuple[int, int], int] = {}
    pts: list[tuple[float, float]] = []
    radii: list[float] = []
    lo_x, hi_x = p.margin, p.width - p.margin
    lo_y, hi_y = p.margin, p.height - p.margin

    def radius_at(x: float, y: float) -> float:
        return p.spacing * ZONE_SPACING[layout.zone_at(x, y)]

    def fits(x: float, y: float, r: float) -> bool:
        gx, gy = int(x / cell), int(y / cell)
        for i in range(gx - reach, gx + reach + 1):
            for j in range(gy - reach, gy + reach + 1):
                idx = grid.get((i, j))
                if idx is None:
                    continue
                qx, qy = pts[idx]
                sep = 0.5 * (r + radii[idx])
                if (qx - x) ** 2 + (qy - y) ** 2 < sep * sep:
                    return False
        return True

    def add(x: float, y: float, r: float) -> None:
        grid[(int(x / cell), int(y / cell))] = len(pts)
        pts.append((x, y))
        radii.append(r)

    x0, y0 = p.width / 2 + rng.uniform(-50, 50), p.height / 2 + rng.uniform(-50, 50)
    add(x0, y0, radius_at(x0, y0))
    active = [0]
    while active:
        k = rng.randrange(len(active))
        i = active[k]
        px, py = pts[i]
        r = radii[i]
        placed = False
        for _ in range(20):
            ang = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(r, 1.9 * r)
            x, y = px + math.cos(ang) * dist, py + math.sin(ang) * dist
            if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
                continue
            rr = radius_at(x, y)
            if fits(x, y, rr):
                add(x, y, rr)
                active.append(len(pts) - 1)
                placed = True
                break
        if not placed:
            active[k] = active[-1]
            active.pop()
    return pts


# ---------------------------------------------------------------------------------------
# Roads


def _gabriel_edges(pts: list[tuple[float, float]], max_len: float) -> set[tuple[int, int]]:
    cell = max_len
    grid: dict[tuple[int, int], list[int]] = {}
    for i, (x, y) in enumerate(pts):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(i)

    def near(i: int) -> list[int]:
        x, y = pts[i]
        gx, gy = int(x // cell), int(y // cell)
        out = []
        for a in (gx - 1, gx, gx + 1):
            for b in (gy - 1, gy, gy + 1):
                for j in grid.get((a, b), ()):
                    if j != i and distance(pts[i], pts[j]) <= max_len:
                        out.append(j)
        return out

    edges: set[tuple[int, int]] = set()
    for i in range(len(pts)):
        neigh = near(i)
        for j in neigh:
            if j < i:
                continue
            (ax, ay), (bx, by) = pts[i], pts[j]
            mx, my = (ax + bx) / 2, (ay + by) / 2
            r2 = ((bx - ax) ** 2 + (by - ay) ** 2) / 4 - 1e-6
            if all((pts[k][0] - mx) ** 2 + (pts[k][1] - my) ** 2 >= r2 for k in neigh if k != j):
                edges.add((i, j))
    return edges


def _largest_component(n: int, edges: set[tuple[int, int]]) -> set[int]:
    adj: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    seen: set[int] = set()
    best: set[int] = set()
    for s in range(n):
        if s in seen:
            continue
        comp = {s}
        queue = deque([s])
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if v not in comp:
                    comp.add(v)
                    queue.append(v)
        seen |= comp
        if len(comp) > len(best):
            best = comp
    return best


def _still_connected(adj: list[set[int]], a: int, b: int) -> bool:
    """Is ``b`` reachable from ``a`` once the road a–b is removed? (connectivity check)"""
    seen = {a}
    queue = deque([a])
    while queue:
        u = queue.popleft()
        for v in adj[u]:
            if u == a and v == b:
                continue
            if v == b:
                return True
            if v not in seen:
                seen.add(v)
                queue.append(v)
    return False


def _prune(rng: random.Random, pts: list[tuple[float, float]], edges: set[tuple[int, int]],
           fraction: float) -> set[tuple[int, int]]:
    adj: list[set[int]] = [set() for _ in pts]
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)

    def try_remove(a: int, b: int) -> bool:
        if b not in adj[a] or len(adj[a]) <= 2 or len(adj[b]) <= 2:
            return False
        if not _still_connected(adj, a, b):
            return False
        adj[a].discard(b)
        adj[b].discard(a)
        return True

    # 1. Acute junctions look unnatural: drop the longer of two roads meeting at < 32°.
    acute: set[tuple[int, int]] = set()
    for u in range(len(pts)):
        nb = sorted(adj[u], key=lambda v: math.atan2(pts[v][1] - pts[u][1], pts[v][0] - pts[u][0]))
        if len(nb) < 3:
            continue
        angs = [math.atan2(pts[v][1] - pts[u][1], pts[v][0] - pts[u][0]) for v in nb]
        for k in range(len(nb)):
            gap = (angs[(k + 1) % len(nb)] - angs[k]) % (2 * math.pi)
            if gap < math.radians(32):
                v1, v2 = nb[k], nb[(k + 1) % len(nb)]
                longer = v1 if distance(pts[u], pts[v1]) > distance(pts[u], pts[v2]) else v2
                acute.add((min(u, longer), max(u, longer)))
    for a, b in sorted(acute, key=lambda e: -distance(pts[e[0]], pts[e[1]])):
        try_remove(a, b)

    # 2. Random pruning merges small triangles into city blocks.
    remaining = sorted((min(a, b), max(a, b)) for a in range(len(pts)) for b in adj[a] if a < b)
    rng.shuffle(remaining)
    target = int(len(remaining) * fraction)
    removed = 0
    for a, b in remaining:
        if removed >= target:
            break
        if try_remove(a, b):
            removed += 1

    return {(a, b) for a in range(len(pts)) for b in adj[a] if a < b}


def _corridor(pts: list[tuple[float, float]], adj: list[list[int]], s: int, t: int,
              line: tuple[tuple[float, float], tuple[float, float]], tolerance: float) -> list[int]:
    """Generation-time helper: find a near-straight corridor between s and t.

    Cost penalises roads that stray from the line between the anchors, which produces
    arterials that look like real avenues. This only shapes the map; it is unrelated to
    the agents' route planners in ``app.planning``.
    """
    a, b = line

    def cost(u: int, v: int) -> float:
        mid = ((pts[u][0] + pts[v][0]) / 2, (pts[u][1] + pts[v][1]) / 2)
        dev = point_line_distance(mid, a, b)
        return distance(pts[u], pts[v]) * (1.0 + (dev / tolerance) ** 2)

    dist = {s: 0.0}
    prev: dict[int, int] = {}
    heap = [(0.0, s)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == t:
            break
        if d > dist[u]:
            continue
        for v in adj[u]:
            nd = d + cost(u, v)
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if t not in dist:
        return []
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return path[::-1]


def _classify_roads(rng: random.Random, pts: list[tuple[float, float]], edges: list[tuple[int, int]],
                    p: CityParams) -> dict[tuple[int, int], RoadClass]:
    adj: list[list[int]] = [[] for _ in pts]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    W, H = p.width, p.height

    def nearest(x: float, y: float) -> int:
        return min(range(len(pts)), key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - y) ** 2)

    classes = {e: RoadClass.LOCAL for e in edges}
    u = rng.uniform
    arterial_lines = [
        ((0.0, H * u(0.26, 0.34)), (W, H * u(0.26, 0.36))),
        ((0.0, H * u(0.64, 0.74)), (W, H * u(0.62, 0.72))),
        ((W * u(0.42, 0.5), 0.0), (W * u(0.5, 0.58), H)),
        ((W * u(0.04, 0.12), H * u(0.85, 0.95)), (W * u(0.86, 0.96), H * u(0.06, 0.14))),
    ]
    for a, b in arterial_lines:
        path = _corridor(pts, adj, nearest(*a), nearest(*b), (a, b), tolerance=140.0)
        for x, y in zip(path, path[1:]):
            classes[(min(x, y), max(x, y))] = RoadClass.ARTERIAL

    for _ in range(7):
        for _attempt in range(30):
            s, t = rng.randrange(len(pts)), rng.randrange(len(pts))
            if distance(pts[s], pts[t]) > 0.32 * W:
                break
        path = _corridor(pts, adj, s, t, (pts[s], pts[t]), tolerance=230.0)
        for x, y in zip(path, path[1:]):
            key = (min(x, y), max(x, y))
            if classes[key] == RoadClass.LOCAL:
                classes[key] = RoadClass.COLLECTOR
    return classes


# ---------------------------------------------------------------------------------------
# Points of interest & blocks


def _farthest_point_sample(rng: random.Random, pts: list[tuple[float, float]], candidates: list[int],
                           count: int, existing: list[int]) -> list[int]:
    chosen: list[int] = []
    pool = list(candidates)
    if not pool:
        return chosen
    min_d = {i: min((distance(pts[i], pts[e]) for e in existing), default=math.inf) for i in pool}
    if not existing:
        first = rng.choice(pool)
        chosen.append(first)
        pool.remove(first)
        for i in pool:
            min_d[i] = distance(pts[i], pts[first])
    while pool and len(chosen) < count:
        best = max(pool, key=lambda i: (min_d[i], -i))
        chosen.append(best)
        pool.remove(best)
        for i in pool:
            d = distance(pts[i], pts[best])
            if d < min_d[i]:
                min_d[i] = d
    return chosen


def _faces(pts: list[tuple[float, float]], edges: list[tuple[int, int]]) -> list[list[int]]:
    nbrs: dict[int, list[int]] = {}
    for a, b in edges:
        nbrs.setdefault(a, []).append(b)
        nbrs.setdefault(b, []).append(a)
    for u, lst in nbrs.items():
        lst.sort(key=lambda v: math.atan2(pts[v][1] - pts[u][1], pts[v][0] - pts[u][0]))

    visited: set[tuple[int, int]] = set()
    faces: list[list[int]] = []
    for a, b in edges:
        for start in ((a, b), (b, a)):
            if start in visited:
                continue
            face = []
            u, v = start
            guard = 0
            while (u, v) not in visited and guard < 10_000:
                visited.add((u, v))
                face.append(u)
                lst = nbrs[v]
                idx = lst.index(u)
                u, v = v, lst[(idx - 1) % len(lst)]
                guard += 1
            if len(face) >= 3:
                faces.append(face)
    if not faces:
        return []
    areas = [signed_area([pts[i] for i in f]) for f in faces]
    outer = max(range(len(faces)), key=lambda i: abs(areas[i]))
    outer_sign = math.copysign(1.0, areas[outer])
    return [f for f, ar in zip(faces, areas) if math.copysign(1.0, ar) != outer_sign and abs(ar) > 1.0]


# ---------------------------------------------------------------------------------------


def generate_city(seed: int, params: CityParams | None = None) -> Environment:
    p = params or CityParams()
    rng = random.Random(f"fleetmind:{seed}:city")
    layout = _Layout(rng, p)

    raw_pts = _poisson_disk(rng, p, layout)
    raw_edges = _gabriel_edges(raw_pts, max_len=p.spacing * 2.6)
    keep = sorted(_largest_component(len(raw_pts), raw_edges))
    remap = {old: new for new, old in enumerate(keep)}
    pts = [raw_pts[i] for i in keep]
    edges_set = {(remap[a], remap[b]) for a, b in raw_edges if a in remap and b in remap}
    edges_set = _prune(rng, pts, edges_set, p.prune_fraction)
    edges = sorted(edges_set)
    classes = _classify_roads(rng, pts, edges, p)

    degree = [0] * len(pts)
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    seed_idx = [layout.seed_index(x, y) for x, y in pts]
    zones = [layout.seeds[i].zone for i in seed_idx]

    industrial = [i for i in range(len(pts)) if zones[i] == Zone.INDUSTRIAL and degree[i] >= 3]
    if len(industrial) < p.warehouses:
        industrial = [i for i in range(len(pts)) if degree[i] >= 3]
    warehouses = _farthest_point_sample(rng, pts, industrial, p.warehouses, [])

    energy_seed = next(s for s in layout.seeds if s.zone == Zone.ENERGY)
    used = set(warehouses)
    hub = min((i for i in range(len(pts)) if i not in used and degree[i] >= 3),
              key=lambda i: distance(pts[i], (energy_seed.x, energy_seed.y)))
    chargers = [hub]
    used.add(hub)
    # Chargers serve the whole fleet, so keep them off the city fringe.
    charger_pool = [i for i in range(len(pts)) if i not in used and degree[i] >= 3
                    and 320 < pts[i][0] < p.width - 320 and 260 < pts[i][1] < p.height - 260]
    chargers += _farthest_point_sample(rng, pts, charger_pool, p.chargers - 1, warehouses + chargers)
    used |= set(chargers)

    customer_pool = [i for i in range(len(pts)) if i not in used
                     and zones[i] in (Zone.RESIDENTIAL, Zone.COMMERCIAL)]
    customers = _farthest_point_sample(rng, pts, customer_pool, p.customers, warehouses + chargers)

    kinds = [NodeKind.INTERSECTION] * len(pts)
    names = [f"N-{i}" for i in range(len(pts))]
    for k, i in enumerate(warehouses, start=1):
        kinds[i], names[i] = NodeKind.WAREHOUSE, f"W-{k}"
    for k, i in enumerate(chargers, start=1):
        kinds[i], names[i] = NodeKind.CHARGER, f"CS-{k}"
    for k, i in enumerate(sorted(customers, key=lambda i: (pts[i][1] // 400, pts[i][0])), start=1):
        kinds[i], names[i] = NodeKind.CUSTOMER, f"C-{k:02d}"

    nodes = [Node(i, round(x, 2), round(y, 2), kinds[i], zones[i], names[i]) for i, (x, y) in enumerate(pts)]
    # Road length is the exact distance between the *stored* coordinates: rounding it separately could make a
    # road marginally shorter than the straight line, breaking heuristic admissibility.
    roads = [Road(rid, a, b, distance(nodes[a].pos, nodes[b].pos), classes[(a, b)]) for rid, (a, b) in enumerate(edges)]

    faces = []
    for fid, f in enumerate(_faces(pts, edges)):
        cx, cy = centroid([pts[i] for i in f])
        faces.append(Face(fid, f, layout.zone_at(cx, cy)))

    districts = []
    for si, s in enumerate(layout.seeds):
        members = [pts[i] for i in range(len(pts)) if seed_idx[i] == si]
        if len(members) >= 4:
            cx, cy = centroid(members)
            districts.append(District(s.name, s.zone, round(cx, 1), round(cy, 1)))

    charger_slots = {i: rng.choice((2, 2, 3)) for i in chargers}
    return Environment(seed=seed, width=p.width, height=p.height, nodes=nodes, roads=roads,
                       faces=faces, districts=districts, charger_slots=charger_slots)
