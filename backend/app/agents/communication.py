"""Fleet communication channel.

Agents (and infrastructure such as the city traffic feed or the operator console) publish
observations here. The channel updates the shared world model and, if belief actually
changed, broadcasts a :class:`WorldChange` so every agent can check whether its current
plan is still valid. Duplicate reports are absorbed: only the first robot to see a closure
changes the shared state.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.core.event_bus import EventBus, Topics
from app.simulation.environment import TrafficLevel
from app.simulation.world_model import WorldModel


@dataclass(slots=True)
class FleetMessage:
    seq: int
    t: float
    sender: str
    kind: str
    road_ids: list[int]
    detail: str = ""

    def as_dict(self) -> dict:
        return {"seq": self.seq, "t": round(self.t, 2), "sender": self.sender, "kind": self.kind,
                "road_ids": self.road_ids, "detail": self.detail}


@dataclass(slots=True)
class WorldChange:
    kind: str                      # "blocked" | "reopened" | "traffic"
    road_ids: list[int]
    sender: str
    message_seq: int
    levels: dict[int, tuple[TrafficLevel, TrafficLevel]] = field(default_factory=dict)  # road -> (old, new)


class FleetChannel:
    def __init__(self, world: WorldModel, bus: EventBus) -> None:
        self.world = world
        self.bus = bus
        self.messages: deque[FleetMessage] = deque(maxlen=300)
        self._seq = 0
        self.now = 0.0

    def _send(self, sender: str, kind: str, road_ids: list[int], detail: str = "") -> FleetMessage:
        self._seq += 1
        msg = FleetMessage(self._seq, self.now, sender, kind, road_ids, detail)
        self.messages.append(msg)
        return msg

    @property
    def message_count(self) -> int:
        return self._seq

    def report_road_blocked(self, sender: str, road_id: int) -> bool:
        if not self.world.mark_blocked(road_id, True):
            return False
        msg = self._send(sender, "ROAD_BLOCKED", [road_id])
        self.bus.publish(Topics.WORLD_CHANGED, WorldChange("blocked", [road_id], sender, msg.seq))
        return True

    def announce_reopened(self, sender: str, road_id: int) -> bool:
        if not self.world.mark_blocked(road_id, False):
            return False
        msg = self._send(sender, "ROAD_REOPENED", [road_id])
        self.bus.publish(Topics.WORLD_CHANGED, WorldChange("reopened", [road_id], sender, msg.seq))
        return True

    def announce_traffic(self, sender: str, updates: list[tuple[int, TrafficLevel]]) -> bool:
        levels: dict[int, tuple[TrafficLevel, TrafficLevel]] = {}
        for road_id, level in updates:
            old = self.world.known_traffic[road_id]
            if self.world.update_traffic(road_id, level):
                levels[road_id] = (old, level)
        if not levels:
            return False
        msg = self._send(sender, "TRAFFIC_UPDATE", list(levels))
        self.bus.publish(Topics.WORLD_CHANGED, WorldChange("traffic", list(levels), sender, msg.seq, levels))
        return True
