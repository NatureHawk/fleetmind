"""Battery and energy model.

    energy_used (Wh) = distance (m) × robot_energy_rate (Wh/m) × traffic_energy_factor

Robots plan with *estimates* (straight-line distance × detour factor) when choosing tasks
and chargers, and with the *exact* energy of a planned route before committing to it. The
ground-truth drain happens in the movement step, so a robot that runs out of charge really
stops — nothing completes a route on credit.
"""

from __future__ import annotations

from app.simulation.environment import TRAFFIC_ENERGY_FACTOR, TrafficLevel

MIN_RESERVE_FRACTION = 0.06      # never plan to arrive anywhere below this
LOW_BATTERY_FRACTION = 0.20      # warning threshold
IDLE_CHARGE_FRACTION = 0.35      # idle robots below this go and charge proactively
CHARGE_TARGET_FRACTION = 0.95    # charge until this level
CHARGE_RESUME_FRACTION = 0.80    # a charging robot may leave early for work above this
ESTIMATE_DETOUR = 1.4            # mean network distance ≈ 1.43 × straight-line distance (measured)
ESTIMATE_SAFETY = 1.25           # margin so estimates cover ~90 % of routes; the planner verifies the rest
CHARGE_POWER_WH_PER_S = 3.6
FIELD_SERVICE_DELAY_S = 480.0    # a depleted robot gets a field battery swap after this
FIELD_SERVICE_CHARGE = 0.30


def movement_energy(distance_m: float, rate_wh_per_m: float, traffic: TrafficLevel) -> float:
    return distance_m * rate_wh_per_m * TRAFFIC_ENERGY_FACTOR[traffic]


def estimate_energy(straight_line_m: float, rate_wh_per_m: float) -> float:
    return straight_line_m * ESTIMATE_DETOUR * rate_wh_per_m * ESTIMATE_SAFETY


def pct(value_wh: float, max_wh: float) -> float:
    return 100.0 * value_wh / max_wh if max_wh else 0.0
