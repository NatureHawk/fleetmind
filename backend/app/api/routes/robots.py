from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_runtime
from app.services.simulation_service import SimulationRuntime
from app.simulation.snapshot import robot_detail

router = APIRouter(prefix="/robots", tags=["robots"])


@router.get("")
async def robots(rt: SimulationRuntime = Depends(get_runtime)):
    return rt.engine.metrics.robot_metrics(rt.engine)


@router.get("/{robot_id}")
async def robot(robot_id: str, rt: SimulationRuntime = Depends(get_runtime)):
    data = robot_detail(rt.engine, robot_id)
    if data is None:
        raise HTTPException(404, f"robot {robot_id} not found")
    data["timeline"] = [e.as_dict() for e in rt.engine.timeline.query(robot_id=robot_id, limit=80)]
    return data
