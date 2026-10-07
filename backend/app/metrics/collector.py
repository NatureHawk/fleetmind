"""Metrics collection.

Search telemetry is gathered from ``PLAN_COMPLETED`` events; delivery, energy and
utilisation metrics are computed from the order book and the robots at query time, so they
can never drift from the simulation state. Nothing here is estimated or hard-coded.
"""

from __future__ import annotations

import statistics
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.event_bus import EventBus, Topics
from app.planning.route_service import PlanRecord
from app.simulation.orders import OrderStatus

if TYPE_CHECKING:
    from app.simulation.engine import SimulationEngine


@dataclass
class AlgorithmStats:
    requests: int = 0
    executed: int = 0
    cache_hits: int = 0
    successes: int = 0
    failures: int = 0
    nodes_explored: int = 0
    nodes_generated: int = 0
    max_nodes: int = 0
    elapsed_ms: float = 0.0
    route_cost: float = 0.0
    hops: int = 0
    purposes: Counter = field(default_factory=Counter)

    def add(self, rec: PlanRecord) -> None:
        r = rec.result
        self.requests += 1
        self.purposes[rec.purpose] += 1
        if r.cached:
            self.cache_hits += 1
        else:
            self.executed += 1
            self.nodes_explored += r.nodes_explored
            self.nodes_generated += r.nodes_generated
            self.max_nodes = max(self.max_nodes, r.nodes_explored)
            self.elapsed_ms += r.elapsed_ms
        if r.success:
            self.successes += 1
            self.route_cost += r.cost
            self.hops += r.hops
        else:
            self.failures += 1

    def summary(self) -> dict:
        ex = max(self.executed, 1)
        ok = max(self.successes, 1)
        return {
            "requests": self.requests,
            "searches": self.executed,
            "cache_hits": self.cache_hits,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.successes / self.requests, 4) if self.requests else None,
            "nodes_explored": self.nodes_explored,
            "avg_nodes_explored": round(self.nodes_explored / ex, 2) if self.executed else None,
            "max_nodes_explored": self.max_nodes,
            "avg_nodes_generated": round(self.nodes_generated / ex, 2) if self.executed else None,
            "planning_ms_total": round(self.elapsed_ms, 3),
            "avg_planning_ms": round(self.elapsed_ms / ex, 4) if self.executed else None,
            "avg_route_cost": round(self.route_cost / ok, 2) if self.successes else None,
            "avg_hops": round(self.hops / ok, 2) if self.successes else None,
            "purposes": dict(self.purposes),
        }


