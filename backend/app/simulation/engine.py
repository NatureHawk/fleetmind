"""The deterministic simulation engine.

One call to :meth:`SimulationEngine.step` advances the world by exactly one fixed tick:

    1. apply due events (scenario incidents, operator commands, demo script)
    2. release newly arrived delivery requests
    3. run the task allocator (every ``ALLOCATION_INTERVAL_S``)
    4. tick every agent: PERCEIVE → DECIDE → ACT
    5. expire stale orders, sample metrics

The engine never reads the wall clock and every random draw comes from a seeded stream, so
the same scenario + seed + algorithm always produces the same run — the basis for fair
experiments. The live server and the experiment runner drive the very same class.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.agents.agent_manager import AgentManager
from app.agents.charging import ChargingNetwork
from app.agents.communication import FleetChannel
from app.agents.context import AgentContext
from app.agents.fleet_factory import create_fleet
from app.allocation.task_allocator import TaskAllocator
from app.core.event_bus import EventBus, Topics
from app.core.rng import SeedStreams
from app.core.simulation_clock import SimulationClock
from app.metrics.collector import MetricsCollector
from app.planning.registry import ALGORITHM_CATALOG
from app.planning.route_service import RouteService
from app.simulation.environment import NodeKind, TrafficLevel
from app.simulation.event_processor import EventProcessor
from app.simulation.events import (
    EventScheduler,
    EventSource,
    EventType,
    ScheduledEvent,
    build_incidents,
    corridor,
    initial_traffic,
)
from app.simulation.generator import generate_city
from app.simulation.orders import UNASSIGNED_EXPIRY_GRACE, Order, OrderBook, OrderStatus, OrderStream, Priority
from app.simulation.scenarios import ScenarioConfig
from app.simulation.timeline import Category, Severity, Timeline
from app.simulation.world_model import WorldModel

DEFAULT_TICK_S = 0.5
ALLOCATION_INTERVAL_S = 2.0
EXPIRY_INTERVAL_S = 10.0


class SimulationEngine:
    def __init__(self, config: ScenarioConfig, *, tick_seconds: float = DEFAULT_TICK_S,
                 metrics_interval: float = 15.0) -> None:
        self.config = config
        self.seed = config.seed
        self.streams = SeedStreams(config.seed)
        self.clock = SimulationClock(dt=tick_seconds)
        self.bus = EventBus()
        self.timeline = Timeline(self.bus)

        self.env = generate_city(config.seed)
        for rid, level in initial_traffic(self.env, config.traffic_intensity, self.streams.stream("traffic")):
            self.env.set_traffic(rid, level)
        self.world = WorldModel(self.env)

        self.routes = RouteService(self.world, self.bus, config.algorithm, config.heuristic)
        self.orders = OrderBook()
        self.charging = ChargingNetwork(self.env)
        self.channel = FleetChannel(self.world, self.bus)
        self.ctx = AgentContext(self.env, self.world, self.routes, self.charging, self.channel, self.orders,
                                self.timeline, self.bus, dt=tick_seconds)
        robots = create_fleet(self.env, self.streams.stream("fleet"), config.robots,
                              (config.battery_min, config.battery_max), config.low_battery_robots)
        self.fleet = AgentManager(robots, self.ctx)
        self.allocator = TaskAllocator(preemption=config.preemption)
        self.metrics = MetricsCollector(self.bus, sample_interval=metrics_interval)

        weights = {Priority[k]: w for k, w in config.priority_weights.items()}
        orders_rng = self.streams.stream("orders")
        self._orders_state_hash = hashlib.sha256(repr(orders_rng.getstate()).encode()).hexdigest()[:16]
        self.order_stream = OrderStream(self.env, orders_rng, initial=config.initial_orders,
                                        rate_per_min=config.order_rate_per_min, max_orders=config.max_orders,
                                        priority_weights=weights)
        self.scheduler = EventScheduler()
        incidents = build_incidents(self.env, config, self.streams.stream("incidents"), [r.id for r in robots])
        for t, type_, params in incidents:
            self.scheduler.schedule(t, type_, params, EventSource.SCENARIO)
        self.processor = EventProcessor(self)
        self.operator_rng = self.streams.stream("operator")

        self.pause_requested = False
        self.demo = None
        if config.demo:
            from app.simulation.demo import DemoDirector
            self.demo = DemoDirector(self, self.streams.stream("demo"))

        self.fingerprints = self._fingerprints(incidents)
        self._alloc_every = max(1, round(ALLOCATION_INTERVAL_S / tick_seconds))
        self._expire_every = max(1, round(EXPIRY_INTERVAL_S / tick_seconds))
        self._sync_now()
        alg = ALGORITHM_CATALOG[config.algorithm]["short"]
        self.timeline.add(Category.SYSTEM, "SIMULATION_READY",
                          f"Scenario '{config.name}' · seed {config.seed} · {len(robots)} robots · "
                          f"{len(self.env.nodes)} nodes / {len(self.env.roads)} roads · planner {alg}",
                          data={"fingerprints": self.fingerprints})

    # ------------------------------------------------------------------------------------
    @property
    def now(self) -> float:
        return self.clock.time

    def _sync_now(self) -> None:
        t = self.clock.time
        self.ctx.now = t
        self.timeline.now = t
        self.channel.now = t
        self.routes.now = t

    def step(self) -> None:
        self._sync_now()
        t = self.now
        for ev in self.scheduler.due(t):
            self.processor.apply(ev)
        for source, destination, priority in self.order_stream.due(t):
            self.create_order(source, destination, priority, origin="stream")
        if self.demo is not None:
            self.demo.tick()
        if self.clock.tick % self._alloc_every == 0:
            self.allocator.allocate(self.ctx, self.fleet.robots, t)
        self.fleet.tick()
        if self.clock.tick % self._expire_every == 0:
            self._expire_orders(t)
        self.metrics.maybe_sample(self)
        self.clock.advance()

    def run_until(self, t_end: float) -> None:
        while self.now < t_end:
            self.step()

    # ------------------------------------------------------------------------------------
    def create_order(self, source: int, destination: int, priority: Priority, *, origin: str = "stream") -> Order:
        order = self.orders.create(self.env, source, destination, priority, self.now)
        env = self.env
        tag = "" if origin == "stream" else f" [{origin}]"
        self.timeline.add(Category.ORDER, "NEW_ORDER",
                          f"New {priority.label} order {order.id}: {env.nodes[source].name} → "
                          f"{env.nodes[destination].name}, deadline T+{order.deadline / 60:.1f} min{tag}",
                          severity=Severity.NOTICE if priority >= Priority.HIGH else Severity.INFO,
                          order_id=order.id, node_id=destination,
                          data={"priority": priority.label, "deadline": round(order.deadline, 1), "origin": origin})
        self.bus.publish(Topics.ORDER_CREATED, order)
        return order

    def _expire_orders(self, now: float) -> None:
        for order in self.orders.pending():
            if now > order.deadline + UNASSIGNED_EXPIRY_GRACE:
                order.status = OrderStatus.FAILED
                order.failure_reason = "expired before a robot could be assigned"
                order.log(now, order.failure_reason)
                self.timeline.add(Category.ORDER, "ORDER_EXPIRED", f"{order.id} expired — never assigned",
                                  severity=Severity.WARNING, order_id=order.id)
                self.bus.publish(Topics.ORDER_FAILED, order)

    def set_algorithm(self, key: str, heuristic: str | None = None) -> None:
        self.routes.set_algorithm(key, heuristic)
        self.config = self.config.model_copy(update={"algorithm": key, "heuristic": self.routes.heuristic})
        self.timeline.add(Category.SYSTEM, "PLANNER_CHANGED",
                          f"Planner switched to {ALGORITHM_CATALOG[key]['short']} "
                          f"(heuristic: {self.routes.heuristic}) — applies to every new plan")

    # Operator events ------------------------------------------------------------------------
    def inject_event(self, type_: EventType, params: dict[str, Any]) -> ScheduledEvent:
        """Validate an operator command and apply it immediately."""
        params = {k: v for k, v in params.items() if v is not None}
        env = self.env
        if type_ in (EventType.ROAD_BLOCKED, EventType.TRAFFIC_INCREASE):
            if "road_id" not in params and "road_ids" not in params:
                target = self.suggest_road_target()
                if target is None:
                    raise ValueError("no robot is currently driving; pick a road explicitly")
                params["road_id"] = target
            self._check_road(params.get("road_id"))
            if type_ == EventType.TRAFFIC_INCREASE and "road_ids" not in params:
                params["road_ids"] = corridor(env, int(params["road_id"]), 3, self.operator_rng)
                params.setdefault("level", "JAMMED")
            if type_ == EventType.TRAFFIC_INCREASE:
                level = str(params.get("level", "JAMMED")).upper()
                if level not in TrafficLevel.__members__:
                    raise ValueError(f"level must be one of {list(TrafficLevel.__members__)}")
                params["level"] = level
        elif type_ in (EventType.ROAD_REOPENED, EventType.TRAFFIC_CLEAR):
            if "road_id" not in params and "road_ids" not in params:
                pool = sorted(env.blocked_ids) if type_ == EventType.ROAD_REOPENED else \
                    [r.id for r in env.roads if r.traffic != TrafficLevel.LOW]
                if not pool:
                    raise ValueError("nothing to clear")
                params["road_ids" if type_ == EventType.TRAFFIC_CLEAR else "road_id"] = \
                    pool if type_ == EventType.TRAFFIC_CLEAR else pool[0]
            if "road_id" in params:
                self._check_road(params["road_id"])
        elif type_ in (EventType.ROBOT_LOW_BATTERY, EventType.ROBOT_FAILURE):
            if "robot_id" not in params:
                busy = [r for r in self.fleet.robots if r.active_orders and r.status.value != "OFFLINE"]
                if not busy:
                    raise ValueError("no busy robot to target; pick a robot explicitly")
                params["robot_id"] = max(busy, key=lambda r: (r.battery_pct, r.id)).id
            if self.fleet.get(params["robot_id"]) is None:
                raise LookupError(f"robot {params['robot_id']} not found")
            if "level" in params and not 0.0 <= float(params["level"]) <= 1.0:
                raise ValueError("level must be a fraction between 0 and 1")
        elif type_ == EventType.CHARGING_STATION_BUSY:
            if "node_id" not in params:
                params["node_id"] = max(self.charging.stations.values(), key=lambda s: (s.load, -s.node)).node
            if int(params["node_id"]) not in self.charging.stations:
                raise ValueError("node_id must be a charging station")
        elif type_ == EventType.NEW_ORDER:
            if "source" in params and env.nodes[int(params["source"])].kind != NodeKind.WAREHOUSE:
                raise ValueError("source must be a warehouse")
            if "destination" in params and env.nodes[int(params["destination"])].kind != NodeKind.CUSTOMER:
                raise ValueError("destination must be a customer")
            if str(params.get("priority", "NORMAL")).upper() not in Priority.__members__:
                raise ValueError(f"priority must be one of {list(Priority.__members__)}")
        elif type_ == EventType.ORDER_CANCELLED:
            if "order_id" in params and self.orders.get(params["order_id"]) is None:
                raise LookupError(f"order {params['order_id']} not found")

        self._sync_now()
        ev = ScheduledEvent(self.now, -1, type_, params, EventSource.OPERATOR)
        self.scheduler.history.append(ev)
        self.processor.apply(ev)
        return ev

    def _check_road(self, road_id: Any) -> None:
        if road_id is None:
            return
        rid = int(road_id)
        if not 0 <= rid < len(self.env.roads):
            raise LookupError(f"road {road_id} not found")

    def suggest_road_target(self, ahead: int = 2) -> int | None:
        """A road a few segments ahead on the longest active route — the most instructive closure."""
        driving = [r for r in self.fleet.robots if r.status.value == "EN_ROUTE" and len(r.remaining_roads()) > 1]
        if not driving:
            return None
        robot = max(driving, key=lambda r: (len(r.remaining_roads()), r.id))
        roads = robot.remaining_roads()
        return roads[min(ahead, len(roads) - 1)]

    # ------------------------------------------------------------------------------------
    def _fingerprints(self, incidents: list) -> dict[str, str]:
        fleet = hashlib.sha256(json.dumps([
            [r.id, r.model.key, r.node, round(r.battery_wh, 2), round(r.speed_mps, 4), r.capacity]
            for r in self.fleet.robots]).encode()).hexdigest()[:16]
        events = hashlib.sha256(json.dumps([[round(t, 3), ty.value, p] for t, ty, p in incidents],
                                           sort_keys=True, default=str).encode()).hexdigest()[:16]
        return {"graph": self.env.fingerprint(), "fleet": fleet, "orders": self._orders_state_hash,
                "events": events}
