from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.simulation.scenarios import ScenarioConfig


class ResetRequest(BaseModel):
    scenario: str | None = Field(None, description="Preset key; omit to keep the current scenario")
    seed: int | None = Field(None, ge=0, le=2_147_483_647)
    algorithm: str | None = None
    heuristic: str | None = None
    config: ScenarioConfig | None = Field(None, description="Full custom configuration (scenario builder)")


class SpeedRequest(BaseModel):
    speed: float


class StepRequest(BaseModel):
    ticks: int = Field(1, ge=1, le=2000)


class AlgorithmRequest(BaseModel):
    algorithm: str
    heuristic: str | None = None


class SimulationStatus(BaseModel):
    running: bool
    speed: float
    speeds: list[float]
    t: float
    tick: int
    tick_seconds: float
    sim_seconds_per_second_at_1x: float
    scenario: dict[str, Any]
    algorithm: str
    heuristic: str
    run_id: str | None
    version: int
    fingerprints: dict[str, str]
    clients: int
