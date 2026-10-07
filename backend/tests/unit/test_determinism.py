from __future__ import annotations

import hashlib
import json

from app.simulation.engine import SimulationEngine
from app.simulation.scenarios import get_scenario


def state_hash(e: SimulationEngine) -> str:
    data = {
        "robots": [[r.id, round(r.x, 6), round(r.y, 6), round(r.battery_wh, 6), r.status.value, r.replans,
                    r.orders_completed, list(r.active_orders)] for r in e.fleet.robots],
        "orders": [[o.id, o.status.value, o.assigned_robot, o.delivered_at] for o in e.orders.all()],
        "roads": sorted(e.env.blocked_ids),
        "timeline": [(x.kind, x.message) for x in e.timeline.entries if x.kind not in ("ROUTE_PLANNED", "ROUTE_REPLANNED", "NO_ROUTE", "ROUTE_SWITCHED", "ROUTE_KEPT")],
    }
    return hashlib.sha256(json.dumps(data, default=str).encode()).hexdigest()


def test_same_seed_same_run():
    cfg = get_scenario("road_closure", seed=99)
    a, b = SimulationEngine(cfg), SimulationEngine(cfg)
    a.run_until(900)
    b.run_until(900)
    assert state_hash(a) == state_hash(b)
    assert a.metrics.global_summary(a)["orders_delivered"] == b.metrics.global_summary(b)["orders_delivered"]


def test_different_seed_different_run():
    a = SimulationEngine(get_scenario("baseline", seed=1))
    b = SimulationEngine(get_scenario("baseline", seed=2))
    a.run_until(300)
    b.run_until(300)
    assert state_hash(a) != state_hash(b)


def test_initial_conditions_do_not_depend_on_algorithm():
    prints = {SimulationEngine(get_scenario("surge", algorithm=alg)).fingerprints["graph"] for alg in ("bfs", "astar")}
    full = [SimulationEngine(get_scenario("surge", algorithm=alg)).fingerprints for alg in ("bfs", "dfs", "astar")]
    assert len(prints) == 1
    assert full[0] == full[1] == full[2]


def test_demo_script_is_deterministic():
    cfg = get_scenario("demo")
    a, b = SimulationEngine(cfg), SimulationEngine(cfg)
    a.run_until(600)
    b.run_until(600)
    assert state_hash(a) == state_hash(b)
    assert a.demo.index == len(a.demo.phases) - 1
