from __future__ import annotations

from collections import Counter

from app.agents.robot import RobotStatus
from app.allocation.scoring import evaluate
from app.simulation.environment import NodeKind
from app.simulation.orders import OrderStatus, Priority


def _warehouse_and_customer(e, near_robot=None, far=False):
    wh = [n.id for n in e.env.nodes_of_kind(NodeKind.WAREHOUSE)]
    cu = [n.id for n in e.env.nodes_of_kind(NodeKind.CUSTOMER)]
    if near_robot is not None:
        wh.sort(key=lambda w: e.world.straight_line(near_robot.anchor, w), reverse=far)
    return wh[0], cu[0]


def test_closest_idle_robot_wins_with_explanation(make_engine):
    e = make_engine(robots=4)
    target = e.fleet.robots[2]
    src, dst = _warehouse_and_customer(e, target)
    order = e.create_order(src, dst, Priority.NORMAL)
    evals = {r.id: evaluate(r, order, e.ctx, e.now) for r in e.fleet.robots}
    expected = min((ev for ev in evals.values() if ev.eligible), key=lambda ev: ev.score).robot_id
    e.allocator.allocate(e.ctx, e.fleet.robots, e.now)
    assert order.status == OrderStatus.ASSIGNED
    assert order.assigned_robot == expected
    exp = order.explanation
    assert exp and exp["robot_id"] == expected
    assert set(exp["components"]) == {"travel", "workload", "battery", "deadline"}
    assert abs(sum(exp["components"].values()) - exp["score"]) < 0.5
    assert any("battery" in reason for reason in exp["reasons"])
    assert any("deadline" in reason for reason in exp["reasons"])


def test_ineligible_robots_are_rejected_with_reasons(make_engine):
    e = make_engine(robots=3)
    a, b, c = e.fleet.robots
    a.set_battery_fraction(0.03)
    b.status = RobotStatus.OFFLINE
    b.offline_reason = "test"
    src, dst = _warehouse_and_customer(e)
    order = e.create_order(src, dst, Priority.NORMAL)
    ev_a, ev_b = evaluate(a, order, e.ctx, 0), evaluate(b, order, e.ctx, 0)
    assert not ev_a.eligible and "battery" in ev_a.rejection
    assert not ev_b.eligible and "offline" in ev_b.rejection
    e.allocator.allocate(e.ctx, e.fleet.robots, 0)
    assert order.assigned_robot == c.id


def test_capacity_is_respected_and_no_order_is_double_assigned(make_engine):
    e = make_engine(robots=2)
    src, dst = _warehouse_and_customer(e)
    orders = [e.create_order(src, dst, Priority.NORMAL) for _ in range(12)]
    for _ in range(5):
        e.allocator.allocate(e.ctx, e.fleet.robots, e.now)
    assigned = [o for o in orders if o.status == OrderStatus.ASSIGNED]
    per_robot = Counter(o.assigned_robot for o in assigned)
    for robot in e.fleet.robots:
        assert per_robot[robot.id] <= robot.capacity
        assert len(robot.active_orders) == per_robot[robot.id]
    all_queued = [oid for r in e.fleet.robots for oid in r.active_orders]
    assert len(all_queued) == len(set(all_queued))
    assert all(o.assignment_count == 1 for o in assigned)


def test_critical_orders_are_dispatched_first(make_engine):
    e = make_engine(robots=1)
    src, dst = _warehouse_and_customer(e)
    low = e.create_order(src, dst, Priority.LOW)
    critical = e.create_order(src, dst, Priority.CRITICAL)
    assert e.orders.pending()[0] is critical
    robot = e.fleet.robots[0]
    robot.capacity = 1
    e.allocator.allocate(e.ctx, e.fleet.robots, e.now)
    assert critical.assigned_robot == robot.id
    assert low.status == OrderStatus.PENDING


def test_critical_order_can_preempt_a_low_priority_pickup(make_engine):
    e = make_engine(robots=1)
    robot = e.fleet.robots[0]
    robot.capacity = 1
    src, dst = _warehouse_and_customer(e, robot, far=True)  # a long drive to the pickup
    low = e.create_order(src, dst, Priority.LOW)
    e.allocator.allocate(e.ctx, e.fleet.robots, e.now)
    assert low.assigned_robot == robot.id
    for _ in range(6):  # robot starts driving toward the pickup
        e.step()
    assert robot.status == RobotStatus.EN_ROUTE
    critical = e.create_order(src, dst, Priority.CRITICAL)
    e.allocator.allocate(e.ctx, e.fleet.robots, e.now)
    assert critical.assigned_robot == robot.id
    assert low.status == OrderStatus.PENDING and low.assigned_robot is None
    assert e.allocator.preemptions == 1
    assert any(x.kind == "PREEMPTION" for x in e.timeline.entries)
