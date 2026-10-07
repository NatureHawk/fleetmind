from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.simulation.scenarios import ScenarioConfig, get_scenario, list_scenarios

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("")
async def scenarios():
    return [s.model_dump() for s in list_scenarios()]


@router.get("/schema")
async def schema():
    """JSON schema of the scenario builder (field limits and descriptions)."""
    return ScenarioConfig.model_json_schema()


@router.get("/{key}")
async def scenario(key: str):
    try:
        return get_scenario(key).model_dump()
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc
