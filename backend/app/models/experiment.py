from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.planning.registry import ALGORITHM_KEYS
from app.simulation.scenarios import ScenarioConfig


class ExperimentRequest(BaseModel):
    scenario: str = Field("baseline", description="Preset key used when `config` is omitted")
    config: ScenarioConfig | None = None
    seed: int | None = Field(None, ge=0, le=2_147_483_647)
    algorithms: list[str] = Field(default_factory=lambda: list(ALGORITHM_KEYS), min_length=1)
    repetitions: int = Field(1, ge=1, le=5)
    duration_s: float = Field(1800.0, ge=300.0, le=7200.0)
    name: str | None = Field(None, max_length=120)

    @field_validator("algorithms")
    @classmethod
    def _algorithms(cls, v: list[str]) -> list[str]:
        bad = [a for a in v if a not in ALGORITHM_KEYS]
        if bad:
            raise ValueError(f"unknown algorithm(s) {bad}; choose from {list(ALGORITHM_KEYS)}")
        return list(dict.fromkeys(v))


class TraceRequest(BaseModel):
    algorithm: str | None = Field(None, description="Omit to trace every algorithm on the same query")
    start: int | None = Field(None, ge=0)
    goal: int | None = Field(None, ge=0)
    heuristic: str | None = None
