from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_runtime
from app.services.simulation_service import SimulationRuntime
from app.simulation.orders import OrderStatus
from app.simulation.snapshot import order_detail

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def orders(status: OrderStatus | None = None, limit: int = Query(200, ge=1, le=1000),
                 rt: SimulationRuntime = Depends(get_runtime)):
    items = [o for o in rt.engine.orders.all() if status is None or o.status == status]
    items.sort(key=lambda o: o.seq, reverse=True)
    return [order_detail(rt.engine, o.id) for o in items[:limit]]


@router.get("/{order_id}")
async def order(order_id: str, rt: SimulationRuntime = Depends(get_runtime)):
    data = order_detail(rt.engine, order_id)
    if data is None:
        raise HTTPException(404, f"order {order_id} not found")
    data["timeline"] = [e.as_dict() for e in rt.engine.timeline.query(order_id=order_id, limit=60)]
    return data
