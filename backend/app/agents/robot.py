"""Autonomous delivery robot agent.

Each tick a robot runs one cycle of its control loop:

    PERCEIVE  sense nearby roads; report closures the fleet does not know about yet
    DECIDE    react to notifications (closures, congestion, low battery, new tasks),
              choose the next stop, plan or re-plan a route with the active search algorithm
    ACT       drive along the route (draining the battery), load, deliver or charge

Replanning is triggered by:
* a road on the remaining route becoming known as blocked (own perception or a fleet report)
* congestion on the route (re-evaluate; switch only if the alternative is clearly faster)
* insufficient battery for the remaining route plus a safe reserve (divert to a charger)
* the task allocator inserting a CRITICAL order or reassigning an order

Robots hold an ordered list of *stops* (pickup, drop-off, charge). Only the leg to the next
stop is planned at any time — later legs are planned when they become current, on the most
up-to-date world knowledge.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from app.agents.battery import (
    CHARGE_POWER_WH_PER_S,
    CHARGE_RESUME_FRACTION,
    CHARGE_TARGET_FRACTION,
    FIELD_SERVICE_CHARGE,
    FIELD_SERVICE_DELAY_S,
    IDLE_CHARGE_FRACTION,
    LOW_BATTERY_FRACTION,
    MIN_RESERVE_FRACTION,
    estimate_energy,
    pct,
)
from app.agents.context import AgentContext
from app.core.event_bus import Topics
from app.core.formatting import fmt_duration
from app.planning.planner_interface import SearchResult
from app.planning.registry import ALGORITHM_CATALOG
from app.simulation.environment import (
    REFERENCE_SPEED_MPS,
    ROAD_SPEED_FACTOR,
    TRAFFIC_ENERGY_FACTOR,
    TRAFFIC_TIME_FACTOR,
    Environment,
)
from app.simulation.orders import CLOSED_STATUSES, OrderStatus
from app.simulation.timeline import Category, Severity


class RobotStatus(StrEnum):
    IDLE = "IDLE"
    ASSIGNED = "ASSIGNED"
    PLANNING = "PLANNING"
    EN_ROUTE = "EN_ROUTE"
    WAITING = "WAITING"
    LOADING = "LOADING"
    DELIVERING = "DELIVERING"
    CHARGING = "CHARGING"
    REPLANNING = "REPLANNING"
    OFFLINE = "OFFLINE"


class StopKind(StrEnum):
    PICKUP = "PICKUP"
    DROPOFF = "DROPOFF"
    CHARGE = "CHARGE"


@dataclass(slots=True)
class Stop:
    kind: StopKind
    node: int
    order_id: str | None = None


@dataclass(frozen=True, slots=True)
class RobotModel:
    key: str
    name: str
    speed_factor: float
    capacity: int
    battery_wh: float
    energy_rate: float  # Wh per metre


@dataclass(slots=True)
class PlanInfo:
    algorithm: str
    purpose: str
    trigger: str
    goal: int
    cost: float
    hops: int
    nodes_explored: int
    nodes_generated: int
    elapsed_ms: float
    energy_wh: float
    planned_at: float
    cached: bool

    def as_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "purpose": self.purpose,
            "trigger": self.trigger,
            "goal": self.goal,
            "cost": round(self.cost, 1),
            "hops": self.hops,
            "nodes_explored": self.nodes_explored,
            "nodes_generated": self.nodes_generated,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "energy_wh": round(self.energy_wh, 1),
            "planned_at": round(self.planned_at, 1),
            "cached": self.cached,
        }


PICKUP_DWELL_S = 10.0
DROPOFF_DWELL_S = 12.0
ASSIGN_DELAY_S = 0.5
PLAN_DELAY_S = 1.0
REPLAN_DELAY_S = 2.0
SENSOR_RANGE_M = 90.0
NO_ROUTE_RETRY_S = 20.0
REROUTE_MIN_GAIN = 0.08
INVALIDATED_ROUTE_TTL_S = 45.0
IDLE_CHARGE_COOLDOWN_S = 60.0

WORKING_STATUSES = {RobotStatus.LOADING, RobotStatus.DELIVERING}


class RobotAgent:
    def __init__(self, robot_id: str, model: RobotModel, node: int, env: Environment, *, speed_mps: float,
                 energy_rate: float, max_battery_wh: float, battery_wh: float, capacity: int) -> None:
        self.id = robot_id
        self.model = model
        self.speed_mps = speed_mps
        self.energy_rate = energy_rate
        self.max_battery_wh = max_battery_wh
        self.battery_wh = battery_wh
        self.capacity = capacity

        self.status = RobotStatus.IDLE
        self.status_since = 0.0
        self.node: int | None = node
        self.x, self.y = env.nodes[node].x, env.nodes[node].y
        self.heading = 0.0
        self.home_node = node

        # Active plan: robot is on road path_roads[path_index-1] from path[path_index-1] to path[path_index]
        self.path: list[int] = []
        self.path_roads: list[int] = []
        self.path_index = 0
        self.edge_progress = 0.0
        self.plan: PlanInfo | None = None

        self.stops: list[Stop] = []
        self.active_stop: Stop | None = None
        self.active_orders: list[str] = []
        self.carrying: list[str] = []

        self.timer = 0.0
        self.pending_replan: tuple[str, str] | None = None
        self.pending_reevaluate: str | None = None
        self.needs_charge: str | None = None
        self.replan_trigger: str | None = None
        self.low_battery_mode = False
        self.battery_warned = False
        self.wait_reason: str | None = None
        self.offline_until: float | None = None
        self.offline_reason: str | None = None
        self.recover_battery: float | None = None
        self.idle_charge_cooldown = 0.0
        self.invalidated_path: list[int] | None = None
        self.invalidated_at = -1e9
        self.charge_started_at = 0.0
        self.charge_start_wh = 0.0

        # Statistics
        self.total_distance = 0.0
        self.energy_consumed = 0.0
        self.energy_charged = 0.0
        self.orders_completed = 0
        self.replans = 0
        self.plans = 0
        self.charge_sessions = 0
        self.depletions = 0
        self.idle_time = 0.0
        self.busy_time = 0.0
        self.charging_time = 0.0
        self.offline_time = 0.0

        # Explainability
        self.decisions: deque[tuple[float, str, str]] = deque(maxlen=60)
        self.perception: tuple[int, int] = (0, 0)
        self.last_decision = "Awaiting tasks"
        self.last_decision_t = 0.0
        self.now = 0.0

    # ------------------------------------------------------------------ derived state
    @property
    def battery_fraction(self) -> float:
        return self.battery_wh / self.max_battery_wh

    @property
    def battery_pct(self) -> float:
        return pct(self.battery_wh, self.max_battery_wh)

    @property
    def speed_ratio(self) -> float:
        return self.speed_mps / REFERENCE_SPEED_MPS

    @property
    def on_edge(self) -> bool:
        return self.node is None and bool(self.path)

    @property
    def current_road(self) -> int | None:
        return self.path_roads[self.path_index - 1] if self.on_edge else None

    @property
    def anchor(self) -> int:
        """The node from which the next plan starts (current node, or end of current road)."""
        if self.node is not None:
            return self.node
        return self.path[self.path_index]

    def remaining_roads(self) -> list[int]:
        if not self.path:
            return []
        start = self.path_index - 1 if self.node is None else self.path_index
        return self.path_roads[start:]

    def route_uses(self, road_ids: set[int]) -> bool:
        return any(r in road_ids for r in self.remaining_roads())

    def display_route(self) -> list[int]:
        return self.path[self.path_index:] if self.path else []

    @property
    def current_stop(self) -> Stop | None:
        return self.stops[0] if self.stops else None

    @property
    def current_order_id(self) -> str | None:
        for s in self.stops:
            if s.order_id:
                return s.order_id
        return None

    def heading_to_charger(self) -> bool:
        return bool(self.stops) and self.stops[0].kind == StopKind.CHARGE

    @property
    def available_for_work(self) -> bool:
        return self.status != RobotStatus.OFFLINE and len(self.active_orders) < self.capacity

    # ------------------------------------------------------------------ commands
    def assign(self, order, ctx: AgentContext, *, front: bool = False) -> None:
        pickup = Stop(StopKind.PICKUP, order.source, order.id)
        drop = Stop(StopKind.DROPOFF, order.destination, order.id)
        if front and self.stops:
            in_progress = self.stops[0].kind == StopKind.CHARGE or self.status in WORKING_STATUSES
            idx = 1 if in_progress else 0
            self.stops[idx:idx] = [pickup, drop]
            if idx == 0 and self.status in (RobotStatus.EN_ROUTE, RobotStatus.REPLANNING, RobotStatus.WAITING):
                self.request_replan("PRIORITY", f"{order.id} ({order.priority.label}) inserted ahead of current task")
        else:
            self.stops += [pickup, drop]
        self.active_orders.append(order.id)
        env = ctx.env
        self._log("DECIDE", f"Accepted {order.id}: {env.nodes[order.source].name} → {env.nodes[order.destination].name}")
        if self.status == RobotStatus.IDLE:
            self._set_status(RobotStatus.ASSIGNED)
            self.timer = ASSIGN_DELAY_S

    def release(self, order_id: str, ctx: AgentContext, reason: str) -> None:
        was_current = bool(self.stops) and self.stops[0].order_id == order_id
        self.stops = [s for s in self.stops if s.order_id != order_id]
        if order_id in self.active_orders:
            self.active_orders.remove(order_id)
        if order_id in self.carrying:
            self.carrying.remove(order_id)
        self._log("DECIDE", f"Released {order_id}: {reason}")
        if not was_current:
            return
        if self.status in WORKING_STATUSES:
            self.active_stop = None
            self._next_leg(ctx)
        elif self.status in (RobotStatus.EN_ROUTE, RobotStatus.REPLANNING, RobotStatus.PLANNING,
                             RobotStatus.ASSIGNED, RobotStatus.WAITING):
            self.request_replan("REASSIGNED", reason)

    def request_replan(self, trigger: str, reason: str) -> None:
        if self.status == RobotStatus.OFFLINE:
            return
        if self.pending_replan is None:
            self.pending_replan = (trigger, reason)

    def request_reevaluate(self, reason: str) -> None:
        if self.status == RobotStatus.EN_ROUTE and self.pending_reevaluate is None:
            self.pending_reevaluate = reason

    def request_charge(self, reason: str) -> None:
        if self.needs_charge is None and not self.heading_to_charger():
            self.needs_charge = reason
            self.request_replan("LOW_BATTERY", reason)

    def set_battery_fraction(self, fraction: float) -> None:
        self.battery_wh = max(0.0, min(1.0, fraction)) * self.max_battery_wh
        self.battery_warned = False

    def fail(self, ctx: AgentContext, reason: str, duration: float | None, recover_battery: float | None = None) -> None:
        for oid in list(self.active_orders):
            order = ctx.orders.get(oid)
            if order is None or order.status in CLOSED_STATUSES:
                continue
            if oid in self.carrying:
                order.status = OrderStatus.FAILED
                order.failure_reason = f"{self.id} {reason} with parcel on board"
                order.log(ctx.now, order.failure_reason)
                ctx.timeline.add(Category.ORDER, "ORDER_FAILED", f"{oid} failed — {order.failure_reason}",
                                 severity=Severity.CRITICAL, robot_id=self.id, order_id=oid)
                ctx.bus.publish(Topics.ORDER_FAILED, order)
            else:
                order.status = OrderStatus.PENDING
                order.assigned_robot = None
                order.log(ctx.now, f"returned to queue ({self.id} {reason})")
        self.stops.clear()
        self.active_orders.clear()
        self.carrying.clear()
        self.active_stop = None
        ctx.charging.cancel(self.id)
        ctx.charging.finish(self.id)
        if self.on_edge:
            self._truncate_to_current_edge()
        else:
            self._clear_path()
        self.pending_replan = self.pending_reevaluate = self.needs_charge = None
        self.low_battery_mode = False
        self.offline_until = None if duration is None else ctx.now + duration
        self.offline_reason = reason
        self.recover_battery = recover_battery
        self._set_status(RobotStatus.OFFLINE)
        eta = "" if duration is None else f"; back in service in ≈{fmt_duration(duration)}"
        self._log("ACT", f"OFFLINE — {reason}")
        ctx.timeline.add(Category.AGENT, "ROBOT_OFFLINE", f"{self.id} offline — {reason}{eta}",
                         severity=Severity.CRITICAL, robot_id=self.id)

    # ------------------------------------------------------------------ control loop
    def tick(self, ctx: AgentContext) -> None:
        self.now = ctx.now
        if self.status == RobotStatus.OFFLINE:
            self._tick_offline(ctx)
        else:
            self._perceive(ctx)
            self._decide(ctx)
            self._act(ctx)
        self._account(ctx.dt)

    # PERCEIVE ---------------------------------------------------------------------------
    def _perceive(self, ctx: AgentContext) -> None:
        env = ctx.env
        if not ctx.world.has_hidden_closures():
            sensed = len(env.adjacency[self.anchor]) if (self.node is not None or self.path) else 0
            self.perception = (sensed, 0)
            return
        roads = self._sensed_roads(env)
        anomalies = 0
        for rid in roads:
            if env.roads[rid].blocked and not ctx.world.is_blocked(rid):
                anomalies += 1
                self._report_closure(ctx, rid)
        self.perception = (len(roads), anomalies)

    def _sensed_roads(self, env: Environment) -> list[int]:
        if self.node is not None:
            return [rid for _, rid in env.adjacency[self.node]]
        if not self.path:
            return []
        road_id = self.path_roads[self.path_index - 1]
        roads = [road_id]
        if env.roads[road_id].length - self.edge_progress <= SENSOR_RANGE_M:
            roads += [rid for _, rid in env.adjacency[self.path[self.path_index]] if rid != road_id]
        return roads

    def _report_closure(self, ctx: AgentContext, road_id: int) -> None:
        if ctx.world.is_blocked(road_id):
            return
        name = ctx.env.roads[road_id].name
        self._log("PERCEIVE", f"Detected closure on {name}")
        ctx.timeline.add(Category.ENVIRONMENT, "CLOSURE_DETECTED", f"{self.id} detected closure on {name}",
                         severity=Severity.WARNING, robot_id=self.id, road_id=road_id)
        ctx.channel.report_road_blocked(self.id, road_id)

    # DECIDE ----------------------------------------------------------------------------
    def _decide(self, ctx: AgentContext) -> None:
        s = self.status
        dt = ctx.dt
        if s in WORKING_STATUSES:
            self.timer -= dt
            if self.timer <= 0:
                self._complete_stop(ctx)
            return
        if s == RobotStatus.CHARGING:
            has_work = any(st.kind != StopKind.CHARGE for st in self.stops)
            if (self.battery_fraction >= CHARGE_TARGET_FRACTION
                    or (has_work and self.battery_fraction >= CHARGE_RESUME_FRACTION)):
                self._finish_charging(ctx, interrupted=self.battery_fraction < CHARGE_TARGET_FRACTION)
            return
        if s == RobotStatus.WAITING and self.wait_reason == "charger_queue" and self.pending_replan is None:
            if ctx.charging.is_charging(self.id):
                self._start_charging(ctx)
            return
        if self.pending_replan is not None:
            self._begin_replan(ctx)
            return
        if self.pending_reevaluate is not None:
            self._reevaluate(ctx)
        if s == RobotStatus.WAITING and self.wait_reason == "no_route":
            self.timer -= dt
            if self.timer <= 0:
                self._plan_leg(ctx)
        elif s == RobotStatus.ASSIGNED:
            self.timer -= dt
            if self.timer <= 0:
                self._set_status(RobotStatus.PLANNING)
                self.timer = PLAN_DELAY_S
        elif s in (RobotStatus.PLANNING, RobotStatus.REPLANNING):
            self.timer -= dt
            if self.timer <= 0:
                self._plan_leg(ctx)
        elif s == RobotStatus.IDLE:
            if self.stops:
                self._set_status(RobotStatus.ASSIGNED)
                self.timer = ASSIGN_DELAY_S
            elif self.battery_fraction < IDLE_CHARGE_FRACTION:
                self.idle_charge_cooldown -= dt
                if self.idle_charge_cooldown <= 0:
                    self.idle_charge_cooldown = IDLE_CHARGE_COOLDOWN_S
                    if self._insert_charge_stop(ctx, f"idle with battery at {self.battery_pct:.0f}%"):
                        self._set_status(RobotStatus.PLANNING)
                        self.timer = PLAN_DELAY_S

    def _begin_replan(self, ctx: AgentContext) -> None:
        trigger, reason = self.pending_replan or ("REPLAN", "")
        self.pending_replan = None
        if self.needs_charge is not None:
            if not self.heading_to_charger():
                self._insert_charge_stop(ctx, self.needs_charge)
            self.needs_charge = None

        if not self.stops:
            # Nothing left to do: finish the current road segment (turning back if it is closed), then idle.
            if self.on_edge:
                if ctx.world.is_blocked(self.current_road):
                    self._u_turn(ctx.env)
                self._truncate_to_current_edge()
                self._set_status(RobotStatus.EN_ROUTE)
            else:
                self._clear_path()
                self._set_status(RobotStatus.IDLE)
            return

        if self.on_edge and ctx.world.is_blocked(self.current_road):
            self._u_turn(ctx.env)
            self._log("ACT", f"U-turn on {ctx.env.roads[self.current_road].name}")
        if self.path:
            self.invalidated_path = self.path[max(0, self.path_index - 1):]
            self.invalidated_at = ctx.now
        self.replans += 1
        self.replan_trigger = trigger
        self.wait_reason = None
        self._set_status(RobotStatus.REPLANNING)
        self.timer = REPLAN_DELAY_S
        self._log("REPLAN", f"Route invalidated — {reason}")
        ctx.timeline.add(Category.REPLANNING, "REPLAN_TRIGGERED", f"{self.id} replanning — {reason}",
                         severity=Severity.NOTICE, robot_id=self.id, order_id=self.current_order_id,
                         data={"trigger": trigger, "invalidated_route": self.invalidated_path})
        ctx.bus.publish(Topics.ROBOT_REPLANNED, (self.id, trigger))

    def _plan_leg(self, ctx: AgentContext, *, allow_charge_insert: bool = True) -> None:
        if not self.stops:
            self._clear_path()
            self._set_status(RobotStatus.IDLE)
            return
        stop = self.stops[0]
        if stop.kind == StopKind.CHARGE and not ctx.charging.stations[stop.node].is_available(ctx.now):
            self._reselect_charger(ctx)
            stop = self.stops[0]

        world, env = ctx.world, ctx.env
        anchor = self.anchor
        trigger = self.replan_trigger or "PLAN"
        purpose = stop.kind.value.lower() if trigger == "PLAN" else "replan"
        result = ctx.routes.plan(anchor, stop.node, robot_id=self.id, purpose=purpose)
        self.plans += 1
        if not result.success:
            self._set_status(RobotStatus.WAITING)
            self.wait_reason = "no_route"
            self.timer = NO_ROUTE_RETRY_S
            msg = (f"{ALGORITHM_CATALOG[result.algorithm]['short']} found no route {env.nodes[anchor].name} → "
                   f"{env.nodes[stop.node].name} with current knowledge ({result.nodes_explored} nodes explored); "
                   f"retrying in {NO_ROUTE_RETRY_S:.0f}s")
            self._log("DECIDE", msg)
            ctx.timeline.add(Category.PLANNING, "NO_ROUTE", f"{self.id}: {msg}", severity=Severity.WARNING,
                             robot_id=self.id, order_id=stop.order_id, data=result.as_dict(include_path=False))
            return

        on_edge = self.on_edge
        new_path, new_roads, energy = self._compose(ctx, result)

        if stop.kind == StopKind.CHARGE and energy > self.battery_wh:
            # The straight-line estimate picked this charger, but the actual route is too long.
            switched = self._switch_to_reachable_charger(ctx, stop, energy)
            if switched is not None:
                result, stop = switched
                new_path, new_roads, energy = self._compose(ctx, result)

        if stop.kind != StopKind.CHARGE and allow_charge_insert:
            reserve = ctx.charging.reserve_energy(stop.node, self.energy_rate)
            floor = self.max_battery_wh * MIN_RESERVE_FRACTION
            if self.battery_wh - energy - reserve < floor:
                need = pct(energy + reserve + floor, self.max_battery_wh)
                reason = (f"leg to {env.nodes[stop.node].name} needs ≈{need:.0f}% incl. reserve, "
                          f"battery at {self.battery_pct:.0f}%")
                if self._insert_charge_stop(ctx, reason):
                    self._plan_leg(ctx, allow_charge_insert=False)
                    return

        self.replan_trigger = None
        self.wait_reason = None
        if not on_edge and len(new_path) == 1:
            self._clear_path()
            self._arrive(ctx)
            return

        self.path, self.path_roads, self.path_index = new_path, new_roads, 1
        if not on_edge:
            self.node = None
            self.edge_progress = 0.0
        self._set_status(RobotStatus.EN_ROUTE)
        self._record_plan(ctx, result, purpose, trigger, energy, stop)

    def _compose(self, ctx: AgentContext, result: SearchResult) -> tuple[list[int], list[int], float]:
        """Turn a search result from the anchor into this robot's full path, roads and energy need."""
        world, env = ctx.world, ctx.env
        if self.on_edge:
            new_path = [self.path[self.path_index - 1]] + result.path
            new_roads = [self.current_road] + world.path_roads(result.path)
            road = env.roads[self.current_road]
            partial = ((road.length - self.edge_progress) * self.energy_rate
                       * TRAFFIC_ENERGY_FACTOR[world.known_traffic[road.id]])
            return new_path, new_roads, partial + world.roads_energy(new_roads[1:], self.energy_rate)
        new_roads = world.path_roads(result.path)
        return list(result.path), new_roads, world.roads_energy(new_roads, self.energy_rate)

    def _switch_to_reachable_charger(self, ctx: AgentContext, stop: Stop,
                                     needed: float) -> tuple[SearchResult, Stop] | None:
        """Plan to every other available charger and take the cheapest one the battery can reach."""
        env = ctx.env
        best: tuple[float, SearchResult, int] | None = None
        for st in ctx.charging.stations.values():
            if st.node == stop.node or not st.is_available(ctx.now):
                continue
            res = ctx.routes.plan(self.anchor, st.node, robot_id=self.id, purpose="charger-check")
            self.plans += 1
            if not res.success:
                continue
            _, _, energy = self._compose(ctx, res)
            if energy <= self.battery_wh and (best is None or res.cost + st.expected_wait() < best[0]):
                best = (res.cost + st.expected_wait(), res, st.node)
        name = env.nodes[stop.node].name
        if best is None:
            msg = (f"{self.id}: no charger reachable on {self.battery_wh:.0f} Wh (route to {name} needs "
                   f"{needed:.0f} Wh) — heading to {name} anyway")
            self._log("BATTERY", msg)
            ctx.timeline.add(Category.BATTERY, "NO_REACHABLE_CHARGER", msg, severity=Severity.CRITICAL,
                             robot_id=self.id, node_id=stop.node)
            return None
        _, res, node = best
        ctx.charging.reserve(node, self.id)
        new_stop = Stop(StopKind.CHARGE, node)
        self.stops[0] = new_stop
        msg = (f"{self.id}: planned route to {name} needs {needed:.0f} Wh but only {self.battery_wh:.0f} Wh left — "
               f"switching to reachable {env.nodes[node].name}")
        self._log("BATTERY", msg)
        ctx.timeline.add(Category.BATTERY, "CHARGER_REASSIGNED", msg, severity=Severity.WARNING, robot_id=self.id,
                         node_id=node)
        return res, new_stop

    def _record_plan(self, ctx: AgentContext, result: SearchResult, purpose: str, trigger: str, energy: float,
                     stop: Stop) -> None:
        env = ctx.env
        self.plan = PlanInfo(result.algorithm, purpose, trigger, stop.node, result.cost, result.hops,
                             result.nodes_explored, result.nodes_generated, result.elapsed_ms, energy, ctx.now,
                             result.cached)
        alg = ALGORITHM_CATALOG[result.algorithm]["short"]
        via = [env.nodes[n].name for n in result.path[1:-1]]
        via_txt = ""
        if via:
            shown = via[:3] if len(via) <= 4 else via[:2] + ["…", via[-1]]
            via_txt = " via " + " → ".join(shown)
        replanned = trigger != "PLAN"
        verb = "New route" if replanned else "Route"
        msg = (f"{alg}: {verb.lower()} {env.nodes[result.start].name} → {env.nodes[stop.node].name}{via_txt} · "
               f"{result.hops} roads · cost {result.cost:.0f}s · {result.nodes_explored} nodes explored · "
               f"{result.elapsed_ms:.2f} ms")
        self._log("REPLAN" if replanned else "DECIDE", msg)
        data = result.as_dict()
        data.update({"purpose": purpose, "trigger": trigger, "energy_wh": round(energy, 1),
                     "energy_pct": round(pct(energy, self.max_battery_wh), 1)})
        ctx.timeline.add(Category.REPLANNING if replanned else Category.PLANNING,
                         "ROUTE_REPLANNED" if replanned else "ROUTE_PLANNED",
                         f"{self.id} {msg}", robot_id=self.id, order_id=stop.order_id, node_id=stop.node,
                         severity=Severity.NOTICE if replanned else Severity.INFO, data=data)

    def _reevaluate(self, ctx: AgentContext) -> None:
        reason = self.pending_reevaluate or ""
        self.pending_reevaluate = None
        if self.status != RobotStatus.EN_ROUTE or not self.on_edge or not self.stops:
            return
        stop = self.stops[0]
        if self.path[-1] != stop.node:
            return
        world = ctx.world
        current = sum(world.road_cost(r) for r in self.path_roads[self.path_index:])
        result = ctx.routes.plan(self.anchor, stop.node, robot_id=self.id, purpose="reevaluate")
        self.plans += 1
        alg = ALGORITHM_CATALOG[result.algorithm]["short"]
        if result.success and result.cost < current * (1.0 - REROUTE_MIN_GAIN):
            self.invalidated_path = self.path[self.path_index - 1:]
            self.invalidated_at = ctx.now
            self.path = [self.path[self.path_index - 1]] + result.path
            self.path_roads = [self.path_roads[self.path_index - 1]] + world.path_roads(result.path)
            self.path_index = 1
            self.replans += 1
            energy = world.roads_energy(self.path_roads, self.energy_rate)
            saved = current - result.cost
            ctx.timeline.add(Category.REPLANNING, "ROUTE_SWITCHED",
                             f"{self.id} rerouted around congestion — {alg} alternative saves {fmt_duration(saved)} "
                             f"({current:.0f}s → {result.cost:.0f}s)",
                             severity=Severity.NOTICE, robot_id=self.id, order_id=stop.order_id,
                             data={**result.as_dict(), "previous_cost": round(current, 1), "reason": reason,
                                   "invalidated_route": self.invalidated_path})
            ctx.bus.publish(Topics.ROBOT_REPLANNED, (self.id, "TRAFFIC"))
            self._record_plan(ctx, result, "reroute", "TRAFFIC", energy, stop)
        else:
            alt = f"best alternative {result.cost:.0f}s" if result.success else "no alternative"
            msg = f"{reason}; current route still best ({current:.0f}s vs {alt})"
            self._log("DECIDE", msg)
            ctx.timeline.add(Category.PLANNING, "ROUTE_KEPT", f"{self.id} kept route — {msg}",
                             robot_id=self.id, order_id=stop.order_id,
                             data={"current_cost": round(current, 1), "alternative": result.as_dict(False)})

    # ACT -------------------------------------------------------------------------------
    def _act(self, ctx: AgentContext) -> None:
        if self.status == RobotStatus.EN_ROUTE and self.on_edge:
            self._advance(ctx)
        elif self.status == RobotStatus.CHARGING:
            add = min(CHARGE_POWER_WH_PER_S * ctx.dt, self.max_battery_wh - self.battery_wh)
            self.battery_wh += add
            self.energy_charged += add
            ctx.charging.record_energy(self.id, add)

    def _advance(self, ctx: AgentContext) -> None:
        env = ctx.env
        budget = ctx.dt
        while budget > 1e-9:
            road = env.roads[self.path_roads[self.path_index - 1]]
            speed = self.speed_mps * ROAD_SPEED_FACTOR[road.road_class] / TRAFFIC_TIME_FACTOR[road.traffic]
            per_m = self.energy_rate * TRAFFIC_ENERGY_FACTOR[road.traffic]
            remaining = road.length - self.edge_progress
            step = min(speed * budget, remaining)
            if step * per_m >= self.battery_wh:
                self._travel(self.battery_wh / per_m, per_m)
                self._update_position(env)
                self._deplete(ctx)
                return
            self._travel(step, per_m)
            budget -= step / speed
            if self.edge_progress < road.length - 1e-6:
                break
            arrived = self.path[self.path_index]
            if self.path_index == len(self.path) - 1:
                self._set_at_node(env, arrived)
                self._arrive(ctx)
                return
            next_road = self.path_roads[self.path_index]
            if env.roads[next_road].blocked:
                # Physically at the junction and the next road is closed: stop and report.
                self._set_at_node(env, arrived)
                self._report_closure(ctx, next_road)
                self.request_replan("ROAD_BLOCKED", f"{env.roads[next_road].name} closed ahead")
                return
            self.path_index += 1
            self.edge_progress = 0.0
            self._at_intersection(ctx)
            if self.pending_replan is not None:
                break
        self._update_position(env)

    def _travel(self, distance: float, per_m: float) -> None:
        self.edge_progress += distance
        self.total_distance += distance
        energy = distance * per_m
        self.battery_wh = max(0.0, self.battery_wh - energy)
        self.energy_consumed += energy

    def _at_intersection(self, ctx: AgentContext) -> None:
        """Battery monitor, run at every junction."""
        if self.heading_to_charger():
            return
        if not self.battery_warned and self.battery_fraction < LOW_BATTERY_FRACTION:
            self.battery_warned = True
            ctx.timeline.add(Category.BATTERY, "LOW_BATTERY", f"{self.id} battery below "
                             f"{LOW_BATTERY_FRACTION * 100:.0f}% ({self.battery_pct:.0f}%)",
                             severity=Severity.WARNING, robot_id=self.id)
        self.check_battery(ctx)

    def check_battery(self, ctx: AgentContext) -> None:
        """Can the robot finish its current leg and still reach a charger? If not, divert."""
        if self.heading_to_charger() or not self.stops or self.status == RobotStatus.OFFLINE:
            return
        if self.path:
            goal = self.path[-1]
            remaining = ctx.world.roads_energy(self.remaining_roads(), self.energy_rate)
        else:
            goal = self.stops[0].node
            remaining = estimate_energy(ctx.world.straight_line(self.anchor, goal), self.energy_rate)
        reserve = ctx.charging.reserve_energy(goal, self.energy_rate)
        floor = self.max_battery_wh * MIN_RESERVE_FRACTION
        if self.battery_wh < remaining + reserve + floor:
            need = pct(remaining + reserve + floor, self.max_battery_wh)
            self.request_charge(f"remaining route needs ≈{need:.0f}% incl. reserve, battery at {self.battery_pct:.0f}%")

    def _arrive(self, ctx: AgentContext) -> None:
        stop = self.stops[0] if self.stops else None
        self._clear_path()
        if stop is None or stop.node != self.node:
            self._next_leg(ctx)
            return
        env = ctx.env
        self.active_stop = stop
        place = env.nodes[stop.node].name
        if stop.kind == StopKind.PICKUP:
            self._set_status(RobotStatus.LOADING)
            self.timer = PICKUP_DWELL_S
            self._log("ACT", f"Arrived at {place}; loading {stop.order_id}")
        elif stop.kind == StopKind.DROPOFF:
            self._set_status(RobotStatus.DELIVERING)
            self.timer = DROPOFF_DWELL_S
            self._log("ACT", f"Arrived at {place}; handing over {stop.order_id}")
        else:
            if ctx.charging.arrive(stop.node, self.id, ctx.now):
                self._start_charging(ctx)
            else:
                st = ctx.charging.stations[stop.node]
                self._set_status(RobotStatus.WAITING)
                self.wait_reason = "charger_queue"
                position = st.queue.index(self.id) + 1 if self.id in st.queue else 1
                msg = (f"{place} full ({len(st.charging)}/{st.slots} slots) — {self.id} queued at position {position}"
                       if st.is_available(ctx.now) else f"{place} unavailable — {self.id} waiting")
                self._log("ACT", msg)
                ctx.timeline.add(Category.COORDINATION, "CHARGING_STATION_BUSY", msg, severity=Severity.NOTICE,
                                 robot_id=self.id, node_id=stop.node)

    def _complete_stop(self, ctx: AgentContext) -> None:
        stop = self.active_stop
        self.active_stop = None
        if stop is None:
            self._next_leg(ctx)
            return
        if stop in self.stops:
            self.stops.remove(stop)
        order = ctx.orders.get(stop.order_id) if stop.order_id else None
        if order is not None and order.status not in CLOSED_STATUSES:
            env = ctx.env
            if stop.kind == StopKind.PICKUP:
                order.status = OrderStatus.IN_TRANSIT
                order.picked_up_at = ctx.now
                order.log(ctx.now, f"picked up by {self.id}")
                self.carrying.append(order.id)
                ctx.timeline.add(Category.ORDER, "ORDER_PICKED_UP",
                                 f"{self.id} picked up {order.id} at {env.nodes[stop.node].name}",
                                 robot_id=self.id, order_id=order.id, node_id=stop.node)
            else:
                order.status = OrderStatus.DELIVERED
                order.delivered_at = ctx.now
                order.log(ctx.now, f"delivered by {self.id}")
                if order.id in self.carrying:
                    self.carrying.remove(order.id)
                if order.id in self.active_orders:
                    self.active_orders.remove(order.id)
                self.orders_completed += 1
                slack = order.deadline - ctx.now
                timing = (f"on time ({fmt_duration(slack)} to spare)" if slack >= 0
                          else f"late by {fmt_duration(-slack)}")
                ctx.timeline.add(Category.ORDER, "ORDER_DELIVERED",
                                 f"{order.id} delivered by {self.id} to {env.nodes[stop.node].name} in "
                                 f"{fmt_duration(order.delivery_time or 0)} — {timing}",
                                 severity=Severity.INFO if slack >= 0 else Severity.WARNING,
                                 robot_id=self.id, order_id=order.id, node_id=stop.node,
                                 data={"delivery_time": round(order.delivery_time or 0, 1), "late": slack < 0})
                ctx.bus.publish(Topics.ORDER_DELIVERED, order)
                self._log("ACT", f"Delivered {order.id} ({timing})")
        self._next_leg(ctx)

    def _next_leg(self, ctx: AgentContext) -> None:
        self.pending_replan = None
        if self.needs_charge is not None:
            reason, self.needs_charge = self.needs_charge, None
            if not self.heading_to_charger():
                self._insert_charge_stop(ctx, reason)
        if self.stops:
            self._set_status(RobotStatus.PLANNING)
            self.timer = PLAN_DELAY_S
        else:
            self._set_status(RobotStatus.IDLE)
            self._log("DECIDE", "No tasks queued — idle")

    # Charging ---------------------------------------------------------------------------
    def _insert_charge_stop(self, ctx: AgentContext, reason: str) -> bool:
        choice = ctx.charging.select(self.anchor, self.battery_wh, self.energy_rate, self.speed_mps, ctx.now)
        if choice is None:
            self._log("BATTERY", "No charging station available")
            ctx.timeline.add(Category.BATTERY, "NO_CHARGER", f"{self.id} needs charge but no station is available",
                             severity=Severity.WARNING, robot_id=self.id)
            return False
        self.stops = [s for s in self.stops if s.kind != StopKind.CHARGE]
        self.stops.insert(0, Stop(StopKind.CHARGE, choice.station.node))
        ctx.charging.reserve(choice.station.node, self.id)
        self.low_battery_mode = True
        queue = f", expected wait {fmt_duration(choice.wait_s)}" if choice.wait_s > 0 else ""
        reach = "" if choice.reachable else " — WARNING: may be beyond remaining range"
        msg = (f"{self.id} battery {self.battery_pct:.0f}% — {reason}. Diverting to {choice.station.name} "
               f"(ETA ≈{fmt_duration(choice.eta_s)}{queue}){reach}")
        self._log("BATTERY", msg)
        ctx.timeline.add(Category.BATTERY, "CHARGE_DIVERSION", msg, severity=Severity.WARNING, robot_id=self.id,
                         node_id=choice.station.node,
                         data={"station": choice.station.name, "eta_s": round(choice.eta_s, 1),
                               "wait_s": round(choice.wait_s, 1), "battery_pct": round(self.battery_pct, 1)})
        return True

    def _reselect_charger(self, ctx: AgentContext) -> None:
        old = self.stops[0].node
        ctx.charging.cancel(self.id)
        choice = ctx.charging.select(self.anchor, self.battery_wh, self.energy_rate, self.speed_mps, ctx.now,
                                     exclude=(old,))
        if choice is None:
            return
        self.stops[0] = Stop(StopKind.CHARGE, choice.station.node)
        ctx.charging.reserve(choice.station.node, self.id)
        msg = (f"{self.id} switched charger {ctx.env.nodes[old].name} → {choice.station.name} "
               f"({ctx.env.nodes[old].name} unavailable)")
        self._log("BATTERY", msg)
        ctx.timeline.add(Category.COORDINATION, "CHARGER_REASSIGNED", msg, robot_id=self.id, node_id=choice.station.node)

    def _start_charging(self, ctx: AgentContext) -> None:
        self._set_status(RobotStatus.CHARGING)
        self.wait_reason = None
        self.charge_sessions += 1
        self.charge_started_at = ctx.now
        self.charge_start_wh = self.battery_wh
        place = ctx.env.nodes[self.node].name if self.node is not None else "station"
        self._log("ACT", f"Charging at {place} from {self.battery_pct:.0f}%")
        ctx.timeline.add(Category.BATTERY, "CHARGING_STARTED", f"{self.id} charging at {place} from "
                         f"{self.battery_pct:.0f}%", robot_id=self.id, node_id=self.node)

    def _finish_charging(self, ctx: AgentContext, interrupted: bool) -> None:
        ctx.charging.finish(self.id)
        if self.stops and self.stops[0].kind == StopKind.CHARGE:
            self.stops.pop(0)
        self.low_battery_mode = False
        self.battery_warned = False
        start = pct(self.charge_start_wh, self.max_battery_wh)
        place = ctx.env.nodes[self.node].name if self.node is not None else "station"
        note = " — left early for queued work" if interrupted else ""
        msg = (f"{self.id} charged {start:.0f}% → {self.battery_pct:.0f}% at {place} in "
               f"{fmt_duration(ctx.now - self.charge_started_at)}{note}")
        self._log("ACT", msg)
        ctx.timeline.add(Category.BATTERY, "CHARGING_COMPLETE", msg, robot_id=self.id, node_id=self.node)
        self._next_leg(ctx)

    # Failure handling ---------------------------------------------------------------------
    def _deplete(self, ctx: AgentContext) -> None:
        self.battery_wh = 0.0
        self.depletions += 1
        self.fail(ctx, "battery depleted", FIELD_SERVICE_DELAY_S, FIELD_SERVICE_CHARGE)

    def _tick_offline(self, ctx: AgentContext) -> None:
        if self.offline_until is None or ctx.now < self.offline_until:
            return
        if self.recover_battery is not None:
            self.battery_wh = max(self.battery_wh, self.recover_battery * self.max_battery_wh)
        reason = self.offline_reason
        self.offline_until = self.offline_reason = self.recover_battery = None
        self._set_status(RobotStatus.EN_ROUTE if self.on_edge else RobotStatus.IDLE)
        self._log("ACT", "Back in service")
        ctx.timeline.add(Category.AGENT, "ROBOT_RECOVERED",
                         f"{self.id} back in service after {reason} (battery {self.battery_pct:.0f}%)",
                         robot_id=self.id)

    # Helpers ------------------------------------------------------------------------------
    def _u_turn(self, env: Environment) -> None:
        """Reverse along the current road: a→b at progress p becomes b→a at progress (L − p)."""
        a, b = self.path[self.path_index - 1], self.path[self.path_index]
        road = self.path_roads[self.path_index - 1]
        self.path, self.path_roads, self.path_index = [b, a], [road], 1
        self.edge_progress = max(0.0, env.roads[road].length - self.edge_progress)

    def _truncate_to_current_edge(self) -> None:
        a, b = self.path[self.path_index - 1], self.path[self.path_index]
        road = self.path_roads[self.path_index - 1]
        self.path, self.path_roads, self.path_index = [a, b], [road], 1

    def _clear_path(self) -> None:
        self.path, self.path_roads, self.path_index = [], [], 0
        self.edge_progress = 0.0

    def _set_at_node(self, env: Environment, node: int) -> None:
        self.node = node
        self.edge_progress = 0.0
        n = env.nodes[node]
        self.x, self.y = n.x, n.y

    def _update_position(self, env: Environment) -> None:
        if not self.on_edge:
            return
        a = env.nodes[self.path[self.path_index - 1]]
        b = env.nodes[self.path[self.path_index]]
        length = math.hypot(b.x - a.x, b.y - a.y) or 1.0
        t = min(1.0, self.edge_progress / length)
        self.x = a.x + (b.x - a.x) * t
        self.y = a.y + (b.y - a.y) * t
        self.heading = math.atan2(b.y - a.y, b.x - a.x)

    def _set_status(self, status: RobotStatus) -> None:
        if status != self.status:
            self.status = status
            self.status_since = self.now

    def _log(self, phase: str, message: str) -> None:
        self.decisions.append((self.now, phase, message))
        if phase in ("DECIDE", "REPLAN", "BATTERY"):
            self.last_decision = message
            self.last_decision_t = self.now

    def _account(self, dt: float) -> None:
        s = self.status
        if s == RobotStatus.OFFLINE:
            self.offline_time += dt
        elif s == RobotStatus.CHARGING or (s == RobotStatus.WAITING and self.wait_reason == "charger_queue"):
            self.charging_time += dt
        elif self.active_orders or s in WORKING_STATUSES:
            self.busy_time += dt
        else:
            self.idle_time += dt

    @property
    def utilization(self) -> float:
        total = self.busy_time + self.idle_time + self.charging_time
        return self.busy_time / total if total > 0 else 0.0

