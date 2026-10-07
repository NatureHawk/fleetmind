"""A synchronous, deterministic publish/subscribe bus (Observer pattern).

The simulation is single-threaded and must be reproducible, so handlers run inline and in
subscription order. Subsystems (fleet coordination, metrics, persistence, timeline) react
to domain events without knowing about each other.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

Handler = Callable[[Any], None]
WildcardHandler = Callable[[str, Any], None]


class Topics:
    PLAN_COMPLETED = "planning.completed"
    WORLD_CHANGED = "world.changed"
    ROBOT_REPLANNED = "robot.replanned"
    ORDER_CREATED = "order.created"
    ORDER_ASSIGNED = "order.assigned"
    ORDER_DELIVERED = "order.delivered"
    ORDER_FAILED = "order.failed"
    TIMELINE = "timeline.entry"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._wildcard: list[WildcardHandler] = []

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        self._subscribers[topic].append(handler)
        return lambda: self._subscribers[topic].remove(handler)

    def subscribe_all(self, handler: WildcardHandler) -> Callable[[], None]:
        self._wildcard.append(handler)
        return lambda: self._wildcard.remove(handler)

    def publish(self, topic: str, payload: Any = None) -> None:
        for handler in tuple(self._subscribers.get(topic, ())):
            handler(payload)
        for handler in tuple(self._wildcard):
            handler(topic, payload)
