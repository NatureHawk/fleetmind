from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_runtime
from app.services.simulation_service import SimulationRuntime
from app.simulation.environment import ROAD_SPEED_FACTOR, NodeKind
from app.simulation.snapshot import static_payload

router = APIRouter(prefix="/environment", tags=["environment"])


@router.get("")
async def environment(rt: SimulationRuntime = Depends(get_runtime)):
    return static_payload(rt.engine)


@router.get("/roads/{road_id}")
async def road(road_id: int, rt: SimulationRuntime = Depends(get_runtime)):
    e = rt.engine
    if not 0 <= road_id < len(e.env.roads):
        raise HTTPException(404, f"road {road_id} not found")
    r = e.env.roads[road_id]
    users = [rb.id for rb in e.fleet.robots if road_id in rb.remaining_roads()]
    return {
        "id": r.id,
        "name": r.name,
        "source": r.a,
        "destination": r.b,
        "source_name": e.env.nodes[r.a].name,
        "destination_name": e.env.nodes[r.b].name,
        "distance": r.length,
        "road_class": r.road_class.value,
        "speed_factor": ROAD_SPEED_FACTOR[r.road_class],
        "traffic_level": r.traffic.label,
        "known_traffic_level": e.world.known_traffic[r.id].label,
        "travel_time": round(r.travel_time, 2),
        "planner_cost": round(e.world.road_cost(r.id), 2),
        "energy_cost": round(r.energy_cost, 2),
        "blocked": r.blocked,
        "blocked_known_to_fleet": e.world.is_blocked(r.id),
        "status": "closed" if r.blocked else "open",
        "robots_routed": users,
    }


@router.get("/nodes/{node_id}")
async def node(node_id: int, rt: SimulationRuntime = Depends(get_runtime)):
    e = rt.engine
    if not 0 <= node_id < len(e.env.nodes):
        raise HTTPException(404, f"node {node_id} not found")
    n = e.env.nodes[node_id]
    data = {"id": n.id, "name": n.name, "kind": n.kind.value, "zone": n.zone.value, "x": n.x, "y": n.y,
            "degree": e.env.degree(n.id),
            "roads": [{"id": rid, "name": e.env.roads[rid].name, "to": e.env.nodes[v].name}
                      for v, rid in e.env.adjacency[n.id]]}
    if n.kind == NodeKind.CHARGER:
        st = e.charging.stations[n.id]
        data["station"] = st.as_dict(e.now) | {"available_capacity": max(0, st.slots - len(st.charging)),
                                               "inbound": list(st.reserved)}
    elif n.kind == NodeKind.WAREHOUSE:
        data["orders_waiting"] = [o.id for o in e.orders.open_orders() if o.source == n.id and o.picked_up_at is None]
    elif n.kind == NodeKind.CUSTOMER:
        data["orders_inbound"] = [o.id for o in e.orders.open_orders() if o.destination == n.id]
    return data


@router.get("/chargers")
async def chargers(rt: SimulationRuntime = Depends(get_runtime)):
    e = rt.engine
    return [st.as_dict(e.now) for st in e.charging.stations.values()]
