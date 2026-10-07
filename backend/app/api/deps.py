"""Dependency providers (the services are created once in the app lifespan)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.db.repository import Repository
from app.services.experiment_service import ExperimentService
from app.services.simulation_service import SimulationRuntime


def get_runtime(request: Request) -> SimulationRuntime:
    return request.app.state.runtime


def get_experiments(request: Request) -> ExperimentService:
    return request.app.state.experiments


def get_repository(request: Request) -> Repository:
    repo = request.app.state.repo
    if repo is None:
        raise HTTPException(503, "persistence is disabled — no database is available")
    return repo
