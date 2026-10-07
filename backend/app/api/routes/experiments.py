from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_experiments
from app.models.experiment import ExperimentRequest
from app.services.experiment_service import ExperimentService
from app.simulation.scenarios import get_scenario

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("/run", status_code=202)
async def run(body: ExperimentRequest, svc: ExperimentService = Depends(get_experiments)):
    """Run the same scenario once per algorithm (× repetitions) under identical conditions."""
    if body.config is not None:
        scenario = body.config
    else:
        try:
            scenario = get_scenario(body.scenario)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
    if body.seed is not None:
        scenario = scenario.model_copy(update={"seed": body.seed})
    job = await svc.launch(scenario, body.algorithms, body.repetitions, body.duration_s, body.name)
    return job.as_dict(include_results=False)


@router.get("")
async def list_experiments(svc: ExperimentService = Depends(get_experiments)):
    return await svc.list()


@router.get("/{experiment_id}")
async def get_experiment(experiment_id: str, svc: ExperimentService = Depends(get_experiments)):
    data = await svc.get(experiment_id)
    if data is None:
        raise HTTPException(404, f"experiment {experiment_id} not found")
    return data


@router.delete("/{experiment_id}", status_code=204)
async def delete_experiment(experiment_id: str, svc: ExperimentService = Depends(get_experiments)):
    if not await svc.delete(experiment_id):
        raise HTTPException(404, f"experiment {experiment_id} not found")
