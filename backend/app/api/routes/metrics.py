from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime
from app.services.simulation_service import SimulationRuntime

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def metrics(rt: SimulationRuntime = Depends(get_runtime)):
    """Global, per-algorithm and per-robot metrics for the current run, plus its time series."""
    e = rt.engine
    return {
        "global": e.metrics.global_summary(e),
        "algorithms": e.metrics.algorithm_summary(),
        "robots": e.metrics.robot_metrics(e),
        "timeseries": e.metrics.samples,
        "recent_plans": list(e.metrics.recent_plans),
        "scenario": e.config.model_dump(),
    }
