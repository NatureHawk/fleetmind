"""Environment events: types, scheduling and scenario incident generation.

Events come from three sources:

* ``SCENARIO`` — pre-generated from the seed when the run starts. Because the schedule
  depends only on the seed and scenario (never on what the agents do), every algorithm in
  an experiment faces exactly the same incidents at exactly the same times.
* ``OPERATOR`` — injected manually from the console.
* ``DEMO`` — issued by the guided demo director.

Closures from scenario incidents are *hidden*: they change the ground truth only, and the
fleet learns about them when a robot perceives the closed road. Operator closures are
announced to the fleet immediately.
"""

from __future__ import annotations

import heapq
import random
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import count
from typing import Any

from app.simulation.environment import Environment, RoadClass, TrafficLevel


class EventType(StrEnum):
    ROAD_BLOCKED = "ROAD_BLOCKED"
    ROAD_REOPENED = "ROAD_REOPENED"
    TRAFFIC_INCREASE = "TRAFFIC_INCREASE"
    TRAFFIC_CLEAR = "TRAFFIC_CLEAR"
    NEW_ORDER = "NEW_ORDER"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ROBOT_LOW_BATTERY = "ROBOT_LOW_BATTERY"
    ROBOT_FAILURE = "ROBOT_FAILURE"
    CHARGING_STATION_BUSY = "CHARGING_STATION_BUSY"


class EventSource(StrEnum):
    SCENARIO = "SCENARIO"
    OPERATOR = "OPERATOR"
    DEMO = "DEMO"
    SYSTEM = "SYSTEM"


EVENT_DESCRIPTIONS = {
    EventType.ROAD_BLOCKED: "Close a road. Robots whose route uses it must replan.",
    EventType.ROAD_REOPENED: "Reopen a closed road.",
    EventType.TRAFFIC_INCREASE: "Raise congestion on a road corridor; affected robots re-evaluate.",
    EventType.TRAFFIC_CLEAR: "Return a road corridor to free-flowing traffic.",
    EventType.NEW_ORDER: "Create a delivery request (optionally CRITICAL).",
    EventType.ORDER_CANCELLED: "Cancel an order that has not been picked up.",
    EventType.ROBOT_LOW_BATTERY: "Drop a robot's battery reading; it must decide whether to divert to a charger.",
    EventType.ROBOT_FAILURE: "Take a robot offline for a while; its unpicked orders return to the queue.",
    EventType.CHARGING_STATION_BUSY: "Make a charging station unavailable; robots heading there choose another.",
}


@dataclass(order=True, slots=True)
class ScheduledEvent:
    time: float
    seq: int
    type: EventType = field(compare=False)
    params: dict[str, Any] = field(compare=False, default_factory=dict)
    source: EventSource = field(compare=False, default=EventSource.SCENARIO)

    def as_dict(self) -> dict:
        return {"time": round(self.time, 1), "type": self.type.value, "params": self.params,
                "source": self.source.value}


class EventScheduler:
    def __init__(self) -> None:
        self._heap: list[ScheduledEvent] = []
        self._seq = count()
        self.history: deque[ScheduledEvent] = deque(maxlen=500)

    def schedule(self, time: float, type_: EventType, params: dict[str, Any] | None = None,
                 source: EventSource = EventSource.SCENARIO) -> ScheduledEvent:
        ev = ScheduledEvent(time, next(self._seq), type_, params or {}, source)
        heapq.heappush(self._heap, ev)
        return ev

    def due(self, now: float) -> list[ScheduledEvent]:
        out = []
        while self._heap and self._heap[0].time <= now:
            ev = heapq.heappop(self._heap)
            self.history.append(ev)
            out.append(ev)
        return out

    def upcoming(self, limit: int = 20) -> list[ScheduledEvent]:
        return sorted(self._heap)[:limit]

    def __len__(self) -> int:
        return len(self._heap)


# ---------------------------------------------------------------------------------------
# Incident generation


