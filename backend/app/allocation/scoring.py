"""Transparent candidate scoring for task allocation.

Lower score is better. Every score is a sum of named components measured in seconds, so
an assignment can always be explained term by term:

    score = travel        estimated time until the robot reaches the pickup
                          (finishing its queued work first, then driving there)
          + workload      90 s per order already queued on the robot (spreads work)
          + battery       6 s per percentage point the robot would end below 40 %
          + deadline      3 s per second the delivery is estimated to be late

Hard constraints (offline, at capacity, charging below 80 %, returning to charge, or not
enough energy for the job plus a reserve to reach a charger) make a robot ineligible.

Estimates use straight-line distance × a detour factor. The allocator deliberately does
*not* run the route planner for every robot/order pair: allocation must stay cheap and
independent of the search algorithm under test. The chosen robot then plans the actual
route with the configured algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.battery import (
    CHARGE_POWER_WH_PER_S,
    CHARGE_RESUME_FRACTION,
    ESTIMATE_DETOUR,
    MIN_RESERVE_FRACTION,
    estimate_energy,
    pct,
)
from app.agents.context import AgentContext
from app.agents.robot import DROPOFF_DWELL_S, PICKUP_DWELL_S, RobotAgent, RobotStatus, StopKind
from app.simulation.orders import Order

WORKLOAD_PENALTY_S = 90.0
BATTERY_COMFORT_PCT = 40.0
BATTERY_PENALTY_PER_PCT = 6.0
LATENESS_PENALTY_FACTOR = 3.0


@dataclass(slots=True)
class Commitment:
    """Where and when a robot becomes free, and the energy its queued work will use."""

    end_node: int
    busy_s: float
    energy_wh: float
    queued_orders: int


def robot_commitment(robot: RobotAgent, ctx: AgentContext) -> Commitment:
    world = ctx.world
    t = 0.0
    energy = 0.0
    pos = robot.anchor
    if robot.status in (RobotStatus.LOADING, RobotStatus.DELIVERING):
        t += max(robot.timer, 0.0)
    if robot.path and robot.stops and robot.path[-1] == robot.stops[0].node:
        roads = robot.remaining_roads()
        t += sum(world.road_cost(r) for r in roads) / robot.speed_ratio
        energy += world.roads_energy(roads, robot.energy_rate)
        pos = robot.path[-1]
        legs = robot.stops
        first_done = True
    else:
        legs = robot.stops
        first_done = False
    for i, stop in enumerate(legs):
        if not (i == 0 and first_done):
            d = world.straight_line(pos, stop.node)
            t += d * ESTIMATE_DETOUR / robot.speed_mps
            energy += estimate_energy(d, robot.energy_rate)
            pos = stop.node
        if stop.kind == StopKind.PICKUP:
            t += PICKUP_DWELL_S
        elif stop.kind == StopKind.DROPOFF:
            t += DROPOFF_DWELL_S
        else:
            t += max(0.0, robot.max_battery_wh * 0.95 - robot.battery_wh) / CHARGE_POWER_WH_PER_S
    return Commitment(pos, t, energy, len(robot.active_orders))


@dataclass(slots=True)
class CandidateEvaluation:
    robot_id: str
    eligible: bool
    rejection: str | None = None
    score: float = float("inf")
    components: dict[str, float] = field(default_factory=dict)
    pickup_eta: float = 0.0
    delivery_eta: float = 0.0
    lateness: float = 0.0
    battery_now_pct: float = 0.0
    battery_after_pct: float = 0.0
    queued_orders: int = 0
    idle: bool = False

    def as_dict(self) -> dict:
        return {
            "robot_id": self.robot_id,
            "eligible": self.eligible,
            "rejection": self.rejection,
            "score": None if not self.eligible else round(self.score, 1),
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "pickup_eta": round(self.pickup_eta, 1),
            "delivery_eta": round(self.delivery_eta, 1),
            "lateness": round(self.lateness, 1),
            "battery_now_pct": round(self.battery_now_pct, 1),
            "battery_after_pct": round(self.battery_after_pct, 1),
            "queued_orders": self.queued_orders,
        }


def eligibility(robot: RobotAgent) -> str | None:
    if robot.status == RobotStatus.OFFLINE:
        return f"offline ({robot.offline_reason})"
    if robot.low_battery_mode or robot.heading_to_charger():
        if robot.status == RobotStatus.CHARGING and robot.battery_fraction >= CHARGE_RESUME_FRACTION:
            return None
        return f"recharging (battery {robot.battery_pct:.0f}%)"
    if len(robot.active_orders) >= robot.capacity:
        return f"at capacity ({len(robot.active_orders)}/{robot.capacity})"
    return None


def evaluate(robot: RobotAgent, order: Order, ctx: AgentContext, now: float,
             commitment: Commitment | None = None) -> CandidateEvaluation:
    rejection = eligibility(robot)
    if rejection:
        return CandidateEvaluation(robot.id, False, rejection, battery_now_pct=robot.battery_pct)

    c = commitment or robot_commitment(robot, ctx)
    world = ctx.world
    d_pickup = world.straight_line(c.end_node, order.source)
    d_deliver = world.straight_line(order.source, order.destination)
    to_pickup = d_pickup * ESTIMATE_DETOUR / robot.speed_mps
    deliver_leg = d_deliver * ESTIMATE_DETOUR / robot.speed_mps
    pickup_eta = c.busy_s + to_pickup
    delivery_eta = pickup_eta + PICKUP_DWELL_S + deliver_leg + DROPOFF_DWELL_S

    job_energy = estimate_energy(d_pickup, robot.energy_rate) + estimate_energy(d_deliver, robot.energy_rate)
    reserve = ctx.charging.reserve_energy(order.destination, robot.energy_rate)
    floor = robot.max_battery_wh * MIN_RESERVE_FRACTION
    after = robot.battery_wh - c.energy_wh - job_energy
    if after - reserve < floor:
        need = pct(c.energy_wh + job_energy + reserve + floor, robot.max_battery_wh)
        return CandidateEvaluation(robot.id, False,
                                   f"insufficient battery (job needs ≈{need:.0f}%, has {robot.battery_pct:.0f}%)",
                                   battery_now_pct=robot.battery_pct)

    after_pct = pct(after, robot.max_battery_wh)
    lateness = max(0.0, now + delivery_eta - order.deadline)
    components = {
        "travel": pickup_eta,
        "workload": WORKLOAD_PENALTY_S * c.queued_orders,
        "battery": max(0.0, BATTERY_COMFORT_PCT - after_pct) * BATTERY_PENALTY_PER_PCT,
        "deadline": lateness * LATENESS_PENALTY_FACTOR,
    }
    return CandidateEvaluation(
        robot.id, True, None, sum(components.values()), components, pickup_eta, delivery_eta, lateness,
        robot.battery_pct, after_pct, c.queued_orders,
        idle=robot.status == RobotStatus.IDLE and not robot.stops,
    )
