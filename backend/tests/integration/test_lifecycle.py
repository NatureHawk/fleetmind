"""End-to-end behaviour of the engine: delivery lifecycle, closures, charging, experiments."""

from __future__ import annotations

import pytest

from app.agents.robot import RobotStatus
from app.metrics.experiment_runner import run_experiment
from app.simulation.engine import SimulationEngine
from app.simulation.environment import NodeKind
from app.simulation.orders import OrderStatus, Priority
from app.simulation.scenarios import get_scenario


def test_delivery_lifecycle(make_engine):
    e = make_engine(robots=2)
    wh = e.env.nodes_of_kind(NodeKind.WAREHOUSE)[0].id
    cu = e.env.nodes_of_kind(NodeKind.CUSTOMER)[3].id
    order = e.create_order(wh, cu, Priority.HIGH)
    seen = [order.status]
    while order.status != OrderStatus.DELIVERED and e.now < 3000:
        e.step()
        if not seen or seen[-1] != order.status:
            seen.append(order.status)
    assert seen == [OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED]
    robot = e.fleet.get(order.assigned_robot)
    assert robot.orders_completed == 1 and not robot.active_orders and not robot.carrying
    assert order.created_at <= order.assigned_at <= order.picked_up_at <= order.delivered_at
    kinds = [x.kind for x in e.timeline.query(order_id=order.id)]
    for k in ("NEW_ORDER", "ORDER_ASSIGNED", "ORDER_PICKED_UP", "ORDER_DELIVERED"):
        assert k in kinds
    e.run_until(e.now + 30)
    assert robot.status == RobotStatus.IDLE


def test_robot_assignment_spreads_work(make_engine):
    e = make_engine(robots=4)
    whs = [n.id for n in e.env.nodes_of_kind(NodeKind.WAREHOUSE)]
    cus = [n.id for n in e.env.nodes_of_kind(NodeKind.CUSTOMER)]
    for i in range(4):
        e.create_order(whs[i % len(whs)], cus[i * 5], Priority.NORMAL)
    e.run_until(10)
    assigned = {o.assigned_robot for o in e.orders.all()}
    assert len(assigned) == 4  # workload penalty spreads four orders over four idle robots


def test_dynamic_road_closure_scenario_completes_with_replans():
    cfg = get_scenario("road_closure", seed=4242)
    e = SimulationEngine(cfg)
    e.run_until(1500)
    s = e.metrics.global_summary(e)
    kinds = {x.kind for x in e.timeline.entries}
    assert "ROAD_BLOCKED" in kinds and "CLOSURE_DETECTED" in kinds
    assert s["replans"] > 0
    assert s["orders_delivered"] > 10
    assert s["battery_depletions"] == 0
    # No robot is ever routed over a road the fleet knows is closed.
    for r in e.fleet.robots:
        upcoming = r.remaining_roads()[1:]
        assert not any(e.world.is_blocked(x) for x in upcoming)


def test_battery_charging_cycle(make_engine):
    e = make_engine(robots=2, battery_min=0.22, battery_max=0.25)
    wh = e.env.nodes_of_kind(NodeKind.WAREHOUSE)
    cu = e.env.nodes_of_kind(NodeKind.CUSTOMER)
    for i in range(6):
        e.create_order(wh[i % len(wh)].id, cu[i * 7].id, Priority.NORMAL)
    e.run_until(2400)
    kinds = [x.kind for x in e.timeline.entries]
    assert kinds.count("CHARGING_STARTED") >= 2
    assert "CHARGING_COMPLETE" in kinds
    assert all(r.depletions == 0 for r in e.fleet.robots)
    assert sum(r.orders_completed for r in e.fleet.robots) >= 3


def test_experiment_comparison_is_fair_and_meaningful():
    scenario = get_scenario("baseline", seed=777)
    out = run_experiment(scenario, ["bfs", "greedy", "dijkstra", "astar"], repetitions=1, duration_s=600)
    assert out["fairness"]["identical_conditions"] is True
    agg = out["aggregates"]
    # A* and Dijkstra are both optimal → identical routes and outcomes; A* expands fewer nodes.
    assert agg["astar"]["avg_route_cost"]["mean"] == pytest.approx(agg["dijkstra"]["avg_route_cost"]["mean"])
    assert agg["astar"]["deliveries_completed"]["mean"] == agg["dijkstra"]["deliveries_completed"]["mean"]
    assert agg["astar"]["avg_nodes_explored"]["mean"] < agg["dijkstra"]["avg_nodes_explored"]["mean"]
    # Greedy explores the least; uninformed BFS routes are no cheaper than optimal ones.
    assert agg["greedy"]["avg_nodes_explored"]["mean"] < agg["astar"]["avg_nodes_explored"]["mean"]
    for r in out["results"]:
        assert r["metrics"]["searches"] > 0 and r["metrics"]["orders_created"] > 0


def test_experiment_repetitions_use_distinct_seeds():
    scenario = get_scenario("baseline", seed=5)
    out = run_experiment(scenario, ["astar"], repetitions=2, duration_s=300)
    seeds = [r["seed"] for r in out["results"]]
    assert len(set(seeds)) == 2
    assert out["aggregates"]["astar"]["deliveries_completed"]["n"] == 2
