from __future__ import annotations

from app.agents.robot import RobotStatus
from app.simulation.environment import NodeKind, TrafficLevel
from app.simulation.events import EventSource, EventType, ScheduledEvent, is_bridge
from app.simulation.orders import Priority


def _drive_long_route(e):
    robot = e.fleet.robots[0]
    wh = min((n.id for n in e.env.nodes_of_kind(NodeKind.WAREHOUSE)),
             key=lambda w: e.world.straight_line(robot.anchor, w))
    far = max((n.id for n in e.env.nodes_of_kind(NodeKind.CUSTOMER)), key=lambda c: e.world.straight_line(wh, c))
    order = e.create_order(wh, far, Priority.NORMAL)
    while order.status.value != "IN_TRANSIT" and e.now < 3000:
        e.step()
    while robot.status != RobotStatus.EN_ROUTE and e.now < 3000:
        e.step()
    assert robot.status == RobotStatus.EN_ROUTE and len(robot.remaining_roads()) >= 5
    return robot, order


def _closable_road_ahead(e, robot, offset=3):
    for rid in robot.remaining_roads()[offset:]:
        if not is_bridge(e.env, rid, set()):
            return rid
    raise AssertionError("no closable road ahead")


def test_operator_closure_invalidates_route_and_robot_avoids_it(make_engine):
    e = make_engine(robots=1)
    robot, order = _drive_long_route(e)
    road = _closable_road_ahead(e, robot)
    replans_before = robot.replans
    e.inject_event(EventType.ROAD_BLOCKED, {"road_id": road})
    assert e.world.is_blocked(road)  # operator closures are announced immediately
    for _ in range(12):
        e.step()
    assert robot.replans == replans_before + 1
    assert road not in robot.remaining_roads()
    kinds = [x.kind for x in e.timeline.entries]
    assert "BROADCAST_BLOCKED" in kinds and "REPLAN_TRIGGERED" in kinds and "ROUTE_REPLANNED" in kinds
    e.run_until(e.now + 1500)
    assert order.status.value == "DELIVERED"


def test_hidden_closure_is_perceived_reported_and_avoided(make_engine):
    e = make_engine(robots=1)
    robot, order = _drive_long_route(e)
    road = _closable_road_ahead(e, robot)
    e.processor.apply(ScheduledEvent(e.now, -1, EventType.ROAD_BLOCKED, {"road_id": road}, EventSource.SCENARIO))
    assert e.env.roads[road].blocked and not e.world.is_blocked(road)  # truth ≠ belief
    while not e.world.is_blocked(road) and e.now < 3000:
        e.step()
    detected = [x for x in e.timeline.entries if x.kind == "CLOSURE_DETECTED"]
    assert detected and detected[0].robot_id == robot.id
    for _ in range(12):
        e.step()
    assert road not in robot.remaining_roads()
    e.run_until(e.now + 1500)
    assert order.status.value == "DELIVERED"
    assert robot.total_distance > 0


def test_closure_reported_by_one_robot_updates_everyone(make_engine):
    e = make_engine(robots=3)
    road = 10
    reporter = e.fleet.robots[0]
    assert e.channel.report_road_blocked(reporter.id, road)
    assert not e.channel.report_road_blocked(e.fleet.robots[1].id, road)  # duplicate reports absorbed
    entry = [x for x in e.timeline.entries if x.kind == "BROADCAST_BLOCKED"][-1]
    assert entry.data["listeners"] == 3


def test_congestion_triggers_reevaluation(make_engine):
    e = make_engine(robots=1)
    robot, _ = _drive_long_route(e)
    ahead = robot.remaining_roads()[1:5]
    plans_before = robot.plans
    e.inject_event(EventType.TRAFFIC_INCREASE, {"road_ids": ahead, "level": "JAMMED"})
    for _ in range(3):
        e.step()
    assert robot.plans == plans_before + 1  # re-evaluated with the planner
    kinds = [x.kind for x in e.timeline.entries]
    assert "ROUTE_SWITCHED" in kinds or "ROUTE_KEPT" in kinds
    assert all(e.world.known_traffic[r] == TrafficLevel.JAMMED for r in ahead)


def test_low_battery_event_diverts_to_charger_then_resumes(make_engine):
    e = make_engine(robots=1)
    robot, order = _drive_long_route(e)
    e.inject_event(EventType.ROBOT_LOW_BATTERY, {"robot_id": robot.id, "level": 0.1})
    for _ in range(10):
        e.step()
    assert robot.heading_to_charger()
    e.run_until(e.now + 3000)
    assert robot.charge_sessions >= 1
    assert order.status.value == "DELIVERED"
