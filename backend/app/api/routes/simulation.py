from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.api.deps import get_runtime
from app.models.simulation import AlgorithmRequest, ResetRequest, SimulationStatus, SpeedRequest, StepRequest
from app.planning.heuristics import HEURISTICS
from app.planning.registry import ALGORITHM_KEYS
from app.services.simulation_service import SimulationRuntime
from app.simulation.scenarios import get_scenario
from app.simulation.snapshot import live_snapshot

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/status", response_model=SimulationStatus)
async def status(rt: SimulationRuntime = Depends(get_runtime)):
    return rt.status()


@router.get("/state")
async def state(rt: SimulationRuntime = Depends(get_runtime)):
    """Full current state (the same payload the WebSocket streams, with the whole recent timeline)."""
    return {"status": rt.status(), "snapshot": live_snapshot(rt.engine, 0, running=rt.running, speed=rt.speed)}


@router.post("/start", response_model=SimulationStatus)
async def start(rt: SimulationRuntime = Depends(get_runtime)):
    await rt.start()
    return rt.status()


@router.post("/resume", response_model=SimulationStatus)
async def resume(rt: SimulationRuntime = Depends(get_runtime)):
    await rt.start()
    return rt.status()


@router.post("/pause", response_model=SimulationStatus)
async def pause(rt: SimulationRuntime = Depends(get_runtime)):
    rt.pause()
    return rt.status()


@router.post("/step", response_model=SimulationStatus)
async def step(body: StepRequest, rt: SimulationRuntime = Depends(get_runtime)):
    if rt.running:
        raise HTTPException(409, "pause the simulation before stepping")
    await rt.step(body.ticks)
    rt.broadcast()
    return rt.status()


@router.post("/reset", response_model=SimulationStatus)
async def reset(body: ResetRequest, rt: SimulationRuntime = Depends(get_runtime)):
    current = rt.engine.config
    try:
        if body.config is not None:
            config = body.config
        elif body.scenario is not None:
            config = get_scenario(body.scenario, seed=body.seed if body.seed is not None else current.seed,
                                  algorithm=body.algorithm or current.algorithm,
                                  heuristic=body.heuristic or current.heuristic)
        else:
            updates = {k: v for k, v in {"seed": body.seed, "algorithm": body.algorithm,
                                         "heuristic": body.heuristic}.items() if v is not None}
            config = current.model_validate({**current.model_dump(), **updates})
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    await rt.reset(config)
    rt.broadcast()
    return rt.status()


@router.post("/speed", response_model=SimulationStatus)
async def speed(body: SpeedRequest, rt: SimulationRuntime = Depends(get_runtime)):
    try:
        rt.set_speed(body.speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return rt.status()


@router.post("/algorithm", response_model=SimulationStatus)
async def algorithm(body: AlgorithmRequest, rt: SimulationRuntime = Depends(get_runtime)):
    if body.algorithm not in ALGORITHM_KEYS:
        raise HTTPException(422, f"algorithm must be one of {list(ALGORITHM_KEYS)}")
    if body.heuristic is not None and body.heuristic not in HEURISTICS:
        raise HTTPException(422, f"heuristic must be one of {sorted(HEURISTICS)}")
    rt.engine.set_algorithm(body.algorithm, body.heuristic)
    return rt.status()
