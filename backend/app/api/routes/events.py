from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_runtime
from app.models.events import EventRequest
from app.services.simulation_service import SimulationRuntime
from app.simulation.events import EVENT_DESCRIPTIONS, EventType

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", status_code=201)
async def inject(body: EventRequest, rt: SimulationRuntime = Depends(get_runtime)):
    """Inject an operator event; it is applied immediately and recorded in the timeline."""
    params = body.model_dump(exclude={"type"}, exclude_none=True)
    before = rt.engine.timeline.last_seq
    try:
        ev = rt.engine.inject_event(body.type, params)
    except LookupError as exc:
        raise HTTPException(404, str(exc.args[0] if exc.args else exc)) from exc
    except (ValueError, IndexError) as exc:
        raise HTTPException(422, str(exc)) from exc
    rt.broadcast()
    return {"event": ev.as_dict(), "timeline": [e.as_dict() for e in rt.engine.timeline.since(before)]}


@router.get("")
async def timeline(since: int = Query(0, ge=0), robot_id: str | None = None, order_id: str | None = None,
                   category: str | None = None, kind: str | None = None, limit: int = Query(200, ge=1, le=2000),
                   rt: SimulationRuntime = Depends(get_runtime)):
    entries = rt.engine.timeline.query(robot_id=robot_id, order_id=order_id, category=category, kind=kind,
                                       limit=limit)
    return [e.as_dict() for e in entries if e.seq > since]


@router.get("/types")
async def event_types():
    return [{"type": t.value, "description": EVENT_DESCRIPTIONS[t]} for t in EventType]


@router.get("/scheduled")
async def scheduled(rt: SimulationRuntime = Depends(get_runtime)):
    """Upcoming scenario incidents (the experimenter's view; agents cannot see these)."""
    return [ev.as_dict() for ev in rt.engine.scheduler.upcoming(50)]
