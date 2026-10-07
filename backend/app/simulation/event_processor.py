"""Applies environment events to the simulation (ground truth, world model and agents)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.robot import RobotStatus
from app.simulation.environment import NodeKind, TrafficLevel
from app.simulation.events import EventSource, EventType, ScheduledEvent
from app.simulation.orders import OrderStatus, Priority
from app.simulation.timeline import Category, Severity

if TYPE_CHECKING:
    from app.simulation.engine import SimulationEngine


class EventProcessor:
    def __init__(self, engine: SimulationEngine) -> None:
        self.e = engine

    def apply(self, ev: ScheduledEvent) -> None:
        handler = getattr(self, f"_on_{ev.type.value.lower()}")
        try:
            handler(ev)
        except (KeyError, ValueError, IndexError) as exc:
            self.e.timeline.add(Category.SYSTEM, "EVENT_REJECTED", f"{ev.type.value} ignored: {exc}",
                                severity=Severity.WARNING, data=ev.as_dict())

    # Roads -------------------------------------------------------------------------------
    def _on_road_blocked(self, ev: ScheduledEvent) -> None:
        e = self.e
        rid = int(ev.params["road_id"])
        road = e.env.roads[rid]
        if road.blocked:
            return
        e.env.set_blocked(rid, True)
        duration = ev.params.get("duration_s")
        if duration:
            e.scheduler.schedule(e.now + float(duration), EventType.ROAD_REOPENED, {"road_id": rid}, ev.source)
        where = f"{e.env.nodes[road.a].name}–{e.env.nodes[road.b].name}"
        reopen = f", reopens in ≈{float(duration) / 60:.0f} min" if duration else ""
        if ev.source == EventSource.OPERATOR:
            e.timeline.add(Category.ENVIRONMENT, "ROAD_BLOCKED",
                           f"Operator closed {road.name} ({road.road_class.value}, {where}){reopen} — announced to fleet",
                           severity=Severity.WARNING, road_id=rid, data={"hidden": False, "source": ev.source.value})
            e.channel.report_road_blocked("OPERATOR", rid)
        else:
            e.timeline.add(Category.ENVIRONMENT, "ROAD_BLOCKED",
                           f"Incident: {road.name} ({road.road_class.value}, {where}) closed{reopen} — "
                           f"not yet known to the fleet",
                           severity=Severity.WARNING, road_id=rid, data={"hidden": True, "source": ev.source.value})

    def _on_road_reopened(self, ev: ScheduledEvent) -> None:
        e = self.e
        rid = int(ev.params["road_id"])
        road = e.env.roads[rid]
        if not road.blocked:
            return
        e.env.set_blocked(rid, False)
        e.timeline.add(Category.ENVIRONMENT, "ROAD_REOPENED", f"{road.name} reopened", road_id=rid)
        e.channel.announce_reopened("CITY-OPS", rid)

    def _on_traffic_increase(self, ev: ScheduledEvent) -> None:
        e = self.e
        roads = [int(r) for r in ev.params.get("road_ids") or [ev.params["road_id"]]]
        level = TrafficLevel[str(ev.params.get("level", "HIGH")).upper()]
        updates = [(r, level) for r in roads if e.env.roads[r].traffic < level]
        if not updates:
            return
        for rid, lvl in updates:
            e.env.set_traffic(rid, lvl)
        duration = ev.params.get("duration_s")
        if duration:
            e.scheduler.schedule(e.now + float(duration), EventType.TRAFFIC_CLEAR,
                                 {"road_ids": [r for r, _ in updates]}, ev.source)
        names = ", ".join(e.env.roads[r].name for r, _ in updates[:4])
        more = f" +{len(updates) - 4}" if len(updates) > 4 else ""
        e.timeline.add(Category.ENVIRONMENT, "TRAFFIC_INCREASE",
                       f"Traffic {level.label} on {names}{more}", severity=Severity.NOTICE,
                       road_id=updates[0][0], data={"roads": [r for r, _ in updates], "level": level.name})
        e.channel.announce_traffic("TRAFFIC-FEED", updates)

    def _on_traffic_clear(self, ev: ScheduledEvent) -> None:
        e = self.e
        roads = [int(r) for r in ev.params.get("road_ids") or [ev.params["road_id"]]]
        updates = [(r, TrafficLevel.LOW) for r in roads if e.env.roads[r].traffic != TrafficLevel.LOW]
        if not updates:
            return
        for rid, lvl in updates:
            e.env.set_traffic(rid, lvl)
        names = ", ".join(e.env.roads[r].name for r, _ in updates[:4])
        e.timeline.add(Category.ENVIRONMENT, "TRAFFIC_CLEAR", f"Traffic cleared on {names}",
                       road_id=updates[0][0], data={"roads": [r for r, _ in updates]})
        e.channel.announce_traffic("TRAFFIC-FEED", updates)

    # Orders ------------------------------------------------------------------------------
    def _on_new_order(self, ev: ScheduledEvent) -> None:
        e = self.e
        rng = e.operator_rng
        source = ev.params.get("source")
        destination = ev.params.get("destination")
        if source is None:
            source = rng.choice([n.id for n in e.env.nodes_of_kind(NodeKind.WAREHOUSE)])
        if destination is None:
            destination = rng.choice([n.id for n in e.env.nodes_of_kind(NodeKind.CUSTOMER)])
        priority = Priority[str(ev.params.get("priority", "NORMAL")).upper()]
        e.create_order(int(source), int(destination), priority, origin=ev.source.value.lower())

    def _on_order_cancelled(self, ev: ScheduledEvent) -> None:
        e = self.e
        order_id = ev.params.get("order_id")
        if order_id is None:
            candidates = [o for o in e.orders.open_orders() if o.status != OrderStatus.IN_TRANSIT]
            if not candidates:
                raise ValueError("no cancellable order")
            order = e.operator_rng.choice(sorted(candidates, key=lambda o: o.seq))
        else:
            order = e.orders.get(order_id)
            if order is None:
                raise KeyError(f"order {order_id} not found")
        if order.status == OrderStatus.IN_TRANSIT:
            raise ValueError(f"{order.id} is already on board a robot")
        if not order.is_open:
            return
        robot_id = order.assigned_robot
        order.status = OrderStatus.CANCELLED
        order.log(e.now, "cancelled")
        if robot_id:
            robot = e.fleet.get(robot_id)
            if robot:
                robot.release(order.id, e.ctx, "order cancelled by customer")
        e.timeline.add(Category.ORDER, "ORDER_CANCELLED",
                       f"{order.id} cancelled" + (f" — {robot_id} released" if robot_id else ""),
                       order_id=order.id, robot_id=robot_id)

    # Robots & infrastructure ---------------------------------------------------------------
    def _on_robot_low_battery(self, ev: ScheduledEvent) -> None:
        e = self.e
        robot = e.fleet.get(ev.params["robot_id"])
        if robot is None:
            raise KeyError(f"robot {ev.params['robot_id']} not found")
        level = float(ev.params.get("level", 0.12))
        before = robot.battery_pct
        robot.set_battery_fraction(level)
        e.timeline.add(Category.BATTERY, "ROBOT_LOW_BATTERY",
                       f"Battery fault on {robot.id}: reading dropped {before:.0f}% → {robot.battery_pct:.0f}%",
                       severity=Severity.WARNING, robot_id=robot.id)
        robot.check_battery(e.ctx)

    def _on_robot_failure(self, ev: ScheduledEvent) -> None:
        e = self.e
        robot = e.fleet.get(ev.params["robot_id"])
        if robot is None:
            raise KeyError(f"robot {ev.params['robot_id']} not found")
        if robot.status == RobotStatus.OFFLINE:
            return
        robot.fail(e.ctx, str(ev.params.get("reason", "drive fault")), float(ev.params.get("duration_s", 240.0)))

    def _on_charging_station_busy(self, ev: ScheduledEvent) -> None:
        e = self.e
        node = int(ev.params["node_id"])
        if node not in e.charging.stations:
            raise ValueError(f"node {node} is not a charging station")
        duration = float(ev.params.get("duration_s", 300.0))
        st = e.charging.mark_unavailable(node, e.now + duration)
        affected = sorted(set(st.reserved) | set(st.queue))
        for rid in affected:
            robot = e.fleet.get(rid)
            if robot:
                robot.request_replan("CHARGER_UNAVAILABLE", f"{st.name} unavailable")
        e.timeline.add(Category.COORDINATION, "CHARGING_STATION_BUSY",
                       f"{st.name} unavailable for {duration / 60:.0f} min — {len(affected)} robot(s) redirected",
                       severity=Severity.WARNING, node_id=node, data={"affected": affected})
