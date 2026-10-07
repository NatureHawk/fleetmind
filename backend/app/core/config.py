"""Application settings, loaded from environment variables (prefix ``FLEETMIND_``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLEETMIND_", env_file=".env", extra="ignore")

    # Persistence ------------------------------------------------------------------
    database_url: str = "postgresql+psycopg://fleetmind:fleetmind@localhost:5432/fleetmind"
    # Used only when the primary database is unreachable. Set to an empty string to
    # disable the fallback and run without persistence instead.
    database_fallback_url: str = "sqlite:///./fleetmind.db"
    persist_live_runs: bool = True

    # Simulation runtime -----------------------------------------------------------
    # Simulated seconds advanced per fixed tick. Core logic only ever sees this value,
    # never the wall clock, which is what keeps runs deterministic.
    tick_seconds: float = 0.5
    # Ticks per wall-clock second at 1x speed (1x = 8 simulated seconds per second).
    base_ticks_per_second: float = 16.0
    broadcast_hz: float = 15.0
    default_scenario: str = "demo"
    default_seed: int = 42173

    # Experiments ------------------------------------------------------------------
    experiment_workers: int = Field(default=4, ge=0, le=16)

    # HTTP -------------------------------------------------------------------------
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
