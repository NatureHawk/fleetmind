from __future__ import annotations

from pydantic import BaseModel, Field

from app.simulation.events import EventType


class EventRequest(BaseModel):
    """A manual (operator) event. Omitted targets are chosen automatically where sensible —
    e.g. ``ROAD_BLOCKED`` without ``road_id`` closes a road ahead on the busiest active route."""

    type: EventType
    road_id: int | None = Field(None, ge=0)
    road_ids: list[int] | None = None
    robot_id: str | None = None
    order_id: str | None = None
    node_id: int | None = Field(None, ge=0)
    level: str | float | None = Field(None, description="Traffic level name, or battery fraction 0–1")
    priority: str | None = None
    source: int | None = Field(None, ge=0, description="Warehouse node for NEW_ORDER")
    destination: int | None = Field(None, ge=0, description="Customer node for NEW_ORDER")
    duration_s: float | None = Field(None, gt=0, le=7200)
    reason: str | None = Field(None, max_length=80)
