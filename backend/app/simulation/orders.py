"""Delivery requests: the order model, the order book and the arrival stream."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from app.simulation.environment import REFERENCE_SPEED_MPS, Environment, NodeKind


class Priority(IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return self.name


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


OPEN_STATUSES = (OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT)
CLOSED_STATUSES = (OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.CANCELLED)

# Allowed time = fixed handling allowance + factor × direct travel estimate.
DEADLINE_POLICY = {
    Priority.CRITICAL: (240.0, 1.6),
    Priority.HIGH: (420.0, 2.0),
    Priority.NORMAL: (720.0, 2.5),
    Priority.LOW: (1200.0, 3.0),
}
DETOUR_FACTOR = 1.35  # typical network distance / straight-line distance in generated cities
UNASSIGNED_EXPIRY_GRACE = 300.0


@dataclass
class Order:
    id: str
    seq: int
    source: int
    destination: int
    priority: Priority
    created_at: float
    deadline: float
    status: OrderStatus = OrderStatus.PENDING
    assigned_robot: str | None = None
    assigned_at: float | None = None
    picked_up_at: float | None = None
    delivered_at: float | None = None
    failure_reason: str | None = None
    assignment_count: int = 0
    explanation: dict | None = None
    history: list[tuple[float, str]] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def delivery_time(self) -> float | None:
        return None if self.delivered_at is None else self.delivered_at - self.created_at

    @property
    def late(self) -> bool:
        return self.delivered_at is not None and self.delivered_at > self.deadline

    def log(self, t: float, message: str) -> None:
        self.history.append((t, message))


def direct_travel_estimate(env: Environment, a: int, b: int) -> float:
    na, nb = env.nodes[a], env.nodes[b]
    return math.hypot(nb.x - na.x, nb.y - na.y) * DETOUR_FACTOR / REFERENCE_SPEED_MPS


def deadline_for(env: Environment, source: int, destination: int, priority: Priority, created_at: float) -> float:
    allowance, factor = DEADLINE_POLICY[priority]
    return created_at + allowance + factor * direct_travel_estimate(env, source, destination)


class OrderBook:
    """Single source of truth for orders; the allocator is its only writer of assignments."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self._seq = 0

    def create(self, env: Environment, source: int, destination: int, priority: Priority, now: float,
               deadline: float | None = None) -> Order:
        self._seq += 1
        order = Order(
            id=f"ORD-{self._seq:03d}",
            seq=self._seq,
            source=source,
            destination=destination,
            priority=priority,
            created_at=now,
            deadline=deadline if deadline is not None else deadline_for(env, source, destination, priority, now),
        )
        order.log(now, "created")
        self.orders[order.id] = order
        return order

    def get(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def pending(self) -> list[Order]:
        """Pending orders in dispatch order: priority, then earliest deadline, then FIFO."""
        return sorted((o for o in self.orders.values() if o.status == OrderStatus.PENDING),
                      key=lambda o: (-o.priority, o.deadline, o.seq))

    def open_orders(self) -> list[Order]:
        return [o for o in self.orders.values() if o.is_open]

    def all(self) -> list[Order]:
        return list(self.orders.values())


class OrderStream:
    """Deterministic arrival process for delivery requests.

    An initial batch is released at t≈0, then requests arrive as a Poisson process with
    ``rate_per_min`` until ``max_orders`` have been created. Draws come from a dedicated
    random stream, so arrivals are identical across algorithms for the same seed.
    """

    def __init__(self, env: Environment, rng: random.Random, *, initial: int, rate_per_min: float,
                 max_orders: int, priority_weights: dict[Priority, float]) -> None:
        self.env = env
        self.rng = rng
        self.rate_per_s = max(rate_per_min, 0.0) / 60.0
        self.max_orders = max_orders
        self.created = 0
        self.warehouses = [n.id for n in env.nodes_of_kind(NodeKind.WAREHOUSE)]
        self.customers = [n.id for n in env.nodes_of_kind(NodeKind.CUSTOMER)]
        self.priorities = list(priority_weights.keys())
        self.weights = list(priority_weights.values())
        self._queue: list[float] = [i * 2.0 for i in range(min(initial, max_orders))]
        self._next_poisson = self._sample_gap(0.0)

    def _sample_gap(self, t: float) -> float:
        if self.rate_per_s <= 0:
            return math.inf
        return t + self.rng.expovariate(self.rate_per_s)

    def due(self, now: float) -> list[tuple[int, int, Priority]]:
        out: list[tuple[int, int, Priority]] = []
        while self._queue and self._queue[0] <= now and self.created < self.max_orders:
            self._queue.pop(0)
            out.append(self._draw())
        while self._next_poisson <= now and self.created < self.max_orders:
            out.append(self._draw())
            self._next_poisson = self._sample_gap(self._next_poisson)
        return out

    def _draw(self) -> tuple[int, int, Priority]:
        self.created += 1
        source = self.rng.choice(self.warehouses)
        destination = self.rng.choice(self.customers)
        priority = self.rng.choices(self.priorities, weights=self.weights, k=1)[0]
        return source, destination, priority