def is_bridge(env: Environment, road_id: int, extra_blocked: set[int]) -> bool:
    """Would closing ``road_id`` (plus ``extra_blocked``) disconnect its endpoints?"""
    road = env.roads[road_id]
    blocked = extra_blocked | {road_id}
    seen = {road.a}
    queue = deque([road.a])
    while queue:
        u = queue.popleft()
        for v, rid in env.adjacency[u]:
            if rid in blocked or v in seen:
                continue
            if v == road.b:
                return False
            seen.add(v)
            queue.append(v)
    return True


def busy_road_weights(env: Environment) -> list[float]:
    """Closures and congestion hit major roads more often than quiet side streets."""
    return [{RoadClass.ARTERIAL: 4.0, RoadClass.COLLECTOR: 2.5, RoadClass.LOCAL: 1.0}[r.road_class] for r in env.roads]


def corridor(env: Environment, start_road: int, length: int, rng: random.Random) -> list[int]:
    """A connected chain of roads of the same class starting at ``start_road``."""
    roads = [start_road]
    road = env.roads[start_road]
    tip = road.b
    while len(roads) < length:
        options = [rid for _, rid in env.adjacency[tip]
                   if rid not in roads and env.roads[rid].road_class == road.road_class]
        if not options:
            options = [rid for _, rid in env.adjacency[tip] if rid not in roads]
        if not options:
            break
        nxt = options[rng.randrange(len(options))] if len(options) > 1 else options[0]
        roads.append(nxt)
        tip = env.roads[nxt].other(tip)
    return roads


def initial_traffic(env: Environment, intensity: float, rng: random.Random) -> list[tuple[int, TrafficLevel]]:
    if intensity <= 0:
        return []
    weights = busy_road_weights(env)
    n = int(len(env.roads) * intensity)
    chosen: set[int] = set()
    ids = list(range(len(env.roads)))
    while len(chosen) < n:
        chosen.add(rng.choices(ids, weights=weights, k=1)[0])
    return [(rid, TrafficLevel.HIGH if rng.random() < 0.3 else TrafficLevel.MODERATE) for rid in sorted(chosen)]


def build_incidents(env: Environment, cfg: Any, rng: random.Random, robot_ids: list[str]) -> list[tuple[float, EventType, dict]]:
    """Pre-generate the scenario's incident timeline from the seed."""
    horizon = cfg.duration_s
    events: list[tuple[float, EventType, dict]] = []
    weights = busy_road_weights(env)
    ids = list(range(len(env.roads)))

    for _ in range(cfg.congestion_events):
        t = rng.uniform(90.0, horizon * 0.75)
        start = rng.choices(ids, weights=weights, k=1)[0]
        roads = corridor(env, start, rng.randint(3, 6), rng)
        level = TrafficLevel.JAMMED if rng.random() < 0.45 else TrafficLevel.HIGH
        duration = rng.uniform(300.0, 700.0)
        events.append((t, EventType.TRAFFIC_INCREASE, {"road_ids": roads, "level": level.name, "duration_s": duration}))

    closures = cfg.closure_events
    minutes = int(horizon // 60)
    extra = sum(1 for _ in range(minutes) if rng.random() < cfg.road_failure_probability)
    blocked: set[int] = set()
    for i in range(closures + extra):
        t = rng.uniform(120.0, horizon * 0.8)
        for _attempt in range(40):
            rid = rng.choices(ids, weights=weights, k=1)[0]
            if rid not in blocked and not is_bridge(env, rid, blocked):
                break
        else:
            continue
        blocked.add(rid)
        duration = rng.uniform(360.0, 900.0) if i < closures else rng.uniform(240.0, 480.0)
        events.append((t, EventType.ROAD_BLOCKED, {"road_id": rid, "duration_s": duration}))

    for _ in range(cfg.robot_failures):
        if not robot_ids:
            break
        t = rng.uniform(200.0, horizon * 0.8)
        events.append((t, EventType.ROBOT_FAILURE, {"robot_id": rng.choice(robot_ids),
                                                     "duration_s": rng.uniform(180.0, 320.0)}))
    events.sort(key=lambda e: e[0])
    return events
