from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/simulation")
async def simulation_stream(ws: WebSocket):
    """Real-time channel.

    Server → client: one ``static`` message (the map) per run, then ``snapshot`` messages at
    ~15 Hz with robot positions, open orders, road state, KPIs and new timeline entries.
    Client → server: ``{"type": "focus", "robot_id": "R-07"}`` to receive inspector detail
    for one robot in every snapshot; ``{"type": "resync"}`` to request the map again.
    """
    await ws.accept()
    try:
        await ws.app.state.runtime.serve(ws)
    except WebSocketDisconnect:
        pass
