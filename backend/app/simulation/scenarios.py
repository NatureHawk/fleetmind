"""Scenario definitions and presets.

A scenario fully determines a run together with its seed: city, fleet, order stream and
incident timeline. ``ScenarioConfig`` doubles as the validated payload of the scenario
builder in the UI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.planning.heuristics import HEURISTICS
from app.planning.registry import ALGORITHM_KEYS


class ScenarioConfig(BaseModel):
    key: str = "custom"
    name: str = "Custom scenario"
    description: str = ""
    purpose: str = ""

    seed: int = Field(42173, ge=0, le=2_147_483_647)
    algorithm: str = "astar"
    heuristic: str = "euclidean"

    robots: int = Field(14, ge=1, le=60)
    initial_orders: int = Field(10, ge=0, le=500)
    max_orders: int = Field(400, ge=0, le=1000, description="Total delivery requests that will be generated")
    order_rate_per_min: float = Field(2.0, ge=0.0, le=60.0)
    priority_weights: dict[str, float] = Field(
        default_factory=lambda: {"LOW": 0.2, "NORMAL": 0.55, "HIGH": 0.2, "CRITICAL": 0.05})

    traffic_intensity: float = Field(0.06, ge=0.0, le=0.8, description="Share of roads congested at start")
    congestion_events: int = Field(0, ge=0, le=40)
    closure_events: int = Field(0, ge=0, le=40)
    road_failure_probability: float = Field(0.0, ge=0.0, le=1.0,
                                            description="Per-minute probability of an extra random closure")
    robot_failures: int = Field(0, ge=0, le=20)

    battery_min: float = Field(0.55, ge=0.05, le=1.0)
    battery_max: float = Field(1.0, ge=0.05, le=1.0)
    low_battery_robots: int = Field(0, ge=0, le=60)

    duration_s: float = Field(1800.0, ge=120.0, le=14_400.0,
                              description="Incident window and experiment horizon (simulated seconds)")
    speed: float = Field(1.0, ge=0.25, le=16.0)
    preemption: bool = True
    demo: bool = False

    @field_validator("algorithm")
    @classmethod
    def _algorithm(cls, v: str) -> str:
        if v not in ALGORITHM_KEYS:
            raise ValueError(f"algorithm must be one of {list(ALGORITHM_KEYS)}")
        return v

    @field_validator("heuristic")
    @classmethod
    def _heuristic(cls, v: str) -> str:
        if v not in HEURISTICS:
            raise ValueError(f"heuristic must be one of {sorted(HEURISTICS)}")
        return v

    @field_validator("priority_weights")
    @classmethod
    def _weights(cls, v: dict[str, float]) -> dict[str, float]:
        allowed = {"LOW", "NORMAL", "HIGH", "CRITICAL"}
        if not set(v) <= allowed:
            raise ValueError(f"priority keys must be within {sorted(allowed)}")
        if any(w < 0 for w in v.values()) or sum(v.values()) <= 0:
            raise ValueError("priority weights must be non-negative and not all zero")
        return {k: float(v.get(k, 0.0)) for k in ("LOW", "NORMAL", "HIGH", "CRITICAL")}

    @model_validator(mode="after")
    def _ranges(self) -> ScenarioConfig:
        if self.battery_min > self.battery_max:
            raise ValueError("battery_min must not exceed battery_max")
        if self.low_battery_robots > self.robots:
            raise ValueError("low_battery_robots cannot exceed robots")
        return self


_PRESETS: dict[str, dict] = {
    "demo": {
        "name": "Guided demo",
        "description": "A scripted seven-phase story: normal operations, congestion, a hidden road closure, "
                       "replanning, a battery emergency, a CRITICAL order and a final report.",
        "purpose": "Presentation: shows perception, coordination, replanning and explainable allocation.",
        "robots": 12, "initial_orders": 9, "order_rate_per_min": 1.3, "traffic_intensity": 0.05,
        "battery_min": 0.5, "battery_max": 0.95, "demo": True, "duration_s": 900.0,
    },
    "baseline": {
        "name": "Baseline",
        "description": "Normal traffic, no closures, stable fleet.",
        "purpose": "Compare the basic behaviour of the search algorithms.",
        "robots": 15, "initial_orders": 12, "order_rate_per_min": 1.7, "traffic_intensity": 0.04,
    },
    "congestion": {
        "name": "Congestion",
        "description": "A quarter of the network starts congested and traffic waves roll through major corridors.",
        "purpose": "Evaluate weighted, traffic-aware path planning.",
        "robots": 15, "initial_orders": 12, "order_rate_per_min": 1.7, "traffic_intensity": 0.25,
        "congestion_events": 10,
    },
    "road_closure": {
        "name": "Road closure",
        "description": "Roads close without warning during the run and reopen later. Robots must discover them.",
        "purpose": "Test perception, fleet communication and dynamic replanning.",
        "robots": 15, "initial_orders": 12, "order_rate_per_min": 1.7, "traffic_intensity": 0.06,
        "closure_events": 9, "road_failure_probability": 0.08,
    },
    "battery_critical": {
        "name": "Battery critical",
        "description": "Six robots start between 14 % and 26 % charge; the rest are only partly charged.",
        "purpose": "Test battery-aware planning, charger selection and charging-station queues.",
        "robots": 14, "initial_orders": 12, "order_rate_per_min": 1.6, "battery_min": 0.35, "battery_max": 0.7,
        "low_battery_robots": 6,
    },
    "surge": {
        "name": "Surge",
        "description": "A large initial backlog and a high arrival rate across 25 robots, with occasional faults.",
        "purpose": "Test multi-agent allocation and scalability.",
        "robots": 25, "initial_orders": 40, "max_orders": 450, "order_rate_per_min": 7.5,
        "traffic_intensity": 0.1, "congestion_events": 4, "closure_events": 3, "robot_failures": 2,
        "priority_weights": {"LOW": 0.15, "NORMAL": 0.5, "HIGH": 0.25, "CRITICAL": 0.1},
    },
}

SCENARIO_ORDER = ["demo", "baseline", "congestion", "road_closure", "battery_critical", "surge"]


def get_scenario(key: str, **overrides) -> ScenarioConfig:
    if key not in _PRESETS:
        raise KeyError(f"unknown scenario '{key}'; choose from {SCENARIO_ORDER}")
    data = {"key": key, **_PRESETS[key], **{k: v for k, v in overrides.items() if v is not None}}
    return ScenarioConfig(**data)


def list_scenarios() -> list[ScenarioConfig]:
    return [get_scenario(k) for k in SCENARIO_ORDER]
