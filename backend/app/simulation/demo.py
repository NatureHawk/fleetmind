"""Guided demo: a scripted, easy-to-follow story for presentations.

The director does not fake anything — it only injects real events (traffic, a hidden road
closure, a battery fault, a CRITICAL order) at chosen moments, targeting robots whose
current routes make the effect visible. Everything that follows (perception, fleet
broadcast, replanning, charger diversion, allocation and preemption) is the normal agent
behaviour.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.agents.battery import MIN_RESERVE_FRACTION, estimate_energy
from app.core.event_bus import Topics
from app.simulation.environment import NodeKind
from app.simulation.events import EventSource, EventType, ScheduledEvent, is_bridge
from app.simulation.orders import Priority
from app.simulation.timeline import Category, Severity

if TYPE_CHECKING:
    from app.simulation.engine import SimulationEngine


@dataclass
class Phase:
    key: str
    title: str
    description: str
    at: float | None  # None = triggered by an observed event
    started_at: float | None = None
    note: str = ""


class DemoDirector:
    def __init__(self, engine: SimulationEngine, rng: random.Random) -> None:
        self.e = engine
        self.rng = rng
        self.phases = [
            Phase("normal", "Normal delivery",
                  "Orders arrive, the allocator scores every robot and assigns the best one; each robot plans its "
                  "route with the active search algorithm.", 0.0),
            Phase("traffic", "Traffic increase",
                  "Congestion builds on a corridor an active robot is using. The traffic feed broadcasts it and "
                  "affected robots re-evaluate their routes.", 80.0),
            Phase("closure", "Road closure",
                  "An incident closes a road ahead of a robot. The fleet does not know yet — the robot has to "
                  "perceive it with its own sensors.", 170.0),
            Phase("replan", "Robot replanning",
                  "The robot detects the closure, reports it over the fleet channel, invalidates its route and "
                  "plans a new one.", None),
            Phase("battery", "Battery warning",
                  "A battery fault drops one robot's charge. It checks whether it can still finish safely and "
                  "diverts to the best charging station.", 300.0),
            Phase("priority", "High-priority order",
                  "A CRITICAL order arrives. The allocator scores the fleet — and may preempt a lower-priority "
                  "pickup to meet the deadline.", 400.0),
            Phase("metrics", "Final metrics",
                  "The scripted demo is complete. Review the metrics and decision timeline, or resume to keep "
                  "the fleet running.", 560.0),
        ]
        self.index = -1
        self.closure_road: int | None = None
        self.closure_robot: str | None = None
        self._closure_at: float | None = None
        engine.bus.subscribe(Topics.ROBOT_REPLANNED, self._on_replan)

    # ------------------------------------------------------------------------------------
    def tick(self) -> None:
        now = self.e.now
        nxt = self.index + 1
        if nxt >= len(self.phases):
            return
        phase = self.phases[nxt]
        if phase.at is not None and now >= phase.at:
            self._start(nxt)
        elif phase.key == "replan" and self._closure_at is not None and now - self._closure_at > 90.0:
            self._start(nxt, note="closure has not been reached yet; continuing")

    def _on_replan(self, payload: tuple[str, str]) -> None:
        robot_id, trigger = payload
        nxt = self.index + 1
        if (nxt < len(self.phases) and self.phases[nxt].key == "replan" and trigger == "ROAD_BLOCKED"
                and self._closure_at is not None):
            self._start(nxt, note=f"{robot_id} replanned around the closure")

    def _start(self, idx: int, note: str = "") -> None:
        phase = self.phases[idx]
        self.index = idx
        phase.started_at = self.e.now
        action = getattr(self, f"_do_{phase.key}", None)
        if action is not None:
            note = action() or note
        phase.note = note
        self.e.timeline.add(Category.DEMO, "DEMO_PHASE",
                            f"Phase {idx + 1} · {phase.title} — {phase.description}" + (f" ({note})" if note else ""),
                            severity=Severity.NOTICE, data={"phase": idx + 1, "key": phase.key})

    # Phase actions --------------------------------------------------------------------------
    def _driving(self, min_roads: int = 4):
        robots = [r for r in self.e.fleet.robots
                  if r.status.value == "EN_ROUTE" and len(r.remaining_roads()) >= min_roads]
        return sorted(robots, key=lambda r: (-len(r.remaining_roads()), r.id))

    def _apply(self, type_: EventType, params: dict, source: EventSource = EventSource.DEMO) -> None:
        ev = ScheduledEvent(self.e.now, -1, type_, params, source)
        self.e.scheduler.history.append(ev)
        self.e.processor.apply(ev)

    def _do_traffic(self) -> str:
        candidates = self._driving(5)
        if not candidates:
            return "no robot on a long route; skipped"
        robot = candidates[0]
        roads = robot.remaining_roads()[1:4]
        self._apply(EventType.TRAFFIC_INCREASE, {"road_ids": roads, "level": "JAMMED", "duration_s": 300.0})
        return f"corridor ahead of {robot.id}"

    def _do_closure(self) -> str:
        env = self.e.env
        for robot in self._driving(4):
            for rid in robot.remaining_roads()[2:5]:
                if not env.roads[rid].blocked and not is_bridge(env, rid, set(env.blocked_ids)):
                    self.closure_road, self.closure_robot = rid, robot.id
                    self._closure_at = self.e.now
                    # SCENARIO source = hidden incident: the robot must discover it itself.
                    self._apply(EventType.ROAD_BLOCKED, {"road_id": rid, "duration_s": 420.0}, EventSource.SCENARIO)
                    return f"{env.roads[rid].name} on {robot.id}'s route"
        self._closure_at = self.e.now
        return "no suitable route; skipped"

    def _do_battery(self) -> str:
        e = self.e
        robots = [r for r in e.fleet.robots
                  if r.status.value == "EN_ROUTE" and r.active_orders and not r.heading_to_charger()
                  and r.id != self.closure_robot and r.battery_fraction > 0.3 and len(r.remaining_roads()) >= 4]
        if not robots:
            return "no suitable robot; skipped"
        # Prefer a robot close to a charger so the story is "divert and recover", not "strand".
        robot = min(robots, key=lambda r: (e.charging.nearest_distance(r.anchor), r.id))
        to_charger = estimate_energy(e.charging.nearest_distance(robot.anchor), robot.energy_rate)
        route = e.world.roads_energy(robot.remaining_roads(), robot.energy_rate)
        reserve = e.charging.reserve_energy(robot.path[-1], robot.energy_rate)
        # Enough to reach a charger with margin, not enough to finish the leg plus reserve.
        level = (to_charger * 1.8 + robot.max_battery_wh * MIN_RESERVE_FRACTION) / robot.max_battery_wh
        level = min(level, (route + reserve) / robot.max_battery_wh * 0.9)
        level = max(0.08, min(0.22, level))
        self._apply(EventType.ROBOT_LOW_BATTERY, {"robot_id": robot.id, "level": round(level, 3)})
        return f"{robot.id} affected"

    def _do_priority(self) -> str:
        env = self.e.env
        warehouses = [n.id for n in env.nodes_of_kind(NodeKind.WAREHOUSE)]
        customers = [n.id for n in env.nodes_of_kind(NodeKind.CUSTOMER)]
        source = self.rng.choice(warehouses)
        destination = max(customers, key=lambda c: (self.e.world.straight_line(source, c) * self.rng.uniform(0.6, 1.0), c))
        order = self.e.create_order(source, destination, Priority.CRITICAL, origin="demo")
        return order.id

    def _do_metrics(self) -> str:
        self.e.pause_requested = True
        return "simulation paused for review"

    # ------------------------------------------------------------------------------------
    def state(self) -> dict:
        now = self.e.now
        phases = []
        for i, p in enumerate(self.phases):
            status = "done" if i < self.index else "active" if i == self.index else "pending"
            phases.append({"key": p.key, "title": p.title, "description": p.description, "status": status,
                           "at": p.at, "started_at": p.started_at, "note": p.note})
        upcoming = next((p for p in self.phases[self.index + 1:] if p.at is not None), None)
        return {
            "index": self.index,
            "phases": phases,
            "next_at": upcoming.at if upcoming else None,
            "next_in": None if upcoming is None else max(0.0, upcoming.at - now),
            "complete": self.index == len(self.phases) - 1,
        }
