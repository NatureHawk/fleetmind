"""Everything an agent may perceive or act through during a tick."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.charging import ChargingNetwork
from app.agents.communication import FleetChannel
from app.core.event_bus import EventBus
from app.planning.route_service import RouteService
from app.simulation.environment import Environment
from app.simulation.orders import OrderBook
from app.simulation.timeline import Timeline
from app.simulation.world_model import WorldModel


@dataclass
class AgentContext:
    env: Environment
    world: WorldModel
    routes: RouteService
    charging: ChargingNetwork
    channel: FleetChannel
    orders: OrderBook
    timeline: Timeline
    bus: EventBus
    dt: float
    now: float = 0.0
