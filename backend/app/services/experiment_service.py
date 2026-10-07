"""Background execution of algorithm experiments.

Runs execute in a process pool (true parallelism, and the live simulation keeps its CPU
time). Progress is tracked in memory for polling and persisted when the experiment ends.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings
from app.db.repository import Repository, new_id
from app.metrics.experiment_runner import aggregate, build_payloads, fairness_report, run_single
from app.simulation.engine import SimulationEngine
from app.simulation.scenarios import ScenarioConfig

log = logging.getLogger("fleetmind.experiments")


@dataclass
class ExperimentJob:
    id: str
    name: str
    scenario: ScenarioConfig
    algorithms: list[str]
    repetitions: int
    duration_s: float
    status: str = "running"
    total: int = 0
    done: int = 0
    results: list[dict] = field(default_factory=list)
    aggregates: dict | None = None
    fairness: dict | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def as_dict(self, include_results: bool = True) -> dict[str, Any]:
        data = {
            "id": self.id, "name": self.name, "scenario_key": self.scenario.key, "seed": self.scenario.seed,
            "algorithms": self.algorithms, "repetitions": self.repetitions, "duration_s": self.duration_s,
            "status": self.status, "progress": round(self.done / self.total, 4) if self.total else 0.0,
            "done": self.done, "total": self.total, "aggregates": self.aggregates, "fairness": self.fairness,
            "error": self.error, "config": self.scenario.model_dump(), "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
        if include_results:
            data["results"] = [{k: r[k] for k in ("algorithm", "repetition", "seed", "wall_time_s", "metrics",
                                                  "timeseries")} for r in self.results]
        return data


class ExperimentService:
    def __init__(self, settings: Settings, repo: Repository | None) -> None:
        self.settings = settings
        self.repo = repo
        self.jobs: dict[str, ExperimentJob] = {}
        self._executor: ProcessPoolExecutor | None = None

    def _pool(self) -> ProcessPoolExecutor | None:
        workers = self.settings.experiment_workers
        if workers <= 0:
            return None
        if self._executor is None:
            # "spawn" gives workers a clean interpreter (no inherited event loop or threads), on every OS.
            self._executor = ProcessPoolExecutor(max_workers=min(workers, os.cpu_count() or 1),
                                                 mp_context=multiprocessing.get_context("spawn"))
        return self._executor

    async def launch(self, scenario: ScenarioConfig, algorithms: list[str], repetitions: int, duration_s: float,
                     name: str | None = None) -> ExperimentJob:
        scenario = scenario.model_copy(update={"demo": False, "duration_s": duration_s})
        job = ExperimentJob(new_id(), name or f"{scenario.name} · seed {scenario.seed}", scenario, algorithms,
                            repetitions, duration_s)
        job.total = len(algorithms) * repetitions
        self.jobs[job.id] = job
        if self.repo is not None:
            try:
                await asyncio.to_thread(self.repo.create_experiment, job.id, job.name, scenario.model_dump(),
                                        algorithms, repetitions, duration_s)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not persist experiment: %s", exc)
        asyncio.create_task(self._run(job), name=f"experiment-{job.id}")
        return job

    async def _run(self, job: ExperimentJob) -> None:
        payloads = build_payloads(job.scenario, job.algorithms, job.repetitions, job.duration_s)
        loop = asyncio.get_running_loop()
        try:
            pool = self._pool()
            if pool is None:
                futures = [asyncio.to_thread(run_single, p) for p in payloads]
            else:
                futures = [loop.run_in_executor(pool, run_single, p) for p in payloads]
            for fut in asyncio.as_completed(futures):
                result = await fut
                job.results.append(result)
                job.done += 1
                if self.repo is not None:
                    asyncio.create_task(asyncio.to_thread(self.repo.update_experiment_progress, job.id,
                                                          job.done / job.total))
            order = {a: i for i, a in enumerate(job.algorithms)}
            job.results.sort(key=lambda r: (r["repetition"], order[r["algorithm"]]))
            job.aggregates = aggregate(job.results)
            job.fairness = fairness_report(job.results)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            if self.repo is not None:
                env_engine = await asyncio.to_thread(SimulationEngine, job.scenario.model_copy(update={"robots": 1}))
                await asyncio.to_thread(self.repo.complete_experiment, job.id, job.results, job.aggregates,
                                        job.fairness, env_engine)
        except Exception as exc:  # noqa: BLE001
            log.exception("experiment %s failed", job.id)
            job.status = "failed"
            job.error = f"{exc.__class__.__name__}: {exc}"
            if self.repo is not None:
                await asyncio.to_thread(self.repo.fail_experiment, job.id, job.error)

    async def get(self, exp_id: str) -> dict | None:
        job = self.jobs.get(exp_id)
        if job is not None:
            return job.as_dict()
        if self.repo is None:
            return None
        return await asyncio.to_thread(self.repo.get_experiment, exp_id)

    async def list(self) -> list[dict]:
        items: dict[str, dict] = {}
        if self.repo is not None:
            try:
                for row in await asyncio.to_thread(self.repo.list_experiments):
                    items[row["id"]] = row
            except Exception as exc:  # noqa: BLE001
                log.warning("listing experiments failed: %s", exc)
        for job in self.jobs.values():
            items[job.id] = job.as_dict(include_results=False)
        return sorted(items.values(), key=lambda x: x["created_at"] or "", reverse=True)

    async def delete(self, exp_id: str) -> bool:
        removed = self.jobs.pop(exp_id, None) is not None
        if self.repo is not None:
            removed = await asyncio.to_thread(self.repo.delete_experiment, exp_id) or removed
        return removed

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
