"""The live simulation runtime.

Owns the current :class:`SimulationEngine`, advances it in fixed ticks paced by the wall
clock and the speed multiplier, and streams state to WebSocket clients. Commands from the
REST API and the loop both run on the asyncio event loop, so the engine is never touched
concurrently.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import Settings
from app.core.simulation_clock import FixedStepPacer
from app.db.repository import Repository
from app.simulation.engine import SimulationEngine
from app.simulation.scenarios import ScenarioConfig, get_scenario
from app.simulation.snapshot import live_snapshot, robot_detail, static_payload

log = logging.getLogger("fleetmind.runtime")

SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)
FLUSH_INTERVAL_S = 2.0


@dataclass(eq=False)
class Client:
    ws: WebSocket
    cursor: int = 0
    focus: str | None = None
    version: int = -1
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=4))


class SimulationRuntime:
    def __init__(self, settings: Settings, repo: Repository | None) -> None:
        self.settings = settings
        self.repo = repo
        self.pacer = FixedStepPacer(settings.base_ticks_per_second)
        self.clients: set[Client] = set()
        self.running = False
        self.speed = 1.0
        self.version = 0
        self.engine: SimulationEngine = None  # type: ignore[assignment]
        self.recorder = None
        self._task: asyncio.Task | None = None
        self._static_cache: str | None = None
        self.load(get_scenario(settings.default_scenario, seed=settings.default_seed))

    # Lifecycle -------------------------------------------------------------------------
    def load(self, config: ScenarioConfig) -> None:
        self.engine = SimulationEngine(config, tick_seconds=self.settings.tick_seconds)
        self.running = False
        self.speed = config.speed if config.speed in SPEEDS else 1.0
        self.pacer.reset()
        self.version += 1
        self._static_cache = None
        if self.repo is not None and self.settings.persist_live_runs:
            from app.services.persistence import RunRecorder
            self.recorder = RunRecorder(self.repo, self.engine)
        else:
            self.recorder = None

    async def startup(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="simulation-loop")

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.recorder:
            await self.recorder.finish("aborted" if self.running else "completed")

    # Commands --------------------------------------------------------------------------
    async def start(self) -> None:
        if self.recorder:
            await self.recorder.begin()
        self.running = True
        self.pacer.reset()

    def pause(self) -> None:
        self.running = False

    async def step(self, ticks: int) -> None:
        if self.recorder:
            await self.recorder.begin()
        for _ in range(ticks):
            self.engine.step()
        self.engine.pause_requested = False

    async def reset(self, config: ScenarioConfig) -> None:
        if self.recorder:
            await self.recorder.finish("completed")
        self.load(config)

    def set_speed(self, speed: float) -> None:
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {list(SPEEDS)}")
        self.speed = speed

    def status(self) -> dict[str, Any]:
        e = self.engine
        return {
            "running": self.running,
            "speed": self.speed,
            "speeds": list(SPEEDS),
            "t": round(e.now, 2),
            "tick": e.clock.tick,
            "tick_seconds": e.clock.dt,
            "sim_seconds_per_second_at_1x": self.settings.base_ticks_per_second * e.clock.dt,
            "scenario": e.config.model_dump(),
            "algorithm": e.routes.algorithm,
            "heuristic": e.routes.heuristic,
            "run_id": self.recorder.run_id if self.recorder else None,
            "version": self.version,
            "fingerprints": e.fingerprints,
            "clients": len(self.clients),
        }

    # Real-time channel -----------------------------------------------------------------
    def static_message(self) -> str:
        if self._static_cache is None:
            payload = {"type": "static", "version": self.version, "map": static_payload(self.engine),
                       "status": self.status()}
            self._static_cache = json.dumps(payload, separators=(",", ":"))
        return self._static_cache

    async def serve(self, ws: WebSocket) -> None:
        client = Client(ws)
        self.clients.add(client)
        sender = asyncio.create_task(self._sender(client))
        try:
            while True:
                msg = await ws.receive_json()
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "focus":
                    rid = msg.get("robot_id")
                    client.focus = rid if isinstance(rid, str) and self.engine.fleet.get(rid) else None
                elif msg.get("type") == "resync":
                    client.version = -1
        finally:
            self.clients.discard(client)
            sender.cancel()

    async def _sender(self, client: Client) -> None:
        try:
            while True:
                text = await client.queue.get()
                await client.ws.send_text(text)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - client went away
            self.clients.discard(client)

    def _enqueue(self, client: Client, text: str) -> None:
        if client.queue.full():
            try:
                client.queue.get_nowait()  # drop the oldest frame for slow clients
            except asyncio.QueueEmpty:
                pass
        client.queue.put_nowait(text)

    def broadcast(self) -> None:
        if not self.clients:
            return
        for client in list(self.clients):
            if client.version != self.version:
                self._enqueue(client, self.static_message())
                client.version = self.version
                client.cursor = 0
            snap = live_snapshot(self.engine, client.cursor, running=self.running, speed=self.speed)
            client.cursor = snap["last_seq"]
            if client.focus:
                snap["focus"] = robot_detail(self.engine, client.focus)
            self._enqueue(client, json.dumps(snap, separators=(",", ":")))

    # Loop ------------------------------------------------------------------------------
    async def _loop(self) -> None:
        last = time.perf_counter()
        last_broadcast = 0.0
        last_flush = last
        interval = 1.0 / self.settings.broadcast_hz
        while True:
            await asyncio.sleep(1 / 120)
            now = time.perf_counter()
            elapsed, last = now - last, now
            try:
                if self.running:
                    for _ in range(self.pacer.steps_due(elapsed, self.speed)):
                        self.engine.step()
                        if self.engine.pause_requested:
                            self.engine.pause_requested = False
                            self.running = False
                            break
                if now - last_broadcast >= interval:
                    last_broadcast = now
                    self.broadcast()
                if self.recorder and now - last_flush >= FLUSH_INTERVAL_S:
                    last_flush = now
                    asyncio.create_task(self.recorder.flush())
            except Exception:  # noqa: BLE001 - never let the loop die silently
                log.exception("simulation loop error; pausing")
                self.running = False
