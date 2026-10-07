"""Serialisation of simulation state for the API and the real-time channel.

* ``static_payload`` — the map (sent once per run, it never changes)
* ``live_snapshot`` — the compact per-frame state (robots, open orders, road overrides,
  chargers, KPIs, new timeline entries)
* ``robot_detail`` / ``order_detail`` — the inspector views
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.battery import pct
from app.agents.robot import INVALIDATED_ROUTE_TTL_S, RobotAgent, RobotStatus
from app.core.formatting import fmt_duration
from app.planning.registry import ALGORITHM_CATALOG
from app.simulation.environment import REFERENCE_SPEED_MPS, TrafficLevel
from app.simulation.orders import Order, OrderStatus

if TYPE_CHECKING:
    from app.simulation.engine import SimulationEngine

RECENT_CLOSED_ORDERS = 25


def static_payload(engine: SimulationEngine) -> dict:
    env = engine.env
    return {
        "seed": env.seed,
        "width": env.width,
        "height": env.height,
        "fingerprint": env.fingerprint(),
        "nodes": [{"id": n.id, "x": n.x, "y": n.y, "kind": n.kind.value, "zone": n.zone.value, "name": n.name,
                   "degree": env.degree(n.id)} for n in env.nodes],
        "roads": [{"id": r.id, "a": r.a, "b": r.b, "length": r.length, "class": r.road_class.value,
                   "name": r.name} for r in env.roads],
        "faces": [{"id": f.id, "nodes": f.nodes, "zone": f.zone.value} for f in env.faces],
        "districts": [{"name": d.name, "zone": d.zone.value, "x": d.x, "y": d.y} for d in env.districts],
        "chargers": [{"node": node, "slots": slots} for node, slots in sorted(env.charger_slots.items())],
    }


def _robot_state(r: RobotAgent, now: float) -> dict:
    stop = r.current_stop
    invalid = r.invalidated_path if now - r.invalidated_at <= INVALIDATED_ROUTE_TTL_S else None
    return {
        "id": r.id,
        "model": r.model.name,
        "status": r.status.value,
        "x": round(r.x, 2),
        "y": round(r.y, 2),
        "heading": round(r.heading, 3),
        "battery_pct": round(r.battery_pct, 1),
        "capacity": r.capacity,
        "orders": list(r.active_orders),
        "carrying": list(r.carrying),
        "current_order": r.current_order_id,
        "target": None if stop is None else {"node": stop.node, "kind": stop.kind.value, "order_id": stop.order_id},
        "route": r.display_route(),
        "invalidated_route": invalid,
        "invalidated_at": round(r.invalidated_at, 1) if invalid else None,
        "replans": r.replans,
        "orders_completed": r.orders_completed,
        "low_battery": r.low_battery_mode,
        "algorithm": r.plan.algorithm if r.plan else None,
        "route_cost": round(r.plan.cost, 1) if r.plan and r.path else None,
    }


def _order_state(o: Order) -> dict:
    return {
        "id": o.id,
        "source": o.source,
        "destination": o.destination,
        "priority": o.priority.label,
        "status": o.status.value,
        "created_at": round(o.created_at, 1),
        "deadline": round(o.deadline, 1),
        "assigned_robot": o.assigned_robot,
        "picked_up_at": None if o.picked_up_at is None else round(o.picked_up_at, 1),
        "delivered_at": None if o.delivered_at is None else round(o.delivered_at, 1),
        "late": o.late,
    }


def live_snapshot(engine: SimulationEngine, since_seq: int, *, running: bool, speed: float) -> dict:
    now = engine.now
    env = engine.env
    world = engine.world
    open_orders = [o for o in engine.orders.all() if o.is_open]
    closed = [o for o in engine.orders.all() if not o.is_open]
    closed.sort(key=lambda o: o.delivered_at or o.created_at, reverse=True)
    roads = []
    for r in env.roads:
        if r.blocked or r.traffic != TrafficLevel.LOW or r.id in world.known_blocked:
            roads.append({"id": r.id, "traffic": r.traffic.label, "blocked": r.blocked,
                          "known": r.id in world.known_blocked})
    summary = engine.metrics.global_summary(engine)
    return {
        "type": "snapshot",
        "t": round(now, 2),
        "tick": engine.clock.tick,
        "running": running,
        "speed": speed,
        "scenario": engine.config.key,
        "scenario_name": engine.config.name,
        "seed": engine.seed,
        "algorithm": engine.routes.algorithm,
        "heuristic": engine.routes.heuristic,
        "robots": [_robot_state(r, now) for r in engine.fleet.robots],
        "orders": [_order_state(o) for o in sorted(open_orders, key=lambda o: o.seq)],
        "recent_orders": [_order_state(o) for o in closed[:RECENT_CLOSED_ORDERS]],
        "roads": roads,
        "chargers": [st.as_dict(now) for st in engine.charging.stations.values()],
        "kpis": summary,
        "events": [e.as_dict() for e in engine.timeline.since(since_seq, limit=200)],
        "last_seq": engine.timeline.last_seq,
        "demo": engine.demo.state() if engine.demo else None,
        "upcoming_events": len(engine.scheduler),
    }


def _loop_state(r: RobotAgent, engine: SimulationEngine) -> dict:
    env = engine.env
    sensed, anomalies = r.perception
    status = r.status
    if status == RobotStatus.EN_ROUTE and r.on_edge:
        road = env.roads[r.current_road]
        target = env.nodes[r.path[-1]].name
        act = f"Driving {road.name} ({road.traffic.label} traffic) toward {target}"
    elif status == RobotStatus.CHARGING:
        act = f"Charging at {env.nodes[r.node].name if r.node is not None else 'station'}"
    elif status == RobotStatus.LOADING:
        act = f"Loading parcel ({max(r.timer, 0):.0f}s left)"
    elif status == RobotStatus.DELIVERING:
        act = f"Handing over parcel ({max(r.timer, 0):.0f}s left)"
    elif status == RobotStatus.WAITING:
        act = "Queued for a charging slot" if r.wait_reason == "charger_queue" else "Holding — no route available"
    elif status == RobotStatus.REPLANNING:
        act = "Holding position while replanning"
    elif status == RobotStatus.OFFLINE:
        act = f"Offline — {r.offline_reason}"
    else:
        act = "Stationary"
    phase = "REPLAN" if status == RobotStatus.REPLANNING else "DECIDE" if status in (
        RobotStatus.PLANNING, RobotStatus.ASSIGNED) else "ACT"
    return {
        "phase": phase,
        "perceive": f"{sensed} road(s) sensed · " + ("no anomalies" if anomalies == 0 else f"{anomalies} anomaly reported"),
        "decide": r.last_decision,
        "decide_t": round(r.last_decision_t, 1),
        "act": act,
    }


def robot_detail(engine: SimulationEngine, robot_id: str) -> dict | None:
    r = engine.fleet.get(robot_id)
    if r is None:
        return None
    env = engine.env
    now = engine.now
    data = _robot_state(r, now)
    remaining_energy = engine.world.roads_energy(r.remaining_roads(), r.energy_rate) if r.path else 0.0
    data.update({
        "speed_mps": round(r.speed_mps, 2),
        "speed_factor": round(r.speed_mps / REFERENCE_SPEED_MPS, 2),
        "battery_wh": round(r.battery_wh, 1),
        "max_battery_wh": r.max_battery_wh,
        "energy_rate_wh_per_m": round(r.energy_rate, 4),
        "node": r.node,
        "status_since": round(r.status_since, 1),
        "stops": [{"kind": s.kind.value, "node": s.node, "name": env.nodes[s.node].name, "order_id": s.order_id}
                  for s in r.stops],
        "plan": None if r.plan is None else {
            **r.plan.as_dict(),
            "algorithm_name": ALGORITHM_CATALOG[r.plan.algorithm]["short"],
            "goal_name": env.nodes[r.plan.goal].name,
        },
        "route_names": [env.nodes[n].name for n in r.display_route()],
        "remaining_energy_pct": round(pct(remaining_energy, r.max_battery_wh), 1),
        "distance_km": round(r.total_distance / 1000.0, 3),
        "energy_wh": round(r.energy_consumed, 1),
        "energy_pct_used": round(pct(r.energy_consumed, r.max_battery_wh), 1),
        "energy_charged_wh": round(r.energy_charged, 1),
        "stats": {
            "plans": r.plans,
            "replans": r.replans,
            "orders_completed": r.orders_completed,
            "charge_sessions": r.charge_sessions,
            "depletions": r.depletions,
            "idle_time": round(r.idle_time, 1),
            "busy_time": round(r.busy_time, 1),
            "charging_time": round(r.charging_time, 1),
            "offline_time": round(r.offline_time, 1),
            "utilization": round(r.utilization, 4),
        },
        "loop": _loop_state(r, engine),
        "decisions": [{"t": round(t, 1), "phase": phase, "message": msg} for t, phase, msg in list(r.decisions)[-40:]],
        "wait_reason": r.wait_reason,
        "offline_reason": r.offline_reason,
    })
    return data


def order_detail(engine: SimulationEngine, order_id: str) -> dict | None:
    o = engine.orders.get(order_id)
    if o is None:
        return None
    env = engine.env
    data = _order_state(o)
    now = engine.now
    data.update({
        "source_name": env.nodes[o.source].name,
        "destination_name": env.nodes[o.destination].name,
        "assigned_at": None if o.assigned_at is None else round(o.assigned_at, 1),
        "delivery_time": None if o.delivery_time is None else round(o.delivery_time, 1),
        "time_to_deadline": round(o.deadline - now, 1) if o.is_open else None,
        "time_to_deadline_text": fmt_duration(abs(o.deadline - now)) if o.is_open else None,
        "failure_reason": o.failure_reason,
        "assignment_count": o.assignment_count,
        "explanation": o.explanation,
        "history": [{"t": round(t, 1), "message": m} for t, m in o.history],
        "open": o.status not in (OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.CANCELLED),
    })
    return data
