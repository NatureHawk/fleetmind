"""Batched persistence of a live run (timeline + metric samples + final records)."""

from __future__ import annotations

import asyncio
import logging

from app.core.event_bus import Topics
from app.db.repository import Repository
from app.simulation.engine import SimulationEngine
from app.simulation.timeline import TimelineEntry

log = logging.getLogger("fleetmind.persistence")


class RunRecorder:
    def __init__(self, repo: Repository, engine: SimulationEngine) -> None:
        self.repo = repo
        self.engine = engine
        self.run_id: str | None = None
        self._buffer: list[TimelineEntry] = []
        self._samples_saved = 0
        self._flushing = False
        self.failed = False
        engine.bus.subscribe(Topics.TIMELINE, self._buffer.append)

    async def begin(self) -> None:
        if self.run_id is not None or self.failed:
            return
        try:
            self.run_id = await asyncio.to_thread(self.repo.create_run, self.engine, "live")
        except Exception as exc:  # noqa: BLE001
            self.failed = True
            log.warning("could not create run record: %s", exc)

    async def flush(self) -> None:
        if self.run_id is None or self._flushing or self.failed:
            return
        entries, self._buffer[:] = list(self._buffer), []
        samples = self.engine.metrics.samples[self._samples_saved:]
        self._samples_saved += len(samples)
        if not entries and not samples:
            return
        self._flushing = True
        try:
            await asyncio.to_thread(self._write, entries, samples)
        except Exception as exc:  # noqa: BLE001
            log.warning("persisting run batch failed: %s", exc)
        finally:
            self._flushing = False

    def _write(self, entries: list[TimelineEntry], samples: list[dict]) -> None:
        assert self.run_id is not None
        self.repo.add_events(self.run_id, entries)
        self.repo.add_metric_samples(self.run_id, samples)

    async def finish(self, status: str = "completed") -> None:
        if self.run_id is None or self.failed:
            return
        while self._flushing:
            await asyncio.sleep(0.02)
        await self.flush()
        try:
            await asyncio.to_thread(self.repo.finish_run, self.run_id, self.engine, status)
        except Exception as exc:  # noqa: BLE001
            log.warning("finalising run failed: %s", exc)