class MetricsCollector:
    def __init__(self, bus: EventBus, sample_interval: float = 15.0) -> None:
        self.algorithms: dict[str, AlgorithmStats] = {}
        self.replans = 0
        self.replan_triggers: Counter = Counter()
        self.samples: list[dict] = []
        self.sample_interval = sample_interval
        self.next_sample = 0.0
        self.recent_plans: deque[dict] = deque(maxlen=300)
        bus.subscribe(Topics.PLAN_COMPLETED, self._on_plan)
        bus.subscribe(Topics.ROBOT_REPLANNED, self._on_replan)

    def _on_plan(self, rec: PlanRecord) -> None:
        self.algorithms.setdefault(rec.result.algorithm, AlgorithmStats()).add(rec)
        r = rec.result
        self.recent_plans.append({
            "t": round(rec.t, 1), "robot_id": rec.robot_id, "purpose": rec.purpose, "algorithm": r.algorithm,
            "nodes_explored": r.nodes_explored, "elapsed_ms": round(r.elapsed_ms, 4), "cost": round(r.cost, 1)
            if r.success else None, "hops": r.hops, "success": r.success, "cached": r.cached,
        })

    def _on_replan(self, payload: tuple[str, str]) -> None:
        self.replans += 1
        self.replan_triggers[payload[1]] += 1

    # ------------------------------------------------------------------------------------
    def maybe_sample(self, engine: SimulationEngine) -> None:
        if engine.now + 1e-9 >= self.next_sample:
            self.samples.append(self._sample(engine))
            self.next_sample += self.sample_interval

    def _sample(self, engine: SimulationEngine) -> dict:
        robots = engine.fleet.robots
        orders = engine.orders.all()
        statuses = Counter(r.status.value for r in robots)
        delivered = [o for o in orders if o.status == OrderStatus.DELIVERED]
        return {
            "t": round(engine.now, 1),
            "delivered": len(delivered),
            "failed": sum(1 for o in orders if o.status == OrderStatus.FAILED),
            "pending": sum(1 for o in orders if o.status == OrderStatus.PENDING),
            "open": sum(1 for o in orders if o.is_open),
            "created": len(orders),
            "avg_battery_pct": round(statistics.fmean(r.battery_pct for r in robots), 2) if robots else 0.0,
            "energy_wh": round(sum(r.energy_consumed for r in robots), 1),
            "distance_m": round(sum(r.total_distance for r in robots), 1),
            "replans": self.replans,
            "busy": sum(1 for r in robots if r.active_orders),
            "charging": statuses.get("CHARGING", 0),
            "offline": statuses.get("OFFLINE", 0),
            "statuses": dict(statuses),
            "nodes_explored": sum(a.nodes_explored for a in self.algorithms.values()),
        }

    # ------------------------------------------------------------------------------------
    def global_summary(self, engine: SimulationEngine) -> dict:
        robots = engine.fleet.robots
        orders = engine.orders.all()
        by_status = Counter(o.status.value for o in orders)
        delivered = [o for o in orders if o.status == OrderStatus.DELIVERED]
        times = [o.delivery_time for o in delivered if o.delivery_time is not None]
        on_time = sum(1 for o in delivered if not o.late)
        waits = [o.assigned_at - o.created_at for o in orders if o.assigned_at is not None]
        total_plan = AlgorithmStats()
        for s in self.algorithms.values():
            total_plan.requests += s.requests
            total_plan.executed += s.executed
            total_plan.cache_hits += s.cache_hits
            total_plan.successes += s.successes
            total_plan.failures += s.failures
            total_plan.nodes_explored += s.nodes_explored
            total_plan.elapsed_ms += s.elapsed_ms
            total_plan.route_cost += s.route_cost
            total_plan.hops += s.hops
        plan = total_plan.summary()
        energy_wh = sum(r.energy_consumed for r in robots)
        distance_m = sum(r.total_distance for r in robots)
        utilizations = [r.utilization for r in robots]
        closed = by_status.get("DELIVERED", 0) + by_status.get("FAILED", 0)
        return {
            "t": round(engine.now, 1),
            "orders_created": len(orders),
            "orders_delivered": by_status.get("DELIVERED", 0),
            "orders_failed": by_status.get("FAILED", 0),
            "orders_cancelled": by_status.get("CANCELLED", 0),
            "orders_pending": by_status.get("PENDING", 0),
            "orders_assigned": by_status.get("ASSIGNED", 0),
            "orders_in_transit": by_status.get("IN_TRANSIT", 0),
            "completion_rate": round(by_status.get("DELIVERED", 0) / closed, 4) if closed else None,
            "on_time_rate": round(on_time / len(delivered), 4) if delivered else None,
            "avg_delivery_time": round(statistics.fmean(times), 2) if times else None,
            "p90_delivery_time": round(statistics.quantiles(times, n=10)[-1], 2) if len(times) >= 10 else None,
            "avg_assignment_wait": round(statistics.fmean(waits), 2) if waits else None,
            "total_distance_km": round(distance_m / 1000.0, 3),
            "total_energy_kwh": round(energy_wh / 1000.0, 4),
            "energy_per_delivery_wh": round(energy_wh / len(delivered), 2) if delivered else None,
            "searches": plan["searches"],
            "plan_requests": plan["requests"],
            "cache_hits": plan["cache_hits"],
            "nodes_explored": plan["nodes_explored"],
            "avg_nodes_explored": plan["avg_nodes_explored"],
            "avg_planning_ms": plan["avg_planning_ms"],
            "avg_route_cost": plan["avg_route_cost"],
            "plan_success_rate": plan["success_rate"],
            "replans": self.replans,
            "replan_triggers": dict(self.replan_triggers),
            "robot_utilization": round(statistics.fmean(utilizations), 4) if utilizations else None,
            "robots_total": len(robots),
            "robots_busy": sum(1 for r in robots if r.active_orders),
            "robots_charging": sum(1 for r in robots if r.status.value == "CHARGING"),
            "robots_offline": sum(1 for r in robots if r.status.value == "OFFLINE"),
            "battery_depletions": sum(r.depletions for r in robots),
            "charge_sessions": sum(r.charge_sessions for r in robots),
            "preemptions": engine.allocator.preemptions,
            "assignments": engine.allocator.assignments,
            "fleet_messages": engine.channel.message_count,
        }

    def algorithm_summary(self) -> dict[str, dict]:
        return {k: v.summary() for k, v in sorted(self.algorithms.items())}

    @staticmethod
    def robot_metrics(engine: SimulationEngine) -> list[dict]:
        return [{
            "id": r.id,
            "model": r.model.name,
            "status": r.status.value,
            "battery_pct": round(r.battery_pct, 1),
            "orders_completed": r.orders_completed,
            "distance_km": round(r.total_distance / 1000.0, 3),
            "energy_wh": round(r.energy_consumed, 1),
            "idle_time": round(r.idle_time, 1),
            "busy_time": round(r.busy_time, 1),
            "charging_time": round(r.charging_time, 1),
            "offline_time": round(r.offline_time, 1),
            "utilization": round(r.utilization, 4),
            "replans": r.replans,
            "plans": r.plans,
            "charge_sessions": r.charge_sessions,
            "depletions": r.depletions,
            "current_order": r.current_order_id,
        } for r in engine.fleet.robots]
