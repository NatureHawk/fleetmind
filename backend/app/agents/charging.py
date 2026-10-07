"""Charging infrastructure shared by the fleet.

Stations have a fixed number of slots. Robots *reserve* a station when they decide to
charge, *queue* if all slots are busy on arrival, and are promoted FIFO when a slot frees.
Choosing a station weighs travel time against the expected queue — a simple form of
multi-agent resource coordination that keeps robots from piling onto the nearest charger.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.agents.battery import ESTIMATE_DETOUR, estimate_energy
from app.simulation.environment import Environment, NodeKind

AVERAGE_SESSION_S = 180.0


@dataclass
class ChargingStation:
    node: int
    name: str
    slots: int
    charging: list[str] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)
    reserved: list[str] = field(default_factory=list)
    unavailable_until: float = 0.0
    sessions: int = 0
    energy_delivered_wh: float = 0.0

    def is_available(self, now: float) -> bool:
        return now >= self.unavailable_until

    @property
    def load(self) -> int:
        return len(self.charging) + len(self.queue) + len(self.reserved)

    def expected_wait(self) -> float:
        backlog = max(0, len(self.charging) + len(self.queue) + len(self.reserved) - self.slots + 1)
        return backlog * AVERAGE_SESSION_S / self.slots

    def as_dict(self, now: float) -> dict:
        return {
            "node": self.node,
            "name": self.name,
            "slots": self.slots,
            "charging": list(self.charging),
            "queue": list(self.queue),
            "reserved": list(self.reserved),
            "available": self.is_available(now),
            "unavailable_until": self.unavailable_until if not self.is_available(now) else None,
            "occupancy": len(self.charging),
            "sessions": self.sessions,
            "energy_delivered_wh": round(self.energy_delivered_wh, 1),
        }


@dataclass(slots=True)
class ChargerChoice:
    station: ChargingStation
    eta_s: float
    wait_s: float
    energy_wh: float
    reachable: bool


class ChargingNetwork:
    def __init__(self, env: Environment) -> None:
        self.env = env
        self.stations: dict[int, ChargingStation] = {
            n.id: ChargingStation(n.id, n.name, env.charger_slots.get(n.id, 2))
            for n in env.nodes_of_kind(NodeKind.CHARGER)
        }
        nodes = env.nodes
        self._nearest_m = [
            min(math.hypot(nodes[c].x - n.x, nodes[c].y - n.y) for c in self.stations) if self.stations else 0.0
            for n in nodes
        ]

    # Estimates ---------------------------------------------------------------------------
    def nearest_distance(self, node: int) -> float:
        """Straight-line distance from ``node`` to the closest charger."""
        return self._nearest_m[node]

    def reserve_energy(self, node: int, rate_wh_per_m: float) -> float:
        """Estimated energy to reach *some* charger from ``node`` (kept in reserve)."""
        return estimate_energy(self._nearest_m[node], rate_wh_per_m)

    def select(self, origin: int, battery_wh: float, rate_wh_per_m: float, speed_mps: float, now: float,
               exclude: tuple[int, ...] = ()) -> ChargerChoice | None:
        best: ChargerChoice | None = None
        best_score = math.inf
        o = self.env.nodes[origin]
        for st in self.stations.values():
            if st.node in exclude or not st.is_available(now):
                continue
            n = self.env.nodes[st.node]
            straight = math.hypot(n.x - o.x, n.y - o.y)
            energy = estimate_energy(straight, rate_wh_per_m)
            eta = straight * ESTIMATE_DETOUR / speed_mps
            wait = st.expected_wait()
            reachable = energy <= battery_wh
            score = eta + wait + (0.0 if reachable else 1e6 + energy)
            if score < best_score:
                best_score = score
                best = ChargerChoice(st, eta, wait, energy, reachable)
        return best

    # Reservation lifecycle -------------------------------------------------------------
    def station_of(self, robot_id: str) -> ChargingStation | None:
        for st in self.stations.values():
            if robot_id in st.charging or robot_id in st.queue or robot_id in st.reserved:
                return st
        return None

    def reserve(self, node: int, robot_id: str) -> None:
        self.cancel(robot_id)
        self.stations[node].reserved.append(robot_id)

    def cancel(self, robot_id: str) -> None:
        for st in self.stations.values():
            if robot_id in st.reserved:
                st.reserved.remove(robot_id)
            if robot_id in st.queue:
                st.queue.remove(robot_id)

    def arrive(self, node: int, robot_id: str, now: float) -> bool:
        """Robot arrives at a station. Returns True if it starts charging, False if queued."""
        st = self.stations[node]
        if robot_id in st.reserved:
            st.reserved.remove(robot_id)
        if st.is_available(now) and len(st.charging) < st.slots and not st.queue:
            st.charging.append(robot_id)
            st.sessions += 1
            return True
        if robot_id not in st.queue:
            st.queue.append(robot_id)
        return False

    def is_charging(self, robot_id: str) -> bool:
        return any(robot_id in st.charging for st in self.stations.values())

    def finish(self, robot_id: str) -> None:
        for st in self.stations.values():
            if robot_id in st.charging:
                st.charging.remove(robot_id)

    def record_energy(self, robot_id: str, wh: float) -> None:
        for st in self.stations.values():
            if robot_id in st.charging:
                st.energy_delivered_wh += wh
                return

    def promote(self, now: float) -> list[tuple[str, ChargingStation]]:
        """Move queued robots into free slots (FIFO). Returns the robots that started."""
        started = []
        for st in self.stations.values():
            while st.queue and len(st.charging) < st.slots and st.is_available(now):
                rid = st.queue.pop(0)
                st.charging.append(rid)
                st.sessions += 1
                started.append((rid, st))
        return started

    def mark_unavailable(self, node: int, until: float) -> ChargingStation:
        st = self.stations[node]
        st.unavailable_until = max(st.unavailable_until, until)
        return st
