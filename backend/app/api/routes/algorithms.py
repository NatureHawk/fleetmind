from __future__ import annotations

import random

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_runtime
from app.models.experiment import TraceRequest
from app.planning.heuristics import HEURISTIC_INFO, HEURISTICS
from app.planning.registry import ALGORITHM_CATALOG, ALGORITHM_KEYS, create_planner
from app.services.simulation_service import SimulationRuntime
from app.simulation.environment import NodeKind

router = APIRouter(prefix="/algorithms", tags=["algorithms"])


@router.get("")
async def algorithms(rt: SimulationRuntime = Depends(get_runtime)):
    stats = rt.engine.metrics.algorithm_summary()
    return {
        "active": rt.engine.routes.algorithm,
        "heuristic": rt.engine.routes.heuristic,
        "heuristics": [{"key": k, "description": HEURISTIC_INFO[k]} for k in HEURISTICS],
        "algorithms": [{**ALGORITHM_CATALOG[k], "live": stats.get(k)} for k in ALGORITHM_KEYS],
    }


@router.post("/trace")
async def trace(body: TraceRequest, rt: SimulationRuntime = Depends(get_runtime)):
    """Run traced searches on the fleet's current world model for the Algorithm Explorer.

    Traces do not affect the simulation or its metrics.
    """
    e = rt.engine
    n = len(e.env.nodes)
    for v in (body.start, body.goal):
        if v is not None and not 0 <= v < n:
            raise HTTPException(404, f"node {v} not found")
    if body.algorithm is not None and body.algorithm not in ALGORITHM_KEYS:
        raise HTTPException(422, f"algorithm must be one of {list(ALGORITHM_KEYS)}")
    heuristic = body.heuristic or e.routes.heuristic
    if heuristic not in HEURISTICS:
        raise HTTPException(422, f"heuristic must be one of {sorted(HEURISTICS)}")

    rng = random.Random()
    start = body.start if body.start is not None else rng.choice([x.id for x in e.env.nodes_of_kind(NodeKind.WAREHOUSE)])
    if body.goal is not None:
        goal = body.goal
    else:
        customers = [x.id for x in e.env.nodes_of_kind(NodeKind.CUSTOMER)]
        customers.sort(key=lambda c: -e.world.straight_line(start, c))
        goal = rng.choice(customers[: max(3, len(customers) // 3)])

    keys = [body.algorithm] if body.algorithm else list(ALGORITHM_KEYS)
    results = []
    for key in keys:
        res = create_planner(key, heuristic).find_path(e.world, start, goal, trace=True)
        data = res.as_dict()
        data["name"] = ALGORITHM_CATALOG[key]["short"]
        data["trace"] = [[node, added] for node, added in res.trace.steps] if res.trace else []
        frontier_left = set()
        for node, added in data["trace"]:
            frontier_left.discard(node)
            frontier_left.update(added)
        data["final_frontier"] = sorted(frontier_left)
        results.append(data)
    return {"start": start, "goal": goal, "start_name": e.env.nodes[start].name, "goal_name": e.env.nodes[goal].name,
            "heuristic": heuristic, "world_version": e.world.version, "t": e.now, "results": results}
