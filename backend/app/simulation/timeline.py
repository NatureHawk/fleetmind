"""The decision timeline: an append-only, explainable log of what happened and why.

Every allocation, plan, replan, environment change, battery decision and coordination
message becomes a :class:`TimelineEntry`. The UI's live feed, the robot inspector and the
persisted run history are all views of this log.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.event_bus import EventBus, Topics


class Category(StrEnum):
    ENVIRONMENT = "environment"
    ORDER = "order"
    ALLOCATION = "allocation"
    PLANNING = "planning"
    REPLANNING = "replanning"
    BATTERY = "battery"
    COORDINATION = "coordination"
    AGENT = "agent"
    SYSTEM = "system"
    DEMO = "demo"


class Severity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(slots=True)
class TimelineEntry:
    seq: int
    t: float
    category: Category
    kind: str
    severity: Severity
    message: str
    robot_id: str | None = None
    order_id: str | None = None
    road_id: int | None = None
    node_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "t": round(self.t, 2),
            "category": self.category.value,
            "kind": self.kind,
            "severity": self.severity.value,
            "message": self.message,
            "robot_id": self.robot_id,
            "order_id": self.order_id,
            "road_id": self.road_id,
            "node_id": self.node_id,
            "data": self.data,
        }


class Timeline:
    def __init__(self, bus: EventBus | None = None, maxlen: int = 5000) -> None:
        self.entries: deque[TimelineEntry] = deque(maxlen=maxlen)
        self.bus = bus
        self._seq = 0
        self.now = 0.0

    @property
    def last_seq(self) -> int:
        return self._seq

    def add(self, category: Category, kind: str, message: str, *, severity: Severity = Severity.INFO,
            robot_id: str | None = None, order_id: str | None = None, road_id: int | None = None,
            node_id: int | None = None, data: dict[str, Any] | None = None) -> TimelineEntry:
        self._seq += 1
        entry = TimelineEntry(self._seq, self.now, category, kind, severity, message, robot_id, order_id,
                              road_id, node_id, data or {})
        self.entries.append(entry)
        if self.bus is not None:
            self.bus.publish(Topics.TIMELINE, entry)
        return entry

    def since(self, seq: int, limit: int = 500) -> list[TimelineEntry]:
        if seq >= self._seq:
            return []
        out = [e for e in self.entries if e.seq > seq]
        return out[-limit:]

    def query(self, *, robot_id: str | None = None, category: str | None = None, kind: str | None = None,
              order_id: str | None = None, limit: int = 200) -> list[TimelineEntry]:
        out = []
        for e in reversed(self.entries):
            if robot_id and e.robot_id != robot_id:
                continue
            if category and e.category != category:
                continue
            if kind and e.kind != kind:
                continue
            if order_id and e.order_id != order_id:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        out.reverse()
        return out
