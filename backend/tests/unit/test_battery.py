from __future__ import annotations

import pytest

from app.agents.battery import CHARGE_POWER_WH_PER_S, movement_energy
from app.agents.robot import RobotStatus
from app.simulation.environment import TRAFFIC_ENERGY_FACTOR, NodeKind, TrafficLevel
from app.simulation.orders import OrderStatus, Priority


def test_energy_formula():
    assert movement_energy(1000, 0.04, TrafficLevel.LOW) == pytest.approx(40.0)
    assert movement_energy(1000, 0.04, TrafficLevel.JAMMED) == pytest.approx(40.0 * TRAFFIC_ENERGY_FACTOR[TrafficLevel.JAMMED])
    assert TRAFFIC_ENERGY_FACTOR[TrafficLevel.JAMMED] > TRAFFIC_ENERGY_FACTOR[TrafficLevel.LOW]


def test_driving_drains_exactly_distance_times_rate(make_engine):
    e = make_engine(robots=1)
    r = e.fleet.robots[0]
    start_wh = r.battery_wh
    customers = [n.id for n in e.env.nodes if n.kind.value == "customer"]
    e.create_order(e.env.nodes_of_kind(NodeKind.WAREHOUSE)[0].id, customers[0], Priority.NORMAL)
    e.run_until(150)
    assert r.total_distance > 0
    # No traffic in a quiet scenario: every metre costs exactly energy_rate.
    assert r.energy_consumed == pytest.approx(r.total_distance * r.energy_rate, rel=1e-6)
    assert r.battery_wh == pytest.approx(start_wh - r.energy_consumed, rel=1e-6)


def test_charging_adds_energy_at_station_power(make_engine):
    e = make_engine(robots=1, battery_min=0.3, battery_max=0.3)
    r = e.fleet.robots[0]
    e.run_until(1200)  # idle below 35% → proactively charges
    assert r.charge_sessions >= 1
    assert r.energy_charged > 0
    assert r.battery_fraction > 0.3
    # Charging power is respected: energy charged never exceeds power × time spent charging.
    assert r.energy_charged <= CHARGE_POWER_WH_PER_S * r.charging_time + 1e-6


def test_depleted_robot_stops_and_fails_its_parcel(make_engine):
    e = make_engine(robots=1)
    r = e.fleet.robots[0]
    wh = [n.id for n in e.env.nodes if n.kind.value == "warehouse"][0]
    far = max((n.id for n in e.env.nodes if n.kind.value == "customer"), key=lambda c: e.world.straight_line(wh, c))
    order = e.create_order(wh, far, Priority.NORMAL)
    # Run until the parcel is on board, then sabotage the battery (bypassing the planner's safety checks).
    while order.status.value != "IN_TRANSIT" and e.now < 3000:
        e.step()
    assert order.status.value == "IN_TRANSIT"
    r.battery_wh = 0.5
    r.low_battery_mode = True  # suppress diversion: we want to observe a hard depletion
    for _ in range(200):
        e.step()
        if r.status == RobotStatus.OFFLINE:
            break
    assert r.status == RobotStatus.OFFLINE
    assert r.depletions == 1
    assert r.battery_wh == 0.0
    assert order.status.value == "FAILED"


def test_robot_refuses_leg_it_cannot_finish_and_charges_first(make_engine):
    e = make_engine(robots=1, battery_min=0.12, battery_max=0.12)
    r = e.fleet.robots[0]
    wh = [n.id for n in e.env.nodes if n.kind.value == "warehouse"]
    far = max((n.id for n in e.env.nodes if n.kind.value == "customer"),
              key=lambda c: e.world.straight_line(wh[0], c))
    # The allocator would reject this robot; assign directly to exercise the agent's own check.
    order = e.create_order(wh[0], far, Priority.NORMAL)
    r.assign(order, e.ctx)
    order.status = OrderStatus.ASSIGNED
    order.assigned_robot = r.id
    for _ in range(20):
        e.step()
    assert r.heading_to_charger() or r.status == RobotStatus.CHARGING
    assert any(k == "CHARGE_DIVERSION" for k in (x.kind for x in e.timeline.entries))
