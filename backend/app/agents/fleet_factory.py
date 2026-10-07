"""Deterministic creation of a heterogeneous robot fleet."""

from __future__ import annotations

import random

from app.agents.robot import RobotAgent, RobotModel
from app.simulation.environment import REFERENCE_SPEED_MPS, Environment, NodeKind

ROBOT_MODELS: dict[str, RobotModel] = {
    "courier-s": RobotModel("courier-s", "Courier S", speed_factor=1.18, capacity=1, battery_wh=520.0,
                            energy_rate=0.032),
    "courier-m": RobotModel("courier-m", "Courier M", speed_factor=1.0, capacity=2, battery_wh=680.0,
                            energy_rate=0.038),
    "hauler-l": RobotModel("hauler-l", "Hauler L", speed_factor=0.84, capacity=3, battery_wh=900.0,
                           energy_rate=0.047),
}
MODEL_MIX = (("courier-s", 0.35), ("courier-m", 0.45), ("hauler-l", 0.20))


def create_fleet(env: Environment, rng: random.Random, count: int, battery_range: tuple[float, float],
                 low_battery_count: int = 0, low_battery_range: tuple[float, float] = (0.14, 0.26)) -> list[RobotAgent]:
    warehouses = [n.id for n in env.nodes_of_kind(NodeKind.WAREHOUSE)]
    chargers = [n.id for n in env.nodes_of_kind(NodeKind.CHARGER)]
    intersections = [n.id for n in env.nodes_of_kind(NodeKind.INTERSECTION) if env.degree(n.id) >= 3]
    keys = [k for k, _ in MODEL_MIX]
    weights = [w for _, w in MODEL_MIX]

    low_ids = set(rng.sample(range(count), min(low_battery_count, count)))
    robots: list[RobotAgent] = []
    for i in range(count):
        model = ROBOT_MODELS[rng.choices(keys, weights=weights, k=1)[0]]
        pool = (warehouses, chargers, intersections)[i % 3] or intersections
        node = pool[(i // 3) % len(pool)] if i % 3 != 2 else rng.choice(pool)
        lo, hi = low_battery_range if i in low_ids else battery_range
        fraction = rng.uniform(lo, hi)
        max_wh = model.battery_wh * rng.uniform(0.96, 1.04)
        robots.append(RobotAgent(
            f"R-{i + 1:02d}", model, node, env,
            speed_mps=REFERENCE_SPEED_MPS * model.speed_factor * rng.uniform(0.96, 1.04),
            energy_rate=model.energy_rate * rng.uniform(0.95, 1.05),
            max_battery_wh=round(max_wh, 1),
            battery_wh=round(max_wh * fraction, 1),
            capacity=model.capacity,
        ))
    return robots
