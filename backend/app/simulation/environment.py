"""The logistics environment: a weighted, undirected road graph (ground truth).

Nodes are warehouses, customers, charging stations and intersections. Edges are roads with
a length, a road class, a traffic level and a blocked flag. This module holds the *true*
state of the world; agents plan on :class:`~app.simulation.world_model.WorldModel`, their
shared belief about it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class NodeKind(StrEnum):
    WAREHOUSE = "warehouse"
    CUSTOMER = "customer"
    CHARGER = "charger"
    INTERSECTION = "intersection"


class Zone(StrEnum):
    INDUSTRIAL = "industrial"
    COMMERCIAL = "commercial"
    RESIDENTIAL = "residential"
    ENERGY = "energy"


class RoadClass(StrEnum):
    ARTERIAL = "arterial"
    COLLECTOR = "collector"
    LOCAL = "local"


class TrafficLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    JAMMED = 3

    @property
    def label(self) -> str:
        return self.name.lower()


# Movement model ------------------------------------------------------------------------
# Edge cost used by the planners is the travel time (seconds) for a reference robot.
REFERENCE_SPEED_MPS = 8.0
ROAD_SPEED_FACTOR: dict[RoadClass, float] = {
    RoadClass.ARTERIAL: 1.35,
    RoadClass.COLLECTOR: 1.0,
    RoadClass.LOCAL: 0.8,
}
TRAFFIC_TIME_FACTOR: dict[TrafficLevel, float] = {
    TrafficLevel.LOW: 1.0,
    TrafficLevel.MODERATE: 1.5,
    TrafficLevel.HIGH: 2.3,
    TrafficLevel.JAMMED: 3.6,
}
# Stop-and-go traffic costs energy, not only time.
TRAFFIC_ENERGY_FACTOR: dict[TrafficLevel, float] = {
    TrafficLevel.LOW: 1.0,
    TrafficLevel.MODERATE: 1.12,
    TrafficLevel.HIGH: 1.3,
    TrafficLevel.JAMMED: 1.55,
}
REFERENCE_ENERGY_WH_PER_M = 0.038
MAX_SPEED_FACTOR = max(ROAD_SPEED_FACTOR.values())


def travel_time(length_m: float, road_class: RoadClass, traffic: TrafficLevel,
                speed_mps: float = REFERENCE_SPEED_MPS) -> float:
    return length_m / (speed_mps * ROAD_SPEED_FACTOR[road_class]) * TRAFFIC_TIME_FACTOR[traffic]


def energy_cost(length_m: float, traffic: TrafficLevel,
                rate_wh_per_m: float = REFERENCE_ENERGY_WH_PER_M) -> float:
    return length_m * rate_wh_per_m * TRAFFIC_ENERGY_FACTOR[traffic]


@dataclass(slots=True)
class Node:
    id: int
    x: float
    y: float
    kind: NodeKind
    zone: Zone
    name: str

    @property
    def pos(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass(slots=True)
class Road:
    id: int
    a: int
    b: int
    length: float
    road_class: RoadClass
    traffic: TrafficLevel = TrafficLevel.LOW
    blocked: bool = False

    @property
    def name(self) -> str:
        return f"E-{self.id}"

    def other(self, node: int) -> int:
        return self.b if node == self.a else self.a

    @property
    def travel_time(self) -> float:
        return travel_time(self.length, self.road_class, self.traffic)

    @property
    def energy_cost(self) -> float:
        return energy_cost(self.length, self.traffic)


@dataclass(slots=True)
class Face:
    """A city block: a bounded face of the planar road graph (used for rendering)."""

    id: int
    nodes: list[int]
    zone: Zone


@dataclass(slots=True)
class District:
    name: str
    zone: Zone
    x: float
    y: float


@dataclass
class Environment:
    seed: int
    width: float
    height: float
    nodes: list[Node]
    roads: list[Road]
    faces: list[Face] = field(default_factory=list)
    districts: list[District] = field(default_factory=list)
    charger_slots: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.blocked_ids: set[int] = {r.id for r in self.roads if r.blocked}
        self.adjacency: list[list[tuple[int, int]]] = [[] for _ in self.nodes]
        self._road_index: dict[tuple[int, int], int] = {}
        for road in self.roads:
            self.adjacency[road.a].append((road.b, road.id))
            self.adjacency[road.b].append((road.a, road.id))
            self._road_index[(min(road.a, road.b), max(road.a, road.b))] = road.id
        # Deterministic neighbour order (by node id) — DFS/BFS behaviour depends on it.
        for lst in self.adjacency:
            lst.sort()

    # Queries ----------------------------------------------------------------------------
    def road_between(self, a: int, b: int) -> Road | None:
        rid = self._road_index.get((min(a, b), max(a, b)))
        return None if rid is None else self.roads[rid]

    def nodes_of_kind(self, kind: NodeKind) -> list[Node]:
        return [n for n in self.nodes if n.kind == kind]

    def node_by_name(self, name: str) -> Node | None:
        return next((n for n in self.nodes if n.name == name), None)

    def degree(self, node: int) -> int:
        return len(self.adjacency[node])

    def fingerprint(self) -> str:
        """Stable hash of the static graph — used to prove experiment runs are comparable."""
        h = hashlib.sha256()
        for n in self.nodes:
            h.update(f"{n.id}:{n.x:.2f}:{n.y:.2f}:{n.kind}|".encode())
        for r in self.roads:
            h.update(f"{r.id}:{r.a}:{r.b}:{r.road_class}:{r.traffic.value}|".encode())
        return h.hexdigest()[:16]

    # Ground-truth mutation (only the event processor should call these) ---------------
    def set_traffic(self, road_id: int, level: TrafficLevel) -> None:
        self.roads[road_id].traffic = level

    def set_blocked(self, road_id: int, blocked: bool) -> None:
        self.roads[road_id].blocked = blocked
        if blocked:
            self.blocked_ids.add(road_id)
        else:
            self.blocked_ids.discard(road_id)
